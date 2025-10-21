# **Product Requirements Document (PRD)**
## **12-Month Sales Forecasting System**
*Version 1.0 - December 2024*

---

## **1. Executive Summary**

### **Product Overview**
A comprehensive 12-month sales forecasting system that leverages existing warehouse transfer data infrastructure to predict future demand, optimize inventory planning, and improve business decision-making across both Burnaby and Kentucky warehouses.

### **Key Objectives**
- Generate accurate 12-month sales forecasts by SKU and warehouse
- Leverage existing seasonal patterns and stockout corrections
- Provide visual dashboards for forecast analysis and decision-making
- Enable forecast accuracy tracking and continuous improvement
- Support both quantity and revenue forecasting

### **Integration Context**
This system complements the existing warehouse transfer tool and will provide foundational data for the future supplier ordering system.

---

## **2. Current State Analysis**

### **Existing Data Assets (From SQL Schema)**
✅ **Already Available:**
- Monthly sales history with revenue (`monthly_sales` table with `burnaby_revenue`, `kentucky_revenue`)
- Stockout tracking and corrected demand calculations
- ABC/XYZ classification system
- Seasonal pattern detection (`seasonal_factors`, `seasonal_patterns_summary`)
- Forecast accuracy tracking infrastructure
- Comprehensive performance views and analytics

### **Current Gaps**
- No forward-looking 12-month projections
- No consolidated forecast dashboard
- Manual forecast generation process
- No confidence intervals on predictions
- Limited integration between seasonal patterns and forecasting

---

## **3. Solution Architecture**

### **3.1 Data Flow**
```
Existing Data Sources → Forecast Engine → Database Storage → UI/Export
       ↓                      ↓                ↓              ↓
  monthly_sales      Calculate Base      forecast_runs    Dashboard
  seasonal_factors   Apply Patterns       forecast_details Reports
  sku_demand_stats   Growth Adjust        (new tables)     API
```

### **3.2 Core Components**

#### **Forecast Engine**
- Base demand calculation with existing corrected demand
- Seasonal adjustment using existing `seasonal_factors`
- Growth trend analysis
- ABC/XYZ-specific methods
- Confidence scoring

#### **Data Storage**
- Leverage existing tables
- Add forecast-specific tables (detailed below)
- Maintain forecast history for accuracy tracking

#### **User Interface**
- Executive dashboard
- SKU-level detail views
- Forecast vs actual tracking
- Export capabilities

---

## **4. Functional Requirements**

### **4.1 Forecast Generation**

#### **Core Calculation Flow**
```python
def generate_12_month_forecast(sku_id, warehouse):
    """
    Leverage existing data structure for forecasting
    """
    # 1. Get corrected historical demand (already calculated)
    base_demand = get_from_sku_demand_stats(sku_id, warehouse)
    
    # 2. Apply seasonal factors (already in database)
    seasonal_factors = get_from_seasonal_factors(sku_id, warehouse)
    
    # 3. Calculate growth trend
    growth_rate = calculate_growth_trend(sku_id, warehouse)
    
    # 4. Generate monthly forecasts
    for month in next_12_months:
        forecast[month] = base_demand * seasonal_factors[month] * (1 + growth_rate)
    
    # 5. Apply confidence based on data quality
    confidence = calculate_confidence(
        data_quality_score,  # From sku_demand_stats
        pattern_strength,    # From seasonal_patterns_summary
        coefficient_variation # From sku_demand_stats
    )
    
    return forecast
```

#### **ABC/XYZ Specific Methods**
```python
# Using existing classification from skus table
forecast_methods = {
    'AX': {'method': 'demand_6mo_weighted', 'confidence': 0.90},
    'AY': {'method': 'demand_3mo_weighted', 'confidence': 0.80},
    'AZ': {'method': 'demand_3mo_simple', 'confidence': 0.60},
    'BX': {'method': 'demand_6mo_simple', 'confidence': 0.85},
    'BY': {'method': 'demand_3mo_weighted', 'confidence': 0.70},
    'BZ': {'method': 'demand_3mo_simple', 'confidence': 0.50},
    'CX': {'method': 'last_3_months_avg', 'confidence': 0.70},
    'CY': {'method': 'last_3_months_avg', 'confidence': 0.60},
    'CZ': {'method': 'last_month_only', 'confidence': 0.40}
}
```

### **4.2 Database Schema Additions**

```sql
-- New forecast master table
CREATE TABLE forecast_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    forecast_name VARCHAR(100),
    forecast_date DATE NOT NULL,
    forecast_type ENUM('monthly', 'quarterly', 'annual') DEFAULT 'monthly',
    status ENUM('draft', 'active', 'archived') DEFAULT 'draft',
    growth_assumption DECIMAL(5,2) DEFAULT 0.00,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by VARCHAR(100),
    approved_at TIMESTAMP NULL,
    notes TEXT,
    INDEX idx_forecast_status (status),
    INDEX idx_forecast_date (forecast_date)
);

-- Detailed forecast by SKU
CREATE TABLE forecast_details (
    id INT AUTO_INCREMENT PRIMARY KEY,
    forecast_run_id INT NOT NULL,
    sku_id VARCHAR(50) NOT NULL,
    warehouse ENUM('burnaby', 'kentucky', 'combined') NOT NULL,
    
    -- Monthly quantity forecasts
    month_1_qty INT DEFAULT 0,
    month_2_qty INT DEFAULT 0,
    month_3_qty INT DEFAULT 0,
    month_4_qty INT DEFAULT 0,
    month_5_qty INT DEFAULT 0,
    month_6_qty INT DEFAULT 0,
    month_7_qty INT DEFAULT 0,
    month_8_qty INT DEFAULT 0,
    month_9_qty INT DEFAULT 0,
    month_10_qty INT DEFAULT 0,
    month_11_qty INT DEFAULT 0,
    month_12_qty INT DEFAULT 0,
    
    -- Monthly revenue forecasts
    month_1_rev DECIMAL(12,2) DEFAULT 0.00,
    month_2_rev DECIMAL(12,2) DEFAULT 0.00,
    month_3_rev DECIMAL(12,2) DEFAULT 0.00,
    month_4_rev DECIMAL(12,2) DEFAULT 0.00,
    month_5_rev DECIMAL(12,2) DEFAULT 0.00,
    month_6_rev DECIMAL(12,2) DEFAULT 0.00,
    month_7_rev DECIMAL(12,2) DEFAULT 0.00,
    month_8_rev DECIMAL(12,2) DEFAULT 0.00,
    month_9_rev DECIMAL(12,2) DEFAULT 0.00,
    month_10_rev DECIMAL(12,2) DEFAULT 0.00,
    month_11_rev DECIMAL(12,2) DEFAULT 0.00,
    month_12_rev DECIMAL(12,2) DEFAULT 0.00,
    
    -- Summary statistics
    total_qty_forecast INT GENERATED ALWAYS AS (
        month_1_qty + month_2_qty + month_3_qty + month_4_qty + 
        month_5_qty + month_6_qty + month_7_qty + month_8_qty + 
        month_9_qty + month_10_qty + month_11_qty + month_12_qty
    ) STORED,
    
    total_rev_forecast DECIMAL(14,2) GENERATED ALWAYS AS (
        month_1_rev + month_2_rev + month_3_rev + month_4_rev + 
        month_5_rev + month_6_rev + month_7_rev + month_8_rev + 
        month_9_rev + month_10_rev + month_11_rev + month_12_rev
    ) STORED,
    
    avg_monthly_qty DECIMAL(10,2) GENERATED ALWAYS AS (total_qty_forecast / 12) STORED,
    avg_monthly_rev DECIMAL(12,2) GENERATED ALWAYS AS (total_rev_forecast / 12) STORED,
    
    -- Metadata
    base_demand_used DECIMAL(10,2),
    seasonal_pattern_applied VARCHAR(20),
    growth_rate_applied DECIMAL(5,2),
    confidence_score DECIMAL(3,2),
    method_used VARCHAR(50),
    manual_override BOOLEAN DEFAULT FALSE,
    override_reason TEXT,
    
    FOREIGN KEY (forecast_run_id) REFERENCES forecast_runs(id),
    FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
    INDEX idx_forecast_sku (forecast_run_id, sku_id, warehouse)
);

-- Forecast adjustments log
CREATE TABLE forecast_adjustments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    forecast_run_id INT NOT NULL,
    sku_id VARCHAR(50) NOT NULL,
    adjustment_type ENUM('manual', 'event', 'promotion', 'phase_out'),
    original_value DECIMAL(10,2),
    adjusted_value DECIMAL(10,2),
    adjustment_reason TEXT,
    adjusted_by VARCHAR(100),
    adjusted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (forecast_run_id) REFERENCES forecast_runs(id),
    FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
);
```

### **4.3 User Interface Requirements**

#### **Main Dashboard**
```
┌─────────────────────────────────────────────────────┐
│ 12-MONTH SALES FORECAST DASHBOARD                    │
├─────────────────────────────────────────────────────┤
│ Active Forecast: December 2024 (Generated: Dec 5)    │
│ [Generate New] [View History] [Export]               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ KEY METRICS                                          │
├──────────────┬──────────────┬──────────────┬────────┤
│ 12M Forecast │ YoY Growth   │ Confidence   │ At Risk│
│ $4.2M / 45K  │ +12.3%       │ 78%          │ 23 SKUs│
└──────────────┴──────────────┴──────────────┴────────┘

[Forecast vs History Chart - Line graph with confidence bands]
[Category Breakdown - Stacked bar chart by month]
[ABC/XYZ Performance Matrix - Heat map]
```

#### **Forecast Generation Wizard**
```
Step 1: Select Parameters
┌─────────────────────────────────────────────────────┐
│ FORECAST PARAMETERS                                  │
├─────────────────────────────────────────────────────┤
│ Forecast Name: [January 2025 Forecast]               │
│ Growth Assumption: [10%] ▼                           │
│ Include Stockout Correction: ☑                       │
│ Use Seasonal Patterns: ☑                             │
│ Exclude Discontinued: ☑                              │
│                                                       │
│ Advanced Options:                                    │
│ - Confidence Threshold: [60%]                        │
│ - Minimum History Required: [6 months]               │
│ - Growth Cap: [50%]                                  │
└─────────────────────────────────────────────────────┘
[Cancel] [Next →]

Step 2: Review & Adjust
┌─────────────────────────────────────────────────────┐
│ FORECAST PREVIEW                                     │
├─────────────────────────────────────────────────────┤
│ Total SKUs: 2,847                                    │
│ Forecasted: 2,645                                    │
│ Insufficient Data: 202                               │
│                                                       │
│ Top Growth SKUs:                                     │
│ • UB-YTX14-BS: +45% (viral status detected)         │
│ • CHG-001: +38% (seasonal peak expected)            │
│                                                       │
│ Manual Adjustments:                                  │
│ [Search SKU] [Bulk Adjust Category]                  │
└─────────────────────────────────────────────────────┘
[← Back] [Generate Forecast]
```

#### **SKU Detail View**
```
SKU: UB-YTX14-BS - 12V Battery
ABC: A | XYZ: Y | Status: Active | Pattern: Year-round

┌─────────────────────────────────────────────────────┐
│ FORECAST BREAKDOWN                                   │
├─────────────────────────────────────────────────────┤
│ Base Demand: 950 units/month (6mo weighted avg)      │
│ Seasonal Adjustment: Applied (confidence: 0.72)      │
│ Growth Rate: +10% annually                           │
│ Stockout Correction: +8% (15 days lost last 6mo)    │
│                                                       │
│ Monthly Forecast:                                    │
│ Jan: 1,045 | Feb: 1,023 | Mar: 1,089 | Apr: 1,156   │
│ May: 1,234 | Jun: 1,298 | Jul: 1,345 | Aug: 1,289   │
│ Sep: 1,178 | Oct: 1,098 | Nov: 1,045 | Dec: 1,023   │
│                                                       │
│ Total: 13,823 units | $1,347,743 revenue            │
│ Confidence: 72% (High quality, moderate variability) │
└─────────────────────────────────────────────────────┘
[Adjust Forecast] [View History] [Export]
```

### **4.4 Calculation Logic**

#### **Base Demand Calculation**
```python
def calculate_base_demand(sku_id, warehouse):
    """
    Use existing sku_demand_stats table
    """
    # Get from existing calculated stats
    stats = query("""
        SELECT 
            demand_3mo_weighted,
            demand_6mo_weighted,
            coefficient_variation,
            data_quality_score
        FROM sku_demand_stats
        WHERE sku_id = ? AND warehouse = ?
    """)
    
    # Select method based on variability
    if stats['coefficient_variation'] < 0.25:
        # Low variability - use longer period
        return stats['demand_6mo_weighted']
    else:
        # High variability - use shorter period
        return stats['demand_3mo_weighted']
```

#### **Seasonal Adjustment**
```python
def apply_seasonal_factors(base_demand, sku_id, warehouse):
    """
    Use existing seasonal_factors table
    """
    seasonal_data = query("""
        SELECT 
            sf.month_number,
            sf.seasonal_factor,
            sf.confidence_level,
            sps.pattern_strength
        FROM seasonal_factors sf
        JOIN seasonal_patterns_summary sps 
            ON sf.sku_id = sps.sku_id 
            AND sf.warehouse = sps.warehouse
        WHERE sf.sku_id = ? AND sf.warehouse = ?
    """)
    
    monthly_forecast = {}
    for month in range(1, 13):
        if seasonal_data[month]['confidence_level'] > 0.5:
            # Apply seasonal factor if confident
            monthly_forecast[month] = base_demand * seasonal_data[month]['seasonal_factor']
        else:
            # Use base demand if not confident
            monthly_forecast[month] = base_demand
    
    return monthly_forecast
```

#### **Growth Trend Calculation**
```python
def calculate_growth_trend(sku_id, warehouse):
    """
    Calculate trend from recent history
    """
    # Get last 12 months vs previous 12 months
    growth_data = query("""
        SELECT 
            SUM(CASE WHEN year_month >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 12 MONTH), '%Y-%m')
                THEN COALESCE(burnaby_sales, 0) + COALESCE(kentucky_sales, 0) 
                ELSE 0 END) as recent_12m,
            SUM(CASE WHEN year_month < DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 12 MONTH), '%Y-%m')
                AND year_month >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 24 MONTH), '%Y-%m')
                THEN COALESCE(burnaby_sales, 0) + COALESCE(kentucky_sales, 0)
                ELSE 0 END) as previous_12m
        FROM monthly_sales
        WHERE sku_id = ?
    """)
    
    if growth_data['previous_12m'] > 0:
        yoy_growth = (growth_data['recent_12m'] - growth_data['previous_12m']) / growth_data['previous_12m']
        
        # Apply caps based on growth_status
        if sku['growth_status'] == 'viral':
            return min(yoy_growth, 1.0)  # Cap at 100% for viral
        elif sku['growth_status'] == 'declining':
            return max(yoy_growth, -0.5)  # Floor at -50% for declining
        else:
            return max(min(yoy_growth, 0.5), -0.3)  # Normal: -30% to +50%
    else:
        return 0  # No growth for new products
```

### **4.5 Accuracy Tracking**

#### **Monthly Accuracy Update**
```python
def update_forecast_accuracy():
    """
    Runs monthly to compare forecast vs actual
    Uses existing forecast_accuracy table
    """
    # Get last month's actuals
    actuals = query("""
        SELECT sku_id, 
               burnaby_sales + kentucky_sales as actual_qty,
               burnaby_revenue + kentucky_revenue as actual_rev
        FROM monthly_sales
        WHERE year_month = DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 1 MONTH), '%Y-%m')
    """)
    
    # Update forecast_accuracy table
    for sku in actuals:
        update("""
            UPDATE forecast_accuracy
            SET actual_demand = ?,
                absolute_error = ABS(actual_demand - predicted_demand),
                percentage_error = (actual_demand - predicted_demand) / actual_demand * 100,
                is_actual_recorded = 1
            WHERE sku_id = ? 
            AND forecast_period_start = DATE_SUB(NOW(), INTERVAL 1 MONTH)
        """)
```

---

## **5. Integration Requirements**

### **5.1 Data Sources**
All from existing database:
- `monthly_sales` - Historical sales and revenue
- `sku_demand_stats` - Pre-calculated demand statistics
- `seasonal_factors` - Seasonal patterns
- `inventory_current` - Current stock levels
- `pending_inventory` - Incoming orders
- `stockout_dates` - Stockout history

### **5.2 Export Formats**

#### **CSV Export for Excel Analysis**
```csv
sku_id,description,warehouse,jan_qty,feb_qty,...,dec_qty,total_qty,total_revenue,confidence
UB-YTX14-BS,12V Battery,burnaby,523,498,...,545,6234,607,815.00,0.72
```

#### **JSON API for System Integration**
```json
{
  "forecast_run_id": 123,
  "created_date": "2024-12-05",
  "forecasts": [
    {
      "sku_id": "UB-YTX14-BS",
      "warehouse": "burnaby",
      "monthly_quantities": [523, 498, ...],
      "monthly_revenues": [50991.50, 48554.40, ...],
      "annual_total_qty": 6234,
      "annual_total_rev": 607815.00,
      "confidence": 0.72
    }
  ]
}
```

---

## **6. Performance Requirements**

### **Processing Speed**
- Forecast generation: <60 seconds for 3,000 SKUs
- Dashboard load: <2 seconds
- SKU detail view: <1 second
- Export generation: <10 seconds

### **Data Volumes**
- Support up to 10,000 SKUs
- 36 months of history
- 2 warehouses
- 10 concurrent users

---

## **7. User Stories & Acceptance Criteria**

### **Core User Stories**

```gherkin
Feature: Generate Monthly Forecast
  As an inventory manager
  I want to generate a 12-month sales forecast
  So that I can plan inventory and cash flow

  Scenario: Generate forecast with default settings
    Given I have at least 6 months of sales history
    When I click "Generate Forecast"
    Then I should see a 12-month forecast for all active SKUs
    And the forecast should use corrected demand from stockouts
    And seasonal patterns should be applied where confident
```

```gherkin
Feature: Adjust Individual SKU Forecast
  As a supply chain analyst
  I want to manually adjust specific SKU forecasts
  So that I can incorporate business knowledge

  Scenario: Adjust forecast for discontinued product
    Given SKU "ABC-123" is marked as "Death Row"
    When I view the SKU forecast
    And I set months 7-12 to zero quantity
    Then the forecast should be updated
    And an adjustment record should be logged
```

---

## **8. Success Metrics**

### **Launch Metrics (Month 1)**
- Successfully generate forecast for 95%+ of active SKUs
- Dashboard loads within 2 seconds
- Export functionality works for all users

### **Adoption Metrics (Month 3)**
- Weekly active users: 5+
- Forecasts generated monthly: Yes
- Manual adjustments per forecast: <10%

### **Accuracy Metrics (Month 6)**
- Overall MAPE: <20%
- A-class items MAPE: <15%
- Forecast bias: ±5%

---

## **9. Implementation Phases**

### **Phase 1: MVP (Weeks 1-2)**
- [ ] Create forecast database tables
- [ ] Build basic calculation engine
- [ ] Simple UI for forecast generation
- [ ] CSV export functionality

### **Phase 2: Dashboard (Weeks 3-4)**
- [ ] Executive dashboard with charts
- [ ] SKU detail views
- [ ] Manual adjustment capability
- [ ] Forecast vs actual tracking

### **Phase 3: Advanced Features (Weeks 5-6)**
- [ ] Confidence scoring
- [ ] Growth pattern detection
- [ ] Event/promotion adjustments
- [ ] API for external systems

### **Phase 4: Optimization (Month 2+)**
- [ ] Performance tuning
- [ ] Advanced visualizations
- [ ] Automated alerts
- [ ] Machine learning enhancements

---

## **10. Technical Architecture**

### **Technology Stack**
- Frontend: React (matching transfer tool)
- Backend: Node.js/Python
- Database: MySQL/MariaDB (existing)
- Charts: Recharts for consistency
- State Management: React hooks

### **Key Algorithms**
1. **Weighted Moving Average** (existing in `sku_demand_stats`)
2. **Seasonal Decomposition** (existing in `seasonal_factors`)
3. **Stockout Correction** (existing `corrected_demand` fields)
4. **Confidence Scoring** (new, based on CV and data quality)

---

## **11. Risks & Mitigation**

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| Poor accuracy for new SKUs | High | High | Use category averages as baseline |
| Seasonal patterns not reliable | Medium | Medium | Allow manual override |
| User doesn't trust forecasts | High | Low | Show calculation transparency |
| Performance issues with 3000+ SKUs | Medium | Low | Implement caching and pagination |

---

## **12. Out of Scope (v1)**

- Integration with supplier ordering (Phase 2 project)
- Automated email reports
- Mobile application
- AI/ML models (use statistical methods first)
- Multi-currency handling
- Collaborative forecasting workflow

---

## **13. Appendix: Sample Calculations**

### **Example: UB-YTX14-BS Battery**

```sql
-- Input data from existing tables
Base demand (6mo weighted): 950 units/month
Seasonal factor (January): 0.92
Growth rate: +10% annually
Stockout correction: +8%
Confidence: 0.72 (based on CV=0.15, 18 months history)

-- Calculation
January forecast = 950 * 0.92 * 1.008 * 1.008
                = 886 units

Revenue forecast = 886 * $97.50 (from avg_revenue)
                = $86,385
```

---

**Document Status:** Ready for Review  
**Next Steps:** Technical review → Stakeholder approval → Development kickoff

**Key Advantages of This Approach:**
1. Leverages ALL existing data infrastructure
2. No need to rebuild seasonal/stockout calculations
3. Uses proven `sku_demand_stats` calculations
4. Integrates with existing accuracy tracking
5. Minimal new development required