# Complete Forecast Learning & Accuracy System Recommendations

Based on your warehouse database structure and the proposed plan, here are the comprehensive improvements:

## Database Schema Enhancements

### 1. Separate Learning from Manual Adjustments

```sql
-- New table for system learning (separate from manual forecast_adjustments)
CREATE TABLE forecast_learning_adjustments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku_id VARCHAR(50) NOT NULL,
    adjustment_type ENUM('growth_rate', 'seasonal_factor', 'method_switch', 'volatility_adjustment') NOT NULL,
    original_value DECIMAL(10,4),
    adjusted_value DECIMAL(10,4),
    adjustment_magnitude DECIMAL(10,4),
    learning_reason TEXT,
    confidence_score DECIMAL(3,2),
    mape_before DECIMAL(5,2),
    mape_expected DECIMAL(5,2),
    applied BOOLEAN DEFAULT FALSE,
    applied_date TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
    INDEX idx_applied (applied, created_at),
    INDEX idx_sku_type (sku_id, adjustment_type)
);

-- Learning audit trail
CREATE TABLE forecast_learning_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku_id VARCHAR(50),
    learning_type VARCHAR(50),
    original_assumption TEXT,
    learned_insight TEXT,
    confidence_score DECIMAL(3,2),
    supporting_data_points INT,
    action_taken TEXT,
    expected_improvement DECIMAL(5,2),
    actual_improvement DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_sku_learning (sku_id, created_at)
);

-- Enhance forecast_accuracy table
ALTER TABLE forecast_accuracy 
ADD COLUMN stockout_affected BOOLEAN DEFAULT FALSE,
ADD COLUMN data_quality_score DECIMAL(3,2),
ADD COLUMN volatility_at_forecast DECIMAL(5,2),
ADD COLUMN seasonal_confidence_at_forecast DECIMAL(5,4),
ADD COLUMN learning_applied BOOLEAN DEFAULT FALSE,
ADD COLUMN learning_applied_date TIMESTAMP NULL,
ADD INDEX idx_learning_status (learning_applied, forecast_date);
```

## Enhanced Phase 1: Intelligent Forecast Recording

```python
# backend/forecast_accuracy.py

def record_forecast_for_accuracy_tracking(
    forecast_run_id: int,
    sku_id: str,
    warehouse: str,
    forecast_data: Dict
) -> bool:
    """
    Enhanced forecast recording with context capture.
    """
    try:
        # Get forecast run metadata
        run_result = execute_query(
            "SELECT forecast_date, created_at FROM forecast_runs WHERE id = %s",
            (forecast_run_id,), fetch_all=True
        )
        
        forecast_date = run_result[0]['forecast_date']
        
        # Get comprehensive SKU context at time of forecast
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
        
        for month_forecast in monthly_forecasts:
            forecast_period_date = datetime.strptime(month_forecast['date'], '%Y-%m')
            month_number = forecast_period_date.month
            
            context_result = execute_query(
                context_query,
                (warehouse, warehouse, month_number, warehouse, sku_id),
                fetch_all=True
            )
            
            context = context_result[0] if context_result else {}
            
            # Insert with full context
            insert_query = """
                INSERT INTO forecast_accuracy
                (sku_id, forecast_date, forecast_period_start, forecast_period_end,
                 predicted_demand, forecast_method, abc_class, xyz_class,
                 seasonal_pattern, volatility_at_forecast, data_quality_score,
                 seasonal_confidence_at_forecast, is_actual_recorded)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """
            
            forecast_period_start = forecast_period_date.date()
            forecast_period_end = (forecast_period_date + relativedelta(months=1) - relativedelta(days=1)).date()
            
            execute_query(
                insert_query,
                (sku_id, forecast_date, forecast_period_start, forecast_period_end,
                 month_forecast['quantity'], method_used,
                 context.get('abc_code'), context.get('xyz_code'),
                 context.get('seasonal_pattern'),
                 context.get('coefficient_variation'),
                 context.get('data_quality_score'),
                 context.get('seasonal_confidence')),
                fetch_all=False
            )
            
        logger.info(f"Recorded {len(monthly_forecasts)} periods with context for {sku_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error recording forecast for {sku_id}: {e}", exc_info=True)
        return False
```

## Enhanced Phase 2: Smart Monthly Accuracy Update

```python
def update_monthly_accuracy(target_month: Optional[str] = None) -> Dict:
    """
    Enhanced accuracy update that distinguishes true errors from supply issues.
    """
    if target_month is None:
        last_month = datetime.now() - relativedelta(months=1)
        target_month = last_month.strftime('%Y-%m')
    
    logger.info(f"Starting smart accuracy update for month: {target_month}")
    
    target_date = datetime.strptime(target_month, '%Y-%m')
    period_start = target_date.date()
    period_end = (target_date + relativedelta(months=1) - relativedelta(days=1)).date()
    
    # Find forecasts with stockout context
    find_forecasts_query = """
        SELECT
            fa.id, fa.sku_id, fa.predicted_demand,
            fa.abc_class, fa.xyz_class,
            fa.volatility_at_forecast,
            -- Check for stockouts in the period
            (SELECT COUNT(*) FROM stockout_dates sd
             WHERE sd.sku_id = fa.sku_id
             AND sd.stockout_date BETWEEN fa.forecast_period_start 
             AND fa.forecast_period_end
             AND sd.is_resolved = 0) as stockout_days
        FROM forecast_accuracy fa
        WHERE fa.forecast_period_start = %s
          AND fa.forecast_period_end = %s
          AND fa.is_actual_recorded = 0
    """
    
    forecasts = execute_query(
        find_forecasts_query,
        (period_start, period_end),
        fetch_all=True
    )
    
    # Get actuals with corrected demand
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
    actuals_dict = {row['sku_id']: row for row in actuals}
    
    for forecast in forecasts:
        sku_id = forecast['sku_id']
        predicted = float(forecast['predicted_demand'])
        stockout_affected = forecast['stockout_days'] > 0
        
        if sku_id in actuals_dict:
            actual_data = actuals_dict[sku_id]
            actual = actual_data['actual_demand']
            
            # Calculate errors with stockout awareness
            absolute_error = abs(actual - predicted)
            
            if actual > 0:
                percentage_error = ((actual - predicted) / actual) * 100
                absolute_percentage_error = abs(percentage_error)
            else:
                if predicted > 0:
                    percentage_error = -100.0
                    absolute_percentage_error = 100.0
                else:
                    percentage_error = 0.0
                    absolute_percentage_error = 0.0
            
            # If stockout affected and we under-sold, don't count as forecast error
            if stockout_affected and actual < predicted:
                # Mark as stockout-affected for learning algorithms
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
            else:
                # Normal accuracy update
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
            
            execute_query(
                update_query,
                (actual, absolute_error, percentage_error,
                 absolute_percentage_error, stockout_affected, forecast['id']),
                fetch_all=False
            )
    
    return {
        'month_updated': target_month,
        'total_forecasts': len(forecasts),
        'stockout_affected_count': sum(1 for f in forecasts if f['stockout_days'] > 0)
    }
```

## Enhanced Phase 3: Multi-Dimensional Learning

```python
# backend/forecast_learning.py

class ForecastLearningEngine:
    """
    Comprehensive learning system with multiple strategies.
    """
    
    def __init__(self):
        self.learning_rates = self._initialize_learning_rates()
    
    def _initialize_learning_rates(self):
        """ABC/XYZ specific learning rates"""
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
        """Learn growth rate adjustments by SKU characteristics"""
        
        # Analyze by growth status
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
                AND fa.stockout_affected = 0  -- Exclude supply-constrained periods
                AND fa.forecast_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
            GROUP BY s.sku_id, s.growth_status, fd.growth_rate_source
            HAVING sample_size >= 3 AND ABS(avg_bias) > 10
        """
        
        results = execute_query(growth_analysis_query, fetch_all=True)
        
        for row in results:
            sku_id = row['sku_id']
            classification = f"{row['abc_code']}{row['xyz_code']}"
            
            # Different strategies for different growth statuses
            if row['growth_status'] == 'viral':
                # Viral products need faster adaptation
                adjustment = self._calculate_viral_adjustment(row)
            elif row['growth_status'] == 'declining':
                # Declining products need conservative adjustments
                adjustment = self._calculate_declining_adjustment(row)
            else:
                # Normal products use standard learning
                learning_rate = self.learning_rates.get(classification, {}).get('growth', 0.05)
                adjustment = min(0.10, max(-0.10, row['avg_bias'] / 100 * learning_rate))
            
            self._log_learning_adjustment(
                sku_id=sku_id,
                adjustment_type='growth_rate',
                original_value=row['growth_rate_applied'],
                adjustment=adjustment,
                reason=f"Bias: {row['avg_bias']:.2f}%, Growth Status: {row['growth_status']}"
            )
    
    def learn_seasonal_improvements(self):
        """Compare forecast seasonal factors with actual patterns"""
        
        seasonal_learning_query = """
            SELECT
                fa.sku_id,
                MONTH(fa.forecast_period_start) as month_num,
                fa.seasonal_confidence_at_forecast,
                AVG(fa.percentage_error) as avg_error_by_month,
                COUNT(*) as samples,
                sf.seasonal_factor as current_factor,
                sps.pattern_strength
            FROM forecast_accuracy fa
            LEFT JOIN seasonal_factors sf ON fa.sku_id = sf.sku_id
                AND MONTH(fa.forecast_period_start) = sf.month_number
            LEFT JOIN seasonal_patterns_summary sps ON fa.sku_id = sps.sku_id
            WHERE fa.is_actual_recorded = 1
                AND fa.stockout_affected = 0
            GROUP BY fa.sku_id, MONTH(fa.forecast_period_start)
            HAVING samples >= 2  -- Need at least 2 years of same month
        """
        
        results = execute_query(seasonal_learning_query, fetch_all=True)
        
        for row in results:
            if row['seasonal_confidence_at_forecast'] < 0.5:
                # Low confidence seasonal - needs recalculation
                self._trigger_seasonal_recalculation(row['sku_id'])
            elif abs(row['avg_error_by_month']) > 20:
                # High error for specific month - adjust factor
                adjustment = 1 + (row['avg_error_by_month'] / 100)
                new_factor = row['current_factor'] * adjustment
                self._update_seasonal_factor(row['sku_id'], row['month_num'], new_factor)
    
    def learn_method_effectiveness(self):
        """Determine best forecasting method by SKU characteristics"""
        
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
                    'confidence': 1 - (row['mape_std'] / 100)
                }
        
        # Store recommendations for future use
        for key, recommendation in best_methods.items():
            self._store_method_recommendation(key, recommendation)
    
    def learn_from_categories(self):
        """Category-level learning for new/sparse SKUs"""
        
        category_patterns_query = """
            SELECT
                s.category,
                s.seasonal_pattern,
                AVG(fd.growth_rate_applied) as avg_growth_rate,
                AVG(fa.absolute_percentage_error) as category_mape,
                GROUP_CONCAT(DISTINCT s.seasonal_pattern) as patterns_found,
                COUNT(DISTINCT s.sku_id) as sku_count
            FROM skus s
            JOIN forecast_details fd ON s.sku_id = fd.sku_id
            JOIN forecast_accuracy fa ON s.sku_id = fa.sku_id
            WHERE fa.is_actual_recorded = 1
            GROUP BY s.category, s.seasonal_pattern
            HAVING sku_count >= 5
        """
        
        results = execute_query(category_patterns_query, fetch_all=True)
        
        # Use for new SKUs or SKUs with limited history
        for row in results:
            self._store_category_defaults(
                category=row['category'],
                seasonal_pattern=row['seasonal_pattern'],
                default_growth=row['avg_growth_rate'],
                expected_mape=row['category_mape']
            )
    
    def apply_volatility_adjustments(self):
        """Adjust learning based on SKU volatility"""
        
        volatility_query = """
            SELECT
                fa.sku_id,
                sds.coefficient_variation,
                sds.volatility_class,
                AVG(ABS(fa.percentage_error)) as avg_abs_error,
                STDDEV(fa.percentage_error) as error_volatility
            FROM forecast_accuracy fa
            JOIN sku_demand_stats sds ON fa.sku_id = sds.sku_id
            WHERE fa.is_actual_recorded = 1
            GROUP BY fa.sku_id
        """
        
        results = execute_query(volatility_query, fetch_all=True)
        
        for row in results:
            if row['volatility_class'] == 'high':
                # High volatility - use ensemble methods, conservative adjustments
                self._recommend_ensemble_forecast(row['sku_id'])
            elif row['volatility_class'] == 'low':
                # Low volatility - can use aggressive learning
                self._enable_aggressive_learning(row['sku_id'])
    
    def detect_error_patterns(self):
        """Find systematic patterns in forecast errors"""
        
        pattern_detection_query = """
            SELECT
                sku_id,
                MONTH(forecast_period_start) as month,
                DAYOFWEEK(forecast_period_start) as day_of_week,
                AVG(percentage_error) as avg_error,
                COUNT(*) as occurrences
            FROM forecast_accuracy
            WHERE is_actual_recorded = 1
            GROUP BY sku_id, MONTH(forecast_period_start)
            HAVING ABS(avg_error) > 15 AND occurrences >= 3
        """
        
        results = execute_query(pattern_detection_query, fetch_all=True)
        
        for row in results:
            # Log pattern for investigation
            self._log_error_pattern(
                sku_id=row['sku_id'],
                pattern_type='monthly_bias',
                month=row['month'],
                bias=row['avg_error']
            )
```

## Phase 4: Real-Time Learning Triggers

```python
class RealTimeLearningTriggers:
    """
    Event-driven learning that doesn't wait for monthly cycles.
    """
    
    def on_stockout_detected(self, sku_id, warehouse):
        """Immediate learning when stockout detected"""
        
        # Check if forecast underestimated
        recent_forecast_query = """
            SELECT predicted_demand, actual_demand
            FROM forecast_accuracy
            WHERE sku_id = %s
                AND forecast_period_start <= CURDATE()
                AND forecast_period_end >= CURDATE()
                AND is_actual_recorded = 1
            ORDER BY forecast_date DESC
            LIMIT 1
        """
        
        result = execute_query(recent_forecast_query, (sku_id,), fetch_all=True)
        
        if result and result[0]['actual_demand'] > result[0]['predicted_demand'] * 1.2:
            # Significant under-forecast led to stockout
            self._increase_growth_rate(sku_id, magnitude=0.05)
            self._flag_for_priority_review(sku_id)
    
    def on_viral_growth_detected(self, sku_id):
        """When growth_status changes to 'viral'"""
        
        # Switch to short-term forecasting methods
        self._switch_to_viral_methods(sku_id)
        
        # Increase forecast frequency
        self._enable_weekly_forecasting(sku_id)
        
        # Weight recent data heavily
        self._adjust_data_weighting(sku_id, recent_weight=0.8)
    
    def on_seasonal_shift(self, sku_id):
        """When seasonal pattern changes"""
        
        # Trigger immediate recalculation
        self._recalculate_seasonal_factors(sku_id)
        
        # Alert forecasting team
        self._send_seasonal_alert(sku_id)
```

## Phase 5: Enhanced Dashboard & Reporting

```python
# backend/forecasting_api.py additions

@router.get("/accuracy/learning-insights", response_model=Dict)
async def get_learning_insights():
    """
    Get insights from the learning system.
    """
    insights = {
        'growth_adjustments': get_recent_growth_adjustments(),
        'method_recommendations': get_method_recommendations(),
        'category_patterns': get_category_patterns(),
        'problem_patterns': get_systematic_errors()
    }
    return insights

@router.get("/accuracy/sku/{sku_id}/learning-history", response_model=List[Dict])
async def get_sku_learning_history(sku_id: str):
    """
    Get complete learning history for a SKU.
    """
    history_query = """
        SELECT
            fll.learning_type,
            fll.original_assumption,
            fll.learned_insight,
            fll.confidence_score,
            fll.action_taken,
            fll.expected_improvement,
            fll.actual_improvement,
            fll.created_at
        FROM forecast_learning_log fll
        WHERE sku_id = %s
        ORDER BY created_at DESC
        LIMIT 50
    """
    
    return execute_query(history_query, (sku_id,), fetch_all=True)
```

## Implementation Priority

1. **Week 1**: Database schema updates + Enhanced recording (Phase 1)
2. **Week 2**: Smart accuracy updates with stockout awareness (Phase 2)
3. **Week 3**: Core learning algorithms (Phase 3)
4. **Week 4**: Real-time triggers + Dashboard (Phase 4-5)

## Key Success Metrics

- MAPE improvement: Target 15% reduction in 3 months
- Stockout-adjusted accuracy: Separate true forecast errors from supply issues
- Method optimization: 80% of SKUs using optimal method within 6 months
- Learning velocity: Average time to detect and correct systematic bias < 2 months

This comprehensive approach leverages your existing sophisticated infrastructure while adding intelligent learning capabilities focused purely on demand forecasting accuracy.