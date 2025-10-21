  What Was Accomplished in This Session

  V7.3 Phase 1 & 2: Pattern Detection & Auto-Sync (COMPLETED)

  Problem: New SKU forecasts were severely under-forecasted (UB-YTX7A-BS showing 42 units instead of expected ~60-90 units).

  Root Cause:
  - June-July 2025 had 0 stockout_days in monthly_sales table despite actual stockouts
  - Pattern detection incorrectly treated stockout months as "low sales periods"
  - June 2025: Only 1 unit sold but availability_rate = 1.0 (100%)

  Solution Implemented:

  1. Automatic Stockout Data Sync (backend/forecast_jobs.py:102-109)
    - Added auto-sync call before forecasting begins
    - Syncs monthly_sales.stockout_days from stockout_dates table
    - Processed 3,268 records for 504 SKUs in ~20 seconds
  2. Test & Learn Pattern Detection (backend/forecasting.py:732-847)
    - Launch spike detection: max_month > avg_others * 1.3
    - Early stockout detection: Check first max(3, len//2) months
    - Weighted baseline: (recent_3 * 0.7) + (older_3 * 0.3)
    - Stockout boost: 1.2x multiplier when early stockout proves demand
    - Safety multiplier: 1.1x for pattern-based (vs 1.3-1.5x standard)
  3. Bug Fixes:
    - Availability rate CASE now checks stockout_days before sales
    - Launch spike uses max_month instead of first_month
    - Edge case handling for uniform clean_months values (prevents StatisticsError)
    - Comprehensive debug logging throughout pattern detection

  Results:
  - UB-YTX7A-BS: 42.59 → 79.20 units/month (84% improvement)
  - Method: "limited_data_test_launch" (correctly identified)
  - Baseline: 72.00 (avg of clean months [24, 133, 100, 31])
  - June properly excluded (30 stockout_days, availability < 30%)
  - UB-YTX14-BS: Unchanged (2,708 base) - regression test passed

  Files Modified:
  - backend/forecast_jobs.py (lines 102-109)
  - backend/forecasting.py (lines 732-848)
  - docs/TASKS.md (V7.3 completion documentation)

  Committed to GitHub: Commit cbd86a3 - "feat: V7.3 New SKU Pattern Detection & Stockout Auto-Sync"

  ---
  What Still Needs to Be Done

  V7.3 Phase 3A: Similar SKU Matching & Enhanced Forecasting (NEXT TO IMPLEMENT)

  Scope: Enhance forecasting for new SKUs (3-6 months data) that don't trigger Test & Learn pattern detection.

  User Decisions Made:
  - ❌ Skip growth rate fallback from similar SKUs (needs validation)
  - ❌ Skip pending inventory checks (belongs in future ordering page, not forecasting)
  - ✅ Implement similar SKU seasonal factor averaging
  - ✅ Fix growth_rate_source metadata persistence bug

  Detailed Implementation Plan

  1. Similar SKU Matching Function

  Location: backend/forecasting.py (add new helper function)

  def _find_similar_skus(sku_id: str, category: str, abc_code: str, xyz_code: str, limit: int = 5) -> List[Dict]:
      """
      Find similar SKUs for new product forecasting.
      
      Matches by:
      - Same category
      - Same ABC code (value classification)
      - Same XYZ code (variability classification)
      - Must have >= 12 months of data (established patterns)
      
      Args:
          sku_id: SKU to find matches for (excluded from results)
          category: Product category
          abc_code: ABC classification (A/B/C)
          xyz_code: XYZ classification (X/Y/Z)
          limit: Maximum matches to return
      
      Returns:
          List of dicts with: sku_id, months_of_data, avg_demand, seasonal_factors
      """
      query = """
          SELECT 
              s.sku_id,
              COUNT(DISTINCT ms.year_month) as months_of_data,
              AVG((ms.corrected_demand_burnaby + ms.corrected_demand_kentucky)) as avg_demand,
              s.seasonal_factors
          FROM skus s
          JOIN monthly_sales ms ON s.sku_id = ms.sku_id
          WHERE s.sku_id != %s
            AND s.category = %s
            AND s.abc_code = %s
            AND s.xyz_code = %s
            AND s.status = 'Active'
            AND s.seasonal_factors IS NOT NULL
          GROUP BY s.sku_id, s.seasonal_factors
          HAVING COUNT(DISTINCT ms.year_month) >= 12
          ORDER BY COUNT(DISTINCT ms.year_month) DESC, avg_demand DESC
          LIMIT %s
      """
      results = execute_query(query, params=(sku_id, category, abc_code, xyz_code, limit), fetch_all=True)

      similar_skus = []
      for row in results:
          # Parse seasonal_factors JSON string to dict
          factors = json.loads(row['seasonal_factors']) if row['seasonal_factors'] else None
          similar_skus.append({
              'sku_id': row['sku_id'],
              'months_of_data': row['months_of_data'],
              'avg_demand': float(row['avg_demand']),
              'seasonal_factors': factors
          })

      return similar_skus

  2. Integrate Similar SKU Logic

  Location: backend/forecasting.py _handle_limited_data_sku() function (around line 900-950)

  Add after pattern detection but before fallback to category average:

  # STEP 4: If no pattern detected, try similar SKU matching
  if baseline_from_pattern is None:
      print(f"[DEBUG V7.3] {sku_id}: No pattern detected, attempting similar SKU matching")

      # Find similar SKUs
      similar_skus = _find_similar_skus(
          sku_id=sku_id,
          category=sku_data.get('category'),
          abc_code=sku_data.get('abc_code'),
          xyz_code=sku_data.get('xyz_code'),
          limit=5
      )

      if similar_skus and len(similar_skus) >= 2:
          print(f"[DEBUG V7.3] {sku_id}: Found {len(similar_skus)} similar SKUs")

          # Average seasonal factors from similar SKUs
          month_factors = {month: [] for month in range(1, 13)}
          for sim in similar_skus:
              if sim['seasonal_factors']:
                  for month_str, factor in sim['seasonal_factors'].items():
                      month_num = int(month_str)
                      month_factors[month_num].append(factor)

          # Calculate averaged factors
          averaged_factors = {}
          for month, factors_list in month_factors.items():
              if factors_list:
                  averaged_factors[month] = statistics.mean(factors_list)

          # Store for later use
          seasonal_factors_from_similar = averaged_factors
          similar_skus_used = [s['sku_id'] for s in similar_skus]

          # Update metadata
          metadata['similar_skus_used'] = similar_skus_used
          metadata['similar_sku_count'] = len(similar_skus)
          metadata['method_used'] = 'limited_data_similar_skus'
          metadata['confidence'] = 0.45  # Lower than pattern-based (0.55)

          print(f"[DEBUG V7.3] {sku_id}: Using seasonal factors from similar SKUs: {similar_skus_used}")
      else:
          print(f"[DEBUG V7.3] {sku_id}: No suitable similar SKUs found (need >= 2)")
          seasonal_factors_from_similar = None

  3. Fix growth_rate_source Metadata Bug

  Location: backend/forecasting.py save_forecast() function (around line 662-677)

  Current Issue: growth_rate_source shows empty string in database despite being set.

  Root Cause: Column order mismatch in INSERT statement or missing column in forecast_details table.

  Fix:
  1. Verify forecast_details table schema has growth_rate_source column
  2. Check INSERT statement column order matches VALUES order exactly
  3. Add debug print before INSERT to verify value is set:

  print(f"[DEBUG V7.3] Saving forecast with growth_rate_source: {forecast_data.get('growth_rate_source', 'NOT SET')}")

  Location of INSERT: backend/forecasting.py around line 662-677

  Look for this pattern:
  INSERT INTO forecast_details (
      forecast_run_id, sku_id, warehouse,
      base_demand_used, method_used,
      growth_rate_applied, growth_rate_source,  # Verify this column exists and is in right position
      ...
  ) VALUES (%s, %s, %s, %s, %s, %s, %s, ...)

  4. Add similar_skus_used Column (Optional)

  If you want to track which similar SKUs were used for audit:

  ALTER TABLE forecast_details
  ADD COLUMN similar_skus_used TEXT AFTER growth_rate_source;

  Then update INSERT statement to include it.

  Test Cases for Phase 3A

  1. UB-YTX7A-BS: Should still use pattern detection (has 9 months + launch spike)
    - Method: "limited_data_test_launch"
    - Should NOT use similar SKU matching
  2. New SKU with 4 months, no pattern: Should use similar SKU seasonal factors
    - Find a SKU with 3-6 months data
    - Verify method: "limited_data_similar_skus"
    - Check similar_skus_used field populated
  3. growth_rate_source persistence:
    - Query: SELECT growth_rate_source FROM forecast_details WHERE sku_id = 'UB-YTX7A-BS' AND forecast_run_id = 34
    - Should show: "proven_demand_stockout" (not empty string)

  Performance Target

  - Similar SKU matching: < 200ms per SKU
  - No impact on overall forecast generation time (< 20 seconds for 1,768 SKUs)

  ---
  V7.3 Phase 4: Queue Management System (AFTER Phase 3A)

  Scope: Handle concurrent forecast requests gracefully, preventing "job already running" errors.

  Detailed Implementation Plan

  1. Backend Queue System

  Location: backend/forecast_jobs.py (modify existing worker)

  Add at module level:
  import queue
  import threading

  # Global forecast queue
  _forecast_queue = queue.Queue()
  _queue_lock = threading.Lock()

  Modify start_forecast_generation() function:
  def start_forecast_generation(...) -> dict:
      """
      Start a new forecast generation job.
      
      Returns:
          dict with keys: run_id, status (either 'started' or 'queued')
      """
      if _forecast_worker.is_running:
          # Another forecast is running, add to queue
          with _queue_lock:
              queue_position = _forecast_queue.qsize() + 1

          # Create forecast run entry with 'queued' status
          run_id = create_forecast_run(forecast_name, growth_rate, warehouse, status='queued')

          # Add to queue
          _forecast_queue.put({
              'run_id': run_id,
              'sku_ids': sku_ids,
              'warehouse': warehouse,
              'growth_rate': growth_rate
          })

          # Update queue position in database
          update_forecast_run_status(run_id, status='queued', queue_position=queue_position)

          logger.info(f"Forecast {run_id} queued at position {queue_position}")

          return {'run_id': run_id, 'status': 'queued', 'queue_position': queue_position}

      else:
          # No forecast running, start immediately
          run_id = create_forecast_run(forecast_name, growth_rate, warehouse)
          _forecast_worker.start_forecast_job(run_id, sku_ids, warehouse, growth_rate)

          return {'run_id': run_id, 'status': 'started'}

  Add queue processing in worker's _run_forecast_job():
  def _run_forecast_job(...):
      try:
          # ... existing forecast logic ...

      finally:
          self.is_running = False
          self.current_job_id = None

          # Process next job in queue
          _process_next_queued_job()

  def _process_next_queued_job():
      """Check queue and start next job if available."""
      if not _forecast_queue.empty():
          next_job = _forecast_queue.get()

          logger.info(f"Processing queued forecast {next_job['run_id']}")

          _forecast_worker.start_forecast_job(
              next_job['run_id'],
              next_job['sku_ids'],
              next_job['warehouse'],
              next_job['growth_rate']
          )

  2. Database Support

  Add migration: database/add_queue_support.sql
  ALTER TABLE forecast_runs
  ADD COLUMN queue_position INT NULL AFTER status,
  ADD COLUMN queued_at TIMESTAMP NULL AFTER created_at;

  -- Update status enum to include 'queued'
  ALTER TABLE forecast_runs
  MODIFY COLUMN status ENUM('pending', 'queued', 'running', 'completed', 'failed', 'cancelled')
  DEFAULT 'pending';

  3. API Endpoints

  Location: backend/forecasting_api.py

  Add new endpoints:
  @router.get("/forecasts/queue", response_model=List[Dict])
  async def get_forecast_queue():
      """Get current forecast queue status."""
      query = """
          SELECT id, forecast_name, queue_position, queued_at, total_skus
          FROM forecast_runs
          WHERE status = 'queued'
          ORDER BY queue_position ASC
      """
      results = execute_query(query, fetch_all=True)
      return results

  @router.delete("/forecasts/queue/{run_id}")
  async def cancel_queued_forecast(run_id: int):
      """Remove a forecast from the queue."""
      # Check if queued
      check_query = "SELECT status FROM forecast_runs WHERE id = %s"
      result = execute_query(check_query, params=(run_id,), fetch_all=True)

      if not result or result[0]['status'] != 'queued':
          raise HTTPException(status_code=400, detail="Forecast not in queue")

      # Update status to cancelled
      update_forecast_run_status(run_id, status='cancelled')

      # TODO: Remove from queue.Queue() - need to implement queue item removal

      return {"message": "Forecast removed from queue", "run_id": run_id}

  Modify existing generate endpoint:
  @router.post("/forecasts/generate")
  async def generate_forecast(request: ForecastGenerateRequest):
      try:
          result = start_forecast_generation(...)

          if result['status'] == 'queued':
              return {
                  "message": "Forecast queued",
                  "run_id": result['run_id'],
                  "queue_position": result['queue_position']
              }
          else:
              return {
                  "message": "Forecast generation started",
                  "run_id": result['run_id']
              }
      except RuntimeError as e:
          # This should not happen anymore with queue system
          raise HTTPException(status_code=409, detail=str(e))

  4. Frontend UI

  Location: frontend/forecasting.html

  Add confirmation modal (around line 100):
  <!-- Queue Confirmation Modal -->
  <div class="modal fade" id="queueConfirmModal" tabindex="-1">
      <div class="modal-dialog">
          <div class="modal-content">
              <div class="modal-header">
                  <h5 class="modal-title">Forecast Already Running</h5>
                  <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
              <div class="modal-body">
                  <p>A forecast generation is currently in progress.</p>
                  <p><strong>Queue Position:</strong> <span id="queuePositionText">1</span></p>
                  <p><strong>Estimated Wait:</strong> <span id="estimatedWaitText">15-20 minutes</span></p>
                  <p>Would you like to queue this forecast or cancel?</p>
              </div>
              <div class="modal-footer">
                  <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                  <button type="button" class="btn btn-primary" id="confirmQueueBtn">Queue Forecast</button>
              </div>
          </div>
      </div>
  </div>

  Location: frontend/forecasting.js

  Modify generateForecast() function (around line 50):
  async function generateForecast() {
      const forecastName = document.getElementById('forecastName').value;
      // ... get other fields ...

      try {
          const response = await fetch('/api/forecasts/generate', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(requestData)
          });

          const result = await response.json();

          if (result.queue_position) {
              // Show queue confirmation modal
              document.getElementById('queuePositionText').textContent = result.queue_position;
              document.getElementById('estimatedWaitText').textContent =
                  `${result.queue_position * 15}-${result.queue_position * 20} minutes`;

              const modal = new bootstrap.Modal(document.getElementById('queueConfirmModal'));
              modal.show();

              // Store run_id for potential cancellation
              window.pendingQueuedRunId = result.run_id;
          } else {
              showAlert('success', 'Forecast generation started!');
              loadForecastList();
              startProgressPolling(result.run_id);
          }

      } catch (error) {
          showAlert('danger', 'Failed to start forecast generation');
      }
  }

  Add queue status indicator in forecast list:
  function renderForecastRow(run) {
      let statusBadge = '';
      if (run.status === 'queued') {
          statusBadge = `<span class="badge bg-info">QUEUED (Position ${run.queue_position})</span>`;
      } else if (run.status === 'running') {
          statusBadge = '<span class="badge bg-primary">RUNNING</span>';
      }
      // ... rest of function
  }

  Test Cases for Phase 4

  1. Concurrent Forecast Test:
    - Generate forecast A (should start)
    - Immediately generate forecast B (should queue with position 1)
    - Verify modal shows queue confirmation
    - Complete forecast A
    - Verify forecast B auto-starts
  2. Cancel Queued Forecast:
    - Queue forecast B (while A is running)
    - Click cancel on forecast B in list
    - Verify status changes to 'cancelled'
    - Verify forecast B doesn't start when A completes
  3. Multiple Queued Forecasts:
    - Generate 3 forecasts in quick succession
    - Verify queue positions: 1, 2, 3
    - Verify FIFO processing order

  Performance Target

  - Queue operations: < 100ms
  - No impact on forecast generation speed

  ---
  V7.4: Auto Growth Rate Calculation (FUTURE PLAN)

  Status: DEFERRED until Phase 3A similar SKU matching is validated and we have production data on trend predictability.

  Detailed Implementation Plan

  Scope: Automatically calculate SKU-specific growth rates using weighted linear regression instead of manual input.

  Algorithm: Weighted Linear Regression with Exponential Decay

  def calculate_auto_growth_rate(sku_id: str, months_window: int = 12) -> Dict:
      """
      Calculate automatic growth rate using weighted linear regression.
      
      Uses exponential weighting: weight = 0.5^(n-i) where n is total months, i is month index.
      Recent months have higher weight (approach 1.0), older months decay to 0.0.
      
      Args:
          sku_id: SKU to analyze
          months_window: Lookback period (6-12 months recommended)
      
      Returns:
          dict with: growth_rate (monthly %), confidence (0-1), method_used, data_points
      """
      # Get monthly demand data
      query = """
          SELECT year_month, 
                 (corrected_demand_burnaby + corrected_demand_kentucky) as demand
          FROM monthly_sales
          WHERE sku_id = %s
            AND (corrected_demand_burnaby > 0 OR corrected_demand_kentucky > 0)
          ORDER BY year_month DESC
          LIMIT %s
      """
      results = execute_query(query, params=(sku_id, months_window), fetch_all=True)

      if len(results) < 6:
          # Not enough data for SKU-specific trend
          return {
              'growth_rate': None,
              'confidence': 0.0,
              'method_used': 'insufficient_data',
              'data_points': len(results)
          }

      # Reverse to chronological order (oldest first)
      results = list(reversed(results))

      # Prepare data for regression
      n = len(results)
      x_values = list(range(n))  # 0, 1, 2, ..., n-1
      y_values = [float(row['demand']) for row in results]

      # Calculate exponential weights (recent months weighted higher)
      weights = [0.5 ** (n - i - 1) for i in range(n)]

      # Weighted linear regression
      sum_w = sum(weights)
      sum_wx = sum(w * x for w, x in zip(weights, x_values))
      sum_wy = sum(w * y for w, y in zip(weights, y_values))
      sum_wxx = sum(w * x * x for w, x in zip(weights, x_values))
      sum_wxy = sum(w * x * y for w, x, y in zip(weights, x_values, y_values))

      # Calculate slope (monthly change)
      denominator = (sum_w * sum_wxx) - (sum_wx ** 2)
      if abs(denominator) < 1e-10:
          # Flat trend
          return {
              'growth_rate': 0.0,
              'confidence': 0.7,
              'method_used': 'flat_trend',
              'data_points': n
          }

      slope = ((sum_w * sum_wxy) - (sum_wx * sum_wy)) / denominator
      intercept = (sum_wy - slope * sum_wx) / sum_w

      # Calculate average demand
      avg_demand = sum_wy / sum_w

      # Growth rate = (slope / avg_demand) * 100
      # This gives percentage change per month
      if avg_demand > 0:
          growth_rate_pct = (slope / avg_demand) * 100
      else:
          growth_rate_pct = 0.0

      # Apply safety cap: ±50% per month
      growth_rate_pct = max(-50.0, min(50.0, growth_rate_pct))

      # Calculate confidence based on data quality
      # More data points = higher confidence
      # Lower variance = higher confidence
      confidence = min(1.0, (n - 5) / 7.0)  # 6 months = 0.14, 12+ months = 1.0

      return {
          'growth_rate': growth_rate_pct / 100.0,  # Convert to decimal (0.05 = 5%)
          'confidence': confidence,
          'method_used': 'weighted_regression',
          'data_points': n,
          'slope': slope,
          'avg_demand': avg_demand
      }

  Category-Level Fallback:

  def get_category_growth_rate(category: str) -> float:
      """
      Calculate category-average growth rate for SKUs without enough individual data.
      
      Uses all Active SKUs in category with >= 12 months data.
      """
      query = """
          SELECT s.sku_id
          FROM skus s
          JOIN monthly_sales ms ON s.sku_id = ms.sku_id
          WHERE s.category = %s
            AND s.status = 'Active'
          GROUP BY s.sku_id
          HAVING COUNT(DISTINCT ms.year_month) >= 12
      """
      results = execute_query(query, params=(category,), fetch_all=True)

      if not results:
          return 0.0  # No category data

      # Calculate individual growth rates
      growth_rates = []
      for row in results:
          gr = calculate_auto_growth_rate(row['sku_id'], months_window=12)
          if gr['growth_rate'] is not None:
              growth_rates.append(gr['growth_rate'])

      if not growth_rates:
          return 0.0

      # Return median (more robust than mean)
      return statistics.median(growth_rates)

  Integration Points:

  1. In generate_forecast_for_sku() (backend/forecasting.py):
  # Calculate growth rate
  if manual_growth_override is not None:
      growth_rate = manual_growth_override
      growth_source = 'manual_override'
  else:
      # Auto-calculate
      gr_result = calculate_auto_growth_rate(sku_id)

      if gr_result['growth_rate'] is not None and gr_result['confidence'] >= 0.5:
          growth_rate = gr_result['growth_rate']
          growth_source = 'auto_sku_specific'
      else:
          # Fallback to category average
          growth_rate = get_category_growth_rate(category)
          growth_source = 'auto_category_average'

  2. Frontend Display (frontend/forecasting.html):
  - Add "Growth Rate" column in forecast results table
  - Show source in tooltip (manual, auto-SKU, auto-category)
  - Add toggle: "Use auto-calculated growth rates" (default ON)

  3. API Response Enhancement (backend/forecasting_api.py):
  # Add growth_rate and growth_source to forecast results
  {
      "sku_id": "UB-YTX14-BS",
      "base_demand": 2708,
      "growth_rate": -0.37,  # -37% monthly decline
      "growth_source": "auto_sku_specific",
      "confidence": 0.85,
      ...
  }

  Test Cases for V7.4

  1. UB-YTX14-BS (Declining SKU):
    - Should detect negative growth rate (~-30 to -40%)
    - Method: auto_sku_specific
    - Confidence: high (69 months data)
  2. New SKU with 4 months:
    - Should use category average growth rate
    - Method: auto_category_average
    - Confidence: medium
  3. Manual Override:
    - User sets growth rate = 0.10 (10%)
    - Should override auto-calculation
    - Method: manual_override
  4. Flat Trend SKU:
    - SKU with stable demand (no growth/decline)
    - Should detect ~0% growth rate
    - Method: auto_sku_specific (flat_trend)

  Performance Target

  - Growth rate calculation: < 50ms per SKU
  - No significant impact on overall forecast time

  ---
  Current File States

  Modified Files (Committed):
  - backend/forecast_jobs.py (auto-sync added at lines 102-109)
  - backend/forecasting.py (pattern detection at lines 732-847)
  - docs/TASKS.md (V7.3 Phase 1&2 completed, Phase 3A & 4 planned)

  Known Issues to Fix:
  1. growth_rate_source shows empty string in database (line ~662-677 in backend/forecasting.py)
  2. Debug print statements throughout forecasting.py (can be removed after validation)

  Database State:
  - monthly_sales.stockout_days properly synced for 504 SKUs
  - forecast_details table has all necessary columns
  - No schema changes needed for Phase 3A

  ---
  Key Technical Concepts

  Test & Learn Pattern: Industry-standard approach for new SKU forecasting that detects launch spikes and early stockouts to avoid under-forecasting successful test
  products.

  Availability Rate: (days_in_month - stockout_days) / days_in_month. Used to filter months for baseline calculations.

  Clean Months: Months with availability_rate >= 0.3 (30%). Below this threshold indicates severe stockout distortion.

  Expert Validation: Methodology reviewed in docs/claudesuggestion.md and docs/claudesuggestions2.md.

  ---
  Testing Recommendations

  Always Test With:
  - UB-YTX7A-BS (new SKU, 9 months, has pattern)
  - UB-YTX14-BS (established SKU, 69 months, regression test)
  - Find a 3-4 month SKU without pattern (for similar SKU matching test)

  Playwright Testing:
  - Generate forecast via UI
  - Check debug logs in server output
  - Query database to verify results
  - Export and verify CSV

  ---
  Important Notes

  1. Do not implement pending inventory checks - User confirmed this belongs in future ordering page, not forecasting.
  2. Do not use growth rate from similar SKUs yet - Needs validation that similar SKU trends are actually predictive.
  3. Queue Management is Phase 4 - Only start after Phase 3A is complete and tested.
  4. Debug logs can stay for now - Remove only after Phase 3A & 4 are stable in production.
  5. All code changes must follow project standards - No emojis, comprehensive docstrings, files under 500 lines.

  ---
  This context should be sufficient for the next Claude Code instance to continue implementation of Phase 3A and beyond.