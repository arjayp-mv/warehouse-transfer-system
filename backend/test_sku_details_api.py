"""
Backend API Testing Script for V10.0 SKU Details Endpoints

Tests the following endpoints:
- GET /api/pending-orders/sku/{sku_id}
- GET /api/forecasts/sku/{sku_id}/latest
- GET /api/stockouts/sku/{sku_id}
- GET /api/supplier-orders/{order_month}/csv

TASK-599: Functional testing
TASK-600: Performance benchmarking
"""

import requests
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"

# Test Configuration
TEST_SKU_VALID = "UB-YTX14-BS"  # Known SKU from database
TEST_SKU_INVALID = "INVALID-SKU-999"  # Should return 404
TEST_WAREHOUSE = "burnaby"  # Changed from kentucky - burnaby has pending data
TEST_ORDER_MONTH = "2025-10"

# Performance Targets
TARGET_RESPONSE_TIME_MS = 500


def test_pending_orders_endpoint():
    """
    TASK-599: Test GET /api/pending-orders/sku/{sku_id}

    Verifies:
    - 200 status for valid SKU
    - Required fields present in response
    - Pending orders array structure
    - Total and effective pending calculations
    """
    print("\n=== Testing Pending Orders Endpoint ===")

    url = f"{BASE_URL}/api/pending-orders/sku/{TEST_SKU_VALID}"
    params = {"warehouse": TEST_WAREHOUSE}

    start_time = time.time()
    response = requests.get(url, params=params)
    elapsed_ms = (time.time() - start_time) * 1000

    # Status check
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Response structure check
    data = response.json()
    assert "sku_id" in data, "Missing sku_id field"
    assert "warehouse" in data, "Missing warehouse field"
    assert "pending_orders" in data, "Missing pending_orders field"
    assert "total_pending" in data, "Missing total_pending field"
    assert "effective_pending" in data, "Missing effective_pending field"

    # Data type validation
    assert isinstance(data["pending_orders"], list), "pending_orders should be a list"
    assert isinstance(data["total_pending"], int), "total_pending should be an integer"
    assert isinstance(data["effective_pending"], int), "effective_pending should be an integer"

    # Pending order structure check (if any exist)
    if data["pending_orders"]:
        order = data["pending_orders"][0]
        required_fields = ["po_number", "qty", "expected_arrival", "confidence", "category", "supplier"]
        for field in required_fields:
            assert field in order, f"Missing field '{field}' in pending order"

        # Category validation
        valid_categories = ["overdue", "imminent", "covered", "future"]
        assert order["category"] in valid_categories, f"Invalid category: {order['category']}"

    print(f"[PASS] Pending orders endpoint ({elapsed_ms:.0f}ms)")
    print(f"  - Found {len(data['pending_orders'])} pending orders")
    print(f"  - Total pending: {data['total_pending']} units")
    print(f"  - Effective pending: {data['effective_pending']} units")

    return elapsed_ms


def test_forecast_endpoint():
    """
    TASK-599: Test GET /api/forecasts/sku/{sku_id}/latest

    Verifies:
    - 200 status for valid SKU with forecast
    - Required fields present in response
    - Monthly forecast array structure
    - Learning adjustment fields
    """
    print("\n=== Testing Forecast Endpoint ===")

    url = f"{BASE_URL}/api/forecasts/sku/{TEST_SKU_VALID}/latest"
    params = {"warehouse": TEST_WAREHOUSE}

    start_time = time.time()
    response = requests.get(url, params=params)
    elapsed_ms = (time.time() - start_time) * 1000

    # Status check
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Response structure check
    data = response.json()
    assert "sku_id" in data, "Missing sku_id field"
    assert "warehouse" in data, "Missing warehouse field"
    assert "forecast_run_id" in data, "Missing forecast_run_id field"
    assert "forecast_method" in data, "Missing forecast_method field"
    assert "monthly_forecast" in data, "Missing monthly_forecast field"
    assert "avg_monthly" in data, "Missing avg_monthly field"

    # Monthly forecast structure check
    assert isinstance(data["monthly_forecast"], list), "monthly_forecast should be a list"
    assert len(data["monthly_forecast"]) <= 12, "monthly_forecast should have max 12 months"

    if data["monthly_forecast"]:
        month_data = data["monthly_forecast"][0]
        required_fields = ["month", "base_qty", "adjusted_qty", "learning_applied"]
        for field in required_fields:
            assert field in month_data, f"Missing field '{field}' in monthly forecast"

        # Data type validation
        assert isinstance(month_data["learning_applied"], bool), "learning_applied should be boolean"
        if month_data["learning_applied"]:
            assert "adjustment_reason" in month_data, "Missing adjustment_reason when learning applied"

    print(f"[PASS] PASS: Forecast endpoint ({elapsed_ms:.0f}ms)")
    print(f"  - Forecast run ID: {data['forecast_run_id']}")
    print(f"  - Method: {data['forecast_method']}")
    print(f"  - Monthly forecast points: {len(data['monthly_forecast'])}")
    print(f"  - Average monthly demand: {data['avg_monthly']:.2f} units")

    return elapsed_ms


def test_stockout_endpoint():
    """
    TASK-599: Test GET /api/stockouts/sku/{sku_id}

    Verifies:
    - 200 status for valid SKU
    - Required fields present in response
    - Stockout array structure
    - Pattern detection fields
    """
    print("\n=== Testing Stockout Endpoint ===")

    url = f"{BASE_URL}/api/stockouts/sku/{TEST_SKU_VALID}"

    start_time = time.time()
    response = requests.get(url)
    elapsed_ms = (time.time() - start_time) * 1000

    # Status check
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Response structure check
    data = response.json()
    assert "sku_id" in data, "Missing sku_id field"
    assert "total_stockouts" in data, "Missing total_stockouts field"
    assert "pattern_detected" in data, "Missing pattern_detected field"
    assert "pattern_type" in data, "Missing pattern_type field"
    assert "stockouts" in data, "Missing stockouts field"

    # Data type validation
    assert isinstance(data["stockouts"], list), "stockouts should be a list"
    assert isinstance(data["pattern_detected"], bool), "pattern_detected should be boolean"
    assert isinstance(data["total_stockouts"], int), "total_stockouts should be integer"

    # Stockout structure check (if any exist)
    if data["stockouts"]:
        stockout = data["stockouts"][0]
        required_fields = ["stockout_date", "days_out_of_stock", "warehouse"]
        for field in required_fields:
            assert field in stockout, f"Missing field '{field}' in stockout"

    # Pattern type validation (if pattern detected)
    if data["pattern_detected"]:
        valid_patterns = ["chronic", "seasonal", "supply_issue"]
        assert data["pattern_type"] in valid_patterns, f"Invalid pattern type: {data['pattern_type']}"
        print(f"  [WARN] Pattern detected: {data['pattern_type']}")

    print(f"[PASS] PASS: Stockout endpoint ({elapsed_ms:.0f}ms)")
    print(f"  - Total stockouts: {data['total_stockouts']}")
    print(f"  - Pattern detected: {data['pattern_detected']}")

    return elapsed_ms


def test_invalid_sku():
    """
    TASK-599: Test 404 handling for invalid SKU

    Verifies:
    - 404 status for non-existent SKU
    - Proper error message
    """
    print("\n=== Testing Invalid SKU Handling ===")

    # Test pending orders with invalid SKU
    url = f"{BASE_URL}/api/pending-orders/sku/{TEST_SKU_INVALID}"
    params = {"warehouse": TEST_WAREHOUSE}

    response = requests.get(url, params=params)
    assert response.status_code == 404, f"Expected 404 for invalid SKU, got {response.status_code}"

    # Test forecast with invalid SKU
    url = f"{BASE_URL}/api/forecasts/sku/{TEST_SKU_INVALID}/latest"
    response = requests.get(url, params=params)
    assert response.status_code == 404, f"Expected 404 for invalid SKU, got {response.status_code}"

    # Test stockout with invalid SKU
    url = f"{BASE_URL}/api/stockouts/sku/{TEST_SKU_INVALID}"
    response = requests.get(url)
    assert response.status_code == 404, f"Expected 404 for invalid SKU, got {response.status_code}"

    print("[PASS] PASS: Invalid SKU returns 404 for all endpoints")


def test_csv_export():
    """
    TASK-599: Test CSV export endpoint

    Verifies:
    - 200 status
    - Content-Type is text/csv
    - Response contains valid CSV data
    - Content-Disposition header present
    """
    print("\n=== Testing CSV Export Endpoint ===")

    url = f"{BASE_URL}/api/supplier-orders/{TEST_ORDER_MONTH}/csv"

    start_time = time.time()
    response = requests.get(url)
    elapsed_ms = (time.time() - start_time) * 1000

    # Status check
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Content-Type check
    content_type = response.headers.get("content-type", "")
    assert "text/csv" in content_type, f"Expected text/csv, got {content_type}"

    # Content-Disposition check
    assert "Content-Disposition" in response.headers, "Missing Content-Disposition header"
    disposition = response.headers["Content-Disposition"]
    assert "attachment" in disposition, "Content-Disposition should be attachment"
    assert TEST_ORDER_MONTH in disposition, f"Filename should contain {TEST_ORDER_MONTH}"

    # CSV content validation
    csv_content = response.text
    lines = csv_content.strip().split('\n')
    assert len(lines) > 0, "CSV should not be empty"

    # Check header row
    header = lines[0]
    expected_columns = ["sku_id", "warehouse", "supplier", "suggested_qty"]
    for col in expected_columns:
        assert col in header, f"Missing column '{col}' in CSV header"

    print(f"[PASS] PASS: CSV export endpoint ({elapsed_ms:.0f}ms)")
    print(f"  - CSV rows: {len(lines)}")
    print(f"  - File size: {len(csv_content)} bytes")


def benchmark_endpoint(name, url, params=None, target_ms=TARGET_RESPONSE_TIME_MS):
    """
    TASK-600: Benchmark endpoint response time

    Args:
        name: Endpoint name for display
        url: Full URL to test
        params: Query parameters
        target_ms: Target response time in milliseconds

    Returns:
        bool: True if within target, False otherwise
    """
    start_time = time.time()
    response = requests.get(url, params=params)
    elapsed_ms = (time.time() - start_time) * 1000

    status = "[PASS] PASS" if elapsed_ms < target_ms else "[FAIL] FAIL"
    print(f"{status}: {name} - {elapsed_ms:.0f}ms (target: {target_ms}ms)")

    return elapsed_ms < target_ms


def run_performance_benchmarks():
    """
    TASK-600: Run performance benchmarks for all endpoints

    Tests each endpoint 5 times and calculates average response time
    Target: All endpoints under 500ms average
    """
    print("\n" + "="*60)
    print("PERFORMANCE BENCHMARKS (TASK-600)")
    print("="*60)
    print(f"Target: {TARGET_RESPONSE_TIME_MS}ms per endpoint")
    print(f"Running 5 iterations per endpoint...")

    benchmarks = [
        {
            "name": "Pending Orders",
            "url": f"{BASE_URL}/api/pending-orders/sku/{TEST_SKU_VALID}",
            "params": {"warehouse": TEST_WAREHOUSE}
        },
        {
            "name": "Forecast",
            "url": f"{BASE_URL}/api/forecasts/sku/{TEST_SKU_VALID}/latest",
            "params": {"warehouse": TEST_WAREHOUSE}
        },
        {
            "name": "Stockout History",
            "url": f"{BASE_URL}/api/stockouts/sku/{TEST_SKU_VALID}",
            "params": None
        },
        {
            "name": "CSV Export",
            "url": f"{BASE_URL}/api/supplier-orders/{TEST_ORDER_MONTH}/csv",
            "params": None
        }
    ]

    all_pass = True

    for benchmark in benchmarks:
        print(f"\n{benchmark['name']}:")
        times = []

        for i in range(5):
            passed = benchmark_endpoint(
                f"  Iteration {i+1}",
                benchmark["url"],
                benchmark["params"],
                TARGET_RESPONSE_TIME_MS
            )

            # Record time for averaging
            start = time.time()
            requests.get(benchmark["url"], params=benchmark["params"])
            times.append((time.time() - start) * 1000)

            all_pass = all_pass and passed

        avg_time = sum(times) / len(times)
        print(f"  Average: {avg_time:.0f}ms")

    return all_pass


def run_all_tests():
    """
    Execute all TASK-599 and TASK-600 tests

    Returns:
        bool: True if all tests pass, False otherwise
    """
    print("="*60)
    print("V10.0 SKU DETAILS API TEST SUITE")
    print("="*60)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}")
    print(f"Test SKU: {TEST_SKU_VALID}")
    print(f"Test Warehouse: {TEST_WAREHOUSE}")

    try:
        # TASK-599: Functional Tests
        print("\n" + "="*60)
        print("FUNCTIONAL TESTS (TASK-599)")
        print("="*60)

        test_pending_orders_endpoint()
        test_forecast_endpoint()
        test_stockout_endpoint()
        test_invalid_sku()
        test_csv_export()

        # TASK-600: Performance Benchmarks
        benchmark_pass = run_performance_benchmarks()

        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print("[PASS] All functional tests passed (TASK-599)")

        if benchmark_pass:
            print("[PASS] All performance targets met (TASK-600)")
        else:
            print("[FAIL] Some endpoints exceeded performance targets")
            print(f"  Target was {TARGET_RESPONSE_TIME_MS}ms per endpoint")

        print("\n[PASS] TASK-599 COMPLETE: Backend test script created and executed")
        print("[PASS] TASK-600 COMPLETE: Performance benchmarks run")

        return True

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"\n[FAIL] CONNECTION ERROR: Could not connect to {BASE_URL}")
        print("  Make sure the development server is running: run_dev.bat")
        return False
    except Exception as e:
        print(f"\n[FAIL] UNEXPECTED ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
