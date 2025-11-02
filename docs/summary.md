  ✅ CORRECTLY IMPLEMENTED Features

  From claudesuggestions3.md (Monthly Ordering):

  1. Fixed 30-day review period ✅
    - Line 46: REVIEW_PERIOD_DAYS = 30
  2. Enhanced safety stock for monthly ✅
    - Lines 230-302: calculate_safety_stock_monthly()
  3. Urgency levels ✅
    - Lines 382-393: must_order, should_order, optional, skip
  4. ABC-XYZ service levels ✅
    - Lines 33-43: Proper Z-scores (2.33 for A-X, etc.)
  5. Monthly ordering cycle logic ✅
    - Lines 305-435: determine_monthly_order_timing()

  From claudesuggestions2.md (Pending Order Timing):

  1. Time-phased pending orders ✅
    - Lines 49-114: Categorizes overdue/imminent/covered/future
  2. Confidence scoring ✅
    - Lines 117-227: calculate_effective_pending_inventory() with confidence
  3. Overdue pending tracking ✅
    - Database field: overdue_pending_count
  4. Stockout risk date ✅
    - Database field: stockout_risk_date

  From claudesuggestion.md (Core Calculations):

  1. Stockout-corrected demand ✅
    - Lines 347-359: Uses corrected_demand_burnaby/kentucky from monthly_sales
  2. Dynamic lead time ✅
    - Lines 369-375: Uses P95 from supplier_lead_times
  3. Coefficient of variation for safety stock ✅
    - Lines 260-263: Joins sku_demand_stats table

  ---
  ❌ CRITICAL GAPS - Should Be Implemented

  1. Forecast Integration (HIGH PRIORITY)

  Status: ❌ NOT IMPLEMENTEDSuggestion Source: claudesuggestion.md lines 271-283

  What's Missing:
  # Currently uses monthly_sales (historical)
  # SHOULD use forecast_details (forward-looking 12-month)

  # Current code (line 347-359):
  demand_query = """
      SELECT corrected_demand_burnaby/kentucky
      FROM monthly_sales  # ❌ Backward-looking
      WHERE sku_id = %s
      ORDER BY year_month DESC LIMIT 1
  """

  # Should be:
  forecast_query = """
      SELECT 
          fd.avg_monthly_qty,
          fla.adjusted_value as learning_adjusted_demand
      FROM forecast_details fd  # ✅ Forward-looking
      LEFT JOIN forecast_learning_adjustments fla 
          ON fd.sku_id = fla.sku_id AND fla.applied = TRUE
      WHERE fd.sku_id = %s AND fd.warehouse = %s
      AND fd.forecast_run_id = (SELECT MAX(id) FROM forecast_runs)
  """

  Tables Available:
  - ✅ forecast_details - 12-month projections
  - ✅ forecast_runs - Run tracking
  - ✅ forecast_learning_adjustments - Learning system

  Impact: Using historical sales instead of forecasts misses seasonal trends and growth patterns

  ---
  2. Forecast Learning Integration (HIGH PRIORITY)

  Status: ❌ NOT IMPLEMENTEDSuggestion Source: claudesuggestion.md lines 374-408

  What's Missing:
  def apply_forecast_learning_to_orders():
      """
      Use forecast accuracy insights to adjust orders.
      """
      # Get SKUs with consistent bias from forecast_accuracy table
      biased_skus = query("""
          SELECT 
              sku_id,
              AVG(percentage_error) as avg_bias,
              COUNT(*) as sample_size
          FROM forecast_accuracy
          WHERE is_actual_recorded = TRUE
          AND stockout_affected = FALSE
          GROUP BY sku_id
          HAVING sample_size >= 3
          AND ABS(avg_bias) > 10  # Consistent over/under forecasting
      """)

      # Apply adjustment factor to demand
      for sku in biased_skus:
          adjustment = 1 + (sku['avg_bias'] / 100)
          # Store in forecast_learning_adjustments table

  Tables Available:
  - ✅ forecast_accuracy - MAPE, bias tracking
  - ✅ forecast_learning_adjustments - Adjustment storage
  - ✅ v_forecast_accuracy_summary - Aggregated view

  Impact: System doesn't learn from past forecast errors

  ---
  3. Seasonal Adjustment Integration (MEDIUM PRIORITY)

  Status: ❌ NOT IMPLEMENTEDSuggestion Source: SUPPLIER_ORDERING_PLAN.md Appendix 7.1 + claudesuggestion.md lines 147-160

  What's Missing:
  def adjust_for_seasonality(sku_id, safety_stock, current_month):
      """Adjust safety stock if SKU has seasonal patterns."""
      seasonal_data = query("""
          SELECT 
              seasonal_strength,
              month_1_factor, month_2_factor, ..., month_12_factor
          FROM seasonal_patterns
          WHERE sku_id = %s
      """)

      if seasonal_data and seasonal_data['seasonal_strength'] > 0.3:
          current_factor = seasonal_data[f'month_{current_month}_factor']
          if current_factor > 1.2:  # Peak season
              safety_stock *= current_factor

      return safety_stock

  Tables Available:
  - ✅ seasonal_patterns - Monthly factors
  - ✅ seasonal_patterns_summary - Strength metrics
  - ✅ v_current_seasonal_factors - Active patterns

  Impact: No adjustment for Q4 peaks, January lulls, etc.

  ---
  4. Stockout Pattern Awareness (MEDIUM PRIORITY)

  Status: ❌ NOT IMPLEMENTEDSuggestion Source: SUPPLIER_ORDERING_PLAN.md Appendix 7.2

  What's Missing:
  # In UI: Show badge for SKUs with stockout_pattern_detected = 1
  # In calculations: Increase urgency for chronic stockout SKUs

  stockout_risk = query("""
      SELECT stockout_pattern_detected, pattern_type
      FROM stockout_patterns
      WHERE sku_id = %s
  """)

  if stockout_risk and stockout_risk['stockout_pattern_detected']:
      urgency_boost = 30  # Increase priority score

  Tables Available:
  - ✅ stockout_patterns - Pattern detection
  - ✅ v_current_stockouts_enhanced - Active stockouts
  - ✅ v_stockout_trends - Trend analysis

  Impact: Missing early warning for repeat stockout risks

  ---
  5. Coverage Timeline Visualization (MEDIUM PRIORITY)

  Status: ❌ NOT IMPLEMENTEDSuggestion Source: claudesuggestions2.md lines 256-290

  What's Missing:
  def build_coverage_timeline(current_stock, pending_orders, daily_demand):
      """Build day-by-day inventory projection including pending arrivals."""
      timeline = []
      inventory = current_stock

      for day in range(180):  # 6-month projection
          date = CURRENT_DATE + day

          # Check for arriving orders
          arriving_today = [o for o in pending_orders if o['expected_arrival'] == date]
          for order in arriving_today:
              inventory += order['quantity'] * order['confidence']

          inventory -= daily_demand
          timeline.append({
              'date': date,
              'inventory': max(0, inventory),
              'arrivals': arriving_today,
              'stockout': inventory < 0
          })

          if inventory < 0:
              break  # Found stockout date

      return timeline

  Impact: Can't visualize when inventory will run out - crucial for monthly ordering

  ---
  6. Supplier Performance Dashboard (LOW PRIORITY - UI)

  Status: ❌ NOT IMPLEMENTEDSuggestion Source: claudesuggestion.md lines 352-370

  What's Missing:
  CREATE VIEW supplier_performance_dashboard AS
  SELECT
      s.supplier_name,
      slt.destination,
      slt.reliability_score,
      slt.avg_lead_time,
      slt.p95_lead_time,
      COUNT(DISTINCT ss.po_number) as total_shipments,
      AVG(DATEDIFF(ss.actual_arrival, ss.expected_arrival)) as avg_delay_days
  FROM suppliers s
  JOIN supplier_lead_times slt ON s.supplier_name = slt.supplier
  LEFT JOIN supplier_shipments ss ON s.supplier_name = ss.supplier
  GROUP BY s.supplier_name, slt.destination;

  Impact: No visibility into supplier performance metrics

  ---
  7. Revenue Analysis in UI (LOW PRIORITY - UI)

  Status: ❌ NOT IMPLEMENTEDSuggestion Source: SUPPLIER_ORDERING_PLAN.md Appendix 7.4

  What's Missing:
  - Show total order value (CA + KY)
  - Display revenue impact per supplier
  - Prioritize high-revenue SKUs

  ---
  📋 PRIORITIZED IMPLEMENTATION PLAN

  Phase 1: Critical Fixes (Do First - 4-6 hours)

  1. ✅ Fix modal tab API endpoints
    - /api/pending-orders/sku/{sku_id}
    - /api/forecasts/sku/{sku_id}/latest
    - /api/stockouts/sku/{sku_id}
  2. ✅ Integrate forecast_details table
    - Replace monthly_sales with forecast_details for demand
    - Use learning-adjusted forecasts
  3. ✅ Add CSV export
    - Simple addition to existing Excel export

  Phase 2: Intelligence Layer (2-3 hours)

  4. ✅ Forecast learning integration
    - Query forecast_accuracy table
    - Apply bias adjustments to demand
  5. ✅ Seasonal adjustments
    - Check seasonal_patterns table
    - Adjust safety stock for peak/low seasons
  6. ✅ Stockout pattern awareness
    - Highlight chronic stockout SKUs
    - Boost urgency for pattern-detected items

  Phase 3: Visualization & UX (2-3 hours)

  7. ✅ Coverage timeline
    - Day-by-day inventory projection
    - Visual stockout date prediction
  8. ✅ Supplier Performance tab in modal
    - Show reliability metrics
    - Display delay statistics
  9. ✅ Revenue metrics
    - Total order value by warehouse
    - Revenue impact per supplier

  ---
  🎯 RECOMMENDATION

  Start with Phase 1 immediately. The missing API endpoints are causing errors, and the lack of forecast integration means        
  you're not using your sophisticated forecasting system at all.

  The current implementation is using backward-looking historical sales when you have forward-looking 12-month forecasts with     
  learning already built!

  Shall I start implementing Phase 1 now? This will:
  1. Fix the modal tab errors
  2. Switch to using forecast_details (the right data source)
  3. Add CSV export
  4. Take about 4-6 hours total