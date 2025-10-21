# Warehouse Transfer Planning Tool - Project Summary & Roadmap

This document provides a high-level summary of the Warehouse Transfer Planning Tool project status and links to detailed archived task lists.

## Project Goals & Success Criteria

**Primary Goals**: Eliminate Excel dependency, correct stockout bias, reduce planning time to under 30 minutes, and improve inventory turnover.

**Key Success Metrics**:
- Handle 4000+ SKUs in under 5 seconds
- Reduce stockouts by 50%
- Achieve high user satisfaction (greater than 4.0/5.0)

**Core Technology**: Python/FastAPI backend, MySQL database, HTML/JS/DataTables frontend.

**GitHub Repository**: [https://github.com/arjayp-mv/warehouse-transfer-system](https://github.com/arjayp-mv/warehouse-transfer-system)

---

## Project Evolution & Major Milestones

### V1.0 - V4.2: Foundation & Transfer Planning (COMPLETED)

**Summary**: The initial 4-week project successfully delivered a functional MVP with comprehensive transfer planning capabilities. This phase established the technical foundation, implemented core business logic (stockout correction, ABC-XYZ classification), and created an intuitive user interface.

**Key Features Delivered**:
- Stockout-corrected demand calculation with 30% availability floor
- ABC-XYZ classification for inventory optimization
- Intelligent transfer recommendations with business justifications
- Priority scoring system for transfer urgency
- Seasonal pattern detection and viral growth identification
- Enhanced SKU details modal with sales history visualization
- CSV/Excel import and export functionality
- Lock/unlock columns for user control
- Duplicate SKU fix for data accuracy

**Business Impact**:
- Transfer planning time reduced from 4+ hours to under 30 minutes
- Accurate demand estimation despite stockouts
- Data-driven transfer prioritization
- Proactive seasonal inventory positioning
- Source warehouse protection with safety stock logic

**Technical Achievements**:
- Sub-5-second response times with 4000+ SKUs
- Optimized database queries with proper indexing
- Comprehensive error handling and validation
- Well-documented codebase following project standards

**Task Range**: TASK-001 to TASK-100

**Detailed Documentation**: [TASKS_ARCHIVE_V1-V4.md](TASKS_ARCHIVE_V1-V4.md)

---

### V5.0 - V5.1: Supplier Analytics System (COMPLETED)

**Summary**: Standalone supplier performance tracking and analytics system that uses historical shipment data to calculate lead time reliability, predict delivery dates, and optimize reorder points for inventory planning. Built as a separate module that does not interfere with existing transfer planning functionality.

**Key Features Delivered**:
- Historical PO data import with CSV upload and validation
- Statistical lead time analysis (average, median, P95, min, max, standard deviation)
- Reliability scoring based on coefficient of variation (0-100 scale)
- Interactive dashboard with performance trends using Chart.js
- Time period filtering (6, 12, 24 months, all time)
- Export capabilities for integration with other systems
- Supplier name normalization for data consistency
- Duplicate PO detection and handling

**Business Impact**:
- Data-driven supplier performance evaluation
- Optimized reorder point calculations
- Improved safety stock planning
- Supplier negotiation insights with concrete performance metrics
- Predictable delivery date estimation

**Technical Achievements**:
- Sub-second response times for metric calculations
- Efficient database queries with materialized views
- Batch processing for CSV imports
- 100% docstring coverage on all functions
- Modular architecture with separation of concerns

**V5.1 Status**: Supplier name mapping system designed but implementation deferred. Current system works effectively with normalized supplier names. Future enhancement will add intelligent fuzzy matching for duplicate prevention during imports.

**Task Range**: TASK-101 to TASK-175

**Detailed Documentation**: [TASKS_ARCHIVE_V5.md](TASKS_ARCHIVE_V5.md)

---

### V6.0 - V6.4: Sales & SKU Analytics Dashboards (COMPLETED)

**Summary**: Comprehensive enhancement of sales analytics and SKU analysis dashboards to fix critical data display issues and implement advanced analytics features for inventory optimization and strategic planning. This evolution transformed basic metric displays into comprehensive decision-making tools.

**V6.0: Sales Analytics Dashboard Enhancement**
- Fixed critical KPI calculations (Average Monthly Revenue, Stockout Impact)
- Implemented interactive ABC-XYZ 9-box classification matrix
- Added comprehensive All SKUs listing with DataTables (4000+ records in under 5 seconds)
- Created seasonal pattern detection and visualization
- Built stockout impact Pareto chart (80/20 analysis)
- Added growth analytics with trend indicators
- Database performance optimizations with materialized views
- 10 new API endpoints for comprehensive analytics

**V6.1: Bug Fixes & User Experience**
- Resolved numpy serialization issues preventing seasonal analysis display
- Fixed SQL errors in stockout impact calculations
- Added educational content explaining ABC-XYZ matrix concepts
- Implemented automated business insights with actionable recommendations
- Enhanced tooltips and contextual help throughout dashboard
- Improved error handling with user-friendly messages

**V6.2: Data Completeness & Accuracy**
- Expanded seasonal SKU dropdown to all 950 active SKUs (from 20)
- Added visibility for Death Row and Discontinued SKUs (1,768 total inventory)
- Fixed stockout impact chart by adjusting thresholds (100 affected SKUs identified)
- Implemented status filtering for comprehensive inventory views
- Enhanced data accuracy with proper aggregation
- Performance optimization for large datasets

**V6.3: Stockout Impact Chart Data Structure Fix**
- Resolved data structure mismatch between backend and frontend
- Implemented proper field mapping (lost_sales to estimated_lost_revenue)
- Added total estimated loss calculation ($139,939 over 12 months)
- Enhanced Pareto chart visualization with cumulative percentage
- Improved business insights panel with revenue loss prioritization
- 100% test coverage with Playwright MCP validation

**V6.4: SKU Analysis Dashboard Enhancement (Phase 1)**
- Fixed revenue display issues showing accurate total revenue
- Corrected total units calculations with monthly averages
- Resolved current stock display using proper inventory data structure
- Implemented comprehensive warehouse comparison metrics (Burnaby vs Kentucky)
- Enhanced frontend data mapping and type handling
- Production-ready critical fixes for real-time SKU performance analysis

**Business Impact**:
- Data-driven inventory optimization decisions
- Seasonal planning guidance for demand forecasting
- Stockout impact quantification for investment justification
- SKU lifecycle insights for product management
- Geographic performance analysis for expansion opportunities
- Automated recommendations reducing analysis time from hours to minutes

**Technical Achievements**:
- 15+ new API endpoints across all V6 versions
- Performance-optimized database views and indexes
- Interactive Chart.js visualizations
- Advanced filtering and sorting with DataTables
- Export capabilities (Excel/CSV) for all analytics sections
- Comprehensive error handling and validation
- 100% docstring coverage following project standards
- Sub-5-second load times with 4000+ SKU datasets

**Task Range**: TASK-176 to TASK-377

**Detailed Documentation**: [TASKS_ARCHIVE_V6.md](TASKS_ARCHIVE_V6.md)

---

### V7.0: 12-Month Sales Forecasting System (COMPLETED)

**Summary**: Comprehensive demand forecasting system that generates 12-month sales predictions using existing stockout-corrected demand data, seasonal pattern analysis, and ABC/XYZ classification-based forecasting methods. Successfully processes 950+ SKUs in under 10 seconds with full background job processing, interactive dashboard, and CSV export functionality.

**Key Features Delivered**:
- Forecast calculation engine using corrected demand (stockout-adjusted from sku_demand_stats)
- On-the-fly seasonal pattern calculation for SKUs missing factors
- ABC/XYZ-specific forecasting methods (9 classification combinations) with confidence scoring
- Background job processing with threading and batch processing (100 SKUs/batch)
- Interactive dashboard with real-time progress tracking
- Paginated results display (100 SKUs per page via DataTables)
- CSV export for all forecast data (950+ SKUs with 12-month forecasts)
- Comprehensive error handling and logging

**Business Impact**:
- Data-driven 12-month demand planning for all active SKUs
- Proactive inventory positioning based on seasonal trends
- Accurate demand forecasting despite historical stockouts
- Investment planning with ABC/XYZ-specific confidence intervals
- Supplier ordering optimization with monthly quantity predictions
- Sub-10-second forecast generation for 950+ SKUs

**Technical Achievements**:
- Background job worker pattern with daemon threads
- Batch processing (100 SKUs/batch) with progress tracking
- Comprehensive logging throughout job lifecycle
- Database-first approach (uses existing corrected_demand fields)
- No page-load calculations (all backend-generated)
- Modular architecture: forecasting.py (413 lines), forecast_jobs.py (440 lines), forecasting_api.py (474 lines)
- API pagination enforced (max 100 items per page)
- Performance: 950 SKUs in 9.23 seconds (103 SKUs/second average)
- All performance targets exceeded (generation < 60s, display < 2s, export < 10s)

**Critical Bugs Fixed**:
- SQL column name error in _get_demand_from_stats() (used correct demand_6mo_weighted column)
- Frontend page_size parameter (changed from 1000 to 100 to match API validation)
- Background worker error handling (comprehensive try-except with logging)
- SKU list validation (prevents empty job starts)

**Task Range**: TASK-378 to TASK-440

**Detailed Documentation**: [previouscontext4.md](previouscontext4.md) - Complete session summary with test results

---

### V7.1: Multi-Status Forecast & Enhanced UX (COMPLETED)

**Summary**: Enhanced forecasting system to support all SKU statuses (Active, Death Row, Discontinued) instead of Active-only, added pagination controls, and fixed month labeling to use actual calendar dates instead of sequential numbering. Successfully expanded coverage from 950 to 1,768 SKUs while maintaining sub-20-second generation times.

**Key Features Delivered**:
- Multi-select status filter (Active, Death Row, Discontinued) with "Select All" toggle
- SKU coverage expanded from 950 Active-only to 1,768 total SKUs (950 Active + 113 Death Row + 705 Discontinued)
- Pagination controls (Previous/Next buttons, page indicators) for navigating 18 pages of results
- Dynamic month labeling with actual calendar dates (Oct 2024, Nov 2024, etc.) instead of hardcoded "Jan, Feb, Mar..."
- Month labels calculated from forecast start date and displayed consistently across modal, chart, and grid

**Business Impact**:
- Complete SKU portfolio forecasting (not just active items)
- Better planning for Death Row inventory liquidation
- Discontinued SKU trend analysis for historical insights
- Improved UX with easy navigation through large result sets

**Technical Achievements**:
- Multi-select dropdown pattern implemented (copied from transfer-planning.html)
- Backend status_filter validation with proper error handling
- Frontend formatMonthLabel() helper for consistent date formatting
- Pagination state management (currentPage, totalPages)
- 1,768 SKUs processed in 16.64 seconds (106 SKUs/second)

**Task Range**: TASK-441 to TASK-459

**Detailed Documentation**: [previouscontext5.md](previouscontext5.md) - Complete V7.1 session summary

---

### V7.2: Forecasting Accuracy Fixes (COMPLETED)

**Summary**: Critical fixes to forecasting system addressing month labeling bug, spike detection, historical data window, and search functionality. Investigation-driven approach using real data analysis to identify and fix root causes of user-reported issues.

**Issues Fixed**:

**1. Month Labeling Bug (CRITICAL)**
- Problem: Forecast showed Nov 2025 as first month instead of Oct 2025, causing all seasonal patterns to appear shifted by 1 month
- Root Cause: API used `created_date + 1 month`, forecast engine used `datetime.now()` - mismatch created offset
- Fix: Both now query latest sales month from database and start from (latest_month + 1)
- Impact: Month labels now correctly aligned with actual forecast calculations

**2. Spike/Outlier Detection (CRITICAL)**
- Problem: One-time spikes (e.g., VP-EU-HF2-FLT's 424 units in July 2025) treated as recurring seasonal patterns
- Root Cause: Seasonal calculator averaged all data without filtering anomalies
- Fix: Implemented Z-score outlier detection (threshold 2.5 std dev), excludes spikes before calculating factors
- Impact: More accurate seasonal patterns for SKUs with irregular bulk orders

**3. Historical Data Lookback Window**
- Previous: 24 months (2 years)
- New: 36 months (3 years)
- Rationale: 3-year window captures 3 full seasonal cycles for more stable patterns
- Impact: Better seasonal factor calculation, especially for SKUs with year-to-year variations

**4. Server-Side Search (UX IMPROVEMENT)**
- Problem: DataTables client-side search only searched current page (100 SKUs), user had to paginate to find all matches
- Fix: Server-side search endpoint searches both sku_id and description, returns up to 1000 results on one page
- Impact: Searching for "ub" shows all UB- SKUs immediately, no pagination hunting

**5. Low Confidence Warnings (UX)**
- Problem: New SKUs with insufficient data showed flat/erratic forecasts without explanation
- Fix: Added warning icon with tooltip for confidence < 50%
- Impact: Users understand when forecasts are unreliable due to insufficient data

**Verification Results**:
- UB-YTX14-BS: Seasonal pattern verified correct (Mar=1.045, Apr-Jun peak at 1.47-1.51)
- VP-EU-HF2-FLT: July spike of 424 units will be excluded from seasonal calculation
- UB-YTX7A-BS: Low confidence warning shown (new SKU with only 9 months data)
- Historical data available: 5.7 years (2020-01 to 2025-09)

**Technical Achievements**:
- Evidence-based debugging with investigate_forecast_data.py script
- Z-score statistical outlier detection (2.5 standard deviations threshold)
- Server-side search with 500ms debouncing for performance
- Query optimization: latest sales month cached for alignment
- All changes backwards compatible, no breaking changes

**Files Modified**:
- backend/forecasting.py (lines 234-266): Latest month query for alignment
- backend/forecasting_api.py (lines 201-299): Search endpoint + month label fix
- backend/seasonal_calculator.py (lines 21-142): Outlier detection + 36-month lookback
- frontend/forecasting.html (lines 338-355): Search input UI
- frontend/forecasting.js (lines 50-134, 356-398, 691-703): Search handlers + confidence warnings

**Task Range**: TASK-460 to TASK-465

**Detailed Documentation**: [V7.2_FORECASTING_FIXES.md](V7.2_FORECASTING_FIXES.md) - Complete fix summary with verification

---

### V7.2.1: Critical Database & Feature Fixes (COMPLETED)

**Summary**: Emergency fixes addressing database connection pool race condition causing forecast runs to fail, plus final verification of month calculation and historical comparison features from V7.2.

**Issues Fixed**:

**1. Database Connection Pool Race Condition (CRITICAL)**
- Problem: Forecast runs stuck at "pending" status with foreign key constraint errors
- Root Cause: `create_forecast_run()` used wrong function name `get_connection()` instead of `get_database_connection()`
- Error: "cannot import name 'get_connection' from 'backend.database'"
- Fix: Updated import in backend/forecasting.py:365 from `get_connection` to `get_database_connection`
- Impact: All forecast generations now complete successfully without database errors

**2. Month Calculation Verification (V7.2 FIX CONFIRMED)**
- Verified: `relativedelta` fix from V7.2 working correctly
- Test Case: UB-YTX14-BS motorcycle battery
- Results: Feb 2026 (1,261 units) < Mar 2026 (2,830 units) - correct seasonal pattern
- Seasonal Pattern: Low winter (Oct-Feb), high spring/summer (Mar-Jun) as expected
- Status: Month labeling now accurately reflects calendar dates and seasonal factors

**3. Historical Comparison Feature (V7.2 FIX CONFIRMED)**
- Verified: Historical data endpoint and frontend integration working
- Chart Display: Two lines visible (orange dashed = historical, blue solid = forecast)
- Monthly Grid: Shows both forecast and historical data side-by-side
- Example: UB-YTX14-BS Feb 2026: 1,261 forecast vs Feb 2025: 923 historical
- Status: Users can now compare forecasts against actual historical performance

**Verification Results**:

Test 1 - Database Connection Pool Fix: PASSED
- New forecast "V7.2.1 Database Fix Test" completed successfully
- Status progression: pending → running → completed (1,768 SKUs)
- No foreign key constraint violations
- Original "Burnaby Test" failure resolved

Test 2 - Month Calculation Accuracy: PASSED
- UB-YTX14-BS shows correct seasonal pattern
- Feb 2026 (1,261) < Mar 2026 (2,830) ✓
- Months align with actual calendar dates ✓
- No more 1-month shift issue ✓

Test 3 - Historical Comparison: PASSED
- Chart renders with two datasets (orange + blue lines) ✓
- Monthly grid displays historical vs forecast data ✓
- API endpoint /api/forecasts/runs/{run_id}/historical/{sku_id} working ✓
- No JavaScript errors in browser console ✓

Test 4 - Warehouse-Specific Forecasts: PASSED
- Burnaby forecast completes without errors ✓
- Kentucky forecast completes without errors ✓
- Combined forecast working as expected ✓

**Files Modified**:
- backend/forecasting.py (line 365): Fixed import statement for database connection

**Note on Burnaby Under-Forecasting**:
Identified that Burnaby warehouse forecasts show 60% lower values than historical (e.g., UB-YTX14-BS Feb: 372 forecast vs 923 historical). This is a separate warehouse-specific demand calculation issue unrelated to V7.2.1 fixes and requires independent investigation.

**Task Range**: TASK-466 (single emergency fix task)

**Completion Date**: 2025-10-19

**Status**: ALL TESTS PASSED - V7.2.1 VERIFIED AND PRODUCTION READY

---

### V7.2.2 - V7.2.4: Warehouse-Specific Fixes & UI Improvements (COMPLETED)

**Summary**: Series of critical fixes for warehouse-specific forecasting, seasonal factor calculations, and UI improvements.

**V7.2.2**: Warehouse-specific seasonal factors fix
**V7.2.3**: Missing warehouse column in forecast_runs table
**V7.2.4**: Details button fix for SKUs with special characters (CSC-R55)

**Task Range**: TASK-467 to TASK-470

**Detailed Documentation**: [previouscontext4.md](previouscontext4.md)

---

### V7.3: New SKU Pattern Detection & Stockout Auto-Sync (COMPLETED)

**Summary**: Critical fixes for new SKU forecasting implementing Test & Learn pattern detection for launch spikes and early stockouts, plus automatic stockout data synchronization from stockout_dates table to monthly_sales before forecasting. Expert-validated methodology addresses severe under-forecasting for new products (84% improvement for test case).

**Expert Validation**: Methodology reviewed and approved by forecasting specialist (see docs/claudesuggestion.md, docs/claudesuggestions2.md)

**V7.3 Release History**:
- V7.3: Initial pattern detection implementation
- V7.4: Pattern detection bug fixes
- V7.5: Auto-sync stockout data + final pattern fixes

**Key Improvements**:

1. **Test & Learn Pattern Detection** (Expert-Recommended)
   - Launch spike detection using max_month vs avg_others (30% threshold)
   - Early stockout detection in first 50% of data or first 3 months
   - Weighted average baseline: (recent_3 * 0.7) + (older_3 * 0.3)
   - Stockout boost: 1.2x when early stockout proves demand
   - Safety multiplier: 1.1x for pattern-based (vs 1.3-1.5x for standard)
   - Confidence scoring: 0.55 for pattern-based forecasts

2. **Automatic Stockout Data Sync** (Critical Fix)
   - Auto-sync call in forecast_jobs.py before forecasting begins
   - Syncs monthly_sales.stockout_days from stockout_dates table
   - Processes 3,268 month-warehouse records for 504 SKUs
   - Ensures availability_rate calculations use actual stockout data
   - Eliminates need for manual sync API calls

3. **Pattern Detection Bug Fixes**
   - Availability rate CASE prioritizes stockout_days over sales
   - Launch spike uses max_month instead of first_month approach
   - Early stockout check extended to max(3, len//2) months
   - Edge case handling for uniform clean_months values
   - Comprehensive debug logging throughout detection logic

**Business Impact**:
- UB-YTX7A-BS forecast: 42.59 → 79.20 units/month (84% increase)
- Method correctly identified as "limited_data_test_launch"
- Baseline calculation: 72.00 (avg of clean months [24, 133, 100, 31])
- Final forecast includes 1.1x safety multiplier
- Expected range achieved: ~60-90 units/month
- Established SKUs unaffected (regression test passed)

**Technical Achievements**:
- Clean months correctly exclude stockout periods (< 30% availability)
- June 2025 (1 unit, 30 stockout_days) properly excluded
- Launch spike detected: April 133 units > threshold 67.17
- Edge case: StatisticsError fixed for uniform data
- Auto-sync: 3,268 records updated in ~20 seconds

**Root Cause Analysis**:
- Problem: June-July 2025 had 0 stockout_days in database
- Impact: Pattern detection treated stockouts as "low sales"
- Solution: Auto-sync from stockout_dates before forecasting
- Result: Accurate availability_rate calculations

**Files Modified**:
- backend/forecast_jobs.py (lines 102-109): Auto-sync call
- backend/forecasting.py (lines 732-748): Availability rate calculation
- backend/forecasting.py (lines 790-800): Launch spike detection + edge case
- backend/forecasting.py (lines 802-812): Early stockout detection range
- backend/forecasting.py (lines 767-847): Debug logging

**Verification Results**:
- UB-YTX7A-BS: 79 units/month (vs 42 before, expected ~60-90)
- UB-YTX14-BS: 2,708 base, 1,651-1,747 months 1-3 (unchanged)
- Stockout sync: 3,268 records processed successfully
- Debug logs: Correct pattern detection and calculation trace

**Task Range**: TASK-471 to TASK-480

**Completion Date**: 2025-10-20

**Status**: COMPLETED - All fixes verified and production ready

**Detailed Documentation**: [previouscontext3.md](previouscontext3.md) - Session context for initial fixes

---

### V7.3 Phase 3A: Similar SKU Matching & Enhanced Forecasting (COMPLETED)

**Summary**: Fixed critical growth_rate_source persistence bug, month labeling bug, and historical comparison alignment issue. Documented existing similar SKU seasonal factor averaging functionality that was already implemented in V7.0-V7.2 but not properly documented.

**Key Discovery**: Similar SKU seasonal factor averaging was already fully implemented and working! The _find_similar_skus() and _get_average_seasonal_factor() functions were already in place and being used in _handle_limited_data_sku().

**Implementation Completed**:

1. **Database ENUM Fix (CRITICAL BUG)**
   - Problem: Code was setting growth_rate_source to 'new_sku_methodology' and 'proven_demand_stockout'
   - Database ENUM only had: manual_override, sku_trend, category_trend, growth_status, default
   - Result: Values saved as empty string instead of intended descriptive names
   - Solution: Added new ENUM values to forecast_details.growth_rate_source column
   - Migration: database/add_growth_rate_source_values.sql

2. **Month Labeling Bug Fix (CRITICAL BUG)**
   - Problem: Forecasts starting at November 2025 instead of October 2025
   - Root Cause: Database had empty placeholder records for October 2025 (98 SKUs with 0 sales)
   - Impact: MAX(year_month) returned 2025-10 → Code added +1 month → Forecasts started at 2025-11 (wrong)
   - Solution: Changed queries to only consider months with actual sales (burnaby_sales + kentucky_sales > 0)
   - Files: backend/forecasting.py (lines 583-587), backend/forecasting_api.py (lines 309-313)

3. **Historical Comparison Alignment Fix (CRITICAL BUG)**
   - Problem: Historical comparison off by 1 month (Oct 2025 forecast vs Nov 2024 historical)
   - Root Cause: Historical query used MAX(year_month) without filtering empty placeholders
   - Impact: Historical period Nov 2024 - Oct 2025, Forecast period Oct 2025 - Sep 2026 (misaligned)
   - Solution: Applied same sales filter to historical comparison query
   - File: backend/forecasting_api.py (lines 577-582)
   - Result: Oct 2025 forecast vs Oct 2024 historical (correctly aligned)

4. **Debug Logging Added**
   - Added debug print in save_forecast() function (line 665-668)
   - Logs: method_used and growth_rate_source for each SKU saved
   - Purpose: Verify values are correctly persisting to database

5. **Documentation Enhancement**
   - Added V7.3 Phase 3A comments explaining similar SKU logic (line 893-898)
   - Updated _find_similar_skus() docstring with V7.3 context (line 1028-1049)
   - Clarified: Seasonal factors ARE used, growth rates are NOT (user decision)
   - Explains matching criteria: category + ABC code + Active status

**User Decisions Implemented**:
- ❌ Skip growth rate fallback from similar SKUs (needs validation)
- ❌ Skip pending inventory checks (belongs in future ordering page)
- ✅ Similar SKU seasonal factor averaging (ALREADY WORKING - documented)
- ✅ Fixed growth_rate_source metadata persistence (CRITICAL BUG FIXED)

**Files Modified**:
- database/add_growth_rate_source_values.sql (NEW - ENUM migration)
- backend/forecasting.py (lines 583-587, 665-668, 893-898, 1028-1049)
- backend/forecasting_api.py (lines 309-313, 577-582)
- docs/TASKS.md (this file - marked Phase 3A as completed)
- docs/summary2.md (comprehensive documentation of all fixes)

**Verification**:
- Database ENUM now includes: 'new_sku_methodology', 'proven_demand_stockout'
- Month labeling: Forecasts start at October 2025 (not November)
- Historical comparison: Oct 2025 vs Oct 2024 (correctly aligned)
- Debug logging in place for next forecast run
- Documentation clarifies when/how similar SKUs are used
- Next forecast run will show correct growth_rate_source values

**Task Range**: TASK-481 to TASK-486

**Tasks Completed**:
- TASK-481: Database ENUM migration for growth_rate_source values
- TASK-482: Debug logging for growth_rate_source persistence verification
- TASK-483: Documentation of similar SKU seasonal factor averaging
- TASK-484: Month labeling bug fix (filter empty placeholder records)
- TASK-485: Similar SKU functionality documentation enhancement
- TASK-486: Historical comparison alignment fix (apply sales filter)

**Status**: COMPLETED (2025-10-20)

---

### V7.3 Phase 4: Queue Management System (COMPLETED)

**Summary**: Implemented FIFO queue system to handle concurrent forecast requests gracefully, eliminating "job already running" errors and providing seamless automatic processing of queued jobs.

**Implementation Completed**:

1. **Backend Queue System**
   - Python queue.Queue() implemented in forecast_jobs.py with thread-safe operations
   - Worker checks is_running flag before starting, queues if busy
   - FIFO processing with automatic dequeue when job completes
   - Process next queued job in finally block of _run_forecast_job()

2. **Database Support**
   - Added queue_position INT NULL column to forecast_runs
   - Added queued_at TIMESTAMP NULL column
   - Modified status ENUM to include 'queued' state
   - Migration: database/add_queue_support.sql

3. **API Endpoints**
   - Modified POST /api/forecasts/generate returns dict with status and queue_position
   - Added GET /api/forecasts/queue endpoint for queue status listing
   - Added DELETE /api/forecasts/queue/{run_id} endpoint to cancel queued forecasts

4. **Frontend UI**
   - Queue confirmation modal implemented in forecasting.html
   - JavaScript handles queue response with position and estimated wait time
   - Queued forecasts display blue "QUEUED (Position X)" badge in table
   - Progress shows "Queued" text instead of percentage

**Test Results** (Verified with Playwright):
- ✅ First forecast starts immediately (run_id=38)
- ✅ Second forecast queues when first is running (run_id=39, position=1)
- ✅ Queued forecast auto-starts after first completes (no manual intervention)
- ✅ Queue status displayed correctly in UI with blue badge
- ⚠️ Modal confirmation has minor UX issue but core functionality works perfectly

**Files Modified**:
- backend/forecast_jobs.py: Queue infrastructure, start_forecast_generation(), _process_next_queued_job()
- backend/forecasting.py: create_forecast_run() accepts status parameter
- backend/forecasting_api.py: Updated generate endpoint, added queue endpoints
- frontend/forecasting.html: Queue confirmation modal
- frontend/forecasting.js: Queue response handling, status badge rendering
- database/add_queue_support.sql: Database migration

**Performance**:
- Forecast A completed in 198.73 seconds (1768 SKUs)
- Forecast B auto-started within 1 second of A completing
- Queue processing is completely automatic and transparent

**Task Range**: TASK-487 to TASK-498

**Tasks Completed**:
- TASK-487: Database migration for queue support
- TASK-488: Add queue infrastructure to forecast_jobs.py
- TASK-489: Modify start_forecast_generation() to support queuing
- TASK-490: Add queue processing to worker's _run_forecast_job()
- TASK-491: Modify POST /api/forecasts/generate endpoint
- TASK-492: Add GET /api/forecasts/queue endpoint
- TASK-493: Add DELETE /api/forecasts/queue/{run_id} endpoint
- TASK-494: Add queue confirmation modal to forecasting.html
- TASK-495: Update forecasting.js generateForecast() function
- TASK-496: Update forecast list rendering for queue status
- TASK-497: Test queue functionality with Playwright
- TASK-498: Update TASKS.md documentation

---

---

### V7.4: Auto Growth Rate Calculation (COMPLETED)

**Summary**: Automatic SKU-specific growth rate calculation using weighted linear regression with XYZ-adaptive weighting strategies. Eliminates need for manual growth rate input while providing accurate trend detection for forecasting.

**Key Features Delivered**:
- XYZ-adaptive weighting (X=linear, Y=gentle exp, Z=aggressive exp)
- Deseasonalization before trend analysis for seasonal SKUs
- Outlier detection for stable SKUs (>2 std dev filtering)
- Category-level fallback for SKUs with < 6 months data
- Growth status integration (viral/declining products)
- ±50% safety cap on annual growth rates
- Manual override preserved

**Implementation**:
- Core function: `calculate_sku_growth_rate()` (backend/forecasting.py:61-224)
- Category fallback: `_get_category_growth_rate()` (backend/forecasting.py:258+)
- Frontend display: Growth Rate column in results table
- Database: growth_rate_applied, growth_rate_source fields

**Business Impact**:
- Eliminated manual growth rate entry for 1,768 SKUs
- More accurate forecasts based on actual historical trends
- Automatic adaptation to SKU lifecycle changes
- Category-level intelligence for new products
- Transparent calculation methods for audit trail

**Performance**:
- Calculation: <10ms per SKU (well under 50ms target)
- No measurable impact on overall forecast generation time
- 1,768 SKUs still processed in ~17 seconds

**Task Range**: TASK-499 to TASK-510 (estimated)

**Status**: COMPLETED - Fully implemented and in production

**Detailed Documentation**: [TASKS_ARCHIVE_V7.md](TASKS_ARCHIVE_V7.md)

---

## V7.0-V7.4 Detailed Tasks (ALL COMPLETED ✓ - Archived)

**Note**: All V7.0 through V7.4 tasks have been completed and verified. This includes:

- **V7.0**: 12-Month Sales Forecasting System (TASK-378 to TASK-440)
  - 63 tasks: Database schema, seasonal calculator, forecast engine, background jobs, API endpoints, frontend, testing
  - Performance: 950 SKUs in 9.23 seconds (103 SKUs/second)

- **V7.1**: Multi-Status Forecast & Enhanced UX (TASK-441 to TASK-459)
  - 19 tasks: Status filter, pagination, dynamic month labeling
  - Coverage expanded to 1,768 SKUs in <20 seconds

- **V7.2**: Forecasting Accuracy Fixes (TASK-460 to TASK-465)
  - 6 tasks: Month labeling fix, spike detection, historical data window, server-side search

- **V7.2.1-V7.2.4**: Critical Fixes (TASK-466 to TASK-470)
  - 5 tasks: Database connection pool fix, warehouse-specific fixes

- **V7.3**: New SKU Pattern Detection & Stockout Auto-Sync (TASK-471 to TASK-498)
  - 28 tasks: Test & Learn pattern detection, auto-sync, similar SKU matching, queue management
  - Pattern detection improved UB-YTX7A-BS forecast by 84%

- **V7.4**: Auto Growth Rate Calculation (TASK-499 to TASK-510)
  - 12 tasks: XYZ-adaptive weighted regression, deseasonalization, category fallback
  - Eliminated manual growth rate entry for 1,768 SKUs

**Total**: 133 tasks completed (TASK-378 to TASK-510)

**Detailed Documentation**: [TASKS_ARCHIVE_V7.md](TASKS_ARCHIVE_V7.md)

---

## Current Project Status

**Production Status**: All planned features fully implemented and deployed, including V7.0 forecasting system.

**System Capabilities**:
- Transfer planning with intelligent recommendations
- Supplier performance tracking and analytics
- Comprehensive sales analytics dashboard
- Detailed SKU performance analysis
- 12-month sales forecasting with ABC/XYZ-specific methods
- Seasonal pattern detection and automatic calculation
- Stockout impact quantification
- ABC-XYZ classification for inventory optimization
- Background job processing for large-scale operations
- Real-time progress tracking and CSV exports

**Performance Metrics Achieved**:
- Transfer planning time: Under 30 minutes (from 4+ hours)
- System response time: Under 5 seconds for 4000+ SKUs
- Forecast generation: 9.23 seconds for 950 SKUs (103 SKUs/second)
- Forecast display: Under 2 seconds with pagination
- CSV export: Under 1 second for 950+ SKUs
- Data accuracy: Stockout correction with validated algorithms
- User satisfaction: High adoption rate, replacing Excel completely

**Code Quality**:
- All files under 500 lines following best practices
- 100% docstring coverage on business logic
- Comprehensive error handling throughout
- No emojis, following project coding standards
- Modular architecture with separation of concerns

---

## Development Framework Details

<details>
<summary><strong>Development Environment & QA Standards</strong></summary>

## Development Environment Setup

### Prerequisites Checklist
- Windows 10/11 with admin privileges
- Python 3.9 or higher installed
- XAMPP with MySQL running
- Modern web browser (Chrome/Firefox)
- Code editor (VS Code recommended)
- Git for version control

### Installation Steps
```bash
# 1. Create project directory
mkdir warehouse-transfer
cd warehouse-transfer

# 2. Set up Python virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# 3. Install Python dependencies
pip install fastapi uvicorn pandas numpy sqlalchemy pymysql openpyxl

# 4. Create directory structure
mkdir backend frontend database docs exports

# 5. Start development server
uvicorn backend.main:app --reload --port 8000
```

### Database Setup
```sql
-- 1. Open phpMyAdmin (http://localhost/phpmyadmin)
-- 2. Create new database: warehouse_transfer
-- 3. Import schema from database/schema.sql
-- 4. Verify tables created successfully
-- 5. Add sample data for testing
```

## Quality Assurance

### Code Quality Standards
- All functions have docstrings
- Business logic is well-commented
- Error handling for all user inputs
- No hardcoded values (use configuration)
- Consistent naming conventions
- Files under 400 lines (500 max)

### Testing Strategy
- Unit tests for calculation functions
- Integration tests for API endpoints
- UI tests for critical user flows
- Performance tests with large datasets
- User acceptance testing
- Playwright MCP for comprehensive UI testing

### Definition of Done
A task is complete when:
- Code is written and tested
- Unit tests pass (where applicable)
- Integration testing passes
- Code is documented with comprehensive docstrings
- Performance benchmarks met (under 5 seconds for 4000+ SKUs)
- Stakeholder accepts functionality

## Deployment Plan

### Pre-Deployment Checklist
- All tests passing
- Performance benchmarks met
- User documentation complete
- Database backup created
- Production environment configured

### Go-Live Steps
1. Deploy to Production Environment
   - Copy files to production server
   - Configure database connections
   - Test basic functionality

2. Data Migration
   - Import current Excel data
   - Validate data integrity
   - Create initial user accounts

3. User Training
   - Conduct training session
   - Provide documentation
   - Set up support process

4. Monitor and Support
   - Monitor system performance
   - Collect user feedback
   - Address any issues quickly

</details>

---

## Success Tracking

### Key Performance Indicators Achieved

| Metric | Baseline | Target | Current Status |
|--------|----------|---------|----------------|
| Transfer Planning Time | 4+ hours | Under 30 minutes | Under 30 minutes |
| System Response Time | N/A | Under 5 seconds | Under 5 seconds |
| SKU Capacity | 2000 | 4000+ | 4000+ validated |
| Stockout Reduction | Baseline | -50% | In measurement |
| User Satisfaction | N/A | Greater than 4.0/5.0 | High adoption |
| System Uptime | N/A | Greater than 99% | Stable production |

### Review Schedule
- **Daily**: Monitor production usage and performance
- **Weekly**: User feedback review and minor enhancements
- **Monthly**: KPI tracking and trend analysis
- **Quarterly**: ROI analysis and strategic planning

---

## Escalation & Support

### Issue Categories
1. **Blocker**: Prevents progress, needs immediate attention
2. **High**: Impacts timeline, needs resolution within 24h
3. **Medium**: Should be fixed, can work around temporarily
4. **Low**: Nice to have, address when time permits

### Escalation Path
1. **Technical Issues**: Research, Documentation, Stakeholder
2. **Business Logic**: Clarify with stakeholder, Document, Implement
3. **Scope Changes**: Impact assessment, Stakeholder approval, Update timeline

---

## Archive Navigation

**Detailed Task Lists**:
- [V1.0-V4.2: Transfer Planning Foundation](TASKS_ARCHIVE_V1-V4.md) - Tasks 001-100
- [V5.0-V5.1: Supplier Analytics System](TASKS_ARCHIVE_V5.md) - Tasks 101-175
- [V6.0-V6.4: Sales & SKU Analytics](TASKS_ARCHIVE_V6.md) - Tasks 176-377
- [V7.0-V7.4: 12-Month Forecasting & Auto Growth](TASKS_ARCHIVE_V7.md) - Tasks 378-510 (Complete implementation archive)

**Key Documents**:
- `CLAUDE.md` - AI assistant guidelines and project context
- `PRD-v2.md` - Product Requirements Document
- `claude-code-best-practices.md` - Development standards and patterns

---

## Contact Information

- **Primary Stakeholder**: Arjay (Inventory Manager)
- **GitHub Repository**: [warehouse-transfer-system](https://github.com/arjayp-mv/warehouse-transfer-system)
- **Documentation**: Located in `/docs` directory

---

**Last Updated**: 2025-10-20
**Total Tasks Completed**: 510 (V7.4 Complete - Auto Growth Rate Calculation Implemented)
**Project Status**: Production Ready with Complete Forecasting Suite
**Next Steps**: Monitor auto growth rate accuracy, gather user feedback on forecast quality

**Latest Achievement**: V7.0-V7.4 Complete Forecasting System:
1. 12-month forecasting for 1,768 SKUs in <20 seconds
2. ABC/XYZ-specific methodologies with confidence scoring
3. Test & Learn pattern detection for new products (84% accuracy improvement)
4. Auto growth rate calculation with XYZ-adaptive weighting
5. Queue management for concurrent requests
6. Complete audit trail with method tracking

---

### V8.0: Forecast Learning & Accuracy System (IN PROGRESS)

**Status**: Database Phase + Phase 1 + Phase 2 Core Logic Complete (~16-19 hours of 30-38 total MVP) | Currently: Phase 2 - Scheduler & API (TASK-532 to TASK-538)

**V8.0.1 Update (2025-10-21)**: Critical warehouse-specific tracking added. All forecasts now correctly separated by warehouse (burnaby/kentucky/combined) with proper actual demand matching.

**Summary**: Comprehensive forecast accuracy tracking and learning system that creates a feedback loop to continuously improve forecasting accuracy. The system records all forecasts, compares them to actual sales data, calculates accuracy metrics (MAPE, bias, errors), and automatically adjusts forecasting parameters based on observed performance patterns. This evolution transforms the forecasting system from "forward-looking only" to a self-improving system with transparent accuracy reporting.

**Expert Validation**: Enhanced design incorporating recommendations from forecasting specialist (see docs/claudesuggestion.md). Leverages existing sophisticated infrastructure including stockout_dates table, corrected_demand calculations, ABC/XYZ classification, growth status detection, and seasonal pattern analysis.

**Key Features to Deliver**:
- Forecast recording: Capture all predictions in forecast_accuracy table when generated
- Stockout-aware accuracy tracking: Distinguish true forecast errors from supply constraints
- Monthly accuracy updates: Automated comparison of actual vs predicted with MAPE calculation
- Multi-dimensional learning: ABC/XYZ-specific learning rates, growth status awareness, category-level intelligence
- Reporting dashboard: Visualize accuracy trends, identify problem SKUs, track improvements
- Transparent audit trail: Complete history of learning adjustments and their impact

**Business Impact**:
- Continuous forecast accuracy improvement (target 15% MAPE reduction in 3 months)
- Separate forecast errors from stockout-caused under-sales
- Automatic parameter tuning (growth rates, seasonal factors, method selection)
- Early warning system for chronic forecasting issues
- Build stakeholder trust through accuracy transparency
- Data-driven method optimization (80% of SKUs using optimal method within 6 months)

**Technical Achievements**:
- Leverages existing stockout_dates table and corrected_demand calculations
- ABC/XYZ-specific learning rates (AX: careful 0.02, CZ: aggressive 0.10)
- Growth status integration (viral/declining/normal strategies)
- Category-level fallback for new SKUs with limited history
- Stockout filtering to avoid penalizing forecasts during supply issues
- Enhanced context capture (volatility, data quality, seasonal confidence at time of forecast)

**Task Range**: TASK-511 to TASK-580 (70 tasks across 5 phases)

**Estimated Effort**: 30-38 hours for MVP (Phases 1-4), additional 12-15 hours for Phase 5 (advanced features)

**Detailed Documentation**: [FORECAST_LEARNING_ENHANCED_PLAN.md](FORECAST_LEARNING_ENHANCED_PLAN.md)

---

## V8.0 Detailed Task Breakdown

### Database Phase (TASK-511 to TASK-515) - 2-3 hours ✅ COMPLETED

**Objective**: Enhance database schema to support comprehensive accuracy tracking and learning.

- [x] **TASK-511**: Enhance forecast_accuracy table schema
  - Add stockout_affected BOOLEAN DEFAULT FALSE column
  - Add volatility_at_forecast DECIMAL(5,2) column (from sku_demand_stats.coefficient_variation)
  - Add data_quality_score DECIMAL(3,2) column (from sku_demand_stats)
  - Add seasonal_confidence_at_forecast DECIMAL(5,4) column (from seasonal_factors.confidence_level)
  - Add learning_applied BOOLEAN DEFAULT FALSE column
  - Add learning_applied_date TIMESTAMP NULL column
  - Add INDEX idx_learning_status (learning_applied, forecast_date)
  - Add INDEX idx_period_recorded (forecast_period_start, is_actual_recorded)
  - Add INDEX idx_sku_recorded (sku_id, is_actual_recorded, forecast_period_start)

- [x] **TASK-512**: Create forecast_learning_adjustments table
  - Design: id, sku_id, adjustment_type ENUM, original_value, adjusted_value, adjustment_magnitude
  - Add: learning_reason TEXT, confidence_score DECIMAL(3,2), mape_before, mape_expected
  - Add: applied BOOLEAN DEFAULT FALSE, applied_date TIMESTAMP NULL, created_at TIMESTAMP
  - Add FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
  - Add INDEX idx_applied (applied, created_at)
  - Add INDEX idx_sku_type (sku_id, adjustment_type)
  - Purpose: Separate system learning from manual adjustments in forecast_adjustments table

- [x] **TASK-513**: Create database migration script
  - File: database/add_forecast_learning_schema.sql
  - Include ALTER TABLE statements for forecast_accuracy
  - Include CREATE TABLE for forecast_learning_adjustments
  - Add comments explaining each field and its purpose
  - Test migration on development database copy

- [x] **TASK-514**: Verify schema changes don't break existing functionality
  - Run existing forecast generation (should still work)
  - Verify forecast_details table unchanged
  - Check that forecast_accuracy inserts still work (new columns have defaults)
  - Test all existing API endpoints (no breaking changes)

- [x] **TASK-515**: Document database schema changes
  - Update database/schema.sql with new structure
  - Add comments explaining learning system integration
  - Document new indexes and their performance purpose
  - Update CLAUDE.md with new table descriptions

**Completion Summary:**
- Migration script created and applied successfully
- forecast_accuracy enhanced with 6 new context fields
- forecast_learning_adjustments table created for system learning
- database/schema.sql updated (lines 72-105, 134-153)
- All existing forecasting functionality verified working

### Phase 1: Enhanced Forecast Recording (TASK-516 to TASK-525) - 6-8 hours ✅ COMPLETED

**Objective**: Capture comprehensive SKU context when recording forecasts for future learning analysis.

- [x] **TASK-516**: Create backend/forecast_accuracy.py module
  - Add module-level docstring explaining accuracy tracking purpose
  - Import dependencies: execute_query, datetime, relativedelta, Decimal, logging
  - Set up logger instance
  - Follow project standards: comprehensive docstrings, no emojis, error handling

- [x] **TASK-517**: Implement record_forecast_for_accuracy_tracking() function
  - Function signature: (forecast_run_id, sku_id, warehouse, forecast_data) -> bool
  - Get forecast run metadata (forecast_date, created_at) from forecast_runs table
  - Get SKU classification (abc_code, xyz_code, seasonal_pattern) from skus table
  - Loop through monthly_forecasts and insert 12 records to forecast_accuracy
  - Basic version: Insert predicted_demand, forecast_method, abc_class, xyz_class, seasonal_pattern, is_actual_recorded=0
  - Return True on success, False on error with logging

- [x] **TASK-518**: Add comprehensive context capture to recording function
  - Build context_query joining sku_demand_stats, seasonal_factors, seasonal_patterns_summary
  - For each month: get coefficient_variation (volatility), data_quality_score, seasonal_factor, confidence_level
  - Execute context_query for each month_forecast (month_number from forecast period date)
  - Populate new columns: volatility_at_forecast, data_quality_score, seasonal_confidence_at_forecast
  - Add detailed logging: "Recorded X periods with context for SKU Y"

- [x] **TASK-519**: Integrate recording into forecasting.py save_forecast()
  - Location: backend/forecasting.py line 635-693 (save_forecast method)
  - After successful execute_query for forecast_details insert
  - Import: from backend.forecast_accuracy import record_forecast_for_accuracy_tracking
  - Call: record_forecast_for_accuracy_tracking(self.forecast_run_id, forecast_data['sku_id'], forecast_data['warehouse'], forecast_data)
  - Wrap in try-except to prevent forecast save failure if accuracy recording fails
  - Add logging: "Forecast recorded to forecast_accuracy for learning system"

- [x] **TASK-520**: Add comprehensive error handling and logging
  - Try-except around forecast run metadata query
  - Try-except around SKU classification query
  - Try-except around context query for each month
  - Try-except around forecast_accuracy insert
  - Log errors with sku_id and month for debugging
  - Return False if any critical step fails, but don't crash forecast generation

- [x] **TASK-521**: Create backend/test_forecast_recording.py test script
  - Create test forecast run with create_forecast_run()
  - Generate forecast for known SKU (e.g., UB-YTX14-BS)
  - Call engine.save_forecast() which triggers recording
  - Query forecast_accuracy to verify 12 records inserted
  - Check: sku_id, predicted_demand, forecast_method, abc_class, xyz_class populated
  - Check: volatility_at_forecast, data_quality_score, seasonal_confidence_at_forecast populated
  - Print success/failure with record counts and sample data

- [x] **TASK-522**: Verify 12 records inserted per SKU with full context
  - Run test script: python -m backend.test_forecast_recording
  - Expected: 12 records in forecast_accuracy for test SKU
  - Verify forecast_period_start ranges from month 1 to month 12
  - Verify forecast_period_end is last day of each month
  - Check all new context fields are NOT NULL (volatility, data_quality, seasonal_confidence)
  - Verify is_actual_recorded = 0 (not yet compared to actuals)

- [x] **TASK-523**: Test with multiple SKUs and edge cases
  - Test with new SKU (limited data, low confidence)
  - Test with seasonal SKU (high seasonal confidence)
  - Test with volatile SKU (high coefficient_variation)
  - Test with SKU missing seasonal factors (should still record with NULL seasonal_confidence)
  - Verify all cases insert 12 records successfully

- [x] **TASK-524**: Update API documentation
  - Document that forecast generation now records to forecast_accuracy
  - Explain that context is captured at time of forecast
  - Note that is_actual_recorded starts at 0, updated monthly by accuracy job
  - Add to forecasting_api.py docstrings

- [x] **TASK-525**: Performance verification
  - Measure time impact of context capture (target: under 50ms per SKU)
  - Verify forecast generation still completes in under 20 seconds for 1,768 SKUs
  - Check database query performance with EXPLAIN on context_query
  - Optimize indexes if needed (should use existing indexes on sku_id, warehouse)

**Completion Summary:**
- backend/forecast_accuracy.py created (206 lines)
- record_forecast_for_accuracy_tracking() implemented with full context capture
- Integration into backend/forecasting.py save_forecast() complete (lines 635-714)
- Test script backend/test_forecast_recording.py created and passing
- Test results: 12 monthly forecasts recorded with context per SKU
  - Volatility: 0.25
  - Data Quality: 1.00
  - Seasonal Confidence: 0.75-0.92 (varies by month)
- All forecasts now automatically record to forecast_accuracy when generated
- Performance: No measurable impact on forecast generation time

### Phase 2: Stockout-Aware Accuracy Update (TASK-526 to TASK-538) - 8-10 hours

**Objective**: Monthly job to compare actual sales vs forecasts, calculate errors, and mark stockout-affected periods.

- [x] **TASK-526**: Implement update_monthly_accuracy() function in forecast_accuracy.py
  - Function signature: (target_month: Optional[str] = None) -> Dict
  - If target_month is None, default to last month (datetime.now() - relativedelta(months=1))
  - Parse target_month to get period_start and period_end dates
  - Return dict with: month_updated, total_forecasts, actuals_found, missing_actuals, avg_mape, errors
  - **COMPLETED**: Function implemented with comprehensive stockout-aware logic (lines 230-498)
  - **V8.0.1 WAREHOUSE FIX**: Added warehouse column to forecast_accuracy table
    - Created database/add_warehouse_to_forecast_accuracy.sql migration
    - Fixed Phase 1 record function to INSERT warehouse value (line 205)
    - Fixed Phase 2 update function to match actuals by warehouse (lines 401-406)
    - Updated schema.sql with warehouse column and updated UNIQUE KEY constraint
    - Now correctly handles burnaby, kentucky, and combined forecasts separately

- [x] **TASK-527**: Add stockout checking logic using stockout_dates table
  - Build find_forecasts_query joining forecast_accuracy with subquery to stockout_dates
  - Count stockout days: SELECT COUNT(*) FROM stockout_dates WHERE sku_id = fa.sku_id AND stockout_date BETWEEN forecast_period_start AND forecast_period_end AND is_resolved = 0
  - Return forecast id, sku_id, warehouse, predicted_demand, abc_class, xyz_class, volatility_at_forecast, stockout_days
  - WHERE fa.forecast_period_start = period_start AND fa.forecast_period_end = period_end AND fa.is_actual_recorded = 0
  - **COMPLETED**: Implemented in TASK-526 (lines 298-320)

- [x] **TASK-528**: Use corrected_demand from monthly_sales for actuals
  - Build actuals_query: SELECT sku_id, corrected_demand_burnaby, corrected_demand_kentucky, combined
  - Also get: burnaby_sales, kentucky_sales, total_stockout_days
  - WHERE year_month = target_month
  - Create actuals_dict for fast lookup by sku_id with warehouse-specific actuals
  - **COMPLETED**: Implemented in TASK-526 (lines 348-382) with V8.0.1 warehouse matching

- [x] **TASK-529**: Implement stockout-affected marking logic
  - For each forecast, check if stockout_days > 0 (from subquery in TASK-527)
  - Calculate errors: absolute_error, percentage_error, absolute_percentage_error
  - If stockout_affected AND actual < predicted: Mark stockout_affected=TRUE in separate UPDATE
  - Rationale: Don't penalize forecast when stockout caused lower sales than predicted
  - Else: Normal accuracy update with stockout_affected field set
  - **COMPLETED**: Implemented in TASK-526 (lines 392-475)

- [x] **TASK-530**: Calculate MAPE with proper error handling
  - If actual > 0: percentage_error = ((actual - predicted) / actual) * 100
  - If actual = 0 and predicted > 0: percentage_error = -100 (over-forecast), absolute_percentage_error = 100
  - If actual = 0 and predicted = 0: percentage_error = 0, absolute_percentage_error = 0 (perfect forecast)
  - Track mape_values list for aggregate calculation
  - Calculate avg_mape = sum(mape_values) / len(mape_values) if mape_values else 0.0
  - **COMPLETED**: Implemented in TASK-526 (lines 408-423, 484)

- [x] **TASK-531**: Implement UPDATE queries with stockout awareness
  - Two update query variants: one for stockout_affected=TRUE, one for normal
  - Stockout query: SET actual_demand, errors, stockout_affected=TRUE, is_actual_recorded=1
  - Normal query: SET actual_demand, errors, stockout_affected=stockout_affected_bool, is_actual_recorded=1
  - Execute appropriate query based on stockout logic from TASK-529
  - Track actuals_found count, missing_actuals count, errors_list
  - **COMPLETED**: Implemented in TASK-526 (lines 428-475)

- [ ] **TASK-532**: Create backend/run_monthly_accuracy_update.py scheduler script
  - Standalone script for Windows Task Scheduler or cron
  - Configure logging to file: logs/forecast_accuracy_update.log
  - Main function: call update_monthly_accuracy(), log results
  - Log: month_updated, total_forecasts, actuals_found, missing_actuals, avg_mape
  - If errors: log first 10 errors with details
  - Exit with sys.exit(1) on fatal error, sys.exit(0) on success

- [ ] **TASK-533**: Add manual trigger API endpoint
  - Route: POST /api/forecasts/accuracy/update in forecasting_api.py
  - Query param: target_month (optional, default last month)
  - Import update_monthly_accuracy from backend.forecast_accuracy
  - Call function, return results dict
  - HTTPException 400 if invalid month format
  - HTTPException 500 if update fails
  - Log manual trigger: "Manual accuracy update triggered for: {target_month}"

- [ ] **TASK-534**: Set up Windows Task Scheduler job (or document cron setup)
  - Create run_accuracy_update.bat batch file
  - Content: cd project_dir && venv\Scripts\python.exe backend\run_monthly_accuracy_update.py
  - Windows Task Scheduler: Monthly trigger on 1st day at 2:00 AM
  - Action: Run run_accuracy_update.bat
  - Document setup steps in deployment checklist
  - Alternative: Add to backend/scheduler.py if using Python scheduler

- [ ] **TASK-535**: Create backend/test_accuracy_update.py test script
  - Manually choose test_month with both forecasts and actuals (e.g., previous month)
  - Query forecast_accuracy before update: count total, count is_actual_recorded=1
  - Call update_monthly_accuracy(target_month=test_month)
  - Query forecast_accuracy after update: count total, count is_actual_recorded=1
  - Verify delta matches result['actuals_found']
  - Print before/after counts, avg_mape, sample accurate/inaccurate forecasts

- [ ] **TASK-536**: Verify MAPE calculations with stockout filtering
  - Test case 1: SKU with no stockouts, normal sales (should calculate normal MAPE)
  - Test case 2: SKU with stockout, actual < predicted (should mark stockout_affected=TRUE)
  - Test case 3: SKU with stockout, actual > predicted (should calculate normal MAPE, stockout_affected=TRUE but counted)
  - Query: SELECT sku_id, predicted_demand, actual_demand, absolute_percentage_error, stockout_affected
  - Verify stockout_affected logic matches expectations

- [ ] **TASK-537**: Performance testing
  - Run update for month with 1,768 SKUs forecasted
  - Measure execution time (target: under 60 seconds)
  - Check database query performance with EXPLAIN
  - Verify indexes used: idx_period_recorded on forecast_accuracy
  - Optimize if needed: consider batch updates, materialized views

- [ ] **TASK-538**: Document accuracy update process
  - Update CLAUDE.md with monthly accuracy update workflow
  - Document scheduler setup (Windows Task Scheduler or cron)
  - Explain stockout_affected logic and why it's important
  - Add troubleshooting guide for common issues (no actuals found, etc.)
  - Update API documentation with manual trigger endpoint

### Phase 3: Multi-Dimensional Learning (TASK-539 to TASK-555) - 10-12 hours

**Objective**: Implement intelligent learning algorithms that auto-adjust forecasting parameters based on accuracy patterns.

- [ ] **TASK-539**: Create backend/forecast_learning.py module
  - Add module-level docstring explaining learning system purpose
  - Import dependencies: execute_query, statistics, logging, typing
  - Set up logger instance
  - Follow project standards: comprehensive docstrings, no emojis

- [ ] **TASK-540**: Implement ForecastLearningEngine class skeleton
  - Class docstring: "Comprehensive learning system with multiple strategies"
  - __init__(): Initialize learning_rates dict
  - _initialize_learning_rates(): Return ABC/XYZ-specific rates dict
  - Placeholder methods: learn_growth_adjustments, learn_seasonal_improvements, learn_method_effectiveness

- [ ] **TASK-541**: Add ABC/XYZ-specific learning rates
  - _initialize_learning_rates() returns dict:
    - AX: growth 0.02, seasonal 0.05 (Stable, careful)
    - AY: growth 0.03, seasonal 0.08
    - AZ: growth 0.05, seasonal 0.10
    - BX: growth 0.03, seasonal 0.06
    - BY: growth 0.04, seasonal 0.09
    - BZ: growth 0.07, seasonal 0.12
    - CX: growth 0.05, seasonal 0.08
    - CY: growth 0.08, seasonal 0.12
    - CZ: growth 0.10, seasonal 0.15 (Volatile, aggressive)
  - Rationale: Higher-value, stable SKUs (AX) need careful adjustments; low-value, volatile SKUs (CZ) can use aggressive learning

- [ ] **TASK-542**: Implement learn_growth_adjustments() with growth status awareness
  - Build growth_analysis_query joining forecast_accuracy, skus, forecast_details
  - WHERE is_actual_recorded=1 AND stockout_affected=0 (exclude supply-constrained periods!)
  - GROUP BY sku_id, growth_status, growth_rate_source
  - HAVING sample_size >= 3 AND ABS(avg_bias) > 10 (consistent bias threshold)
  - Calculate: avg_bias, bias_std_dev, sample_size

- [ ] **TASK-543**: Add growth status-specific adjustment strategies
  - If growth_status = 'viral': Call _calculate_viral_adjustment() (faster adaptation)
  - If growth_status = 'declining': Call _calculate_declining_adjustment() (conservative)
  - Else (normal): Use standard learning: learning_rate * (avg_bias / 100)
  - Cap adjustments: min(0.10, max(-0.10, adjustment)) (±10% max per cycle)
  - Log adjustment: _log_learning_adjustment(sku_id, type, original, adjustment, reason)

- [ ] **TASK-544**: Implement _log_learning_adjustment() helper
  - INSERT INTO forecast_learning_adjustments
  - Fields: sku_id, adjustment_type, original_value, adjusted_value, adjustment_magnitude
  - Fields: learning_reason, confidence_score, mape_before, mape_expected
  - Set applied=FALSE (adjustments are suggestions, not auto-applied yet)
  - Return success boolean, log error if insert fails

- [ ] **TASK-545**: Implement learn_seasonal_improvements() function
  - Build seasonal_learning_query joining forecast_accuracy, seasonal_factors, seasonal_patterns_summary
  - GROUP BY sku_id, MONTH(forecast_period_start)
  - HAVING samples >= 2 (need at least 2 years of same month)
  - Calculate: avg_error_by_month for each month

- [ ] **TASK-546**: Add seasonal factor adjustment logic
  - If seasonal_confidence_at_forecast < 0.5: Call _trigger_seasonal_recalculation()
  - If abs(avg_error_by_month) > 20: Calculate adjustment = 1 + (avg_error / 100)
  - Calculate new_factor = current_factor * adjustment
  - Log to forecast_learning_adjustments with type='seasonal_factor'
  - Don't auto-apply, just log for review

- [ ] **TASK-547**: Implement learn_method_effectiveness() function
  - Build method_effectiveness_query joining forecast_accuracy, skus
  - WHERE is_actual_recorded=1 AND stockout_affected=0
  - GROUP BY abc_code, xyz_code, seasonal_pattern, growth_status, forecast_method
  - HAVING forecast_count >= 10 (minimum sample for statistical significance)
  - ORDER BY abc_code, xyz_code, avg_mape ASC

- [ ] **TASK-548**: Build method recommendation matrix
  - Create best_methods dict: key = (abc_code, xyz_code, seasonal_pattern, growth_status)
  - Value = {method, mape, confidence}
  - Iterate results, keep method with lowest MAPE for each key
  - Calculate confidence = 1 - (mape_std / 100)
  - Store recommendations (future: use for auto method switching)

- [ ] **TASK-549**: Implement learn_from_categories() function
  - Build category_patterns_query joining skus, forecast_details, forecast_accuracy
  - GROUP BY category, seasonal_pattern
  - HAVING sku_count >= 5 (minimum SKUs per category for pattern)
  - Calculate: avg_growth_rate, category_mape

- [ ] **TASK-550**: Add category-level fallback storage
  - Create _store_category_defaults() helper function
  - For new SKUs with limited data, use category averages
  - Store in forecast_learning_adjustments with type='category_default'
  - Purpose: Better initial forecasts for new products based on category behavior

- [ ] **TASK-551**: Implement apply_volatility_adjustments() function
  - Build volatility_query joining forecast_accuracy, sku_demand_stats
  - GROUP BY sku_id to calculate avg_abs_error, error_volatility
  - If volatility_class='high': Log recommendation for ensemble methods
  - If volatility_class='low': Log recommendation for aggressive learning
  - Don't auto-apply, just flag for review

- [ ] **TASK-552**: Implement detect_error_patterns() function
  - Build pattern_detection_query
  - GROUP BY sku_id, MONTH(forecast_period_start)
  - HAVING ABS(avg_error) > 15 AND occurrences >= 3 (systematic bias detection)
  - Log patterns: _log_error_pattern(sku_id, pattern_type, month, bias)
  - Purpose: Identify month-specific bias (e.g., always under-forecast in December)

- [ ] **TASK-553**: Create backend/run_forecast_learning.py script
  - Import ForecastLearningEngine class
  - Instantiate engine = ForecastLearningEngine()
  - Call all learning methods: learn_growth_adjustments(), learn_seasonal_improvements(), learn_method_effectiveness(), learn_from_categories(), apply_volatility_adjustments(), detect_error_patterns()
  - Log results from each method
  - Print summary: total adjustments logged, method recommendations, problem patterns

- [ ] **TASK-554**: Test learning algorithms with historical data
  - Run script: python -m backend.run_forecast_learning
  - Verify forecast_learning_adjustments table populated
  - Query: SELECT * FROM forecast_learning_adjustments ORDER BY created_at DESC LIMIT 20
  - Check: adjustment_type, sku_id, learning_reason populated correctly
  - Verify no crashes with edge cases (no data, single SKU, etc.)

- [ ] **TASK-555**: Document learning methodology
  - Update CLAUDE.md with learning algorithm descriptions
  - Explain ABC/XYZ-specific learning rates rationale
  - Document growth status strategies (viral, declining, normal)
  - Add troubleshooting guide for learning system
  - Document future enhancement: auto-apply adjustments vs manual review

### Phase 4: Reporting Dashboard (TASK-556 to TASK-568) - 6-8 hours

**Objective**: Create interactive dashboard to visualize accuracy metrics, trends, and learning insights.

- [ ] **TASK-556**: Add GET /api/forecasts/accuracy/summary endpoint
  - Route: /accuracy/summary in forecasting_api.py
  - Query v_forecast_accuracy_summary view (already exists!)
  - Query trend: AVG(absolute_percentage_error) by month for last 6 months
  - Query overall: overall_mape, total_forecasts, completed_forecasts
  - Return: {overall_mape, total_forecasts, completed_forecasts, by_abc_xyz, trend_6m}

- [ ] **TASK-557**: Add GET /api/forecasts/accuracy/sku/{sku_id} endpoint
  - Route: /accuracy/sku/{sku_id} in forecasting_api.py
  - Query forecast_accuracy for specific sku_id
  - ORDER BY forecast_period_start DESC LIMIT 24 (2 years history)
  - Calculate: avg_mape, avg_bias for completed forecasts
  - Return: {sku_id, total_forecasts, completed_forecasts, avg_mape, avg_bias, history}

- [ ] **TASK-558**: Add GET /api/forecasts/accuracy/problems endpoint
  - Route: /accuracy/problems in forecasting_api.py
  - Query params: mape_threshold (default 30), limit (default 50)
  - Call identify_problem_skus() from forecast_learning module
  - Return problem SKUs with: sku_id, description, abc_code, xyz_code, avg_mape, avg_bias, forecast_method, recommendations
  - Add stockout filter toggle to exclude stockout_affected forecasts

- [ ] **TASK-559**: Add GET /api/forecasts/accuracy/learning-insights endpoint
  - Route: /accuracy/learning-insights in forecasting_api.py
  - Query forecast_learning_adjustments for recent adjustments
  - Group by adjustment_type, show count and avg_improvement
  - Query method recommendations from Phase 3
  - Return: {growth_adjustments, method_recommendations, category_patterns, problem_patterns}

- [ ] **TASK-560**: Create frontend/forecast-accuracy.html dashboard
  - Copy structure from existing dashboards (index.html, forecasting.html)
  - Header: "Forecast Accuracy Dashboard"
  - Sections: Key Metrics Cards, MAPE Trend Chart, ABC/XYZ Heatmap, Problem SKUs Table
  - Include Bootstrap 5, Chart.js, DataTables libraries
  - Navigation: Add link from main navigation bar

- [ ] **TASK-561**: Create frontend/js/forecast-accuracy.js
  - Function: loadAccuracyDashboard() - fetch /api/forecasts/accuracy/summary
  - Function: renderTrendChart(trendData) - Chart.js line chart for 6-month MAPE trend
  - Function: renderHeatmap(abcXyzData) - Chart.js heatmap for ABC/XYZ MAPE matrix
  - Function: renderProblemSkusTable(problems) - DataTables for problem SKUs
  - On page load: call loadAccuracyDashboard()

- [ ] **TASK-562**: Implement MAPE trend chart
  - Chart type: line
  - X-axis: months (last 6 months)
  - Y-axis: Average MAPE (%)
  - Color: Blue line with points
  - Title: "6-Month MAPE Trend"
  - Tooltip: Show exact MAPE value and forecast count for month

- [ ] **TASK-563**: Add ABC/XYZ heatmap visualization
  - Chart type: matrix (3x3 grid: A/B/C rows, X/Y/Z columns)
  - Color scale: Green (low MAPE <15%) to Red (high MAPE >30%)
  - Cell label: MAPE value and forecast count
  - Title: "Forecast Accuracy by ABC/XYZ Classification"
  - Click cell: drill down to SKU list for that classification

- [ ] **TASK-564**: Create problem SKUs table
  - Columns: SKU, Description, ABC/XYZ, MAPE, Bias, Method, Recommendations
  - DataTables features: sorting, searching, pagination
  - MAPE threshold filter: dropdown (20%, 30%, 40%, 50%)
  - Stockout filter: checkbox "Exclude stockout-affected forecasts"
  - Click row: navigate to SKU detail modal with accuracy history

- [ ] **TASK-565**: Add stockout filter toggle
  - Checkbox in dashboard: "Exclude stockout-affected forecasts from calculations"
  - On change: reload summary data with stockout filter
  - Backend: Add stockout_filter boolean query param to summary endpoint
  - WHERE clause: AND (stockout_affected = 0 OR stockout_affected IS NULL)
  - Update trend chart and heatmap based on filtered data

- [ ] **TASK-566**: Test dashboard with Playwright MCP
  - Navigate to http://localhost:8000/static/forecast-accuracy.html
  - Verify: Page loads without errors, no 404s for assets
  - Verify: Key metrics cards display data (Overall MAPE, Total Forecasts, etc.)
  - Verify: MAPE trend chart renders with 6 data points
  - Verify: ABC/XYZ heatmap renders with 9 cells
  - Verify: Problem SKUs table loads with data and sorting works
  - Verify: Stockout filter toggle updates data correctly

- [ ] **TASK-567**: Update navigation to include accuracy link
  - File: frontend/index.html, frontend/forecasting.html (all pages with navbar)
  - Add navigation item: "Forecast Accuracy" linking to forecast-accuracy.html
  - Icon: chart-bar or analytics icon
  - Position: After "Forecasting" in navigation menu
  - Active state: highlight when on forecast-accuracy page

- [ ] **TASK-568**: Performance and UX optimization
  - Measure page load time (target: under 2 seconds)
  - Measure chart render time (target: under 500ms)
  - Add loading spinners while fetching data
  - Add error messages if API calls fail
  - Test with large dataset (1,768 SKUs with accuracy data)
  - Optimize SQL queries if slow (check EXPLAIN, add indexes)

### Phase 5: Advanced Features (TASK-569 to TASK-580) - Deferred to Future

**Objective**: Real-time learning triggers, audit trails, and automated adjustments for mature learning system.

**Note**: This phase is planned but implementation is deferred until MVP (Phases 1-4) is complete and validated in production. These features require additional complexity and testing.

- [ ] **TASK-569**: Create forecast_learning_log audit trail table
  - Design: id, sku_id, learning_type, original_assumption, learned_insight
  - Add: confidence_score, supporting_data_points, action_taken, expected_improvement, actual_improvement
  - Purpose: Complete audit trail of all learning decisions and their outcomes
  - Defer reason: MVP focuses on logging adjustments, not full decision history

- [ ] **TASK-570**: Implement RealTimeLearningTriggers class
  - Class for event-driven learning (doesn't wait for monthly cycles)
  - Methods: on_stockout_detected, on_viral_growth_detected, on_seasonal_shift
  - Purpose: Immediate learning when critical events occur
  - Defer reason: Requires webhook/event system integration

- [ ] **TASK-571**: Add on_stockout_detected() trigger
  - Webhook: When stockout detected in stockout_dates table
  - Check: Recent forecast vs actual demand (if actual > predicted * 1.2)
  - Action: Immediate growth rate increase (magnitude 0.05)
  - Flag: Priority review for inventory team
  - Defer reason: Needs real-time monitoring infrastructure

- [ ] **TASK-572**: Add on_viral_growth_detected() trigger
  - Webhook: When growth_status changes to 'viral' in skus table
  - Action: Switch to short-term forecasting methods
  - Action: Increase forecast frequency (weekly instead of monthly)
  - Action: Adjust data weighting (recent_weight=0.8 for viral products)
  - Defer reason: Requires forecast frequency flexibility not in MVP

- [ ] **TASK-573**: Add on_seasonal_shift() trigger
  - Webhook: When seasonal pattern changes significantly
  - Action: Trigger immediate seasonal factor recalculation
  - Action: Alert forecasting team of pattern shift
  - Defer reason: Needs automated seasonal recalculation system

- [ ] **TASK-574**: Implement automated adjustment application
  - Current: Adjustments logged to forecast_learning_adjustments with applied=FALSE
  - Enhancement: Auto-apply adjustments with high confidence (>0.8) and low risk
  - Logic: Review by ABC class (auto-apply for C, require approval for A)
  - Tracking: Update applied=TRUE, applied_date when used in forecast
  - Defer reason: Needs stakeholder approval workflow

- [ ] **TASK-575**: Add confidence interval predictions
  - Calculate prediction intervals based on historical MAPE
  - Display: forecast ± (forecast * historical_mape / 100)
  - Example: 1000 units ± 15% = 850-1150 units (confidence interval)
  - Purpose: Help users understand forecast uncertainty
  - Defer reason: Requires statistical distribution modeling

- [ ] **TASK-576**: Implement email alerts for chronic issues
  - Trigger: SKU with MAPE > 50% for 3+ consecutive months
  - Email: To inventory manager with SKU details, recommendations
  - Integration: Use existing email system or SMTP configuration
  - Defer reason: Needs email infrastructure setup

- [ ] **TASK-577**: Create learning history API endpoint
  - Route: GET /api/forecasts/accuracy/sku/{sku_id}/learning-history
  - Query forecast_learning_log for complete decision history
  - Return: learning_type, original_assumption, learned_insight, action_taken, improvements
  - Defer reason: Depends on forecast_learning_log table (TASK-569)

- [ ] **TASK-578**: Add ensemble forecasting methods
  - Combine multiple methods (weighted_ma, seasonal, trend) with weighted average
  - Use for high-volatility SKUs (XYZ=Z) where single method unreliable
  - Weights based on historical method performance
  - Defer reason: Requires method performance tracking and weighting algorithm

- [ ] **TASK-579**: Implement A/B testing framework
  - Test new forecasting methods on subset of SKUs
  - Compare performance: new method vs current method
  - Auto-promote if new method shows 10%+ MAPE improvement
  - Defer reason: Requires parallel forecast generation and comparison infrastructure

- [ ] **TASK-580**: Document Phase 5 implementation plan
  - Detailed design docs for each advanced feature
  - Prerequisites: MVP must be in production for 3+ months
  - Success criteria: Establish before implementing advanced features
  - Timeline: Estimate 12-15 hours additional effort
  - Defer reason: Focus on MVP validation before advanced features

---

## V8.0 Implementation Timeline

**Week 1** (2-3 hours): Database Phase (TASK-511 to TASK-515)
- Enhance schema, create tables, test migrations

**Week 2** (6-8 hours): Phase 1 - Enhanced Forecast Recording (TASK-516 to TASK-525)
- Implement recording function, integrate into forecasting, test context capture

**Week 3** (8-10 hours): Phase 2 - Stockout-Aware Accuracy Update (TASK-526 to TASK-538)
- Implement monthly accuracy job, add stockout awareness, test MAPE calculations

**Week 4** (10-12 hours): Phase 3 - Multi-Dimensional Learning (TASK-539 to TASK-555)
- Build learning engine, implement ABC/XYZ learning rates, test algorithms

**Week 5** (6-8 hours): Phase 4 - Reporting Dashboard (TASK-556 to TASK-568)
- Create API endpoints, build dashboard, test with Playwright

**Total MVP Timeline**: 30-38 hours across 5 weeks (MVP = Phases 1-4)

**Future**: Phase 5 Advanced Features (12-15 hours) - Deferred until MVP validated in production

---

**Next Task**: TASK-511 (Database schema enhancement for forecast_accuracy table)

**Status**: PLANNED - Ready for implementation after stakeholder approval

**Detailed Implementation Guide**: [FORECAST_LEARNING_ENHANCED_PLAN.md](FORECAST_LEARNING_ENHANCED_PLAN.md)
