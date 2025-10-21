# Forecast Learning & Accuracy System - Enhanced Implementation Plan

**Version:** 2.0 (Enhanced)
**Date:** 2025-10-20
**Status:** Ready for Implementation
**Estimated Effort:** 30-38 hours for MVP (Phases 1-4), additional 12-15 hours for Phase 5
**Expert Validation:** Incorporates recommendations from forecasting specialist

---

## Executive Summary

### Problem Statement

The current forecasting system (V7.0-V7.4) generates sophisticated 12-month predictions using ABC/XYZ classification, seasonal patterns, and growth rate calculations. However, it has **NO feedback loop**:

- Forecasts are generated but never recorded for comparison
- Actual sales data is never compared to predictions
- No accuracy metrics calculated (MAPE, bias, error rates)
- No learning mechanism to improve future forecasts
- Users cannot see forecast performance or trust levels
- Stockouts create false negatives (low sales looks like low demand)

### Solution Overview

Build a complete **Forecast Learning & Accuracy System** with 5 components:

1. **Enhanced Forecast Recording**: Capture predictions with comprehensive context (volatility, data quality, seasonal confidence)
2. **Stockout-Aware Accuracy Tracking**: Monthly comparison using corrected demand, marking stockout-affected periods
3. **Multi-Dimensional Learning**: ABC/XYZ-specific learning rates, growth status awareness, category-level intelligence
4. **Reporting Dashboard**: Visualize accuracy trends, identify problem SKUs, track learning improvements
5. **Advanced Features** (Phase 5): Real-time triggers, audit trails, automated adjustments (deferred to future)

### What Makes This Enhanced?

This enhanced plan incorporates expert recommendations and leverages your **existing sophisticated infrastructure**:

**Leverage Existing Infrastructure**:
- Your `stockout_dates` table with `is_resolved` tracking
- Your `monthly_sales.corrected_demand` calculations (already accounting for stockouts!)
- Your `skus.growth_status` detection (viral/declining/normal)
- Your `sku_demand_stats` with `coefficient_variation` and `data_quality_score`
- Your `seasonal_factors` with `confidence_level`
- Your `ABC/XYZ` classification system

**Enhanced Features vs Original Plan**:

| Feature | Original Plan | Enhanced Plan |
|---------|--------------|---------------|
| Forecast Recording | Basic: predicted, method, ABC/XYZ | Enhanced: + volatility, data quality, seasonal confidence |
| Accuracy Update | Simple actuals comparison | Stockout-aware: mark supply-constrained periods separately |
| Learning Rates | Single rate for all SKUs | ABC/XYZ-specific: AX (0.02 careful) to CZ (0.10 aggressive) |
| Growth Adjustments | Generic bias detection | Growth status-aware: viral/declining/normal strategies |
| Category Learning | Not included | Category-level fallback for new SKUs |
| Stockout Handling | Not addressed | Uses existing stockout_dates + corrected_demand |

### Key Benefits

- **Continuous Improvement**: Feedback loop auto-tunes parameters monthly
- **Stockout Intelligence**: Separate true forecast errors from supply issues
- **Transparency**: Users see accuracy history and build trust
- **Smart Learning**: Different strategies for stable (AX) vs volatile (CZ) SKUs
- **Category Intelligence**: New SKUs inherit category patterns
- **Early Warning**: Flag chronic forecasting issues before they impact business

---

## Current State Analysis

### What Already Exists in Your System

**Database Tables** (All Ready to Use):
```sql
-- forecast_accuracy table: Structure exists, currently empty (no inserts)
CREATE TABLE `forecast_accuracy` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sku_id` varchar(50) NOT NULL,
  `forecast_date` date NOT NULL,
  `forecast_period_start` date NOT NULL,
  `forecast_period_end` date NOT NULL,
  `predicted_demand` decimal(10,2) NOT NULL,
  `actual_demand` decimal(10,2) DEFAULT NULL,
  `absolute_error` decimal(10,2) DEFAULT NULL,
  `percentage_error` decimal(5,2) DEFAULT NULL,
  `absolute_percentage_error` decimal(5,2) DEFAULT NULL,
  `forecast_method` varchar(50) NOT NULL,
  `abc_class` char(1) DEFAULT NULL,
  `xyz_class` char(1) DEFAULT NULL,
  `seasonal_pattern` varchar(20) DEFAULT NULL,
  `is_actual_recorded` tinyint(1) DEFAULT 0
);

-- v_forecast_accuracy_summary view: Structure exists, no data
CREATE VIEW `v_forecast_accuracy_summary` AS
SELECT abc_class, COUNT(*) as total_forecasts, ...
  AVG(absolute_percentage_error) as avg_mape
FROM forecast_accuracy
WHERE is_actual_recorded = 1
GROUP BY abc_class;
```

**Your Sophisticated Infrastructure**:
```sql
-- stockout_dates: Real stockout tracking with resolution status
CREATE TABLE stockout_dates (
  sku_id VARCHAR(50),
  stockout_date DATE,
  warehouse VARCHAR(20),
  is_resolved TINYINT(1) DEFAULT 0
);

-- monthly_sales: Already calculates corrected_demand!
CREATE TABLE monthly_sales (
  sku_id VARCHAR(50),
  year_month VARCHAR(7),
  burnaby_sales INT,
  kentucky_sales INT,
  burnaby_stockout_days INT,
  kentucky_stockout_days INT,
  corrected_demand_burnaby DECIMAL(10,2),  -- Already accounts for stockouts
  corrected_demand_kentucky DECIMAL(10,2)
);

-- sku_demand_stats: Volatility and data quality metrics
CREATE TABLE sku_demand_stats (
  sku_id VARCHAR(50),
  coefficient_variation DECIMAL(5,2),  -- Volatility measure
  data_quality_score DECIMAL(3,2),     -- Data completeness
  volatility_class VARCHAR(10)          -- 'low', 'medium', 'high'
);

-- seasonal_factors: Seasonal patterns with confidence
CREATE TABLE seasonal_factors (
  sku_id VARCHAR(50),
  month_number INT,
  seasonal_factor DECIMAL(5,4),
  confidence_level DECIMAL(5,4)  -- How confident in this factor
);

-- skus: Growth status already detected
CREATE TABLE skus (
  sku_id VARCHAR(50),
  abc_code CHAR(1),         -- Value classification
  xyz_code CHAR(1),         -- Volatility classification
  growth_status VARCHAR(20), -- 'viral', 'declining', 'normal'
  seasonal_pattern VARCHAR(20)
);
```

**Forecasting Engine** (backend/forecasting.py):
- `ForecastEngine` class with ABC/XYZ-based methods
- `calculate_sku_growth_rate()`: Weighted regression with XYZ-adaptive weighting
- `_calculate_monthly_forecasts()`: Generates 12-month predictions
- `save_forecast()`: Currently saves to forecast_details only (needs enhancement)

### What's Missing (What We'll Build)

1. **No code to INSERT into forecast_accuracy** when forecasts are generated
2. **No monthly job** to compare actuals vs forecasts
3. **No stockout awareness** in accuracy calculations
4. **No learning algorithms** to adjust parameters
5. **No API endpoints** for accuracy data
6. **No frontend dashboard** to view accuracy
7. **No context capture** (volatility, data quality, seasonal confidence at time of forecast)

---

## Database Schema Enhancements

### Phase 1: Enhance forecast_accuracy Table

**Add Context Fields** (capture state at time of forecast):

```sql
ALTER TABLE forecast_accuracy
ADD COLUMN stockout_affected BOOLEAN DEFAULT FALSE COMMENT 'TRUE if stockout occurred during forecast period, causing under-sales',
ADD COLUMN volatility_at_forecast DECIMAL(5,2) COMMENT 'coefficient_variation from sku_demand_stats at time of forecast',
ADD COLUMN data_quality_score DECIMAL(3,2) COMMENT 'Data quality score at time of forecast',
ADD COLUMN seasonal_confidence_at_forecast DECIMAL(5,4) COMMENT 'confidence_level from seasonal_factors at time of forecast',
ADD COLUMN learning_applied BOOLEAN DEFAULT FALSE COMMENT 'TRUE if learning adjustment was applied to this SKU after this forecast',
ADD COLUMN learning_applied_date TIMESTAMP NULL COMMENT 'When learning adjustment was applied';

-- Performance Indexes
ALTER TABLE forecast_accuracy
ADD INDEX idx_learning_status (learning_applied, forecast_date),
ADD INDEX idx_period_recorded (forecast_period_start, is_actual_recorded),
ADD INDEX idx_sku_recorded (sku_id, is_actual_recorded, forecast_period_start);
```

**Why These Fields Matter**:
- `stockout_affected`: Don't penalize forecast when stockout caused low sales
- `volatility_at_forecast`: Understand if high MAPE was expected due to volatility
- `data_quality_score`: Know if poor accuracy was due to limited/poor data
- `seasonal_confidence_at_forecast`: Distinguish good vs uncertain seasonal factors
- `learning_applied`: Track which SKUs have been adjusted by learning system

### Phase 2: Create forecast_learning_adjustments Table

**Separate System Learning from Manual Adjustments**:

```sql
CREATE TABLE forecast_learning_adjustments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku_id VARCHAR(50) NOT NULL,
    adjustment_type ENUM(
        'growth_rate',
        'seasonal_factor',
        'method_switch',
        'volatility_adjustment',
        'category_default'
    ) NOT NULL,
    original_value DECIMAL(10,4) COMMENT 'Value before adjustment',
    adjusted_value DECIMAL(10,4) COMMENT 'Recommended value after adjustment',
    adjustment_magnitude DECIMAL(10,4) COMMENT 'Size of adjustment (for tracking)',
    learning_reason TEXT COMMENT 'Why this adjustment is recommended',
    confidence_score DECIMAL(3,2) COMMENT 'Confidence in this adjustment (0-1)',
    mape_before DECIMAL(5,2) COMMENT 'MAPE before adjustment',
    mape_expected DECIMAL(5,2) COMMENT 'Expected MAPE after adjustment',
    applied BOOLEAN DEFAULT FALSE COMMENT 'TRUE when adjustment is applied to forecasts',
    applied_date TIMESTAMP NULL COMMENT 'When adjustment was applied',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
    INDEX idx_applied (applied, created_at),
    INDEX idx_sku_type (sku_id, adjustment_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

**Why Separate Table**:
- Your existing `forecast_adjustments` table is for manual user adjustments
- This new table is for system-learned adjustments
- Allows auditing: see what system learned vs what user manually changed
- `applied=FALSE` by default: adjustments are logged as recommendations first
- Future: auto-apply high-confidence adjustments, require approval for low-confidence

---

## Phase 1: Enhanced Forecast Recording

### Objective
Capture comprehensive SKU context when recording forecasts for future learning analysis.

### Implementation

**File**: `backend/forecast_accuracy.py` (NEW FILE)

```python
"""
Forecast Accuracy Tracking Module

Handles recording forecasts with comprehensive context, comparing actuals,
calculating errors, and supporting continuous learning improvements.

This module integrates with existing infrastructure:
- stockout_dates: For stockout-aware accuracy tracking
- monthly_sales.corrected_demand: For true demand (stockout-adjusted)
- sku_demand_stats: For volatility and data quality context
- seasonal_factors: For seasonal confidence context
"""

from typing import Dict, List, Optional
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from backend.database import execute_query
import logging

logger = logging.getLogger(__name__)


def record_forecast_for_accuracy_tracking(
    forecast_run_id: int,
    sku_id: str,
    warehouse: str,
    forecast_data: Dict
) -> bool:
    """
    Record forecast predictions to forecast_accuracy table with comprehensive context.

    Creates 12 separate records (one per month) for later comparison with actual sales.
    Captures SKU state at time of forecast (volatility, data quality, seasonal confidence)
    to understand forecast performance in context.

    Args:
        forecast_run_id: ID of the forecast run
        sku_id: SKU identifier
        warehouse: Warehouse location ('burnaby', 'kentucky', 'combined')
        forecast_data: Dictionary from ForecastEngine.generate_forecast_for_sku()
                      Contains: monthly_forecasts, method_used, confidence_score, etc.

    Returns:
        True if successful, False otherwise

    Example forecast_data structure:
        {
            'sku_id': 'UB-YTX14-BS',
            'warehouse': 'combined',
            'monthly_forecasts': [
                {'month': 1, 'date': '2025-10', 'quantity': 950, 'revenue': 92625.00},
                {'month': 2, 'date': '2025-11', 'quantity': 980, 'revenue': 95550.00},
                ...
            ],
            'method_used': 'weighted_ma_6mo',
            'confidence_score': 0.72,
            'seasonal_pattern': 'year-round',
            'base_demand_used': 950.0,
            'growth_rate_applied': 0.10
        }
    """
    try:
        # Get forecast run metadata
        run_query = """
            SELECT forecast_date, created_at
            FROM forecast_runs
            WHERE id = %s
        """
        run_result = execute_query(run_query, (forecast_run_id,), fetch_all=True)

        if not run_result:
            logger.error(f"Forecast run {forecast_run_id} not found")
            return False

        forecast_date = run_result[0]['forecast_date']

        # Get SKU classification for tracking
        sku_query = """
            SELECT abc_code, xyz_code, seasonal_pattern
            FROM skus
            WHERE sku_id = %s
        """
        sku_result = execute_query(sku_query, (sku_id,), fetch_all=True)

        if not sku_result:
            logger.warning(f"SKU {sku_id} not found in skus table")
            abc_class = None
            xyz_class = None
            seasonal_pattern = None
        else:
            abc_class = sku_result[0]['abc_code']
            xyz_class = sku_result[0]['xyz_code']
            seasonal_pattern = sku_result[0]['seasonal_pattern']

        # Enhanced: Get comprehensive context for each month
        # This captures SKU state at time of forecast for later analysis
        context_query = """
            SELECT
                s.abc_code, s.xyz_code, s.seasonal_pattern, s.growth_status,
                sds.coefficient_variation, sds.data_quality_score,
                sf.seasonal_factor, sf.confidence_level as seasonal_confidence,
                sps.pattern_strength, sps.statistical_significance
            FROM skus s
            LEFT JOIN sku_demand_stats sds ON s.sku_id = sds.sku_id
                AND sds.warehouse = %s
            LEFT JOIN seasonal_factors sf ON s.sku_id = sf.sku_id
                AND sf.warehouse = %s AND sf.month_number = %s
            LEFT JOIN seasonal_patterns_summary sps ON s.sku_id = sps.sku_id
                AND sps.warehouse = %s
            WHERE s.sku_id = %s
        """

        monthly_forecasts = forecast_data.get('monthly_forecasts', [])
        method_used = forecast_data.get('method_used', 'unknown')

        # Insert one record per month (12 total)
        for month_forecast in monthly_forecasts:
            # Parse date (format: '2025-10')
            forecast_period_date = datetime.strptime(month_forecast['date'], '%Y-%m')
            month_number = forecast_period_date.month

            # Get context for this specific month
            context_result = execute_query(
                context_query,
                (warehouse, warehouse, month_number, warehouse, sku_id),
                fetch_all=True
            )

            context = context_result[0] if context_result else {}

            # Period is the whole month
            forecast_period_start = forecast_period_date.date()
            forecast_period_end = (
                forecast_period_date + relativedelta(months=1) - relativedelta(days=1)
            ).date()

            predicted_qty = month_forecast['quantity']

            # Enhanced insert with context fields
            insert_query = """
                INSERT INTO forecast_accuracy
                (sku_id, forecast_date, forecast_period_start, forecast_period_end,
                 predicted_demand, forecast_method, abc_class, xyz_class,
                 seasonal_pattern, volatility_at_forecast, data_quality_score,
                 seasonal_confidence_at_forecast, is_actual_recorded)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """

            execute_query(
                insert_query,
                (sku_id, forecast_date, forecast_period_start, forecast_period_end,
                 predicted_qty, method_used,
                 context.get('abc_code'), context.get('xyz_code'),
                 context.get('seasonal_pattern'),
                 context.get('coefficient_variation'),  # Volatility at forecast time
                 context.get('data_quality_score'),     # Data quality at forecast time
                 context.get('seasonal_confidence')),   # Seasonal confidence at forecast time
                fetch_all=False
            )

        logger.info(f"Recorded {len(monthly_forecasts)} periods with context for {sku_id}")
        return True

    except Exception as e:
        logger.error(f"Error recording forecast for {sku_id}: {e}", exc_info=True)
        return False
```

### Integration Point

**File**: `backend/forecasting.py` (MODIFY EXISTING)
**Function**: `save_forecast()` (lines 635-693)
**Action**: Add call after saving to forecast_details

```python
def save_forecast(self, forecast_data: Dict) -> bool:
    """
    Save forecast results to forecast_details table.

    MODIFIED V8.0: Now also records to forecast_accuracy for learning.

    Args:
        forecast_data: Forecast dictionary from generate_forecast_for_sku()

    Returns:
        True if successful, False otherwise
    """
    monthly = forecast_data['monthly_forecasts']

    # Extract monthly quantities and revenues
    qty_values = [m['quantity'] for m in monthly]
    rev_values = [m['revenue'] for m in monthly]

    query = """
        INSERT INTO forecast_details
        (forecast_run_id, sku_id, warehouse,
         month_1_qty, month_2_qty, month_3_qty, month_4_qty,
         month_5_qty, month_6_qty, month_7_qty, month_8_qty,
         month_9_qty, month_10_qty, month_11_qty, month_12_qty,
         month_1_rev, month_2_rev, month_3_rev, month_4_rev,
         month_5_rev, month_6_rev, month_7_rev, month_8_rev,
         month_9_rev, month_10_rev, month_11_rev, month_12_rev,
         base_demand_used, seasonal_pattern_applied,
         growth_rate_applied, growth_rate_source, confidence_score, method_used)
        VALUES
        (%s, %s, %s,
         %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
         %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
         %s, %s, %s, %s, %s, %s)
    """

    params = (
        self.forecast_run_id,
        forecast_data['sku_id'],
        forecast_data['warehouse'],
        *qty_values,
        *rev_values,
        forecast_data['base_demand_used'],
        forecast_data['seasonal_pattern'],
        forecast_data['growth_rate_applied'],
        forecast_data['growth_rate_source'],
        forecast_data['confidence_score'],
        forecast_data['method_used']
    )

    try:
        # Save to forecast_details (existing code)
        execute_query(query, params, fetch_all=False)

        # NEW V8.0: Record to forecast_accuracy for learning
        from backend.forecast_accuracy import record_forecast_for_accuracy_tracking

        success = record_forecast_for_accuracy_tracking(
            forecast_run_id=self.forecast_run_id,
            sku_id=forecast_data['sku_id'],
            warehouse=forecast_data['warehouse'],
            forecast_data=forecast_data
        )

        if success:
            logger.info(f"Forecast recorded to forecast_accuracy for {forecast_data['sku_id']}")
        else:
            logger.warning(f"Failed to record forecast_accuracy for {forecast_data['sku_id']} (non-critical)")

        return True

    except Exception as e:
        logger.error(f"Error saving forecast for {forecast_data['sku_id']}: {e}")
        return False
```

### Testing Phase 1

**File**: `backend/test_forecast_recording.py` (NEW FILE)

```python
"""
Test script to verify forecast recording to forecast_accuracy table.
"""

from backend.forecasting import ForecastEngine, create_forecast_run
from backend.database import execute_query

def test_forecast_recording():
    """Test that forecasts are being recorded to forecast_accuracy with context."""

    # Create test forecast run
    run_id = create_forecast_run(
        forecast_name="V8.0 Test - Accuracy Recording",
        growth_assumption=0.05,
        warehouse='combined'
    )

    print(f"Created test forecast run: {run_id}")

    # Generate forecast for a single SKU
    engine = ForecastEngine(run_id, manual_growth_override=0.05)

    # Use UB-YTX14-BS (known good SKU from V7.0 testing)
    test_sku = 'UB-YTX14-BS'

    try:
        forecast = engine.generate_forecast_for_sku(test_sku, warehouse='combined')
        success = engine.save_forecast(forecast)

        print(f"Forecast generation: {'SUCCESS' if success else 'FAILED'}")

        # Verify records in forecast_accuracy
        check_query = """
            SELECT COUNT(*) as record_count,
                   MIN(forecast_period_start) as first_period,
                   MAX(forecast_period_end) as last_period,
                   AVG(volatility_at_forecast) as avg_volatility,
                   AVG(data_quality_score) as avg_data_quality,
                   AVG(seasonal_confidence_at_forecast) as avg_seasonal_conf
            FROM forecast_accuracy
            WHERE sku_id = %s
              AND forecast_date = (SELECT forecast_date FROM forecast_runs WHERE id = %s)
        """

        result = execute_query(check_query, (test_sku, run_id), fetch_all=True)

        if result:
            print(f"\nRecords in forecast_accuracy: {result[0]['record_count']}")
            print(f"First period: {result[0]['first_period']}")
            print(f"Last period: {result[0]['last_period']}")
            print(f"Avg volatility captured: {result[0]['avg_volatility']}")
            print(f"Avg data quality: {result[0]['avg_data_quality']}")
            print(f"Avg seasonal confidence: {result[0]['avg_seasonal_conf']}")

            if result[0]['record_count'] == 12:
                print("\nTEST PASSED: All 12 monthly forecasts recorded with context!")
            else:
                print(f"\nTEST FAILED: Expected 12 records, got {result[0]['record_count']}")

    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_forecast_recording()
```

**Run Test**:
```bash
cd C:\Users\Arjay\Downloads\warehouse-transfer
python -m backend.test_forecast_recording
```

**Expected Output**:
```
Created test forecast run: 45
Forecast generation: SUCCESS

Records in forecast_accuracy: 12
First period: 2025-10-01
Last period: 2026-09-30
Avg volatility captured: 0.23
Avg data quality: 0.89
Avg seasonal confidence: 0.75

TEST PASSED: All 12 monthly forecasts recorded with context!
```

---

## Phase 2: Stockout-Aware Accuracy Update

### Objective
Monthly job to compare actual sales vs forecasts, calculate errors, and mark stockout-affected periods separately.

### Key Innovation: Stockout Awareness

**Your Existing Infrastructure** (Already Built!):
- `stockout_dates` table tracks daily stockouts with `is_resolved` status
- `monthly_sales.corrected_demand` already calculates true demand accounting for stockouts
- 30% availability floor prevents overcorrection (from your existing logic)

**Enhancement**: Use this data to avoid penalizing forecasts when stockouts caused under-sales.

### Implementation

**File**: `backend/forecast_accuracy.py` (append to existing file)

```python
def update_monthly_accuracy(target_month: Optional[str] = None) -> Dict:
    """
    Compare actual sales to forecast predictions for a specific month.

    ENHANCED V8.0: Stockout-aware accuracy tracking.
    - Uses corrected_demand from monthly_sales (already accounts for stockouts)
    - Marks forecasts as stockout_affected when stockouts occurred during period
    - Doesn't penalize forecasts when stockout caused under-sales

    This function runs monthly (typically on the 1st) to:
    1. Find forecast_accuracy records with is_actual_recorded = 0
    2. Look up actual sales from monthly_sales for that period
    3. Check stockout_dates for stockouts during forecast period
    4. Calculate errors: absolute_error, percentage_error, MAPE
    5. Update forecast_accuracy with actuals and errors
    6. Mark stockout_affected periods separately

    Args:
        target_month: Month to update in 'YYYY-MM' format.
                     If None, updates previous month (default).

    Returns:
        Dictionary with update statistics:
        {
            'month_updated': '2025-10',
            'total_forecasts': 1768,
            'actuals_found': 1650,
            'missing_actuals': 118,
            'avg_mape': 18.5,
            'stockout_affected_count': 45,
            'errors': []
        }

    Example:
        # Run on Nov 1st to update October actuals
        result = update_monthly_accuracy(target_month='2025-10')
    """
    # Determine target month
    if target_month is None:
        # Default: previous month
        last_month = datetime.now() - relativedelta(months=1)
        target_month = last_month.strftime('%Y-%m')

    logger.info(f"Starting stockout-aware accuracy update for month: {target_month}")

    # Parse target month
    try:
        target_date = datetime.strptime(target_month, '%Y-%m')
        period_start = target_date.date()
        period_end = (target_date + relativedelta(months=1) - relativedelta(days=1)).date()
    except ValueError:
        logger.error(f"Invalid target_month format: {target_month}. Use YYYY-MM")
        return {'error': 'Invalid month format'}

    # Find unrecorded forecasts for this period WITH stockout context
    # ENHANCED: Check stockout_dates table for stockouts during forecast period
    find_forecasts_query = """
        SELECT
            fa.id,
            fa.sku_id,
            fa.forecast_period_start,
            fa.forecast_period_end,
            fa.predicted_demand,
            fa.forecast_method,
            fa.abc_class,
            fa.xyz_class,
            fa.volatility_at_forecast,
            -- Count stockout days during this forecast period
            (SELECT COUNT(*) FROM stockout_dates sd
             WHERE sd.sku_id = fa.sku_id
             AND sd.stockout_date BETWEEN fa.forecast_period_start
                 AND fa.forecast_period_end
             AND sd.is_resolved = 0) as stockout_days
        FROM forecast_accuracy fa
        WHERE fa.forecast_period_start = %s
          AND fa.forecast_period_end = %s
          AND fa.is_actual_recorded = 0
        ORDER BY fa.sku_id
    """

    forecasts = execute_query(
        find_forecasts_query,
        (period_start, period_end),
        fetch_all=True
    )

    total_forecasts = len(forecasts)
    logger.info(f"Found {total_forecasts} unrecorded forecasts for {target_month}")

    if total_forecasts == 0:
        return {
            'month_updated': target_month,
            'total_forecasts': 0,
            'message': 'No unrecorded forecasts found for this month'
        }

    # Get actual sales for all SKUs in this month
    # ENHANCED: Use corrected_demand (your existing stockout-adjusted demand!)
    actuals_query = """
        SELECT
            sku_id,
            (corrected_demand_burnaby + corrected_demand_kentucky) as actual_demand,
            (burnaby_sales + kentucky_sales) as actual_sales,
            burnaby_stockout_days + kentucky_stockout_days as total_stockout_days
        FROM monthly_sales
        WHERE year_month = %s
    """

    actuals = execute_query(actuals_query, (target_month,), fetch_all=True)

    # Create lookup dictionary for fast access
    actuals_dict = {
        row['sku_id']: {
            'actual_demand': float(row['actual_demand']),
            'actual_sales': int(row['actual_sales']),
            'total_stockout_days': int(row['total_stockout_days'])
        }
        for row in actuals
    }

    logger.info(f"Retrieved actuals for {len(actuals_dict)} SKUs")

    actuals_found = 0
    missing_actuals = 0
    stockout_affected_count = 0
    errors_list = []
    mape_values = []

    for forecast in forecasts:
        sku_id = forecast['sku_id']
        predicted = float(forecast['predicted_demand'])
        stockout_days = forecast['stockout_days']
        stockout_affected = stockout_days > 0

        if sku_id in actuals_dict:
            actual = actuals_dict[sku_id]['actual_demand']  # Using corrected_demand!

            # Calculate errors
            absolute_error = abs(actual - predicted)

            # Handle division by zero for percentage error
            if actual > 0:
                percentage_error = ((actual - predicted) / actual) * 100
                absolute_percentage_error = abs(percentage_error)
            else:
                # Actual is 0 - special case
                if predicted > 0:
                    # We predicted demand but there was none
                    percentage_error = -100.0  # Over-forecast
                    absolute_percentage_error = 100.0
                else:
                    # Both are 0 - perfect forecast
                    percentage_error = 0.0
                    absolute_percentage_error = 0.0

            # ENHANCED STOCKOUT LOGIC:
            # If stockout affected AND we under-sold (actual < predicted),
            # mark as stockout_affected but don't count error against forecast quality
            # Rationale: Forecast was correct, but supply constraint prevented sales
            if stockout_affected and actual < predicted:
                # Stockout caused lower sales than forecast predicted
                # Still record the error, but mark it as supply-constrained
                update_query = """
                    UPDATE forecast_accuracy
                    SET actual_demand = %s,
                        absolute_error = %s,
                        percentage_error = %s,
                        absolute_percentage_error = %s,
                        stockout_affected = TRUE,
                        is_actual_recorded = 1
                    WHERE id = %s
                """
                stockout_affected_count += 1
                # Don't add to mape_values (exclude from accuracy metrics)
            else:
                # Normal accuracy update (no stockout, or stockout but over-sold)
                update_query = """
                    UPDATE forecast_accuracy
                    SET actual_demand = %s,
                        absolute_error = %s,
                        percentage_error = %s,
                        absolute_percentage_error = %s,
                        stockout_affected = %s,
                        is_actual_recorded = 1
                    WHERE id = %s
                """
                mape_values.append(absolute_percentage_error)

            execute_query(
                update_query,
                (actual, absolute_error, percentage_error,
                 absolute_percentage_error, stockout_affected, forecast['id']),
                fetch_all=False
            )

            actuals_found += 1

        else:
            # No actual sales data for this SKU this month
            # This can happen for new SKUs or SKUs with zero sales
            missing_actuals += 1
            errors_list.append(f"No actuals for SKU {sku_id}")

    # Calculate aggregate MAPE (excluding stockout-affected forecasts)
    avg_mape = sum(mape_values) / len(mape_values) if mape_values else 0.0

    logger.info(f"Accuracy update complete: {actuals_found} updated, {missing_actuals} missing")
    logger.info(f"Stockout-affected forecasts: {stockout_affected_count}")
    logger.info(f"Average MAPE (excluding stockout-affected): {avg_mape:.2f}%")

    return {
        'month_updated': target_month,
        'total_forecasts': total_forecasts,
        'actuals_found': actuals_found,
        'missing_actuals': missing_actuals,
        'avg_mape': round(avg_mape, 2),
        'stockout_affected_count': stockout_affected_count,
        'errors': errors_list[:10]  # First 10 errors
    }
```

### Scheduler Script

**File**: `backend/run_monthly_accuracy_update.py` (NEW FILE)

```python
"""
Standalone script to run monthly accuracy update.
Designed to be called by Windows Task Scheduler or cron.
"""

import sys
import logging
from datetime import datetime
from backend.forecast_accuracy import update_monthly_accuracy

# Configure logging to file
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
    logger.info("="*60)
    logger.info("Starting Monthly Forecast Accuracy Update")
    logger.info("="*60)

    try:
        # Update previous month (default behavior)
        result = update_monthly_accuracy()

        logger.info(f"Update Results:")
        logger.info(f"  Month: {result.get('month_updated')}")
        logger.info(f"  Total Forecasts: {result.get('total_forecasts')}")
        logger.info(f"  Actuals Found: {result.get('actuals_found')}")
        logger.info(f"  Missing Actuals: {result.get('missing_actuals')}")
        logger.info(f"  Average MAPE: {result.get('avg_mape')}%")
        logger.info(f"  Stockout-Affected: {result.get('stockout_affected_count')}")

        if result.get('errors'):
            logger.warning(f"Errors encountered: {len(result['errors'])}")
            for error in result['errors']:
                logger.warning(f"  - {error}")

        logger.info("Monthly accuracy update completed successfully")

    except Exception as e:
        logger.error(f"Fatal error during accuracy update: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Manual Trigger API Endpoint

**File**: `backend/forecasting_api.py` (append to existing routes)

```python
@router.post("/accuracy/update", response_model=Dict)
async def trigger_accuracy_update(target_month: Optional[str] = None):
    """
    Manually trigger accuracy update for a specific month.

    Useful for:
    - Testing accuracy calculations
    - Backfilling historical data
    - Re-running failed updates

    Args:
        target_month: Month in 'YYYY-MM' format (default: last month)

    Returns:
        Update statistics including MAPE and stockout-affected count

    Example:
        POST /api/forecasts/accuracy/update?target_month=2025-10
    """
    from backend.forecast_accuracy import update_monthly_accuracy

    try:
        logger.info(f"Manual accuracy update triggered for: {target_month or 'last month'}")

        result = update_monthly_accuracy(target_month=target_month)

        if 'error' in result:
            raise HTTPException(status_code=400, detail=result['error'])

        return {
            "message": "Accuracy update completed",
            "details": result
        }

    except Exception as e:
        logger.error(f"Accuracy update failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Phase 3: Multi-Dimensional Learning

### Objective
Implement intelligent learning algorithms that auto-adjust forecasting parameters based on accuracy patterns.

### ABC/XYZ-Specific Learning Rates

**Concept**: Different SKU classifications need different learning aggressiveness.

**Your ABC/XYZ Classification** (Already Built):
- **ABC**: Value (A = high, B = medium, C = low)
- **XYZ**: Volatility (X = stable, Y = variable, Z = erratic)

**Learning Rate Strategy**:
- **AX SKUs** (high-value, stable): Careful adjustments (0.02) - mistakes costly
- **CZ SKUs** (low-value, volatile): Aggressive learning (0.10) - can tolerate experimentation
- **Medium SKUs** (BY, etc.): Moderate learning rates

### Implementation

**File**: `backend/forecast_learning.py` (NEW FILE)

```python
"""
Forecast Learning Module

Implements self-improving algorithms that adjust forecasting parameters
based on observed accuracy patterns.

Leverages existing infrastructure:
- ABC/XYZ classification for learning rate tuning
- growth_status (viral/declining/normal) for strategy selection
- stockout_affected filtering to exclude supply-constrained periods
- Category patterns for new SKU fallback
"""

from typing import Dict, List, Tuple
from backend.database import execute_query
import statistics
import logging

logger = logging.getLogger(__name__)


class ForecastLearningEngine:
    """
    Comprehensive learning system with multiple strategies.

    Uses ABC/XYZ-specific learning rates, growth status awareness,
    and category-level intelligence for continuous improvement.
    """

    def __init__(self):
        self.learning_rates = self._initialize_learning_rates()

    def _initialize_learning_rates(self):
        """
        ABC/XYZ specific learning rates.

        Rationale:
        - High-value, stable SKUs (AX): Careful adjustments to avoid costly mistakes
        - Low-value, volatile SKUs (CZ): Aggressive learning to improve erratic forecasts
        - Medium combinations: Moderate approach

        Returns:
            Dict mapping classification to growth and seasonal learning rates
        """
        return {
            'AX': {'growth': 0.02, 'seasonal': 0.05},  # Stable, careful
            'AY': {'growth': 0.03, 'seasonal': 0.08},
            'AZ': {'growth': 0.05, 'seasonal': 0.10},
            'BX': {'growth': 0.03, 'seasonal': 0.06},
            'BY': {'growth': 0.04, 'seasonal': 0.09},
            'BZ': {'growth': 0.07, 'seasonal': 0.12},
            'CX': {'growth': 0.05, 'seasonal': 0.08},
            'CY': {'growth': 0.08, 'seasonal': 0.12},
            'CZ': {'growth': 0.10, 'seasonal': 0.15},  # Volatile, aggressive
        }

    def learn_growth_adjustments(self):
        """
        Learn growth rate adjustments by SKU characteristics.

        ENHANCED: Growth status-aware (viral/declining/normal strategies).
        Excludes stockout-affected periods from analysis.
        """
        logger.info("Starting growth rate adjustment analysis...")

        # Analyze by growth status
        # IMPORTANT: Exclude stockout_affected periods!
        growth_analysis_query = """
            SELECT
                s.sku_id,
                s.growth_status,
                s.abc_code,
                s.xyz_code,
                fd.growth_rate_source,
                fd.growth_rate_applied,
                AVG(fa.percentage_error) as avg_bias,
                STDDEV(fa.percentage_error) as bias_std,
                COUNT(*) as sample_size
            FROM forecast_accuracy fa
            JOIN skus s ON fa.sku_id = s.sku_id
            JOIN forecast_details fd ON fa.sku_id = fd.sku_id
            WHERE fa.is_actual_recorded = 1
                AND fa.stockout_affected = 0  -- Exclude supply-constrained periods!
                AND fa.forecast_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
            GROUP BY s.sku_id, s.growth_status, fd.growth_rate_source
            HAVING sample_size >= 3 AND ABS(avg_bias) > 10
        """

        results = execute_query(growth_analysis_query, fetch_all=True)

        logger.info(f"Found {len(results)} SKUs with consistent forecast bias")

        adjustments_made = 0

        for row in results:
            sku_id = row['sku_id']
            classification = f"{row['abc_code']}{row['xyz_code']}"
            avg_bias = float(row['avg_bias'])

            # ENHANCED: Different strategies for different growth statuses
            if row['growth_status'] == 'viral':
                # Viral products need faster adaptation
                adjustment = min(0.10, avg_bias / 100)  # More aggressive
                direction = 'increase' if avg_bias > 0 else 'decrease'
            elif row['growth_status'] == 'declining':
                # Declining products need conservative adjustments
                adjustment = min(0.05, avg_bias / 200)  # More conservative
                direction = 'decrease' if avg_bias < 0 else 'increase'
            else:
                # Normal products use standard ABC/XYZ-based learning
                learning_rate = self.learning_rates.get(classification, {}).get('growth', 0.05)
                adjustment = min(0.10, max(-0.10, avg_bias / 100 * learning_rate))
                direction = 'increase' if avg_bias > 0 else 'decrease'

            # Log adjustment to forecast_learning_adjustments table
            self._log_learning_adjustment(
                sku_id=sku_id,
                adjustment_type='growth_rate',
                original_value=row['growth_rate_applied'],
                adjustment=adjustment,
                reason=f"Bias: {avg_bias:.2f}%, Growth Status: {row['growth_status']}, Direction: {direction}"
            )

            adjustments_made += 1

        return {
            'skus_analyzed': len(results),
            'adjustments_logged': adjustments_made,
            'message': 'Growth rate adjustments logged to forecast_learning_adjustments table'
        }

    def _log_learning_adjustment(
        self, sku_id: str, adjustment_type: str,
        original_value: float, adjustment: float, reason: str
    ) -> bool:
        """
        Log learning adjustment to forecast_learning_adjustments table.

        Adjustments are logged as recommendations (applied=FALSE).
        Future enhancement: auto-apply high-confidence adjustments.
        """
        adjusted_value = original_value + adjustment

        log_query = """
            INSERT INTO forecast_learning_adjustments
            (sku_id, adjustment_type, original_value, adjusted_value,
             adjustment_magnitude, learning_reason, applied)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
        """

        try:
            execute_query(
                log_query,
                (sku_id, adjustment_type, original_value, adjusted_value,
                 adjustment, reason),
                fetch_all=False
            )
            logger.info(f"Adjustment logged for {sku_id}: {adjustment_type} by {adjustment:.3f}")
            return True
        except Exception as e:
            logger.error(f"Failed to log adjustment for {sku_id}: {e}")
            return False

    def learn_method_effectiveness(self):
        """
        Determine best forecasting method by SKU characteristics.

        Builds recommendation matrix for future method switching.
        """
        logger.info("Analyzing forecasting method performance...")

        method_effectiveness_query = """
            SELECT
                s.abc_code,
                s.xyz_code,
                s.seasonal_pattern,
                s.growth_status,
                fa.forecast_method,
                AVG(fa.absolute_percentage_error) as avg_mape,
                STDDEV(fa.absolute_percentage_error) as mape_std,
                COUNT(DISTINCT fa.sku_id) as sku_count,
                COUNT(*) as forecast_count
            FROM forecast_accuracy fa
            JOIN skus s ON fa.sku_id = s.sku_id
            WHERE fa.is_actual_recorded = 1
                AND fa.stockout_affected = 0
            GROUP BY s.abc_code, s.xyz_code, s.seasonal_pattern,
                     s.growth_status, fa.forecast_method
            HAVING forecast_count >= 10
            ORDER BY s.abc_code, s.xyz_code, avg_mape ASC
        """

        results = execute_query(method_effectiveness_query, fetch_all=True)

        # Build recommendation matrix
        best_methods = {}
        for row in results:
            key = (row['abc_code'], row['xyz_code'],
                   row['seasonal_pattern'], row['growth_status'])

            if key not in best_methods or row['avg_mape'] < best_methods[key]['mape']:
                best_methods[key] = {
                    'method': row['forecast_method'],
                    'mape': row['avg_mape'],
                    'confidence': 1 - (row['mape_std'] / 100) if row['mape_std'] else 0.5
                }

        logger.info(f"Identified best methods for {len(best_methods)} classifications")

        return {
            'total_method_classifications': len(results),
            'best_methods_by_class': best_methods
        }

    def learn_from_categories(self):
        """
        Category-level learning for new/sparse SKUs.

        Use category patterns as fallback when SKU has insufficient history.
        """
        logger.info("Analyzing category patterns for new SKU fallback...")

        category_patterns_query = """
            SELECT
                s.category,
                s.seasonal_pattern,
                AVG(fd.growth_rate_applied) as avg_growth_rate,
                AVG(fa.absolute_percentage_error) as category_mape,
                COUNT(DISTINCT s.sku_id) as sku_count
            FROM skus s
            JOIN forecast_details fd ON s.sku_id = fd.sku_id
            JOIN forecast_accuracy fa ON s.sku_id = fa.sku_id
            WHERE fa.is_actual_recorded = 1
            GROUP BY s.category, s.seasonal_pattern
            HAVING sku_count >= 5
        """

        results = execute_query(category_patterns_query, fetch_all=True)

        # Store category defaults for new SKUs
        for row in results:
            # Future: Store in category_defaults table or use for limited_data SKUs
            logger.info(f"Category {row['category']}: avg growth {row['avg_growth_rate']:.3f}, MAPE {row['category_mape']:.1f}%")

        return {
            'categories_analyzed': len(results),
            'message': 'Category patterns available for new SKU fallback'
        }


def identify_problem_skus(mape_threshold: float = 30.0) -> List[Dict]:
    """
    Identify SKUs with consistently poor forecast accuracy.

    Args:
        mape_threshold: MAPE above which SKU is considered problematic (default: 30%)

    Returns:
        List of problematic SKUs with diagnostic info and recommendations
    """
    logger.info(f"Identifying problem SKUs (MAPE > {mape_threshold}%)...")

    problem_query = """
        SELECT
            fa.sku_id,
            s.description,
            s.abc_code,
            s.xyz_code,
            s.seasonal_pattern,
            COUNT(*) as forecast_periods,
            AVG(fa.absolute_percentage_error) as avg_mape,
            AVG(fa.percentage_error) as avg_bias,
            fa.forecast_method
        FROM forecast_accuracy fa
        JOIN skus s ON fa.sku_id = s.sku_id
        WHERE fa.is_actual_recorded = 1
          AND fa.stockout_affected = 0  -- Exclude stockout-affected
          AND fa.forecast_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
        GROUP BY fa.sku_id, fa.forecast_method
        HAVING AVG(fa.absolute_percentage_error) > %s
           AND COUNT(*) >= 3
        ORDER BY avg_mape DESC
        LIMIT 50
    """

    problems = execute_query(problem_query, (mape_threshold,), fetch_all=True)

    logger.info(f"Found {len(problems)} problem SKUs")

    # Add diagnostic recommendations
    for problem in problems:
        recommendations = []

        if problem['xyz_code'] == 'Z':
            recommendations.append("High volatility (XYZ=Z): Consider shorter forecast window or ensemble methods")

        if abs(problem['avg_bias']) > 20:
            if problem['avg_bias'] > 0:
                recommendations.append("Consistent over-forecasting: Reduce growth rate")
            else:
                recommendations.append("Consistent under-forecasting: Increase growth rate")

        if problem['seasonal_pattern'] == 'unknown':
            recommendations.append("No seasonal pattern: Verify sales history length or recalculate seasonality")

        problem['recommendations'] = recommendations

    return problems
```

### Learning Script

**File**: `backend/run_forecast_learning.py` (NEW FILE)

```python
"""
Run forecast learning algorithms after accuracy updates.
"""

from backend.forecast_learning import (
    ForecastLearningEngine,
    identify_problem_skus
)
import logging

logger = logging.getLogger(__name__)

def run_learning_cycle():
    """
    Execute all learning algorithms.

    Should run monthly after accuracy update completes.
    """
    logger.info("="*60)
    logger.info("Starting Forecast Learning Cycle")
    logger.info("="*60)

    # Instantiate learning engine
    engine = ForecastLearningEngine()

    # Step 1: Adjust growth rates
    logger.info("\n[1/3] Adjusting growth rates...")
    growth_result = engine.learn_growth_adjustments()
    logger.info(f"Growth adjustments: {growth_result}")

    # Step 2: Analyze method performance
    logger.info("\n[2/3] Analyzing method performance...")
    method_result = engine.learn_method_effectiveness()
    logger.info(f"Best methods identified: {len(method_result['best_methods_by_class'])}")

    # Step 3: Learn from categories
    logger.info("\n[3/3] Analyzing category patterns...")
    category_result = engine.learn_from_categories()
    logger.info(f"Category analysis: {category_result}")

    # Bonus: Identify problem SKUs
    logger.info("\nIdentifying problem SKUs...")
    problems = identify_problem_skus(mape_threshold=30.0)
    logger.info(f"Problem SKUs detected: {len(problems)}")

    if problems:
        logger.warning("Top 5 Problem SKUs:")
        for problem in problems[:5]:
            logger.warning(f"  {problem['sku_id']}: MAPE={problem['avg_mape']:.1f}%, "
                          f"Method={problem['forecast_method']}")

    logger.info("\nLearning cycle complete!")

    return {
        'growth_adjustments': growth_result,
        'method_analysis': method_result,
        'category_patterns': category_result,
        'problem_skus': len(problems)
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_learning_cycle()
```

---

## Phase 4: Reporting Dashboard & API

### API Endpoints

**File**: `backend/forecasting_api.py` (append to existing routes)

```python
@router.get("/accuracy/summary", response_model=Dict)
async def get_accuracy_summary():
    """
    Get overall forecast accuracy summary.

    Returns aggregate MAPE by ABC/XYZ classification and trends.

    Example Response:
    {
        "overall_mape": 18.5,
        "total_forecasts": 5000,
        "completed_forecasts": 4200,
        "by_abc_xyz": [
            {"class": "AX", "mape": 12.3, "count": 500},
            {"class": "AY", "mape": 15.8, "count": 450},
            ...
        ],
        "trend_6m": [
            {"month": "2025-05", "mape": 20.1},
            {"month": "2025-06", "mape": 19.3},
            ...
        ]
    }
    """
    # Use existing view
    summary_query = """
        SELECT * FROM v_forecast_accuracy_summary
        ORDER BY abc_class
    """

    summary = execute_query(summary_query, fetch_all=True)

    # Get monthly trend (last 6 months)
    trend_query = """
        SELECT
            DATE_FORMAT(forecast_period_start, '%Y-%m') as month,
            AVG(absolute_percentage_error) as mape,
            COUNT(*) as forecast_count
        FROM forecast_accuracy
        WHERE is_actual_recorded = 1
          AND stockout_affected = 0  -- Exclude stockout-affected
          AND forecast_period_start >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        GROUP BY DATE_FORMAT(forecast_period_start, '%Y-%m')
        ORDER BY month
    """

    trend = execute_query(trend_query, fetch_all=True)

    # Overall metrics
    overall_query = """
        SELECT
            AVG(absolute_percentage_error) as overall_mape,
            COUNT(*) as total_forecasts,
            SUM(is_actual_recorded) as completed_forecasts
        FROM forecast_accuracy
        WHERE forecast_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
          AND stockout_affected = 0  -- Exclude stockout-affected
    """

    overall = execute_query(overall_query, fetch_all=True)

    return {
        "overall_mape": round(float(overall[0]['overall_mape'] or 0), 2),
        "total_forecasts": overall[0]['total_forecasts'],
        "completed_forecasts": overall[0]['completed_forecasts'],
        "by_abc_xyz": summary,
        "trend_6m": trend
    }


@router.get("/accuracy/sku/{sku_id}", response_model=Dict)
async def get_sku_accuracy_history(sku_id: str):
    """
    Get forecast accuracy history for a specific SKU.

    Returns month-by-month comparison of predicted vs actual.
    """
    history_query = """
        SELECT
            forecast_date,
            forecast_period_start,
            forecast_period_end,
            predicted_demand,
            actual_demand,
            absolute_error,
            percentage_error,
            absolute_percentage_error,
            forecast_method,
            stockout_affected,
            is_actual_recorded
        FROM forecast_accuracy
        WHERE sku_id = %s
        ORDER BY forecast_period_start DESC
        LIMIT 24
    """

    history = execute_query(history_query, (sku_id,), fetch_all=True)

    if not history:
        raise HTTPException(status_code=404, detail=f"No forecast history for SKU {sku_id}")

    # Calculate statistics
    completed = [h for h in history if h['is_actual_recorded'] and not h['stockout_affected']]

    if completed:
        avg_mape = sum(float(h['absolute_percentage_error']) for h in completed) / len(completed)
        avg_bias = sum(float(h['percentage_error']) for h in completed) / len(completed)
    else:
        avg_mape = 0.0
        avg_bias = 0.0

    return {
        "sku_id": sku_id,
        "total_forecasts": len(history),
        "completed_forecasts": len(completed),
        "avg_mape": round(avg_mape, 2),
        "avg_bias": round(avg_bias, 2),
        "history": history
    }


@router.get("/accuracy/problems", response_model=List[Dict])
async def get_problem_skus(
    mape_threshold: float = Query(default=30.0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200)
):
    """
    Get list of SKUs with poor forecast accuracy.

    Args:
        mape_threshold: Minimum MAPE to be considered problematic (default: 30%)
        limit: Maximum number of results (default: 50)

    Returns:
        List of problematic SKUs with diagnostics
    """
    from backend.forecast_learning import identify_problem_skus

    problems = identify_problem_skus(mape_threshold=mape_threshold)

    return problems[:limit]


@router.get("/accuracy/learning-insights", response_model=Dict)
async def get_learning_insights():
    """
    Get insights from the learning system.

    Returns recent adjustments, method recommendations, and problem patterns.
    """
    # Get recent adjustments
    adjustments_query = """
        SELECT
            adjustment_type,
            COUNT(*) as count,
            AVG(adjustment_magnitude) as avg_magnitude
        FROM forecast_learning_adjustments
        WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY adjustment_type
    """

    adjustments = execute_query(adjustments_query, fetch_all=True)

    return {
        'growth_adjustments': [a for a in adjustments if a['adjustment_type'] == 'growth_rate'],
        'seasonal_adjustments': [a for a in adjustments if a['adjustment_type'] == 'seasonal_factor'],
        'message': 'Learning insights from last 30 days'
    }
```

### Frontend Dashboard (Outline)

**File**: `frontend/forecast-accuracy.html` (NEW FILE)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forecast Accuracy Dashboard</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css">
    <link rel="stylesheet" href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css">
</head>
<body>
    <div class="container-fluid">
        <h1 class="mt-4">Forecast Accuracy Dashboard</h1>

        <!-- Key Metrics Cards -->
        <div class="row mt-4">
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5>Overall MAPE</h5>
                        <h2 id="overall-mape">--</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5>Forecasts Completed</h5>
                        <h2 id="completed-count">--</h2>
                    </div>
                </div>
            </div>
            <!-- More metric cards -->
        </div>

        <!-- Charts -->
        <div class="row mt-4">
            <div class="col-md-6">
                <canvas id="mape-trend-chart"></canvas>
            </div>
            <div class="col-md-6">
                <canvas id="abc-xyz-heatmap"></canvas>
            </div>
        </div>

        <!-- Stockout Filter -->
        <div class="row mt-4">
            <div class="col-md-12">
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" id="excludeStockouts" checked>
                    <label class="form-check-label" for="excludeStockouts">
                        Exclude stockout-affected forecasts from calculations
                    </label>
                </div>
            </div>
        </div>

        <!-- Problem SKUs Table -->
        <div class="row mt-4">
            <div class="col-md-12">
                <h3>Problem SKUs</h3>
                <table id="problem-skus-table" class="table table-striped">
                    <thead>
                        <tr>
                            <th>SKU</th>
                            <th>Description</th>
                            <th>ABC/XYZ</th>
                            <th>MAPE</th>
                            <th>Bias</th>
                            <th>Method</th>
                            <th>Recommendations</th>
                        </tr>
                    </thead>
                    <tbody id="problem-skus-body">
                        <!-- Populated via JavaScript -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js@3.7.0/dist/chart.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
    <script src="https://cdn.datatables.net/1.11.5/js/dataTables.bootstrap5.min.js"></script>
    <script src="js/forecast-accuracy.js"></script>
</body>
</html>
```

**File**: `frontend/js/forecast-accuracy.js` (NEW FILE)

```javascript
// Load accuracy data and render dashboard
async function loadAccuracyDashboard() {
    try {
        // Fetch summary data
        const summary = await fetch('/api/forecasts/accuracy/summary').then(r => r.json());

        // Update metrics
        document.getElementById('overall-mape').textContent = `${summary.overall_mape}%`;
        document.getElementById('completed-count').textContent = summary.completed_forecasts;

        // Render MAPE trend chart
        renderTrendChart(summary.trend_6m);

        // Render ABC/XYZ heatmap
        renderHeatmap(summary.by_abc_xyz);

        // Load problem SKUs
        const problems = await fetch('/api/forecasts/accuracy/problems?mape_threshold=30').then(r => r.json());
        renderProblemSkusTable(problems);

    } catch (error) {
        console.error('Failed to load accuracy dashboard:', error);
    }
}

function renderTrendChart(trendData) {
    const ctx = document.getElementById('mape-trend-chart').getContext('2d');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: trendData.map(d => d.month),
            datasets: [{
                label: 'Average MAPE (%)',
                data: trendData.map(d => d.mape),
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: '6-Month MAPE Trend'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'MAPE (%)'
                    }
                }
            }
        }
    });
}

// Document ready
$(document).ready(function() {
    loadAccuracyDashboard();
});
```

---

## Phase 5: Advanced Features (Deferred)

**Status**: Planned but implementation deferred until MVP (Phases 1-4) validated in production.

**Features**:
1. Real-time learning triggers (on_stockout_detected, on_viral_growth_detected)
2. forecast_learning_log audit trail table
3. Automated adjustment application (auto-apply high-confidence adjustments)
4. Confidence interval predictions
5. Email alerts for chronic issues
6. Ensemble forecasting methods
7. A/B testing framework

**Estimated Effort**: 12-15 hours additional

**Prerequisites**: MVP must be in production for 3+ months with validated accuracy improvements.

---

## Implementation Timeline

**Week 1** (2-3 hours): Database Phase
- Enhance forecast_accuracy table
- Create forecast_learning_adjustments table
- Test migrations

**Week 2** (6-8 hours): Phase 1 - Enhanced Forecast Recording
- Implement record_forecast_for_accuracy_tracking()
- Integrate into forecasting.py
- Test context capture

**Week 3** (8-10 hours): Phase 2 - Stockout-Aware Accuracy Update
- Implement update_monthly_accuracy()
- Add stockout checking logic
- Set up scheduler job
- Test MAPE calculations

**Week 4** (10-12 hours): Phase 3 - Multi-Dimensional Learning
- Build ForecastLearningEngine class
- Implement ABC/XYZ learning rates
- Test learning algorithms

**Week 5** (6-8 hours): Phase 4 - Reporting Dashboard
- Create API endpoints
- Build dashboard HTML/JS
- Test with Playwright MCP

**Total MVP Timeline**: 30-38 hours across 5 weeks

**Future**: Phase 5 Advanced Features (12-15 hours) - Deferred until MVP validated

---

## Testing Strategy

### Unit Tests
```python
# tests/test_forecast_accuracy.py
def test_record_forecast():
    """Test forecast recording creates 12 records with context."""
    # Create test forecast
    # Verify 12 records in forecast_accuracy
    # Verify context fields populated (volatility, data_quality, seasonal_confidence)

def test_accuracy_update():
    """Test accuracy update calculates errors correctly."""
    # Create test data with known forecast/actual
    # Run update
    # Verify MAPE calculated correctly

def test_stockout_awareness():
    """Test stockout-affected marking logic."""
    # Create forecast with stockout
    # Verify stockout_affected=TRUE when actual < predicted
    # Verify not counted in MAPE
```

### Integration Tests with Playwright MCP
```javascript
// Playwright test scenarios
test('forecast accuracy dashboard loads', async ({ page }) => {
    await page.goto('http://localhost:8000/static/forecast-accuracy.html');
    await expect(page.locator('#overall-mape')).toBeVisible();
    await expect(page.locator('#mape-trend-chart')).toBeVisible();
});

test('stockout filter updates metrics', async ({ page }) => {
    await page.goto('http://localhost:8000/static/forecast-accuracy.html');
    const initialMape = await page.locator('#overall-mape').textContent();
    await page.locator('#excludeStockouts').click();
    const updatedMape = await page.locator('#overall-mape').textContent();
    expect(initialMape).not.toBe(updatedMape);
});
```

---

## Success Metrics

### Immediate (Phase 1-2, First Month)
- All forecasts recorded to forecast_accuracy table (100% coverage)
- Monthly accuracy updates running successfully
- 90%+ of forecasts have actuals matched
- Stockout-affected periods identified and marked

### Short-term (Phase 3, 1-2 months)
- Growth rate adjustments logged for 50+ SKUs
- Method performance comparison available
- Problem SKUs identified and flagged
- 5-10% MAPE improvement for SKUs with learning adjustments

### Long-term (Phase 4, 3-6 months)
- Overall MAPE improves from baseline to <20%
- A-class items achieve MAPE <15%
- Forecast bias (over/under) within ±5%
- 80% of SKUs using optimal method based on performance data
- User trust in forecasts increases (measured via adoption and feedback)

---

## Deployment Checklist

### Phase 1 Deployment
- [ ] Create database/add_forecast_learning_schema.sql migration
- [ ] Run migration on development database
- [ ] Add backend/forecast_accuracy.py module
- [ ] Modify backend/forecasting.py save_forecast() method
- [ ] Run test: python -m backend.test_forecast_recording
- [ ] Verify 12 records per SKU with context fields populated
- [ ] Commit to git: "feat(V8.0): Phase 1 - Enhanced forecast recording with context capture"

### Phase 2 Deployment
- [ ] Implement update_monthly_accuracy() in forecast_accuracy.py
- [ ] Create backend/run_monthly_accuracy_update.py scheduler script
- [ ] Set up Windows Task Scheduler or cron job (monthly on 1st at 2:00 AM)
- [ ] Add POST /api/forecasts/accuracy/update endpoint
- [ ] Run test: python -m backend.test_accuracy_update
- [ ] Verify stockout_affected marking logic
- [ ] Commit to git: "feat(V8.0): Phase 2 - Stockout-aware accuracy tracking"

### Phase 3 Deployment
- [ ] Add backend/forecast_learning.py module
- [ ] Implement ForecastLearningEngine class with ABC/XYZ learning rates
- [ ] Create backend/run_forecast_learning.py script
- [ ] Run test: python -m backend.run_forecast_learning
- [ ] Verify adjustments logged to forecast_learning_adjustments
- [ ] Commit to git: "feat(V8.0): Phase 3 - Multi-dimensional learning algorithms"

### Phase 4 Deployment
- [ ] Add accuracy API endpoints to forecasting_api.py
- [ ] Create frontend/forecast-accuracy.html dashboard
- [ ] Create frontend/js/forecast-accuracy.js
- [ ] Test dashboard with Playwright MCP
- [ ] Add navigation link from main dashboard
- [ ] Commit to git: "feat(V8.0): Phase 4 - Forecast accuracy reporting dashboard"

---

## Contacts & Support

**Implementation Questions**: Refer to existing codebase patterns in backend/forecasting.py
**Database Schema**: See database/schema.sql and existing views
**Testing**: Use Playwright MCP for comprehensive UI testing
**Deployment**: Follow existing FastAPI patterns in backend/main.py

---

**Document Version**: 2.0 (Enhanced)
**Last Updated**: 2025-10-20
**Status**: Ready for Implementation
**Estimated Total Effort**: 30-38 hours for MVP (Phases 1-4), additional 12-15 hours for Phase 5
**Next Task**: TASK-511 (Database schema enhancement)

**Key Differentiator**: This enhanced plan leverages your existing sophisticated infrastructure (stockout_dates, corrected_demand, ABC/XYZ classification, growth_status detection) to build a more intelligent learning system than generic forecasting theory would provide.
