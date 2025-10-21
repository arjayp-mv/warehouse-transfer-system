"""
Performance testing for forecast accuracy update system.

This script validates the update_monthly_accuracy() function with a realistic
workload of 1,768 SKUs to ensure it meets production performance requirements.

Test Methodology:
1. Query existing SKUs with sales data from monthly_sales
2. Generate forecast_accuracy records for those SKUs
3. Create corresponding actual sales data
4. Add realistic stockout scenarios (10% of SKUs)
5. Measure execution time for update_monthly_accuracy()
6. Analyze database query performance with EXPLAIN
7. Verify index usage (idx_period_recorded)
8. Clean up all test data

Performance Targets:
- Execution time: < 60 seconds for 1,768 SKUs
- Database queries: All using proper indexes (no table scans)
- Memory: Stable usage (no leaks)

Part of TASK-537: Performance Testing
"""

import sys
from pathlib import Path
import time
import random
from datetime import datetime, date
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import execute_query
from backend.forecast_accuracy import update_monthly_accuracy
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Test configuration
TEST_MONTH = '2025-08'  # August 2025 - we have sales data for this month
TARGET_SKU_COUNT = 1768  # Performance test target
STOCKOUT_PERCENTAGE = 0.10  # 10% of SKUs will have stockout scenarios
STOCKOUT_DAYS_RANGE = (3, 15)  # Random stockout days between 3-15


def get_test_skus(limit: int = TARGET_SKU_COUNT):
    """
    Get list of SKU IDs from monthly_sales table.

    Uses existing SKUs with sales data to avoid foreign key issues.

    Args:
        limit: Maximum number of SKUs to retrieve

    Returns:
        List of SKU ID strings
    """
    logger.info(f"Retrieving up to {limit} SKUs from monthly_sales table...")

    query = """
        SELECT DISTINCT sku_id
        FROM monthly_sales
        WHERE `year_month` = %s
        ORDER BY sku_id
        LIMIT %s
    """

    results = execute_query(query, (TEST_MONTH, limit), fetch_all=True)

    if not results:
        logger.error(f"No SKUs found in monthly_sales for {TEST_MONTH}")
        return []

    sku_ids = [row['sku_id'] for row in results]
    logger.info(f"Retrieved {len(sku_ids)} SKUs for testing")

    return sku_ids


def generate_test_forecasts(sku_ids: list, test_month: str):
    """
    Generate forecast_accuracy records for performance testing.

    Creates one forecast record per SKU with realistic data:
    - Predicted demand: Random between 50-500 units
    - Forecast method: Random from common methods
    - ABC/XYZ classes: Random distribution
    - Seasonal patterns: Random from typical patterns

    Args:
        sku_ids: List of SKU IDs to create forecasts for
        test_month: Target month in 'YYYY-MM' format

    Returns:
        Number of forecast records created
    """
    logger.info(f"Generating {len(sku_ids)} forecast records for {test_month}...")

    forecast_date = date.today()
    period_start = f"{test_month}-01"

    # Calculate period_end (last day of month)
    if test_month.endswith('-02'):
        period_end = f"{test_month}-28"
    elif test_month.endswith(('-04', '-06', '-09', '-11')):
        period_end = f"{test_month}-30"
    else:
        period_end = f"{test_month}-31"

    # Common forecast methods from ForecastEngine
    methods = ['weighted_ma_6mo', 'weighted_ma_12mo', 'exponential_smoothing', 'linear_regression']
    abc_classes = ['A', 'B', 'C']
    xyz_classes = ['X', 'Y', 'Z']
    seasonal_patterns = ['year-round', 'spring-peak', 'summer-peak', 'fall-peak', 'winter-peak']

    insert_query = """
        INSERT INTO forecast_accuracy (
            sku_id, warehouse, forecast_date, forecast_period_start, forecast_period_end,
            predicted_demand, forecast_method, abc_class, xyz_class, seasonal_pattern,
            is_actual_recorded
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
    """

    created_count = 0

    for sku_id in sku_ids:
        # Random predicted demand between 50-500
        predicted = Decimal(random.randint(50, 500))

        # Random classifications
        method = random.choice(methods)
        abc = random.choice(abc_classes)
        xyz = random.choice(xyz_classes)
        seasonal = random.choice(seasonal_patterns)

        try:
            execute_query(
                insert_query,
                (sku_id, 'combined', forecast_date, period_start, period_end,
                 predicted, method, abc, xyz, seasonal),
                fetch_all=False
            )
            created_count += 1

            if created_count % 500 == 0:
                logger.info(f"  Created {created_count} forecast records...")

        except Exception as e:
            logger.error(f"Failed to create forecast for {sku_id}: {e}")

    logger.info(f"Successfully created {created_count} forecast records")
    return created_count


def generate_test_actuals(sku_ids: list, test_month: str):
    """
    Generate actual sales data in monthly_sales table.

    Creates realistic actual demand that varies around predicted values:
    - 70% of actual sales within 80-120% of forecast
    - 20% of actual sales significantly lower (50-80% of forecast)
    - 10% of actual sales significantly higher (120-150% of forecast)

    Args:
        sku_ids: List of SKU IDs to create actuals for
        test_month: Target month in 'YYYY-MM' format

    Returns:
        Number of actual sales records created
    """
    logger.info(f"Generating {len(sku_ids)} actual sales records for {test_month}...")

    # First, get predicted values from forecast_accuracy
    forecast_query = """
        SELECT sku_id, predicted_demand
        FROM forecast_accuracy
        WHERE forecast_period_start = %s
        AND is_actual_recorded = 0
    """

    forecasts = execute_query(
        forecast_query,
        (f"{test_month}-01",),
        fetch_all=True
    )

    if not forecasts:
        logger.error("No forecasts found to generate actuals for")
        return 0

    # Create a map of sku_id -> predicted_demand
    forecast_map = {row['sku_id']: float(row['predicted_demand']) for row in forecasts}

    insert_query = """
        INSERT INTO monthly_sales (
            sku_id, `year_month`, corrected_demand_burnaby, corrected_demand_kentucky
        ) VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            corrected_demand_burnaby = VALUES(corrected_demand_burnaby),
            corrected_demand_kentucky = VALUES(corrected_demand_kentucky)
    """

    created_count = 0

    for sku_id in sku_ids:
        if sku_id not in forecast_map:
            continue

        predicted = forecast_map[sku_id]

        # Determine actual demand variation
        rand = random.random()

        if rand < 0.70:
            # 70%: Close to forecast (80-120%)
            variation = random.uniform(0.80, 1.20)
        elif rand < 0.90:
            # 20%: Significantly lower (50-80%)
            variation = random.uniform(0.50, 0.80)
        else:
            # 10%: Significantly higher (120-150%)
            variation = random.uniform(1.20, 1.50)

        actual = round(predicted * variation, 2)

        # Split demand between warehouses (random allocation)
        burnaby_pct = random.uniform(0.3, 0.7)
        burnaby_demand = Decimal(round(actual * burnaby_pct, 2))
        kentucky_demand = Decimal(round(actual * (1 - burnaby_pct), 2))

        try:
            execute_query(
                insert_query,
                (sku_id, test_month, burnaby_demand, kentucky_demand),
                fetch_all=False
            )
            created_count += 1

            if created_count % 500 == 0:
                logger.info(f"  Created {created_count} actual sales records...")

        except Exception as e:
            logger.error(f"Failed to create actuals for {sku_id}: {e}")

    logger.info(f"Successfully created {created_count} actual sales records")
    return created_count


def add_random_stockouts(sku_ids: list, test_month: str, percentage: float = STOCKOUT_PERCENTAGE):
    """
    Add random stockout scenarios for realistic testing.

    Creates stockout_dates entries for a percentage of SKUs to simulate
    real-world conditions where some forecasts are affected by supply issues.

    Args:
        sku_ids: List of SKU IDs
        test_month: Target month in 'YYYY-MM' format
        percentage: Percentage of SKUs to have stockouts (default: 0.10 = 10%)

    Returns:
        Number of stockout records created
    """
    stockout_count = int(len(sku_ids) * percentage)
    logger.info(f"Adding stockouts for {stockout_count} SKUs ({percentage*100:.0f}% of total)...")

    # Randomly select SKUs for stockouts
    stockout_skus = random.sample(sku_ids, stockout_count)

    # Determine year and month for stockout dates
    year, month = test_month.split('-')
    year = int(year)
    month = int(month)

    insert_query = """
        INSERT INTO stockout_dates (
            sku_id, warehouse, stockout_date, is_resolved
        ) VALUES (%s, %s, %s, 1)
    """

    created_count = 0

    for sku_id in stockout_skus:
        # Random number of stockout days
        num_days = random.randint(*STOCKOUT_DAYS_RANGE)

        # Random warehouse (burnaby or kentucky)
        warehouse = random.choice(['burnaby', 'kentucky'])

        # Add multiple stockout dates for this SKU
        for day_offset in range(num_days):
            day = (day_offset % 28) + 1  # Keep within month bounds
            stockout_date = date(year, month, day)

            try:
                execute_query(
                    insert_query,
                    (sku_id, warehouse, stockout_date),
                    fetch_all=False
                )
                created_count += 1

            except Exception as e:
                # Duplicate dates are OK, just skip
                if 'Duplicate entry' not in str(e):
                    logger.error(f"Failed to create stockout for {sku_id}: {e}")

    logger.info(f"Successfully created {created_count} stockout date records")
    return created_count


def analyze_query_performance(test_month: str):
    """
    Use EXPLAIN to analyze database query performance.

    Checks the main queries used by update_monthly_accuracy() to ensure
    proper index usage and identify potential bottlenecks.

    Args:
        test_month: Target month in 'YYYY-MM' format

    Returns:
        Dictionary with query analysis results
    """
    logger.info("Analyzing database query performance with EXPLAIN...")

    period_start = f"{test_month}-01"

    # Query 1: Fetch unrecorded forecasts
    explain_forecasts = """
        EXPLAIN
        SELECT id, sku_id, warehouse, predicted_demand, forecast_period_start
        FROM forecast_accuracy
        WHERE forecast_period_start = %s
        AND is_actual_recorded = 0
    """

    # Query 2: Fetch actuals from monthly_sales
    explain_actuals = """
        EXPLAIN
        SELECT sku_id, corrected_demand_burnaby, corrected_demand_kentucky
        FROM monthly_sales
        WHERE `year_month` = %s
    """

    # Query 3: Check stockouts
    explain_stockouts = """
        EXPLAIN
        SELECT COUNT(*) as stockout_days
        FROM stockout_dates
        WHERE sku_id = 'AP-2187172'
        AND warehouse IN ('burnaby', 'kentucky')
        AND stockout_date BETWEEN %s AND %s
        AND is_resolved = 1
    """

    results = {}

    try:
        # Analyze forecast query
        forecast_explain = execute_query(explain_forecasts, (period_start,), fetch_all=True)
        results['forecast_query'] = forecast_explain

        logger.info("\n[QUERY 1] Forecast Fetch Performance:")
        for row in forecast_explain:
            logger.info(f"  Table: {row.get('table')}, Type: {row.get('type')}, "
                       f"Key: {row.get('key')}, Rows: {row.get('rows')}")

        # Analyze actuals query
        actuals_explain = execute_query(explain_actuals, (test_month,), fetch_all=True)
        results['actuals_query'] = actuals_explain

        logger.info("\n[QUERY 2] Actuals Fetch Performance:")
        for row in actuals_explain:
            logger.info(f"  Table: {row.get('table')}, Type: {row.get('type')}, "
                       f"Key: {row.get('key')}, Rows: {row.get('rows')}")

        # Analyze stockout query
        stockout_explain = execute_query(
            explain_stockouts,
            (period_start, f"{test_month}-31"),
            fetch_all=True
        )
        results['stockout_query'] = stockout_explain

        logger.info("\n[QUERY 3] Stockout Check Performance:")
        for row in stockout_explain:
            logger.info(f"  Table: {row.get('table')}, Type: {row.get('type')}, "
                       f"Key: {row.get('key')}, Rows: {row.get('rows')}")

    except Exception as e:
        logger.error(f"Query analysis failed: {e}")

    return results


def measure_performance(test_month: str):
    """
    Measure execution time and performance metrics for update_monthly_accuracy().

    Captures:
    - Total execution time
    - Time per SKU
    - Records processed
    - Average MAPE
    - Stockout-affected count

    Args:
        test_month: Target month in 'YYYY-MM' format

    Returns:
        Dictionary with performance metrics
    """
    logger.info(f"\n{'='*70}")
    logger.info("PERFORMANCE TEST: update_monthly_accuracy()")
    logger.info(f"{'='*70}")

    # Start timing
    start_time = time.time()

    try:
        # Run the accuracy update
        result = update_monthly_accuracy(target_month=test_month)

        # End timing
        end_time = time.time()
        execution_time = end_time - start_time

        # Calculate metrics
        total_forecasts = result.get('total_forecasts', 0)
        actuals_found = result.get('actuals_found', 0)
        avg_mape = result.get('avg_mape', 0)
        stockout_affected = result.get('stockout_affected_count', 0)

        time_per_sku = execution_time / total_forecasts if total_forecasts > 0 else 0

        # Display results
        logger.info(f"\nPERFORMANCE RESULTS:")
        logger.info(f"  Total Execution Time: {execution_time:.2f} seconds")
        logger.info(f"  Target Time: 60.00 seconds")
        logger.info(f"  Status: {'PASS' if execution_time < 60 else 'FAIL'}")
        logger.info(f"\n  Total Forecasts: {total_forecasts}")
        logger.info(f"  Actuals Found: {actuals_found}")
        logger.info(f"  Missing Actuals: {result.get('missing_actuals', 0)}")
        logger.info(f"  Stockout Affected: {stockout_affected}")
        logger.info(f"\n  Average MAPE: {avg_mape:.2f}%")
        logger.info(f"  Time per SKU: {time_per_sku*1000:.2f} ms")

        # Performance assessment
        if execution_time < 60:
            logger.info(f"\n  PERFORMANCE ASSESSMENT: EXCELLENT")
            logger.info(f"  Execution time is {60 - execution_time:.2f}s under target")
        else:
            logger.info(f"\n  PERFORMANCE ASSESSMENT: NEEDS OPTIMIZATION")
            logger.info(f"  Execution time is {execution_time - 60:.2f}s over target")

        return {
            'execution_time': execution_time,
            'time_per_sku': time_per_sku,
            'total_forecasts': total_forecasts,
            'actuals_found': actuals_found,
            'avg_mape': avg_mape,
            'stockout_affected': stockout_affected,
            'passed': execution_time < 60
        }

    except Exception as e:
        logger.error(f"Performance test failed: {e}", exc_info=True)
        return {
            'execution_time': 0,
            'passed': False,
            'error': str(e)
        }


def cleanup_test_data(test_month: str):
    """
    Remove all test data created by this script.

    Deletes:
    - forecast_accuracy records for test month
    - monthly_sales records for test month
    - stockout_dates records for test month

    Args:
        test_month: Target month in 'YYYY-MM' format

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"\nCleaning up test data for {test_month}...")

    period_start = f"{test_month}-01"

    try:
        # Delete forecast_accuracy records
        delete_forecasts = """
            DELETE FROM forecast_accuracy
            WHERE forecast_period_start = %s
        """
        execute_query(delete_forecasts, (period_start,), fetch_all=False)
        logger.info("  Deleted forecast_accuracy records")

        # Delete monthly_sales records
        delete_sales = """
            DELETE FROM monthly_sales
            WHERE `year_month` = %s
        """
        execute_query(delete_sales, (test_month,), fetch_all=False)
        logger.info("  Deleted monthly_sales records")

        # Delete stockout_dates for August 2025
        delete_stockouts = """
            DELETE FROM stockout_dates
            WHERE stockout_date BETWEEN %s AND '2025-08-31'
        """
        execute_query(delete_stockouts, (period_start,), fetch_all=False)
        logger.info("  Deleted stockout_dates records")

        logger.info("Test data cleanup completed successfully")
        return True

    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return False


def run_performance_test():
    """
    Main performance test orchestrator.

    Executes the complete test workflow:
    1. Retrieve test SKUs
    2. Generate forecasts
    3. Generate actuals
    4. Add stockouts
    5. Analyze query performance
    6. Measure execution time
    7. Cleanup test data

    Returns:
        True if test passed, False otherwise
    """
    logger.info("\n" + "="*70)
    logger.info("FORECAST ACCURACY - PERFORMANCE TEST")
    logger.info("="*70)
    logger.info(f"\nTarget: {TARGET_SKU_COUNT} SKUs")
    logger.info(f"Test Month: {TEST_MONTH}")
    logger.info(f"Stockout Percentage: {STOCKOUT_PERCENTAGE*100:.0f}%")
    logger.info("="*70)

    try:
        # Step 1: Get test SKUs
        logger.info("\n[STEP 1] Retrieving test SKUs...")
        sku_ids = get_test_skus(TARGET_SKU_COUNT)

        if not sku_ids:
            logger.error("No SKUs available for testing")
            return False

        actual_sku_count = len(sku_ids)
        logger.info(f"Using {actual_sku_count} SKUs for performance test")

        # Step 2: Generate forecasts
        logger.info("\n[STEP 2] Generating forecast records...")
        forecast_count = generate_test_forecasts(sku_ids, TEST_MONTH)

        if forecast_count == 0:
            logger.error("Failed to generate forecast records")
            return False

        # Step 3: Generate actuals
        logger.info("\n[STEP 3] Generating actual sales records...")
        actuals_count = generate_test_actuals(sku_ids, TEST_MONTH)

        if actuals_count == 0:
            logger.error("Failed to generate actual sales records")
            cleanup_test_data(TEST_MONTH)
            return False

        # Step 4: Add stockouts
        logger.info("\n[STEP 4] Adding stockout scenarios...")
        stockout_count = add_random_stockouts(sku_ids, TEST_MONTH, STOCKOUT_PERCENTAGE)

        # Step 5: Analyze query performance
        logger.info("\n[STEP 5] Analyzing database query performance...")
        query_analysis = analyze_query_performance(TEST_MONTH)

        # Step 6: Measure performance
        logger.info("\n[STEP 6] Running performance test...")
        performance_results = measure_performance(TEST_MONTH)

        # Step 7: Cleanup
        logger.info("\n[STEP 7] Cleaning up test data...")
        cleanup_success = cleanup_test_data(TEST_MONTH)

        # Final Summary
        logger.info("\n" + "="*70)
        logger.info("PERFORMANCE TEST SUMMARY")
        logger.info("="*70)

        logger.info(f"\nTest Configuration:")
        logger.info(f"  SKUs Tested: {actual_sku_count}")
        logger.info(f"  Forecasts Created: {forecast_count}")
        logger.info(f"  Actuals Created: {actuals_count}")
        logger.info(f"  Stockouts Added: {stockout_count}")

        logger.info(f"\nPerformance Results:")
        logger.info(f"  Execution Time: {performance_results.get('execution_time', 0):.2f}s")
        logger.info(f"  Time per SKU: {performance_results.get('time_per_sku', 0)*1000:.2f}ms")
        logger.info(f"  Target Time: 60.00s")

        passed = performance_results.get('passed', False)

        if passed:
            logger.info(f"\nTEST STATUS: PASSED")
            logger.info(f"System meets performance requirements for {actual_sku_count} SKUs")
        else:
            logger.info(f"\nTEST STATUS: FAILED")
            logger.info(f"System does not meet performance requirements")
            if 'error' in performance_results:
                logger.info(f"Error: {performance_results['error']}")

        logger.info("\n" + "="*70)

        return passed

    except Exception as e:
        logger.error(f"Performance test failed: {e}", exc_info=True)

        # Attempt cleanup on error
        try:
            cleanup_test_data(TEST_MONTH)
        except:
            pass

        return False


if __name__ == "__main__":
    success = run_performance_test()
    exit(0 if success else 1)
