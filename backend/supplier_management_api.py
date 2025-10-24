"""
Supplier Management API Endpoints

Provides REST API endpoints for managing supplier lead times and viewing
historical performance data. Includes cascade update functionality to
propagate lead time changes to existing supplier order confirmations.

Key Features:
- Update supplier-wide lead times (affects all SKUs from that supplier)
- Retrieve historical lead time statistics and trends
- Cascade updates to supplier_order_confirmations records
- Performance analytics integration
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

from database import get_db
from supplier_analytics import SupplierAnalytics

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


# ============================================================================
# Pydantic Models
# ============================================================================

class UpdateLeadTimeRequest(BaseModel):
    """Request model for updating supplier lead time"""
    p95_lead_time: int = Field(
        ...,
        ge=1,
        le=365,
        description="P95 lead time in days (1-365)"
    )
    notes: Optional[str] = Field(
        None,
        description="Optional notes about the lead time change"
    )
    updated_by: str = Field(
        ...,
        description="Username making the update"
    )


class UpdateLeadTimeResponse(BaseModel):
    """Response model for lead time update"""
    supplier: str
    old_p95_lead_time: Optional[int]
    new_p95_lead_time: int
    affected_skus: int
    affected_orders: int
    updated_at: datetime
    updated_by: str


class LeadTimeHistoryResponse(BaseModel):
    """Response model for historical lead time statistics"""
    supplier: str
    current_p95: Optional[int]
    avg_lead_time: float
    median_lead_time: float
    min_lead_time: int
    max_lead_time: int
    std_dev_lead_time: float
    coefficient_variation: float
    reliability_score: int
    shipment_count: int
    calculation_period: str
    last_calculated: Optional[datetime]
    destination_breakdown: dict
    seasonal_patterns: Optional[dict]
    performance_trends: Optional[dict]


# ============================================================================
# API Endpoints
# ============================================================================

@router.put("/{supplier}/lead-time", response_model=UpdateLeadTimeResponse)
async def update_supplier_lead_time(
    supplier: str,
    request: UpdateLeadTimeRequest,
    db: Session = Depends(get_db)
):
    """
    Update P95 lead time for ALL SKUs from this supplier.

    This endpoint updates the supplier-wide lead time setting, which affects:
    1. The supplier_lead_times cache table
    2. All future supplier_order_confirmations for this supplier
    3. Existing supplier_order_confirmations (cascade update)

    The cascade update only affects orders that do NOT have a user-defined
    lead_time_days_override, preserving manual overrides.

    Args:
        supplier: Supplier name (will be normalized)
        request: Lead time update parameters
        db: Database session

    Returns:
        Summary of update including affected SKU and order counts

    Raises:
        HTTPException: If supplier not found or update fails
    """
    try:
        # Normalize supplier name
        normalized_supplier = supplier.strip().upper()

        # Check if supplier exists in supplier_lead_times table
        check_query = text("""
            SELECT id, p95_lead_time, supplier
            FROM supplier_lead_times
            WHERE UPPER(TRIM(supplier)) = :supplier
            LIMIT 1
        """)

        existing = db.execute(
            check_query,
            {"supplier": normalized_supplier}
        ).fetchone()

        old_p95 = existing[1] if existing else None
        supplier_display_name = existing[2] if existing else supplier

        # Update or insert supplier_lead_times record
        if existing:
            update_query = text("""
                UPDATE supplier_lead_times
                SET p95_lead_time = :p95_lead_time,
                    updated_at = NOW()
                WHERE id = :id
            """)
            db.execute(update_query, {
                "id": existing[0],
                "p95_lead_time": request.p95_lead_time
            })
        else:
            # New supplier - insert with basic data
            insert_query = text("""
                INSERT INTO supplier_lead_times (
                    supplier, p95_lead_time, calculation_period, last_calculated
                )
                VALUES (:supplier, :p95_lead_time, 'manual', NOW())
            """)
            db.execute(insert_query, {
                "supplier": supplier_display_name,
                "p95_lead_time": request.p95_lead_time
            })

        # Count affected SKUs
        sku_count_query = text("""
            SELECT COUNT(DISTINCT sku_id)
            FROM skus
            WHERE UPPER(TRIM(supplier)) = :supplier
        """)

        sku_count = db.execute(
            sku_count_query,
            {"supplier": normalized_supplier}
        ).fetchone()[0]

        # Cascade update to supplier_order_confirmations
        # Only update records without user-defined overrides
        cascade_update_query = text("""
            UPDATE supplier_order_confirmations
            SET lead_time_days_default = :p95_lead_time
            WHERE UPPER(TRIM(supplier)) = :supplier
            AND lead_time_days_override IS NULL
        """)

        cascade_result = db.execute(cascade_update_query, {
            "supplier": normalized_supplier,
            "p95_lead_time": request.p95_lead_time
        })

        affected_orders = cascade_result.rowcount

        # Log the change in supplier_lead_time_history if table exists
        try:
            history_insert = text("""
                INSERT INTO supplier_lead_time_history (
                    supplier, old_p95_lead_time, new_p95_lead_time,
                    updated_by, notes, updated_at
                )
                VALUES (:supplier, :old_p95, :new_p95, :updated_by, :notes, NOW())
            """)
            db.execute(history_insert, {
                "supplier": supplier_display_name,
                "old_p95": old_p95,
                "new_p95": request.p95_lead_time,
                "updated_by": request.updated_by,
                "notes": request.notes
            })
        except Exception as log_error:
            # History logging is optional - don't fail if table doesn't exist
            pass

        db.commit()

        return UpdateLeadTimeResponse(
            supplier=supplier_display_name,
            old_p95_lead_time=old_p95,
            new_p95_lead_time=request.p95_lead_time,
            affected_skus=sku_count,
            affected_orders=affected_orders,
            updated_at=datetime.now(),
            updated_by=request.updated_by
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update supplier lead time: {str(e)}"
        )


@router.get("/{supplier}/lead-time-history", response_model=LeadTimeHistoryResponse)
async def get_supplier_lead_time_history(
    supplier: str,
    period_months: int = Query(12, ge=0, le=60, description="Analysis period in months (0 for all time)"),
    include_seasonal: bool = Query(False, description="Include seasonal pattern analysis"),
    include_trends: bool = Query(False, description="Include performance trend analysis"),
    db: Session = Depends(get_db)
):
    """
    Get historical lead time statistics and performance metrics for a supplier.

    Provides comprehensive analysis including:
    - Statistical lead time metrics (avg, median, P95, std dev, CV)
    - Reliability scoring based on consistency
    - Destination-specific breakdown (Burnaby vs Kentucky)
    - Optional seasonal pattern detection
    - Optional performance trend analysis

    Args:
        supplier: Supplier name (will be normalized)
        period_months: Analysis period (0 for all time, default 12 months)
        include_seasonal: Include seasonal pattern analysis
        include_trends: Include performance trend analysis
        db: Database session

    Returns:
        Comprehensive historical performance statistics

    Raises:
        HTTPException: If supplier not found or analysis fails
    """
    try:
        # Initialize analytics engine
        analytics = SupplierAnalytics()

        # Get current P95 from supplier_lead_times table
        current_p95_query = text("""
            SELECT p95_lead_time
            FROM supplier_lead_times
            WHERE UPPER(TRIM(supplier)) = :supplier
            LIMIT 1
        """)

        current_p95_result = db.execute(
            current_p95_query,
            {"supplier": supplier.strip().upper()}
        ).fetchone()

        current_p95 = current_p95_result[0] if current_p95_result else None

        # Calculate comprehensive metrics
        metrics = analytics.calculate_supplier_metrics(
            supplier=supplier,
            period_months=period_months
        )

        if metrics.get('error'):
            raise HTTPException(
                status_code=404,
                detail=f"Supplier '{supplier}' not found or has no shipment data"
            )

        # Optional: Add seasonal pattern analysis
        seasonal_patterns = None
        if include_seasonal and metrics.get('shipment_count', 0) >= 10:
            seasonal_patterns = analytics.detect_seasonal_patterns(supplier)

        # Optional: Add performance trend analysis
        performance_trends = None
        if include_trends and metrics.get('shipment_count', 0) >= 10:
            performance_trends = analytics.calculate_performance_trends(supplier)

        return LeadTimeHistoryResponse(
            supplier=metrics['supplier'],
            current_p95=current_p95,
            avg_lead_time=metrics['avg_lead_time'],
            median_lead_time=metrics['median_lead_time'],
            min_lead_time=metrics['min_lead_time'],
            max_lead_time=metrics['max_lead_time'],
            std_dev_lead_time=metrics['std_dev_lead_time'],
            coefficient_variation=metrics['coefficient_variation'],
            reliability_score=metrics['reliability_score'],
            shipment_count=metrics['shipment_count'],
            calculation_period=metrics['time_period'],
            last_calculated=metrics.get('last_calculated'),
            destination_breakdown=metrics.get('destination_breakdown', {}),
            seasonal_patterns=seasonal_patterns,
            performance_trends=performance_trends
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve lead time history: {str(e)}"
        )


@router.get("/{supplier}/performance-alerts")
async def get_supplier_performance_alerts(
    supplier: str,
    db: Session = Depends(get_db)
):
    """
    Get performance degradation and reliability alerts for a supplier.

    Analyzes recent performance to detect:
    - Performance degradation (lead time increased >15% vs historical)
    - High variability warnings (CV > 25%)
    - Insufficient data warnings (<5 shipments in 6 months)

    Args:
        supplier: Supplier name
        db: Database session

    Returns:
        List of alerts with severity levels and action recommendations
    """
    try:
        analytics = SupplierAnalytics()
        alerts = analytics.detect_performance_alerts(supplier=supplier)

        return {
            "supplier": supplier,
            "alert_count": len(alerts),
            "alerts": alerts,
            "checked_at": datetime.now()
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check performance alerts: {str(e)}"
        )
