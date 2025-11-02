I'll scan the key backend files to locate the failing query, how parameters are bound, and where the API returns "Unable to generate recommendations." Then I'll propose concrete query fixes and defensive error handling.

[3 tools called]

- Read your error log. The immediate blocker is Query 5; there are also two correctness issues that will trigger “Unable to generate recommendations” even if SQL passes.

### What to change (high impact fixes)

1) Fix Query 5 (historical demand) for MariaDB 10.4 and driver quirks
- Avoid window functions and escape `year_month`.
- Do not rely on `IN %s` inside subqueries; also avoid driver-dependent tuple expansion. Use a correlated subquery and explicit placeholders.

Replace the existing Query 5 with this:

```python
# helper to build IN placeholders once
def _in_placeholders(seq) -> str:
    return ",".join(["%s"] * len(seq)) or "NULL"

placeholders = _in_placeholders(sku_ids)
historical_query = f"""
    SELECT ms1.sku_id, ms1.corrected_demand_burnaby, ms1.corrected_demand_kentucky
    FROM monthly_sales ms1
    WHERE ms1.sku_id IN ({placeholders})
      AND ms1.`year_month` = (
          SELECT MAX(ms2.`year_month`)
          FROM monthly_sales ms2
          WHERE ms2.sku_id = ms1.sku_id
      )
"""
historical_params = tuple(sku_ids)
historical_data = execute_query(historical_query, historical_params, fetch_one=False, fetch_all=True) or []
```

2) Align the calculator’s return shape with the API’s expectations
- The API reads `result['order_month']` and `*_count` keys, which the calculator does not return today. This will raise an exception even if all queries succeed.

At the end of `generate_monthly_recommendations_batched`, return this:

```python
summary_response = {
    "order_month": order_month,
    "total_processed": len(results),
    "must_order_count": summary["must_order"],
    "should_order_count": summary["should_order"],
    "optional_count": summary["optional"],
    "skip_count": summary["skip"],
}
return summary_response
```

3) Make IN-clause usage robust across all queries that pass tuples
- Today several queries use `WHERE ... IN %s` with tuples. These work under pooling/SQLAlchemy but can fail if the code falls back to direct PyMySQL.
- For each query using `IN %s`, build placeholders with the helper above and pass a flat tuple of values. Do this for:
  - Query 2 (inventory), 3 (pending), 4 (forecast), 6 (lead times), 7 (stats), 8 (seasonal), 9 (stockout).

Example pattern:

```python
placeholders = _in_placeholders(sku_ids)
inventory_query = f"""
    SELECT sku_id, burnaby_qty, kentucky_qty
    FROM inventory_current
    WHERE sku_id IN ({placeholders})
"""
inventory_params = tuple(sku_ids)
inventory_data = execute_query(inventory_query, inventory_params, fetch_one=False, fetch_all=True) or []
```

4) Backtick `year_month` consistently
- In any SQL touching `monthly_sales.year_month`, use backticks: ``ms.`year_month` ``.
- You already do this in some places; make Query 5 consistent and review other references.

### Defensive improvements (to prevent generic failures)

- Add context to logs around each query to quickly isolate failures:
  - Wrap each batch query in try/except and log the query “name” and a short hint.
- Keep using connection pooling to prevent socket exhaustion (it’s enabled by default via `USE_CONNECTION_POOLING`). If the pool is unavailable, the fallback path may expose the IN-clause issue; the placeholder approach above avoids that.

### Code references (where the problems are)

Existing failing query:

```150:160:backend/supplier_ordering_calculations_batched.py
    historical_query = """
        SELECT ms1.sku_id, ms1.corrected_demand_burnaby, ms1.corrected_demand_kentucky
        FROM monthly_sales ms1
        INNER JOIN (
            SELECT sku_id, MAX(year_month) as max_month
            FROM monthly_sales
            WHERE sku_id IN %s
            GROUP BY sku_id
        ) ms2 ON ms1.sku_id = ms2.sku_id AND ms1.year_month = ms2.max_month
    """
```

API expecting keys the calculator doesn’t return:

```71:94:backend/supplier_ordering_api.py
        result = generate_monthly_recommendations_batched(order_month=request.order_month)

        # Calculate total value of suggestions
        total_value_query = """
            SELECT COALESCE(SUM(soc.suggested_qty * s.cost_per_unit), 0) as total_value
            FROM supplier_order_confirmations soc
            JOIN skus s ON soc.sku_id = s.sku_id
            WHERE soc.order_month = %s
        """

        total_value_result = execute_query(
            total_value_query,
            (result['order_month'],),
            fetch_one=True,
            fetch_all=False
        )

        return GenerateRecommendationsResponse(
            order_month=result['order_month'],
            recommendations_generated=result['total_processed'],
            must_order_count=result['must_order_count'],
            should_order_count=result['should_order_count'],
            optional_count=result['optional_count'],
            skip_count=result['skip_count'],
            total_value=float(total_value_result.get('total_value', 0) if total_value_result else 0)
        )
```

Current return (missing expected keys):

```403:408:backend/supplier_ordering_calculations_batched.py
    print(f"[BATCHED] TOTAL TIME: {total_time:.2f}s")
    print(f"[BATCHED] Summary: {summary}")

    summary['total_processed'] = len(results)
    return summary
```

### Optional follow-ups (useful but not strictly required)

- Add a small utility in `backend/database.py` to expand tuples for `IN` automatically when direct PyMySQL is used (so call sites remain cleaner). But changing call sites as shown above is simplest and safest.
- Verify there is a unique key on `supplier_order_confirmations` for ON DUPLICATE KEY (e.g., `(sku_id, warehouse, order_month)`), otherwise updates won’t deduplicate.
- Add an index on `monthly_sales (sku_id, year_month)` if not already present (your doc shows it exists).

### Quick test checklist (post-fix)
- Query 5 returns ≤ 1,063 rows, no syntax errors.
- All other queries run in a single pass, no driver errors on IN clauses.
- API returns 200 with counts populated and a non-zero `recordsTotal` when listing.
- Total execution time ~5–10s; no socket exhaustion.

- I read your SQL error doc and the core backend files. I’ll replace Query 5 with a correlated subquery with backticks and explicit IN placeholders, and make the function return the keys the API expects so the generic failure stops appearing.