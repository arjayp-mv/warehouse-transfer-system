# Forecast Learning & Accuracy System - Complete Implementation Plan

**Version:** 1.0
**Date:** 2025-10-20
**Status:** Ready for Implementation
**Estimated Effort:** 3-4 days (across 4 phases)

---

## Executive Summary

### Problem Statement
The current forecasting system generates predictions but has NO feedback loop:
- Forecasts are generated but not recorded for comparison
- Actual sales data is never compared to predictions
- No accuracy metrics (MAPE, bias, error rates)
- No learning mechanism to improve future forecasts
- Users cannot see forecast performance

### Solution Overview
Build a complete Forecast Learning & Accuracy System with 4 components:
1. **Forecast Recording**: Capture predictions when generated
2. **Accuracy Tracking**: Monthly comparison of actual vs predicted
3. **Learning Mechanisms**: Auto-adjust parameters based on errors
4. **Reporting Dashboard**: Visualize accuracy and identify issues

### Key Benefits
- Continuous improvement through feedback loops
- Identify underperforming forecasting methods
- Auto-tune growth rates and seasonal factors
- Alert on chronic forecasting issues
- Build stakeholder trust through transparency

---

## Current State Analysis

### What Already Exists ✅

#### Database Tables
```sql
-- Already created and ready to use
CREATE TABLE `forecast_accuracy` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sku_id` varchar(50) NOT NULL,
  `forecast_date` date NOT NULL COMMENT 'Date when forecast was made',
  `forecast_period_start` date NOT NULL COMMENT 'Start of forecasted period',
  `forecast_period_end` date NOT NULL COMMENT 'End of forecasted period',
  `predicted_demand` decimal(10,2) NOT NULL,
  `actual_demand` decimal(10,2) DEFAULT NULL,
  `absolute_error` decimal(10,2) DEFAULT NULL,
  `percentage_error` decimal(5,2) DEFAULT NULL,
  `absolute_percentage_error` decimal(5,2) DEFAULT NULL,
  `forecast_method` varchar(50) NOT NULL,
  `abc_class` char(1) DEFAULT NULL,
  `xyz_class` char(1) DEFAULT NULL,
  `seasonal_pattern` varchar(20) DEFAULT NULL,
  `is_actual_recorded` tinyint(1) DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
);

-- View for aggregate reporting
CREATE VIEW `v_forecast_accuracy_summary` AS
SELECT
  abc_class,
  COUNT(*) as total_forecasts,
  SUM(is_actual_recorded) as completed_forecasts,
  AVG(absolute_percentage_error) as avg_mape,
  STDDEV(absolute_percentage_error) as mape_std_dev,
  SUM(CASE WHEN absolute_percentage_error < 10 THEN 1 ELSE 0 END) as excellent_forecasts,
  SUM(CASE WHEN absolute_percentage_error BETWEEN 10 AND 20 THEN 1 ELSE 0 END) as good_forecasts,
  SUM(CASE WHEN absolute_percentage_error > 20 THEN 1 ELSE 0 END) as poor_forecasts,
  MAX(forecast_date) as latest_forecast_date,
  MIN(forecast_date) as earliest_forecast_date
FROM forecast_accuracy
WHERE is_actual_recorded = 1
GROUP BY abc_class;
```

#### Forecast Storage
```sql
-- forecast_runs: Master table tracking forecast generation
-- Fields: id, forecast_name, forecast_date, status, created_at, etc.

-- forecast_details: Monthly forecasts per SKU
-- Fields: month_1_qty through month_12_qty, month_1_rev through month_12_rev
--         base_demand_used, growth_rate_applied, confidence_score, method_used
```

#### Monthly Sales Actuals
```sql
-- monthly_sales: Actual sales data for comparison
-- Fields: year_month, sku_id, burnaby_sales, kentucky_sales
--         burnaby_revenue, kentucky_revenue, corrected_demand_*
```

#### Forecasting Engine (backend/forecasting.py)
- `ForecastEngine` class with ABC/XYZ-based methods
- `_calculate_monthly_forecasts()` generates 12-month predictions
- Growth rate calculation with weighted regression
- Seasonal factor application
- "Test & Learn" pattern detection for new SKUs

### What's Missing ❌

1. **No code to INSERT into forecast_accuracy** when forecasts are generated
2. **No monthly job** to compare actuals vs forecasts
3. **No learning algorithms** to adjust parameters
4. **No API endpoints** for accuracy data
5. **No frontend dashboard** to view accuracy
6. **No alerts** for poor-performing forecasts

---

## System Architecture

### Data Flow Overview
```
┌─────────────────────────────────────────────────────────────────┐
│                    FORECAST GENERATION                           │
│  User Triggers → ForecastEngine → forecast_details (12 months)  │
│                                         ↓                        │
│                         NEW: Insert to forecast_accuracy         │
│                         (12 records per SKU - one per month)     │
└─────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────┐
│                    MONTHLY ACCURACY UPDATE                       │
│  Scheduled Job → Compare actuals vs forecasts → Update errors   │
│                                         ↓                        │
│                         Calculate MAPE, bias, absolute error     │
│                         Set is_actual_recorded = 1               │
└─────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────┐
│                    LEARNING & ADJUSTMENT                         │
│  Analyze errors → Adjust growth rates → Update seasonal factors │
│                                         ↓                        │
│                         Flag problem SKUs → Notify users         │
│                         Switch to better methods                 │
└─────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────┐
│                    REPORTING & ALERTS                            │
│  Dashboard → MAPE by ABC/XYZ → Top/Bottom performers            │
│  Alerts → Email/UI notifications for chronic issues              │
└─────────────────────────────────────────────────────────────────┘
```

### Key Integration Points

#### 1. Forecast Recording (During Generation)
**Location**: `backend/forecasting.py` → `ForecastEngine.save_forecast()`
**Current Line**: 635-693
**Action**: Add call to `record_forecast_for_accuracy_tracking()`

#### 2. Monthly Accuracy Update (Scheduled Job)
**New File**: `backend/forecast_accuracy.py`
**Function**: `update_monthly_accuracy()`
**Schedule**: Runs 1st of each month via cron/scheduler

#### 3. Learning Mechanisms (After Accuracy Update)
**New File**: `backend/forecast_learning.py`
**Function**: `apply_learning_adjustments()`
**Trigger**: After accuracy update completes

#### 4. API Endpoints (For Frontend)
**Location**: `backend/forecasting_api.py`
**New Routes**:
- `GET /api/forecasts/accuracy/summary`
- `GET /api/forecasts/accuracy/sku/{sku_id}`
- `GET /api/forecasts/accuracy/problems`

#### 5. Frontend Dashboard
**New File**: `frontend/forecast-accuracy.html`
**Components**: Charts, tables, alerts, SKU drill-down

---

## Phase 1: Forecast Recording (Foundation)

**Goal**: Capture all forecasts in `forecast_accuracy` table when generated
**Effort**: 4-6 hours
**Priority**: CRITICAL (enables all other phases)

### Implementation Steps

#### Step 1.1: Add Forecast Recording Function

**File**: `backend/forecast_accuracy.py` (NEW FILE)

```python
"""
Forecast Accuracy Tracking Module

Handles recording forecasts, comparing actuals, calculating errors,
and driving continuous learning improvements.
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
    Record forecast predictions to forecast_accuracy table.

    Creates 12 separate records (one per month) for later comparison
    with actual sales data.

    Args:
        forecast_run_id: ID of the forecast run
        sku_id: SKU identifier
        warehouse: Warehouse location
        forecast_data: Dictionary from ForecastEngine.generate_forecast_for_sku()
                      Contains: monthly_forecasts, method_used, confidence_score, etc.

    Returns:
        True if successful, False otherwise

    Example forecast_data structure:
        {
            'sku_id': 'UB-YTX14-BS',
            'warehouse': 'combined',
            'monthly_forecasts': [
                {'month': 1, 'date': '2025-11', 'quantity': 950, 'revenue': 92625.00},
                {'month': 2, 'date': '2025-12', 'quantity': 980, 'revenue': 95550.00},
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

        # Insert one record per month (12 total)
        insert_query = """
            INSERT INTO forecast_accuracy
            (sku_id, forecast_date, forecast_period_start, forecast_period_end,
             predicted_demand, forecast_method, abc_class, xyz_class,
             seasonal_pattern, is_actual_recorded)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
        """

        monthly_forecasts = forecast_data.get('monthly_forecasts', [])
        method_used = forecast_data.get('method_used', 'unknown')

        for month_forecast in monthly_forecasts:
            # Parse date (format: '2025-11')
            forecast_period_date = datetime.strptime(month_forecast['date'], '%Y-%m')

            # Period is the whole month
            forecast_period_start = forecast_period_date.date()
            forecast_period_end = (forecast_period_date + relativedelta(months=1) - relativedelta(days=1)).date()

            predicted_qty = month_forecast['quantity']

            # Execute insert
            execute_query(
                insert_query,
                (sku_id, forecast_date, forecast_period_start, forecast_period_end,
                 predicted_qty, method_used, abc_class, xyz_class,
                 seasonal_pattern),
                fetch_all=False
            )

        logger.info(f"Recorded {len(monthly_forecasts)} forecast periods for SKU {sku_id}")
        return True

    except Exception as e:
        logger.error(f"Error recording forecast for {sku_id}: {e}", exc_info=True)
        return False
```

#### Step 1.2: Integrate Recording into Forecast Engine

**File**: `backend/forecasting.py`
**Function**: `save_forecast()` (lines 635-693)
**Action**: Add call after saving to forecast_details

```python
def save_forecast(self, forecast_data: Dict) -> bool:
    """
    Save forecast results to forecast_details table.

    MODIFIED: Now also records to forecast_accuracy for learning.

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

    # Debug logging
    print(f"[DEBUG V7.3] Saving forecast for {forecast_data['sku_id']}: "
          f"method={forecast_data['method_used']}, "
          f"growth_rate_source={forecast_data.get('growth_rate_source', 'NOT SET')}")

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

        # NEW: Record to forecast_accuracy for learning
        from backend.forecast_accuracy import record_forecast_for_accuracy_tracking

        record_forecast_for_accuracy_tracking(
            forecast_run_id=self.forecast_run_id,
            sku_id=forecast_data['sku_id'],
            warehouse=forecast_data['warehouse'],
            forecast_data=forecast_data
        )

        return True
    except Exception as e:
        print(f"Error saving forecast for {forecast_data['sku_id']}: {e}")
        return False
```

#### Step 1.3: Test Forecast Recording

**Test Script**: `backend/test_forecast_recording.py` (NEW FILE)

```python
"""
Test script to verify forecast recording to forecast_accuracy table.
"""

from backend.forecasting import ForecastEngine, create_forecast_run
from backend.database import execute_query

def test_forecast_recording():
    """Test that forecasts are being recorded to forecast_accuracy."""

    # Create test forecast run
    run_id = create_forecast_run(
        forecast_name="Accuracy Test - Recording",
        growth_assumption=0.05,
        warehouse='combined'
    )

    print(f"Created test forecast run: {run_id}")

    # Generate forecast for a single SKU
    engine = ForecastEngine(run_id, manual_growth_override=0.05)

    # Use UB-YTX14-BS (known good SKU from testing)
    test_sku = 'UB-YTX14-BS'

    try:
        forecast = engine.generate_forecast_for_sku(test_sku, warehouse='combined')
        success = engine.save_forecast(forecast)

        print(f"Forecast generation: {'SUCCESS' if success else 'FAILED'}")

        # Verify records in forecast_accuracy
        check_query = """
            SELECT COUNT(*) as record_count,
                   MIN(forecast_period_start) as first_period,
                   MAX(forecast_period_end) as last_period
            FROM forecast_accuracy
            WHERE sku_id = %s
              AND forecast_date = (SELECT forecast_date FROM forecast_runs WHERE id = %s)
        """

        result = execute_query(check_query, (test_sku, run_id), fetch_all=True)

        if result:
            print(f"\nRecords in forecast_accuracy: {result[0]['record_count']}")
            print(f"First period: {result[0]['first_period']}")
            print(f"Last period: {result[0]['last_period']}")

            if result[0]['record_count'] == 12:
                print("\n✅ TEST PASSED: All 12 monthly forecasts recorded!")
            else:
                print(f"\n❌ TEST FAILED: Expected 12 records, got {result[0]['record_count']}")

    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
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
Created test forecast run: 44
Forecast generation: SUCCESS

Records in forecast_accuracy: 12
First period: 2025-11-01
Last period: 2026-10-31

✅ TEST PASSED: All 12 monthly forecasts recorded!
```

#### Step 1.4: Verify Database State

**SQL Verification**:
```sql
-- Check forecast_accuracy has data
SELECT
    sku_id,
    COUNT(*) as total_periods,
    MIN(forecast_period_start) as first_month,
    MAX(forecast_period_end) as last_month,
    AVG(predicted_demand) as avg_predicted,
    forecast_method,
    confidence_score
FROM forecast_accuracy
WHERE forecast_date = (SELECT MAX(forecast_date) FROM forecast_runs)
GROUP BY sku_id, forecast_method
LIMIT 10;

-- Expected: 12 periods per SKU, is_actual_recorded = 0
```

---

## Phase 2: Monthly Accuracy Update (Comparison Engine)

**Goal**: Compare actual sales vs forecasts, calculate errors
**Effort**: 6-8 hours
**Priority**: HIGH

### Implementation Steps

#### Step 2.1: Create Monthly Update Function

**File**: `backend/forecast_accuracy.py` (append to existing file)

```python
def update_monthly_accuracy(target_month: Optional[str] = None) -> Dict:
    """
    Compare actual sales to forecast predictions for a specific month.

    This function runs monthly (typically on the 1st) to:
    1. Find forecast_accuracy records with is_actual_recorded = 0
    2. Look up actual sales from monthly_sales for that period
    3. Calculate errors: absolute_error, percentage_error, MAPE
    4. Update forecast_accuracy with actuals and errors

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
            'errors': []
        }

    Example:
        # Run on Nov 1st to update October actuals
        result = update_monthly_accuracy(target_month='2025-10')
    """
    from dateutil.relativedelta import relativedelta

    # Determine target month
    if target_month is None:
        # Default: previous month
        last_month = datetime.now() - relativedelta(months=1)
        target_month = last_month.strftime('%Y-%m')

    logger.info(f"Starting accuracy update for month: {target_month}")

    # Parse target month
    try:
        target_date = datetime.strptime(target_month, '%Y-%m')
        period_start = target_date.date()
        period_end = (target_date + relativedelta(months=1) - relativedelta(days=1)).date()
    except ValueError:
        logger.error(f"Invalid target_month format: {target_month}. Use YYYY-MM")
        return {'error': 'Invalid month format'}

    # Find unrecorded forecasts for this period
    find_forecasts_query = """
        SELECT
            fa.id,
            fa.sku_id,
            fa.forecast_period_start,
            fa.forecast_period_end,
            fa.predicted_demand,
            fa.forecast_method,
            fa.abc_class,
            fa.xyz_class
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
    # Use corrected_demand_burnaby + corrected_demand_kentucky for true demand
    actuals_query = """
        SELECT
            sku_id,
            (corrected_demand_burnaby + corrected_demand_kentucky) as actual_demand,
            (burnaby_sales + kentucky_sales) as actual_sales
        FROM monthly_sales
        WHERE year_month = %s
    """

    actuals = execute_query(actuals_query, (target_month,), fetch_all=True)

    # Create lookup dictionary for fast access
    actuals_dict = {
        row['sku_id']: {
            'actual_demand': float(row['actual_demand']),
            'actual_sales': int(row['actual_sales'])
        }
        for row in actuals
    }

    logger.info(f"Retrieved actuals for {len(actuals_dict)} SKUs")

    # Update each forecast record
    update_query = """
        UPDATE forecast_accuracy
        SET actual_demand = %s,
            absolute_error = %s,
            percentage_error = %s,
            absolute_percentage_error = %s,
            is_actual_recorded = 1
        WHERE id = %s
    """

    actuals_found = 0
    missing_actuals = 0
    errors_list = []
    mape_values = []

    for forecast in forecasts:
        sku_id = forecast['sku_id']
        predicted = float(forecast['predicted_demand'])

        if sku_id in actuals_dict:
            actual = actuals_dict[sku_id]['actual_demand']

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

            # Execute update
            execute_query(
                update_query,
                (actual, absolute_error, percentage_error,
                 absolute_percentage_error, forecast['id']),
                fetch_all=False
            )

            actuals_found += 1
            mape_values.append(absolute_percentage_error)

        else:
            # No actual sales data for this SKU this month
            # This can happen for new SKUs or SKUs with zero sales
            missing_actuals += 1
            errors_list.append(f"No actuals for SKU {sku_id}")

    # Calculate aggregate MAPE
    avg_mape = sum(mape_values) / len(mape_values) if mape_values else 0.0

    logger.info(f"Accuracy update complete: {actuals_found} updated, {missing_actuals} missing")
    logger.info(f"Average MAPE: {avg_mape:.2f}%")

    return {
        'month_updated': target_month,
        'total_forecasts': total_forecasts,
        'actuals_found': actuals_found,
        'missing_actuals': missing_actuals,
        'avg_mape': round(avg_mape, 2),
        'errors': errors_list[:10]  # First 10 errors
    }
```

#### Step 2.2: Create Scheduler/Cron Job

**Option A: Windows Task Scheduler** (if on Windows)

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

**Windows Task Scheduler Setup**:
```batch
REM Create batch file: run_accuracy_update.bat
@echo off
cd C:\Users\Arjay\Downloads\warehouse-transfer
C:\Users\Arjay\Downloads\warehouse-transfer\venv\Scripts\python.exe backend\run_monthly_accuracy_update.py
```

**Schedule**:
- Trigger: Monthly on 1st day at 2:00 AM
- Action: Run `run_accuracy_update.bat`

**Option B: Python Scheduler** (if server runs 24/7)

**File**: `backend/scheduler.py` (append to existing or create new)

```python
"""
Background scheduler for recurring forecast tasks.
"""

import schedule
import time
import logging
from backend.forecast_accuracy import update_monthly_accuracy

logger = logging.getLogger(__name__)

def scheduled_accuracy_update():
    """Wrapper for monthly accuracy update."""
    logger.info("Running scheduled accuracy update...")
    try:
        result = update_monthly_accuracy()
        logger.info(f"Scheduled update complete: {result}")
    except Exception as e:
        logger.error(f"Scheduled update failed: {e}", exc_info=True)

# Schedule monthly on 1st at 2:00 AM
schedule.every().month.at("02:00").do(scheduled_accuracy_update)

# Run scheduler loop (add to main.py or separate process)
def run_scheduler():
    """Run schedule loop."""
    logger.info("Forecast accuracy scheduler started")
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
```

#### Step 2.3: Add Manual Trigger API Endpoint

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
        Update statistics

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

#### Step 2.4: Test Monthly Update

**Test Script**: `backend/test_accuracy_update.py` (NEW FILE)

```python
"""
Test monthly accuracy update functionality.
"""

from backend.forecast_accuracy import update_monthly_accuracy
from backend.database import execute_query
from datetime import datetime
from dateutil.relativedelta import relativedelta

def test_accuracy_update():
    """Test accuracy update for a past month with known data."""

    # Choose a month with both forecasts and actuals
    # For example, if forecast was generated in Sept for Oct-Sept next year,
    # and we're now in Nov, we can test Oct update

    test_month = (datetime.now() - relativedelta(months=1)).strftime('%Y-%m')

    print(f"Testing accuracy update for: {test_month}")
    print("="*60)

    # Check initial state
    before_query = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_actual_recorded = 1 THEN 1 ELSE 0 END) as recorded
        FROM forecast_accuracy
        WHERE DATE_FORMAT(forecast_period_start, '%Y-%m') = %s
    """

    before = execute_query(before_query, (test_month,), fetch_all=True)

    if before:
        print(f"Before update:")
        print(f"  Total forecasts: {before[0]['total']}")
        print(f"  Already recorded: {before[0]['recorded']}")

    # Run update
    result = update_monthly_accuracy(target_month=test_month)

    print(f"\nUpdate Results:")
    print(f"  Month: {result['month_updated']}")
    print(f"  Total forecasts: {result['total_forecasts']}")
    print(f"  Actuals found: {result['actuals_found']}")
    print(f"  Missing actuals: {result['missing_actuals']}")
    print(f"  Average MAPE: {result['avg_mape']}%")

    # Check final state
    after = execute_query(before_query, (test_month,), fetch_all=True)

    if after:
        print(f"\nAfter update:")
        print(f"  Total forecasts: {after[0]['total']}")
        print(f"  Now recorded: {after[0]['recorded']}")

    # Show sample accuracy records
    sample_query = """
        SELECT
            sku_id,
            predicted_demand,
            actual_demand,
            absolute_percentage_error as mape,
            forecast_method
        FROM forecast_accuracy
        WHERE DATE_FORMAT(forecast_period_start, '%Y-%m') = %s
          AND is_actual_recorded = 1
        ORDER BY absolute_percentage_error ASC
        LIMIT 5
    """

    samples = execute_query(sample_query, (test_month,), fetch_all=True)

    print(f"\nTop 5 Most Accurate Forecasts:")
    print(f"{'SKU':<15} {'Predicted':<10} {'Actual':<10} {'MAPE':<8} {'Method':<20}")
    print("-"*70)

    for row in samples:
        print(f"{row['sku_id']:<15} {row['predicted_demand']:<10.1f} "
              f"{row['actual_demand']:<10.1f} {row['mape']:<8.2f}% {row['forecast_method']:<20}")

    print("\n✅ Test complete!")

if __name__ == "__main__":
    test_accuracy_update()
```

**Run Test**:
```bash
python -m backend.test_accuracy_update
```

---

## Phase 3: Learning Mechanisms (Self-Improvement)

**Goal**: Auto-adjust forecasting parameters based on errors
**Effort**: 8-10 hours
**Priority**: MEDIUM-HIGH

### Learning Algorithms

#### 3.1: Growth Rate Adjustment

**Concept**: If forecasts consistently over/under-predict, adjust growth assumptions

**File**: `backend/forecast_learning.py` (NEW FILE)

```python
"""
Forecast Learning Module

Implements self-improving algorithms that adjust forecasting parameters
based on observed accuracy patterns.
"""

from typing import Dict, List, Tuple
from backend.database import execute_query
import statistics
import logging

logger = logging.getLogger(__name__)


def adjust_growth_rates_from_errors() -> Dict:
    """
    Analyze forecast errors to adjust growth rate assumptions.

    Logic:
    - If SKU consistently OVER-forecasts: reduce growth rate
    - If SKU consistently UNDER-forecasts: increase growth rate
    - Only adjust if pattern is consistent (3+ months, same direction)

    Returns:
        Dictionary with adjustment statistics
    """
    logger.info("Starting growth rate adjustment analysis...")

    # Find SKUs with consistent forecast bias
    bias_query = """
        SELECT
            sku_id,
            COUNT(*) as forecast_count,
            AVG(percentage_error) as avg_bias,
            STDDEV(percentage_error) as bias_std_dev,
            SUM(CASE WHEN percentage_error > 0 THEN 1 ELSE 0 END) as over_forecast_count,
            SUM(CASE WHEN percentage_error < 0 THEN 1 ELSE 0 END) as under_forecast_count,
            AVG(ABS(percentage_error)) as avg_mape
        FROM forecast_accuracy
        WHERE is_actual_recorded = 1
          AND forecast_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
        GROUP BY sku_id
        HAVING COUNT(*) >= 3
          AND ABS(avg_bias) > 10  -- Consistent bias > 10%
        ORDER BY ABS(avg_bias) DESC
    """

    biased_skus = execute_query(bias_query, fetch_all=True)

    logger.info(f"Found {len(biased_skus)} SKUs with consistent forecast bias")

    adjustments_made = 0

    for sku in biased_skus:
        sku_id = sku['sku_id']
        avg_bias = float(sku['avg_bias'])

        # Determine adjustment direction
        if avg_bias > 0:
            # Over-forecasting: actual > predicted (positive bias)
            # Need to INCREASE growth rate
            adjustment = min(0.05, avg_bias / 200)  # Cap at 5% adjustment
            direction = 'increase'
        else:
            # Under-forecasting: actual < predicted (negative bias)
            # Need to DECREASE growth rate
            adjustment = max(-0.05, avg_bias / 200)  # Cap at -5% adjustment
            direction = 'decrease'

        # Log the adjustment (don't actually modify SKU table yet)
        # Instead, store in a new `forecast_adjustments` table for audit

        log_query = """
            INSERT INTO forecast_adjustments
            (sku_id, adjustment_type, original_value, adjusted_value,
             adjustment_reason, adjusted_by, adjusted_at)
            VALUES (%s, 'growth_rate', NULL, %s, %s, 'learning_system', NOW())
        """

        reason = f"Consistent {direction} bias detected: avg_bias={avg_bias:.2f}%, " \
                f"sample_size={sku['forecast_count']}, suggested_adjustment={adjustment:.3f}"

        try:
            execute_query(log_query, (sku_id, adjustment, reason), fetch_all=False)
            adjustments_made += 1

            logger.info(f"Adjustment logged for {sku_id}: {direction} by {adjustment:.3f}")

        except Exception as e:
            logger.error(f"Failed to log adjustment for {sku_id}: {e}")

    return {
        'skus_analyzed': len(biased_skus),
        'adjustments_logged': adjustments_made,
        'message': 'Growth rate adjustments logged to forecast_adjustments table'
    }
```

#### 3.2: Method Performance Comparison

**Concept**: Identify best-performing forecasting methods by ABC/XYZ class

```python
def analyze_method_performance() -> Dict:
    """
    Compare accuracy of different forecasting methods.

    Returns:
        Performance metrics by method and ABC/XYZ class
    """
    logger.info("Analyzing forecasting method performance...")

    method_query = """
        SELECT
            forecast_method,
            abc_class,
            xyz_class,
            COUNT(*) as forecast_count,
            AVG(absolute_percentage_error) as avg_mape,
            STDDEV(absolute_percentage_error) as mape_std_dev,
            MIN(absolute_percentage_error) as best_mape,
            MAX(absolute_percentage_error) as worst_mape,
            SUM(CASE WHEN absolute_percentage_error < 10 THEN 1 ELSE 0 END) as excellent_count,
            SUM(CASE WHEN absolute_percentage_error BETWEEN 10 AND 20 THEN 1 ELSE 0 END) as good_count,
            SUM(CASE WHEN absolute_percentage_error > 20 THEN 1 ELSE 0 END) as poor_count
        FROM forecast_accuracy
        WHERE is_actual_recorded = 1
          AND abc_class IS NOT NULL
          AND xyz_class IS NOT NULL
        GROUP BY forecast_method, abc_class, xyz_class
        HAVING COUNT(*) >= 5
        ORDER BY abc_class, xyz_class, avg_mape ASC
    """

    results = execute_query(method_query, fetch_all=True)

    # Identify best method per ABC/XYZ combination
    best_methods = {}

    for row in results:
        classification = f"{row['abc_class']}{row['xyz_class']}"

        if classification not in best_methods:
            best_methods[classification] = {
                'method': row['forecast_method'],
                'mape': float(row['avg_mape']),
                'sample_size': row['forecast_count']
            }
        elif float(row['avg_mape']) < best_methods[classification]['mape']:
            # Found better method
            best_methods[classification] = {
                'method': row['forecast_method'],
                'mape': float(row['avg_mape']),
                'sample_size': row['forecast_count']
            }

    logger.info(f"Identified best methods for {len(best_methods)} classifications")

    return {
        'total_method_classifications': len(results),
        'best_methods_by_class': best_methods,
        'full_results': results
    }
```

#### 3.3: Problem SKU Detection

**Concept**: Flag SKUs with chronically poor forecast accuracy

```python
def identify_problem_skus(mape_threshold: float = 30.0) -> List[Dict]:
    """
    Identify SKUs with consistently poor forecast accuracy.

    Args:
        mape_threshold: MAPE above which SKU is considered problematic (default: 30%)

    Returns:
        List of problematic SKUs with diagnostic info
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
            recommendations.append("High volatility (XYZ=Z): Consider shorter forecast window")

        if abs(problem['avg_bias']) > 20:
            if problem['avg_bias'] > 0:
                recommendations.append("Consistent over-forecasting: Reduce growth rate")
            else:
                recommendations.append("Consistent under-forecasting: Increase growth rate")

        if problem['seasonal_pattern'] == 'unknown':
            recommendations.append("No seasonal pattern: Verify sales history length")

        problem['recommendations'] = recommendations

    return problems
```

#### 3.4: Automated Learning Job

**File**: `backend/run_forecast_learning.py` (NEW FILE)

```python
"""
Run forecast learning algorithms after accuracy updates.
"""

from backend.forecast_learning import (
    adjust_growth_rates_from_errors,
    analyze_method_performance,
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

    # Step 1: Adjust growth rates
    logger.info("\n[1/3] Adjusting growth rates...")
    growth_result = adjust_growth_rates_from_errors()
    logger.info(f"Growth adjustments: {growth_result}")

    # Step 2: Analyze method performance
    logger.info("\n[2/3] Analyzing method performance...")
    method_result = analyze_method_performance()
    logger.info(f"Best methods identified: {len(method_result['best_methods_by_class'])}")

    # Step 3: Identify problem SKUs
    logger.info("\n[3/3] Identifying problem SKUs...")
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
        'problem_skus': len(problems)
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_learning_cycle()
```

---

## Phase 4: Reporting Dashboard & API

**Goal**: Visualize accuracy metrics, trends, and problems
**Effort**: 6-8 hours
**Priority**: MEDIUM

### API Endpoints

**File**: `backend/forecasting_api.py` (append)

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

    # Get monthly trend
    trend_query = """
        SELECT
            DATE_FORMAT(forecast_period_start, '%Y-%m') as month,
            AVG(absolute_percentage_error) as mape,
            COUNT(*) as forecast_count
        FROM forecast_accuracy
        WHERE is_actual_recorded = 1
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
    completed = [h for h in history if h['is_actual_recorded']]

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
```

### Frontend Dashboard

**File**: `frontend/forecast-accuracy.html` (NEW FILE)

Due to length constraints, I'll provide the outline:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <title>Forecast Accuracy Dashboard</title>
    <!-- Bootstrap 5, Chart.js -->
</head>
<body>
    <div class="container-fluid">
        <!-- Header -->
        <div class="row">
            <h1>Forecast Accuracy Dashboard</h1>
        </div>

        <!-- Key Metrics Cards -->
        <div class="row">
            <div class="col-md-3">
                <div class="card">
                    <h3>Overall MAPE</h3>
                    <h2 id="overall-mape">--</h2>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <h3>Forecasts Completed</h3>
                    <h2 id="completed-count">--</h2>
                </div>
            </div>
            <!-- More metric cards -->
        </div>

        <!-- Charts -->
        <div class="row">
            <div class="col-md-6">
                <canvas id="mape-trend-chart"></canvas>
            </div>
            <div class="col-md-6">
                <canvas id="abc-xyz-heatmap"></canvas>
            </div>
        </div>

        <!-- Problem SKUs Table -->
        <div class="row">
            <table id="problem-skus-table" class="table">
                <thead>
                    <tr>
                        <th>SKU</th>
                        <th>Description</th>
                        <th>MAPE</th>
                        <th>Bias</th>
                        <th>Recommendations</th>
                    </tr>
                </thead>
                <tbody id="problem-skus-body">
                    <!-- Populated via JavaScript -->
                </tbody>
            </table>
        </div>
    </div>

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
        showAlert('danger', 'Failed to load accuracy data');
    }
}

function renderTrendChart(trendData) {
    const ctx = document.getElementById('mape-trend-chart').getContext('2d');

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: trendData.map(d => d.month),
            datasets: [{
                label: 'Average MAPE',
                data: trendData.map(d => d.mape),
                borderColor: 'rgb(75, 192, 192)',
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

// More rendering functions...
```

---

## Database Schema Changes

### New Tables Needed

```sql
-- None! forecast_accuracy table already exists
-- But add index for performance:

ALTER TABLE forecast_accuracy
ADD INDEX idx_period_recorded (forecast_period_start, is_actual_recorded);

ALTER TABLE forecast_accuracy
ADD INDEX idx_sku_recorded (sku_id, is_actual_recorded, forecast_period_start);

-- Optional: Add forecast_adjustments table if not exists
CREATE TABLE IF NOT EXISTS forecast_adjustments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku_id VARCHAR(50) NOT NULL,
    adjustment_type ENUM('growth_rate', 'seasonal_factor', 'method_change', 'manual') NOT NULL,
    original_value DECIMAL(10,2),
    adjusted_value DECIMAL(10,2),
    adjustment_reason TEXT,
    adjusted_by VARCHAR(100) DEFAULT 'learning_system',
    adjusted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
    INDEX idx_sku_adjustments (sku_id, adjusted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_forecast_accuracy.py
def test_record_forecast():
    """Test forecast recording creates 12 records."""
    # Create test forecast
    # Verify 12 records in forecast_accuracy
    # Verify is_actual_recorded = 0
    pass

def test_accuracy_update():
    """Test accuracy update calculates errors correctly."""
    # Create test data with known forecast/actual
    # Run update
    # Verify MAPE calculated correctly
    pass

def test_growth_adjustment():
    """Test growth rate adjustment logic."""
    # Create SKUs with consistent bias
    # Run learning algorithm
    # Verify adjustments logged
    pass
```

### Integration Tests

```python
# tests/test_forecast_learning_flow.py
def test_complete_learning_cycle():
    """Test end-to-end learning flow."""
    # 1. Generate forecast
    # 2. Simulate actual sales
    # 3. Run accuracy update
    # 4. Run learning algorithms
    # 5. Verify improvements in next forecast
    pass
```

---

## Deployment Checklist

### Phase 1 Deployment
- [ ] Add `backend/forecast_accuracy.py`
- [ ] Modify `backend/forecasting.py` → `save_forecast()`
- [ ] Run test: `python -m backend.test_forecast_recording`
- [ ] Verify forecast_accuracy has 12 records per SKU
- [ ] Commit to git: "feat: Add forecast recording for accuracy tracking"

### Phase 2 Deployment
- [ ] Implement `update_monthly_accuracy()` function
- [ ] Create scheduler script (`run_monthly_accuracy_update.py`)
- [ ] Set up Windows Task Scheduler or cron job
- [ ] Run test: `python -m backend.test_accuracy_update`
- [ ] Verify actuals populated for past month
- [ ] Commit to git: "feat: Add monthly accuracy update job"

### Phase 3 Deployment
- [ ] Add `backend/forecast_learning.py`
- [ ] Implement learning algorithms
- [ ] Run test: `python -m backend.run_forecast_learning`
- [ ] Verify adjustments logged to forecast_adjustments
- [ ] Commit to git: "feat: Add forecast learning mechanisms"

### Phase 4 Deployment
- [ ] Add API endpoints to `forecasting_api.py`
- [ ] Create `frontend/forecast-accuracy.html`
- [ ] Create `frontend/js/forecast-accuracy.js`
- [ ] Test dashboard loads and displays data
- [ ] Add navigation link from main dashboard
- [ ] Commit to git: "feat: Add forecast accuracy dashboard"

---

## Success Metrics

### Immediate (Phase 1-2)
- All forecasts recorded to forecast_accuracy table
- Monthly accuracy updates running successfully
- 90%+ of forecasts have actuals matched

### Short-term (Phase 3, 1-2 months)
- Growth rate adjustments improve MAPE by 5%+
- Problem SKUs identified and flagged
- Method performance comparison available

### Long-term (Phase 4, 3-6 months)
- Overall MAPE improves from baseline to <20%
- A-class items achieve MAPE <15%
- Forecast bias (over/under) within ±5%
- User trust in forecasts increases (measured via adoption)

---

## Troubleshooting

### Common Issues

**Issue**: No forecasts in forecast_accuracy table
**Solution**: Check if `record_forecast_for_accuracy_tracking()` is being called in `save_forecast()`

**Issue**: Accuracy update finds no actuals
**Solution**: Verify monthly_sales has data for target month, check date format matching

**Issue**: MAPE calculations show 0% for all SKUs
**Solution**: Check if actual_demand is being populated, verify calculation logic

**Issue**: Learning algorithms make no adjustments
**Solution**: Verify forecast_accuracy has is_actual_recorded=1 records, check bias thresholds

---

## Future Enhancements

### Phase 5: Advanced Learning (Future)
- Machine learning models (ARIMA, Prophet, LSTM)
- External factor integration (holidays, promotions, weather)
- Confidence interval predictions
- Automated A/B testing of methods

### Phase 6: Collaboration Features (Future)
- User feedback on forecast accuracy
- Manual adjustment tracking and learning
- Forecast approval workflows
- Collaborative planning tools

---

## Appendix: Key Calculations

### MAPE (Mean Absolute Percentage Error)
```python
MAPE = (|Actual - Predicted| / Actual) * 100

# Average MAPE across SKUs:
Avg_MAPE = Σ(MAPE) / n
```

### Forecast Bias
```python
Bias = (Actual - Predicted) / Actual * 100

# Positive bias: Over-forecasting (predicted < actual)
# Negative bias: Under-forecasting (predicted > actual)
```

### Growth Rate Adjustment
```python
# If consistent over-forecast (positive bias):
New_Growth_Rate = Old_Growth_Rate + (Avg_Bias / 200)

# If consistent under-forecast (negative bias):
New_Growth_Rate = Old_Growth_Rate + (Avg_Bias / 200)

# Cap adjustments at ±5% per cycle
Adjustment = max(-0.05, min(0.05, Adjustment))
```

---

## Contacts & Support

**Implementation Questions**: Refer to existing codebase patterns in `backend/forecasting.py`
**Database Schema**: See `database/schema.sql` and existing views
**Testing**: Follow patterns in `backend/test_*.py` files
**Deployment**: Use existing FastAPI patterns in `backend/main.py`

---

**Document Version**: 1.0
**Last Updated**: 2025-10-20
**Status**: Ready for Implementation
**Estimated Total Effort**: 24-32 hours across 4 phases
