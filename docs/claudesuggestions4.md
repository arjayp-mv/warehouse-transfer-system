I'll search the project knowledge to find the relevant forecasting methodology and thresholds that have been established for your system.Based on the extensive forecasting and inventory management methodologies in your project knowledge, here are the recommended thresholds and parameters for your Phase 2 implementation:

## 1. **Learning Adjustment Application**

**Recommendation**: Use the `applied = TRUE` flag as the primary control mechanism.

The methodology indicates that learning adjustments should be manually reviewed and approved before application. While confidence scores are important for prioritization, the `applied` flag serves as explicit approval:
- **Only use adjustments where `applied = TRUE`** - this represents manual validation by a forecasting expert
- Use `confidence_score > 0.7` as a threshold for flagging adjustments for review
- The `applied = TRUE` flag means the adjustment has been reviewed, validated, and approved for production use

## 2. **Seasonal Safety Stock Multiplier**

**Recommendation**: Use a dynamic multiplier based on pattern strength:

```python
if approaching_peak and statistical_significance == TRUE:
    if pattern_strength >= 0.5:
        safety_stock *= 1.3  # Strong pattern
    elif pattern_strength >= 0.3:
        safety_stock *= 1.2  # Moderate pattern
    else:
        safety_stock *= 1.15  # Weak pattern
```

Additional criteria:
- **Require `overall_confidence > 0.6`** to apply any seasonal adjustment
- **Require `statistical_significance = TRUE`** as a mandatory condition
- Apply multiplier 2-4 weeks before peak months (from `peak_months` field)

## 3. **Stockout Pattern Urgency Escalation**

**Recommendation**: Use pattern-specific thresholds with confidence requirements:

```python
# Chronic patterns - require high frequency
if pattern_type == 'chronic' and frequency_score > 70 and confidence_level == 'high':
    escalate_urgency()  # Move to must_order

# Seasonal patterns - be proactive
elif pattern_type == 'seasonal' and is_approaching_season and confidence_level in ['medium', 'high']:
    increase_safety_buffer()  # Increase safety stock by 20%
    
# Day of week patterns - moderate threshold
elif pattern_type == 'day_of_week' and frequency_score > 60:
    consider_escalation()  # Move from optional to should_order
```

Key thresholds:
- **Chronic stockouts**: `frequency_score > 70` with `high` confidence
- **Seasonal stockouts**: `frequency_score > 50` with at least `medium` confidence
- **Other patterns**: `frequency_score > 60`

## 4. **Minimum Forecast Confidence**

**Recommendation**: Use tiered confidence thresholds:

```python
if forecast_confidence_score < 0.5:
    # Very low confidence - fall back to historical
    demand = get_corrected_demand_historical(sku_id, warehouse)
    
elif forecast_confidence_score < 0.75:
    # Moderate confidence - blend forecast with historical
    forecast_weight = forecast_confidence_score
    demand = (forecast_data['avg_monthly_qty'] * forecast_weight + 
              historical_corrected_demand * (1 - forecast_weight))
    
else:
    # High confidence - use forecast
    demand = forecast_data['avg_monthly_qty']
```

Thresholds:
- **< 0.5**: Use historical data only
- **0.5 - 0.75**: Weighted blend of forecast and historical
- **> 0.75**: Trust forecast fully

## 5. **Pattern Reliability Thresholds**

**Recommendation**: Use combined criteria for pattern trust:

A pattern is considered reliable when ALL of the following are met:
- `pattern_strength > 0.3` (minimum detectible pattern)
- `overall_confidence > 0.6` (statistical reliability)
- `statistical_significance = TRUE` (passes F-test)

For different use cases:
- **Critical decisions** (e.g., large orders): Require `pattern_strength > 0.5` AND `overall_confidence > 0.8`
- **Standard operations**: Use thresholds above
- **Exploratory/testing**: Can use `pattern_strength > 0.2` with manual review

## Implementation Notes

1. **ABC/XYZ Classification Impact**: Adjust thresholds based on product importance:
   - A-items: Use more conservative thresholds (higher confidence required)
   - C-items: Can use more aggressive thresholds

2. **Safety Stock by Classification**:
   - AX items: Target 95% service level
   - BY items: Target 90% service level  
   - CZ items: Target 70-80% service level

3. **Continuous Monitoring**: Track MAPE (Mean Absolute Percentage Error) after implementing these thresholds and adjust quarterly based on actual performance.

These thresholds align with the forecasting methodology's emphasis on balancing accuracy with practical business constraints while avoiding overfitting.