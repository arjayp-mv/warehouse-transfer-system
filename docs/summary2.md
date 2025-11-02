     Implementation Plan - Task Range: TASK-593 to TASK-619 (27 tasks)

     ---
     CRITICAL NOTICE: TASKS.md File Size

     Current TASKS.md is 2514 lines (exceeds 400-line limit from CLAUDE.md by 6x).
     Action Required: After V10.0 completion, archive V7.0-V9.0 detailed tasks to TASKS_ARCHIVE_V7-V9.md

     ---
     Phase 1: Critical Fixes & API Endpoints (TASK-593 to TASK-603) - 4-6 hours

     Backend API Development (3-4 hours)

     TASK-593: Create backend/supplier_ordering_sku_details.py module
     - Purpose: Centralize SKU detail data aggregation (separation of concerns)
     - File size target: 250-300 lines max
     - Functions: get_pending_orders(), get_forecast_data(), get_stockout_history()
     - Follow execute_query pattern (PyMySQL with DictCursor)
     - No calculations on data fetch (pre-calculated data only)

     TASK-594: Implement GET /api/pending-orders/sku/{sku_id} endpoint
     - Add to backend/supplier_ordering_api.py (check file size - if >400 lines, split first)
     - Return time-phased pending orders (overdue, imminent, covered, future)
     - Include confidence scoring from supplier_lead_times.reliability_score
     - Response pagination: max 50 pending orders per SKU
     - Database query optimization: single query with LEFT JOINs

     TASK-595: Implement GET /api/forecasts/sku/{sku_id}/latest endpoint
     - Add to backend/supplier_ordering_api.py (check file size)
     - Query forecast_details table for 12-month projections
     - Include forecast_learning_adjustments.adjusted_value if applied=TRUE
     - Join with forecast_runs to get latest run_id
     - Return format: monthly data points with learning adjustments highlighted

     TASK-596: Implement GET /api/stockouts/sku/{sku_id} endpoint
     - Add to backend/supplier_ordering_api.py (check file size)
     - Query stockout_dates and stockout_patterns tables
     - Include pattern detection (from stockout_patterns.stockout_pattern_detected)
     - Show pattern_type if detected (seasonal, chronic, supply_issue)
     - Pagination: max 50 stockout records

     TASK-597: Add GET /api/supplier-orders/export/csv endpoint
     - Simple CSV export using Python csv module
     - Same data as Excel export, different format
     - Headers: All 29 fields from supplier_order_confirmations
     - File size: Under 100 lines (simple conversion)

     TASK-598: Backend error handling and validation
     - Add try-except blocks for all new endpoints
     - Validate sku_id exists before queries
     - Return 404 if SKU not found
     - Return 500 with error message on database errors
     - Add logging for all API calls

     Backend Testing (1 hour)

     TASK-599: Create backend/test_sku_details_api.py test script
     - Test all 3 new SKU detail endpoints
     - Verify response formats match frontend expectations
     - Test with valid SKU IDs (from test data)
     - Test with invalid SKU IDs (404 handling)
     - Test CSV export format and content

     TASK-600: Performance testing for new endpoints
     - Target: All endpoints respond in <500ms
     - Test with SKUs having 50+ pending orders
     - Test with SKUs having 12+ months of forecasts
     - Verify no N+1 query problems
     - Check database query execution time

     Frontend Integration (1-2 hours)

     TASK-601: Update frontend/supplier-ordering.js modal tab functions
     - Fix loadPendingTab() to call new /api/pending-orders/sku/{sku_id}
     - Fix loadForecastTab() to call new /api/forecasts/sku/{sku_id}/latest
     - Fix loadStockoutTab() to call new /api/stockouts/sku/{sku_id}
     - Add proper error handling (user-friendly messages)
     - Add loading indicators during fetch

     TASK-602: Implement Chart.js visualization for forecast tab
     - Line chart showing 12-month forecast projection
     - Highlight months with learning adjustments applied
     - Include base forecast vs adjusted forecast comparison
     - Color coding: blue (base), green (learning-adjusted)
     - Chart.js configuration: responsive, tooltips with details

     TASK-603: Add CSV export button to frontend
     - Add button next to Excel export in navbar
     - JavaScript function: exportToCSV()
     - Trigger download using Blob API
     - Same filters applied as current view
     - No changes to supplier-ordering.html (use existing button slot)

     ---
     Phase 2: Intelligence Layer (TASK-604 to TASK-612) - 2-3 hours

     Forecast Integration (1.5 hours)

     TASK-604: Refactor demand source in supplier_ordering_calculations.py
     - CRITICAL: Change from monthly_sales to forecast_details
     - Update determine_monthly_order_timing() function (lines 305-435)
     - New query: SELECT avg_monthly_qty FROM forecast_details WHERE forecast_run_id = latest
     - Fallback: Use monthly_sales.corrected_demand if no forecast exists
     - File already 573 lines - ensure changes don't exceed 600 lines

     TASK-605: Integrate forecast learning adjustments
     - Join forecast_learning_adjustments table in TASK-604 query
     - Use adjusted_value if applied=TRUE, otherwise use avg_monthly_qty
     - Add field to supplier_order_confirmations: learning_adjusted BOOLEAN
     - Update pending_breakdown JSON to include "using_learning_adjustment": true/false
     - Document which SKUs benefited from learning

     TASK-606: Add forecast metadata to order confirmations
     - New fields in supplier_order_confirmations:
       - forecast_run_id INT (which forecast was used)
       - forecast_method VARCHAR(50) (exponential_smoothing, linear_regression, etc.)
     - Database migration: add columns with default NULL
     - Update INSERT query in generate_monthly_recommendations()

     Seasonal Adjustments (1 hour)

     TASK-607: Create seasonal adjustment helper in supplier_ordering_calculations.py
     - Function: adjust_safety_stock_for_seasonality(sku_id, warehouse, base_safety_stock, order_month)
     - Query seasonal_patterns table for seasonal_strength and month factors
     - Apply adjustment if seasonal_strength > 0.3 (significant seasonality)
     - Formula: adjusted_ss = base_safety_stock * month_factor if factor > 1.2
     - Return: (adjusted_safety_stock, seasonal_adjustment_applied BOOLEAN)

     TASK-608: Integrate seasonal adjustments into safety stock calculation
     - Update calculate_safety_stock_monthly() function (lines 230-302)
     - Call adjust_safety_stock_for_seasonality() after base calculation
     - Store seasonal adjustment in pending_breakdown JSON
     - Add field: seasonal_factor_applied DECIMAL(5,2) NULL
     - Log when seasonal adjustments are applied

     Stockout Pattern Awareness (0.5 hours)

     TASK-609: Add stockout pattern checking to urgency determination
     - Query stockout_patterns table in determine_monthly_order_timing()
     - Check stockout_pattern_detected = 1 for SKU
     - If detected and pattern_type = 'chronic', boost urgency
     - Urgency boost logic:
       - 'skip' → 'optional' if chronic stockout
       - 'optional' → 'should_order' if chronic stockout
       - 'should_order' → 'must_order' if chronic stockout
     - Add field: stockout_pattern_boost BOOLEAN to pending_breakdown

     TASK-610: Backend testing for intelligence layer
     - Test forecast integration with sample forecast_details data
     - Verify learning adjustments applied correctly
     - Test seasonal adjustment calculations for Q4 peak
     - Test stockout pattern urgency boosting
     - Verify all new fields populated correctly

     TASK-611: Update generate recommendations to show intelligence
     - Add success message showing: "Using forecasts with learning" or "Using historical sales"
     - Show count of SKUs with seasonal adjustments applied
     - Show count of SKUs with stockout pattern boost
     - Update frontend/supplier-ordering.js success handler

     TASK-612: Documentation for intelligence features
     - Update docs/SUPPLIER_ORDERING_API.md with new response fields
     - Document forecast vs historical sales decision logic
     - Explain seasonal adjustment thresholds
     - Explain stockout pattern urgency boosting

     ---
     Phase 3: Visualization & UX (TASK-613 to TASK-619) - 2-3 hours

     Coverage Timeline (1.5 hours)

     TASK-613: Create backend/supplier_coverage_timeline.py module
     - Function: build_coverage_projection(sku_id, warehouse, days=180)
     - Algorithm: Day-by-day inventory projection
     - Inputs: current_stock, pending_orders[], daily_demand
     - Logic:
       - Start with current inventory
       - For each day: inventory -= daily_demand
       - Check for pending arrivals on that day: inventory += qty * confidence
       - Track: date, projected_inventory, arriving_orders[], stockout_risk
     - Return: List of 180 daily projections (6 months)
     - File size target: 150-200 lines

     TASK-614: Add GET /api/coverage-timeline/sku/{sku_id} endpoint
     - Add to backend/supplier_ordering_api.py (check file size first)
     - Call build_coverage_projection() from TASK-613
     - Return paginated timeline (default: 90 days, max: 180 days)
     - Include: stockout_date (first day inventory < 0)
     - Response format: {timeline: [], stockout_date: "2025-11-15", coverage_days: 45}

     TASK-615: Add coverage timeline tab to SKU modal (frontend)
     - Add 5th tab to frontend/supplier-ordering.html modal: "Coverage Timeline"
     - Chart.js area chart showing inventory projection over time
     - X-axis: dates, Y-axis: projected inventory
     - Shaded regions: green (safe), yellow (warning <30 days), red (stockout)
     - Markers: Show pending order arrivals as vertical lines
     - Tooltip: Show arriving orders and projected stock level

     Supplier Performance Tab (1 hour)

     TASK-616: Create supplier performance summary view
     - Backend: Add to backend/supplier_ordering_api.py
     - GET /api/supplier-performance endpoint
     - Query supplier_lead_times table for all suppliers
     - Join supplier_shipments for delay statistics
     - Aggregate: avg_lead_time, p95_lead_time, reliability_score, avg_delay_days
     - Group by supplier, destination warehouse

     TASK-617: Add Supplier Performance modal tab (frontend)
     - New tab in SKU modal (or separate page if modal crowded)
     - Table showing: Supplier, Warehouse, Avg Lead Time, P95, Reliability, Avg Delay
     - Color coding: green (reliability >0.9), yellow (>0.7), red (<0.7)
     - Sortable columns (DataTables client-side for small dataset)

     Revenue Metrics (0.5 hours)

     TASK-618: Add revenue metrics to summary cards
     - Update GET /api/supplier-orders/summary endpoint
     - Calculate: total_order_value_burnaby, total_order_value_kentucky
     - Use confirmed_qty * cost_per_unit from supplier_order_confirmations
     - Return new fields: {total_value_ca: 125000.50, total_value_ky: 89000.25}
     - Update frontend summary cards to show revenue metrics

     TASK-619: Revenue breakdown by supplier
     - Add table to main supplier-ordering.html page (below summary cards)
     - Group orders by supplier, show total value per supplier
     - Sort descending by total value
     - Columns: Supplier, Order Count, Total Units, Total Value
     - Use DataTables for sorting/searching

     ---
     Testing Strategy (Included in phases above)

     Each phase includes testing tasks:
     - TASK-599: Backend API tests
     - TASK-600: Performance benchmarks
     - TASK-610: Intelligence layer tests
     - Final: Comprehensive Playwright test suite (see below)

     ---
     Comprehensive Playwright Testing Plan

     After all tasks complete, run full test suite:

     Test Coverage:
     1. SKU Details Modal - Pending Orders tab loads data correctly
     2. SKU Details Modal - Forecast tab shows 12-month chart
     3. SKU Details Modal - Stockout tab displays history
     4. SKU Details Modal - Coverage Timeline projects inventory correctly
     5. CSV Export downloads and contains correct data
     6. Generate Recommendations shows intelligence indicators
     7. Summary cards display revenue metrics
     8. Supplier performance tab loads metrics
     9. Seasonal adjustments visible in pending_breakdown
     10. Stockout pattern urgency boost applied correctly
     11. Forecast vs historical sales decision logged
     12. Page load time < 2 seconds (performance benchmark)

     ---
     Code Documentation Standards

     Every new function must include:
     def function_name(param1: str, param2: int) -> dict:
         """
         Brief one-line description
         
         Args:
             param1: Description of parameter 1
             param2: Description of parameter 2
             
         Returns:
             Description of return value
             
         Raises:
             ValueError: When validation fails
             
         Example:
             result = function_name("test", 10)
         """

     HTML/JavaScript:
     - Module-level comments explaining purpose
     - Section comments for major UI blocks
     - Function docstrings for complex logic

     ---
     File Size Management

     Current Status Check:
     - backend/supplier_ordering_api.py: Check line count before adding endpoints
     - If >400 lines: Split into routers first (TASK-593a prerequisite)
     - backend/supplier_ordering_calculations.py: Currently 573 lines (close to 600 limit)
     - frontend/supplier-ordering.js: Check size before adding functions

     Split Strategy if Needed:
     backend/supplier_ordering/
     ├── api.py (main endpoints, <300 lines)
     ├── sku_details_api.py (TASK-594, 595, 596)
     ├── calculations.py (existing)
     └── coverage_timeline.py (TASK-613)

     ---
     Performance Targets (claude-code-best-practices.md)

     All endpoints must meet:
     - API response: <500ms
     - Page load: <2 seconds
     - Chart rendering: <1 second
     - CSV export: <3 seconds
     - No calculations on page load (all pre-calculated or cached)

     ---
     Database Migration Strategy

     New columns needed:
     - supplier_order_confirmations.forecast_run_id INT NULL
     - supplier_order_confirmations.forecast_method VARCHAR(50) NULL
     - supplier_order_confirmations.learning_adjusted BOOLEAN DEFAULT FALSE
     - supplier_order_confirmations.seasonal_factor_applied DECIMAL(5,2) NULL
     - supplier_order_confirmations.stockout_pattern_boost BOOLEAN DEFAULT FALSE

     Migration file: database/migrations/v10_supplier_intelligence_fields.sql

     ---
     Implementation Order

     1. Phase 1 (TASK-593 to TASK-603): Fix modal errors first - immediate user value
     2. Phase 2 (TASK-604 to TASK-612): Add intelligence - leverage existing forecasting system
     3. Phase 3 (TASK-613 to TASK-619): Visualization - enhance UX

     Estimated Total Time: 8-12 hours across 3 phases

     Task Completion Protocol:
     - Mark task complete IMMEDIATELY after finishing
     - Update TASKS.md with completion status
     - Run Playwright tests after each phase
     - Document any deviations or discoveries