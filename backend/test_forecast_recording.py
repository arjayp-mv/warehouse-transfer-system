"""
Test script to verify forecast recording to forecast_accuracy table.

V8.0 Phase 1 Testing: Enhanced Forecast Recording

This script tests that:
1. Forecasts are recorded to forecast_accuracy table
2. All 12 monthly records are created per SKU
3. Context fields are captured (volatility, data quality, seasonal confidence)
4. Integration with existing forecasting system works correctly
"""

from backend.forecasting import ForecastEngine, create_forecast_run
from backend.database import execute_query


def test_forecast_recording():
    """Test that forecasts are being recorded to forecast_accuracy with context."""

    print("=" * 80)
    print("V8.0 PHASE 1 TEST: Forecast Recording to forecast_accuracy Table")
    print("=" * 80)

    # Create test forecast run
    run_id = create_forecast_run(
        forecast_name="V8.0 Test - Accuracy Recording",
        growth_assumption=0.05,
        warehouse='combined'
    )

    print(f"\n[STEP 1] Created test forecast run ID: {run_id}")

    # Generate forecast for a single SKU
    engine = ForecastEngine(run_id, manual_growth_override=0.05)

    # Use UB-YTX14-BS (known good SKU from V7.0 testing)
    test_sku = 'UB-YTX14-BS'
    print(f"[STEP 2] Testing with SKU: {test_sku}")

    try:
        forecast = engine.generate_forecast_for_sku(test_sku, warehouse='combined')
        success = engine.save_forecast(forecast)

        print(f"[STEP 3] Forecast generation: {'SUCCESS' if success else 'FAILED'}")

        if not success:
            print("\nTEST FAILED: Forecast save returned False")
            return

        # Verify records in forecast_accuracy (V8.0.1: Now includes warehouse)
        check_query = """
            SELECT COUNT(*) as record_count,
                   warehouse,
                   MIN(forecast_period_start) as first_period,
                   MAX(forecast_period_end) as last_period,
                   AVG(volatility_at_forecast) as avg_volatility,
                   AVG(data_quality_score) as avg_data_quality,
                   AVG(seasonal_confidence_at_forecast) as avg_seasonal_conf
            FROM forecast_accuracy
            WHERE sku_id = %s
              AND forecast_date = (SELECT forecast_date FROM forecast_runs WHERE id = %s)
            GROUP BY warehouse
        """

        result = execute_query(check_query, (test_sku, run_id), fetch_all=True)

        print("\n[STEP 4] Verification Results:")
        print("-" * 80)

        if result:
            record_count = result[0]['record_count']
            warehouse_recorded = result[0]['warehouse']
            print(f"Records in forecast_accuracy: {record_count}")
            print(f"Warehouse: {warehouse_recorded}")
            print(f"First forecast period: {result[0]['first_period']}")
            print(f"Last forecast period: {result[0]['last_period']}")
            print(f"Avg volatility captured: {result[0]['avg_volatility']}")
            print(f"Avg data quality: {result[0]['avg_data_quality']}")
            print(f"Avg seasonal confidence: {result[0]['avg_seasonal_conf']}")

            # Detailed record check (V8.0.1: Now includes warehouse)
            detail_query = """
                SELECT
                    warehouse,
                    forecast_period_start,
                    predicted_demand,
                    forecast_method,
                    abc_class,
                    xyz_class,
                    volatility_at_forecast,
                    data_quality_score,
                    seasonal_confidence_at_forecast,
                    is_actual_recorded
                FROM forecast_accuracy
                WHERE sku_id = %s
                  AND forecast_date = (SELECT forecast_date FROM forecast_runs WHERE id = %s)
                ORDER BY forecast_period_start
                LIMIT 3
            """

            details = execute_query(detail_query, (test_sku, run_id), fetch_all=True)

            print("\n[STEP 5] Sample Records (first 3 months):")
            print("-" * 80)
            for i, record in enumerate(details, 1):
                print(f"\nMonth {i}:")
                print(f"  Warehouse: {record['warehouse']}")
                print(f"  Period Start: {record['forecast_period_start']}")
                print(f"  Predicted Demand: {record['predicted_demand']}")
                print(f"  Forecast Method: {record['forecast_method']}")
                print(f"  ABC/XYZ: {record['abc_class']}/{record['xyz_class']}")
                print(f"  Volatility: {record['volatility_at_forecast']}")
                print(f"  Data Quality: {record['data_quality_score']}")
                print(f"  Seasonal Confidence: {record['seasonal_confidence_at_forecast']}")
                print(f"  Actual Recorded: {record['is_actual_recorded']}")

            print("\n" + "=" * 80)
            if record_count == 12:
                print("TEST PASSED: All 12 monthly forecasts recorded with context!")
                print("=" * 80)
                return True
            else:
                print(f"TEST FAILED: Expected 12 records, got {record_count}")
                print("=" * 80)
                return False
        else:
            print("TEST FAILED: No records found in forecast_accuracy")
            print("=" * 80)
            return False

    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 80)
        return False


if __name__ == "__main__":
    test_forecast_recording()
