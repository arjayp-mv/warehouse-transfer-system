"""
Background Scheduler for Monthly Supplier Order Recommendations

This module implements a scheduled background job that automatically generates
supplier order recommendations on the 1st of each month at 6:00 AM.

V9.0: Monthly auto-generation of supplier order recommendations
"""

import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from backend.database import get_db
from backend.supplier_ordering_calculations import generate_monthly_recommendations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MonthlySupplierOrderScheduler:
    """
    Scheduler that runs monthly supplier order recommendation generation
    on the 1st of each month at 6:00 AM.
    """

    def __init__(self):
        """Initialize the monthly scheduler."""
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.last_run_month: Optional[str] = None
        self.stop_event = threading.Event()

    def start(self):
        """
        Start the scheduler in a background thread.
        """
        if self.is_running:
            logger.warning("Scheduler is already running")
            return

        self.is_running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("Monthly supplier order scheduler started")

    def stop(self):
        """
        Stop the scheduler gracefully.
        """
        if not self.is_running:
            return

        self.stop_event.set()
        self.is_running = False

        if self.thread:
            self.thread.join(timeout=5)

        logger.info("Monthly supplier order scheduler stopped")

    def _run_scheduler(self):
        """
        Main scheduler loop that checks every hour if it's time to run the job.
        Target: 1st of each month at 6:00 AM
        """
        while not self.stop_event.is_set():
            try:
                now = datetime.now()
                current_month = now.strftime('%Y-%m')

                # Check if it's the 1st of the month, 6 AM hour, and we haven't run this month yet
                if (now.day == 1 and
                    now.hour == 6 and
                    self.last_run_month != current_month):

                    logger.info(f"Triggering monthly supplier order generation for {current_month}")
                    self._execute_monthly_generation(current_month)
                    self.last_run_month = current_month

                # Sleep for 1 hour before next check
                # Use stop_event.wait() instead of time.sleep() for graceful shutdown
                self.stop_event.wait(timeout=3600)  # 1 hour

            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}", exc_info=True)
                # Wait 5 minutes before retry on error
                self.stop_event.wait(timeout=300)

    def _execute_monthly_generation(self, order_month: str):
        """
        Execute the monthly order generation job.

        Args:
            order_month: Month in YYYY-MM format
        """
        start_time = datetime.now()
        logger.info(f"Starting monthly order generation for {order_month}")

        try:
            db = next(get_db())

            # Call the generation function
            result = generate_monthly_recommendations(db, order_month)

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Log success
            logger.info(
                f"Monthly order generation completed successfully for {order_month}. "
                f"Generated: {result.get('total_generated', 0)} orders, "
                f"Duration: {duration:.2f} seconds"
            )

            # Could add email notification here if needed
            # send_success_notification(order_month, result)

        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.error(
                f"Monthly order generation FAILED for {order_month}. "
                f"Error: {str(e)}, "
                f"Duration: {duration:.2f} seconds",
                exc_info=True
            )

            # Could add email notification for failures
            # send_failure_notification(order_month, str(e))

        finally:
            if db:
                db.close()

    def trigger_manual_run(self, order_month: Optional[str] = None):
        """
        Manually trigger order generation (for testing or manual runs).

        Args:
            order_month: Month in YYYY-MM format. Defaults to current month.

        Returns:
            dict: Result of the generation
        """
        if not order_month:
            order_month = datetime.now().strftime('%Y-%m')

        logger.info(f"Manual trigger for order generation: {order_month}")
        self._execute_monthly_generation(order_month)
        return {"success": True, "order_month": order_month}


# Global scheduler instance
_scheduler_instance: Optional[MonthlySupplierOrderScheduler] = None


def get_scheduler() -> MonthlySupplierOrderScheduler:
    """
    Get or create the global scheduler instance.

    Returns:
        MonthlySupplierOrderScheduler: The global scheduler instance
    """
    global _scheduler_instance

    if _scheduler_instance is None:
        _scheduler_instance = MonthlySupplierOrderScheduler()

    return _scheduler_instance


def start_scheduler():
    """
    Start the monthly supplier order scheduler.
    Called from main.py on application startup.
    """
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("Monthly supplier order scheduler initialized")


def stop_scheduler():
    """
    Stop the monthly supplier order scheduler.
    Called from main.py on application shutdown.
    """
    scheduler = get_scheduler()
    scheduler.stop()
    logger.info("Monthly supplier order scheduler shutdown")
