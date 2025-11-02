# Forecasting Methodology - Design Decision Query

## Context

I'm implementing Phase 2 of V10.0 Supplier Ordering Intelligence Layer, which switches from backward-looking historical sales (`monthly_sales.corrected_demand`) to forward-looking forecast-based calculations.

## Current System Components

### Database Tables (Intelligence Layer)

1. **forecast_details**
   - `avg_monthly_qty`: Primary demand forecast (generated column from month_1_qty through month_12_qty)
   - `confidence_score`: 0-1 scale for forecast reliability
   - `method_used`: Forecast method (ABC/XYZ classification based)
   - `seasonal_pattern_applied`: Pattern type used in forecast

2. **forecast_learning_adjustments**
   - `adjustment_type`: growth_rate/seasonal_factor/method_switch/volatility_adjustment/category_default
   - `adjusted_value`: Recommended new value
   - `adjustment_magnitude`: Size of adjustment
   - `confidence_score`: 0-1 scale
   - `mape_before` and `mape_expected`: Accuracy metrics
   - `applied`: Boolean flag (TRUE when adjustment is active)

3. **seasonal_patterns_summary**
   - `pattern_type`: none/spring_peak/summer_peak/fall_peak/winter_peak/multi_peak/other
   - `pattern_strength`: 0-1 scale for pattern intensity
   - `overall_confidence`: 0-1 scale for statistical reliability
   - `statistical_significance`: Boolean from F-test
   - `peak_months`: Comma-separated month numbers

4. **stockout_patterns**
   - `pattern_type`: seasonal/day_of_week/monthly/chronic
   - `frequency_score`: 0-100 scale for occurrence rate
   - `confidence_level`: low/medium/high
   - `pattern_value`: Pattern details (e.g., "april,may,june")

## Integration Questions

I need to determine the correct thresholds and logic based on the existing forecasting course methodology:

### Question 1: Learning Adjustment Application
**Current Status**: `forecast_learning_adjustments` table has an `applied` flag
**Options**:
A) Only use adjustments where `applied = TRUE` (manual approval required)
B) Auto-apply adjustments when `confidence_score > [threshold]`

**Question**: What does the forecasting methodology recommend?
- Should learning adjustments be auto-applied based on confidence threshold?
- If yes, what confidence threshold indicates a learning adjustment is trustworthy?
- What does `applied = TRUE` actually mean in the current system workflow?

### Question 2: Seasonal Safety Stock Adjustment
**Current Status**: `seasonal_patterns_summary` tracks pattern strength and confidence
**Need**: Multiplier for safety stock when approaching seasonal peaks

**Question**: What does the forecasting methodology recommend?
- What safety stock multiplier is appropriate for approaching seasonal peaks?
- Should adjustment vary by `pattern_strength` (e.g., 1.2x for weak, 1.5x for strong)?
- What confidence threshold (`overall_confidence`) should be required to trust a seasonal pattern?
- Should `statistical_significance = TRUE` be required?

**Example Logic Options**:
```python
# Option A: Fixed multiplier
if approaching_peak and pattern_strength > 0.3 and statistical_significance:
    safety_stock *= 1.3

# Option B: Variable multiplier based on pattern strength
if approaching_peak and statistical_significance:
    safety_stock *= (1.0 + pattern_strength * 0.5)  # 0.3 strength = 1.15x, 0.6 strength = 1.3x
```

### Question 3: Stockout Pattern Urgency Escalation
**Current Status**: `stockout_patterns` tracks chronic/seasonal patterns with frequency scores
**Need**: Logic to escalate urgency levels (optional → should_order → must_order)

**Question**: What does the forecasting methodology recommend?
- What frequency_score threshold indicates a truly chronic stockout problem?
- Should urgency escalation require both high frequency_score AND high confidence_level?
- Should seasonal stockout patterns be treated differently than chronic patterns?

**Example Logic Options**:
```python
# Option A: Frequency threshold only
if pattern_type == 'chronic' and frequency_score > 70:
    escalate_urgency()

# Option B: Frequency + confidence requirement
if pattern_type == 'chronic' and frequency_score > 70 and confidence_level == 'high':
    escalate_urgency()

# Option C: Different thresholds by pattern type
if pattern_type == 'chronic' and frequency_score > 60:
    escalate_urgency()
elif pattern_type == 'seasonal' and is_approaching_season and confidence_level in ['medium', 'high']:
    increase_safety_buffer()
```

### Question 4: Forecast Confidence Threshold
**Current Status**: `forecast_details.confidence_score` ranges 0-1
**Need**: Minimum confidence to use forecast vs. fallback to historical data

**Question**: What does the forecasting methodology recommend?
- What confidence_score threshold indicates a forecast is reliable enough to use?
- Should SKUs below threshold fall back to historical `corrected_demand`?
- Should confidence affect safety stock calculations?

**Example Logic**:
```python
if forecast_confidence_score < [threshold]:
    # Fallback to historical corrected_demand
    demand = get_corrected_demand_historical(sku_id, warehouse)
else:
    # Use forecast
    demand = forecast_data['avg_monthly_qty']
```

## Existing Code References

Based on system research, these files contain the forecasting logic:

1. **backend/forecasting.py** - Core forecasting engine
2. **backend/seasonal_factors.py** - Seasonal pattern detection
3. **backend/forecast_learning.py** - Learning adjustment system
4. **backend/stockout_detection.py** - Stockout pattern analysis

## Request

Please review the forecasting methodology/course and provide the recommended:

1. **Learning adjustment threshold**: What confidence_score qualifies for auto-application? Or should only `applied=TRUE` adjustments be used?

2. **Seasonal safety stock multiplier**: What multiplier (1.2x, 1.3x, 1.5x) should be used for approaching peaks? Should it vary by pattern_strength?

3. **Stockout urgency threshold**: What frequency_score indicates chronic stockout requiring urgency escalation?

4. **Minimum forecast confidence**: What confidence_score threshold should be used to trust a forecast vs. falling back to historical data?

5. **Pattern reliability thresholds**: What values of pattern_strength, overall_confidence, and statistical_significance indicate a pattern is trustworthy?

## Goal

Integrate forecast intelligence into supplier ordering calculations using the same thresholds and logic that the forecasting system was designed with, ensuring consistency across the platform.
