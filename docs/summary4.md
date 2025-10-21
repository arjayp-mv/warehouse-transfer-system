Project Context

  Building a forecast learning system that records predictions, compares them to actual sales, calculates accuracy metrics
  (MAPE), and automatically improves future forecasts. This creates a feedback loop so the forecasting system learns from its      
  mistakes.

  What Was Completed Successfully

  Database Phase (TASK-511 to TASK-515) ✅ COMPLETE

  Enhanced forecast_accuracy table with 6 new columns:
  - stockout_affected BOOLEAN - Mark periods where stockouts caused under-sales
  - volatility_at_forecast DECIMAL(5,2) - SKU volatility (coefficient_variation) at time of forecast
  - data_quality_score DECIMAL(3,2) - Data quality (0-1) at time of forecast
  - seasonal_confidence_at_forecast DECIMAL(5,4) - Seasonal pattern confidence at time of forecast
  - learning_applied BOOLEAN - Track if learning adjustments were applied
  - learning_applied_date TIMESTAMP - When adjustments were applied

  Created forecast_learning_adjustments table:
  - Tracks system-learned adjustments (separate from manual user adjustments in forecast_adjustments table)
  - Fields: id, sku_id, adjustment_type (ENUM: growth_rate, seasonal_factor, method_switch, volatility_adjustment,
  category_default)
  - Fields: original_value, adjusted_value, adjustment_magnitude, learning_reason, confidence_score
  - Fields: mape_before, mape_expected, applied, applied_date, created_at
  - Foreign key to skus(sku_id) with CASCADE

  Files Created:
  - database/add_forecast_learning_schema.sql - Migration script (applied successfully)

  Files Modified:
  - database/schema.sql - Updated with V8.0 schema (lines 72-105 for forecast_accuracy, lines 134-153 for
  forecast_learning_adjustments)

  Phase 1: Enhanced Forecast Recording (TASK-516 to TASK-522) ✅ COMPLETE

  Created backend/forecast_accuracy.py (206 lines):
  - Module handles recording forecasts with comprehensive context
  - Function: record_forecast_for_accuracy_tracking(forecast_run_id, sku_id, warehouse, forecast_data) -> bool
  - Records 12 monthly forecasts per SKU to forecast_accuracy table
  - Captures context at time of forecast from existing tables:
    - sku_demand_stats → volatility (coefficient_variation), data quality
    - seasonal_factors → seasonal confidence (confidence_level)
    - seasonal_patterns_summary → pattern strength
  - CRITICAL FIX: For 'combined' warehouse (burnaby + kentucky total demand), uses AVG() to average metrics from both
  warehouses. For single warehouse, uses that warehouse's specific data.
  - Error handling: Failures are logged but non-critical (won't prevent forecast from saving to forecast_details)

  Modified backend/forecasting.py:
  - Line 23: Added import logging
  - Line 27: Added logger = logging.getLogger(__name__)
  - Lines 635-714: Modified save_forecast() method:
    - After saving to forecast_details (existing functionality)
    - Imports and calls record_forecast_for_accuracy_tracking()
    - Logs success/failure (non-critical - forecast still saves if accuracy recording fails)

  Created backend/test_forecast_recording.py:
  - Test script that creates a forecast run, generates forecast for SKU 'UB-YTX14-BS', verifies 12 records inserted
  - TEST PASSES: All 12 records created with full context captured:
    - Volatility: 0.25
    - Data Quality: 1.00
    - Seasonal Confidence: 0.75-0.92 (varies by month)

  Current State

  All forecasts now automatically record to forecast_accuracy table when generated. The system creates 12 monthly records per      
  SKU with:
  - Predicted demand for each month
  - Forecast method used (weighted_ma_3mo, seasonal_adj, etc.)
  - ABC/XYZ classification at time of forecast
  - Volatility, data quality, seasonal confidence context
  - is_actual_recorded = 0 (ready for Phase 2 monthly comparison)

  Database has existing infrastructure ready to use:
  - stockout_dates table with is_resolved tracking
  - monthly_sales table with corrected_demand_burnaby and corrected_demand_kentucky (already stockout-adjusted)
  - sku_demand_stats with coefficient_variation, data_quality_score
  - seasonal_factors with confidence_level
  - skus table with growth_status (viral/declining/normal), seasonal_pattern

  What Still Needs to Be Done

  Phase 2: Stockout-Aware Accuracy Update (TASK-526 to TASK-538) - NOT STARTED

  Estimated: 8-10 hours

  Objective: Monthly job to compare actual sales vs forecasts, calculate errors, mark stockout-affected periods.

  Key Tasks:
  1. Implement update_monthly_accuracy() function in backend/forecast_accuracy.py:
    - Takes target_month parameter (e.g., "2025-10" or None for last month)
    - Finds all forecasts in forecast_accuracy where forecast_period_start matches target month and is_actual_recorded = 0
    - For each forecast, check stockout_dates table for stockouts during forecast period
    - Get actual demand from monthly_sales.corrected_demand_burnaby + corrected_demand_kentucky for target month
    - CRITICAL LOGIC: If stockout occurred AND actual < predicted, mark stockout_affected = TRUE but DON'T count error in MAPE     
  (supply constraint, not bad forecast)
    - If no stockout OR actual >= predicted, calculate errors normally:
        - absolute_error = ABS(actual - predicted)
      - percentage_error = (actual - predicted) / actual * 100
      - absolute_percentage_error = ABS(percentage_error)
    - Update forecast_accuracy record with actual_demand, errors, stockout_affected flag, is_actual_recorded = 1
    - Return summary dict: {month_updated, total_forecasts, actuals_found, missing_actuals, avg_mape, stockout_affected_count}     
  2. Create monthly cron job/scheduled task to run update_monthly_accuracy() automatically
  3. Create API endpoints in backend/forecasting_accuracy_api.py:
    - POST /api/forecast-accuracy/update-month (manual trigger for testing)
    - GET /api/forecast-accuracy/summary (overall accuracy metrics)
    - GET /api/forecast-accuracy/by-sku/{sku_id} (SKU-level accuracy trends)
  4. Create test script backend/test_accuracy_update.py:
    - Insert historical forecast_accuracy records with known values
    - Insert corresponding monthly_sales actuals
    - Run update_monthly_accuracy()
    - Verify MAPE calculation, stockout marking logic

  Phase 3: Multi-Dimensional Learning (TASK-539 to TASK-555) - NOT STARTED

  Estimated: 10-12 hours

  Objective: Learning algorithms that auto-adjust forecast parameters based on accuracy patterns.

  Key Implementation: Create backend/forecast_learning.py with ForecastLearningEngine class:

  ABC/XYZ-Specific Learning Rates (from docs/FORECAST_LEARNING_ENHANCED_PLAN.md lines 486-507):
  learning_rates = {
      'AX': {'growth': 0.02, 'seasonal': 0.05},  # Stable, careful adjustments
      'AY': {'growth': 0.03, 'seasonal': 0.08},
      'AZ': {'growth': 0.05, 'seasonal': 0.10},
      'BX': {'growth': 0.03, 'seasonal': 0.06},
      'BY': {'growth': 0.04, 'seasonal': 0.09},
      'BZ': {'growth': 0.07, 'seasonal': 0.12},
      'CX': {'growth': 0.05, 'seasonal': 0.08},
      'CY': {'growth': 0.08, 'seasonal': 0.12},
      'CZ': {'growth': 0.10, 'seasonal': 0.15},  # Volatile, aggressive learning
  }

  Learning Logic:
  1. Query forecast_accuracy for SKUs with is_actual_recorded = 1 and learning_applied = 0
  2. Calculate average MAPE, bias (consistent over/under-forecasting) for each SKU
  3. If bias detected (e.g., 3+ months of over-forecasting), recommend adjustment:
    - Over-forecasting: Reduce growth rate or seasonal factors
    - Under-forecasting: Increase growth rate or seasonal factors
  4. Adjustment magnitude = bias * learning_rate[ABC_XYZ_class]
  5. Insert recommendation to forecast_learning_adjustments with:
    - applied = FALSE (pending approval)
    - confidence_score based on data quality, consistency of error direction
    - learning_reason explaining why adjustment is recommended
    - mape_expected (simulated MAPE after adjustment)
  6. High-confidence adjustments (>0.8) can be auto-applied, low-confidence require approval

  Phase 4: Reporting Dashboard (TASK-556 to TASK-568) - NOT STARTED

  Estimated: 6-8 hours

  Create frontend dashboard frontend/static/forecast-accuracy.html:
  - Overall accuracy metrics cards (avg MAPE, total forecasts, learning adjustments applied)
  - MAPE trend chart over time
  - SKU performance table (sortable by MAPE, filterable by ABC/XYZ)
  - Learning activity log (recent adjustments)
  - Stockout-affected forecast count

  Create API endpoints in backend/forecasting_accuracy_api.py:
  - GET /api/forecast-accuracy/dashboard-metrics
  - GET /api/forecast-accuracy/mape-trends (time series data)
  - GET /api/forecast-accuracy/problem-skus (high MAPE SKUs needing attention)
  - GET /api/forecast-accuracy/learning-history

  Phase 5: Advanced Features (TASK-569 to TASK-580) - DEFERRED

  Estimated: 12-15 hours when needed

  Real-time learning triggers, A/B testing, advanced analytics (deferred until MVP validated).

  Key Files & Locations

  Reference Documentation:
  - docs/FORECAST_LEARNING_ENHANCED_PLAN.md - Complete 1,700-line implementation guide with full code examples
  - docs/TASKS.md - Lines 885-1477 contain V8.0 detailed task breakdown (70 tasks)
  - docs/claudesuggestion.md - Expert recommendations that were incorporated

  Existing Code to Reference:
  - backend/forecasting.py - Main forecasting engine (lines 635-714 show how save_forecast() integrates accuracy recording)        
  - backend/forecast_accuracy.py - Phase 1 complete reference implementation
  - backend/database.py - Database execute_query() function
  - backend/seasonal_calculator.py - Seasonal pattern functions

  Database Tables:
  - forecast_accuracy - Enhanced with V8.0 fields (currently receiving forecast data)
  - forecast_learning_adjustments - Empty, ready for Phase 3
  - stockout_dates - Use for stockout-aware logic
  - monthly_sales - Use corrected_demand fields for actuals
  - sku_demand_stats - Volatility and data quality metrics
  - seasonal_factors - Seasonal confidence per month

  Critical Implementation Notes

  1. 'combined' warehouse handling: Always average burnaby + kentucky metrics (see backend/forecast_accuracy.py lines 115-151)     
  2. Stockout-aware accuracy logic:
    - If stockout_days > 0 during forecast period AND actual < predicted → mark stockout_affected = TRUE, exclude from MAPE        
    - Rationale: Low sales due to supply constraint, not bad forecast
  3. MAPE Calculation:
    - Only include forecasts where stockout_affected = FALSE
    - MAPE = AVG(ABS((actual - predicted) / actual) * 100)
  4. Learning Rate Philosophy:
    - AX (high-value, stable): Careful 2% growth adjustments - mistakes are costly
    - CZ (low-value, volatile): Aggressive 10% adjustments - forecasts are already erratic
  5. Non-breaking changes: All Phase 1 work is non-critical - forecast system still works if accuracy recording fails

  Testing Commands

  # Test Phase 1 (forecast recording)
  cd C:\Users\Arjay\Downloads\warehouse-transfer
  python -m backend.test_forecast_recording

  # Expected: "TEST PASSED: All 12 monthly forecasts recorded with context!"

  # When Phase 2 complete, test accuracy update
  python -m backend.test_accuracy_update

  # Verify database state
  "C:\xampp\mysql\bin\mysql.exe" -u root warehouse_transfer -e "SELECT COUNT(*), AVG(volatility_at_forecast), 
  AVG(data_quality_score) FROM forecast_accuracy WHERE is_actual_recorded = 0;"

  Project Standards (from CLAUDE.md)

  - No emojis in code or documentation
  - Comprehensive docstrings: All functions need Args, Returns, Raises, Examples
  - Error handling: Try-except with detailed logging
  - Performance: Target <20 seconds for 1,768 SKUs
  - Testing: Always use Playwright MCP for UI testing when available
  - Task tracking: Update docs/TASKS.md with completed tasks

  Next Immediate Steps for New Claude Instance

  1. Read docs/FORECAST_LEARNING_ENHANCED_PLAN.md lines 595-850 for Phase 2 complete implementation
  2. Start with TASK-526: Implement update_monthly_accuracy() function
  3. Reference existing record_forecast_for_accuracy_tracking() in backend/forecast_accuracy.py as code pattern
  4. Use stockout-aware logic: Check stockout_dates table before penalizing forecasts
  5. Test with historical data before deploying monthly job

  Total Remaining Work: ~24-30 hours for complete MVP (Phases 2-4)
