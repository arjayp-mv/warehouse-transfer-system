"""
Run forecast learning algorithms after accuracy updates.

This script orchestrates all learning algorithms and should be run
monthly after the accuracy update completes (typically on the 2nd of each month).

It executes:
1. Growth rate adjustment learning
2. Method effectiveness analysis
3. Category pattern learning
4. Problem SKU identification

All adjustments are logged as recommendations to the
forecast_learning_adjustments table for manual review.

Usage:
    python backend/run_forecast_learning.py

Scheduling:
    Windows Task Scheduler: Run monthly on 2nd at 3:00 AM
    Linux/Mac cron: 0 3 2 * * cd /path/to/project && python backend/run_forecast_learning.py

V8.0 Phase 3 - Multi-Dimensional Learning
"""

import sys
import logging
from datetime import datetime
from backend.forecast_learning import (
    ForecastLearningEngine,
    identify_problem_skus
)

# Configure logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/forecast_learning.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def run_learning_cycle():
    """
    Execute all learning algorithms.

    Should run monthly after accuracy update completes.
    Generates recommendations for forecasting parameter adjustments
    based on observed accuracy patterns.

    Returns:
        Dictionary with learning cycle results
    """
    logger.info("="*60)
    logger.info("Starting Forecast Learning Cycle")
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)

    try:
        # Instantiate learning engine
        engine = ForecastLearningEngine()

        # Step 1: Adjust growth rates
        logger.info("\n[1/4] Analyzing growth rate patterns...")
        growth_result = engine.learn_growth_adjustments()

        if 'error' in growth_result:
            logger.error(f"Growth adjustment failed: {growth_result['error']}")
        else:
            logger.info(f"SKUs analyzed: {growth_result['skus_analyzed']}")
            logger.info(f"Adjustments logged: {growth_result['adjustments_logged']}")

        # Step 2: Analyze method performance
        logger.info("\n[2/4] Analyzing forecasting method effectiveness...")
        method_result = engine.learn_method_effectiveness()

        if 'error' in method_result:
            logger.error(f"Method analysis failed: {method_result['error']}")
        else:
            logger.info(f"Method classifications analyzed: {method_result['total_method_classifications']}")
            logger.info(f"Best methods identified for {len(method_result['best_methods_by_class'])} classifications")

        # Step 3: Learn from categories
        logger.info("\n[3/4] Analyzing category patterns...")
        category_result = engine.learn_from_categories()

        if 'error' in category_result:
            logger.error(f"Category analysis failed: {category_result['error']}")
        else:
            logger.info(f"Categories analyzed: {category_result['categories_analyzed']}")

        # Step 4: Identify problem SKUs
        logger.info("\n[4/4] Identifying problem SKUs...")
        problems = identify_problem_skus(mape_threshold=30.0)
        logger.info(f"Problem SKUs detected: {len(problems)}")

        if problems:
            logger.warning("\nTop 5 Problem SKUs:")
            for problem in problems[:5]:
                logger.warning(
                    f"  {problem['sku_id']}: MAPE={problem['avg_mape']:.1f}%, "
                    f"Bias={problem['avg_bias']:.1f}%, "
                    f"Method={problem['forecast_method']}"
                )
                for rec in problem['recommendations']:
                    logger.warning(f"    - {rec}")

        # Summary
        logger.info("\n" + "="*60)
        logger.info("Learning Cycle Complete!")
        logger.info("="*60)
        logger.info(f"Growth adjustments: {growth_result.get('adjustments_logged', 0)}")
        logger.info(f"Method classifications: {len(method_result.get('best_methods_by_class', {}))}")
        logger.info(f"Category patterns: {category_result.get('categories_analyzed', 0)}")
        logger.info(f"Problem SKUs: {len(problems)}")
        logger.info("\nRecommendations logged to forecast_learning_adjustments table")
        logger.info("Review and apply adjustments via dashboard or API")

        return {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'growth_adjustments': growth_result,
            'method_analysis': method_result,
            'category_patterns': category_result,
            'problem_skus_count': len(problems),
            'problem_skus_top5': problems[:5] if problems else []
        }

    except Exception as e:
        logger.error(f"Fatal error during learning cycle: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


if __name__ == "__main__":
    result = run_learning_cycle()

    # Exit with appropriate code
    if result.get('success'):
        sys.exit(0)
    else:
        sys.exit(1)
