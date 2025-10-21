I'll inspect the pattern detection section in `_handle_limited_data_sku` to verify if `baseline_from_pattern` is set and then accidentally reset to None, and to confirm whether debug logs exist for STEP 3.

[1 tool called]

I re-checked the limited‑data (new SKU) path your forecast actually uses and found five concrete defects that explain the “~20 units” result and the missing debug:

- Wrong code path instrumented for logs: The debug you expected was added to a different method earlier; the path used is `_handle_limited_data_sku` (not the established‑SKU path). That’s why you only see the “V7.3 months” logs and nothing for STEP 3.

- Pattern baseline gets diluted/overridden: Even when a launch/stockout pattern is detected, STEP 3 blends it with similar‑SKU demand and then applies a full safety multiplier; this dilutes the Test & Learn baseline and can pull it down into the ~20s range.

- “Similar SKUs” usually resolves to none due to case mismatch: The query uses `status = 'active'` (lowercase) while your data and other modules use `status = 'Active'`. This makes `base_from_similar = 0` and disables seasonal boost, further lowering the result.

- Pending inventory is ignored for “combined”: `_get_pending_quantity` matches `destination = 'combined'` which never exists; that forces the “no pending” branch and applies a larger safety multiplier even when you have pending units.

- Metadata is computed but may not persist: You override `growth_rate_source` in memory, but if `forecast_details` schema/column order doesn’t match the insert, DB ends up empty. That removes a key audit signal showing the Test & Learn path was used.

Where this happens in your code

```720:829:backend/forecasting.py
# STEP 0: Test & Learn detection → sets baseline_from_pattern (with 1.2x stockout boost)
...
if had_early_stockout or launch_spike_detected:
    metadata['launch_pattern_detected'] = True
    metadata['method_used'] = 'limited_data_test_launch'
    metadata['confidence'] = 0.55
    ...
    baseline_from_pattern = ...
    if had_early_stockout:
        baseline_from_pattern *= 1.2
        metadata['growth_rate_source'] = 'proven_demand_stockout'
else:
    baseline_from_pattern = None
```

```874:884:backend/forecasting.py
# STEP 3: Blends away the pattern baseline
if baseline_from_pattern is not None:
    base_demand = baseline_from_pattern
    if base_from_similar > 0:
        base_demand = (baseline_from_pattern * 0.8) + (base_from_similar * 0.2)
```

```912:930:backend/forecasting.py
# STEP 6: Safety multiplier applies fully even when pattern logic already includes boosts
if pending_qty > 0:
    ...
else:
    safety_multiplier = 1.5 if available_months < 3 else 1.3
adjusted_base_demand = base_demand * safety_multiplier
```

```993:1004:backend/forecasting.py
# Similar SKUs use wrong status case (almost always returns none)
WHERE sku_id != %s
  AND category = %s
  AND abc_code = %s
  AND status = 'active'  -- should be 'Active'
```

```1060:1074:backend/forecasting.py
# Pending for 'combined' never matches (destination is 'burnaby' or 'kentucky')
WHERE sku_id = %s
  AND destination = %s          -- 'combined' won’t match
  AND status IN (...)
```

```378:381:backend/forecasting.py
# growth_rate_source is overridden in-memory from metadata
if demand_metadata and 'growth_rate_source' in demand_metadata:
    growth_source = demand_metadata['growth_rate_source']
```

```647:676:backend/forecasting.py
# Save to forecast_details (verify column order matches DB)
INSERT INTO forecast_details (..., growth_rate_applied, growth_rate_source, confidence_score, method_used)
...
..., forecast_data['growth_rate_applied'],
    forecast_data['growth_rate_source'],
    forecast_data['confidence_score'],
    forecast_data['method_used']
```

What to change (minimal, targeted)

- Respect the Test & Learn baseline
  - If `baseline_from_pattern` exists, use it without blending. Only sanity‑cap if absolutely necessary.
  - Set a reduced safety multiplier when pattern used: `safety_multiplier = 1.1`.

- Fix similar‑SKU query
  - Change `status = 'active'` to `status = 'Active'` (or make it case‑insensitive).

- Handle “combined” in pending
  - If `warehouse == 'combined'`, sum both destinations or use the target fulfillment warehouse (KY) for pending coverage.

- Add explicit debug in limited‑data path
  - Log `baseline_from_pattern`, `base_from_actual`, `base_from_similar`, `seasonal_boost`, `pending_qty`, and `adjusted_base_demand`.

- Verify metadata persistence
  - Confirm `forecast_details.growth_rate_source` exists and the insert order matches your schema. Add a one‑line log before save to print the value.

If you want, I can apply these edits now:
- Remove blending in STEP 3 when `baseline_from_pattern` is set.
- Gate safety multiplier to 1.1 for pattern path.
- Fix `status = 'Active'` in `_find_similar_skus`.
- Implement combined‑pending handling in `_get_pending_quantity`.
- Add debug logs around key variables in `_handle_limited_data_sku`.

These changes should lift UB‑YTX7A‑BS from ~19.63 to the ~60–90 range you expect (pattern baseline × low safety, plus any small seasonal/growth effects).