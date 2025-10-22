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
- POST /api/forecasts/accuracy/update - Update forecast accuracy metrics (V8.0)
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
                "status": "started",
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


@router.post("/accuracy/update", response_model=Dict)
async def trigger_accuracy_update(target_month: Optional[str] = None):
    """
    Manually trigger accuracy update for a specific month.

    V8.0 Phase 2: Stockout-aware forecast accuracy tracking.

    Compares actual sales to forecast predictions and calculates accuracy metrics.
    Excludes stockout-affected periods from MAPE calculations to avoid unfairly
    penalizing forecasts when stockouts prevented sales.

    Useful for:
    - Testing accuracy calculations
    - Backfilling historical data
    - Re-running failed updates
    - Manual trigger after uploading monthly sales data

    Args:
        target_month: Month in 'YYYY-MM' format (default: last month)

    Returns:
        Update statistics including MAPE and stockout-affected count

    Raises:
        400: Invalid month format
        500: Update failed

    Example:
        POST /api/forecasts/accuracy/update
        (updates last month)

        POST /api/forecasts/accuracy/update?target_month=2025-10
        (updates October 2025)

    Response:
        {
            "message": "Accuracy update completed",
            "details": {
                "month_updated": "2025-10",
                "total_forecasts": 1768,
                "actuals_found": 1650,
                "missing_actuals": 118,
                "avg_mape": 12.5,
                "stockout_affected_count": 45
            }
        }
    """
    from backend.forecast_accuracy import update_monthly_accuracy

    try:
        logger.info(f"API: Manual accuracy update triggered for: {target_month or 'last month'}")

        # Call the accuracy update function
        result = update_monthly_accuracy(target_month=target_month)

        # Check for errors in result
        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])

        logger.info(f"API: Accuracy update completed for {result.get('month_updated')}")
        logger.info(f"API: Updated {result.get('actuals_found')} forecasts, Avg MAPE: {result.get('avg_mape', 0):.2f}%")

        return {
            "message": "Accuracy update completed",
            "details": result
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"API: Accuracy update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Accuracy update failed: {str(e)}")


@router.get("/accuracy/summary")
async def get_accuracy_summary(
    warehouse: Optional[str] = Query(None, description="Filter by warehouse: burnaby, kentucky, combined, or null for all"),
    exclude_stockouts: bool = Query(True, description="Exclude stockout-affected forecasts from MAPE calculation")
):
    """
    Get forecast accuracy summary with MAPE trends and ABC/XYZ breakdown.

    Returns overall accuracy metrics, 6-month MAPE trend, and accuracy by
    ABC/XYZ classification. Supports warehouse filtering and stockout exclusion.

    Args:
        warehouse: Optional warehouse filter (burnaby/kentucky/combined/null=all)
        exclude_stockouts: Exclude stockout-affected forecasts (default: True)

    Returns:
        Dictionary with:
        - overall_mape: Overall MAPE across all completed forecasts
        - total_forecasts: Total forecast records
        - completed_forecasts: Forecasts with actuals recorded
        - by_abc_xyz: MAPE breakdown by ABC/XYZ classification (9 cells)
        - trend_6m: Monthly MAPE trend for last 6 months
        - stockouts_excluded: Count of excluded stockout-affected forecasts
    """
    try:
        # Build WHERE clause for warehouse and stockout filters
        where_conditions = ["fa.is_actual_recorded = 1"]
        params = []

        if warehouse:
            where_conditions.append("fa.warehouse = %s")
            params.append(warehouse)

        if exclude_stockouts:
            where_conditions.append("(fa.stockout_affected = 0 OR fa.stockout_affected IS NULL)")

        where_clause = " AND ".join(where_conditions)

        # Query overall metrics
        overall_query = f"""
            SELECT
                COUNT(*) as total_forecasts,
                SUM(CASE WHEN fa.is_actual_recorded = 1 THEN 1 ELSE 0 END) as completed_forecasts,
                AVG(CASE WHEN fa.is_actual_recorded = 1 THEN fa.absolute_percentage_error ELSE NULL END) as overall_mape,
                SUM(CASE WHEN fa.stockout_affected = 1 THEN 1 ELSE 0 END) as stockouts_excluded
            FROM forecast_accuracy fa
            WHERE {where_clause if warehouse else 'fa.is_actual_recorded = 1'}
        """
        overall_result = execute_query(overall_query, tuple(params) if params else None, fetch_all=True)

        overall = overall_result[0] if overall_result else {}

        # Query ABC/XYZ breakdown
        abc_xyz_query = f"""
            SELECT
                fa.abc_class,
                fa.xyz_class,
                AVG(fa.absolute_percentage_error) as avg_mape,
                COUNT(*) as forecast_count
            FROM forecast_accuracy fa
            WHERE {where_clause}
            GROUP BY fa.abc_class, fa.xyz_class
            ORDER BY fa.abc_class, fa.xyz_class
        """
        abc_xyz_result = execute_query(abc_xyz_query, tuple(params) if params else None, fetch_all=True)

        # Query 6-month trend
        trend_query = f"""
            SELECT
                DATE_FORMAT(fa.forecast_period_start, '%Y-%m') as month,
                AVG(fa.absolute_percentage_error) as avg_mape,
                COUNT(*) as forecast_count
            FROM forecast_accuracy fa
            WHERE {where_clause}
                AND fa.forecast_period_start >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
            GROUP BY DATE_FORMAT(fa.forecast_period_start, '%Y-%m')
            ORDER BY month ASC
        """
        trend_result = execute_query(trend_query, tuple(params) if params else None, fetch_all=True)

        return {
            "overall_mape": float(overall.get('overall_mape', 0.0) or 0.0),
            "total_forecasts": overall.get('total_forecasts', 0),
            "completed_forecasts": overall.get('completed_forecasts', 0),
            "stockouts_excluded": overall.get('stockouts_excluded', 0) if exclude_stockouts else 0,
            "by_abc_xyz": [
                {
                    "abc_class": row['abc_class'],
                    "xyz_class": row['xyz_class'],
                    "avg_mape": float(row['avg_mape'] or 0.0),
                    "forecast_count": row['forecast_count']
                }
                for row in abc_xyz_result
            ],
            "trend_6m": [
                {
                    "month": row['month'],
                    "avg_mape": float(row['avg_mape'] or 0.0),
                    "forecast_count": row['forecast_count']
                }
                for row in trend_result
            ],
            "warehouse_filter": warehouse,
            "exclude_stockouts": exclude_stockouts
        }

    except Exception as e:
        logger.error(f"API: Failed to get accuracy summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get accuracy summary: {str(e)}")


@router.get("/accuracy/sku/{sku_id}")
async def get_sku_accuracy_history(sku_id: str):
    """
    Get forecast accuracy history for a specific SKU.

    Returns up to 24 months of forecast accuracy data for the specified SKU,
    including MAPE, bias, and trend analysis.

    Args:
        sku_id: SKU identifier

    Returns:
        Dictionary with:
        - sku_id: SKU identifier
        - total_forecasts: Total forecast records
        - completed_forecasts: Forecasts with actuals recorded
        - avg_mape: Average MAPE across completed forecasts
        - avg_bias: Average bias (percentage error, signed)
        - history: List of monthly forecast accuracy records (last 24 months)
    """
    try:
        # Query overall metrics for SKU
        overall_query = """
            SELECT
                COUNT(*) as total_forecasts,
                SUM(CASE WHEN is_actual_recorded = 1 THEN 1 ELSE 0 END) as completed_forecasts,
                AVG(CASE WHEN is_actual_recorded = 1 THEN absolute_percentage_error ELSE NULL END) as avg_mape,
                AVG(CASE WHEN is_actual_recorded = 1 THEN percentage_error ELSE NULL END) as avg_bias
            FROM forecast_accuracy
            WHERE sku_id = %s
        """
        overall_result = execute_query(overall_query, (sku_id,), fetch_all=True)
        overall = overall_result[0] if overall_result else {}

        # Query historical accuracy data (last 24 months)
        history_query = """
            SELECT
                forecast_period_start,
                forecast_period_end,
                warehouse,
                predicted_demand,
                actual_demand,
                absolute_percentage_error as mape,
                percentage_error as bias,
                stockout_affected,
                forecast_method,
                abc_class,
                xyz_class
            FROM forecast_accuracy
            WHERE sku_id = %s
                AND is_actual_recorded = 1
            ORDER BY forecast_period_start DESC
            LIMIT 24
        """
        history_result = execute_query(history_query, (sku_id,), fetch_all=True)

        return {
            "sku_id": sku_id,
            "total_forecasts": overall.get('total_forecasts', 0),
            "completed_forecasts": overall.get('completed_forecasts', 0),
            "avg_mape": float(overall.get('avg_mape', 0.0) or 0.0),
            "avg_bias": float(overall.get('avg_bias', 0.0) or 0.0),
            "history": [
                {
                    "period_start": row['forecast_period_start'].isoformat() if row['forecast_period_start'] else None,
                    "period_end": row['forecast_period_end'].isoformat() if row['forecast_period_end'] else None,
                    "warehouse": row['warehouse'],
                    "predicted": float(row['predicted_demand'] or 0.0),
                    "actual": float(row['actual_demand'] or 0.0),
                    "mape": float(row['mape'] or 0.0),
                    "bias": float(row['bias'] or 0.0),
                    "stockout_affected": bool(row['stockout_affected']),
                    "method": row['forecast_method'],
                    "abc_class": row['abc_class'],
                    "xyz_class": row['xyz_class']
                }
                for row in history_result
            ]
        }

    except Exception as e:
        logger.error(f"API: Failed to get SKU accuracy history for {sku_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get SKU accuracy history: {str(e)}")


@router.get("/accuracy/problems")
async def get_problem_skus(
    mape_threshold: float = Query(30.0, description="MAPE threshold for problem identification (default: 30%)"),
    limit: int = Query(100, description="Maximum number of problem SKUs to return (max: 100)")
):
    """
    Identify problem SKUs with chronic forecasting accuracy issues.

    Uses the identify_problem_skus() function from forecast_learning module
    to find SKUs with consistently high MAPE and provide diagnostic recommendations.

    Args:
        mape_threshold: MAPE threshold for problem identification (default: 30%)
        limit: Maximum number of results (default: 100, max: 100)

    Returns:
        List of problem SKUs with:
        - sku_id: SKU identifier
        - description: SKU description
        - abc_code: ABC classification
        - xyz_code: XYZ classification
        - avg_mape: Average MAPE
        - avg_bias: Average bias
        - forecast_method: Current forecasting method
        - recommendations: List of diagnostic recommendations
    """
    try:
        from backend.forecast_learning import identify_problem_skus

        # Enforce maximum limit
        limit = min(limit, 100)

        # Call learning function to identify problems
        problems = identify_problem_skus(mape_threshold=mape_threshold)

        # Return limited results
        return problems[:limit]

    except Exception as e:
        logger.error(f"API: Failed to identify problem SKUs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to identify problem SKUs: {str(e)}")


@router.get("/accuracy/learning-insights")
async def get_learning_insights():
    """
    Get insights from forecast learning system.

    Returns recent learning adjustments, method recommendations, and
    category-level patterns discovered by the learning algorithms.

    Returns:
        Dictionary with:
        - growth_adjustments: Recent growth rate adjustments
        - seasonal_adjustments: Recent seasonal factor adjustments
        - method_recommendations: Best methods by ABC/XYZ classification
        - category_patterns: Category-level intelligence
        - total_adjustments: Count of logged adjustments
        - applied_adjustments: Count of applied adjustments
    """
    try:
        # Query recent adjustments (last 90 days)
        adjustments_query = """
            SELECT
                adjustment_type,
                COUNT(*) as count,
                AVG(adjustment_magnitude) as avg_magnitude,
                AVG(confidence_score) as avg_confidence,
                SUM(CASE WHEN applied = 1 THEN 1 ELSE 0 END) as applied_count
            FROM forecast_learning_adjustments
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
            GROUP BY adjustment_type
            ORDER BY count DESC
        """
        adjustments_result = execute_query(adjustments_query, None, fetch_all=True)

        # Query top adjustments by type for detail
        top_growth_query = """
            SELECT
                sku_id,
                original_value,
                adjusted_value,
                adjustment_magnitude,
                confidence_score,
                learning_reason,
                created_at
            FROM forecast_learning_adjustments
            WHERE adjustment_type = 'growth_rate'
                AND created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
            ORDER BY ABS(adjustment_magnitude) DESC
            LIMIT 10
        """
        top_growth_result = execute_query(top_growth_query, None, fetch_all=True)

        # Query method recommendations (from Phase 3 learning)
        method_query = """
            SELECT
                sku_id,
                adjustment_type,
                learning_reason,
                confidence_score,
                created_at
            FROM forecast_learning_adjustments
            WHERE adjustment_type = 'method_recommendation'
                AND created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
            ORDER BY confidence_score DESC
            LIMIT 20
        """
        method_result = execute_query(method_query, None, fetch_all=True)

        return {
            "adjustments_by_type": [
                {
                    "type": row['adjustment_type'],
                    "count": row['count'],
                    "avg_magnitude": float(row['avg_magnitude'] or 0.0),
                    "avg_confidence": float(row['avg_confidence'] or 0.0),
                    "applied_count": row['applied_count']
                }
                for row in adjustments_result
            ],
            "top_growth_adjustments": [
                {
                    "sku_id": row['sku_id'],
                    "original_value": float(row['original_value'] or 0.0),
                    "adjusted_value": float(row['adjusted_value'] or 0.0),
                    "magnitude": float(row['adjustment_magnitude'] or 0.0),
                    "confidence": float(row['confidence_score'] or 0.0),
                    "reason": row['learning_reason'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None
                }
                for row in top_growth_result
            ],
            "method_recommendations": [
                {
                    "sku_id": row['sku_id'],
                    "recommendation": row['learning_reason'],
                    "confidence": float(row['confidence_score'] or 0.0),
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None
                }
                for row in method_result
            ],
            "total_adjustments": sum(row['count'] for row in adjustments_result),
            "applied_adjustments": sum(row['applied_count'] for row in adjustments_result)
        }

    except Exception as e:
        logger.error(f"API: Failed to get learning insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get learning insights: {str(e)}")
