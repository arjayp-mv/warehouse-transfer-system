"""
Forecasting API Endpoints

FastAPI routes for 12-month sales forecasting system.

Key Endpoints:
- POST /api/forecasts/generate - Start new forecast generation
- GET /api/forecasts/runs - List forecast runs with pagination
- GET /api/forecasts/runs/{run_id} - Get forecast run status
- GET /api/forecasts/runs/{run_id}/results - Get forecast results
- GET /api/forecasts/runs/{run_id}/export - Export forecast to CSV
- POST /api/forecasts/runs/{run_id}/cancel - Cancel running forecast
- GET /api/forecasts/sku/{sku_id} - Get forecasts for specific SKU
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime, date
import csv
import io
import logging
from fastapi.responses import StreamingResponse

from backend.database import execute_query
from backend.forecast_jobs import (
    start_forecast_generation,
    get_forecast_status,
    cancel_forecast,
    get_active_forecast_runs
)

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/forecasts", tags=["forecasting"])


# Request/Response Models
class ForecastGenerateRequest(BaseModel):
    """Request model for generating a new forecast."""
    forecast_name: str = Field(..., min_length=1, max_length=100)
    warehouse: str = Field(default='combined', pattern='^(burnaby|kentucky|combined)$')
    growth_rate: float = Field(default=0.0, ge=-1.0, le=1.0)
    abc_filter: Optional[str] = Field(default=None, pattern='^[ABC]$')
    xyz_filter: Optional[str] = Field(default=None, pattern='^[XYZ]$')
    status_filter: Optional[List[str]] = Field(default=None, description="SKU statuses to include")


class ForecastRunResponse(BaseModel):
    """Response model for forecast run information."""
    run_id: int
    name: str
    status: str
    progress_percent: float
    total_skus: int
    processed_skus: int
    failed_skus: int
    created_at: Optional[str]
    completed_at: Optional[str]
    duration_seconds: Optional[float]


# API Endpoints

@router.post("/generate", response_model=Dict)
async def generate_forecast(request: ForecastGenerateRequest):
    """
    Start a new forecast generation job.

    This endpoint creates a new forecast run and starts background processing.
    Returns immediately with the run_id - use GET /runs/{run_id} to check progress.

    Args:
        request: Forecast generation parameters

    Returns:
        Dictionary with run_id and initial status

    Example:
        POST /api/forecasts/generate
        {
            "forecast_name": "Q1 2025 Forecast",
            "warehouse": "combined",
            "growth_rate": 0.05,
            "abc_filter": "A"
        }

        Response: {"run_id": 1, "status": "pending", "message": "Forecast generation started"}
    """
    try:
        logger.info(f"API: Received forecast generation request: '{request.forecast_name}'")

        # Build SKU filter from request
        sku_filter = {}
        if request.abc_filter:
            sku_filter['abc_code'] = request.abc_filter
        if request.xyz_filter:
            sku_filter['xyz_code'] = request.xyz_filter

        # Handle status filter with validation
        if request.status_filter:
            valid_statuses = {'Active', 'Death Row', 'Discontinued'}
            invalid_statuses = [s for s in request.status_filter if s not in valid_statuses]
            if invalid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status values: {invalid_statuses}. Must be one of: {valid_statuses}"
                )
            sku_filter['status_filter'] = request.status_filter

        # Convert growth_rate of 0.0 to None for auto-calculation
        # User can still manually set 0% by using a very small non-zero value like 0.001
        growth_rate_override = None if request.growth_rate == 0.0 else request.growth_rate

        logger.info(f"API: SKU Filter: {sku_filter}, Warehouse: {request.warehouse}, Growth Rate: {request.growth_rate} (override: {growth_rate_override})")

        # V7.3 Phase 4: Start forecast generation (may start immediately or queue)
        result = start_forecast_generation(
            forecast_name=request.forecast_name,
            sku_filter=sku_filter if sku_filter else None,
            warehouse=request.warehouse,
            growth_rate=growth_rate_override
        )

        # Handle different results based on queue status
        if result['status'] == 'queued':
            logger.info(f"API: Forecast queued at position {result['queue_position']} with run_id={result['run_id']}")
            return {
                "run_id": result['run_id'],
                "status": "queued",
                "queue_position": result['queue_position'],
                "message": f"Forecast queued at position {result['queue_position']}"
            }
        else:  # status == 'started'
            logger.info(f"API: Forecast generation started successfully with run_id={result['run_id']}")
            return {
                "run_id": result['run_id'],
                "status": "pending",
                "message": "Forecast generation started successfully"
            }

    except ValueError as e:
        # No SKUs found matching filter criteria
        raise HTTPException(
            status_code=400,
            detail=f"Filter validation error: {str(e)}"
        )
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: Failed to start forecast generation. {str(e)}"
        )


@router.get("/queue")
async def get_forecast_queue():
    """
    Get the current forecast generation queue status.

    V7.3 Phase 4: Returns list of queued forecasts in FIFO order.

    Returns:
        List of queued forecast runs with queue position and metadata

    Example Response:
        [
            {
                "run_id": 5,
                "forecast_name": "Q2 Forecast",
                "queue_position": 1,
                "queued_at": "2025-10-20T10:30:00",
                "total_skus": 1768
            },
            {
                "run_id": 6,
                "forecast_name": "Q3 Forecast",
                "queue_position": 2,
                "queued_at": "2025-10-20T10:31:00",
                "total_skus": 950
            }
        ]
    """
    try:
        query = """
            SELECT id, forecast_name, queue_position, queued_at, total_skus
            FROM forecast_runs
            WHERE status = 'queued'
            ORDER BY queue_position ASC
        """
        results = execute_query(query, fetch_all=True)

        queued_runs = []
        for row in results:
            queued_runs.append({
                'run_id': row['id'],
                'forecast_name': row['forecast_name'],
                'queue_position': row['queue_position'],
                'queued_at': row['queued_at'].isoformat() if row['queued_at'] else None,
                'total_skus': row['total_skus']
            })

        logger.info(f"API: Retrieved {len(queued_runs)} queued forecasts")
        return queued_runs

    except Exception as e:
        logger.error(f"API: Failed to retrieve queue: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve forecast queue: {str(e)}"
        )


@router.delete("/queue/{run_id}")
async def cancel_queued_forecast(run_id: int):
    """
    Cancel a queued forecast and remove it from the queue.

    V7.3 Phase 4: Allows users to cancel forecasts that are waiting in queue.
    Cannot cancel forecasts that are already running.

    Args:
        run_id: ID of the forecast run to cancel

    Returns:
        Success message with run_id

    Raises:
        400: If forecast is not in queued status
        404: If forecast run not found
    """
    try:
        # Check if forecast exists and is queued
        check_query = "SELECT status, forecast_name FROM forecast_runs WHERE id = %s"
        result = execute_query(check_query, params=(run_id,), fetch_all=True)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Forecast run {run_id} not found"
            )

        current_status = result[0]['status']
        forecast_name = result[0]['forecast_name']

        if current_status != 'queued':
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel forecast in status '{current_status}'. Only queued forecasts can be cancelled."
            )

        # Update status to cancelled
        update_query = """
            UPDATE forecast_runs
            SET status = 'cancelled', queue_position = NULL
            WHERE id = %s
        """
        execute_query(update_query, params=(run_id,))

        logger.info(f"API: Cancelled queued forecast {run_id} ('{forecast_name}')")

        return {
            "message": f"Forecast '{forecast_name}' removed from queue",
            "run_id": run_id,
            "status": "cancelled"
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"API: Failed to cancel queued forecast {run_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel forecast: {str(e)}"
        )


@router.get("/runs", response_model=List[ForecastRunResponse])
async def get_forecast_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100)
):
    """
    Get paginated list of forecast runs.

    Args:
        page: Page number (starts at 1)
        page_size: Number of runs per page (max 100)

    Returns:
        List of forecast run summaries
    """
    try:
        # Enforce pagination limits (best practice)
        page_size = min(page_size, 100)

        runs = get_active_forecast_runs(limit=page_size)
        return runs

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch forecast runs: {str(e)}")


@router.get("/runs/{run_id}", response_model=ForecastRunResponse)
async def get_run_status(run_id: int):
    """
    Get status and progress of a specific forecast run.

    Args:
        run_id: Forecast run ID

    Returns:
        Detailed forecast run information including progress
    """
    try:
        status = get_forecast_status(run_id)

        if 'error' in status:
            raise HTTPException(status_code=404, detail=status['error'])

        return status

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch run status: {str(e)}")


@router.get("/runs/{run_id}/results")
async def get_forecast_results(
    run_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    sku_filter: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Get forecast results for a completed forecast run.

    Returns paginated list of SKU forecasts with monthly quantities and revenues.

    Args:
        run_id: Forecast run ID
        page: Page number (starts at 1)
        page_size: Number of SKUs per page (max 100)
        sku_filter: Optional SKU ID filter (partial match) - DEPRECATED, use search instead
        search: Search query to filter SKUs (searches sku_id and description)

    Returns:
        Dictionary with forecast results and pagination metadata
    """
    try:
        # Build query with optional search filter
        where_clause = "fd.forecast_run_id = %s"
        params = [run_id]

        # Use search parameter (preferred) or fall back to sku_filter for backwards compatibility
        search_term = search or sku_filter

        if search_term:
            # Search both SKU ID and description
            where_clause += " AND (fd.sku_id LIKE %s OR s.description LIKE %s)"
            search_pattern = f"%{search_term}%"
            params.extend([search_pattern, search_pattern])

        # When searching, show all results on one page (up to 1000 results)
        if search_term:
            page_size = min(1000, page_size * 10)  # Allow up to 1000 search results
            page = 1  # Reset to first page
            offset = 0
        else:
            # Normal pagination
            page_size = min(page_size, 100)
            offset = (page - 1) * page_size

        # Get total count (needs JOIN for description search)
        count_query = f"""
            SELECT COUNT(*) as total
            FROM forecast_details fd
            JOIN skus s ON fd.sku_id = s.sku_id
            WHERE {where_clause}
        """
        total_result = execute_query(count_query, params=tuple(params), fetch_all=True)
        total_count = total_result[0]['total']

        # Get paginated/filtered results
        query = f"""
            SELECT
                fd.sku_id,
                fd.warehouse,
                s.description,
                s.abc_code,
                s.xyz_code,
                fd.month_1_qty, fd.month_2_qty, fd.month_3_qty, fd.month_4_qty,
                fd.month_5_qty, fd.month_6_qty, fd.month_7_qty, fd.month_8_qty,
                fd.month_9_qty, fd.month_10_qty, fd.month_11_qty, fd.month_12_qty,
                fd.month_1_rev, fd.month_2_rev, fd.month_3_rev, fd.month_4_rev,
                fd.month_5_rev, fd.month_6_rev, fd.month_7_rev, fd.month_8_rev,
                fd.month_9_rev, fd.month_10_rev, fd.month_11_rev, fd.month_12_rev,
                fd.total_qty_forecast,
                fd.total_rev_forecast,
                fd.avg_monthly_qty,
                fd.avg_monthly_rev,
                fd.confidence_score,
                fd.method_used,
                fd.seasonal_pattern_applied,
                fd.growth_rate_applied,
                fd.growth_rate_source
            FROM forecast_details fd
            JOIN skus s ON fd.sku_id = s.sku_id
            WHERE {where_clause}
            ORDER BY s.abc_code, s.xyz_code, fd.sku_id
            LIMIT %s OFFSET %s
        """

        params.extend([page_size, offset])
        results = execute_query(query, params=tuple(params), fetch_all=True)

        # Get forecast run info to calculate month labels
        run_query = "SELECT created_at FROM forecast_runs WHERE id = %s"
        run_result = execute_query(run_query, params=(run_id,), fetch_all=True)

        # Calculate month labels starting from CURRENT month (latest sales data)
        # This must match the forecast calculation logic in forecasting.py
        month_labels = []
        forecast_start_month = None
        if run_result and run_result[0]['created_at']:
            from datetime import datetime, timedelta
            from dateutil.relativedelta import relativedelta

            # Get latest sales data month (only months with actual sales, not empty placeholders)
            # to align with forecast engine
            latest_sales_query = """
                SELECT MAX(`year_month`) as latest
                FROM monthly_sales
                WHERE (burnaby_sales + kentucky_sales) > 0
            """
            latest_sales_result = execute_query(latest_sales_query, fetch_all=True)

            if latest_sales_result and latest_sales_result[0]['latest']:
                # Start from month AFTER latest sales data
                latest_month = datetime.strptime(latest_sales_result[0]['latest'], '%Y-%m')
                start_date = latest_month + relativedelta(months=1)
            else:
                # Fallback: use creation date (shouldn't happen with valid data)
                start_date = run_result[0]['created_at']

            forecast_start_month = start_date.strftime('%Y-%m')

            # Generate 12 month labels
            for i in range(12):
                month_date = start_date + relativedelta(months=i)
                month_labels.append(month_date.strftime('%Y-%m'))

        # Format results
        forecasts = []
        for row in results:
            forecasts.append({
                'sku_id': row['sku_id'],
                'description': row['description'],
                'warehouse': row['warehouse'],
                'abc_code': row['abc_code'],
                'xyz_code': row['xyz_code'],
                'monthly_qty': [
                    row['month_1_qty'], row['month_2_qty'], row['month_3_qty'],
                    row['month_4_qty'], row['month_5_qty'], row['month_6_qty'],
                    row['month_7_qty'], row['month_8_qty'], row['month_9_qty'],
                    row['month_10_qty'], row['month_11_qty'], row['month_12_qty']
                ],
                'monthly_rev': [
                    float(row['month_1_rev']), float(row['month_2_rev']),
                    float(row['month_3_rev']), float(row['month_4_rev']),
                    float(row['month_5_rev']), float(row['month_6_rev']),
                    float(row['month_7_rev']), float(row['month_8_rev']),
                    float(row['month_9_rev']), float(row['month_10_rev']),
                    float(row['month_11_rev']), float(row['month_12_rev'])
                ],
                'total_qty_forecast': row['total_qty_forecast'],
                'total_rev_forecast': float(row['total_rev_forecast']),
                'avg_monthly_qty': float(row['avg_monthly_qty']),
                'avg_monthly_rev': float(row['avg_monthly_rev']),
                'confidence_score': float(row['confidence_score']),
                'method_used': row['method_used'],
                'seasonal_pattern': row['seasonal_pattern_applied'],
                'growth_rate_applied': float(row['growth_rate_applied']) if row['growth_rate_applied'] is not None else 0.0,
                'growth_rate_source': row['growth_rate_source']
            })

        return {
            'run_id': run_id,
            'forecasts': forecasts,
            'forecast_start_month': forecast_start_month,
            'month_labels': month_labels,
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch forecast results: {str(e)}")


@router.get("/runs/{run_id}/export")
async def export_forecast_csv(run_id: int):
    """
    Export forecast results to CSV file.

    Args:
        run_id: Forecast run ID

    Returns:
        CSV file download
    """
    try:
        # Get all forecast results (no pagination for export)
        query = """
            SELECT
                fd.sku_id,
                s.description,
                s.abc_code,
                s.xyz_code,
                fd.warehouse,
                fd.month_1_qty, fd.month_2_qty, fd.month_3_qty, fd.month_4_qty,
                fd.month_5_qty, fd.month_6_qty, fd.month_7_qty, fd.month_8_qty,
                fd.month_9_qty, fd.month_10_qty, fd.month_11_qty, fd.month_12_qty,
                fd.total_qty_forecast,
                fd.confidence_score,
                fd.method_used
            FROM forecast_details fd
            JOIN skus s ON fd.sku_id = s.sku_id
            WHERE forecast_run_id = %s
            ORDER BY s.abc_code, s.xyz_code, fd.sku_id
        """

        results = execute_query(query, params=(run_id,), fetch_all=True)

        if not results:
            raise HTTPException(status_code=404, detail="No forecast results found")

        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'SKU ID', 'Description', 'ABC', 'XYZ', 'Warehouse',
            'Month 1', 'Month 2', 'Month 3', 'Month 4', 'Month 5', 'Month 6',
            'Month 7', 'Month 8', 'Month 9', 'Month 10', 'Month 11', 'Month 12',
            'Total Forecast', 'Confidence', 'Method'
        ])

        # Write data rows
        for row in results:
            writer.writerow([
                row['sku_id'],
                row['description'],
                row['abc_code'],
                row['xyz_code'],
                row['warehouse'],
                row['month_1_qty'], row['month_2_qty'], row['month_3_qty'],
                row['month_4_qty'], row['month_5_qty'], row['month_6_qty'],
                row['month_7_qty'], row['month_8_qty'], row['month_9_qty'],
                row['month_10_qty'], row['month_11_qty'], row['month_12_qty'],
                row['total_qty_forecast'],
                row['confidence_score'],
                row['method_used']
            ])

        # Prepare response
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=forecast_run_{run_id}.csv"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export forecast: {str(e)}")


@router.post("/runs/{run_id}/cancel")
async def cancel_forecast_run(run_id: int):
    """
    Cancel a running forecast generation job.

    Args:
        run_id: Forecast run ID

    Returns:
        Success message
    """
    try:
        success = cancel_forecast(run_id)

        if not success:
            raise HTTPException(status_code=404, detail="Forecast run not found or not running")

        return {"message": "Forecast run cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel forecast: {str(e)}")


@router.get("/sku/{sku_id}")
async def get_sku_forecasts(sku_id: str):
    """
    Get all forecast runs for a specific SKU.

    Args:
        sku_id: SKU identifier

    Returns:
        List of forecasts for this SKU across all forecast runs
    """
    try:
        query = """
            SELECT
                fr.id as run_id,
                fr.forecast_name,
                fr.forecast_date,
                fd.warehouse,
                fd.month_1_qty, fd.month_2_qty, fd.month_3_qty, fd.month_4_qty,
                fd.month_5_qty, fd.month_6_qty, fd.month_7_qty, fd.month_8_qty,
                fd.month_9_qty, fd.month_10_qty, fd.month_11_qty, fd.month_12_qty,
                fd.total_qty_forecast,
                fd.confidence_score
            FROM forecast_details fd
            JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
            WHERE fd.sku_id = %s
              AND fr.status = 'completed'
            ORDER BY fr.forecast_date DESC
            LIMIT 10
        """

        results = execute_query(query, params=(sku_id,), fetch_all=True)

        forecasts = []
        for row in results:
            forecasts.append({
                'run_id': row['run_id'],
                'forecast_name': row['forecast_name'],
                'forecast_date': row['forecast_date'].isoformat() if row['forecast_date'] else None,
                'warehouse': row['warehouse'],
                'monthly_qty': [
                    row['month_1_qty'], row['month_2_qty'], row['month_3_qty'],
                    row['month_4_qty'], row['month_5_qty'], row['month_6_qty'],
                    row['month_7_qty'], row['month_8_qty'], row['month_9_qty'],
                    row['month_10_qty'], row['month_11_qty'], row['month_12_qty']
                ],
                'total_qty_forecast': row['total_qty_forecast'],
                'confidence_score': float(row['confidence_score'])
            })

        return {
            'sku_id': sku_id,
            'forecasts': forecasts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch SKU forecasts: {str(e)}")


@router.get("/runs/{run_id}/historical/{sku_id}")
async def get_historical_data(run_id: int, sku_id: str):
    """
    Get last 12 months of historical sales data for comparison with forecast.
    Returns monthly sales quantities and revenues for the year preceding the forecast.

    Args:
        run_id: Forecast run ID (used to determine forecast start date)
        sku_id: SKU identifier

    Returns:
        JSON with months, quantities, and revenues arrays
    """
    try:
        # Get forecast warehouse to match historical data
        forecast_query = """
            SELECT created_at, warehouse
            FROM forecast_runs
            WHERE id = %s
        """
        forecast_result = execute_query(forecast_query, params=(run_id,), fetch_all=True)

        if not forecast_result:
            raise HTTPException(status_code=404, detail="Forecast run not found")

        # Get warehouse from forecast run, default to 'combined' if NULL (backward compatibility)
        warehouse = forecast_result[0].get('warehouse') or 'combined'

        # Get latest sales month to align with forecast engine logic
        # Only consider months with actual sales to avoid empty placeholder records
        latest_sales_query = """
            SELECT MAX(`year_month`) as latest
            FROM monthly_sales
            WHERE (burnaby_sales + kentucky_sales) > 0
        """
        latest_result = execute_query(latest_sales_query, fetch_all=True)

        if not latest_result or not latest_result[0]['latest']:
            return {
                'months': [],
                'quantities': [],
                'revenues': [],
                'message': 'No historical data available'
            }

        # Calculate the 12-month historical period (same months as forecast but previous year)
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        latest_month = datetime.strptime(latest_result[0]['latest'], '%Y-%m')
        # Historical period: 12 months ending at latest_month
        history_start = latest_month - relativedelta(months=11)

        # Build warehouse-specific query to match forecast warehouse
        if warehouse == 'combined':
            sales_column = 'burnaby_sales + kentucky_sales'
            revenue_column = '(burnaby_sales + kentucky_sales) * s.cost_per_unit'
        else:
            sales_column = f'{warehouse}_sales'
            revenue_column = f'{warehouse}_sales * s.cost_per_unit'

        # Fetch historical data for the past 12 months
        history_query = f"""
            SELECT `year_month`,
                   {sales_column} as total_sales,
                   {revenue_column} as total_revenue
            FROM monthly_sales ms
            JOIN skus s ON ms.sku_id = s.sku_id
            WHERE ms.sku_id = %s
              AND ms.year_month >= %s
              AND ms.year_month <= %s
            ORDER BY ms.year_month ASC
        """

        history_results = execute_query(
            history_query,
            params=(sku_id, history_start.strftime('%Y-%m'), latest_month.strftime('%Y-%m')),
            fetch_all=True
        )

        # Build arrays for chart
        months = []
        quantities = []
        revenues = []

        for row in history_results:
            months.append(row['year_month'])
            quantities.append(float(row['total_sales'] or 0))
            revenues.append(float(row['total_revenue'] or 0))

        return {
            'months': months,
            'quantities': quantities,
            'revenues': revenues
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch historical data: {str(e)}")
