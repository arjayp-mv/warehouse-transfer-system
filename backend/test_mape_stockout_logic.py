"""
Test script to verify MAPE calculations with stockout filtering logic.

This script validates the three critical test cases for stockout-aware MAPE:

Test Case 1: SKU with no stockouts
- Should calculate normal MAPE and include in avg_mape calculation
- stockout_affected = FALSE

Test Case 2: SKU with stockout, actual < predicted
- Should mark stockout_affected = TRUE
- Should exclude from avg_mape calculation (forecast was correct, supply failed)
- Logic: Forecast predicted higher demand, but stockout prevented sales

Test Case 3: SKU with stockout, actual > predicted
- Should mark stockout_affected = TRUE (stockout occurred)
- Should calculate normal MAPE and include in avg_mape (forecast was wrong)
- Logic: Even with stockout, actual sales exceeded prediction = bad forecast

Business Rationale:
- Case 2 is NOT a forecast error - supply chain failed, not the forecast
- Case 3 IS a forecast error - we under-predicted demand despite knowing about stockout
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import execute_query
from backend.forecast_accuracy import update_monthly_accuracy
from datetime import datetime, date
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Use existing SKUs from database to avoid foreign key constraints
TEST_SKU_1 = 'AP-2187172'  # Test Case 1: No stockout
TEST_SKU_2 = 'AP-240338001'  # Test Case 2: Stockout + undersales
TEST_SKU_3 = 'AP-279838'  # Test Case 3: Stockout + oversales
TEST_MONTH = '2025-08'  # Using August 2025 since we have actual sales data


def create_test_forecasts():
    """
    Create test forecast records for validation.

    This sets up three test SKUs with forecasts for a past month where
    we can insert corresponding actual sales data to test the logic.

    Using existing SKUs to avoid foreign key constraint issues.
    """

    test_month = TEST_MONTH
    period_start = f'{test_month}-01'
    period_end = f'{test_month}-31'
    forecast_date = '2025-07-15'  # Forecast created mid-July

    print("\n" + "="*70)
    print("CREATING TEST FORECAST DATA")
    print("="*70)

    # Clean up any existing test data first
    cleanup_query = """
        DELETE FROM forecast_accuracy
        WHERE sku_id IN (%s, %s, %s)
          AND forecast_period_start = %s
    """

    try:
        execute_query(cleanup_query, (TEST_SKU_1, TEST_SKU_2, TEST_SKU_3, period_start), fetch_all=False)
        print("Cleaned up existing test data")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

    # Test Case 1: No stockout, normal forecast
    test_case_1 = """
        INSERT INTO forecast_accuracy (
            sku_id, warehouse, forecast_date,
            forecast_period_start, forecast_period_end,
            predicted_demand, forecast_method,
            abc_class, xyz_class, is_actual_recorded
        ) VALUES (
            %s, 'combined', %s,
            %s, %s,
            100.0, 'min-max',
            'A', 'X', 0
        )
    """

    # Test Case 2: Stockout occurred, actual < predicted (should exclude from MAPE)
    test_case_2 = """
        INSERT INTO forecast_accuracy (
            sku_id, warehouse, forecast_date,
            forecast_period_start, forecast_period_end,
            predicted_demand, forecast_method,
            abc_class, xyz_class, is_actual_recorded
        ) VALUES (
            %s, 'combined', %s,
            %s, %s,
            100.0, 'min-max',
            'A', 'X', 0
        )
    """

    # Test Case 3: Stockout occurred, actual > predicted (should include in MAPE)
    test_case_3 = """
        INSERT INTO forecast_accuracy (
            sku_id, warehouse, forecast_date,
            forecast_period_start, forecast_period_end,
            predicted_demand, forecast_method,
            abc_class, xyz_class, is_actual_recorded
        ) VALUES (
            %s, 'combined', %s,
            %s, %s,
            100.0, 'min-max',
            'A', 'X', 0
        )
    """

    try:
        execute_query(test_case_1, (TEST_SKU_1, forecast_date, period_start, period_end), fetch_all=False)
        execute_query(test_case_2, (TEST_SKU_2, forecast_date, period_start, period_end), fetch_all=False)
        execute_query(test_case_3, (TEST_SKU_3, forecast_date, period_start, period_end), fetch_all=False)

        print("\nCreated 3 test forecast records for 2025-08:")
        print(f"  {TEST_SKU_1}: No stockout (predicted=100)")
        print(f"  {TEST_SKU_2}: Stockout + undersales (predicted=100)")
        print(f"  {TEST_SKU_3}: Stockout + oversales (predicted=100)")

        return True

    except Exception as e:
        logger.error(f"Failed to create test forecasts: {e}", exc_info=True)
        return False


def create_test_actuals():
    """
    Create test actual sales records in monthly_sales table.

    Test Case 1: No stockout, actual = 90 (MAPE = 10%)
    Test Case 2: 5 stockout days, actual = 60 (MAPE = 40%, but excluded)
    Test Case 3: 5 stockout days, actual = 120 (MAPE = 20%, included)
    """

    test_month = TEST_MONTH

    print("\n" + "="*70)
    print("CREATING TEST ACTUAL SALES DATA")
    print("="*70)

    # Clean up existing test actuals
    cleanup_query = """
        DELETE FROM monthly_sales
        WHERE sku_id IN (%s, %s, %s)
          AND `year_month` = %s
    """

    try:
        execute_query(cleanup_query, (TEST_SKU_1, TEST_SKU_2, TEST_SKU_3, test_month), fetch_all=False)
        print("Cleaned up existing test actuals")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

    # Test Case 1: No stockout, actual = 90
    # MAPE = |90-100|/90 * 100 = 11.11%
    test_actual_1 = """
        INSERT INTO monthly_sales (
            sku_id, `year_month`,
            burnaby_sales, kentucky_sales,
            corrected_demand_burnaby, corrected_demand_kentucky,
            burnaby_stockout_days, kentucky_stockout_days
        ) VALUES (
            %s, %s,
            45, 45,
            45.0, 45.0,
            0, 0
        )
    """

    # Test Case 2: Stockout, actual = 60 (< predicted 100)
    # MAPE = |60-100|/60 * 100 = 66.67% BUT excluded from avg_mape
    # Corrected demand already accounts for stockout
    test_actual_2 = """
        INSERT INTO monthly_sales (
            sku_id, `year_month`,
            burnaby_sales, kentucky_sales,
            corrected_demand_burnaby, corrected_demand_kentucky,
            burnaby_stockout_days, kentucky_stockout_days
        ) VALUES (
            %s, %s,
            30, 30,
            30.0, 30.0,
            3, 2
        )
    """

    # Test Case 3: Stockout, actual = 120 (> predicted 100)
    # MAPE = |120-100|/120 * 100 = 16.67% AND included in avg_mape
    test_actual_3 = """
        INSERT INTO monthly_sales (
            sku_id, `year_month`,
            burnaby_sales, kentucky_sales,
            corrected_demand_burnaby, corrected_demand_kentucky,
            burnaby_stockout_days, kentucky_stockout_days
        ) VALUES (
            %s, %s,
            60, 60,
            60.0, 60.0,
            3, 2
        )
    """

    try:
        execute_query(test_actual_1, (TEST_SKU_1, test_month), fetch_all=False)
        execute_query(test_actual_2, (TEST_SKU_2, test_month), fetch_all=False)
        execute_query(test_actual_3, (TEST_SKU_3, test_month), fetch_all=False)

        print(f"\nCreated 3 test actual sales records for {test_month}:")
        print(f"  {TEST_SKU_1}: actual=90 (no stockout)")
        print(f"  {TEST_SKU_2}: actual=60 (5 stockout days)")
        print(f"  {TEST_SKU_3}: actual=120 (5 stockout days)")

        return True

    except Exception as e:
        logger.error(f"Failed to create test actuals: {e}", exc_info=True)
        return False


def create_test_stockout_dates():
    """
    Create stockout_dates entries for Test Cases 2 and 3.

    Each needs 5 stockout days to trigger the stockout_affected flag.
    """

    print("\n" + "="*70)
    print("CREATING TEST STOCKOUT DATE RECORDS")
    print("="*70)

    # Clean up existing test stockout dates
    cleanup_query = """
        DELETE FROM stockout_dates
        WHERE sku_id IN (%s, %s)
    """

    try:
        execute_query(cleanup_query, (TEST_SKU_2, TEST_SKU_3), fetch_all=False)
        print("Cleaned up existing test stockout dates")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

    # Create 5 stockout days for TEST_SKU_2 and TEST_SKU_3
    stockout_insert = """
        INSERT INTO stockout_dates (sku_id, stockout_date, warehouse, is_resolved)
        VALUES (%s, %s, %s, 0)
    """

    try:
        for day in range(10, 15):  # Aug 10-14 (5 days)
            # TEST_SKU_2
            execute_query(
                stockout_insert,
                (TEST_SKU_2, f'{TEST_MONTH}-{day}', 'burnaby'),
                fetch_all=False
            )
            # TEST_SKU_3
            execute_query(
                stockout_insert,
                (TEST_SKU_3, f'{TEST_MONTH}-{day}', 'kentucky'),
                fetch_all=False
            )

        print("\nCreated 5 stockout dates each for:")
        print(f"  {TEST_SKU_2} (Burnaby warehouse)")
        print(f"  {TEST_SKU_3} (Kentucky warehouse)")

        return True

    except Exception as e:
        logger.error(f"Failed to create stockout dates: {e}", exc_info=True)
        return False


def verify_mape_calculations():
    """
    Run the update_monthly_accuracy() function and verify results.

    Expected Results:
    - TEST_SKU_1: stockout_affected=FALSE, included in MAPE
    - TEST_SKU_2: stockout_affected=TRUE, excluded from MAPE
    - TEST_SKU_3: stockout_affected=TRUE, included in MAPE
    - avg_mape should be: (11.11 + 16.67) / 2 = 13.89%
    """

    print("\n" + "="*70)
    print(f"RUNNING update_monthly_accuracy() FOR {TEST_MONTH}")
    print("="*70)

    try:
        result = update_monthly_accuracy(target_month=TEST_MONTH)

        print("\nUpdate Results:")
        print(f"  Month: {result['month_updated']}")
        print(f"  Total Forecasts: {result['total_forecasts']}")
        print(f"  Actuals Found: {result['actuals_found']}")
        print(f"  Average MAPE: {result['avg_mape']}%")
        print(f"  Stockout-Affected Count: {result['stockout_affected_count']}")

    except Exception as e:
        logger.error(f"Update failed: {e}", exc_info=True)
        return False

    # Now query the updated records to verify logic
    print("\n" + "="*70)
    print("VERIFYING STOCKOUT-AWARE MAPE LOGIC")
    print("="*70)

    verify_query = """
        SELECT
            sku_id,
            warehouse,
            predicted_demand,
            actual_demand,
            absolute_percentage_error,
            stockout_affected,
            is_actual_recorded
        FROM forecast_accuracy
        WHERE sku_id IN (%s, %s, %s)
          AND forecast_period_start = %s
        ORDER BY sku_id
    """

    try:
        results = execute_query(
            verify_query,
            (TEST_SKU_1, TEST_SKU_2, TEST_SKU_3, f'{TEST_MONTH}-01'),
            fetch_all=True
        )

        if not results:
            print("ERROR: No results found for test cases!")
            return False

        print("\nDetailed Results:")
        print("-" * 70)

        test_case_1 = None
        test_case_2 = None
        test_case_3 = None

        for row in results:
            sku = row['sku_id']
            predicted = float(row['predicted_demand'])
            actual = float(row['actual_demand']) if row['actual_demand'] else 0
            mape = float(row['absolute_percentage_error']) if row['absolute_percentage_error'] else 0
            stockout_affected = bool(row['stockout_affected'])
            recorded = bool(row['is_actual_recorded'])

            print(f"\n{sku}:")
            print(f"  Predicted: {predicted:.2f}")
            print(f"  Actual: {actual:.2f}")
            print(f"  MAPE: {mape:.2f}%")
            print(f"  Stockout Affected: {stockout_affected}")
            print(f"  Recorded: {recorded}")

            if sku == TEST_SKU_1:
                test_case_1 = row
            elif sku == TEST_SKU_2:
                test_case_2 = row
            elif sku == TEST_SKU_3:
                test_case_3 = row

        # Validation
        print("\n" + "="*70)
        print("VALIDATION RESULTS")
        print("="*70)

        all_passed = True

        # Test Case 1: No stockout
        print("\n[TEST CASE 1] No stockout scenario:")
        if test_case_1:
            if not test_case_1['stockout_affected']:
                print("  PASS: stockout_affected = FALSE")
            else:
                print("  FAIL: stockout_affected should be FALSE")
                all_passed = False

            expected_mape = abs(90 - 100) / 90 * 100
            actual_mape = float(test_case_1['absolute_percentage_error'] or 0)
            if abs(actual_mape - expected_mape) < 0.1:
                print(f"  PASS: MAPE = {actual_mape:.2f}% (expected ~{expected_mape:.2f}%)")
            else:
                print(f"  FAIL: MAPE = {actual_mape:.2f}%, expected ~{expected_mape:.2f}%")
                all_passed = False
        else:
            print("  FAIL: Test case 1 not found")
            all_passed = False

        # Test Case 2: Stockout + actual < predicted (should exclude from MAPE)
        print("\n[TEST CASE 2] Stockout + undersales (excluded from MAPE):")
        if test_case_2:
            if test_case_2['stockout_affected']:
                print("  PASS: stockout_affected = TRUE")
            else:
                print("  FAIL: stockout_affected should be TRUE")
                all_passed = False

            # Note: This case is excluded from avg_mape calculation
            print("  NOTE: This MAPE value exists but is excluded from avg_mape")
            actual_mape = float(test_case_2['absolute_percentage_error'] or 0)
            print(f"  MAPE recorded: {actual_mape:.2f}% (not counted in average)")
        else:
            print("  FAIL: Test case 2 not found")
            all_passed = False

        # Test Case 3: Stockout + actual > predicted (should include in MAPE)
        print("\n[TEST CASE 3] Stockout + oversales (included in MAPE):")
        if test_case_3:
            if test_case_3['stockout_affected']:
                print("  PASS: stockout_affected = TRUE")
            else:
                print("  FAIL: stockout_affected should be TRUE")
                all_passed = False

            expected_mape = abs(120 - 100) / 120 * 100
            actual_mape = float(test_case_3['absolute_percentage_error'] or 0)
            if abs(actual_mape - expected_mape) < 0.1:
                print(f"  PASS: MAPE = {actual_mape:.2f}% (expected ~{expected_mape:.2f}%)")
            else:
                print(f"  FAIL: MAPE = {actual_mape:.2f}%, expected ~{expected_mape:.2f}%")
                all_passed = False
        else:
            print("  FAIL: Test case 3 not found")
            all_passed = False

        # Verify avg_mape calculation
        print("\n[AVG_MAPE CALCULATION]:")
        expected_avg = (11.11 + 16.67) / 2  # Only cases 1 and 3
        actual_avg = result['avg_mape']
        if abs(actual_avg - expected_avg) < 1.0:
            print(f"  PASS: avg_mape = {actual_avg:.2f}% (expected ~{expected_avg:.2f}%)")
            print("  Correctly excluded stockout-affected undersales (Case 2)")
        else:
            print(f"  FAIL: avg_mape = {actual_avg:.2f}%, expected ~{expected_avg:.2f}%")
            all_passed = False

        print("\n" + "="*70)
        if all_passed:
            print("ALL TESTS PASSED - STOCKOUT-AWARE MAPE LOGIC VERIFIED")
        else:
            print("SOME TESTS FAILED - REVIEW LOGIC ABOVE")
        print("="*70)

        return all_passed

    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        return False


def cleanup_test_data():
    """
    Remove all test data created by this script.
    """

    print("\n" + "="*70)
    print("CLEANING UP TEST DATA")
    print("="*70)

    try:
        # Delete from forecast_accuracy
        execute_query(
            "DELETE FROM forecast_accuracy WHERE sku_id IN (%s, %s, %s) AND forecast_period_start = %s",
            (TEST_SKU_1, TEST_SKU_2, TEST_SKU_3, f'{TEST_MONTH}-01'),
            fetch_all=False
        )

        # Delete from monthly_sales
        execute_query(
            "DELETE FROM monthly_sales WHERE sku_id IN (%s, %s, %s) AND `year_month` = %s",
            (TEST_SKU_1, TEST_SKU_2, TEST_SKU_3, TEST_MONTH),
            fetch_all=False
        )

        # Delete from stockout_dates
        execute_query(
            "DELETE FROM stockout_dates WHERE sku_id IN (%s, %s) AND stockout_date BETWEEN %s AND %s",
            (TEST_SKU_2, TEST_SKU_3, f'{TEST_MONTH}-01', f'{TEST_MONTH}-31'),
            fetch_all=False
        )

        print("Test data cleaned up successfully")
        return True

    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("MAPE STOCKOUT-AWARE LOGIC VERIFICATION TEST")
    print("="*70)
    print("\nThis test validates three critical scenarios:")
    print("1. No stockout: Normal MAPE calculation, included in average")
    print("2. Stockout + undersales: MAPE excluded (supply failed, not forecast)")
    print("3. Stockout + oversales: MAPE included (forecast wrong despite stockout)")

    try:
        # Step 1: Create test data
        if not create_test_forecasts():
            print("\nERROR: Failed to create test forecasts")
            exit(1)

        if not create_test_actuals():
            print("\nERROR: Failed to create test actuals")
            cleanup_test_data()
            exit(1)

        if not create_test_stockout_dates():
            print("\nERROR: Failed to create test stockout dates")
            cleanup_test_data()
            exit(1)

        # Step 2: Run verification
        success = verify_mape_calculations()

        # Step 3: Cleanup
        print("\n")
        user_input = input("Do you want to keep the test data for inspection? (y/n): ")
        if user_input.lower() != 'y':
            cleanup_test_data()
        else:
            print("\nTest data retained for inspection:")
            print(f"  SKUs: {TEST_SKU_1}, {TEST_SKU_2}, {TEST_SKU_3}")
            print(f"  Month: {TEST_MONTH}")

        exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Test script failed: {e}", exc_info=True)
        cleanup_test_data()
        exit(1)
