# SQL Errors in Batched Supplier Order Generation

## Document Purpose

This document provides a comprehensive analysis of all SQL syntax errors encountered during the implementation of the batched supplier order generation system. This is intended for AI analysis to identify patterns and prevent similar issues.

---

## Database Environment

- **Database**: MariaDB 10.4.32
- **Driver**: PyMySQL (Python)
- **File**: `backend/supplier_ordering_calculations_batched.py`
- **Total Queries**: 10 queries (9 data fetch + 1 insert)
- **Dataset Size**: 1,063 SKUs × 2 warehouses = 2,126 combinations

---

## Error History

### Error #1: Window Function Syntax (FIRST ATTEMPT)

**Timestamp**: 2025-11-01 (First generation attempt)

**Location**: `backend/supplier_ordering_calculations_batched.py`, Lines 150-159 (Query 5)

**Error Message**:
```
(1064, "You have an error in your SQL syntax; check the manual that corresponds to your MariaDB server version for the right syntax to use near 'year_month,\n                ROW_NUMBER() OVER (PARTITION BY sku_id ORDER BY y...' at line 7")
```

**Failed Query**:
```sql
SELECT sku_id, corrected_demand_burnaby, corrected_demand_kentucky
FROM (
    SELECT
        sku_id,
        corrected_demand_burnaby,
        corrected_demand_kentucky,
        year_month,
        ROW_NUMBER() OVER (PARTITION BY sku_id ORDER BY year_month DESC) as rn
    FROM monthly_sales
    WHERE sku_id IN %s
) ranked
WHERE rn = 1
```

**Root Cause**:
- MariaDB 10.4 has limited/unstable support for window functions like `ROW_NUMBER()`
- Window functions were introduced in MariaDB 10.2 but had compatibility issues in 10.4

**Fix Attempted**: Rewrote query to use standard JOIN with subquery approach

---

### Error #2: JOIN Subquery Syntax (SECOND ATTEMPT - CURRENT)

**Timestamp**: 2025-11-01 (After fixing Error #1)

**Location**: `backend/supplier_ordering_calculations_batched.py`, Lines 150-159 (Query 5)

**Error Message**:
```
(1064, "You have an error in your SQL syntax; check the manual that corresponds to your MariaDB server version for the right syntax to use near 'year_month) as max_month\n            FROM monthly_sales\n            WHERE sku...' at line 4")
```

**Failed Query**:
```sql
SELECT ms1.sku_id, ms1.corrected_demand_burnaby, ms1.corrected_demand_kentucky
FROM monthly_sales ms1
INNER JOIN (
    SELECT sku_id, MAX(year_month) as max_month
    FROM monthly_sales
    WHERE sku_id IN %s
    GROUP BY sku_id
) ms2 ON ms1.sku_id = ms2.sku_id AND ms1.year_month = ms2.max_month
```

**Root Cause (Suspected)**:
1. **Column name issue**: `year_month` may be a reserved keyword or need backtick escaping in MariaDB
2. **Parameter binding issue**: PyMySQL may have issues with `IN %s` clause inside subqueries
3. **Aggregate function compatibility**: `MAX(year_month)` on VARCHAR/DATE column type mismatch

**Execution Flow**:
```
[BATCHED] Query 1/9: Fetching SKUs... ✅ SUCCESS (1063 SKUs)
[BATCHED] Query 2/9: Fetching current inventory... ✅ SUCCESS (1063 SKUs)
[BATCHED] Query 3/9: Fetching pending inventory... ✅ SUCCESS (207 pending orders)
[BATCHED] Query 4/9: Fetching forecast data... ✅ SUCCESS (3189 SKU-warehouse combinations)
[BATCHED] Query 5/9: Fetching historical demand... ❌ FAILED (SQL syntax error)
```

**Full Stack Trace**:
```
Traceback (most recent call last):
  File "C:\Users\Arjay\Downloads\warehouse-transfer\backend\supplier_ordering_api.py", line 69, in generate_recommendations
    result = generate_monthly_recommendations_batched(order_month=request.order_month)
  File "C:\Users\Arjay\Downloads\warehouse-transfer\backend\supplier_ordering_calculations_batched.py", line 160, in generate_monthly_recommendations_batched
    historical_data = execute_query(historical_query, (tuple(sku_ids),), fetch_one=False, fetch_all=True) or []
  File "C:\Users\Arjay\Downloads\warehouse-transfer\backend\database.py", line 114, in execute_query
    return _execute_query_direct(query, params, fetch_one, fetch_all)
  File "C:\Users\Arjay\Downloads\warehouse-transfer\backend\database.py", line 129, in _execute_query_direct
    cursor.execute(query, params)
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\cursors.py", line 153, in execute
    result = self._query(query)
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\cursors.py", line 322, in _query
    conn.query(q)
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\connections.py", line 575, in query
    self._affected_rows = self._read_query_result(unbuffered=unbuffered)
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\connections.py", line 826, in _read_query_result
    result.read()
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\connections.py", line 1203, in read
    first_packet = self.connection._read_packet()
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\connections.py", line 782, in _read_packet
    packet.raise_for_error()
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\protocol.py", line 219, in raise_for_error
    err.raise_mysql_exception(self._data)
  File "C:\Users\Arjay\Downloads\warehouse-transfer\venv\Lib\site-packages\pymysql\err.py", line 150, in raise_mysql_exception
    raise errorclass(errno, errval)
pymysql.err.ProgrammingError: (1064, "You have an error in your SQL syntax...")
```

---

## Query 5 Context

**Purpose**: Fetch the latest historical corrected demand per SKU as fallback for SKUs without forecast data

**Expected Behavior**:
- For each SKU in the input list (1,063 SKUs)
- Find the most recent month with sales data (`MAX(year_month)`)
- Return `corrected_demand_burnaby` and `corrected_demand_kentucky` for that month

**Why This Query is Critical**:
- Phase 2 Intelligence Layer prioritizes forecast data
- Historical demand is fallback when forecast is unavailable or low confidence
- Without this query, SKUs without forecasts will have zero demand (incorrect)

**Data Model**:
```sql
-- Table: monthly_sales
CREATE TABLE monthly_sales (
    id INT PRIMARY KEY,
    sku_id VARCHAR(50),
    year_month VARCHAR(7),  -- Format: "YYYY-MM" (e.g., "2025-10")
    corrected_demand_burnaby DECIMAL(10,2),
    corrected_demand_kentucky DECIMAL(10,2),
    -- ... other fields
);
```

---

## All 10 Queries in Batched Function

### Query 1: SKUs ✅ WORKING
```sql
SELECT sku_id, supplier, status, abc_code
FROM skus
WHERE status IN ('Active', 'Death Row')
```
**Status**: Working (1,063 SKUs returned)

### Query 2: Current Inventory ✅ WORKING
```sql
SELECT sku_id, burnaby_qty, kentucky_qty
FROM inventory_current
WHERE sku_id IN %s
```
**Status**: Working (1,063 SKUs returned)

### Query 3: Pending Inventory ✅ WORKING
```sql
SELECT sku_id, supplier, warehouse, pending_qty,
       expected_arrival, reliability_category
FROM pending_inventory
WHERE sku_id IN %s
  AND (expected_arrival IS NULL
       OR expected_arrival <= DATE_ADD(CURDATE(), INTERVAL 180 DAY))
  AND order_type = 'supplier'
  AND status IN ('ordered', 'shipped')
```
**Status**: Working (207 pending orders returned)

### Query 4: Forecast Data ✅ WORKING
```sql
SELECT fd.sku_id, fd.warehouse, fd.avg_monthly_qty,
       fd.confidence_score, fd.demand_volatility_category,
       fd.base_demand_used, fd.method_used, fd.growth_rate_applied,
       fd.growth_rate_source, fd.seasonal_adjustment_applied,
       fd.forecast_run_id, fr.forecast_date
FROM forecast_details fd
JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
WHERE fd.sku_id IN %s
  AND fd.forecast_run_id = (
      SELECT MAX(fd2.forecast_run_id)
      FROM forecast_details fd2
      JOIN forecast_runs fr2 ON fd2.forecast_run_id = fr2.id
      WHERE fd2.sku_id = fd.sku_id
        AND fd2.warehouse = fd.warehouse
        AND fr2.status = 'completed'
  )
```
**Status**: Working (3,189 SKU-warehouse combinations returned)

### Query 5: Historical Demand ❌ FAILING
```sql
SELECT ms1.sku_id, ms1.corrected_demand_burnaby, ms1.corrected_demand_kentucky
FROM monthly_sales ms1
INNER JOIN (
    SELECT sku_id, MAX(year_month) as max_month
    FROM monthly_sales
    WHERE sku_id IN %s
    GROUP BY sku_id
) ms2 ON ms1.sku_id = ms2.sku_id AND ms1.year_month = ms2.max_month
```
**Status**: ❌ SQL Syntax Error (see Error #2 above)

### Query 6: Lead Times ⚠️ NOT YET TESTED
```sql
SELECT supplier, warehouse, p95_lead_time, on_time_rate
FROM supplier_lead_times
WHERE supplier IN %s
```
**Status**: Not yet tested (Query 5 blocks execution)

### Query 7: SKU Demand Stats ⚠️ NOT YET TESTED
```sql
SELECT sku_id, warehouse, coefficient_of_variation
FROM sku_demand_stats
WHERE sku_id IN %s
```
**Status**: Not yet tested (Query 5 blocks execution)

### Query 8: Seasonal Patterns ⚠️ NOT YET TESTED
```sql
SELECT sku_id, warehouse, seasonal_index
FROM seasonal_patterns_summary
WHERE sku_id IN %s
```
**Status**: Not yet tested (Query 5 blocks execution)

### Query 9: Stockout History ⚠️ NOT YET TESTED
```sql
SELECT sku_id,
       MAX(frequency_score) as max_frequency,
       MAX(confidence_level) as confidence
FROM stockout_patterns
WHERE sku_id IN %s
GROUP BY sku_id
```
**Status**: Not yet tested (Query 5 blocks execution)

### Query 10: Batch Insert ⚠️ NOT YET TESTED
```sql
INSERT INTO supplier_order_confirmations (
    sku_id, warehouse, suggested_qty, confirmed_qty, supplier,
    current_inventory, pending_orders_effective, corrected_demand_monthly,
    forecast_demand_monthly, demand_source, forecast_confidence_score,
    safety_stock_qty, reorder_point, order_month, urgency_level,
    -- ... 30+ other fields
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, ...
)
ON DUPLICATE KEY UPDATE
    suggested_qty = VALUES(suggested_qty),
    forecast_demand_monthly = VALUES(forecast_demand_monthly),
    demand_source = VALUES(demand_source),
    -- ... all fields
```
**Status**: Not yet tested (Query 5 blocks execution)

---

## MariaDB Compatibility Issues Identified

### 1. Window Functions (ROW_NUMBER, RANK, etc.)
- **MariaDB Version**: Introduced in 10.2, stabilized in 10.5+
- **Current Version**: 10.4.32 (unstable support)
- **Recommendation**: Avoid window functions, use JOIN/subquery approach

### 2. Reserved Keywords and Column Names
- **Potential Issue**: `year_month` may need backtick escaping
- **Safe Approach**: Always use backticks for column names: `` `year_month` ``

### 3. IN Clause with Tuple Parameters
- **Potential Issue**: PyMySQL may have issues with `IN %s` inside subqueries
- **Alternative Approach**: Use separate query or dynamic SQL generation

### 4. MAX() on VARCHAR/DATE Columns
- **Potential Issue**: `year_month` is VARCHAR(7) format "YYYY-MM"
- **Consideration**: Ensure proper sorting (lexicographic sorting works for "YYYY-MM")

---

## Proposed Solutions for Query 5

### Option 1: Escape Column Names with Backticks
```sql
SELECT ms1.sku_id, ms1.corrected_demand_burnaby, ms1.corrected_demand_kentucky
FROM monthly_sales ms1
INNER JOIN (
    SELECT sku_id, MAX(`year_month`) as max_month
    FROM monthly_sales
    WHERE sku_id IN %s
    GROUP BY sku_id
) ms2 ON ms1.sku_id = ms2.sku_id AND ms1.`year_month` = ms2.max_month
```

### Option 2: Use Correlated Subquery (Simpler, No JOIN)
```sql
SELECT sku_id, corrected_demand_burnaby, corrected_demand_kentucky
FROM monthly_sales ms1
WHERE sku_id IN %s
  AND `year_month` = (
      SELECT MAX(`year_month`)
      FROM monthly_sales ms2
      WHERE ms2.sku_id = ms1.sku_id
  )
```

### Option 3: Two-Step Approach (Split into 2 Queries)
```python
# Step 1: Get latest year_month per SKU
max_months_query = """
    SELECT sku_id, MAX(`year_month`) as max_month
    FROM monthly_sales
    WHERE sku_id IN %s
    GROUP BY sku_id
"""
max_months = execute_query(max_months_query, (tuple(sku_ids),), fetch_all=True)

# Step 2: Build WHERE clause to fetch exact records
conditions = " OR ".join(
    f"(sku_id = '{row['sku_id']}' AND `year_month` = '{row['max_month']}')"
    for row in max_months
)
historical_query = f"""
    SELECT sku_id, corrected_demand_burnaby, corrected_demand_kentucky
    FROM monthly_sales
    WHERE {conditions}
"""
historical_data = execute_query(historical_query, None, fetch_all=True)
```

### Option 4: Use HAVING with GROUP BY (Aggregate Approach)
```sql
SELECT
    sku_id,
    SUBSTRING_INDEX(GROUP_CONCAT(corrected_demand_burnaby ORDER BY `year_month` DESC), ',', 1) as corrected_demand_burnaby,
    SUBSTRING_INDEX(GROUP_CONCAT(corrected_demand_kentucky ORDER BY `year_month` DESC), ',', 1) as corrected_demand_kentucky
FROM monthly_sales
WHERE sku_id IN %s
GROUP BY sku_id
```

**Recommended**: Try Option 1 first (backticks), then Option 2 (correlated subquery) if Option 1 fails.

---

## Action Items for AI Analysis

### CRITICAL: Check All Queries for Similar Issues

1. **Scan all 10 queries** in `backend/supplier_ordering_calculations_batched.py` (lines 80-395)
2. **Look for**:
   - Column names that could be reserved keywords: `year_month`, `month`, `date`, `order`, `status`, etc.
   - Any aggregate functions with VARCHAR columns: `MAX()`, `MIN()`, `GROUP_CONCAT()`
   - Subqueries with `IN` clauses and parameter binding
   - Date/time functions that may behave differently in MariaDB vs MySQL

3. **Test Strategy**:
   - Add backticks to ALL column names in Query 5
   - If Query 5 succeeds, test Queries 6-9
   - Verify Query 10 (batch insert) handles 2,126 rows without timeout

4. **Pattern Analysis**:
   - Identify if other queries use similar JOIN/subquery patterns
   - Check if Queries 6, 7, 8 have the same `IN %s` parameter binding issue
   - Verify all table aliases are correctly referenced

---

## Files Involved

### Primary File (Contains all 10 queries)
- **Path**: `backend/supplier_ordering_calculations_batched.py`
- **Lines**: 1-409 (entire file)
- **Key Sections**:
  - Lines 80-162: Data fetch queries (Queries 1-5)
  - Lines 167-209: Additional data queries (Queries 6-9)
  - Lines 215-358: In-memory processing loop (no DB queries)
  - Lines 360-395: Batch insert (Query 10)

### Related Files
- **Path**: `backend/supplier_ordering_api.py`
  - Line 69: Calls `generate_monthly_recommendations_batched()`
  - Handles API endpoint `/api/supplier-orders/generate`

- **Path**: `backend/database.py`
  - Line 114: `execute_query()` function (query execution wrapper)
  - Line 129: `_execute_query_direct()` (actual cursor.execute() call)

---

## Database Schema Reference

### Table: monthly_sales
```sql
CREATE TABLE monthly_sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku_id VARCHAR(50) NOT NULL,
    year_month VARCHAR(7) NOT NULL,  -- "YYYY-MM" format
    corrected_demand_burnaby DECIMAL(10,2) DEFAULT 0,
    corrected_demand_kentucky DECIMAL(10,2) DEFAULT 0,
    -- ... other fields
    INDEX idx_sku_month (sku_id, year_month),
    INDEX idx_year_month (year_month)
);
```

### Indexes Available
- `idx_sku_month`: Composite index on (sku_id, year_month) - should help with JOIN performance
- `idx_year_month`: Index on year_month alone

---

## Testing Checklist

After fixing Query 5, verify:

- [ ] Query 5 executes without SQL syntax errors
- [ ] Query 5 returns expected number of records (≤ 1,063 SKUs)
- [ ] Query 6 (lead times) executes successfully
- [ ] Query 7 (demand stats) executes successfully
- [ ] Query 8 (seasonal patterns) executes successfully
- [ ] Query 9 (stockout history) executes successfully
- [ ] In-memory processing completes for all 2,126 combinations
- [ ] Query 10 (batch insert) successfully inserts all 2,126 rows
- [ ] Total execution time is 5-10 seconds (not 30-60s)
- [ ] No WinError 10048 socket exhaustion errors
- [ ] `demand_source` field shows mix of 'forecast', 'blended', 'historical' (not all 'historical')
- [ ] API response returns proper metrics (must_order, should_order, optional, skip counts)

---

## Performance Expectations

### Before (N+1 Query Pattern) - BROKEN
- **Total Queries**: ~35,000 queries
- **Execution Time**: 30-60 seconds (then crashes with socket exhaustion)
- **Database Connections**: 35,000 connections created/destroyed
- **Error**: WinError 10048 (only one usage of socket address permitted)

### After (Batched Pattern) - TARGET
- **Total Queries**: 10 queries (9 fetch + 1 insert)
- **Execution Time**: 5-10 seconds
- **Database Connections**: 10 connections
- **Memory Usage**: ~50-100 MB (all data loaded into memory)

---

## Success Criteria

The batched generation is successful when:

1. ✅ All 9 data fetch queries execute without errors
2. ✅ In-memory processing completes for 2,126 SKU-warehouse combinations
3. ✅ Batch insert successfully saves all 2,126 records
4. ✅ Total execution time: 5-10 seconds
5. ✅ No socket exhaustion errors (WinError 10048)
6. ✅ API returns 200 OK with proper metrics
7. ✅ Frontend displays updated recommendations with correct urgency levels
8. ✅ `demand_source` distribution shows proper forecast vs historical usage:
   - Expected: ~60-70% 'forecast' (3189 forecasts / 2126 combinations = good coverage)
   - Expected: ~20-30% 'blended' (forecast exists but low confidence)
   - Expected: ~5-10% 'historical' (no forecast available)

---

## Additional Context

### Why Socket Exhaustion Happened
The original non-batched implementation created a new database connection for every query inside nested loops:

```python
# BAD: N+1 Query Pattern
for sku in skus:  # 1,063 iterations
    for warehouse in ['burnaby', 'kentucky']:  # × 2 = 2,126 iterations
        # Each iteration makes 8-10 database queries
        result = determine_monthly_order_timing(...)  # Opens 8-10 connections
        execute_query(INSERT_QUERY, ...)  # Opens 1 more connection

# Total: 2,126 × 11 = ~23,386 database connections in 30-60 seconds
# Windows TCP limit: ~16,000 TIME_WAIT sockets → Socket Exhaustion
```

### Batched Approach Solution
```python
# GOOD: Batch Query Pattern
# Step 1: Fetch all data (9 queries total, ~5 seconds)
skus = fetch_all_skus()
inventory = fetch_all_inventory(sku_ids)
pending = fetch_all_pending(sku_ids)
forecasts = fetch_all_forecasts(sku_ids)
historical = fetch_all_historical(sku_ids)
lead_times = fetch_all_lead_times(suppliers)
stats = fetch_all_stats(sku_ids)
seasonal = fetch_all_seasonal(sku_ids)
stockout = fetch_all_stockout(sku_ids)

# Step 2: Process in memory (NO database queries, ~2 seconds)
results = []
for sku in skus:
    for warehouse in ['burnaby', 'kentucky']:
        # All lookups are in-memory dictionary access (instant)
        inventory_qty = inventory_by_key.get((sku_id, warehouse), 0)
        forecast = forecast_by_key.get((sku_id, warehouse))
        # ... calculate order quantities
        results.append(result_row)

# Step 3: Batch insert all results (1 query, ~1 second)
cursor.executemany(INSERT_QUERY, results)  # Single batch insert

# Total: 10 database connections, ~8 seconds execution time
```

---

## Conclusion

The batched implementation is architecturally correct and follows best practices for database optimization. The current blocker is a MariaDB SQL syntax compatibility issue in Query 5 (historical demand fetch). Once Query 5 is fixed with proper column escaping or alternative query pattern, the remaining queries should execute successfully.

**Priority**: Fix Query 5 syntax, then verify Queries 6-10 work correctly.

**Risk**: If other queries have similar syntax issues, they will need the same fixes (backticks, parameter binding adjustments, etc.).

---

## Document Metadata

- **Created**: 2025-11-01
- **Purpose**: Comprehensive error analysis for AI debugging
- **Status**: Query 5 still failing, Queries 6-10 untested
- **Next Step**: Apply backticks to Query 5 column names and retest
