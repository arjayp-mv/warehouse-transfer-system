  ⎿  V7.3: Enhanced Forecasting (Expert-Validated Plan)

     Overview

     Three major improvements with expert recommendations incorporated:
     1. Forecast Queue Management
     2. SKU-Specific Auto Growth Rate with Category Fallback
     3. New SKU Multi-Technique Forecasting with Database Integration

     Expert Validation: Based on forecasting best practices review by Claude specialist
     Database Features: Leveraging existing growth_status, seasonal_factors, stockout_patterns, v_sku_demand_analysis

     ---
     ISSUE #1: Forecast Queue Management

     Implementation (Same as before - approved by expert)

     Backend (backend/forecast_jobs.py):
     - Add Python queue.Queue() for pending forecasts
     - Process sequentially (FIFO)
     - Track queue position in database

     Frontend (frontend/forecasting.js, forecasting.html):
     - Modal dialog: "Queue or Cancel?" when forecast already running
     - Queue status badges showing position
     - Delete/Cancel buttons for each run

     Database:
     ALTER TABLE forecast_runs
     ADD COLUMN queue_position INT DEFAULT NULL;

     -- Update status ENUM to include 'queued'
     ALTER TABLE forecast_runs
     MODIFY status ENUM('pending', 'queued', 'running', 'completed', 'failed', 'cancelled');

     ---
     ISSUE #2: Auto Growth Rate (EXPERT IMPROVEMENTS INCORPORATED)

     Changes Based on Expert Feedback

     Key Improvements:
     1. ✅ 6 months minimum (not 3) for trend reliability
     2. ✅ Weighted regression (recent months more important)
     3. ✅ Category-level fallback when insufficient SKU data
     4. ✅ ±50% cap confirmed appropriate

     Implementation Details

     New Function: calculate_sku_growth_rate() with Weighted Regression

     def calculate_sku_growth_rate(self, sku_id: str, warehouse: str, sku_info: Dict) -> Tuple[float, str]:
         """
         Calculate annualized growth rate using weighted linear regression.
         
         Expert recommendation: Use 6-12 months of data with exponential weighting
         favoring recent months for better trend detection.
         
         Returns:
             Tuple[float, str]: (growth_rate, source)
             source: 'sku_trend', 'category_trend', 'default'
         """
         # STEP 1: Try SKU-specific trend (need 6+ months)
         query = """
             SELECT `year_month`, {demand_column} as demand
             FROM monthly_sales
             WHERE sku_id = %s AND {demand_column} > 0
             ORDER BY `year_month` DESC
             LIMIT 12
         """

         results = execute_query(query, (sku_id,))

         if len(results) >= 6:
             # EXPERT RECOMMENDATION: Weighted regression with exponential decay
             results.reverse()  # Chronological order
             n = len(results)
             months = list(range(n))
             sales = [float(row['demand']) for row in results]

             # Exponential weights: more recent = higher weight
             # weights[0] = 0.5^(n-0), weights[n-1] = 0.5^0 = 1.0
             weights = [0.5 ** (n - i - 1) for i in range(n)]
             weight_sum = sum(weights)

             # Normalize weights to sum to 1
             weights = [w / weight_sum for w in weights]

             # Weighted linear regression
             weighted_x_mean = sum(x * w for x, w in zip(months, weights))
             weighted_y_mean = sum(y * w for y, w in zip(sales, weights))

             numerator = sum(w * (x - weighted_x_mean) * (y - weighted_y_mean)
                            for x, y, w in zip(months, sales, weights))
             denominator = sum(w * (x - weighted_x_mean) ** 2
                              for x, w in zip(months, weights))

             slope = numerator / denominator if denominator != 0 else 0

             # Convert to annualized rate
             avg_sales = weighted_y_mean
             if avg_sales > 0:
                 monthly_rate = slope / avg_sales
                 annualized_rate = monthly_rate * 12

                 # Cap at ±50% (expert confirmed appropriate)
                 annualized_rate = max(-0.50, min(0.50, annualized_rate))

                 return annualized_rate, 'sku_trend'

         # STEP 2: EXPERT RECOMMENDATION - Category fallback when insufficient SKU data
         return self._get_category_growth_rate(sku_info['category'], warehouse)


     def _get_category_growth_rate(self, category: str, warehouse: str) -> Tuple[float, str]:
         """
         Calculate category-wide growth rate when SKU has insufficient data.
         
         Expert recommendation: Use category trend for stability when SKU data < 6 months.
         """
         query = """
             SELECT AVG(demand_change) as avg_growth
             FROM (
                 SELECT 
                     s.category,
                     (ms_recent.total_demand - ms_old.total_demand) / ms_old.total_demand as demand_change
                 FROM skus s
                 INNER JOIN (
                     SELECT sku_id, AVG({demand_column}) as total_demand
                     FROM monthly_sales
                     WHERE `year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 6 MONTH), '%Y-%m')
                       AND {demand_column} > 0
                     GROUP BY sku_id
                 ) ms_recent ON s.sku_id = ms_recent.sku_id
                 INNER JOIN (
                     SELECT sku_id, AVG({demand_column}) as total_demand
                     FROM monthly_sales
                     WHERE `year_month` < DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 6 MONTH), '%Y-%m')
                       AND `year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 12 MONTH), '%Y-%m')
                       AND {demand_column} > 0
                     GROUP BY sku_id
                 ) ms_old ON s.sku_id = ms_old.sku_id
                 WHERE s.category = %s
                   AND ms_old.total_demand > 0
             ) category_trends
         """

         result = execute_query(query, (category,))

         if result and result[0]['avg_growth'] is not None:
             growth_rate = float(result[0]['avg_growth'])
             growth_rate = max(-0.50, min(0.50, growth_rate))
             return growth_rate, 'category_trend'

         return 0.0, 'default'

     Database Changes:
     ALTER TABLE forecast_details
     ADD COLUMN growth_rate_source ENUM('manual_override', 'sku_trend', 'category_trend', 'default')
         DEFAULT 'default' AFTER growth_rate_applied;

     Frontend Changes:
     - Form label: "Manual Growth Rate Override (Optional)"
     - Help text: "Leave blank for automatic SKU-specific calculation"
     - Results table: Show "Calculated Growth Rate" column with source badge

     ---
     ISSUE #3: New SKU Forecasting (EXPERT IMPROVEMENTS - MAJOR CHANGES)

     Expert-Recommended Improvements

     Critical Additions:
     1. ✅ Integrate seasonal_factors table (already exists!)
     2. ✅ Use growth_status field from skus table
     3. ✅ Check pending_inventory to avoid over-ordering
     4. ✅ Leverage v_sku_demand_analysis view for pre-calculated metrics

     Implementation with Database Integration

     Enhanced _handle_limited_data_sku() Function:

     def _handle_limited_data_sku(
         self,
         sku_id: str,
         warehouse: str,
         sku_info: Dict,
         available_months: int
     ) -> Tuple[float, Dict]:
         """
         Multi-technique forecasting for SKUs with < 6 months data.
         
         Incorporates expert recommendations:
         - Seasonal factors from seasonal_factors table
         - Growth status from skus.growth_status field
         - Pending inventory check to avoid over-ordering
         - Pre-calculated demand metrics from v_sku_demand_analysis view
         """
         metadata = {
             'data_quality': 'new_sku' if available_months < 3 else 'limited',
             'available_months': available_months,
             'similar_skus_used': [],
             'safety_multiplier': 1.0,
             'techniques_applied': []
         }

         # STEP 1: Use v_sku_demand_analysis view (EXPERT RECOMMENDATION)
         query = """
             SELECT 
                 demand_3mo_weighted,
                 demand_6mo_weighted,
                 coefficient_variation,
                 volatility_class,
                 sample_size_months,
                 data_quality_score
             FROM v_sku_demand_analysis
             WHERE sku_id = %s
         """

         view_data = execute_query(query, (sku_id,), fetch_all=True)

         if view_data and view_data[0]['demand_3mo_weighted']:
             base_from_actual = float(view_data[0]['demand_3mo_weighted'])
             metadata['techniques_applied'].append('v_sku_demand_analysis')
             metadata['data_quality_score'] = view_data[0]['data_quality_score']
         else:
             # Fallback to manual calculation
             base_from_actual = self._calculate_simple_average(sku_id, warehouse, available_months)
             metadata['techniques_applied'].append('simple_average')

         # STEP 2: Find similar SKUs and get their average
         similar_skus = self._find_similar_skus(sku_id, sku_info, warehouse)

         if similar_skus:
             similar_demands = []
             for similar_sku_id in similar_skus[:5]:
                 # Use v_sku_demand_analysis for similar SKUs too
                 similar_query = "SELECT demand_6mo_weighted FROM v_sku_demand_analysis WHERE sku_id = %s"
                 similar_result = execute_query(similar_query, (similar_sku_id,), fetch_all=True)

                 if similar_result and similar_result[0]['demand_6mo_weighted']:
                     similar_demands.append(float(similar_result[0]['demand_6mo_weighted']))
                     metadata['similar_skus_used'].append(similar_sku_id)

             if similar_demands:
                 base_from_similar = statistics.mean(similar_demands)
                 metadata['techniques_applied'].append('similar_sku_average')

                 # EXPERT RECOMMENDATION: Apply seasonal factors from similar SKUs
                 seasonal_boost = self._get_average_seasonal_factor(similar_skus, warehouse)
                 metadata['seasonal_boost_from_similar'] = seasonal_boost
             else:
                 base_from_similar = 0.0
                 seasonal_boost = 1.0
         else:
             base_from_similar = 0.0
             seasonal_boost = 1.0

         # STEP 3: Combine actual and similar data with weighting
         if base_from_actual > 0 and base_from_similar > 0:
             weight_actual = min(0.5 + (available_months * 0.1), 0.8)
             weight_similar = 1.0 - weight_actual

             base_demand = (base_from_actual * weight_actual) + (base_from_similar * weight_similar)
             metadata['techniques_applied'].append('weighted_combination')
         elif base_from_actual > 0:
             base_demand = base_from_actual
         elif base_from_similar > 0:
             base_demand = base_from_similar
         else:
             base_demand = self._get_category_average(sku_info['category'], warehouse)
             metadata['techniques_applied'].append('category_average')

         # STEP 4: Apply seasonal boost (if from similar SKUs)
         base_demand *= seasonal_boost

         # STEP 5: EXPERT RECOMMENDATION - Integrate growth_status from skus table
         growth_multiplier = 1.0
         if sku_info['growth_status'] == 'viral':
             growth_multiplier = 1.2  # 20% boost for viral products
             metadata['growth_status_boost'] = 'viral_20%'
         elif sku_info['growth_status'] == 'declining':
             growth_multiplier = 0.8  # 20% reduction for declining
             metadata['growth_status_boost'] = 'declining_-20%'

         base_demand *= growth_multiplier

         # STEP 6: Check pending inventory (EXPERT RECOMMENDATION)
         pending_qty = self._get_pending_quantity(sku_id, warehouse)

         if pending_qty > 0:
             # Reduce safety multiplier if orders already in pipeline
             pending_coverage = pending_qty / base_demand if base_demand > 0 else 0

             if pending_coverage >= 3.0:  # 3+ months coverage pending
                 safety_multiplier = 0.9  # Reduce buffer significantly
             elif pending_coverage >= 1.5:  # 1.5+ months pending
                 safety_multiplier = 1.0  # No additional buffer
             else:
                 # Normal safety multipliers
                 safety_multiplier = 1.5 if available_months < 3 else 1.3

             metadata['pending_inventory_qty'] = pending_qty
             metadata['pending_coverage_months'] = round(pending_coverage, 2)
         else:
             # No pending inventory - use standard safety multipliers
             safety_multiplier = 1.5 if available_months < 3 else 1.3

         metadata['safety_multiplier'] = safety_multiplier
         adjusted_base_demand = base_demand * safety_multiplier

         # STEP 7: Check similar SKU stockout patterns (EXPERT RECOMMENDATION)
         if similar_skus:
             stockout_risk = self._check_stockout_patterns(similar_skus)
             if stockout_risk > 0.5:  # High stockout risk
                 adjusted_base_demand *= 1.1  # Additional 10% buffer
                 metadata['stockout_risk_adjustment'] = '10%_increase'

         return adjusted_base_demand, metadata


     def _get_average_seasonal_factor(self, similar_sku_ids: List[str], warehouse: str) -> float:
         """
         EXPERT RECOMMENDATION: Get average seasonal factor from similar SKUs.
         
         Uses existing seasonal_factors table to apply seasonality to new SKUs.
         """
         current_month = datetime.now().month

         query = """
             SELECT AVG(seasonal_factor) as avg_factor
             FROM seasonal_factors
             WHERE sku_id IN (%s)
               AND warehouse = %s
               AND month_number = %s
               AND confidence_level >= 0.5
         """ % (','.join(['%s'] * len(similar_sku_ids)), '%s', '%s')

         params = similar_sku_ids + [warehouse, current_month]
         result = execute_query(query, params, fetch_all=True)

         if result and result[0]['avg_factor']:
             return float(result[0]['avg_factor'])

         return 1.0  # No seasonal adjustment


     def _get_pending_quantity(self, sku_id: str, warehouse: str) -> int:
         """
         EXPERT RECOMMENDATION: Check pending inventory to avoid over-ordering.
         """
         query = """
             SELECT SUM(quantity) as total_pending
             FROM pending_inventory
             WHERE sku_id = %s
               AND destination = %s
               AND status IN ('ordered', 'shipped', 'pending')
               AND expected_arrival >= CURDATE()
         """

         result = execute_query(query, (sku_id, warehouse), fetch_all=True)

         if result and result[0]['total_pending']:
             return int(result[0]['total_pending'])

         return 0


     def _check_stockout_patterns(self, similar_sku_ids: List[str]) -> float:
         """
         EXPERT RECOMMENDATION: Check if similar SKUs have chronic stockout patterns.
         
         Returns risk score 0.0-1.0 based on stockout frequency.
         """
         query = """
             SELECT AVG(frequency_score) as avg_frequency
             FROM stockout_patterns
             WHERE sku_id IN (%s)
               AND pattern_type IN ('chronic', 'seasonal')
         """ % ','.join(['%s'] * len(similar_sku_ids))

         result = execute_query(query, similar_sku_ids, fetch_all=True)

         if result and result[0]['avg_frequency']:
             return float(result[0]['avg_frequency']) / 100.0  # Convert 0-100 to 0-1

         return 0.0

     Database Schema Changes:
     ALTER TABLE forecast_details
     ADD COLUMN data_quality ENUM('sufficient', 'limited', 'new_sku') DEFAULT 'sufficient',
     ADD COLUMN similar_skus_used JSON DEFAULT NULL,
     ADD COLUMN safety_multiplier DECIMAL(3,2) DEFAULT 1.00,
     ADD COLUMN techniques_applied VARCHAR(500) DEFAULT NULL,
     ADD COLUMN growth_status_applied ENUM('normal', 'viral', 'declining', 'unknown') DEFAULT NULL,
     ADD COLUMN pending_inventory_considered INT DEFAULT 0,
     ADD COLUMN seasonal_boost_applied DECIMAL(4,3) DEFAULT 1.000,
     ADD COLUMN stockout_risk_adjustment DECIMAL(4,3) DEFAULT 0.000;

     Frontend Changes:
     // Add data quality badge in results table
     function renderDataQuality(data, type, row) {
         const badges = {
             'sufficient': '<span class="badge bg-success">Sufficient Data</span>',
             'limited': '<span class="badge bg-warning">Limited Data</span>',
             'new_sku': '<span class="badge bg-info">New SKU</span>'
         };

         let tooltip = `Available: ${row.available_months || 'N/A'} months`;
         if (row.similar_skus_used && row.similar_skus_used.length > 0) {
             tooltip += `\nSimilar SKUs: ${row.similar_skus_used.join(', ')}`;
         }
         if (row.safety_multiplier > 1.0) {
             tooltip += `\nSafety: ${row.safety_multiplier}x`;
         }

         return `<span data-bs-toggle="tooltip" title="${tooltip}">${badges[data]}</span>`;
     }

     ---
     Implementation Phases (EXPERT RECOMMENDED)

     Phase 1: SKU-Specific Growth Rate (3-4 hours)

     Priority: HIGH

     Tasks:
     - Implement weighted regression in calculate_sku_growth_rate()
     - Add category fallback in _get_category_growth_rate()
     - Update ForecastEngine to use auto-calculated rates
     - Add growth_rate_source database column
     - Frontend: Show calculated rate with source badge
     - Test with UB-YTX14-BS (declining) and trending SKUs

     Phase 2: New SKU Methodology (5-6 hours)

     Priority: HIGH

     Tasks:
     - Implement _handle_limited_data_sku() with all expert recommendations
     - Integrate v_sku_demand_analysis view
     - Add similar SKU finder with seasonal factor averaging
     - Database schema updates (data_quality, similar_skus_used, etc.)
     - Test with UB-YTX7A-BS and other new SKUs

     Phase 3: Database Integration (3-4 hours)

     Priority: MEDIUM

     Tasks:
     - Integrate growth_status field logic (viral, declining, normal)
     - Add pending_inventory checking
     - Implement stockout_patterns risk assessment
     - Add seasonal_boost from similar SKUs
     - Test with various growth_status categories

     Phase 4: Queue Management (4-5 hours)

     Priority: MEDIUM

     Tasks:
     - Backend queue system with Python queue.Queue()
     - Database queue_position column
     - Frontend modal dialog and queue status
     - Delete/Cancel buttons
     - Test concurrent forecast requests

     Phase 5: Testing & Documentation (3-4 hours)

     Priority: HIGH

     Tasks:
     - End-to-end testing of all features
     - Validate against expert checklist
     - Update docs/V7.3_ENHANCEMENTS.md
     - Performance testing with 4000 SKUs
     - Create test report with before/after comparisons

     ---
     Total Time Estimate: 18-23 hours

     Success Criteria (Expert-Validated)

     1. ✅ Growth rates calculated per SKU using 6+ months weighted regression
     2. ✅ Category fallback when SKU has < 6 months data
     3. ✅ New SKUs forecast 30-50% higher with safety multipliers
     4. ✅ Seasonal factors from seasonal_factors table applied to new SKUs
     5. ✅ growth_status field integrated (viral, declining adjustments)
     6. ✅ Pending inventory checked to avoid over-ordering
     7. ✅ Stockout patterns from similar SKUs considered
     8. ✅ Queue management prevents concurrent forecast conflicts
     9. ✅ UB-YTX7A-BS forecast increases from 54 to 260-315 units/month
     10. ✅ All metadata tracked for transparency and debugging

     Risk Mitigation

     Performance:
     - v_sku_demand_analysis view already pre-calculates metrics (fast)
     - Limit similar SKU analysis to top 5 matches
     - Cache category growth rates during forecast run

     Data Quality:
     - Multiple fallback levels (SKU → similar SKU → category → default)
     - Confidence scores stored for validation
     - Manual override always available

     Over-Forecasting:
     - Pending inventory check prevents double-ordering
     - Safety multipliers capped at 1.5x maximum
     - Growth status limits extreme adjustments
