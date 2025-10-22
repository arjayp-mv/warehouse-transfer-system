"""
Background Job Processing for Forecast Generation

This module implements background job processing for generating forecasts.
It uses threading to avoid blocking the main application while processing
large batches of SKUs.

V7.3 Phase 4: Added queue management system to handle concurrent forecast requests.
Jobs are queued in FIFO order when a forecast is already running.

Following best practices from claude-code-best-practices.md:
- Thread-based workers for background processing
- Batch processing (100 SKUs at a time)
- Progress tracking in database
- Error handling and recovery
- Queue management for concurrent requests
"""

import threading
import time
import logging
import queue
from typing import List, Dict
from datetime import datetime
from backend.database import execute_query
from backend.forecasting import ForecastEngine, update_forecast_run_status

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# V7.3 Phase 4: Global forecast queue for handling concurrent requests
_forecast_queue = queue.Queue()
_queue_lock = threading.Lock()


class ForecastJobWorker:
    """
    Background worker that processes forecast generation jobs.

    This worker runs in a separate thread and processes SKUs in batches,
    updating progress in the forecast_runs table.
    """

    def __init__(self):
        """Initialize the forecast job worker."""
        self.is_running = False
        self.current_job_id = None
        self.worker_thread = None

    def start_forecast_job(
        self,
        run_id: int,
        sku_ids: List[str],
        warehouse: str = 'combined',
        growth_rate: float = 0.0
    ) -> None:
        """
        Start a forecast generation job in the background.

        Args:
            run_id: Forecast run ID
            sku_ids: List of SKU IDs to process
            warehouse: Warehouse location
            growth_rate: Growth rate to apply

        Raises:
            RuntimeError: If a job is already running
        """
        if self.is_running:
            raise RuntimeError("A forecast job is already running")

        self.is_running = True
        self.current_job_id = run_id

        # Start worker thread
        self.worker_thread = threading.Thread(
            target=self._run_forecast_job,
            args=(run_id, sku_ids, warehouse, growth_rate),
            daemon=True
        )
        self.worker_thread.start()

    def _run_forecast_job(
        self,
        run_id: int,
        sku_ids: List[str],
        warehouse: str,
        growth_rate: float
    ) -> None:
        """
        Execute the forecast generation job.

        This runs in a background thread and processes SKUs in batches.

        Args:
            run_id: Forecast run ID
            sku_ids: List of SKU IDs to process
            warehouse: Warehouse location
            growth_rate: Growth rate to apply
        """
        start_time = time.time()

        try:
            logger.info(f"[Run {run_id}] Starting forecast job with {len(sku_ids)} SKUs")
            logger.info(f"[Run {run_id}] Warehouse: {warehouse}, Growth Rate: {growth_rate}")

            # Sync stockout days from stockout_dates table before forecasting
            logger.info(f"[Run {run_id}] Syncing stockout days from stockout_dates table...")
            from backend.database import sync_all_stockout_days
            sync_result = sync_all_stockout_days()
            if sync_result['success']:
                logger.info(f"[Run {run_id}] Stockout sync complete: {sync_result['processed_records']} records updated for {sync_result['processed_skus']} SKUs")
            else:
                logger.warning(f"[Run {run_id}] Stockout sync had {len(sync_result.get('errors', []))} errors")

            # Update status to running
            update_forecast_run_status(
                run_id,
                status='running',
                total_skus=len(sku_ids),
                processed_skus=0,
                failed_skus=0
            )
            logger.info(f"[Run {run_id}] Status updated to 'running'")

            # Initialize forecast engine
            logger.info(f"[Run {run_id}] Initializing ForecastEngine")
            # growth_rate is now manual_growth_override (if None, rates are auto-calculated per SKU)
            engine = ForecastEngine(run_id, manual_growth_override=growth_rate)

            processed_count = 0
            failed_count = 0
            batch_size = 100

            # Process SKUs in batches
            logger.info(f"[Run {run_id}] Processing SKUs in batches of {batch_size}")
            for i in range(0, len(sku_ids), batch_size):
                batch = sku_ids[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(sku_ids) + batch_size - 1) // batch_size

                logger.info(f"[Run {run_id}] Processing batch {batch_num}/{total_batches} ({len(batch)} SKUs)")

                for sku_id in batch:
                    try:
                        # Generate forecast for SKU
                        forecast_data = engine.generate_forecast_for_sku(sku_id, warehouse)

                        # Save forecast
                        success = engine.save_forecast(forecast_data)

                        if success:
                            processed_count += 1
                        else:
                            failed_count += 1
                            logger.warning(f"[Run {run_id}] Failed to save forecast for SKU {sku_id}")

                    except Exception as e:
                        logger.error(f"[Run {run_id}] Failed to generate forecast for SKU {sku_id}: {e}", exc_info=True)
                        failed_count += 1

                # Update progress after each batch
                update_forecast_run_status(
                    run_id,
                    status='running',
                    processed_skus=processed_count,
                    failed_skus=failed_count
                )
                logger.info(f"[Run {run_id}] Batch {batch_num} complete: {processed_count} processed, {failed_count} failed")

            # Mark job as completed
            duration = time.time() - start_time
            final_status = 'completed' if failed_count == 0 else 'completed'

            update_forecast_run_status(
                run_id,
                status=final_status,
                processed_skus=processed_count,
                failed_skus=failed_count
            )

            logger.info(f"[Run {run_id}] Job completed in {duration:.2f}s: {processed_count} processed, {failed_count} failed")

        except Exception as e:
            # Catch any unhandled exceptions in the entire job
            duration = time.time() - start_time
            error_msg = f"Fatal error in forecast job: {str(e)}"
            logger.error(f"[Run {run_id}] {error_msg}", exc_info=True)

            # Update run status to failed
            update_forecast_run_status(
                run_id,
                status='failed',
                error_message=error_msg
            )

        finally:
            # V7.3 Phase 4: Always reset worker state and process next queued job
            self.is_running = False
            self.current_job_id = None

            # Process next job in queue if any
            _process_next_queued_job()

    def get_job_status(self, run_id: int) -> Dict:
        """
        Get current status of a forecast job.

        Args:
            run_id: Forecast run ID

        Returns:
            Dictionary with job status and progress
        """
        query = """
            SELECT id, forecast_name, forecast_date, status,
                   total_skus, processed_skus, failed_skus,
                   created_at, started_at, completed_at,
                   duration_seconds, error_message
            FROM forecast_runs
            WHERE id = %s
        """

        result = execute_query(query, params=(run_id,), fetch_all=True)

        if not result:
            return {'error': 'Forecast run not found'}

        job = result[0]

        # Calculate progress percentage
        if job['total_skus'] and job['total_skus'] > 0:
            progress = (job['processed_skus'] / job['total_skus']) * 100
        else:
            progress = 0

        return {
            'run_id': job['id'],
            'name': job['forecast_name'],
            'status': job['status'],
            'progress_percent': round(progress, 1),
            'total_skus': job['total_skus'],
            'processed_skus': job['processed_skus'],
            'failed_skus': job['failed_skus'],
            'created_at': job['created_at'].isoformat() if job['created_at'] else None,
            'started_at': job['started_at'].isoformat() if job['started_at'] else None,
            'completed_at': job['completed_at'].isoformat() if job['completed_at'] else None,
            'duration_seconds': float(job['duration_seconds']) if job['duration_seconds'] else None,
            'error_message': job['error_message']
        }

    def cancel_job(self, run_id: int) -> bool:
        """
        Cancel a running forecast job.

        Args:
            run_id: Forecast run ID to cancel

        Returns:
            True if cancelled successfully, False otherwise
        """
        if self.current_job_id == run_id and self.is_running:
            update_forecast_run_status(
                run_id,
                status='cancelled',
                error_message='Job cancelled by user'
            )
            self.is_running = False
            return True

        return False


# V7.3 Phase 4: Queue processing function
def _process_next_queued_job():
    """
    Process the next forecast job in the queue.

    This function is called automatically when a forecast job completes.
    It checks if there are any queued jobs and starts the next one in FIFO order.
    """
    if not _forecast_queue.empty():
        next_job = _forecast_queue.get()

        logger.info(f"Processing queued forecast {next_job['run_id']}")

        # Update status from 'queued' to 'running' will happen in _run_forecast_job
        # Clear queue_position since job is starting now
        query = """
            UPDATE forecast_runs
            SET queue_position = NULL
            WHERE id = %s
        """
        execute_query(query, params=(next_job['run_id'],))

        # Start the queued job
        _forecast_worker.start_forecast_job(
            next_job['run_id'],
            next_job['sku_ids'],
            next_job['warehouse'],
            next_job['growth_rate']
        )


# Global worker instance
_forecast_worker = ForecastJobWorker()


def start_forecast_generation(
    forecast_name: str,
    sku_filter: Dict = None,
    warehouse: str = 'combined',
    growth_rate: float = 0.0
) -> Dict:
    """
    Start a new forecast generation job or queue it if another job is running.

    V7.3 Phase 4: Changed to return dict with status instead of just run_id.
    If a job is already running, the new job is queued in FIFO order.

    Args:
        forecast_name: User-friendly name for this forecast
        sku_filter: Optional filter criteria including:
                   - status_filter: List of statuses to include (e.g., ['Active', 'Death Row'])
                   - abc_code: ABC classification filter (e.g., 'A')
                   - xyz_code: XYZ classification filter (e.g., 'X')
                   - category: Category filter
                   If not provided, defaults to all statuses and no ABC/XYZ filters
        warehouse: Warehouse location ('burnaby', 'kentucky', 'combined')
        growth_rate: Optional growth rate to apply (e.g., 0.05 for 5% growth)

    Returns:
        Dictionary with keys:
        - run_id: Forecast run ID
        - status: 'started' (job started immediately) or 'queued' (job queued)
        - queue_position: Position in queue (only if status='queued')

    Raises:
        ValueError: If no SKUs match the filter criteria
    """
    from backend.forecasting import create_forecast_run

    logger.info(f"Starting forecast generation: '{forecast_name}'")
    logger.info(f"Filters: {sku_filter}, Warehouse: {warehouse}, Growth Rate: {growth_rate}")

    # Get SKUs to process based on filter
    sku_ids = _get_skus_to_forecast(sku_filter)
    logger.info(f"Retrieved {len(sku_ids)} SKUs matching filter criteria")

    # Validate SKU list
    if not sku_ids or len(sku_ids) == 0:
        error_msg = f"No SKUs found matching filter: {sku_filter}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if a job is currently running
    if _forecast_worker.is_running:
        # Another forecast is running - queue this one
        with _queue_lock:
            queue_position = _forecast_queue.qsize() + 1

        # Create forecast run entry with 'queued' status
        run_id = create_forecast_run(forecast_name, growth_rate, warehouse, status='queued')
        logger.info(f"Created queued forecast run with ID: {run_id}, position: {queue_position}")

        # Update queue position in database
        query = """
            UPDATE forecast_runs
            SET queue_position = %s, queued_at = NOW()
            WHERE id = %s
        """
        execute_query(query, params=(queue_position, run_id))

        # Add to queue
        _forecast_queue.put({
            'run_id': run_id,
            'sku_ids': sku_ids,
            'warehouse': warehouse,
            'growth_rate': growth_rate
        })

        logger.info(f"Forecast {run_id} queued at position {queue_position}")

        return {
            'run_id': run_id,
            'status': 'queued',
            'queue_position': queue_position
        }

    else:
        # No forecast running - start immediately
        run_id = create_forecast_run(forecast_name, growth_rate, warehouse)
        logger.info(f"Created forecast run with ID: {run_id}")

        logger.info(f"Starting background job for {len(sku_ids)} SKUs")
        _forecast_worker.start_forecast_job(run_id, sku_ids, warehouse, growth_rate)

        return {
            'run_id': run_id,
            'status': 'started'
        }


def _get_skus_to_forecast(sku_filter: Dict = None) -> List[str]:
    """
    Get list of SKU IDs to include in forecast.

    Args:
        sku_filter: Optional filter criteria including:
                   - abc_code: ABC classification filter
                   - xyz_code: XYZ classification filter
                   - category: Category filter
                   - status_filter: List of statuses to include (default: all statuses)

    Returns:
        List of SKU IDs
    """
    # Build query with optional filters
    params = []
    where_clauses = []

    # Handle status filter - default to all statuses if not specified
    if sku_filter and 'status_filter' in sku_filter:
        statuses = sku_filter['status_filter']
        if statuses and len(statuses) > 0:
            placeholders = ','.join(['%s'] * len(statuses))
            where_clauses.append(f'status IN ({placeholders})')
            params.extend(statuses)
            logger.info(f"Filtering by statuses: {statuses}")
    else:
        # Default: include all three statuses
        where_clauses.append("status IN ('Active', 'Death Row', 'Discontinued')")
        logger.info("Using default status filter: Active, Death Row, Discontinued")

    if sku_filter:
        if 'abc_code' in sku_filter:
            where_clauses.append('abc_code = %s')
            params.append(sku_filter['abc_code'])
            logger.info(f"Filtering by ABC code: {sku_filter['abc_code']}")

        if 'xyz_code' in sku_filter:
            where_clauses.append('xyz_code = %s')
            params.append(sku_filter['xyz_code'])
            logger.info(f"Filtering by XYZ code: {sku_filter['xyz_code']}")

        if 'category' in sku_filter:
            where_clauses.append('category = %s')
            params.append(sku_filter['category'])
            logger.info(f"Filtering by category: {sku_filter['category']}")

    where_clause = ' AND '.join(where_clauses)

    query = f"""
        SELECT sku_id
        FROM skus
        WHERE {where_clause}
        ORDER BY abc_code, xyz_code, sku_id
    """

    logger.info(f"Executing SKU query with WHERE clause: {where_clause}")
    logger.info(f"Query parameters: {params}")

    results = execute_query(query, params=tuple(params) if params else None, fetch_all=True)

    sku_ids = [row['sku_id'] for row in results]
    logger.info(f"Found {len(sku_ids)} SKUs matching criteria")

    return sku_ids


def get_forecast_status(run_id: int) -> Dict:
    """
    Get status of a forecast generation job.

    Args:
        run_id: Forecast run ID

    Returns:
        Dictionary with job status and progress
    """
    return _forecast_worker.get_job_status(run_id)


def cancel_forecast(run_id: int) -> bool:
    """
    Cancel a running forecast generation job.

    Args:
        run_id: Forecast run ID

    Returns:
        True if cancelled successfully, False otherwise
    """
    return _forecast_worker.cancel_job(run_id)


def get_active_forecast_runs(limit: int = 10) -> List[Dict]:
    """
    Get list of recent forecast runs (excludes archived forecasts).

    Args:
        limit: Maximum number of runs to return

    Returns:
        List of forecast run dictionaries (non-archived only)
    """
    query = """
        SELECT id, forecast_name, forecast_date, status,
               total_skus, processed_skus, failed_skus,
               created_at, completed_at, duration_seconds
        FROM forecast_runs
        WHERE archived = 0
        ORDER BY created_at DESC
        LIMIT %s
    """

    results = execute_query(query, params=(limit,), fetch_all=True)

    runs = []
    for row in results:
        # Calculate progress
        if row['total_skus'] and row['total_skus'] > 0:
            progress = (row['processed_skus'] / row['total_skus']) * 100
        else:
            progress = 0

        runs.append({
            'run_id': row['id'],
            'name': row['forecast_name'],
            'status': row['status'],
            'progress_percent': round(progress, 1),
            'total_skus': row['total_skus'],
            'processed_skus': row['processed_skus'],
            'failed_skus': row['failed_skus'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'completed_at': row['completed_at'].isoformat() if row['completed_at'] else None,
            'duration_seconds': float(row['duration_seconds']) if row['duration_seconds'] else None
        })

    return runs
