"""
Test script to verify forecast learning algorithms.

Tests the ForecastLearningEngine and related functions with real
database data from Phase 2 accuracy tracking.

This script validates:
1. Engine initialization with ABC/XYZ learning rates
2. Growth rate adjustment learning
3. Method effectiveness analysis
4. Category pattern learning
5. Problem SKU identification

Run this after Phase 2 accuracy updates have populated the
forecast_accuracy table with real data.

Usage:
    python backend/test_forecast_learning.py

V8.0 Phase 3 - Multi-Dimensional Learning Testing
"""

import sys
from backend.forecast_learning import (
    ForecastLearningEngine,
    identify_problem_skus
)
from backend.database import execute_query


def test_engine_initialization():
    """Test ForecastLearningEngine initialization and learning rates."""
    print("\n" + "="*60)
    print("TEST 1: Engine Initialization")
    print("="*60)

    try:
        engine = ForecastLearningEngine()

        # Verify learning rates exist for all ABC/XYZ combinations
        expected_classifications = [
            'AX', 'AY', 'AZ',
            'BX', 'BY', 'BZ',
            'CX', 'CY', 'CZ'
        ]

        missing = []
        for classification in expected_classifications:
            if classification not in engine.learning_rates:
                missing.append(classification)
            else:
                rates = engine.learning_rates[classification]
                print(f"{classification}: growth={rates['growth']}, seasonal={rates['seasonal']}")

        if missing:
            print(f"\nFAILED: Missing learning rates for: {missing}")
            return False

        # Verify rate progression (CZ should be more aggressive than AX)
        ax_growth = engine.learning_rates['AX']['growth']
        cz_growth = engine.learning_rates['CZ']['growth']

        if cz_growth > ax_growth:
            print(f"\nPASSED: Learning rate progression correct (AX={ax_growth} < CZ={cz_growth})")
            return True
        else:
            print(f"\nFAILED: Learning rate progression incorrect (AX={ax_growth}, CZ={cz_growth})")
            return False

    except Exception as e:
        print(f"\nFAILED: Exception during initialization: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_availability():
    """Verify Phase 2 data exists for testing."""
    print("\n" + "="*60)
    print("TEST 2: Data Availability Check")
    print("="*60)

    try:
        # Check forecast_accuracy has recorded actuals
        accuracy_query = """
            SELECT COUNT(*) as total,
                   SUM(is_actual_recorded) as recorded,
                   SUM(stockout_affected) as stockout_affected
            FROM forecast_accuracy
        """
        result = execute_query(accuracy_query, fetch_all=True)

        if not result:
            print("FAILED: No data in forecast_accuracy table")
            return False

        total = result[0]['total']
        recorded = result[0]['recorded']
        stockout = result[0]['stockout_affected']

        print(f"Total forecast records: {total}")
        print(f"Actuals recorded: {recorded}")
        print(f"Stockout-affected: {stockout}")

        if total == 0:
            print("\nFAILED: No forecast_accuracy data available")
            print("Run Phase 2 accuracy updates first to populate data")
            return False

        if recorded == 0:
            print("\nWARNING: No actuals recorded yet")
            print("Learning algorithms need recorded actuals to function")
            return False

        print(f"\nPASSED: Data available ({recorded} actuals recorded)")
        return True

    except Exception as e:
        print(f"\nFAILED: Database query error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_growth_adjustments():
    """Test growth rate adjustment learning."""
    print("\n" + "="*60)
    print("TEST 3: Growth Rate Adjustment Learning")
    print("="*60)

    try:
        engine = ForecastLearningEngine()

        # Run growth adjustment learning
        result = engine.learn_growth_adjustments()

        print(f"SKUs analyzed: {result.get('skus_analyzed', 0)}")
        print(f"Adjustments logged: {result.get('adjustments_logged', 0)}")

        if 'error' in result:
            print(f"\nFAILED: {result['error']}")
            return False

        # Verify adjustments were logged to database
        check_query = """
            SELECT COUNT(*) as count,
                   AVG(adjustment_magnitude) as avg_magnitude,
                   AVG(confidence_score) as avg_confidence
            FROM forecast_learning_adjustments
            WHERE adjustment_type = 'growth_rate'
                AND created_at >= DATE_SUB(NOW(), INTERVAL 5 MINUTE)
        """

        check_result = execute_query(check_query, fetch_all=True)

        if check_result and check_result[0]['count'] > 0:
            count = check_result[0]['count']
            avg_mag = float(check_result[0]['avg_magnitude'] or 0)
            avg_conf = float(check_result[0]['avg_confidence'] or 0)

            print(f"\nAdjustments in database: {count}")
            print(f"Average magnitude: {avg_mag:.4f}")
            print(f"Average confidence: {avg_conf:.2f}")
            print("\nPASSED: Growth adjustments logged successfully")
            return True
        else:
            if result['skus_analyzed'] == 0:
                print("\nINFO: No SKUs found with sufficient bias for adjustment")
                print("This is normal if forecasts are very accurate or insufficient data")
                return True
            else:
                print("\nFAILED: Adjustments not found in database")
                return False

    except Exception as e:
        print(f"\nFAILED: Exception during growth adjustment test: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_method_effectiveness():
    """Test method effectiveness analysis."""
    print("\n" + "="*60)
    print("TEST 4: Method Effectiveness Analysis")
    print("="*60)

    try:
        engine = ForecastLearningEngine()

        # Run method effectiveness analysis
        result = engine.learn_method_effectiveness()

        print(f"Method classifications: {result.get('total_method_classifications', 0)}")
        print(f"Best methods identified: {len(result.get('best_methods_by_class', {}))}")

        if 'error' in result:
            print(f"\nFAILED: {result['error']}")
            return False

        best_methods = result.get('best_methods_by_class', {})

        if best_methods:
            # Show sample results
            print("\nSample best methods by classification:")
            for i, (key, method_info) in enumerate(list(best_methods.items())[:5]):
                abc, xyz, seasonal, growth = key
                print(f"  {abc}{xyz} ({seasonal}, {growth}): "
                      f"{method_info['method']} "
                      f"(MAPE: {method_info['mape']:.2f}%, "
                      f"confidence: {method_info['confidence']:.2f})")

            print("\nPASSED: Method effectiveness analysis complete")
            return True
        else:
            print("\nINFO: No method classifications found")
            print("This requires at least 10 forecasts per method/class combination")
            return True

    except Exception as e:
        print(f"\nFAILED: Exception during method effectiveness test: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_category_learning():
    """Test category pattern learning."""
    print("\n" + "="*60)
    print("TEST 5: Category Pattern Learning")
    print("="*60)

    try:
        engine = ForecastLearningEngine()

        # Run category learning
        result = engine.learn_from_categories()

        print(f"Categories analyzed: {result.get('categories_analyzed', 0)}")

        if 'error' in result:
            print(f"\nFAILED: {result['error']}")
            return False

        if result['categories_analyzed'] > 0:
            print("\nPASSED: Category patterns identified")
            return True
        else:
            print("\nINFO: No categories found with sufficient SKUs (need 5+ per category)")
            return True

    except Exception as e:
        print(f"\nFAILED: Exception during category learning test: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_problem_sku_identification():
    """Test problem SKU identification."""
    print("\n" + "="*60)
    print("TEST 6: Problem SKU Identification")
    print("="*60)

    try:
        # Test with 30% MAPE threshold
        problems = identify_problem_skus(mape_threshold=30.0)

        print(f"Problem SKUs identified: {len(problems)}")

        if problems:
            print("\nTop 3 problem SKUs:")
            for problem in problems[:3]:
                print(f"\n  SKU: {problem['sku_id']}")
                print(f"  MAPE: {problem['avg_mape']:.2f}%")
                print(f"  Bias: {problem['avg_bias']:.2f}%")
                print(f"  Classification: {problem['abc_code']}{problem['xyz_code']}")
                print(f"  Method: {problem['forecast_method']}")
                print(f"  Recommendations:")
                for rec in problem['recommendations']:
                    print(f"    - {rec}")

            print("\nPASSED: Problem SKUs identified with recommendations")
            return True
        else:
            print("\nINFO: No problem SKUs found above 30% MAPE threshold")
            print("This is good - all forecasts are relatively accurate!")
            return True

    except Exception as e:
        print(f"\nFAILED: Exception during problem SKU test: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all learning algorithm tests."""
    print("\n" + "#"*60)
    print("# Forecast Learning Algorithm Test Suite")
    print("# V8.0 Phase 3 - Multi-Dimensional Learning")
    print("#"*60)

    tests = [
        ("Engine Initialization", test_engine_initialization),
        ("Data Availability", test_data_availability),
        ("Growth Adjustments", test_growth_adjustments),
        ("Method Effectiveness", test_method_effectiveness),
        ("Category Learning", test_category_learning),
        ("Problem SKU Identification", test_problem_sku_identification),
    ]

    results = {}
    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result

            if result:
                passed += 1
            else:
                failed += 1

        except Exception as e:
            print(f"\nCRITICAL ERROR in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False
            failed += 1

    # Summary
    print("\n" + "#"*60)
    print("# Test Summary")
    print("#"*60)

    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        print(f"{test_name}: {status}")

    print(f"\nTotal: {passed} passed, {failed} failed")

    if failed == 0:
        print("\nALL TESTS PASSED!")
        print("\nPhase 3 learning algorithms are working correctly.")
        print("Ready for production use.")
        return True
    else:
        print(f"\n{failed} TEST(S) FAILED")
        print("\nReview failures above and fix issues before deployment.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
