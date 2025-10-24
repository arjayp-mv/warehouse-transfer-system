"""
Supplier Ordering Data Models

Pydantic models for request validation and response serialization
in the supplier ordering API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import date


class GenerateRecommendationsRequest(BaseModel):
    """Request model for generating monthly recommendations"""
    order_month: Optional[str] = Field(
        None,
        description="Order month in YYYY-MM format (defaults to current month)"
    )


class GenerateRecommendationsResponse(BaseModel):
    """Response model for recommendation generation"""
    order_month: str
    recommendations_generated: int
    must_order_count: int
    should_order_count: int
    optional_count: int
    skip_count: int
    total_value: float


class UpdateOrderRequest(BaseModel):
    """Request model for updating order quantities and overrides"""
    confirmed_qty: Optional[int] = Field(None, ge=0)
    lead_time_days_override: Optional[int] = Field(None, ge=1, le=365)
    expected_arrival_override: Optional[date] = None
    notes: Optional[str] = None


class OrderListResponse(BaseModel):
    """Response model for paginated order list"""
    total: int
    page: int
    page_size: int
    total_pages: int
    orders: List[Dict]
    recordsTotal: Optional[int] = None  # Total records without filtering (for DataTables)
    recordsFiltered: Optional[int] = None  # Total records after filtering (for DataTables)
    summary: Optional[Dict] = None  # Summary statistics (for dashboard cards)


class SummaryResponse(BaseModel):
    """Response model for summary statistics"""
    order_month: str
    total_skus: int
    must_order_count: int
    should_order_count: int
    optional_count: int
    skip_count: int
    total_suggested_value: float
    total_confirmed_value: float
    locked_orders: int
    overdue_pending_total: int
    suppliers: List[Dict]
