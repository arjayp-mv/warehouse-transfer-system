     Overview

     Build a separate forecasting page with full dashboard (Phase 1 + 2) that leverages existing corrected    
      demand data (stockout-adjusted) and calculates seasonal patterns on-the-fly for missing SKUs.
     Follows Claude Code best practices: no page-load calculations, pagination, modular architecture.

     ---
     Phase 1: Database Schema (Week 1, Day 1)

     1.1 Create New Tables

     File: database/add_forecast_tables.sql
     - forecast_runs - Master forecast table
     - forecast_details - Monthly forecasts by SKU/warehouse
     - forecast_adjustments - Manual override log

     1.2 Apply Migration

     - Run SQL script via XAMPP/phpMyAdmin
     - Verify tables created successfully

     ---
     Phase 2: Backend - Forecast Engine (Week 1, Days 2-4)

     2.1 Seasonal Pattern Calculator

     File: backend/seasonal_calculator.py (~250 lines)
     - calculate_seasonal_factors(sku_id, warehouse) - Calculate 12-month factors
     - detect_pattern_type() - spring_summer, fall_winter, holiday, year_round
     - calculate_confidence_score() - Based on data quality
     - Batch Mode: Calculate missing seasonal factors for all SKUs (only 36/1769 currently exist)
     - Store in seasonal_factors and seasonal_patterns_summary tables

     2.2 Forecast Calculation Engine

     File: backend/forecasting.py (~300 lines)

     Core Functions:
     # Uses EXISTING corrected_demand fields (stockout-adjusted)
     def calculate_base_demand(sku_id, warehouse):
         # Query sku_demand_stats for corrected weighted averages
         # Use demand_3mo_weighted or demand_6mo_weighted based on CV

     def apply_seasonal_adjustment(base_demand, sku_id, warehouse):
         # Get or calculate seasonal_factors (if missing)
         # Apply monthly seasonal factors with confidence weighting

     def calculate_growth_trend(sku_id, warehouse):
         # Compare last 12mo vs previous 12mo
         # Apply caps based on growth_status (viral/declining/normal)

     def generate_12_month_forecast(sku_id, warehouse):
         base = calculate_base_demand()
         seasonal = apply_seasonal_adjustment()
         growth = calculate_growth_trend()

         for month in 1..12:
             forecast[month] = base * seasonal[month] * (1 + growth)

         return forecast with confidence score

     ABC/XYZ Methods:
     - AX: demand_6mo_weighted, 90% confidence
     - AY: demand_3mo_weighted, 80% confidence
     - AZ: demand_3mo_simple, 60% confidence
     - (Full matrix as per PRD)

     2.3 API Endpoints

     File: backend/forecasting_api.py (~200 lines)

     POST   /api/forecasts/generate      # Create new forecast run (background job)
     GET    /api/forecasts               # List all forecasts (paginated, 50/page)
     GET    /api/forecasts/{id}          # Get forecast details (paginated, 100 SKUs/page)
     GET    /api/forecasts/{id}/export   # Export CSV
     DELETE /api/forecasts/{id}          # Delete forecast run
     GET    /api/forecasts/{id}/accuracy # Compare vs actuals

     Background Job Pattern (from best practices):
     # Thread-based worker for forecast generation
     def generate_forecast_background(forecast_run_id):
         # Process in batches of 100 SKUs
         # Update forecast_details table
         # No user waiting - async processing

     2.4 Register Routes

     File: backend/main.py
     - Import forecasting_api routes
     - Add to FastAPI app

     ---
     Phase 3: Frontend - Forecast Dashboard (Week 1-2, Days 5-7)

     3.1 Main Forecasting Page

     File: frontend/forecasting.html (~350 lines)

     Structure:
     <!-- Header with Key Metrics -->
     <div class="metrics-cards">
         - 12M Forecast Total
         - YoY Growth %
         - Average Confidence
         - SKUs at Risk
     </div>

     <!-- Forecast Generation Wizard -->
     <div class="forecast-wizard">
         - Name forecast
         - Set growth assumption
         - Advanced options (seasonal patterns, stockout correction)
         - [Generate Forecast] button → background job
     </div>

     <!-- Forecast List Table -->
     <table id="forecast-list">
         - DataTables with pagination (50 per page)
         - Columns: Name, Date, Status, Total Forecast, Actions
         - Export CSV, View Details, Delete
     </table>

     <!-- SKU Detail View (Modal) -->
     <div id="forecast-detail-modal">
         - SKU breakdown table (paginated, 100/page)
         - Monthly forecast chart
         - Confidence indicators
         - Manual adjustment capability
     </div>

     3.2 Frontend JavaScript

     File: frontend/js/forecasting.js (~350 lines)

     Key Functions:
     // Load forecast list (from pre-calculated data)
     async function loadForecastList(page = 1) {
         // GET /api/forecasts?page=1&limit=50
         // Populate DataTable (NO calculations)
     }

     // Generate new forecast (background job)
     async function generateForecast(params) {
         // POST /api/forecasts/generate
         // Show loading indicator
         // Poll for completion status
     }

     // Load SKU details (paginated)
     async function loadForecastDetails(forecastId, page = 1) {
         // GET /api/forecasts/{id}?page=1&limit=100
         // Render monthly forecast table
         // Show confidence scores
     }

     // Export to CSV
     async function exportForecast(forecastId) {
         // GET /api/forecasts/{id}/export
         // Download CSV file
     }

     // Chart rendering (Recharts/Chart.js)
     function renderForecastChart(data) {
         // Line chart: 12 months
         // Confidence bands
     }

     3.3 Navigation Integration

     Files: frontend/index.html, frontend/transfer-planning.html
     - Add "Forecasting" link to navbar
     - URL: /static/forecasting.html

     ---
     Phase 4: Charts & Visualizations (Week 2)

     4.1 Dashboard Charts

     Library: Chart.js or Recharts (lightweight)

     Charts:
     1. Forecast vs History - Line chart with 12mo history + 12mo forecast
     2. Category Breakdown - Stacked bar by month
     3. ABC/XYZ Performance Matrix - Heat map
     4. Confidence Distribution - Histogram

     4.2 SKU Detail Charts

     1. Monthly Forecast Bar Chart - With confidence bands
     2. Seasonality Pattern - Radar/line chart showing seasonal factors
     3. Growth Trend - Historical trend line

     ---
     Phase 5: Testing & Optimization (Week 2)

     5.1 Performance Testing

     - Test with full dataset (1,769 SKUs)
     - Forecast generation time: <60 seconds
     - Dashboard load: <2 seconds
     - Export generation: <10 seconds

     5.2 Data Validation

     - Verify corrected demand is used correctly (stockout-adjusted)
     - Validate seasonal factors calculated properly
     - Check ABC/XYZ method selection logic
     - Confirm confidence scoring

     5.3 Edge Cases

     - New SKUs (< 6 months history)
     - SKUs with no seasonal pattern
     - Death Row SKUs (pending discontinuation)
     - Viral growth SKUs (>100% YoY)

     ---
     Key Implementation Principles (Claude Code Best Practices)

     ✅ NEVER Calculate on Page Load

     - All forecasts pre-calculated in background
     - Stored in forecast_details table
     - UI only fetches and displays cached data

     ✅ Always Paginate

     - Forecast list: 50 items per page
     - SKU details: 100 items per page
     - Use DataTables for efficient pagination

     ✅ Database Aggregation

     - All calculations done in Python backend
     - Results stored in database
     - Frontend queries pre-aggregated data

     ✅ File Size Limits

     - Each Python file: 200-300 lines
     - HTML: 300-400 lines
     - JavaScript: 300-400 lines

     ✅ Modular Architecture

     backend/
       forecasting.py           # Core forecast engine (~300 lines)
       seasonal_calculator.py   # Seasonal analysis (~250 lines)
       forecasting_api.py       # API endpoints (~200 lines)

     frontend/
       forecasting.html         # Main page (~350 lines)
       js/forecasting.js        # Frontend logic (~350 lines)

     database/
       add_forecast_tables.sql  # Schema migration

     ---
     Data Flow Architecture

     1. User clicks "Generate Forecast"
        ↓
     2. POST /api/forecasts/generate (background job starts)
        ↓
     3. Backend loops through all active SKUs:
        - Get corrected_demand from monthly_sales (ALREADY stockout-adjusted)
        - Calculate/retrieve seasonal_factors (generate if missing)
        - Calculate growth trend
        - Generate 12-month forecast
        - Calculate confidence score
        - Store in forecast_details table
        ↓
     4. Background job completes
        ↓
     5. UI polls for completion, refreshes list
        ↓
     6. User views forecast (loads from forecast_details - NO calculation)

     ---
     Success Metrics

     Performance

     - Forecast generation: <60 seconds for 1,769 SKUs
     - Dashboard load: <2 seconds
     - Paginated views: 50-100 items max
     - Export: <10 seconds

     Accuracy

     - Uses corrected demand (stockout-adjusted)
     - Applies seasonal patterns with confidence weighting
     - Incorporates growth trends
     - ABC/XYZ-specific methods

     User Experience

     - No page-load calculations
     - Background job with progress indicator
     - Paginated results
     - CSV export for analysis

     ---
     File Structure Summary

     warehouse-transfer/
     ├── database/
     │   └── add_forecast_tables.sql        # NEW: Schema migration
     ├── backend/
     │   ├── forecasting.py                 # NEW: Forecast engine
     │   ├── seasonal_calculator.py         # NEW: Seasonal analysis
     │   ├── forecasting_api.py             # NEW: API endpoints
     │   └── main.py                        # MODIFY: Register routes
     ├── frontend/
     │   ├── forecasting.html               # NEW: Forecast page
     │   ├── js/
     │   │   └── forecasting.js             # NEW: Frontend logic
     │   ├── index.html                     # MODIFY: Add nav link
     │   └── transfer-planning.html         # MODIFY: Add nav link
     └── docs/
         └── forecasting.md                 # REFERENCE: PRD

     ---
     Timeline Estimate

     - Week 1:
       - Day 1: Database schema
       - Days 2-3: Backend engine + seasonal calculator
       - Days 4-5: API endpoints + testing
       - Days 6-7: Frontend HTML + basic JavaScript
     - Week 2:
       - Days 1-2: Charts and visualizations
       - Days 3-4: Testing and optimization
       - Day 5: Polish and documentation

     Total: ~10-12 days for full implementation

     ---
     Next Steps

     1. Create database migration SQL file
     2. Build seasonal calculator (handles missing factors)
     3. Build forecast engine (uses corrected demand)
     4. Create API endpoints with background jobs
     5. Build frontend with pagination
     6. Add charts and visualizations
     7. Test and optimize