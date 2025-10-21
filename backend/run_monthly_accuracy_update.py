"""
Standalone script to run monthly accuracy update.

V8.0 Phase 2: Stockout-Aware Accuracy Update

This script can be:
1. Run manually from command line
2. Triggered via API endpoint (POST /api/forecasts/accuracy/update)
3. Scheduled with Windows Task Scheduler or cron (OPTIONAL)

Usage:
    python backend/run_monthly_accuracy_update.py
    python backend/run_monthly_accuracy_update.py --month 2025-09

The script will:
- Update forecast_accuracy records with actual demand from monthly_sales
- Calculate accuracy metrics (MAPE) excluding stockout-affected periods
- Log detailed results to logs/forecast_accuracy_update.log
"""

import sys
import logging
import argparse
from datetime import datetime
from backend.forecast_accuracy import update_monthly_accuracy

# Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/forecast_accuracy_update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Run monthly accuracy update."""

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Update forecast accuracy by comparing predictions to actuals'
    )
    parser.add_argument(
        '--month',
        type=str,
        default=None,
        help='Target month in YYYY-MM format (default: last month)'
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Starting Monthly Forecast Accuracy Update")
    logger.info("=" * 60)

    try:
        # Update accuracy for specified month (or last month if None)
        result = update_monthly_accuracy(target_month=args.month)

        # Log results
        logger.info("Update Results:")
        logger.info(f"  Month Updated: {result.get('month_updated')}")
        logger.info(f"  Total Forecasts: {result.get('total_forecasts')}")
        logger.info(f"  Actuals Found: {result.get('actuals_found')}")
        logger.info(f"  Missing Actuals: {result.get('missing_actuals')}")
        logger.info(f"  Average MAPE: {result.get('avg_mape', 0.0):.2f}%")
        logger.info(f"  Stockout-Affected: {result.get('stockout_affected_count', 0)}")

        # Log errors if any
        if result.get('errors'):
            logger.warning(f"Errors encountered: {len(result['errors'])}")
            # Log first 10 errors for debugging
            for i, error in enumerate(result['errors'][:10], 1):
                logger.warning(f"  Error {i}: {error}")
            if len(result['errors']) > 10:
                logger.warning(f"  ... and {len(result['errors']) - 10} more errors")

        logger.info("=" * 60)
        logger.info("Monthly accuracy update completed successfully")
        logger.info("=" * 60)

        # Exit with success code
        sys.exit(0)

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"Fatal error during accuracy update: {e}", exc_info=True)
        logger.error("=" * 60)

        # Exit with error code
        sys.exit(1)


if __name__ == "__main__":
    main()
