"""
Supplier Ordering API Endpoints

Provides REST API endpoints for the monthly supplier ordering system.
Enables users to generate recommendations, review orders, adjust quantities,
lock orders, and export data.

Key Features:
- Monthly order recommendation generation
- Paginated listing with filtering and sorting
- Editable quantities and lead time overrides
- Order locking for confirmed orders
- Summary statistics and Excel export
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from typing import Optional
from datetime import datetime
import json
import logging

from backend.database import execute_query, get_database_connection
from backend.supplier_ordering_calculations import generate_monthly_recommendations
from backend.supplier_ordering_models import (
    GenerateRecommendationsRequest,
    GenerateRecommendationsResponse,
    UpdateOrderRequest,
    OrderListResponse,
    SummaryResponse
)
from backend.supplier_ordering_queries import build_orders_query, build_summary_queries
from backend.import_export import import_export_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/supplier-orders", tags=["supplier-orders"])


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/generate", response_model=GenerateRecommendationsResponse)
async def generate_recommendations(request: GenerateRecommendationsRequest):
    """
    Generate monthly supplier order recommendations for all active SKUs.

    This endpoint calls the core calculation engine to analyze all active SKUs
    across both warehouses and generate order recommendations based on:
    - Current inventory levels
    - Time-phased pending orders with confidence scoring
    - Stockout-corrected demand forecasts
    - Dynamic safety stock calculations
    - ABC-XYZ classification service levels

    Args:
        request: Generation parameters (order_month optional)

    Returns:
        Summary of generated recommendations with counts and totals

    Raises:
        HTTPException: If generation fails due to data issues
    """
    try:
        # Generate recommendations using core calculation engine
        result = generate_monthly_recommendations(order_month=request.order_month)

        # Calculate total value of suggestions
        total_value_query = """
            SELECT COALESCE(SUM(soc.suggested_qty * s.cost_per_unit), 0) as total_value
            FROM supplier_order_confirmations soc
            JOIN skus s ON soc.sku_id = s.sku_id
            WHERE soc.order_month = %s
        """

        total_value_result = execute_query(
            total_value_query,
            (result['order_month'],),
            fetch_one=True,
            fetch_all=False
        )

        return GenerateRecommendationsResponse(
            order_month=result['order_month'],
            recommendations_generated=result['total_processed'],
            must_order_count=result['must_order_count'],
            should_order_count=result['should_order_count'],
            optional_count=result['optional_count'],
            skip_count=result['skip_count'],
            total_value=float(total_value_result.get('total_value', 0) if total_value_result else 0)
        )

    except Exception as e:
        logger.error(f"Failed to generate recommendations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate recommendations: {str(e)}"
        )


@router.get("/{order_month}", response_model=OrderListResponse)
async def get_orders(
    order_month: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=5000),
    warehouse: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    urgency: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("urgency_level"),
    sort_order: str = Query("desc")
):
    """
    Get paginated list of supplier order recommendations with filtering.

    Supports filtering by:
    - Warehouse (burnaby/kentucky)
    - Supplier name
    - Urgency level (must_order/should_order/optional/skip)
    - Search query (SKU ID or description)

    Args:
        order_month: Order month in YYYY-MM format
        page: Page number (1-indexed)
        page_size: Items per page (max 500)
        warehouse: Filter by warehouse
        supplier: Filter by supplier
        urgency: Filter by urgency level
        search: Search SKU ID or description
        sort_by: Column to sort by
        sort_order: Sort direction (asc/desc)

    Returns:
        Paginated list of orders with metadata

    Raises:
        HTTPException: If order_month format is invalid
    """
    try:
        # Validate order_month format
        datetime.strptime(order_month, "%Y-%m")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid order_month format. Use YYYY-MM"
        )

    # Build queries using helper function
    data_query, data_params, count_query, count_params = build_orders_query(
        order_month=order_month,
        warehouse=warehouse,
        supplier=supplier,
        urgency=urgency,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size
    )

    # Get filtered count (with all filters applied)
    count_result = execute_query(count_query, count_params, fetch_one=True, fetch_all=False)
    filtered_total = count_result.get('COUNT(*)', 0) if count_result else 0

    # Get unfiltered total (just order_month, no other filters) for DataTables
    unfiltered_query, unfiltered_params, _, _ = build_orders_query(
        order_month=order_month,
        warehouse=None,
        supplier=None,
        urgency=None,
        search=None,
        sort_by=sort_by,
        sort_order=sort_order,
        page=1,
        page_size=1
    )
    unfiltered_count_query = f"SELECT COUNT(*) FROM ({unfiltered_query}) as subquery"
    unfiltered_result = execute_query(unfiltered_count_query, unfiltered_params, fetch_one=True, fetch_all=False)
    unfiltered_total = unfiltered_result.get('COUNT(*)', 0) if unfiltered_result else 0

    # Execute data query
    orders_raw = execute_query(data_query, data_params, fetch_one=False, fetch_all=True)

    # Convert to dict list with JSON parsing and type conversions
    orders = []
    if orders_raw:
        for row in orders_raw:
            # Row is already a dictionary from execute_query
            # Parse JSON fields if needed
            if row.get('pending_breakdown') and isinstance(row.get('pending_breakdown'), str):
                try:
                    row['pending_breakdown'] = json.loads(row['pending_breakdown'])
                except:
                    row['pending_breakdown'] = None

            # Convert decimal fields to floats for frontend compatibility
            # MySQL returns DECIMAL as Decimal objects, not strings
            from decimal import Decimal
            decimal_fields = ['coverage_months', 'cost_per_unit', 'suggested_value', 'confirmed_value']
            for field in decimal_fields:
                value = row.get(field)
                if value is not None:
                    # Convert both Decimal and str to float
                    if isinstance(value, (Decimal, str)):
                        try:
                            row[field] = float(value)
                        except (ValueError, TypeError):
                            logger.warning(f"Failed to convert {field}: {value} (type: {type(value)})")
                            row[field] = None

            orders.append(row)

    # Get summary statistics for dashboard cards
    summary_query = """
        SELECT
            COUNT(*) as total_skus,
            SUM(CASE WHEN urgency_level = 'must_order' THEN 1 ELSE 0 END) as must_order,
            SUM(CASE WHEN urgency_level = 'should_order' THEN 1 ELSE 0 END) as should_order,
            SUM(CASE WHEN urgency_level = 'optional' THEN 1 ELSE 0 END) as optional,
            SUM(CASE WHEN urgency_level = 'skip' THEN 1 ELSE 0 END) as skip
        FROM supplier_order_confirmations
        WHERE order_month = %s
    """
    summary_result = execute_query(summary_query, (order_month,), fetch_one=True, fetch_all=False)

    summary = {
        'must_order': summary_result.get('must_order', 0) if summary_result else 0,
        'should_order': summary_result.get('should_order', 0) if summary_result else 0,
        'optional': summary_result.get('optional', 0) if summary_result else 0,
        'skip': summary_result.get('skip', 0) if summary_result else 0
    }

    total_pages = (filtered_total + page_size - 1) // page_size if filtered_total > 0 else 0

    return OrderListResponse(
        total=filtered_total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        orders=orders,
        recordsTotal=unfiltered_total,  # For DataTables: total without filters
        recordsFiltered=filtered_total,  # For DataTables: total with filters
        summary=summary  # For dashboard summary cards
    )


@router.put("/{order_id}")
async def update_order(
    order_id: int,
    request: UpdateOrderRequest
):
    """
    Update order quantities, lead time overrides, and notes.

    Allows users to:
    - Adjust confirmed order quantity from system suggestion
    - Override default lead time for specific orders
    - Set custom expected arrival dates
    - Add notes or special instructions

    Locked orders cannot be edited.

    Args:
        order_id: Order confirmation ID
        request: Update parameters

    Returns:
        Updated order record

    Raises:
        HTTPException: If order not found or is locked
    """
    # Check if order exists and is not locked
    check_query = """
        SELECT id, is_locked, locked_by, sku_id, warehouse, order_month
        FROM supplier_order_confirmations
        WHERE id = %s
    """

    order = execute_query(check_query, (order_id,), fetch_one=True, fetch_all=False)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.get('is_locked'):
        raise HTTPException(
            status_code=403,
            detail=f"Order is locked by {order.get('locked_by')}"
        )

    # Build update query dynamically
    updates = []
    params = []

    if request.confirmed_qty is not None:
        updates.append("confirmed_qty = %s")
        params.append(request.confirmed_qty)

    if request.lead_time_days_override is not None:
        updates.append("lead_time_days_override = %s")
        params.append(request.lead_time_days_override)

    if request.expected_arrival_override is not None:
        updates.append("expected_arrival_override = %s")
        params.append(request.expected_arrival_override)

    if request.notes is not None:
        updates.append("notes = %s")
        params.append(request.notes)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Add order_id to params
    params.append(order_id)

    # Execute update
    update_query = f"""
        UPDATE supplier_order_confirmations
        SET {', '.join(updates)}
        WHERE id = %s
    """

    execute_query(update_query, tuple(params), fetch_one=False, fetch_all=False)

    # Return updated record
    return {"message": "Order updated successfully", "order_id": order_id}


@router.post("/{order_id}/lock")
async def lock_order(
    order_id: int,
    username: str = Query("system", description="Username locking the order")
):
    """
    Lock an order to prevent further editing.

    Used when order has been confirmed and should not be modified.
    Locked orders can still be viewed but not edited or deleted.

    Args:
        order_id: Order confirmation ID
        username: User performing the lock

    Returns:
        Confirmation message

    Raises:
        HTTPException: If order not found or already locked
    """
    # Check if order exists
    check_query = """
        SELECT is_locked, locked_by
        FROM supplier_order_confirmations
        WHERE id = %s
    """

    order = execute_query(check_query, (order_id,), fetch_one=True, fetch_all=False)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.get('is_locked'):
        raise HTTPException(
            status_code=400,
            detail=f"Order is already locked by {order.get('locked_by')}"
        )

    # Lock the order
    lock_query = """
        UPDATE supplier_order_confirmations
        SET is_locked = TRUE,
            locked_by = %s,
            locked_at = NOW()
        WHERE id = %s
    """

    execute_query(lock_query, (username, order_id), fetch_one=False, fetch_all=False)

    return {
        "message": "Order locked successfully",
        "order_id": order_id,
        "locked_by": username
    }


@router.post("/{order_id}/unlock")
async def unlock_order(
    order_id: int,
    username: str = Query("system", description="Username unlocking the order")
):
    """
    Unlock an order to allow editing again.

    Use with caution - only unlock orders that were locked by mistake
    or need genuine corrections.

    Args:
        order_id: Order confirmation ID
        username: User performing the unlock

    Returns:
        Confirmation message

    Raises:
        HTTPException: If order not found or not locked
    """
    # Check if order exists and is locked
    check_query = """
        SELECT is_locked
        FROM supplier_order_confirmations
        WHERE id = %s
    """

    order = execute_query(check_query, (order_id,), fetch_one=True, fetch_all=False)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not order.get('is_locked'):
        raise HTTPException(
            status_code=400,
            detail="Order is not locked"
        )

    # Unlock the order
    unlock_query = """
        UPDATE supplier_order_confirmations
        SET is_locked = FALSE,
            locked_by = NULL,
            locked_at = NULL
        WHERE id = %s
    """

    execute_query(unlock_query, (order_id,), fetch_one=False, fetch_all=False)

    return {
        "message": "Order unlocked successfully",
        "order_id": order_id,
        "unlocked_by": username
    }


@router.get("/{order_month}/summary", response_model=SummaryResponse)
async def get_summary(order_month: str):
    """
    Get summary statistics for a specific order month.

    Provides high-level overview including:
    - Total SKU count and urgency breakdown
    - Total suggested vs confirmed order values
    - Locked order count
    - Overdue pending order count
    - Per-supplier summaries

    Args:
        order_month: Order month in YYYY-MM format

    Returns:
        Summary statistics and supplier breakdown

    Raises:
        HTTPException: If order_month format is invalid
    """
    try:
        datetime.strptime(order_month, "%Y-%m")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid order_month format. Use YYYY-MM"
        )

    # Get queries from helper function
    stats_query, supplier_query = build_summary_queries()

    # Execute queries
    stats = execute_query(stats_query, (order_month,), fetch_one=True, fetch_all=False)
    suppliers = execute_query(supplier_query, (order_month,), fetch_one=False, fetch_all=True)

    # Format supplier data (rows are already dictionaries)
    supplier_list = []
    if suppliers:
        for row in suppliers:
            supplier_list.append({
                "supplier": row.get('supplier'),
                "sku_count": row.get('sku_count', 0),
                "total_suggested_qty": row.get('total_suggested_qty', 0),
                "total_confirmed_qty": row.get('total_confirmed_qty', 0),
                "suggested_value": float(row.get('suggested_value', 0)),
                "confirmed_value": float(row.get('confirmed_value', 0)),
                "must_order_count": row.get('must_order_count', 0)
            })

    return SummaryResponse(
        order_month=order_month,
        total_skus=stats.get('total_skus', 0) if stats else 0,
        must_order_count=stats.get('must_order', 0) if stats else 0,
        should_order_count=stats.get('should_order', 0) if stats else 0,
        optional_count=stats.get('optional', 0) if stats else 0,
        skip_count=stats.get('skip', 0) if stats else 0,
        total_suggested_value=float(stats.get('total_suggested', 0)) if stats else 0.0,
        total_confirmed_value=float(stats.get('total_confirmed', 0)) if stats else 0.0,
        locked_orders=stats.get('locked', 0) if stats else 0,
        overdue_pending_total=stats.get('overdue_pending', 0) if stats else 0,
        suppliers=supplier_list
    )


@router.get("/{order_month}/excel")
async def export_to_excel(order_month: str):
    """
    Export supplier order recommendations to Excel with supplier grouping.

    V9.0 Feature: Professional Excel export for monthly supplier ordering
    - Sheet 1: Orders grouped by supplier with Excel outline/grouping
    - Sheet 2: Legend and instructions
    - Color-coded urgency levels
    - Editable fields highlighted in light blue

    Args:
        order_month: Order month in YYYY-MM format

    Returns:
        Excel file for download

    Raises:
        HTTPException: If order_month format is invalid or export fails
    """
    try:
        # Validate order_month format
        datetime.strptime(order_month, "%Y-%m")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid order_month format. Use YYYY-MM"
        )

    try:
        # Generate Excel file
        excel_bytes = import_export_manager.export_supplier_orders_excel(order_month)

        # Prepare filename
        filename = f"supplier_orders_{order_month}.xlsx"

        # Return as downloadable file
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"Failed to generate Excel export: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate Excel export: {str(e)}"
        )
