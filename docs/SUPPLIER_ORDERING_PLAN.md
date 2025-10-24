# Supplier Ordering System - Detailed Implementation Plan

## Executive Summary

This document outlines the implementation plan for a new Supplier Ordering page that intelligently calculates order quantities for both Burnaby (CA) and Kentucky (KY) warehouses using forecasted demand, supplier lead times, safety stock requirements, and current inventory positions.

**Key Differentiators from Transfer Planning**:
- Ordering from external suppliers (not inter-warehouse transfers)
- Separate calculations for CA and KY warehouses
- Incorporates supplier lead time variability
- Uses 12-month demand forecasts for future planning
- Considers safety stock based on ABC-XYZ classification and lead time
- Export-only workflow (no automatic pending inventory creation)

---

## 1. Business Requirements

### 1.1 Core Functionality

**Purpose**: Provide data-driven recommendations for supplier orders that optimize inventory levels across both warehouses while minimizing stockouts and excess inventory.

**User Workflow**:
1. Access Supplier Ordering page from main navigation
2. View all SKUs with auto-calculated order recommendations for CA and KY
3. Filter by supplier, SKU status (Active/Death Row/Discontinued), ABC-XYZ class
4. Review SKU details including 12-month forecast, current inventory, pending orders
5. Adjust recommended quantities as needed
6. Lock confirmed quantities for both warehouses
7. Export order plan to Excel/CSV for supplier communication
8. Submit orders manually through existing procurement process

### 1.2 Key Business Rules

**SKU Coverage**:
- Active SKUs: Full calculation with standard coverage targets
- Death Row SKUs: Show with WARNING badge, allow ordering with reduced quantities
- Discontinued SKUs: Show with DISCONTINUED badge, typically calculate as zero but allow manual override

**Order Rounding**:
- Chargers/Cables: Round to multiples of 25 units
- Standard items: Round to multiples of 50 units
- High-volume items: Round to multiples of 100 units
- Same logic as transfer planning for consistency

**Warehouse Independence**:
- CA (Burnaby) and KY (Kentucky) calculated completely separately
- Each warehouse has its own forecast from `forecast_details` table
- Different supplier lead times per destination from `supplier_lead_times` table
- Orders can be placed for one warehouse, both, or neither

**Supplier Considerations**:
- Use actual lead time data from `supplier_lead_times` table
- Account for lead time variability in safety stock calculations
- Group SKUs by supplier for easier order consolidation
- Show supplier reliability score to inform decisions

---

## 2. Technical Architecture

### 2.1 Database Schema Analysis

**Existing Tables to Leverage**:

```sql
-- Forecast data (12-month projections per SKU per warehouse)
forecast_details:
  - sku_id, warehouse (burnaby/kentucky/combined)
  - month_1_qty through month_12_qty
  - total_qty_forecast, avg_monthly_qty
  - growth_rate_applied, confidence_score
  - method_used (ABC-X, ABC-Y, ABC-Z methodologies)

-- Supplier lead time statistics
supplier_lead_times:
  - supplier, destination (burnaby/kentucky)
  - lead_time_days (default/recommended)
  - avg_lead_time, median_lead_time, p95_lead_time
  - std_dev_lead_time, coefficient_variation
  - reliability_score (0-100)

-- Current inventory positions
inventory_current:
  - sku_id, burnaby_qty, kentucky_qty
  - last_updated

-- Pending orders that will arrive soon
pending_inventory:
  - sku_id, quantity, destination
  - order_date, expected_arrival, lead_time_days
  - order_type (supplier/transfer), status

-- SKU master data
skus:
  - sku_id, description, category, supplier
  - abc_code (A/B/C), xyz_code (X/Y/Z)
  - status (Active/Death Row/Discontinued)

-- Historical demand patterns
monthly_sales:
  - sku_id, year_month
  - burnaby_sales, kentucky_sales
  - stockout_days tracking
  - corrected_demand calculations
```

**New Table Required**: `supplier_order_confirmations`

```sql
CREATE TABLE supplier_order_confirmations (
  id INT PRIMARY KEY AUTO_INCREMENT,
  sku_id VARCHAR(50) NOT NULL,
  warehouse ENUM('burnaby', 'kentucky') NOT NULL,
  suggested_qty INT NOT NULL COMMENT 'System-calculated quantity',
  confirmed_qty INT NOT NULL COMMENT 'User-locked quantity',
  supplier VARCHAR(100) NOT NULL,

  -- Calculation transparency
  current_inventory INT NOT NULL,
  pending_orders INT NOT NULL,
  forecasted_demand_period DECIMAL(10,2) COMMENT 'Demand during lead time + review period',
  safety_stock_qty INT NOT NULL,
  reorder_point INT NOT NULL,

  -- Order context
  lead_time_days INT NOT NULL,
  coverage_months DECIMAL(4,2) COMMENT 'Resulting coverage after order arrives',
  order_date DATE NOT NULL,
  expected_arrival DATE,

  -- User tracking
  is_locked BOOLEAN DEFAULT FALSE,
  locked_by VARCHAR(100),
  locked_at TIMESTAMP NULL,
  notes TEXT,

  -- Audit trail
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  FOREIGN KEY (sku_id) REFERENCES skus(sku_id) ON DELETE CASCADE,
  INDEX idx_warehouse_supplier (warehouse, supplier),
  INDEX idx_locked (is_locked, order_date),
  INDEX idx_sku_warehouse (sku_id, warehouse)
) ENGINE=InnoDB COMMENT='Tracks supplier order recommendations and user confirmations';
```

### 2.2 Order Calculation Algorithm

**Recommended Approach**: Reorder Point Model with Safety Stock

This is the industry-standard approach for inventory replenishment that balances service level with inventory costs.

#### 2.2.1 Core Formula

```python
def calculate_order_quantity(sku_id, warehouse, supplier):
    """
    Calculate recommended order quantity using reorder point model.

    Order Quantity = (Demand during Lead Time + Safety Stock)
                     - (Current Inventory + Pending Orders)

    If result is negative, no order needed (overstocked).
    If result is positive, round to appropriate multiple.
    """

    # 1. Get current position
    current_inventory = get_current_inventory(sku_id, warehouse)
    pending_orders = get_pending_quantity(sku_id, warehouse)
    current_position = current_inventory + pending_orders

    # 2. Get supplier lead time (destination-specific)
    lead_time_data = get_supplier_lead_time(supplier, warehouse)
    lead_time_days = lead_time_data['p95_lead_time']  # Use 95th percentile for safety

    # 3. Get forecasted monthly demand for this warehouse
    forecast = get_forecast_data(sku_id, warehouse)
    avg_monthly_demand = forecast['avg_monthly_qty']

    # 4. Calculate demand during lead time
    # Convert lead time to months and multiply by monthly demand
    lead_time_months = lead_time_days / 30.0
    demand_during_lead_time = avg_monthly_demand * lead_time_months

    # 5. Calculate safety stock (ABC-XYZ based)
    safety_stock = calculate_safety_stock(
        sku_id=sku_id,
        avg_monthly_demand=avg_monthly_demand,
        lead_time_days=lead_time_days,
        lead_time_variability=lead_time_data['coefficient_variation']
    )

    # 6. Calculate reorder point
    reorder_point = demand_during_lead_time + safety_stock

    # 7. Calculate order quantity
    order_qty = reorder_point - current_position

    # 8. Round to appropriate multiple (same as transfer logic)
    if order_qty > 0:
        rounded_qty = round_to_multiple(sku_id, order_qty)

        # Verify supplier can fulfill (check Burnaby availability if supplier is local)
        if supplier_location == 'burnaby':
            available = get_burnaby_available(sku_id)
            final_qty = min(rounded_qty, available)
        else:
            final_qty = rounded_qty
    else:
        final_qty = 0  # No order needed

    return {
        'suggested_qty': final_qty,
        'current_inventory': current_inventory,
        'pending_orders': pending_orders,
        'current_position': current_position,
        'demand_during_lead_time': round(demand_during_lead_time, 2),
        'safety_stock': safety_stock,
        'reorder_point': reorder_point,
        'lead_time_days': lead_time_days,
        'coverage_months': calculate_coverage_months(final_qty, avg_monthly_demand)
    }
```

#### 2.2.2 Safety Stock Calculation

**Approach**: Hybrid ABC-XYZ Model with Lead Time Adjustment

```python
def calculate_safety_stock(sku_id, avg_monthly_demand, lead_time_days,
                          lead_time_variability):
    """
    Calculate safety stock using ABC-XYZ classification and lead time.

    Safety Stock = Service Level Factor × Demand Variability Factor
                   × Average Demand × √(Lead Time in Months)

    Service Level by ABC class (Z-score):
      A-class: 1.65 (95% service level)
      B-class: 1.28 (90% service level)
      C-class: 0.84 (80% service level)

    Demand Variability by XYZ class:
      X (stable): 1.0× multiplier
      Y (variable): 1.2× multiplier
      Z (volatile): 1.5× multiplier

    Lead Time Adjustment:
      Longer lead times = more uncertainty = more safety stock
      Use √(lead_time_months) as is standard in inventory theory
    """

    # Get ABC-XYZ classification
    sku_data = get_sku_data(sku_id)
    abc_class = sku_data['abc_code']  # A, B, or C
    xyz_class = sku_data['xyz_code']  # X, Y, or Z

    # Service level factors (Z-scores)
    service_level_factors = {
        'A': 1.65,  # 95% service level
        'B': 1.28,  # 90% service level
        'C': 0.84   # 80% service level
    }

    # Demand variability factors
    variability_factors = {
        'X': 1.0,   # Stable demand
        'Y': 1.2,   # Variable demand
        'Z': 1.5    # Volatile demand
    }

    # Get factors
    service_factor = service_level_factors.get(abc_class, 1.28)
    variability_factor = variability_factors.get(xyz_class, 1.2)

    # Additional adjustment for supplier reliability
    # If supplier has high lead time variability, increase safety stock
    reliability_adjustment = 1.0
    if lead_time_variability > 0.3:  # CV > 30% means unreliable
        reliability_adjustment = 1.3
    elif lead_time_variability > 0.2:  # CV > 20%
        reliability_adjustment = 1.15

    # Calculate lead time factor (square root of lead time in months)
    lead_time_months = lead_time_days / 30.0
    lead_time_factor = math.sqrt(lead_time_months)

    # Final safety stock calculation
    safety_stock = (service_factor
                   * variability_factor
                   * reliability_adjustment
                   * avg_monthly_demand
                   * lead_time_factor)

    # Round up to ensure protection
    safety_stock = math.ceil(safety_stock)

    # Apply minimum safety stock rules
    if abc_class == 'A' and safety_stock < avg_monthly_demand * 0.5:
        safety_stock = math.ceil(avg_monthly_demand * 0.5)  # Minimum 2 weeks for A items

    return safety_stock
```

#### 2.2.3 Forecast Period Selection

**Dynamic Period Based on Lead Time and Review Cycle**:

```python
def get_forecast_months_needed(lead_time_days, review_period_days=30):
    """
    Determine how many months of forecast to consider.

    Formula: (Lead Time + Review Period) / 30 days

    This ensures we order enough to cover:
    1. Time waiting for the order to arrive (lead time)
    2. Time until next order review (review period)

    Example: 60-day lead time + 30-day review = 3 months forecast
    """
    total_days = lead_time_days + review_period_days
    months_needed = math.ceil(total_days / 30.0)
    return min(months_needed, 12)  # Cap at 12 months


def get_forecasted_demand(sku_id, warehouse, lead_time_days):
    """
    Get forecasted demand for the relevant period.
    Uses month-by-month forecast data for accuracy.
    """
    months_needed = get_forecast_months_needed(lead_time_days)

    forecast_detail = get_forecast_detail(sku_id, warehouse)

    # Sum up the required months
    total_forecast = sum([
        forecast_detail[f'month_{i}_qty']
        for i in range(1, months_needed + 1)
    ])

    # Calculate average monthly for consistency
    avg_monthly = total_forecast / months_needed if months_needed > 0 else 0

    return {
        'avg_monthly_qty': avg_monthly,
        'total_period_qty': total_forecast,
        'months_covered': months_needed,
        'confidence_score': forecast_detail['confidence_score'],
        'method_used': forecast_detail['method_used']
    }
```

### 2.3 API Endpoints

**New Backend Endpoints** (to be added to `backend/forecasting_api.py` or new `backend/supplier_ordering_api.py`):

```python
# GET /api/supplier-orders/recommendations
# Returns all SKUs with order recommendations for both warehouses

# Request Query Parameters:
# - supplier: Filter by supplier name (optional)
# - status: Filter by SKU status (Active/Death Row/Discontinued) (optional)
# - abc_class: Filter by ABC classification (optional)
# - xyz_class: Filter by XYZ classification (optional)
# - warehouse: Filter by specific warehouse (optional)

# Response:
{
  "success": true,
  "data": [
    {
      "sku_id": "UB-YTX14-BS",
      "description": "12V 12AH Battery - YTX14-BS",
      "supplier": "Universal Battery",
      "category": "Batteries",
      "abc_code": "A",
      "xyz_code": "X",
      "status": "Active",

      "burnaby": {
        "current_inventory": 45,
        "pending_orders": 100,
        "current_position": 145,
        "avg_monthly_demand": 32.5,
        "demand_during_lead_time": 65.0,
        "safety_stock": 28,
        "reorder_point": 93,
        "suggested_order_qty": 0,  # No order needed (overstocked)
        "lead_time_days": 60,
        "coverage_months": 4.5,
        "supplier_reliability": 87,
        "next_review_date": "2025-11-15"
      },

      "kentucky": {
        "current_inventory": 12,
        "pending_orders": 0,
        "current_position": 12,
        "avg_monthly_demand": 48.3,
        "demand_during_lead_time": 96.6,
        "safety_stock": 42,
        "reorder_point": 139,
        "suggested_order_qty": 150,  # Rounded to 50s
        "lead_time_days": 60,
        "coverage_months": 3.1,
        "supplier_reliability": 87,
        "next_review_date": "2025-11-15"
      },

      "forecast_12_months": {
        "burnaby_total": 390,
        "kentucky_total": 580,
        "combined_total": 970,
        "monthly_breakdown": [
          {"month": 1, "burnaby_qty": 30, "kentucky_qty": 45},
          {"month": 2, "burnaby_qty": 32, "kentucky_qty": 48},
          // ... months 3-12
        ]
      }
    }
    // ... more SKUs
  ],
  "metadata": {
    "total_skus": 4247,
    "suppliers_count": 45,
    "total_ca_order_value": 125000.00,
    "total_ky_order_value": 185000.00,
    "calculation_date": "2025-10-22",
    "forecast_run_id": 35
  }
}


# POST /api/supplier-orders/confirm
# Lock/unlock confirmed quantities

# Request:
{
  "sku_id": "UB-YTX14-BS",
  "warehouse": "kentucky",
  "confirmed_qty": 150,
  "is_locked": true,
  "notes": "Negotiated bulk pricing at 150 units"
}

# Response:
{
  "success": true,
  "message": "Order quantity confirmed for UB-YTX14-BS (Kentucky)",
  "data": {
    "sku_id": "UB-YTX14-BS",
    "warehouse": "kentucky",
    "suggested_qty": 150,
    "confirmed_qty": 150,
    "is_locked": true,
    "locked_at": "2025-10-22T10:30:00Z"
  }
}


# GET /api/supplier-orders/sku-details/{sku_id}
# Detailed SKU information including full 12-month forecast

# Response:
{
  "success": true,
  "data": {
    "sku_info": { /* basic SKU data */ },
    "burnaby_analysis": {
      "current_inventory": 45,
      "pending_orders": 100,
      "12_month_forecast": {
        "monthly_breakdown": [ /* detailed months */ ],
        "total_qty": 390,
        "total_revenue": 15600.00,
        "avg_monthly_qty": 32.5,
        "confidence_score": 0.85
      },
      "safety_stock_analysis": {
        "calculated_safety_stock": 28,
        "service_level": "95%",
        "abc_xyz_factors": "A-X (High Value, Stable Demand)"
      },
      "supplier_performance": {
        "avg_lead_time": 58,
        "p95_lead_time": 72,
        "reliability_score": 87
      }
    },
    "kentucky_analysis": { /* same structure */ },
    "sales_history": [ /* last 12 months actual sales */ ]
  }
}


# POST /api/supplier-orders/export
# Export order plan to Excel/CSV

# Request:
{
  "format": "excel",  // or "csv"
  "supplier": "Universal Battery",  // optional filter
  "include_locked_only": false,
  "warehouses": ["burnaby", "kentucky"]
}

# Response:
{
  "success": true,
  "file_url": "/exports/supplier_orders_2025-10-22.xlsx",
  "file_size": 45678,
  "records_exported": 247
}
```

---

## 3. Frontend Implementation

### 3.1 Page Structure

**File**: `frontend/supplier-ordering.html`

**Layout Sections**:

```
┌─────────────────────────────────────────────────────────────┐
│ Navigation Bar (consistent with other pages)                │
├─────────────────────────────────────────────────────────────┤
│ Page Header: Supplier Ordering                              │
│ - Title, Last Calculation Date, Forecast Run ID             │
├─────────────────────────────────────────────────────────────┤
│ Metrics Summary Cards (4 cards in row)                      │
│ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
│ │Total SKUs │ │CA Order   │ │KY Order   │ │Locked     │   │
│ │to Order   │ │Value      │ │Value      │ │Items      │   │
│ └───────────┘ └───────────┘ └───────────┘ └───────────┘   │
├─────────────────────────────────────────────────────────────┤
│ Action Buttons Row                                          │
│ [Refresh] [Export Excel] [Export CSV] [Clear All Locks]    │
├─────────────────────────────────────────────────────────────┤
│ Filters Row                                                 │
│ Supplier: [Dropdown] Status: [Dropdown] ABC: [Dropdown]    │
│ XYZ: [Dropdown] Warehouse: [Both/CA/KY]                    │
├─────────────────────────────────────────────────────────────┤
│ Main Data Table (DataTables with frozen header)            │
│ - Scrollable, sortable, searchable                         │
│ - Inline editing for confirmed quantities                  │
│ - Color-coded priority and status badges                   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Table Columns

**Column Configuration**:

| Column | Description | Width | Sortable | Editable | Notes |
|--------|-------------|-------|----------|----------|-------|
| SKU ID | Clickable link to details modal | 120px | Yes | No | Primary identifier |
| Description | Product name | 250px | Yes | No | Truncate with ellipsis |
| Supplier | Supplier name | 140px | Yes | No | Filter-enabled |
| Category | Product category | 100px | Yes | No | Filter-enabled |
| ABC | Classification | 50px | Yes | No | Badge style |
| XYZ | Variability | 50px | Yes | No | Badge style |
| Status | Active/Death Row/Discontinued | 100px | Yes | No | Color-coded badge |
| **CA Current** | Burnaby current inventory | 80px | Yes | No | Numeric |
| **CA Pending** | Burnaby pending orders | 80px | Yes | No | Numeric |
| **CA Position** | Current + Pending | 90px | Yes | No | Calculated, bold |
| **CA to Order** | Suggested CA order qty | 90px | Yes | No | System calculated |
| **CA Confirmed** | User-confirmed CA qty | 100px | Yes | **Yes** | Editable input |
| **CA Lock** | Lock/unlock button | 60px | No | **Yes** | Toggle button |
| **KY Current** | Kentucky current inventory | 80px | Yes | No | Numeric |
| **KY Pending** | Kentucky pending orders | 80px | Yes | No | Numeric |
| **KY Position** | Current + Pending | 90px | Yes | No | Calculated, bold |
| **KY to Order** | Suggested KY order qty | 90px | Yes | No | System calculated |
| **KY Confirmed** | User-confirmed KY qty | 100px | Yes | **Yes** | Editable input |
| **KY Lock** | Lock/unlock button | 60px | No | **Yes** | Toggle button |
| Lead Time | Supplier lead time (days) | 80px | Yes | No | From supplier_lead_times |
| Reliability | Supplier reliability score | 90px | Yes | No | 0-100 scale, color-coded |

**Total Columns**: 23 columns (comprehensive but organized)

**Column Groups** (visual headers):
- SKU Information (columns 1-7)
- Burnaby (CA) Ordering (columns 8-13)
- Kentucky (KY) Ordering (columns 14-19)
- Supplier Data (columns 20-21)

### 3.3 Visual Design Elements

**Status Badges**:

```css
/* SKU Status */
.status-active {
    background-color: #28a745;  /* Green */
    color: white;
}

.status-death-row {
    background-color: #ffc107;  /* Yellow */
    color: black;
    font-weight: bold;
}
.status-death-row::after {
    content: " ⚠️";
}

.status-discontinued {
    background-color: #6c757d;  /* Gray */
    color: white;
    text-decoration: line-through;
}
.status-discontinued::after {
    content: " 🚫";
}

/* ABC-XYZ Classifications */
.abc-A { background: #dc3545; color: white; }  /* Red - High value */
.abc-B { background: #ffc107; color: black; }  /* Yellow - Medium */
.abc-C { background: #28a745; color: white; }  /* Green - Low */

.xyz-X { background: #007bff; color: white; }  /* Blue - Stable */
.xyz-Y { background: #17a2b8; color: white; }  /* Cyan - Variable */
.xyz-Z { background: #6f42c1; color: white; }  /* Purple - Volatile */

/* Supplier Reliability */
.reliability-excellent { color: #28a745; font-weight: bold; }  /* 90-100 */
.reliability-good { color: #ffc107; }  /* 70-89 */
.reliability-poor { color: #dc3545; font-weight: bold; }  /* < 70 */

/* Order Quantity Highlights */
.order-suggested {
    background-color: #e7f3ff;
    font-weight: bold;
    color: #0066cc;
}

.order-locked {
    background-color: #d4edda;  /* Light green */
    color: #155724;
    font-weight: bold;
    border: 2px solid #c3e6cb;
}

.order-zero {
    color: #6c757d;  /* Gray for zero quantities */
    font-style: italic;
}

.order-high-priority {
    background-color: #fff3cd;  /* Light yellow */
    border-left: 4px solid #ffc107;
}
```

**Lock/Unlock Buttons**:

```html
<!-- Unlocked state -->
<button class="btn btn-sm btn-outline-secondary lock-btn"
        data-sku="UB-YTX14-BS"
        data-warehouse="burnaby">
    <i class="fas fa-unlock"></i>
</button>

<!-- Locked state -->
<button class="btn btn-sm btn-success lock-btn locked"
        data-sku="UB-YTX14-BS"
        data-warehouse="burnaby">
    <i class="fas fa-lock"></i>
</button>
```

### 3.4 SKU Details Modal

**Enhanced Modal with Forecasting Data**:

```html
<div class="modal fade" id="skuDetailsModal">
  <div class="modal-dialog modal-xl">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">
          <span id="modal-sku-id"></span> - <span id="modal-description"></span>
        </h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>

      <div class="modal-body">
        <!-- Tab Navigation -->
        <ul class="nav nav-tabs" role="tablist">
          <li class="nav-item">
            <a class="nav-link active" data-bs-toggle="tab" href="#overview-tab">Overview</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" data-bs-toggle="tab" href="#burnaby-tab">Burnaby (CA)</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" data-bs-toggle="tab" href="#kentucky-tab">Kentucky (KY)</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" data-bs-toggle="tab" href="#forecast-tab">12-Month Forecast</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" data-bs-toggle="tab" href="#supplier-tab">Supplier Performance</a>
          </li>
        </ul>

        <!-- Tab Content -->
        <div class="tab-content">

          <!-- Overview Tab -->
          <div id="overview-tab" class="tab-pane fade show active">
            <div class="row mt-3">
              <div class="col-md-6">
                <h6>SKU Information</h6>
                <table class="table table-sm">
                  <tr><th>SKU ID:</th><td id="detail-sku-id"></td></tr>
                  <tr><th>Description:</th><td id="detail-description"></td></tr>
                  <tr><th>Supplier:</th><td id="detail-supplier"></td></tr>
                  <tr><th>Category:</th><td id="detail-category"></td></tr>
                  <tr><th>ABC Classification:</th><td id="detail-abc"></td></tr>
                  <tr><th>XYZ Classification:</th><td id="detail-xyz"></td></tr>
                  <tr><th>Status:</th><td id="detail-status"></td></tr>
                </table>
              </div>
              <div class="col-md-6">
                <h6>Inventory Summary</h6>
                <table class="table table-sm">
                  <tr>
                    <th></th>
                    <th>Burnaby</th>
                    <th>Kentucky</th>
                    <th>Total</th>
                  </tr>
                  <tr>
                    <th>Current Inventory:</th>
                    <td id="summary-ca-current"></td>
                    <td id="summary-ky-current"></td>
                    <td id="summary-total-current"></td>
                  </tr>
                  <tr>
                    <th>Pending Orders:</th>
                    <td id="summary-ca-pending"></td>
                    <td id="summary-ky-pending"></td>
                    <td id="summary-total-pending"></td>
                  </tr>
                  <tr>
                    <th>Suggested Order:</th>
                    <td id="summary-ca-order"></td>
                    <td id="summary-ky-order"></td>
                    <td id="summary-total-order"></td>
                  </tr>
                </table>
              </div>
            </div>
          </div>

          <!-- Burnaby Tab -->
          <div id="burnaby-tab" class="tab-pane fade">
            <div class="row mt-3">
              <div class="col-md-6">
                <h6>Order Calculation (Burnaby)</h6>
                <table class="table table-sm table-bordered">
                  <tr>
                    <th>Current Inventory:</th>
                    <td class="text-end" id="ca-current-inv"></td>
                  </tr>
                  <tr>
                    <th>Pending Orders:</th>
                    <td class="text-end" id="ca-pending-inv"></td>
                  </tr>
                  <tr class="table-primary">
                    <th>Current Position:</th>
                    <td class="text-end fw-bold" id="ca-current-pos"></td>
                  </tr>
                  <tr>
                    <th>Avg Monthly Demand:</th>
                    <td class="text-end" id="ca-avg-demand"></td>
                  </tr>
                  <tr>
                    <th>Lead Time (days):</th>
                    <td class="text-end" id="ca-lead-time"></td>
                  </tr>
                  <tr>
                    <th>Demand During Lead Time:</th>
                    <td class="text-end" id="ca-lead-demand"></td>
                  </tr>
                  <tr>
                    <th>Safety Stock:</th>
                    <td class="text-end" id="ca-safety-stock"></td>
                  </tr>
                  <tr class="table-warning">
                    <th>Reorder Point:</th>
                    <td class="text-end fw-bold" id="ca-reorder-point"></td>
                  </tr>
                  <tr class="table-success">
                    <th>Suggested Order Qty:</th>
                    <td class="text-end fw-bold fs-5" id="ca-suggested-order"></td>
                  </tr>
                  <tr>
                    <th>Coverage After Order (months):</th>
                    <td class="text-end" id="ca-coverage"></td>
                  </tr>
                </table>
              </div>
              <div class="col-md-6">
                <h6>Sales History (Burnaby)</h6>
                <canvas id="ca-sales-chart"></canvas>
                <div class="mt-3">
                  <small class="text-muted">
                    Blue bars: Actual sales | Red line: Stockout days
                  </small>
                </div>
              </div>
            </div>
          </div>

          <!-- Kentucky Tab -->
          <div id="kentucky-tab" class="tab-pane fade">
            <!-- Same structure as Burnaby but with KY data -->
            <div class="row mt-3">
              <div class="col-md-6">
                <h6>Order Calculation (Kentucky)</h6>
                <table class="table table-sm table-bordered">
                  <!-- Same rows as CA but with ky- IDs -->
                </table>
              </div>
              <div class="col-md-6">
                <h6>Sales History (Kentucky)</h6>
                <canvas id="ky-sales-chart"></canvas>
              </div>
            </div>
          </div>

          <!-- 12-Month Forecast Tab -->
          <div id="forecast-tab" class="tab-pane fade">
            <div class="mt-3">
              <h6>12-Month Demand Forecast</h6>
              <div class="row">
                <div class="col-md-12">
                  <canvas id="forecast-chart"></canvas>
                </div>
              </div>

              <div class="row mt-4">
                <div class="col-md-6">
                  <h6>Burnaby Forecast</h6>
                  <table class="table table-sm table-striped">
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th class="text-end">Quantity</th>
                        <th class="text-end">Revenue</th>
                      </tr>
                    </thead>
                    <tbody id="ca-forecast-table">
                      <!-- Populated dynamically -->
                    </tbody>
                    <tfoot class="table-primary">
                      <tr>
                        <th>Total:</th>
                        <th class="text-end" id="ca-forecast-total-qty"></th>
                        <th class="text-end" id="ca-forecast-total-rev"></th>
                      </tr>
                      <tr>
                        <th>Average/Month:</th>
                        <th class="text-end" id="ca-forecast-avg-qty"></th>
                        <th class="text-end" id="ca-forecast-avg-rev"></th>
                      </tr>
                    </tfoot>
                  </table>
                  <div class="alert alert-info">
                    <strong>Forecast Method:</strong> <span id="ca-forecast-method"></span><br>
                    <strong>Confidence Score:</strong> <span id="ca-forecast-confidence"></span>
                  </div>
                </div>

                <div class="col-md-6">
                  <h6>Kentucky Forecast</h6>
                  <table class="table table-sm table-striped">
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th class="text-end">Quantity</th>
                        <th class="text-end">Revenue</th>
                      </tr>
                    </thead>
                    <tbody id="ky-forecast-table">
                      <!-- Populated dynamically -->
                    </tbody>
                    <tfoot class="table-primary">
                      <tr>
                        <th>Total:</th>
                        <th class="text-end" id="ky-forecast-total-qty"></th>
                        <th class="text-end" id="ky-forecast-total-rev"></th>
                      </tr>
                      <tr>
                        <th>Average/Month:</th>
                        <th class="text-end" id="ky-forecast-avg-qty"></th>
                        <th class="text-end" id="ky-forecast-avg-rev"></th>
                      </tr>
                    </tfoot>
                  </table>
                  <div class="alert alert-info">
                    <strong>Forecast Method:</strong> <span id="ky-forecast-method"></span><br>
                    <strong>Confidence Score:</strong> <span id="ky-forecast-confidence"></span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Supplier Performance Tab -->
          <div id="supplier-tab" class="tab-pane fade">
            <div class="row mt-3">
              <div class="col-md-6">
                <h6>Lead Time Statistics</h6>
                <table class="table table-sm">
                  <tr>
                    <th>Destination:</th>
                    <th>Burnaby</th>
                    <th>Kentucky</th>
                  </tr>
                  <tr>
                    <td>Average Lead Time:</td>
                    <td id="supplier-ca-avg-lead"></td>
                    <td id="supplier-ky-avg-lead"></td>
                  </tr>
                  <tr>
                    <td>Median Lead Time:</td>
                    <td id="supplier-ca-median-lead"></td>
                    <td id="supplier-ky-median-lead"></td>
                  </tr>
                  <tr>
                    <td>P95 Lead Time:</td>
                    <td id="supplier-ca-p95-lead"></td>
                    <td id="supplier-ky-p95-lead"></td>
                  </tr>
                  <tr>
                    <td>Min - Max:</td>
                    <td id="supplier-ca-minmax-lead"></td>
                    <td id="supplier-ky-minmax-lead"></td>
                  </tr>
                  <tr>
                    <td>Std Deviation:</td>
                    <td id="supplier-ca-std-lead"></td>
                    <td id="supplier-ky-std-lead"></td>
                  </tr>
                  <tr>
                    <td>Reliability Score:</td>
                    <td id="supplier-ca-reliability"></td>
                    <td id="supplier-ky-reliability"></td>
                  </tr>
                  <tr>
                    <td>Shipment Count:</td>
                    <td id="supplier-ca-shipments"></td>
                    <td id="supplier-ky-shipments"></td>
                  </tr>
                </table>
              </div>
              <div class="col-md-6">
                <h6>Lead Time Distribution</h6>
                <canvas id="supplier-lead-time-chart"></canvas>
                <div class="alert alert-warning mt-3" id="supplier-warning" style="display:none;">
                  <i class="fas fa-exclamation-triangle"></i>
                  <strong>High Variability Detected</strong><br>
                  This supplier has inconsistent lead times. Safety stock has been increased to compensate.
                </div>
              </div>
            </div>
          </div>

        </div><!-- end tab-content -->
      </div>

      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
        <button type="button" class="btn btn-primary" id="btn-adjust-order">Adjust Order Quantities</button>
      </div>
    </div>
  </div>
</div>
```

### 3.5 JavaScript Logic

**File**: `frontend/supplier-ordering.js`

**Key Functions**:

```javascript
// Main data table initialization
let ordersTable;

async function initializeOrdersTable() {
    ordersTable = $('#orders-table').DataTable({
        ajax: {
            url: '/api/supplier-orders/recommendations',
            dataSrc: 'data'
        },
        columns: [
            { data: 'sku_id', render: renderSkuLink },
            { data: 'description' },
            { data: 'supplier' },
            { data: 'category' },
            { data: 'abc_code', render: renderABCBadge },
            { data: 'xyz_code', render: renderXYZBadge },
            { data: 'status', render: renderStatusBadge },

            // Burnaby columns
            { data: 'burnaby.current_inventory', className: 'text-end' },
            { data: 'burnaby.pending_orders', className: 'text-end' },
            { data: 'burnaby.current_position', className: 'text-end fw-bold' },
            { data: 'burnaby.suggested_order_qty', render: renderSuggestedQty },
            { data: 'burnaby', render: renderConfirmedQty },
            { data: 'burnaby', render: renderLockButton },

            // Kentucky columns
            { data: 'kentucky.current_inventory', className: 'text-end' },
            { data: 'kentucky.pending_orders', className: 'text-end' },
            { data: 'kentucky.current_position', className: 'text-end fw-bold' },
            { data: 'kentucky.suggested_order_qty', render: renderSuggestedQty },
            { data: 'kentucky', render: renderConfirmedQty },
            { data: 'kentucky', render: renderLockButton },

            // Supplier data
            { data: 'burnaby.lead_time_days', className: 'text-end' },
            { data: 'burnaby.supplier_reliability', render: renderReliabilityScore }
        ],
        order: [[10, 'desc'], [16, 'desc']],  // Sort by CA and KY suggested qty descending
        pageLength: 50,
        scrollY: 'calc(100vh - 400px)',
        scrollX: true,
        scrollCollapse: true,
        fixedHeader: true,
        dom: 'Bfrtip',
        buttons: ['colvis', 'excel', 'csv']
    });
}


// Render functions
function renderSuggestedQty(data, type, row) {
    if (type === 'display') {
        if (data === 0) {
            return '<span class="order-zero">0</span>';
        }
        return `<span class="order-suggested">${data.toLocaleString()}</span>`;
    }
    return data;
}

function renderConfirmedQty(data, type, row, meta) {
    const warehouse = meta.col < 13 ? 'burnaby' : 'kentucky';
    const isLocked = row[warehouse].is_locked || false;
    const confirmedQty = row[warehouse].confirmed_qty || data.suggested_order_qty;

    if (isLocked) {
        return `<span class="order-locked">${confirmedQty.toLocaleString()}</span>`;
    } else {
        return `<input type="number" class="editable-qty"
                       value="${confirmedQty}"
                       data-sku="${row.sku_id}"
                       data-warehouse="${warehouse}"
                       min="0" step="25">`;
    }
}

function renderLockButton(data, type, row, meta) {
    const warehouse = meta.col < 13 ? 'burnaby' : 'kentucky';
    const isLocked = row[warehouse].is_locked || false;

    if (isLocked) {
        return `<button class="btn btn-sm btn-success lock-btn locked"
                        data-sku="${row.sku_id}"
                        data-warehouse="${warehouse}">
                    <i class="fas fa-lock"></i>
                </button>`;
    } else {
        return `<button class="btn btn-sm btn-outline-secondary lock-btn"
                        data-sku="${row.sku_id}"
                        data-warehouse="${warehouse}">
                    <i class="fas fa-unlock"></i>
                </button>`;
    }
}

function renderStatusBadge(data, type, row) {
    if (type === 'display') {
        if (data === 'Active') {
            return '<span class="badge status-active">Active</span>';
        } else if (data === 'Death Row') {
            return '<span class="badge status-death-row">Death Row</span>';
        } else if (data === 'Discontinued') {
            return '<span class="badge status-discontinued">Discontinued</span>';
        }
    }
    return data;
}

function renderReliabilityScore(data, type, row) {
    if (type === 'display') {
        let className = '';
        if (data >= 90) className = 'reliability-excellent';
        else if (data >= 70) className = 'reliability-good';
        else className = 'reliability-poor';

        return `<span class="${className}">${data}</span>`;
    }
    return data;
}


// Lock/unlock functionality
$(document).on('click', '.lock-btn', async function() {
    const btn = $(this);
    const sku_id = btn.data('sku');
    const warehouse = btn.data('warehouse');
    const isCurrentlyLocked = btn.hasClass('locked');

    // Get confirmed quantity from input or span
    let confirmed_qty;
    if (isCurrentlyLocked) {
        // Already locked, toggle to unlock
        confirmed_qty = parseInt(btn.closest('tr')
            .find(`span.order-locked[data-warehouse="${warehouse}"]`).text().replace(',', ''));
    } else {
        // Not locked, get from input
        confirmed_qty = parseInt(btn.closest('tr')
            .find(`input.editable-qty[data-sku="${sku_id}"][data-warehouse="${warehouse}"]`).val());
    }

    try {
        const response = await fetch('/api/supplier-orders/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sku_id: sku_id,
                warehouse: warehouse,
                confirmed_qty: confirmed_qty,
                is_locked: !isCurrentlyLocked
            })
        });

        const result = await response.json();

        if (result.success) {
            // Refresh the table to show updated lock state
            ordersTable.ajax.reload(null, false);

            showToast('success', `Order ${isCurrentlyLocked ? 'unlocked' : 'locked'} for ${sku_id} (${warehouse})`);
        } else {
            showToast('error', result.message);
        }
    } catch (error) {
        console.error('Lock toggle failed:', error);
        showToast('error', 'Failed to update lock state');
    }
});


// Export to Excel
async function exportToExcel() {
    const filters = {
        supplier: $('#filter-supplier').val(),
        status: $('#filter-status').val(),
        abc_class: $('#filter-abc').val(),
        xyz_class: $('#filter-xyz').val(),
        warehouse: $('#filter-warehouse').val(),
        include_locked_only: $('#filter-locked-only').is(':checked')
    };

    try {
        const response = await fetch('/api/supplier-orders/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ format: 'excel', ...filters })
        });

        const result = await response.json();

        if (result.success) {
            // Trigger download
            window.location.href = result.file_url;
            showToast('success', `Exported ${result.records_exported} records`);
        }
    } catch (error) {
        console.error('Export failed:', error);
        showToast('error', 'Export failed');
    }
}


// SKU details modal
async function showSkuDetails(sku_id) {
    try {
        const response = await fetch(`/api/supplier-orders/sku-details/${sku_id}`);
        const result = await response.json();

        if (result.success) {
            const data = result.data;

            // Populate modal fields
            $('#modal-sku-id').text(data.sku_info.sku_id);
            $('#modal-description').text(data.sku_info.description);
            // ... populate all other fields

            // Draw forecast chart
            drawForecastChart(data.burnaby_analysis['12_month_forecast'],
                            data.kentucky_analysis['12_month_forecast']);

            // Draw sales history charts
            drawSalesHistoryChart('ca', data.sales_history.burnaby);
            drawSalesHistoryChart('ky', data.sales_history.kentucky);

            // Show modal
            $('#skuDetailsModal').modal('show');
        }
    } catch (error) {
        console.error('Failed to load SKU details:', error);
        showToast('error', 'Failed to load SKU details');
    }
}


// Chart drawing functions
function drawForecastChart(burnabyForecast, kentuckyForecast) {
    const ctx = document.getElementById('forecast-chart').getContext('2d');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Month 1', 'Month 2', 'Month 3', 'Month 4', 'Month 5', 'Month 6',
                    'Month 7', 'Month 8', 'Month 9', 'Month 10', 'Month 11', 'Month 12'],
            datasets: [
                {
                    label: 'Burnaby Forecast',
                    data: burnabyForecast.monthly_breakdown.map(m => m.burnaby_qty),
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1
                },
                {
                    label: 'Kentucky Forecast',
                    data: kentuckyForecast.monthly_breakdown.map(m => m.kentucky_qty),
                    borderColor: 'rgb(255, 99, 132)',
                    backgroundColor: 'rgba(255, 99, 132, 0.2)',
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: '12-Month Demand Forecast'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Quantity'
                    }
                }
            }
        }
    });
}
```

---

## 4. Implementation Phases

### Phase 1: Database & Backend (Week 1)

**Tasks**:
1. Create `supplier_order_confirmations` table
2. Implement order calculation algorithm in `backend/calculations.py`:
   - `calculate_order_quantity(sku_id, warehouse, supplier)`
   - `calculate_safety_stock(sku_id, avg_monthly_demand, lead_time_days, lead_time_variability)`
   - `get_forecasted_demand(sku_id, warehouse, lead_time_days)`
   - `round_to_supplier_multiple(sku_id, quantity)`
3. Create API endpoints in `backend/supplier_ordering_api.py`:
   - `GET /api/supplier-orders/recommendations`
   - `POST /api/supplier-orders/confirm`
   - `GET /api/supplier-orders/sku-details/{sku_id}`
   - `POST /api/supplier-orders/export`
4. Add comprehensive docstrings following project standards
5. Write unit tests for calculation logic

**Deliverables**:
- Working API endpoints returning test data
- Calculation accuracy validated with sample SKUs
- API documentation in Swagger/OpenAPI format

### Phase 2: Frontend UI (Week 2)

**Tasks**:
1. Create `frontend/supplier-ordering.html` page structure
2. Implement `frontend/supplier-ordering.js` with DataTables
3. Build SKU details modal with tabbed interface
4. Add Chart.js visualizations for forecasts and history
5. Implement lock/unlock functionality
6. Add filters and search capabilities
7. Style with Bootstrap and custom CSS

**Deliverables**:
- Functional UI displaying order recommendations
- Interactive table with sorting, filtering, searching
- Working lock/unlock mechanism
- Detailed SKU modal with all tabs functional

### Phase 3: Export & Integration (Week 3)

**Tasks**:
1. Implement Excel export with formatted columns
2. Add CSV export option
3. Create export templates with formulas for PO creation
4. Add summary metrics cards
5. Implement bulk lock/unlock operations
6. Add calculation transparency tooltips
7. Create user help documentation

**Deliverables**:
- Excel exports with proper formatting
- CSV exports for system integration
- Complete user documentation
- Help tooltips and guidance

### Phase 4: Testing & Refinement (Week 4)

**Tasks**:
1. Playwright testing of full user workflows
2. Test with full 4000+ SKU dataset
3. Performance optimization (target: sub-5-second load)
4. Edge case testing (discontinued SKUs, zero demand, etc.)
5. User acceptance testing (UAT)
6. Bug fixes and refinements
7. Final documentation updates

**Deliverables**:
- Comprehensive test coverage
- Performance benchmarks met
- All edge cases handled gracefully
- User-approved functionality

---

## 5. Key Data Flow

```
User Opens Supplier Ordering Page
          |
          v
Frontend requests: GET /api/supplier-orders/recommendations
          |
          v
Backend Process:
  1. Get all active forecasts from latest forecast_run
  2. For each SKU:
     a. Get forecast_details for both warehouses
     b. Get current_inventory for both warehouses
     c. Get pending_inventory for both warehouses
     d. Get supplier_lead_times for the supplier
     e. Calculate order quantity for CA (using calculate_order_quantity)
     f. Calculate order quantity for KY (using calculate_order_quantity)
     g. Retrieve any existing confirmed quantities
  3. Compile results into JSON
          |
          v
Frontend renders DataTable with:
  - SKU information columns
  - CA ordering columns (current, pending, suggested, confirmed, lock)
  - KY ordering columns (current, pending, suggested, confirmed, lock)
  - Supplier data columns
          |
          v
User interactions:
  - Filter by supplier/status/ABC-XYZ
  - Search for specific SKUs
  - Click SKU to see details modal
  - Adjust confirmed quantities
  - Lock/unlock quantities
  - Export to Excel/CSV
          |
          v
On Lock/Unlock:
  POST /api/supplier-orders/confirm
  Backend saves to supplier_order_confirmations table
  Frontend refreshes table row
          |
          v
On Export:
  POST /api/supplier-orders/export
  Backend generates Excel/CSV file
  Returns download link
  Frontend triggers download
```

---

## 6. Database Queries

**Key Queries for Performance**:

```sql
-- Main query to get all order recommendations
-- Joins multiple tables efficiently using indexed columns

SELECT
    s.sku_id,
    s.description,
    s.supplier,
    s.category,
    s.abc_code,
    s.xyz_code,
    s.status,

    -- Burnaby data
    ic.burnaby_qty AS burnaby_current,
    COALESCE(pq.burnaby_pending, 0) AS burnaby_pending,
    fd_burnaby.avg_monthly_qty AS burnaby_avg_demand,
    fd_burnaby.month_1_qty, fd_burnaby.month_2_qty, /* ... months 3-12 */
    fd_burnaby.confidence_score AS burnaby_confidence,
    fd_burnaby.method_used AS burnaby_method,

    -- Kentucky data
    ic.kentucky_qty AS kentucky_current,
    COALESCE(pq.kentucky_pending, 0) AS kentucky_pending,
    fd_kentucky.avg_monthly_qty AS kentucky_avg_demand,
    fd_kentucky.month_1_qty, fd_kentucky.month_2_qty, /* ... months 3-12 */
    fd_kentucky.confidence_score AS kentucky_confidence,
    fd_kentucky.method_used AS kentucky_method,

    -- Supplier lead time data
    slt_burnaby.p95_lead_time AS burnaby_lead_time,
    slt_burnaby.coefficient_variation AS burnaby_lead_cv,
    slt_burnaby.reliability_score AS burnaby_reliability,
    slt_kentucky.p95_lead_time AS kentucky_lead_time,
    slt_kentucky.coefficient_variation AS kentucky_lead_cv,
    slt_kentucky.reliability_score AS kentucky_reliability,

    -- Existing confirmations (if any)
    soc_burnaby.confirmed_qty AS burnaby_confirmed,
    soc_burnaby.is_locked AS burnaby_locked,
    soc_kentucky.confirmed_qty AS kentucky_confirmed,
    soc_kentucky.is_locked AS kentucky_locked

FROM skus s

-- Current inventory
LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id

-- Pending quantities aggregated
LEFT JOIN v_pending_quantities pq ON s.sku_id = pq.sku_id

-- Forecast details for Burnaby
LEFT JOIN forecast_details fd_burnaby ON s.sku_id = fd_burnaby.sku_id
    AND fd_burnaby.warehouse = 'burnaby'
    AND fd_burnaby.forecast_run_id = (SELECT id FROM forecast_runs
                                       WHERE status = 'completed'
                                       ORDER BY forecast_date DESC LIMIT 1)

-- Forecast details for Kentucky
LEFT JOIN forecast_details fd_kentucky ON s.sku_id = fd_kentucky.sku_id
    AND fd_kentucky.warehouse = 'kentucky'
    AND fd_kentucky.forecast_run_id = (SELECT id FROM forecast_runs
                                        WHERE status = 'completed'
                                        ORDER BY forecast_date DESC LIMIT 1)

-- Supplier lead times for Burnaby
LEFT JOIN supplier_lead_times slt_burnaby ON s.supplier = slt_burnaby.supplier
    AND slt_burnaby.destination = 'burnaby'

-- Supplier lead times for Kentucky
LEFT JOIN supplier_lead_times slt_kentucky ON s.supplier = slt_kentucky.supplier
    AND slt_kentucky.destination = 'kentucky'

-- Existing order confirmations for Burnaby
LEFT JOIN supplier_order_confirmations soc_burnaby ON s.sku_id = soc_burnaby.sku_id
    AND soc_burnaby.warehouse = 'burnaby'
    AND soc_burnaby.order_date = CURDATE()  -- Today's order session

-- Existing order confirmations for Kentucky
LEFT JOIN supplier_order_confirmations soc_kentucky ON s.sku_id = soc_kentucky.sku_id
    AND soc_kentucky.warehouse = 'kentucky'
    AND soc_kentucky.order_date = CURDATE()

WHERE s.status IN ('Active', 'Death Row', 'Discontinued')

ORDER BY
    s.status = 'Active' DESC,  -- Active first
    s.abc_code ASC,            -- A before B before C
    s.sku_id ASC;
```

**Indexes Required** (add to schema.sql):

```sql
-- Supplier order confirmations indexes
ALTER TABLE supplier_order_confirmations
  ADD INDEX idx_sku_warehouse_date (sku_id, warehouse, order_date),
  ADD INDEX idx_locked_orders (is_locked, order_date),
  ADD INDEX idx_order_date (order_date);

-- Optimize forecast_details queries
ALTER TABLE forecast_details
  ADD INDEX idx_warehouse_run (warehouse, forecast_run_id, sku_id);

-- Optimize supplier_lead_times queries
ALTER TABLE supplier_lead_times
  ADD INDEX idx_supplier_destination (supplier, destination);
```

---

## 7. Additional Features from Schema Analysis

Based on schema review, these additional enhancements should be considered:

### 7.1 Seasonal Patterns Integration

**Tables**: `seasonal_factors`, `seasonal_patterns`, `seasonal_patterns_summary`

**Enhancement**: Show seasonal indicators in the UI
- If a SKU has seasonal patterns, display a badge (e.g., "Seasonal: Q4 Peak")
- Adjust safety stock calculations during peak seasons
- Warn user if ordering during off-season

**Implementation**:
```python
def adjust_for_seasonality(sku_id, safety_stock, current_month):
    """
    Adjust safety stock if SKU has seasonal patterns.
    """
    seasonal_data = get_seasonal_pattern(sku_id)

    if seasonal_data:
        # Get factor for current month
        current_factor = seasonal_data[f'month_{current_month}_factor']

        # If current month is peak season (factor > 1.2), increase safety stock
        if current_factor > 1.2:
            safety_stock = safety_stock * current_factor

    return math.ceil(safety_stock)
```

### 7.2 Stockout Pattern Awareness

**Tables**: `stockout_patterns`, `v_current_stockouts_enhanced`

**Enhancement**: Highlight SKUs with recent stockout patterns
- Show "Stockout Risk" badge for SKUs with stockout_pattern_detected = 1
- Increase urgency/priority for these items
- Display stockout history in SKU details modal

**Implementation**:
```python
def calculate_priority_score(sku_id, order_qty, current_position):
    """
    Calculate priority score for ordering.
    Higher score = more urgent.
    """
    priority = 50  # Base priority

    # Check stockout patterns
    stockout_risk = check_stockout_pattern(sku_id)
    if stockout_risk:
        priority += 30  # High boost for stockout risk

    # Check current position
    if current_position <= 0:
        priority += 40  # Critical - out of stock

    # ABC class priority
    abc_class = get_abc_class(sku_id)
    if abc_class == 'A':
        priority += 20
    elif abc_class == 'B':
        priority += 10

    return priority
```

### 7.3 Pending Orders Analysis

**Tables**: `pending_inventory`, `v_pending_orders_analysis`, `v_pending_orders_aggregated`

**Enhancement**: Show pending order details in modal
- Display all pending orders with arrival dates
- Show if orders are overdue (is_overdue flag)
- Calculate days_until_arrival
- Factor into order quantity calculations

**Implementation**: Already incorporated in main calculation algorithm.

### 7.4 Revenue Analysis

**Tables**: `v_revenue_analysis`, `v_revenue_dashboard`

**Enhancement**: Add revenue-based metrics
- Show total order value (CA + KY)
- Display revenue impact per supplier
- Prioritize high-revenue SKUs

**Implementation**:
```javascript
// Calculate order value in frontend
function calculateOrderValue(confirmedQty, avgSellingPrice) {
    return confirmedQty * avgSellingPrice;
}

// Update summary cards
function updateSummaryCards() {
    let totalCAValue = 0;
    let totalKYValue = 0;

    ordersTable.rows().every(function() {
        const data = this.data();
        const avgPrice = data.avg_selling_price || 0;

        totalCAValue += (data.burnaby.confirmed_qty || 0) * avgPrice;
        totalKYValue += (data.kentucky.confirmed_qty || 0) * avgPrice;
    });

    $('#metric-ca-value').text('$' + totalCAValue.toLocaleString());
    $('#metric-ky-value').text('$' + totalKYValue.toLocaleString());
}
```

---

## 8. User Documentation

### 8.1 Quick Start Guide

**Accessing Supplier Ordering**:
1. Navigate to main menu → "Supplier Ordering"
2. System automatically loads latest forecast data
3. View calculated order recommendations for all SKUs

**Understanding the Table**:
- **CA Columns**: Burnaby (Canada) warehouse data and orders
- **KY Columns**: Kentucky (USA) warehouse data and orders
- **Suggested Qty**: System-calculated recommended order quantity
- **Confirmed Qty**: Your finalized order quantity (editable)
- **Lock Icon**: Lock to prevent accidental changes

**Making Order Decisions**:
1. Review suggested quantities for both warehouses
2. Click SKU ID to see detailed breakdown
3. Adjust confirmed quantities if needed
4. Click lock icon to finalize your decision
5. Repeat for all SKUs requiring orders
6. Export to Excel when ready to place orders

### 8.2 Understanding Calculations

**Order Quantity Formula**:
```
Order Qty = (Demand during Lead Time + Safety Stock) - Current Position
Where:
  Current Position = Current Inventory + Pending Orders
  Demand during Lead Time = Avg Monthly Demand × (Lead Time Days ÷ 30)
  Safety Stock = Based on ABC-XYZ class and lead time variability
```

**Safety Stock Levels**:
- **A-class items**: 95% service level (higher safety stock)
- **B-class items**: 90% service level (moderate safety stock)
- **C-class items**: 80% service level (lower safety stock)
- **Adjustments**: Increased for volatile (Z) items and unreliable suppliers

**Why Zero Order Recommended?**:
- Current inventory + pending orders already exceed reorder point
- System indicates you're well-stocked for the forecast period

**Warehouse Independence**:
- Each warehouse calculated separately
- Different lead times may apply per destination
- Order to one, both, or neither warehouse independently

### 8.3 Best Practices

**Regular Review Cycle**:
- Review orders weekly or bi-weekly
- Lock quantities only when ready to submit PO
- Clear locks after orders placed to reset for next cycle

**Handling Special Cases**:
- **Death Row SKUs**: System shows warning; order conservatively
- **Discontinued SKUs**: Usually shows zero; override only if final sales expected
- **New SKUs**: Limited history; verify forecast in details modal
- **Seasonal Items**: Check 12-month forecast for upcoming peaks

**Supplier Reliability**:
- Green scores (90-100): Highly reliable, safe to use default lead time
- Yellow scores (70-89): Moderate reliability, safety stock increased
- Red scores (<70): Unreliable, consider alternative suppliers or higher safety stock

**Export Workflow**:
1. Lock all confirmed quantities
2. Export to Excel (grouped by supplier)
3. Review totals and adjust if needed
4. Submit POs to suppliers
5. After submission, unlock all to prepare for next cycle

---

## 9. Success Metrics

### 9.1 System Performance
- Page load time: < 5 seconds with 4000+ SKUs
- Calculation accuracy: 95%+ compared to manual calculations
- Export generation: < 10 seconds for full dataset

### 9.2 Business Impact
- Order planning time: Reduce from 4+ hours to under 1 hour
- Stockout reduction: 30% fewer stockouts for A-class items
- Overstock reduction: 20% reduction in excess inventory
- User satisfaction: 4.0+ out of 5.0 rating

### 9.3 Adoption Metrics
- User adoption rate: 90%+ within 3 months
- Lock-in rate: 70%+ of suggested quantities accepted
- Export usage: Used for 90%+ of supplier orders

---

## 10. Future Enhancements (Post-MVP)

### 10.1 Automatic PO Generation
- Generate formatted POs directly from locked quantities
- Email POs to suppliers automatically
- Track PO status and confirmations

### 10.2 Supplier Integration
- API connections to supplier systems
- Automatic order submission
- Real-time inventory availability checks

### 10.3 Budget Constraints
- Set monthly budget limits per supplier
- Optimize order quantities within budget
- Prioritize A-class items when budget limited

### 10.4 Multi-Period Planning
- 3-month rolling order forecast
- Annual purchase planning
- Volume discount optimization

### 10.5 Advanced Analytics
- Supplier performance comparison dashboard
- Cost analysis (total landed cost calculations)
- Fill rate tracking by supplier
- Lead time trend analysis

---

## 11. Questions & Clarifications Needed

Before implementation begins, clarify:

1. **SKU-Supplier Relationship**: Can one SKU be ordered from multiple suppliers? If yes, how to handle in UI?

2. **Order Approval Workflow**: Does locked quantity trigger any approval process, or is it just for tracking?

3. **Historical Order Tracking**: Should we track past orders to compare suggested vs actual over time?

4. **Currency Handling**: Are all prices in USD, or do we need CAD/USD conversion?

5. **Supplier MOQ Data**: Where is minimum order quantity per supplier stored, or should we add it?

6. **Master Carton Sizes**: Should rounding consider master carton sizes (like transfer planning)?

7. **Budget Integration**: Any budget approval system to integrate with?

8. **Notification System**: Should system send alerts for urgent orders or low stock situations?

9. **User Roles**: Different access levels (viewer vs editor vs approver)?

10. **Integration with Existing Systems**: Any ERP or accounting system integration required?

---

## Appendix A: Comparison with Transfer Planning

| Feature | Transfer Planning | Supplier Ordering |
|---------|------------------|-------------------|
| **Purpose** | Move inventory CA → KY | Order from suppliers to CA or KY |
| **Calculation Base** | Current inventory imbalance | Reorder point model |
| **Warehouses** | Single flow (CA to KY) | Independent (CA and KY separately) |
| **Data Source** | Current inventory + sales | Forecast + lead times + safety stock |
| **Timeframe** | Short-term (weeks) | Medium-term (months) |
| **Complexity** | Moderate | High |
| **Lock Functionality** | Single column | Dual columns (CA & KY) |
| **Export** | Transfer orders | Supplier POs |
| **Lead Time** | Fixed 3 weeks | Varies by supplier & destination |
| **Safety Stock** | Not explicitly calculated | Central to calculation |
| **Forecast Usage** | Indirect (via demand) | Direct (12-month projections) |

---

## Appendix B: Sample Calculation Walkthrough

**Example SKU**: UB-YTX14-BS (12V Battery)

**Scenario**: Calculate Kentucky order quantity

**Input Data**:
- Supplier: Universal Battery
- Current KY Inventory: 12 units
- Pending KY Orders: 0 units
- Avg Monthly Demand (KY): 48.3 units
- Supplier Lead Time (to KY): 60 days (P95)
- Lead Time CV: 0.15 (15% variability - good reliability)
- ABC Class: A (high value)
- XYZ Class: X (stable demand)

**Step-by-Step Calculation**:

1. **Current Position**:
   ```
   Current Position = Current Inventory + Pending Orders
                    = 12 + 0 = 12 units
   ```

2. **Lead Time in Months**:
   ```
   Lead Time Months = 60 days ÷ 30 days/month = 2.0 months
   ```

3. **Demand During Lead Time**:
   ```
   Demand During Lead Time = Avg Monthly Demand × Lead Time Months
                           = 48.3 × 2.0 = 96.6 units
   ```

4. **Safety Stock Calculation**:
   ```
   Service Level Factor (A-class): 1.65 (95% service level)
   Variability Factor (X-class): 1.0 (stable demand)
   Reliability Adjustment (CV 15%): 1.0 (good supplier)
   Lead Time Factor: √(2.0) = 1.414

   Safety Stock = 1.65 × 1.0 × 1.0 × 48.3 × 1.414
                = 112.7 units

   Apply minimum for A-class: max(112.7, 48.3 × 0.5) = 112.7 units
   Rounded up: 113 units
   ```

5. **Reorder Point**:
   ```
   Reorder Point = Demand During Lead Time + Safety Stock
                 = 96.6 + 113 = 209.6
   Rounded: 210 units
   ```

6. **Order Quantity**:
   ```
   Order Qty = Reorder Point - Current Position
             = 210 - 12 = 198 units
   ```

7. **Rounding to Multiple** (batteries round to 50s):
   ```
   Rounded Order Qty = round_up_to_50(198) = 200 units
   ```

**Final Recommendation**: **Order 200 units for Kentucky**

**Coverage After Order**:
```
New Position = Current + Order = 12 + 200 = 212 units
Coverage Months = 212 ÷ 48.3 = 4.4 months
```

**Displayed to User**:
- Current Inventory: 12
- Pending Orders: 0
- Current Position: 12
- Suggested Order: 200
- Lead Time: 60 days
- Coverage After Order: 4.4 months
- Safety Stock: 113 units
- Reorder Point: 210 units

---

## Appendix C: File Structure

```
warehouse-transfer/
├── backend/
│   ├── supplier_ordering_api.py     # NEW: API endpoints
│   ├── calculations.py              # MODIFY: Add order calculation functions
│   ├── forecasting_api.py           # EXISTS: May reuse some functions
│   └── main.py                      # MODIFY: Register new routes
│
├── frontend/
│   ├── supplier-ordering.html       # NEW: Main page
│   ├── supplier-ordering.js         # NEW: JavaScript logic
│   └── css/
│       └── supplier-ordering.css    # NEW: Custom styles
│
├── database/
│   ├── schema.sql                   # MODIFY: Add supplier_order_confirmations table
│   └── migrations/
│       └── add_supplier_ordering.sql # NEW: Migration script
│
├── docs/
│   ├── SUPPLIER_ORDERING_PLAN.md    # THIS FILE
│   ├── SUPPLIER_ORDERING_USER_GUIDE.md  # NEW: User documentation
│   └── API_Documentation_v3.md      # MODIFY: Add new endpoints
│
└── tests/
    ├── test_supplier_ordering_api.py    # NEW: API tests
    └── test_order_calculations.py        # NEW: Calculation tests
```

---

## Summary

This comprehensive plan provides a detailed blueprint for implementing a sophisticated Supplier Ordering system that:

1. **Uses advanced inventory theory** (reorder point model with safety stock)
2. **Leverages existing forecasting infrastructure** (12-month projections)
3. **Accounts for supplier variability** (lead time statistics and reliability)
4. **Provides complete transparency** (detailed calculations shown to user)
5. **Maintains warehouse independence** (CA and KY calculated separately)
6. **Follows project standards** (documentation, testing, performance)

The system will dramatically reduce ordering planning time while improving inventory optimization across both warehouses.
