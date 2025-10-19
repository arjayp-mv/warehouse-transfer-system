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

        logger.info(f"API: SKU Filter: {sku_filter}, Warehouse: {request.warehouse}, Growth Rate: {request.growth_rate}")

        # Start forecast generation (background job)
        run_id = start_forecast_generation(
            forecast_name=request.forecast_name,
            sku_filter=sku_filter if sku_filter else None,
            warehouse=request.warehouse,
            growth_rate=request.growth_rate
        )

        logger.info(f"API: Forecast generation started successfully with run_id={run_id}")

        return {
            "run_id": run_id,
            "status": "pending",
            "message": "Forecast generation started successfully"
        }

    except ValueError as e:
        # No SKUs found matching filter criteria
        raise HTTPException(
            status_code=400,
            detail=f"Filter validation error: {str(e)}"
        )
    except RuntimeError as e:
        # Another forecast job is already running
        raise HTTPException(
            status_code=409,
            detail=f"Conflict: {str(e)}"
        )
    except Exception as e:
        # Unexpected error
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: Failed to start forecast generation. {str(e)}"
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
    sku_filter: Optional[str] = None
):
    """
    Get forecast results for a completed forecast run.

    Returns paginated list of SKU forecasts with monthly quantities and revenues.

    Args:
        run_id: Forecast run ID
        page: Page number (starts at 1)
        page_size: Number of SKUs per page (max 100)
        sku_filter: Optional SKU ID filter (partial match)

    Returns:
        Dictionary with forecast results and pagination metadata
    """
    try:
        # Enforce pagination (best practice)
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        # Build query with optional SKU filter
        where_clause = "forecast_run_id = %s"
        params = [run_id]

        if sku_filter:
            where_clause += " AND sku_id LIKE %s"
            params.append(f"%{sku_filter}%")

        # Get total count
        count_query = f"""
            SELECT COUNT(*) as total
            FROM forecast_details
            WHERE {where_clause}
        """
        total_result = execute_query(count_query, params=tuple(params), fetch_all=True)
        total_count = total_result[0]['total']

        # Get paginated results
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
                fd.seasonal_pattern_applied
            FROM forecast_details fd
            JOIN skus s ON fd.sku_id = s.sku_id
            WHERE {where_clause}
            ORDER BY s.abc_code, s.xyz_code, fd.sku_id
            LIMIT %s OFFSET %s
        """

        params.extend([page_size, offset])
        results = execute_query(query, params=tuple(params), fetch_all=True)

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
                'seasonal_pattern': row['seasonal_pattern_applied']
            })

        return {
            'run_id': run_id,
            'forecasts': forecasts,
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
