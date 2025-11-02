# Socket Exhaustion Issue in Supplier Order Generation

## Problem Description

When generating supplier order recommendations for October 2025, the API fails after ~30-60 seconds with:

```
WinError 10048: Only one usage of each socket address (protocol/network address/port) is normally permitted
```

## Root Cause

The `generate_monthly_recommendations()` function processes **1,769 SKUs × 2 warehouses = 3,538 iterations** in a sequential loop. Each iteration:

1. Calls `determine_monthly_order_timing()` which makes **8-10 database queries**:
   - `calculate_effective_pending_inventory()` - 2 queries
   - `get_forecast_demand()` - 1 query (forecast data) + 1 fallback query (historical)
   - Historical demand fallback - 1 query
   - Lead time lookup - 1 query
   - `calculate_safety_stock_monthly()` - 2 queries (SKU stats + supplier reliability)
   - `get_seasonal_adjustment_factor()` - 1 query
   - `check_stockout_urgency()` - 1 query

2. Then executes an INSERT/UPDATE query to save the result

**Total Database Connections Created:**
- 3,538 iterations × ~10 queries = **~35,000 database connections**
- All created and destroyed within 30-60 seconds
- Windows has a default limit of ~16,000 TIME_WAIT sockets

## Current (Broken) Code Pattern

```python
# ❌ BAD: N+1 Query Problem
for sku in skus:  # 1,769 SKUs
    for warehouse in ['burnaby', 'kentucky']:  # × 2 = 3,538 iterations
        result = determine_monthly_order_timing(sku_id, warehouse, supplier, order_month)
        # ↑ Makes 8-10 database queries INSIDE the loop

        # Insert result (another query)
        execute_query(INSERT_QUERY, result_data)
```

## Solution: Batch Query Pattern

### Step 1: Fetch All Data Upfront (3-5 Queries Total)

```python
def generate_monthly_recommendations_optimized(order_month: str):
    # Query 1: Get all SKUs (1 query)
    skus = execute_query("SELECT sku_id, supplier, status, abc_code FROM skus WHERE status IN ('Active', 'Death Row')")
    sku_ids = [sku['sku_id'] for sku in skus]

    # Query 2: Get all current inventory (1 query, batched)
    inventory_query = """
        SELECT sku_id, warehouse, qty
        FROM inventory_current
        WHERE sku_id IN %s
    """
    inventory_data = execute_query(inventory_query, (tuple(sku_ids),))
    inventory_by_key = {(row['sku_id'], row['warehouse']): row['qty'] for row in inventory_data}

    # Query 3: Get all pending inventory (1 query, batched)
    pending_query = """
        SELECT sku_id, warehouse, SUM(pending_qty) as total_pending
        FROM pending_inventory
        WHERE sku_id IN %s AND expected_arrival <= DATE_ADD(%s, INTERVAL 90 DAY)
        GROUP BY sku_id, warehouse
    """
    pending_data = execute_query(pending_query, (tuple(sku_ids), order_month))
    pending_by_key = {(row['sku_id'], row['warehouse']): row['total_pending'] for row in pending_data}

    # Query 4: Get all forecast data (1 query, batched)
    forecast_query = """
        SELECT fd.sku_id, fd.warehouse, fd.avg_monthly_qty, fd.confidence_score,
               fr.forecast_run_id
        FROM forecast_details fd
        JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
        WHERE fd.sku_id IN %s
          AND fd.forecast_run_id = (
              SELECT MAX(forecast_run_id)
              FROM forecast_details
              WHERE sku_id = fd.sku_id AND warehouse = fd.warehouse
                AND forecast_run_id IN (SELECT id FROM forecast_runs WHERE status = 'completed')
          )
    """
    forecast_data = execute_query(forecast_query, (tuple(sku_ids),))
    forecast_by_key = {(row['sku_id'], row['warehouse']): row for row in forecast_data}

    # Query 5: Get all historical corrected demand (1 query, batched)
    historical_query = """
        SELECT sku_id, corrected_demand_burnaby, corrected_demand_kentucky
        FROM monthly_sales
        WHERE sku_id IN %s
          AND (year_month, sku_id) IN (
              SELECT MAX(year_month), sku_id
              FROM monthly_sales
              WHERE sku_id IN %s
              GROUP BY sku_id
          )
    """
    historical_data = execute_query(historical_query, (tuple(sku_ids), tuple(sku_ids)))
    historical_by_sku = {row['sku_id']: row for row in historical_data}

    # Query 6: Get all lead times (1 query, batched)
    lead_time_query = """
        SELECT supplier, warehouse, p95_lead_time
        FROM supplier_lead_times
        WHERE supplier IN %s
    """
    suppliers = list(set(sku['supplier'] for sku in skus))
    lead_time_data = execute_query(lead_time_query, (tuple(suppliers),))
    lead_time_by_key = {(row['supplier'], row['warehouse']): row['p95_lead_time'] for row in lead_time_data}

    # Query 7: Get all SKU demand stats (1 query, batched)
    stats_query = """
        SELECT sku_id, warehouse, coefficient_of_variation
        FROM sku_demand_stats
        WHERE sku_id IN %s
    """
    stats_data = execute_query(stats_query, (tuple(sku_ids),))
    stats_by_key = {(row['sku_id'], row['warehouse']): row['coefficient_of_variation'] for row in stats_data}
```

### Step 2: Process in Memory (No Queries in Loop)

```python
    # Build result list in memory (NO database queries)
    results = []

    for sku in skus:
        for warehouse in ['burnaby', 'kentucky']:
            sku_id = sku['sku_id']

            # Lookup data from pre-fetched dictionaries (NO QUERIES)
            inventory_qty = inventory_by_key.get((sku_id, warehouse), 0)
            pending_qty = pending_by_key.get((sku_id, warehouse), 0)
            forecast = forecast_by_key.get((sku_id, warehouse))
            historical = historical_by_sku.get(sku_id)
            lead_time = lead_time_by_key.get((sku['supplier'], warehouse), 30)
            cv = stats_by_key.get((sku_id, warehouse), 0.5)

            # Calculate demand (in-memory logic, no queries)
            if forecast:
                demand_monthly = forecast['avg_monthly_qty']
                confidence = forecast['confidence_score']
                demand_source = 'forecast' if confidence > 0.75 else 'blended'
            else:
                demand_monthly = historical.get(f'corrected_demand_{warehouse}', 0) if historical else 0
                confidence = 0.75
                demand_source = 'historical'

            # Calculate safety stock (in-memory, no queries)
            daily_demand = demand_monthly / 30
            safety_stock = calculate_safety_stock_in_memory(daily_demand, lead_time, cv, sku['abc_code'])

            # Calculate reorder point (in-memory)
            reorder_point = (daily_demand * lead_time) + safety_stock

            # Determine urgency (in-memory logic)
            urgency = determine_urgency_in_memory(inventory_qty, reorder_point, pending_qty)

            # Calculate order quantity (in-memory)
            suggested_qty = max(0, reorder_point - inventory_qty - pending_qty)

            # Add to results list
            results.append({
                'sku_id': sku_id,
                'warehouse': warehouse,
                'suggested_qty': suggested_qty,
                'confirmed_qty': suggested_qty,
                'supplier': sku['supplier'],
                'current_inventory': inventory_qty,
                'pending_orders_effective': pending_qty,
                'corrected_demand_monthly': demand_monthly,
                'forecast_demand_monthly': demand_monthly if forecast else None,
                'demand_source': demand_source,
                'forecast_confidence_score': confidence if forecast else None,
                'safety_stock_qty': safety_stock,
                'reorder_point': reorder_point,
                'order_month': order_month,
                'urgency_level': urgency,
                # ... other fields
            })
```

### Step 3: Batch Insert Results (1 Query)

```python
    # Batch insert all results at once (1 query using executemany)
    if results:
        insert_query = """
            INSERT INTO supplier_order_confirmations (
                sku_id, warehouse, suggested_qty, confirmed_qty, supplier,
                current_inventory, pending_orders_effective, corrected_demand_monthly,
                forecast_demand_monthly, demand_source, forecast_confidence_score,
                safety_stock_qty, reorder_point, order_month, urgency_level, ...
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, ...
            )
            ON DUPLICATE KEY UPDATE
                suggested_qty = VALUES(suggested_qty),
                forecast_demand_monthly = VALUES(forecast_demand_monthly),
                demand_source = VALUES(demand_source),
                ... (update all fields)
        """

        # Use executemany for batch insert (1 query for all 3,538 rows)
        cursor = db.cursor()
        cursor.executemany(insert_query, [tuple(r.values()) for r in results])
        db.commit()

    return {
        'total_processed': len(results),
        'must_order': sum(1 for r in results if r['urgency_level'] == 'must_order'),
        'should_order': sum(1 for r in results if r['urgency_level'] == 'should_order'),
        'optional': sum(1 for r in results if r['urgency_level'] == 'optional'),
        'skip': sum(1 for r in results if r['urgency_level'] == 'skip'),
    }
```

## Performance Comparison

| Metric | Current (Broken) | Optimized Solution |
|--------|------------------|-------------------|
| **Total Queries** | ~35,000 queries | **7-8 queries** |
| **Database Connections** | 35,000 connections | **7-8 connections** |
| **Execution Time** | 30-60s (then fails) | **5-10 seconds** |
| **Socket Exhaustion** | Yes (fails) | **No (fixed)** |
| **Memory Usage** | Low (streaming) | Moderate (in-memory) |

## Why This Fixes The Issue

1. **Reduces queries from 35,000 to 7-8**: Eliminates socket exhaustion
2. **Batched fetching**: All data loaded upfront in 7-8 efficient queries
3. **In-memory processing**: No queries inside the loop
4. **Batch insert**: Single `executemany()` for all 3,538 results
5. **Follows best practices**: Database aggregation over Python loops

## Implementation Steps

1. Create `generate_monthly_recommendations_batched()` function with batched queries
2. Update API endpoint to call new function
3. Test with October 2025 data (3,538 iterations)
4. Verify demand_source shows 'forecast'/'blended' instead of all 'historical'
5. Compare execution time (should be 5-10 seconds vs 30-60s failure)

## Alternative: Connection Pooling Configuration

If batching is too complex, increase connection pool size:

```python
# database_pool.py
pool = create_engine(
    database_url,
    poolclass=QueuePool,
    pool_size=20,        # Increase from default 5
    max_overflow=40,     # Increase from default 10
    pool_timeout=30,
    pool_recycle=3600,
)
```

But this only delays the problem - **batched queries are the correct solution**.

## Files That Need Changes

1. **backend/supplier_ordering_calculations.py**:
   - Create `generate_monthly_recommendations_batched()` function
   - Add helper functions for in-memory calculations
   - Keep old function for backward compatibility (mark as deprecated)

2. **backend/supplier_ordering_api.py**:
   - Update to call `generate_monthly_recommendations_batched()`

3. **backend/database.py**:
   - Add `executemany()` support for batch inserts
   - Optionally increase pool size as temporary fix

## Estimated Effort

- **Batched Implementation**: 2-3 hours (proper fix)
- **Connection Pool Increase**: 5 minutes (temporary band-aid)

## Recommendation

**Implement the batched query pattern** - it's the correct architectural solution and follows the best practices from claude-code-best-practices.md Rule #3.
