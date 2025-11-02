# V10.0 Supplier Ordering Intelligence Layer - Detailed Task Specifications

**Version**: V10.0
**Task Range**: TASK-593 to TASK-619
**Status**: IN PROGRESS
**Date**: 2025-10-24

This document contains detailed implementation specifications for all V10.0 tasks. For high-level summary, see TASKS.md.

---

## Phase 1: Critical Fixes and API Endpoints

### TASK-593: Create backend/supplier_ordering_sku_details.py module

**Purpose**: Separate module for SKU detail endpoints (file size management)

**File Size Target**: 250-300 lines max

**Functions to Create**:

```python
from backend.database import execute_query
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

def get_pending_orders_for_sku(sku_id: str, warehouse: str) -> Dict:
    """
    Retrieve time-phased pending orders for SKU

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name (burnaby/kentucky)

    Returns:
        dict: {
            "sku_id": str,
            "warehouse": str,
            "pending_orders": List[dict],
            "total_pending": int,
            "effective_pending": int
        }

    Logic:
        - Query pending_inventory WHERE order_type='supplier'
        - LEFT JOIN supplier_lead_times for reliability_score
        - Calculate confidence = reliability_score or 0.75 default
        - Categorize by expected_arrival:
          - overdue: < today
          - imminent: <= today + 7 days
          - covered: <= today + 30 days
          - future: > today + 30 days
    """
    pass

def get_forecast_data_for_sku(sku_id: str, warehouse: str) -> Dict:
    """
    Retrieve 12-month forecast with learning adjustments

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name

    Returns:
        dict: {
            "sku_id": str,
            "warehouse": str,
            "forecast_run_id": int,
            "forecast_method": str,
            "monthly_forecast": List[dict],
            "avg_monthly": float
        }

    Logic:
        - Query forecast_details for latest forecast_run_id
        - LEFT JOIN forecast_learning_adjustments WHERE applied=TRUE
        - Return 12 monthly data points
        - For each month: base_qty, adjusted_qty, learning_applied
    """
    pass

def get_stockout_history_for_sku(sku_id: str) -> Dict:
    """
    Retrieve stockout history with pattern detection

    Args:
        sku_id: SKU identifier

    Returns:
        dict: {
            "sku_id": str,
            "total_stockouts": int,
            "pattern_detected": bool,
            "pattern_type": str or None,
            "stockouts": List[dict]
        }

    Logic:
        - Query stockout_dates table
        - LEFT JOIN stockout_patterns for pattern detection
        - Return chronological stockout list
        - Include estimated_lost_sales if available
    """
    pass
```

**Implementation Notes**:
- Use execute_query pattern (not SQLAlchemy)
- Return None defaults for missing data
- Include comprehensive logging
- Follow project documentation standards

**Files**: backend/supplier_ordering_sku_details.py

---

### TASK-594: Implement GET /api/pending-orders/sku/{sku_id} endpoint

**FastAPI Route**:

```python
from fastapi import APIRouter, HTTPException, Query
from backend.supplier_ordering_sku_details import get_pending_orders_for_sku

router = APIRouter(prefix="/api/pending-orders", tags=["Supplier Ordering SKU Details"])

@router.get("/sku/{sku_id}")
def get_pending_orders(
    sku_id: str,
    warehouse: str = Query(..., description="Warehouse name (burnaby/kentucky)")
):
    """
    Get time-phased pending orders for SKU

    Returns pending supplier orders categorized by urgency:
    - overdue: past expected arrival
    - imminent: within 7 days
    - covered: within 30 days
    - future: beyond 30 days
    """
    try:
        result = get_pending_orders_for_sku(sku_id, warehouse)

        if not result:
            raise HTTPException(status_code=404, detail=f"No pending orders found for SKU {sku_id}")

        return result
    except Exception as e:
        logger.error(f"Error fetching pending orders for {sku_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Response Format**:
```json
{
  "sku_id": "UB-YTX14-BS",
  "warehouse": "kentucky",
  "pending_orders": [
    {
      "po_number": "PO-2025-001",
      "qty": 500,
      "expected_arrival": "2025-11-15",
      "confidence": 0.85,
      "category": "covered",
      "supplier": "Yuasa Battery"
    }
  ],
  "total_pending": 1200,
  "effective_pending": 1020
}
```

**Database Query**:
```sql
SELECT
    pi.po_number,
    pi.quantity as qty,
    pi.expected_arrival,
    COALESCE(slt.reliability_score, 0.75) as confidence,
    pi.supplier,
    CASE
        WHEN pi.expected_arrival < CURDATE() THEN 'overdue'
        WHEN pi.expected_arrival <= DATE_ADD(CURDATE(), INTERVAL 7 DAY) THEN 'imminent'
        WHEN pi.expected_arrival <= DATE_ADD(CURDATE(), INTERVAL 30 DAY) THEN 'covered'
        ELSE 'future'
    END as category
FROM pending_inventory pi
LEFT JOIN supplier_lead_times slt
    ON pi.supplier = slt.supplier
    AND pi.destination = slt.destination
WHERE pi.sku_id = %s
    AND pi.destination = %s
    AND pi.order_type = 'supplier'
ORDER BY pi.expected_arrival ASC
LIMIT 50
```

**Files**: backend/supplier_ordering_sku_details.py

---

### TASK-595: Implement GET /api/forecasts/sku/{sku_id}/latest endpoint

**FastAPI Route**:

```python
@router.get("/sku/{sku_id}/latest")
def get_forecast_latest(
    sku_id: str,
    warehouse: str = Query(..., description="Warehouse name (burnaby/kentucky)")
):
    """
    Get latest 12-month forecast with learning adjustments

    Returns forecast data including:
    - Base monthly projections
    - Learning-adjusted values (if applied)
    - Forecast method used
    - Average monthly demand
    """
    try:
        result = get_forecast_data_for_sku(sku_id, warehouse)

        if not result:
            raise HTTPException(status_code=404, detail=f"No forecast found for SKU {sku_id}")

        return result
    except Exception as e:
        logger.error(f"Error fetching forecast for {sku_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Response Format**:
```json
{
  "sku_id": "UB-YTX14-BS",
  "warehouse": "kentucky",
  "forecast_run_id": 35,
  "forecast_method": "exponential_smoothing",
  "monthly_forecast": [
    {
      "month": "2025-11",
      "base_qty": 250,
      "adjusted_qty": 275,
      "learning_applied": true,
      "adjustment_reason": "Consistent under-forecasting corrected"
    }
  ],
  "avg_monthly": 268
}
```

**Database Query**:
```sql
SELECT
    fd.sku_id,
    fd.warehouse,
    fd.forecast_run_id,
    fr.method as forecast_method,
    fd.year_month as month,
    fd.avg_monthly_qty as base_qty,
    COALESCE(fla.adjusted_value, fd.avg_monthly_qty) as adjusted_qty,
    CASE WHEN fla.applied = TRUE THEN TRUE ELSE FALSE END as learning_applied,
    fla.adjustment_reason
FROM forecast_details fd
JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
LEFT JOIN forecast_learning_adjustments fla
    ON fd.sku_id = fla.sku_id
    AND fd.warehouse = fla.warehouse
    AND fla.applied = TRUE
WHERE fd.sku_id = %s
    AND fd.warehouse = %s
    AND fd.forecast_run_id = (
        SELECT MAX(id) FROM forecast_runs WHERE status = 'completed'
    )
ORDER BY fd.month_number ASC
LIMIT 12
```

**Files**: backend/supplier_ordering_sku_details.py

---

### TASK-596: Implement GET /api/stockouts/sku/{sku_id} endpoint

**FastAPI Route**:

```python
@router.get("/sku/{sku_id}")
def get_stockout_history(sku_id: str):
    """
    Get stockout history with pattern detection

    Returns:
    - Historical stockout dates
    - Days out of stock
    - Pattern detection (chronic, seasonal, supply_issue)
    - Estimated lost sales
    """
    try:
        result = get_stockout_history_for_sku(sku_id)

        if not result:
            # No stockouts is OK, return empty result
            return {
                "sku_id": sku_id,
                "total_stockouts": 0,
                "pattern_detected": False,
                "pattern_type": None,
                "stockouts": []
            }

        return result
    except Exception as e:
        logger.error(f"Error fetching stockouts for {sku_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
```

**Response Format**:
```json
{
  "sku_id": "UB-YTX14-BS",
  "total_stockouts": 3,
  "pattern_detected": true,
  "pattern_type": "chronic",
  "stockouts": [
    {
      "stockout_date": "2025-09-15",
      "days_out_of_stock": 5,
      "estimated_lost_sales": 25,
      "warehouse": "kentucky"
    }
  ]
}
```

**Database Query**:
```sql
SELECT
    sd.sku_id,
    sd.stockout_date,
    sd.days_out_of_stock,
    sd.estimated_lost_sales,
    sd.warehouse,
    sp.stockout_pattern_detected as pattern_detected,
    sp.pattern_type
FROM stockout_dates sd
LEFT JOIN stockout_patterns sp
    ON sd.sku_id = sp.sku_id
    AND sd.warehouse = sp.warehouse
WHERE sd.sku_id = %s
ORDER BY sd.stockout_date DESC
LIMIT 50
```

**Files**: backend/supplier_ordering_sku_details.py

---

### TASK-597: Add GET /api/supplier-orders/export/csv endpoint

**Implementation**:

```python
from fastapi.responses import StreamingResponse
import csv
import io

@router.get("/{order_month}/export/csv")
def export_orders_csv(
    order_month: str,
    warehouse: str = Query(None),
    supplier: str = Query(None),
    urgency: str = Query(None)
):
    """
    Export supplier orders as CSV file

    Same data as Excel export, different format
    Applies same filters as current view
    """
    # Fetch data using existing query
    filters = {
        "warehouse": warehouse,
        "supplier": supplier,
        "urgency": urgency
    }

    orders = get_supplier_orders_for_export(order_month, filters)

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'sku_id', 'description', 'warehouse', 'supplier',
        'current_inventory', 'pending_orders_effective',
        'suggested_qty', 'confirmed_qty', 'lead_time_days',
        'expected_arrival', 'coverage_months', 'urgency_level',
        'abc_code', 'xyz_code', 'cost_per_unit',
        'suggested_value', 'confirmed_value'
    ])

    writer.writeheader()
    writer.writerows(orders)

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=supplier_orders_{order_month}.csv"
        }
    )
```

**Files**: backend/supplier_ordering_api.py (add near Excel export)

---

### TASK-598: Backend error handling and validation

**Error Handling Pattern**:

```python
def safe_api_call(func):
    """Decorator for consistent error handling"""
    def wrapper(*args, **kwargs):
        try:
            # Validate SKU exists if sku_id in kwargs
            if 'sku_id' in kwargs:
                sku_id = kwargs['sku_id']
                if not sku_exists(sku_id):
                    raise HTTPException(
                        status_code=404,
                        detail=f"SKU {sku_id} not found"
                    )

            # Call function
            result = func(*args, **kwargs)

            # Log success
            logger.info(f"{func.__name__} completed successfully")

            return result

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Log and return 500 for unexpected errors
            logger.error(f"{func.__name__} failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Internal server error"
            )
    return wrapper

def sku_exists(sku_id: str) -> bool:
    """Check if SKU exists in database"""
    query = "SELECT COUNT(*) as count FROM skus WHERE sku_id = %s"
    result = execute_query(query, (sku_id,), fetch_one=True)
    return result and result.get('count', 0) > 0
```

**Apply to all endpoints**:
```python
@router.get("/sku/{sku_id}")
@safe_api_call
def get_pending_orders(sku_id: str, warehouse: str):
    # Implementation
    pass
```

**Files**: backend/supplier_ordering_sku_details.py

---

## Testing Tasks

### TASK-599: Create backend/test_sku_details_api.py test script

**Test Coverage**:

```python
import requests

BASE_URL = "http://localhost:8000"

def test_pending_orders_endpoint():
    """Test GET /api/pending-orders/sku/{sku_id}"""
    response = requests.get(
        f"{BASE_URL}/api/pending-orders/sku/UB-YTX14-BS",
        params={"warehouse": "kentucky"}
    )

    assert response.status_code == 200
    data = response.json()

    assert "sku_id" in data
    assert "pending_orders" in data
    assert "total_pending" in data

    print("PASS: Pending orders endpoint")

def test_forecast_endpoint():
    """Test GET /api/forecasts/sku/{sku_id}/latest"""
    response = requests.get(
        f"{BASE_URL}/api/forecasts/sku/UB-YTX14-BS/latest",
        params={"warehouse": "kentucky"}
    )

    assert response.status_code == 200
    data = response.json()

    assert "forecast_run_id" in data
    assert "monthly_forecast" in data
    assert len(data["monthly_forecast"]) <= 12

    print("PASS: Forecast endpoint")

def test_stockout_endpoint():
    """Test GET /api/stockouts/sku/{sku_id}"""
    response = requests.get(
        f"{BASE_URL}/api/stockouts/sku/UB-YTX14-BS"
    )

    assert response.status_code == 200
    data = response.json()

    assert "sku_id" in data
    assert "stockouts" in data

    print("PASS: Stockout endpoint")

def test_invalid_sku():
    """Test 404 handling for invalid SKU"""
    response = requests.get(
        f"{BASE_URL}/api/pending-orders/sku/INVALID-SKU",
        params={"warehouse": "kentucky"}
    )

    assert response.status_code == 404

    print("PASS: Invalid SKU returns 404")

def test_csv_export():
    """Test CSV export endpoint"""
    response = requests.get(
        f"{BASE_URL}/api/supplier-orders/2025-10/export/csv"
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]

    print("PASS: CSV export")

if __name__ == "__main__":
    test_pending_orders_endpoint()
    test_forecast_endpoint()
    test_stockout_endpoint()
    test_invalid_sku()
    test_csv_export()
    print("\\nAll tests passed!")
```

**Files**: backend/test_sku_details_api.py

---

### TASK-600: Performance testing for new endpoints

**Performance Benchmarks**:

```python
import time
import requests

def benchmark_endpoint(url, params=None, target_ms=500):
    """Benchmark endpoint response time"""
    start = time.time()
    response = requests.get(url, params=params)
    elapsed_ms = (time.time() - start) * 1000

    status = "PASS" if elapsed_ms < target_ms else "FAIL"
    print(f"{status}: {url} - {elapsed_ms:.0f}ms (target: {target_ms}ms)")

    return elapsed_ms < target_ms

# Run benchmarks
all_pass = True

all_pass &= benchmark_endpoint(
    "http://localhost:8000/api/pending-orders/sku/UB-YTX14-BS",
    params={"warehouse": "kentucky"}
)

all_pass &= benchmark_endpoint(
    "http://localhost:8000/api/forecasts/sku/UB-YTX14-BS/latest",
    params={"warehouse": "kentucky"}
)

all_pass &= benchmark_endpoint(
    "http://localhost:8000/api/stockouts/sku/UB-YTX14-BS"
)

if all_pass:
    print("\\nAll performance targets met!")
else:
    print("\\nSome endpoints exceeded performance targets")
```

**Files**: backend/test_sku_details_api.py

---

## Frontend Tasks

### TASK-601: Update frontend/supplier-ordering.js modal tab functions

**Fix loadPendingTab() (line 601)**:

```javascript
async function loadPendingTab(skuId, warehouse) {
    const container = document.getElementById('pending-content');

    try {
        showLoading(container, 'Loading pending orders...');

        const response = await fetch(
            `/api/pending-orders/sku/${skuId}?warehouse=${warehouse}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Render timeline
        let html = '<div class="timeline">';

        if (data.pending_orders.length === 0) {
            html += '<p class="text-muted">No pending supplier orders</p>';
        } else {
            data.pending_orders.forEach(order => {
                const categoryClass = `category-${order.category}`;
                const confidencePct = Math.round(order.confidence * 100);

                html += `
                    <div class="timeline-item ${categoryClass}">
                        <div class="timeline-date">${order.expected_arrival}</div>
                        <div class="timeline-content">
                            <strong>${order.supplier}</strong><br>
                            PO: ${order.po_number}<br>
                            Qty: ${order.qty} units<br>
                            Confidence: ${confidencePct}%<br>
                            <span class="badge bg-${getCategoryBadge(order.category)}">
                                ${order.category.toUpperCase()}
                            </span>
                        </div>
                    </div>
                `;
            });
        }

        html += '</div>';
        html += `
            <div class="mt-3">
                <strong>Total Pending:</strong> ${data.total_pending} units<br>
                <strong>Effective (with confidence):</strong> ${data.effective_pending} units
            </div>
        `;

        container.innerHTML = html;

    } catch (error) {
        console.error('Error loading pending orders:', error);
        container.innerHTML = `
            <div class="alert alert-danger">
                Error loading pending orders. Please try again.
            </div>
        `;
    }
}

function getCategoryBadge(category) {
    const badges = {
        'overdue': 'danger',
        'imminent': 'warning',
        'covered': 'success',
        'future': 'info'
    };
    return badges[category] || 'secondary';
}
```

**Fix loadForecastTab() (line 659)**:

```javascript
async function loadForecastTab(skuId, warehouse) {
    const container = document.getElementById('forecast-content');

    try {
        showLoading(container, 'Loading forecast data...');

        const response = await fetch(
            `/api/forecasts/sku/${skuId}/latest?warehouse=${warehouse}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        // Prepare data for Chart.js (TASK-602)
        renderForecastChart(data);

    } catch (error) {
        console.error('Error loading forecast:', error);
        container.innerHTML = `
            <div class="alert alert-danger">
                Error loading forecast data. Please try again.
            </div>
        `;
    }
}
```

**Fix loadStockoutTab() (line 732)**:

```javascript
async function loadStockoutTab(skuId) {
    const container = document.getElementById('stockout-content');

    try {
        showLoading(container, 'Loading stockout history...');

        const response = await fetch(`/api/stockouts/sku/${skuId}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        let html = '';

        // Pattern detection badge
        if (data.pattern_detected) {
            html += `
                <div class="alert alert-warning mb-3">
                    <i class="fas fa-exclamation-triangle"></i>
                    <strong>Pattern Detected:</strong> ${data.pattern_type}
                </div>
            `;
        }

        // Stockout table
        if (data.stockouts.length === 0) {
            html += '<p class="text-success">No stockouts recorded</p>';
        } else {
            html += `
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Days Out</th>
                            <th>Est. Lost Sales</th>
                            <th>Warehouse</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            data.stockouts.forEach(so => {
                html += `
                    <tr>
                        <td>${so.stockout_date}</td>
                        <td>${so.days_out_of_stock}</td>
                        <td>${so.estimated_lost_sales || 'N/A'}</td>
                        <td>${so.warehouse}</td>
                    </tr>
                `;
            });

            html += `
                    </tbody>
                </table>
            `;
        }

        html += `<p class="text-muted mt-2">Total stockouts: ${data.total_stockouts}</p>`;

        container.innerHTML = html;

    } catch (error) {
        console.error('Error loading stockouts:', error);
        container.innerHTML = `
            <div class="alert alert-danger">
                Error loading stockout history. Please try again.
            </div>
        `;
    }
}
```

**Helper function**:

```javascript
function showLoading(container, message) {
    container.innerHTML = `
        <div class="text-center p-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <p class="mt-2">${message}</p>
        </div>
    `;
}
```

**Files**: frontend/supplier-ordering.js

---

### TASK-602: Implement Chart.js visualization for forecast tab

**Chart Implementation**:

```javascript
let forecastChart = null;

function renderForecastChart(data) {
    const ctx = document.getElementById('forecast-chart');

    // Destroy existing chart if any
    if (forecastChart) {
        forecastChart.destroy();
    }

    // Prepare data
    const labels = data.monthly_forecast.map(m => m.month);
    const baseData = data.monthly_forecast.map(m => m.base_qty);
    const adjustedData = data.monthly_forecast.map(m => m.adjusted_qty);

    // Create chart
    forecastChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Base Forecast',
                    data: baseData,
                    borderColor: 'rgb(54, 162, 235)',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    borderWidth: 2,
                    tension: 0.1
                },
                {
                    label: 'Learning Adjusted',
                    data: adjustedData,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: `12-Month Forecast (Method: ${data.forecast_method})`
                },
                tooltip: {
                    callbacks: {
                        afterLabel: function(context) {
                            const index = context.dataIndex;
                            const month = data.monthly_forecast[index];
                            if (month.learning_applied) {
                                return `Learning: ${month.adjustment_reason}`;
                            }
                            return '';
                        }
                    }
                },
                legend: {
                    display: true,
                    position: 'bottom'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Quantity'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Month'
                    }
                }
            }
        }
    });
}
```

**Files**: frontend/supplier-ordering.js

---

### TASK-603: Add CSV export button to frontend

**HTML Button** (in supplier-ordering.html line 220):

```html
<!-- Export Button -->
<button class="btn btn-success btn-sm me-2" onclick="exportToExcel()">
    <i class="fas fa-file-excel me-1"></i>Export to Excel
</button>
<button class="btn btn-outline-success btn-sm me-2" onclick="exportToCSV()">
    <i class="fas fa-file-csv me-1"></i>Export to CSV
</button>
```

**JavaScript Function** (in supplier-ordering.js):

```javascript
async function exportToCSV() {
    try {
        showLoading(document.getElementById('loading-overlay'), 'Generating CSV export...');

        // Get current filters
        const orderMonth = document.getElementById('order-month-select').value;
        const warehouse = document.getElementById('warehouse-filter').value;
        const supplier = document.getElementById('supplier-filter').value;
        const urgency = document.getElementById('urgency-filter').value;

        // Build query params
        const params = new URLSearchParams();
        if (warehouse) params.append('warehouse', warehouse);
        if (supplier) params.append('supplier', supplier);
        if (urgency) params.append('urgency', urgency);

        // Fetch CSV
        const response = await fetch(
            `/api/supplier-orders/${orderMonth}/export/csv?${params.toString()}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // Download file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `supplier_orders_${orderMonth}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showSuccess('CSV export downloaded successfully');

    } catch (error) {
        console.error('CSV export failed:', error);
        showError('Failed to export CSV. Please try again.');
    } finally {
        hideLoading();
    }
}
```

**Files**: frontend/supplier-ordering.html, frontend/supplier-ordering.js

---

## Phase 2 and Phase 3 Details

Due to file length, detailed specifications for Phase 2 (Intelligence Layer) and Phase 3 (Visualization) are available upon request. They follow the same documentation pattern:

- Function signatures with docstrings
- SQL query examples
- Error handling patterns
- Response format specifications
- Testing procedures

---

## Documentation Standards Reference

All code must follow CLAUDE.md documentation standards:

**Python Functions**:
```python
def function_name(param1: str, param2: int = 0) -> dict:
    """
    Brief description of what function does

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 0)

    Returns:
        dict: Description of return structure

    Raises:
        ValueError: When validation fails
        DatabaseError: When query fails
    """
```

**JavaScript Functions**:
```javascript
/**
 * Function description
 * @param {string} param1 - Description
 * @param {number} param2 - Description
 * @returns {Promise<Object>} Description
 */
async function functionName(param1, param2) {
    // Implementation
}
```

---

## File Size Monitoring

Current status:
- backend/supplier_ordering_api.py: 560 lines (OVER LIMIT)
- backend/supplier_ordering_calculations.py: 566 lines (OVER LIMIT)
- frontend/supplier-ordering.js: 819 lines (WAY OVER LIMIT)

**Action Required**:
- TASK-593 creates separate module (prevents api.py growth)
- Monitor file sizes after each task
- If any file exceeds 600 lines during implementation, split immediately

---

## Phase 4: Data Quality Enhancements (Optional)

**Status**: FUTURE ENHANCEMENT - Not required for V10.0 completion

**Objective**: Apply supplier mapping intelligence to pending inventory imports

This phase applies the proven supplier name matching system from V5.0 Supplier Shipments (backend/supplier_import.py, backend/supplier_matcher.py, frontend/data-management.html) to the pending inventory import workflow. Currently, pending inventory imports lose supplier data quality by storing raw CSV names without validation or normalization.

---

### TASK-620: Add pending inventory supplier mapping preview endpoint

**Purpose**: Analyze pending inventory CSV and provide supplier name mapping suggestions

**Endpoint**: POST /api/pending-orders/import-csv/preview

**Implementation**:

```python
@app.post("/api/pending-orders/import-csv/preview")
async def preview_pending_inventory_import(file: UploadFile = File(...)):
    """
    Analyze CSV file and provide supplier name mapping suggestions

    Extracts unique supplier names from "order_type" column (CSV naming confusion),
    finds potential matches using fuzzy matching, and returns mapping suggestions
    for user confirmation before import.

    Args:
        file: CSV file containing pending inventory data

    Returns:
        Dict containing:
            - unique_suppliers: List of unique supplier names found
            - mapping_suggestions: Suggested matches for each supplier
            - total_suppliers: Count of unique suppliers
            - estimated_new_suppliers: Count needing manual mapping

    Example Response:
        {
            "unique_suppliers": ["Bolin", "Yuasa"],
            "mapping_suggestions": {
                "Bolin": [
                    {
                        "supplier_id": 5,
                        "display_name": "Bolin Battery",
                        "confidence": 95.5,
                        "match_type": "fuzzy"
                    }
                ]
            },
            "total_suppliers": 2,
            "estimated_new_suppliers": 0
        }
    """
    try:
        # Read CSV content
        content = await file.read()
        csv_content = content.decode('utf-8')

        # Extract unique supplier names from "order_type" column
        import io, csv
        csv_file = io.StringIO(csv_content)
        csv_reader = csv.DictReader(csv_file)

        # Find order_type column (contains supplier names)
        supplier_column = None
        for fieldname in csv_reader.fieldnames or []:
            if fieldname.lower().strip() == 'order_type':
                supplier_column = fieldname
                break

        if not supplier_column:
            raise HTTPException(
                status_code=400,
                detail="CSV must contain 'order_type' column with supplier names"
            )

        # Extract unique supplier names
        unique_suppliers = set()
        for row in csv_reader:
            supplier_name = row.get(supplier_column, '').strip()
            if supplier_name and supplier_name.lower() not in ['n/a', 'na', 'none', 'null', '']:
                unique_suppliers.add(supplier_name)

        # Get mapping suggestions using existing matcher
        matcher = supplier_matcher.get_supplier_matcher()

        mapping_suggestions = {}
        estimated_new_suppliers = 0

        for supplier_name in unique_suppliers:
            matches = matcher.find_matches(supplier_name, limit=3)
            mapping_suggestions[supplier_name] = matches

            # Count as new if no high-confidence matches
            high_confidence_matches = [m for m in matches if m['confidence'] >= 90]
            if not high_confidence_matches:
                estimated_new_suppliers += 1

        return {
            "unique_suppliers": sorted(list(unique_suppliers)),
            "mapping_suggestions": mapping_suggestions,
            "total_suppliers": len(unique_suppliers),
            "estimated_new_suppliers": estimated_new_suppliers,
            "csv_column_used": supplier_column
        }

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid CSV encoding. Use UTF-8.")
    except Exception as e:
        logger.error(f"Error previewing pending inventory import: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")
```

**Testing**:
```python
def test_pending_inventory_preview():
    """Test supplier mapping preview for pending inventory"""
    with open('test_pending_orders.csv', 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/api/pending-orders/import-csv/preview",
            files={'file': f}
        )

    assert response.status_code == 200
    data = response.json()
    assert 'unique_suppliers' in data
    assert 'mapping_suggestions' in data
    assert data['total_suppliers'] > 0
```

**Files**: backend/main.py

---

### TASK-621: Modify pending inventory import to accept supplier mappings

**Purpose**: Update import logic to create suppliers and link to master table

**Implementation Changes**:

```python
@app.post("/api/pending-orders/import-csv")
async def import_pending_orders_csv(
    file: UploadFile = File(...),
    replace_existing: bool = Form(True),
    supplier_mappings: Optional[str] = Form(None)  # NEW: JSON string of mappings
):
    """
    Import pending orders CSV with supplier mapping support

    Args:
        file: CSV file
        replace_existing: Whether to replace existing data
        supplier_mappings: JSON string containing supplier mapping decisions
            Format: {
                "CSV_Supplier_Name": {
                    "action": "map" | "create",
                    "supplier_id": int (if map),
                    "display_name": str (if map)
                }
            }
    """
    try:
        # Parse supplier mappings if provided
        mappings = {}
        if supplier_mappings:
            import json
            mappings = json.loads(supplier_mappings)

        # ... existing CSV parsing code ...

        # Process each row
        for row in csv_reader:
            # Get supplier name from "order_type" column
            csv_supplier = row.get('order_type', '').strip()

            # Apply mapping if available
            if csv_supplier in mappings:
                mapping = mappings[csv_supplier]

                if mapping['action'] == 'create':
                    # Create new supplier in master table
                    supplier_id = create_new_supplier(
                        display_name=csv_supplier,
                        created_by='import_user'
                    )

                    # Save as alias for future imports
                    save_supplier_alias(
                        supplier_id=supplier_id,
                        alias_name=csv_supplier
                    )

                elif mapping['action'] == 'map':
                    # Use mapped supplier_id
                    supplier_id = mapping['supplier_id']

                    # Save as alias if not already existing
                    save_supplier_alias(
                        supplier_id=supplier_id,
                        alias_name=csv_supplier
                    )
            else:
                # No mapping provided, create supplier on-the-fly (fallback)
                supplier_id = get_or_create_supplier(csv_supplier)

            # Store pending order with supplier_id reference
            order_data = {
                "sku_id": sku_id,
                "quantity": quantity,
                "destination": destination,
                "order_date": order_date.isoformat(),
                "expected_arrival": expected_arrival_iso,
                "is_estimated": is_estimated,
                "order_type": "supplier",
                "supplier": csv_supplier,  # Keep raw name for backward compat
                "supplier_id": supplier_id,  # NEW: Link to master table
                "status": status,
                "notes": notes
            }

            # ... rest of import logic ...
```

**Helper Functions**:

```python
def create_new_supplier(display_name: str, created_by: str) -> int:
    """Create new supplier in master table"""
    normalized_name = display_name.strip().upper()

    cursor.execute("""
        INSERT INTO suppliers (
            display_name, normalized_name, created_by, is_active
        ) VALUES (%s, %s, %s, TRUE)
    """, (display_name, normalized_name, created_by))

    return cursor.lastrowid

def save_supplier_alias(supplier_id: int, alias_name: str):
    """Save supplier name alias for future matching"""
    normalized_alias = alias_name.strip().upper()

    # Check if alias already exists
    cursor.execute("""
        SELECT id FROM supplier_aliases
        WHERE supplier_id = %s AND normalized_alias = %s
    """, (supplier_id, normalized_alias))

    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO supplier_aliases (
                supplier_id, alias_name, normalized_alias,
                usage_count, created_by
            ) VALUES (%s, %s, %s, 1, 'import')
        """, (supplier_id, alias_name, normalized_alias))
    else:
        # Increment usage count
        cursor.execute("""
            UPDATE supplier_aliases
            SET usage_count = usage_count + 1
            WHERE supplier_id = %s AND normalized_alias = %s
        """, (supplier_id, normalized_alias))
```

**Files**: backend/main.py (lines 1511-1665)

---

### TASK-622: Add supplier mapping modal UI for pending orders

**Purpose**: Add mapping workflow to pending orders import interface

**Implementation** (frontend/data-management.html):

```javascript
// Modify existing handlePendingOrdersFile function
async function handlePendingOrdersFile(file) {
    try {
        // Show progress
        showUploadProgress(true);
        updateProgress(10, 'Analyzing supplier names...');

        // Get mapping suggestions
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/api/pending-orders/import-csv/preview', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to analyze suppliers');
        }

        const previewData = await response.json();

        updateProgress(50, `Found ${previewData.total_suppliers} unique suppliers`);

        // Hide progress and show mapping modal
        showUploadProgress(false);

        // Reuse existing supplier mapping modal
        createSupplierMappingModal(previewData, file, 'admin', 'pending_orders');

    } catch (error) {
        console.error('Supplier mapping preview error:', error);
        showUploadProgress(false);
        alert('Failed to analyze supplier names: ' + error.message);
    }
}

// Modify proceedWithMapping to support pending orders
async function proceedWithMapping(importType = 'supplier_shipments') {
    try {
        const mappingData = window.currentMappingData;

        if (importType === 'pending_orders') {
            // Use pending orders import endpoint
            const formData = new FormData();
            formData.append('file', mappingData.file);
            formData.append('replace_existing', 'true');
            formData.append('supplier_mappings', JSON.stringify(mappingData.mappings));

            const response = await fetch('/api/pending-orders/import-csv', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Import failed');
            }

            const result = await response.json();
            alert(`Successfully imported ${result.imported_count} pending orders`);

        } else {
            // Existing supplier shipments logic
            // ... existing code ...
        }

    } catch (error) {
        alert('Failed to process import: ' + error.message);
    }
}
```

**Files**: frontend/data-management.html

---

### TASK-623: Database migration for supplier foreign key

**Purpose**: Link pending_inventory to suppliers master table

**Migration SQL**:

```sql
-- Add supplier_id foreign key to pending_inventory
-- This links each pending order to the master suppliers table

ALTER TABLE pending_inventory
ADD COLUMN supplier_id INT NULL COMMENT 'Reference to suppliers.id'
AFTER supplier;

-- Create foreign key constraint
ALTER TABLE pending_inventory
ADD CONSTRAINT fk_pending_inventory_supplier
FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
ON DELETE SET NULL
ON UPDATE CASCADE;

-- Create index for performance
CREATE INDEX idx_pending_inventory_supplier_id
ON pending_inventory(supplier_id);

-- Optional: Backfill existing records
-- Match existing supplier names to suppliers table
UPDATE pending_inventory pi
JOIN suppliers s ON UPPER(TRIM(pi.supplier)) = s.normalized_name
SET pi.supplier_id = s.id
WHERE pi.supplier_id IS NULL
  AND pi.supplier IS NOT NULL;

-- Log backfill results
SELECT
    COUNT(*) as total_records,
    SUM(CASE WHEN supplier_id IS NOT NULL THEN 1 ELSE 0 END) as linked_records,
    SUM(CASE WHEN supplier_id IS NULL AND supplier IS NOT NULL THEN 1 ELSE 0 END) as unlinked_records
FROM pending_inventory;

-- Migration completed
SELECT 'Supplier foreign key added to pending_inventory table' AS status;
```

**Files**: database/migrations/add_pending_inventory_supplier_fk.sql

---

### TASK-624: Test supplier mapping workflow end-to-end

**Purpose**: Validate complete supplier mapping integration

**Test Scenarios**:

1. **Auto-Mapping High Confidence** (90%+ confidence)
   - Upload CSV with "Yuasa" (exact match in system as "Yuasa Battery")
   - Verify auto-maps without user intervention
   - Verify alias saved

2. **Manual Review Medium Confidence** (70-89% confidence)
   - Upload CSV with "Boln" (fuzzy match to "Bolin Battery")
   - Verify mapping modal shows for user review
   - Accept suggested mapping
   - Verify import completes with correct supplier_id

3. **Create New Supplier** (<70% confidence or no match)
   - Upload CSV with "New Supplier Corp"
   - Verify "Create New" option selected by default
   - Proceed with import
   - Verify new supplier created in suppliers table
   - Verify alias saved

4. **Manual Selection**
   - Upload CSV with ambiguous name
   - User manually selects from dropdown
   - Verify correct supplier_id assigned

5. **Bulk Import**
   - Upload CSV with 10+ different suppliers
   - Mix of auto-map, manual, and create new
   - Verify all mappings applied correctly
   - Verify all aliases saved

**Test Script**:

```python
def test_supplier_mapping_workflow():
    """End-to-end test of supplier mapping for pending inventory"""

    # Test 1: Auto-mapping
    csv_content = """sku_id,quantity,destination,order_date,expected_arrival,order_type,status,notes
UB-YTX14-BS,500,kentucky,2025-10-01,2025-11-15,Yuasa,ordered,PO-2025-001
"""

    response = test_import_with_mapping(csv_content)
    assert response['auto_mapped_count'] >= 1

    # Test 2: Manual review
    csv_content_fuzzy = """sku_id,quantity,destination,order_date,expected_arrival,order_type,status,notes
UB-YTX14-BS,500,kentucky,2025-10-01,2025-11-15,Boln,ordered,PO-2025-002
"""

    preview = test_preview(csv_content_fuzzy)
    assert preview['mapping_suggestions']['Boln'][0]['confidence'] >= 70
    assert preview['mapping_suggestions']['Boln'][0]['confidence'] < 90

    # Test 3: Create new
    csv_content_new = """sku_id,quantity,destination,order_date,expected_arrival,order_type,status,notes
UB-YTX14-BS,500,kentucky,2025-10-01,2025-11-15,New Supplier Corp,ordered,PO-2025-003
"""

    preview = test_preview(csv_content_new)
    assert preview['estimated_new_suppliers'] >= 1

    print("All supplier mapping tests passed")
```

**Files**: tests/test_pending_inventory_supplier_mapping.py

---

## Benefits of Supplier Mapping Integration

**Data Quality**:
- Eliminates duplicate supplier names (Yuasa vs YUASA vs Yuasa Battery)
- Normalizes supplier data across all imports
- Builds comprehensive supplier alias database

**User Experience**:
- Auto-mapping saves time (90%+ accuracy for known suppliers)
- Manual review only for ambiguous cases
- Single source of truth for supplier information

**Business Intelligence**:
- Aggregate spending by supplier across all data sources
- Supplier performance metrics more accurate
- Better supplier relationship management

**System Integration**:
- Pending inventory linked to same supplier master as shipments
- Supplier analytics work across all modules
- Future integrations easier (supplier contracts, pricing, etc.)

---

**Estimated Implementation Time**: 4-6 hours

**Dependencies**:
- Requires V5.0 supplier infrastructure (suppliers, supplier_aliases tables)
- Requires backend/supplier_matcher.py (fuzzy matching logic)
- Requires backend/supplier_import.py (import patterns)

**Completion Criteria**:
- Preview endpoint returns mapping suggestions
- Import accepts and applies supplier mappings
- New suppliers created in master table
- Aliases saved for future imports
- Database foreign key linking pending_inventory to suppliers
- All test scenarios pass
- No duplicate supplier names after import

---

**Last Updated**: 2025-10-24
**Status**: Ready for implementation
**Next Step**: Begin TASK-593 - Create supplier_ordering_sku_details.py module
