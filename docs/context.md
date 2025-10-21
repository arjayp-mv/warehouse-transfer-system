  Executive Summary

  We implemented an expert "Test & Learn" pattern for new SKU forecasting (SKUs with < 12 months of data) based on industry best practices from docs/claudesuggestion.md.    
   The pattern detection logic is working correctly, but the calculated baseline is being overridden by subsequent safety multiplier calculations, resulting in the same     
  low forecasts as before (19.63 units instead of expected 90-110 units).

  ---
  Background Context

  Business Problem

  - SKU: UB-YTX7A-BS (new battery product, only 9 months of sales data)
  - Current Forecast: Declining from 20 → 19 → 17 units/month
  - Historical Pattern: [Jan: 0, Feb: 0, Mar: 24, Apr: 133, May: 100, Jun: 1, Jul: 38, Aug: 14, Sep: 31]
  - Actual Behavior: Launch spike (133 units) followed by stockout (1 unit = out of stock), then recovery phase
  - Expected Forecast: Should be ~90-110 units/month based on expert "Test & Learn" methodology

  Previous Work Completed

  1. ✅ Cache Issue Fixed: Python module caching was preventing new code from loading. Resolved by aggressive cache clearing and server restart.
  2. ✅ New SKU Detection: Added logic at backend/forecasting.py lines 425-436 to detect SKUs with < 12 months of data
  3. ✅ Empty Demands List Bug: Fixed StatisticsError at line 488 by adding empty list check
  4. ✅ Expert Pattern Implementation: Implemented "Test & Learn" pattern in _handle_limited_data_sku() at lines 686-939
  5. ✅ Metadata Return Pattern: Changed _get_base_demand() to return (base_demand, metadata) tuple
  6. ✅ Generate Forecast Integration: Updated to use metadata from _get_base_demand() at lines 355-411

  ---
  Technical Implementation Details

  File: backend/forecasting.py

  Entry Point: _get_base_demand() - Lines 410-501

  def _get_base_demand(self, sku_id: str, warehouse: str, sku_info: Dict) -> tuple[float, Optional[Dict]]:
      """Returns tuple of (base_demand, metadata)"""

      # NEW SKU DETECTION (Lines 425-438)
      print(f"[DEBUG V7.3] Checking total months for SKU: {sku_id}")  # Line 431
      data_check_query = """
          SELECT COUNT(*) as total_months
          FROM monthly_sales
          WHERE sku_id = %s
      """
      data_check_result = execute_query(data_check_query, (sku_id,), fetch_all=True)
      total_months_available = data_check_result[0]['total_months'] if data_check_result else 0

      print(f"[DEBUG V7.3] SKU {sku_id} has {total_months_available} months of data")  # Line 439

      # If new SKU (< 12 months of data), use limited data methodology
      if total_months_available < 12:
          # Returns tuple: (base_demand, metadata)
          return self._handle_limited_data_sku(sku_id, warehouse, sku_info, total_months_available)

      # ESTABLISHED SKU PATH (Lines 442-501)
      # ... existing classification-based logic ...
      # Returns: (base_demand, None)

  Status: ✅ Working correctly - Debug logs confirm detection of 9 months for UB-YTX7A-BS

  ---
  Core Logic: _handle_limited_data_sku() - Lines 686-939

  This function implements the expert "Test & Learn" pattern with 7 steps:

  STEP 0: Launch Pattern Detection (Lines 730-828)

  # Initialize metadata
  metadata = {
      'method_used': 'limited_data_multi_technique',
      'growth_rate_source': 'new_sku_methodology',
      'confidence': 0.45,
      'launch_pattern_detected': False
  }

  # Query monthly sales with availability calculation
  if warehouse == 'combined':
      pattern_query = """
          SELECT
              `year_month`,
              (corrected_demand_burnaby + corrected_demand_kentucky) as total_demand,
              CASE
                  WHEN (burnaby_sales + kentucky_sales) > 0 THEN 1.0
                  WHEN (burnaby_stockout_days + kentucky_stockout_days) >= 15 THEN 0.0
                  ELSE 0.5
              END as availability_rate
          FROM monthly_sales
          WHERE sku_id = %s
            AND (corrected_demand_burnaby > 0 OR corrected_demand_kentucky > 0
                 OR burnaby_stockout_days > 0 OR kentucky_stockout_days > 0)
          ORDER BY `year_month` ASC
      """

  pattern_data = execute_query(pattern_query, (sku_id,), fetch_all=True)

  # Filter out stockout months (< 30% availability)
  clean_months = [
      float(row['total_demand'])
      for row in pattern_data
      if row['availability_rate'] >= 0.3 and float(row['total_demand']) > 0
  ]

  # Detect launch spike (first month 30% higher than average)
  if len(clean_months) >= 2:
      first_month = clean_months[0]
      avg_rest = statistics.mean(clean_months[1:])
      if first_month > avg_rest * 1.3:
          launch_spike_detected = True

  # Detect stockout in first 3 months
  for i, row in enumerate(pattern_data[:3]):
      if row['availability_rate'] < 0.3:
          had_early_stockout = True
          break

  # Calculate baseline with launch pattern logic
  if had_early_stockout or launch_spike_detected:
      metadata['launch_pattern_detected'] = True
      metadata['method_used'] = 'limited_data_test_launch'
      metadata['confidence'] = 0.55

      if len(clean_months_demand) <= 3:
          # Still in launch phase - adjust for inflated early demand
          launch_multiplier = 1.5 if launch_spike_detected else 1.2
          baseline_from_pattern = max(clean_months_demand) / launch_multiplier
      else:
          # Post-launch stabilization - weighted average (70% recent, 30% older)
          if len(clean_months_demand) >= 6:
              recent = clean_months_demand[-3:]
              older = clean_months_demand[:-3]
              baseline_from_pattern = (statistics.mean(recent) * 0.7) + (statistics.mean(older) * 0.3)
          else:
              baseline_from_pattern = statistics.mean(clean_months_demand)

      # Apply stockout boost (stockout = positive signal of demand)
      if had_early_stockout:
          baseline_from_pattern *= 1.2
          metadata['growth_rate_source'] = 'proven_demand_stockout'
  else:
      baseline_from_pattern = None

  For UB-YTX7A-BS:
  - Raw data: [0, 0, 24, 133, 100, 1, 38, 14, 31]
  - Clean months (>30% availability): [24, 133, 100, 38, 14, 31] (6 months)
  - Launch spike detected: 133 > mean([24,100,38,14,31]) * 1.3 = 133 > 53.9 ✅
  - Early stockout detected: June shows 1 unit (availability < 30%) ✅
  - Calculation:
    - Recent 3 months: [38, 14, 31] avg = 27.67
    - Older 3 months: [24, 133, 100] avg = 85.67
    - Weighted: (27.67 * 0.7) + (85.67 * 0.3) = 45.07
    - Stockout boost: 45.07 * 1.2 = 54.08 units
  - Expected baseline_from_pattern: ~54 units

  Status: ✅ Pattern detection logic is correct

  ---
  STEP 1: Get Actual Demand from View (Lines 830-847)

  # Try to use v_sku_demand_analysis view
  query = """
      SELECT
          demand_3mo_weighted,
          demand_6mo_weighted,
          coefficient_variation,
          volatility_class
      FROM v_sku_demand_analysis
      WHERE sku_id = %s
  """

  view_data = execute_query(query, (sku_id,), fetch_all=True)

  if view_data and view_data[0]['demand_3mo_weighted']:
      base_from_actual = float(view_data[0]['demand_3mo_weighted'])
  else:
      base_from_actual = self._calculate_simple_average(sku_id, warehouse, available_months)

  For UB-YTX7A-BS:
  - demand_3mo_weighted likely uses recent 3 months: [38, 14, 31]
  - Weighted calculation: (31 * 0.5) + (14 * 0.3) + (38 * 0.2) ≈ 27 units
  - base_from_actual: ~27 units

  ---
  STEP 2: Find Similar SKUs (Lines 849-872)

  similar_skus = self._find_similar_skus(sku_id, sku_info, warehouse)

  if similar_skus:
      similar_demands = []
      for similar_sku_id in similar_skus[:5]:
          similar_query = "SELECT demand_6mo_weighted FROM v_sku_demand_analysis WHERE sku_id = %s"
          similar_result = execute_query(similar_query, (similar_sku_id,), fetch_all=True)

          if similar_result and similar_result[0]['demand_6mo_weighted']:
              similar_demands.append(float(similar_result[0]['demand_6mo_weighted']))

      if similar_demands:
          base_from_similar = statistics.mean(similar_demands)
          seasonal_boost = self._get_average_seasonal_factor(similar_skus, warehouse)
      else:
          base_from_similar = 0.0
          seasonal_boost = 1.0
  else:
      base_from_similar = 0.0
      seasonal_boost = 1.0

  For UB-YTX7A-BS (motorcycle battery):
  - Similar SKUs: Other YTX batteries with 6-month averages of ~30-50 units
  - base_from_similar: ~40 units (estimated)
  - seasonal_boost: ~1.0 (batteries not highly seasonal)

  ---
  ⚠️ STEP 3: THE PROBLEM - Override Logic (Lines 874-896)

  # STEP 3: Combine actual and similar data with intelligent weighting
  # Prioritize baseline_from_pattern if Test & Learn pattern was detected
  if baseline_from_pattern is not None:
      # Use pattern-based calculation as primary baseline
      base_demand = baseline_from_pattern

      # 🔴 THE ISSUE: This blending overrides the pattern calculation
      if base_from_similar > 0:
          # Light blending: 80% pattern-based, 20% similar SKUs
          base_demand = (baseline_from_pattern * 0.8) + (base_from_similar * 0.2)

  elif base_from_actual > 0 and base_from_similar > 0:
      weight_actual = min(0.5 + (available_months * 0.1), 0.8)
      weight_similar = 1.0 - weight_actual
      base_demand = (base_from_actual * weight_actual) + (base_from_similar * weight_similar)

  elif base_from_actual > 0:
      base_demand = base_from_actual

  elif base_from_similar > 0:
      base_demand = base_from_similar

  else:
      base_demand = self._get_category_average(sku_info.get('category', 'unknown'), warehouse)

  For UB-YTX7A-BS:
  - baseline_from_pattern = 54.08 units ✅
  - base_from_similar = 40 units (estimated)
  - Blended calculation: (54.08 * 0.8) + (40 * 0.2) = 51.26 units
  - This is still reasonable, but then gets further diluted...

  ---
  ⚠️ STEP 4-6: Further Dilution (Lines 898-938)

  # STEP 4: Apply seasonal boost
  base_demand *= seasonal_boost  # 51.26 * 1.0 = 51.26

  # STEP 5: Apply growth multiplier
  growth_multiplier = 1.0  # (UB-YTX7A-BS has no growth_status flag)
  base_demand *= growth_multiplier  # 51.26 * 1.0 = 51.26

  # STEP 6: Check pending inventory and apply safety multiplier
  pending_qty = self._get_pending_quantity(sku_id, warehouse)

  # 🔴 THE BIGGER ISSUE: Safety multiplier logic
  if pending_qty > 0:
      pending_coverage = pending_qty / base_demand
      if pending_coverage >= 3.0:
          safety_multiplier = 0.9
      elif pending_coverage >= 1.5:
          safety_multiplier = 1.0
      else:
          safety_multiplier = 1.5 if available_months < 3 else 1.3
  else:
      # 🔴 THIS PATH IS TAKEN - should increase but might be decreasing
      safety_multiplier = 1.5 if available_months < 3 else 1.3

  adjusted_base_demand = base_demand * safety_multiplier

  # STEP 7: Stockout risk adjustment
  if similar_skus and self._check_stockout_patterns(similar_skus) > 0.5:
      adjusted_base_demand *= 1.1

  return adjusted_base_demand, metadata

  For UB-YTX7A-BS (9 months, so safety_multiplier = 1.3):
  - After STEP 5: 51.26 units
  - After STEP 6: 51.26 * 1.3 = 66.64 units
  - After STEP 7: 66.64 * 1.1 = 73.30 units (if stockout risk detected)

  But database shows: base_demand_used = 19.63 ❌

  ---
  The Mystery: Where Did 73.30 Become 19.63?

  Hypothesis 1: base_from_actual Override

  The view query might be returning a much lower value than expected:
  - If demand_3mo_weighted is calculating wrong (using months with zeros?)
  - If the view has stale data from before stockout correction
  - Need to verify: What is v_sku_demand_analysis.demand_3mo_weighted for UB-YTX7A-BS?

  Hypothesis 2: base_from_similar is Zero

  If _find_similar_skus() returns empty list:
  - Falls through to base_from_actual only at line 890-891
  - Calculation: base_demand = base_from_actual = 27 units
  - After safety multiplier: 27 * 1.3 = 35.1 (still not 19.63)

  Hypothesis 3: The Blending Math is Wrong

  Current logic at line 883:
  base_demand = (baseline_from_pattern * 0.8) + (base_from_similar * 0.2)

  If somehow inverted or calculated differently:
  - baseline_from_pattern = 54.08
  - base_from_similar = 0 (no similar SKUs found)
  - Falls to line 890: base_demand = base_from_actual = 27
  - But 27 still doesn't match 19.63

  Hypothesis 4: _calculate_simple_average() Issue

  If the view returns NULL, falls back to _calculate_simple_average() at line 847:

  def _calculate_simple_average(self, sku_id: str, warehouse: str, months: int) -> float:
      # This might be using the WRONG query that doesn't filter stockouts
      # or is using classification-based months (3 months for BZ classification)

  If this function uses last 3 months with classification logic (BZ = 3 months):
  - Months: [38, 14, 31] but with some zero months mixed in?
  - Or using corrected_demand incorrectly?
  - Average: (38 + 14 + 31) / 3 = 27.67
  - After some factor: 27.67 * 0.71 ≈ 19.63 ✅

  Most Likely: The _calculate_simple_average() is being called and returning 19.63, which means either:
  1. The view doesn't have data for UB-YTX7A-BS (new SKU not in view yet)
  2. The fallback calculation is using wrong logic

  ---
  Database Evidence

  Forecast Run 31 (Combined Test 10) Results:

  forecast_run_id: 31
  sku_id: UB-YTX7A-BS
  warehouse: combined
  base_demand_used: 19.63
  method_used: limited_data_multi_technique
  growth_rate_applied: -0.50
  growth_rate_source: (empty string)
  month_1_qty: 20
  month_2_qty: 19
  month_3_qty: 17

  Key Observations:
  1. ✅ method_used = limited_data_multi_technique (proves new code is running)
  2. ❌ base_demand_used = 19.63 (should be ~70-110)
  3. ❌ growth_rate_source = empty (should be "new_sku_methodology" or "proven_demand_stockout")
  4. ❌ Growth rate = -50% (declining trend, should be flat or positive)

  This suggests:
  - _handle_limited_data_sku() IS being called (method changed)
  - But the metadata is NOT being properly used in generate_forecast()
  - The baseline_from_pattern calculation is being overridden
  - The growth_rate_source from metadata is not being applied

  ---
  Proposed Solutions

  Solution 1: Prioritize Pattern Baseline (Conservative)

  Change lines 876-883 in _handle_limited_data_sku():

  # STEP 3: Combine actual and similar data with intelligent weighting
  if baseline_from_pattern is not None:
      # Use pattern-based calculation WITHOUT blending
      # Pattern already includes stockout boost and launch adjustments
      base_demand = baseline_from_pattern
      # DO NOT BLEND - pattern is more accurate than view for new launches

  elif base_from_actual > 0 and base_from_similar > 0:
      # ... existing logic for non-pattern SKUs ...

  And update lines 920-928 to reduce safety multiplier:

  # Only apply large safety multiplier if NOT using pattern-based forecast
  if baseline_from_pattern is None:
      safety_multiplier = 1.5 if available_months < 3 else 1.3
  else:
      # Pattern already has 1.2x stockout boost, so minimal additional safety
      safety_multiplier = 1.1

  Expected Result:
  - base_demand = 54.08 (from pattern)
  - safety_multiplier = 1.1
  - adjusted_base_demand = 59.49 units
  - With stockout risk: 65.44 units

  ---
  Solution 2: Debug First (Recommended)

  Before making changes, add debug logging to understand what's actually happening:

  # After line 847 in _handle_limited_data_sku()
  print(f"[DEBUG] base_from_actual: {base_from_actual}")
  print(f"[DEBUG] base_from_similar: {base_from_similar}")
  print(f"[DEBUG] baseline_from_pattern: {baseline_from_pattern}")

  # After line 896
  print(f"[DEBUG] base_demand after STEP 3: {base_demand}")

  # After line 899
  print(f"[DEBUG] base_demand after seasonal_boost: {base_demand}")

  # After line 930
  print(f"[DEBUG] adjusted_base_demand: {adjusted_base_demand}")

  # Before line 939
  print(f"[DEBUG] returning: adjusted={adjusted_base_demand}, metadata={metadata}")

  Then run a new forecast and check logs to see exact values.

  ---
  Solution 3: Verify View Data

  Query the view directly to see what base_from_actual is pulling:

  SELECT
      sku_id,
      demand_3mo_weighted,
      demand_6mo_weighted,
      coefficient_variation,
      volatility_class
  FROM v_sku_demand_analysis
  WHERE sku_id = 'UB-YTX7A-BS';

  If this returns NULL or wrong values, the issue is in the view definition, not the forecasting logic.

  ---
  Solution 4: Fix Growth Rate Source

  The growth_rate_source is empty in the database, which means the metadata is not being properly used in generate_forecast().

  Check lines 355-411 in generate_forecast():

  # Get base demand (already stockout-corrected from sku_demand_stats)
  base_demand, demand_metadata = self._get_base_demand(sku_id, warehouse, sku_info)

  # Override growth_rate_source if demand_metadata provided
  if demand_metadata and 'growth_rate_source' in demand_metadata:
      growth_source = demand_metadata['growth_rate_source']

  Verify:
  1. Is demand_metadata being unpacked correctly?
  2. Is growth_source being saved to database correctly?
  3. Is there a bug in the INSERT query at line 662-677?

  ---
  Questions for ChatGPT Analysis

  1. Root Cause: Why is base_demand_used = 19.63 when the expert pattern should calculate ~54-110 units?
  2. Blending Logic: Is the 80/20 blend between baseline_from_pattern and base_from_similar correct, or should we skip blending entirely for pattern-based forecasts?        
  3. Safety Multipliers: The pattern already has 1.2x stockout boost and 1.2-1.5x launch multiplier. Should we skip the additional 1.3x safety multiplier to avoid
  double-counting?
  4. Metadata Flow: Why is growth_rate_source empty in the database when it's set in the metadata dict?
  5. View vs Pattern: Should base_from_actual from the view (which uses recent 3-month weighted average) ever override the expert pattern calculation that specifically      
  filters stockout months?
  6. Similar SKU Weighting: For a SKU with clear launch pattern, is blending with similar SKUs helpful or harmful? The expert guidance says "Don't try to reinvent the       
  wheel" but also emphasizes using the actual pattern when it's clear.
  7. Architecture: Should _handle_limited_data_sku() return the FINAL base_demand (after all adjustments), or just the baseline with metadata, letting
  generate_forecast() apply safety multipliers?

  ---
  Expert Guidance from docs/claudesuggestion.md

  Key quotes that inform this implementation:

  "Your stockout actually gave you valuable information - demand exists! Don't let the system interpret it as decline."

  "If you wait for the next order... it's going to be too late"

  "Most companies launch, forget about it, then react too late"

  "The knowledge base emphasizes: Don't try to reinvent the wheel... consolidate this knowledge... what was working and not working this launch"

  "Since stockout proved demand: recommended_forecast = baseline * 1.1 // Lean optimistic"

  "Result: ~85-90 units/month, not declining!"

  The expert guidance says we should be getting 85-90 units/month, but we're getting 19.63 units. This is a critical failure of the implementation.

  ---
  System Context

  - Language: Python 3.x
  - Framework: FastAPI with uvicorn auto-reload
  - Database: MySQL/MariaDB via XAMPP
  - Connection: Connection pooling via backend/database_pool.py
  - Key Files:
    - backend/forecasting.py (1200+ lines, core engine)
    - backend/forecast_jobs.py (background job processing)
    - backend/forecasting_api.py (REST API endpoints)
  - Test SKUs:
    - UB-YTX7A-BS: New SKU (9 months, BZ classification)
    - UB-YTX14-BS: Established SKU (69 months, AY classification) - working correctly

  ---
  Success Criteria

  A successful fix will produce:

  For UB-YTX7A-BS:
  - base_demand_used: 85-110 units (not 19.63)
  - method_used: limited_data_test_launch (not just limited_data_multi_technique)
  - growth_rate_source: proven_demand_stockout (not empty)
  - month_1_qty: 85-110 (not 20)
  - month_2_qty: 85-110 (not 19)
  - month_3_qty: 85-110 (not 17)

  For UB-YTX14-BS (regression test):
  - Should still show 1,500-2,800 range (established SKU logic unchanged)