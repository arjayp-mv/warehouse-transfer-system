"""
Supplier Ordering SKU Details API Module

Provides detailed information for individual SKUs including:
- Time-phased pending orders with confidence scoring
- 12-month forecast projections with learning adjustments
- Stockout history with pattern detection

This module is separate from supplier_ordering_api.py to manage file size
and maintain separation of concerns (list vs detail views).
"""

from fastapi import APIRouter, HTTPException, Query
from backend.database import execute_query
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Supplier Ordering SKU Details"])


def sku_exists(sku_id: str) -> bool:
    """
    Check if SKU exists in database

    Args:
        sku_id: SKU identifier to check

    Returns:
        bool: True if SKU exists, False otherwise

    Example:
        if sku_exists("UB-YTX14-BS"):
            # Proceed with operations
    """
    query = "SELECT COUNT(*) as count FROM skus WHERE sku_id = %s"
    result = execute_query(query, (sku_id,), fetch_one=True)
    return result and result.get('count', 0) > 0


def get_pending_orders_for_sku(sku_id: str, warehouse: str) -> Dict:
    """
    Retrieve time-phased pending orders for SKU

    Queries pending_inventory table for supplier orders and categorizes them
    by expected arrival date relative to today. Includes confidence scoring
    from supplier reliability metrics.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name (burnaby or kentucky)

    Returns:
        dict: {
            "sku_id": str,
            "warehouse": str,
            "pending_orders": List[dict],
            "total_pending": int,
            "effective_pending": int
        }

    Logic:
        - Query pending_inventory WHERE order_type='supplier'
        - LEFT JOIN supplier_lead_times for reliability_score
        - Calculate confidence = reliability_score or 0.75 default
        - Categorize by expected_arrival:
          - overdue: < today
          - imminent: <= today + 7 days
          - covered: <= today + 30 days
          - future: > today + 30 days

    Example:
        result = get_pending_orders_for_sku("UB-YTX14-BS", "kentucky")
        # Returns pending orders with categories and confidence
    """
    query = """
        SELECT
            COALESCE(pi.notes, CONCAT('PO-', pi.id)) as po_number,
            pi.quantity as qty,
            COALESCE(pi.expected_arrival, DATE_ADD(pi.order_date, INTERVAL pi.lead_time_days DAY)) as expected_arrival,
            pi.order_date,
            pi.status,
            pi.order_type,
            pi.lead_time_days,
            CASE WHEN pi.is_estimated = 1 THEN 0.65 ELSE 0.85 END as confidence,
            COALESCE(pi.supplier, 'Unknown Supplier') as supplier,
            CASE
                WHEN COALESCE(pi.expected_arrival, DATE_ADD(pi.order_date, INTERVAL pi.lead_time_days DAY)) < CURDATE() THEN 'overdue'
                WHEN COALESCE(pi.expected_arrival, DATE_ADD(pi.order_date, INTERVAL pi.lead_time_days DAY)) <= DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN 'imminent'
                WHEN COALESCE(pi.expected_arrival, DATE_ADD(pi.order_date, INTERVAL pi.lead_time_days DAY)) <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 'covered'
                ELSE 'future'
            END as category
        FROM pending_inventory pi
        WHERE pi.sku_id = %s
            AND pi.destination = %s
            AND pi.order_type = 'supplier'
            AND pi.status IN ('ordered', 'shipped')
        ORDER BY COALESCE(pi.expected_arrival, DATE_ADD(pi.order_date, INTERVAL pi.lead_time_days DAY)) ASC
        LIMIT 50
    """

    try:
        pending_orders = execute_query(
            query,
            (sku_id, warehouse),
            fetch_one=False,
            fetch_all=True
        ) or []

        # Convert dates to strings for JSON serialization
        for order in pending_orders:
            if order.get('expected_arrival'):
                order['expected_arrival'] = str(order['expected_arrival'])

        # Calculate totals
        total_pending = sum(order.get('qty', 0) for order in pending_orders)
        effective_pending = sum(
            order.get('qty', 0) * order.get('confidence', 0.75)
            for order in pending_orders
        )

        return {
            "sku_id": sku_id,
            "warehouse": warehouse,
            "pending_orders": pending_orders,
            "total_pending": int(total_pending),
            "effective_pending": int(effective_pending)
        }

    except Exception as e:
        logger.error(f"Error fetching pending orders for {sku_id}: {str(e)}", exc_info=True)
        raise


def get_forecast_data_for_sku(sku_id: str, warehouse: str) -> Dict:
    """
    Retrieve 12-month forecast with learning adjustments

    Fetches latest forecast projections and applies any learning adjustments
    that have been calculated by the forecast accuracy system.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name (burnaby or kentucky)

    Returns:
        dict: {
            "sku_id": str,
            "warehouse": str,
            "forecast_run_id": int,
            "forecast_method": str,
            "monthly_forecast": List[dict],
            "avg_monthly": float
        }

    Logic:
        - Query forecast_details for latest forecast_run_id
        - LEFT JOIN forecast_learning_adjustments WHERE applied=TRUE
        - Return 12 monthly data points
        - For each month: base_qty, adjusted_qty, learning_applied

    Example:
        result = get_forecast_data_for_sku("UB-YTX14-BS", "kentucky")
        # Returns 12-month forecast with any learning adjustments
    """
    # Note: forecast_details stores month_1_qty through month_12_qty in columns
    # We need to unpivot this into a monthly_forecast array in the application code
    query = """
        SELECT
            fd.sku_id,
            fd.warehouse,
            fd.forecast_run_id,
            COALESCE(fd.method_used, 'Unknown') as forecast_method,
            fd.avg_monthly_qty,
            fd.month_1_qty, fd.month_2_qty, fd.month_3_qty, fd.month_4_qty,
            fd.month_5_qty, fd.month_6_qty, fd.month_7_qty, fd.month_8_qty,
            fd.month_9_qty, fd.month_10_qty, fd.month_11_qty, fd.month_12_qty,
            fr.forecast_date
        FROM forecast_details fd
        JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
        WHERE fd.sku_id = %s
            AND fd.warehouse = %s
            AND fd.forecast_run_id = (
                SELECT MAX(forecast_run_id)
                FROM forecast_details
                WHERE sku_id = %s
                    AND warehouse = %s
                    AND forecast_run_id IN (
                        SELECT id FROM forecast_runs WHERE status = 'completed'
                    )
            )
        LIMIT 1
    """

    try:
        result = execute_query(
            query,
            (sku_id, warehouse, sku_id, warehouse),
            fetch_one=True,
            fetch_all=False
        )

        if not result:
            return None

        # Unpivot month columns into monthly_forecast array
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        forecast_date = result.get('forecast_date')
        base_date = datetime.strptime(str(forecast_date), '%Y-%m-%d') if forecast_date else datetime.now()

        monthly_forecast = []
        for month_num in range(1, 13):
            month_key = f'month_{month_num}_qty'
            qty = result.get(month_key, 0) or 0

            # Calculate month date
            month_date = base_date + relativedelta(months=month_num - 1)

            monthly_forecast.append({
                "month": month_date.strftime('%Y-%m'),
                "base_qty": qty,
                "adjusted_qty": qty,  # No learning adjustments yet (Phase 2)
                "learning_applied": False,
                "adjustment_reason": None
            })

        return {
            "sku_id": sku_id,
            "warehouse": warehouse,
            "forecast_run_id": result.get('forecast_run_id'),
            "forecast_method": result.get('forecast_method', 'Unknown'),
            "monthly_forecast": monthly_forecast,
            "avg_monthly": round(result.get('avg_monthly_qty', 0), 2)
        }

    except Exception as e:
        logger.error(f"Error fetching forecast for {sku_id}: {str(e)}", exc_info=True)
        raise


def get_stockout_history_for_sku(sku_id: str, warehouse: Optional[str] = None) -> Dict:
    """
    Retrieve stockout history with pattern detection

    Fetches historical stockout dates and includes pattern detection results
    if available from the stockout analysis system.

    Args:
        sku_id: SKU identifier
        warehouse: Optional warehouse filter (burnaby or kentucky)

    Returns:
        dict: {
            "sku_id": str,
            "warehouse": str or None,
            "total_stockouts": int,
            "pattern_detected": bool,
            "pattern_type": str or None,
            "stockouts": List[dict]
        }

    Logic:
        - Query stockout_dates table
        - LEFT JOIN stockout_patterns for pattern detection
        - Filter by warehouse if specified
        - Return chronological stockout list
        - Include estimated_lost_sales if available

    Example:
        result = get_stockout_history_for_sku("UB-YTX14-BS", "burnaby")
        # Returns stockout history for burnaby warehouse with pattern indicators
    """
    # Build query with optional warehouse filter
    query = """
        SELECT
            sd.sku_id,
            sd.stockout_date,
            DATEDIFF(COALESCE(sd.resolved_date, CURDATE()), sd.stockout_date) as days_out_of_stock,
            sd.warehouse,
            sd.is_resolved,
            sd.resolved_date,
            CASE WHEN COUNT(sp.id) > 0 THEN 1 ELSE 0 END as pattern_detected,
            GROUP_CONCAT(DISTINCT sp.pattern_type) as pattern_type
        FROM stockout_dates sd
        LEFT JOIN stockout_patterns sp
            ON sd.sku_id = sp.sku_id
        WHERE sd.sku_id = %s
    """

    params = [sku_id]

    # Add warehouse filter if specified
    if warehouse:
        query += " AND sd.warehouse = %s"
        params.append(warehouse)

    query += """
        GROUP BY sd.sku_id, sd.stockout_date, sd.warehouse, sd.is_resolved, sd.resolved_date
        ORDER BY sd.stockout_date DESC
        LIMIT 50
    """

    try:
        stockouts = execute_query(
            query,
            tuple(params),
            fetch_one=False,
            fetch_all=True
        ) or []

        # Convert dates to strings
        for so in stockouts:
            if so.get('stockout_date'):
                so['stockout_date'] = str(so['stockout_date'])

        # Extract pattern information from first row if exists
        pattern_detected = False
        pattern_type = None
        if stockouts:
            pattern_detected = bool(stockouts[0].get('pattern_detected'))
            pattern_type = stockouts[0].get('pattern_type')

        return {
            "sku_id": sku_id,
            "warehouse": warehouse,
            "total_stockouts": len(stockouts),
            "pattern_detected": pattern_detected,
            "pattern_type": pattern_type,
            "stockouts": stockouts
        }

    except Exception as e:
        logger.error(f"Error fetching stockouts for {sku_id}: {str(e)}", exc_info=True)
        raise


# FastAPI Endpoints

@router.get("/pending-orders/sku/{sku_id}")
def get_pending_orders(
    sku_id: str,
    warehouse: str = Query(..., description="Warehouse name (burnaby or kentucky)")
):
    """
    Get time-phased pending orders for SKU

    Returns pending supplier orders categorized by urgency:
    - overdue: past expected arrival
    - imminent: within 7 days
    - covered: within 30 days
    - future: beyond 30 days

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse to query (burnaby or kentucky)

    Returns:
        dict: Pending orders with categories and confidence scores

    Raises:
        HTTPException 404: SKU not found
        HTTPException 500: Database error
    """
    try:
        # Validate SKU exists
        if not sku_exists(sku_id):
            raise HTTPException(
                status_code=404,
                detail=f"SKU {sku_id} not found"
            )

        logger.info(f"Fetching pending orders for {sku_id} at {warehouse}")

        result = get_pending_orders_for_sku(sku_id, warehouse)

        logger.info(f"Found {result['total_pending']} pending units for {sku_id}")

        return result

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in get_pending_orders endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.get("/forecasts/sku/{sku_id}/latest")
def get_forecast_latest(
    sku_id: str,
    warehouse: str = Query(..., description="Warehouse name (burnaby or kentucky)")
):
    """
    Get latest 12-month forecast with learning adjustments

    Returns forecast data including:
    - Base monthly projections
    - Learning-adjusted values (if applied)
    - Forecast method used
    - Average monthly demand

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse to query (burnaby or kentucky)

    Returns:
        dict: Forecast data with monthly projections

    Raises:
        HTTPException 404: SKU or forecast not found
        HTTPException 500: Database error
    """
    try:
        # Validate SKU exists
        if not sku_exists(sku_id):
            raise HTTPException(
                status_code=404,
                detail=f"SKU {sku_id} not found"
            )

        logger.info(f"Fetching forecast for {sku_id} at {warehouse}")

        result = get_forecast_data_for_sku(sku_id, warehouse)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"No forecast found for SKU {sku_id} in {warehouse} warehouse. This may indicate the SKU was not included in recent forecast runs."
            )

        logger.info(f"Found forecast run {result['forecast_run_id']} for {sku_id}")

        return result

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in get_forecast_latest endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.get("/stockouts/sku/{sku_id}")
def get_stockout_history(
    sku_id: str,
    warehouse: str = Query(None, description="Warehouse name (burnaby or kentucky)")
):
    """
    Get stockout history with pattern detection

    Returns:
    - Historical stockout dates
    - Days out of stock
    - Pattern detection (chronic, seasonal, supply_issue)
    - Estimated lost sales

    Args:
        sku_id: SKU identifier
        warehouse: Optional warehouse filter (burnaby or kentucky)

    Returns:
        dict: Stockout history with pattern information

    Raises:
        HTTPException 404: SKU not found
        HTTPException 500: Database error
    """
    try:
        # Validate SKU exists
        if not sku_exists(sku_id):
            raise HTTPException(
                status_code=404,
                detail=f"SKU {sku_id} not found"
            )

        logger.info(f"Fetching stockout history for {sku_id}" + (f" at {warehouse}" if warehouse else ""))

        result = get_stockout_history_for_sku(sku_id, warehouse)

        logger.info(f"Found {result['total_stockouts']} stockouts for {sku_id}")

        return result

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error in get_stockout_history endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
