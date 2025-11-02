"""
Supplier Ordering Calculations - Batched Implementation

This module implements an optimized batch-query version of the supplier ordering
recommendation engine. It solves the N+1 query problem by:
- Fetching all data in 7-9 upfront queries
- Processing all SKUs in memory
- Batch inserting results with executemany()

Performance: Processes 3,500+ SKU-warehouse combinations in 5-10 seconds
vs 30-60 seconds (then failure) with the original N+1 approach.

Author: Warehouse Transfer Planning Tool
Version: V10.0 (Performance Optimized)
Created: 2025-11-01
"""

import calendar
import time
from datetime import datetime, date, timedelta
from decimal import Decimal
from math import sqrt
from typing import Dict, List, Optional, Tuple
import json

from backend.database import execute_query, execute_many

# Service level Z-scores for ABC-XYZ classification (same as original)
SERVICE_LEVELS = {
    ('A', 'X'): 2.33,  # 99% service level
    ('A', 'Y'): 1.65,  # 95% service level
    ('A', 'Z'): 1.28,  # 90% service level
    ('B', 'X'): 1.65,  # 95% service level
    ('B', 'Y'): 1.28,  # 90% service level
    ('B', 'Z'): 0.84,  # 80% service level
    ('C', 'X'): 1.28,  # 90% service level
    ('C', 'Y'): 0.84,  # 80% service level
    ('C', 'Z'): 0.52   # 70% service level
}


def generate_monthly_recommendations_batched(order_month: Optional[str] = None) -> Dict:
    """
    Generate supplier order recommendations using batched queries (optimized)

    This function replaces the N+1 query pattern with:
    1. Fetch all data upfront in 7-9 queries
    2. Process all SKUs in memory
    3. Batch insert all results at once

    Performance: 3,538 SKU-warehouse combinations in ~5-10 seconds

    Args:
        order_month: Month for recommendations (format: YYYY-MM)

    Returns:
        Summary dict with counts by urgency level
    """
    # Default to next month if not specified
    if not order_month:
        today = date.today()
        if today.month == 12:
            order_month = f"{today.year + 1}-01"
        else:
            order_month = f"{today.year}-{today.month + 1:02d}"

    # Parse order month for day calculations
    year, month = order_month.split('-')
    days_in_month = calendar.monthrange(int(year), int(month))[1]

    print(f"[BATCHED] Starting generation for {order_month} ({days_in_month} days)...")
    start_time = time.time()

    # ============================================================================
    # Helper function to build IN placeholders for safe parameter binding
    def _in_placeholders(seq) -> str:
        return ",".join(["%s"] * len(seq)) or "NULL"

    # STEP 1: FETCH ALL DATA UPFRONT (7-9 queries)
    # ============================================================================

    # Query 1: Get all active SKUs
    print("[BATCHED] Query 1/9: Fetching SKUs...")
    skus_query = """
        SELECT sku_id, supplier, status, abc_code
        FROM skus
        WHERE status IN ('Active', 'Death Row')
        ORDER BY sku_id
    """
    skus = execute_query(skus_query, None, fetch_one=False, fetch_all=True) or []
    sku_ids = [sku['sku_id'] for sku in skus]
    print(f"[BATCHED] Found {len(skus)} SKUs")

    if not skus:
        return {'must_order': 0, 'should_order': 0, 'optional': 0, 'skip': 0, 'total_processed': 0}

    # Query 2: Get all current inventory
    print("[BATCHED] Query 2/9: Fetching current inventory...")
    placeholders = _in_placeholders(sku_ids)
    inventory_query = f"""
        SELECT sku_id, burnaby_qty, kentucky_qty
        FROM inventory_current
        WHERE sku_id IN ({placeholders})
    """
    inventory_data = execute_query(inventory_query, tuple(sku_ids), fetch_one=False, fetch_all=True) or []
    inventory_by_key = {}
    for row in inventory_data:
        inventory_by_key[(row['sku_id'], 'burnaby')] = float(row['burnaby_qty'] or 0)
        inventory_by_key[(row['sku_id'], 'kentucky')] = float(row['kentucky_qty'] or 0)
    print(f"[BATCHED] Loaded inventory for {len(inventory_data)} SKUs")

    # Query 3: Get all pending inventory (within 180 days)
    print("[BATCHED] Query 3/9: Fetching pending inventory...")
    placeholders = _in_placeholders(sku_ids)
    pending_query = f"""
        SELECT sku_id, destination as warehouse, quantity as pending_qty, expected_arrival,
               supplier, order_type, status
        FROM pending_inventory
        WHERE sku_id IN ({placeholders})
          AND order_type = 'supplier'
          AND status IN ('ordered', 'shipped')
          AND (expected_arrival <= DATE_ADD(%s, INTERVAL 180 DAY) OR expected_arrival IS NULL)
    """
    pending_params = tuple(sku_ids) + (f"{order_month}-01",)
    pending_data = execute_query(pending_query, pending_params, fetch_one=False, fetch_all=True) or []
    print(f"[BATCHED] Loaded {len(pending_data)} pending orders")

    # Group pending by (sku_id, warehouse)
    pending_by_key = {}
    for row in pending_data:
        key = (row['sku_id'], row['warehouse'])
        if key not in pending_by_key:
            pending_by_key[key] = []
        pending_by_key[key].append(row)

    # Query 4: Get all forecast data (latest completed run per SKU-warehouse)
    print("[BATCHED] Query 4/9: Fetching forecast data...")
    placeholders = _in_placeholders(sku_ids)
    forecast_query = f"""
        SELECT fd.sku_id, fd.warehouse, fd.avg_monthly_qty, fd.confidence_score,
               fd.method_used, fd.forecast_run_id
        FROM forecast_details fd
        WHERE fd.sku_id IN ({placeholders})
          AND fd.forecast_run_id = (
              SELECT MAX(forecast_run_id)
              FROM forecast_details
              WHERE sku_id = fd.sku_id
                AND warehouse = fd.warehouse
                AND forecast_run_id IN (SELECT id FROM forecast_runs WHERE status = 'completed')
          )
    """
    forecast_data = execute_query(forecast_query, tuple(sku_ids), fetch_one=False, fetch_all=True) or []
    forecast_by_key = {(row['sku_id'], row['warehouse']): row for row in forecast_data}
    print(f"[BATCHED] Loaded forecasts for {len(forecast_data)} SKU-warehouse combinations")

    # Query 5: Get all historical corrected demand (latest month per SKU)
    print("[BATCHED] Query 5/9: Fetching historical demand...")
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
    historical_data = execute_query(historical_query, tuple(sku_ids), fetch_one=False, fetch_all=True) or []
    historical_by_sku = {row['sku_id']: row for row in historical_data}
    print(f"[BATCHED] Loaded historical demand for {len(historical_data)} SKUs")

    # Query 6: Get all lead times
    print("[BATCHED] Query 6/9: Fetching lead times...")
    suppliers = list(set(sku['supplier'] for sku in skus))
    placeholders = _in_placeholders(suppliers)
    lead_time_query = f"""
        SELECT supplier, destination as warehouse, p95_lead_time, reliability_score
        FROM supplier_lead_times
        WHERE supplier IN ({placeholders})
    """
    lead_time_data = execute_query(lead_time_query, tuple(suppliers), fetch_one=False, fetch_all=True) or []
    lead_time_by_key = {(row['supplier'], row['warehouse']): {
        'lead_time': float(row['p95_lead_time']),
        'reliability': float(row['reliability_score'] or 0.85)
    } for row in lead_time_data}
    print(f"[BATCHED] Loaded lead times for {len(lead_time_data)} supplier-warehouse pairs")

    # Query 7: Get all SKU demand stats (coefficient of variation)
    print("[BATCHED] Query 7/9: Fetching demand statistics...")
    placeholders = _in_placeholders(sku_ids)
    stats_query = f"""
        SELECT sku_id, warehouse, coefficient_variation
        FROM sku_demand_stats
        WHERE sku_id IN ({placeholders})
    """
    stats_data = execute_query(stats_query, tuple(sku_ids), fetch_one=False, fetch_all=True) or []
    stats_by_key = {(row['sku_id'], row['warehouse']): float(row['coefficient_variation'] or 0.5) for row in stats_data}
    print(f"[BATCHED] Loaded demand stats for {len(stats_data)} SKU-warehouse combinations")

    # Query 8: Get seasonal patterns (for adjustment factors)
    print("[BATCHED] Query 8/9: Fetching seasonal patterns...")
    placeholders = _in_placeholders(sku_ids)
    seasonal_query = f"""
        SELECT sku_id, warehouse, pattern_strength
        FROM seasonal_patterns_summary
        WHERE sku_id IN ({placeholders})
    """
    seasonal_data = execute_query(seasonal_query, tuple(sku_ids), fetch_one=False, fetch_all=True) or []
    seasonal_by_key = {(row['sku_id'], row['warehouse']): float(row['pattern_strength'] or 0) for row in seasonal_data}
    print(f"[BATCHED] Loaded seasonal patterns for {len(seasonal_data)} SKU-warehouse combinations")

    # Query 9: Get stockout urgency data
    print("[BATCHED] Query 9/9: Fetching stockout urgency...")
    placeholders = _in_placeholders(sku_ids)
    stockout_query = f"""
        SELECT sku_id, MAX(frequency_score) as max_frequency,
               MAX(confidence_level) as confidence
        FROM stockout_patterns
        WHERE sku_id IN ({placeholders})
        GROUP BY sku_id
    """
    stockout_data = execute_query(stockout_query, tuple(sku_ids), fetch_one=False, fetch_all=True) or []
    stockout_by_sku = {row['sku_id']: {
        'frequency': float(row['max_frequency'] or 0),
        'confidence': row['confidence'] or 'low'
    } for row in stockout_data}
    print(f"[BATCHED] Loaded stockout data for {len(stockout_data)} SKUs")

    fetch_time = time.time() - start_time
    print(f"[BATCHED] Data fetching completed in {fetch_time:.2f}s")

    # ============================================================================
    # STEP 2: PROCESS ALL SKUs IN MEMORY (no database queries)
    # ============================================================================
    print(f"[BATCHED] Processing {len(skus)} SKUs × 2 warehouses = {len(skus) * 2} combinations...")
    process_start = time.time()

    results = []
    summary = {'must_order': 0, 'should_order': 0, 'optional': 0, 'skip': 0}

    for sku in skus:
        for warehouse in ['burnaby', 'kentucky']:
            sku_id = sku['sku_id']
            supplier = sku['supplier']

            # Lookup all data from pre-fetched dictionaries (NO QUERIES)
            current_inv = inventory_by_key.get((sku_id, warehouse), 0)
            pending_rows = pending_by_key.get((sku_id, warehouse), [])
            forecast = forecast_by_key.get((sku_id, warehouse))
            historical = historical_by_sku.get(sku_id)
            lead_time_info = lead_time_by_key.get((supplier, warehouse), {'lead_time': 30, 'reliability': 0.85})
            cv = stats_by_key.get((sku_id, warehouse), 0.5)
            seasonal_strength = seasonal_by_key.get((sku_id, warehouse), 0)
            stockout = stockout_by_sku.get(sku_id, {'frequency': 0, 'confidence': 'low'})

            # Calculate effective pending (in-memory, no queries)
            effective_pending = sum(float(row['pending_qty'] or 0) for row in pending_rows)

            # Determine demand source and monthly demand (Phase 2 logic)
            if forecast:
                confidence = float(forecast['confidence_score'] or 0.5)
                forecast_demand = float(forecast['avg_monthly_qty'] or 0)

                if confidence < 0.5:
                    # Low confidence - use historical only
                    if historical:
                        demand_monthly = float(historical.get(f'corrected_demand_{warehouse}', 0) or 0)
                    else:
                        demand_monthly = 0.0
                    demand_source = 'historical'
                    blend_weight = None
                    forecast_demand_monthly = None

                elif confidence >= 0.75:
                    # High confidence - use forecast only
                    demand_monthly = forecast_demand
                    demand_source = 'forecast'
                    blend_weight = 1.0
                    forecast_demand_monthly = forecast_demand

                else:
                    # Medium confidence - blend
                    blend_weight = (confidence - 0.5) / 0.25  # Maps 0.5-0.75 to 0-1
                    historical_demand = float(historical.get(f'corrected_demand_{warehouse}', 0) or 0) if historical else 0.0
                    demand_monthly = (forecast_demand * blend_weight) + (historical_demand * (1 - blend_weight))
                    demand_source = 'blended'
                    forecast_demand_monthly = forecast_demand

            else:
                # No forecast - use historical
                if historical:
                    demand_monthly = float(historical.get(f'corrected_demand_{warehouse}', 0) or 0)
                else:
                    demand_monthly = 0.0
                demand_source = 'historical'
                confidence = 0.75
                blend_weight = None
                forecast_demand_monthly = None

            # Calculate daily demand
            daily_demand = demand_monthly / days_in_month if days_in_month > 0 else 0

            # Calculate safety stock (in-memory)
            abc_code = sku['abc_code'] or 'C'
            xyz_code = 'Y'  # Default
            if cv < 0.25:
                xyz_code = 'X'
            elif cv > 0.50:
                xyz_code = 'Z'

            z_score = SERVICE_LEVELS.get((abc_code, xyz_code), 1.28)
            lead_time_days = lead_time_info['lead_time']
            safety_stock = z_score * (daily_demand * cv) * sqrt(lead_time_days) if daily_demand > 0 else 0

            # Apply seasonal adjustment if strong pattern
            if seasonal_strength >= 0.5:
                safety_stock *= 1.3
            elif seasonal_strength >= 0.3:
                safety_stock *= 1.2

            safety_stock = int(safety_stock)

            # Calculate reorder point
            reorder_point = int((daily_demand * lead_time_days) + safety_stock)

            # Determine urgency level (in-memory logic)
            coverage_with_pending = (current_inv + effective_pending - reorder_point) / daily_demand if daily_demand > 0 else 999

            if current_inv < reorder_point and coverage_with_pending < 30:
                urgency = 'must_order'
            elif current_inv < reorder_point * 1.5:
                urgency = 'should_order'
            else:
                urgency = 'optional'

            # Apply stockout escalation
            if stockout['frequency'] > 70 and stockout['confidence'] in ['high', 'very_high']:
                if urgency == 'optional':
                    urgency = 'should_order'
                elif urgency == 'should_order':
                    urgency = 'must_order'

            # Death Row handling
            if sku['status'] == 'Death Row' and urgency != 'must_order':
                urgency = 'skip'

            # A-item upgrade
            if abc_code == 'A' and urgency == 'optional':
                urgency = 'should_order'

            # Calculate suggested quantity
            target_inventory = reorder_point * 1.5
            suggested_qty = max(0, int(target_inventory - current_inv - effective_pending))

            # Update summary counters
            summary[urgency] += 1

            # Build result tuple for batch insert
            results.append((
                sku_id, warehouse, suggested_qty, suggested_qty, supplier,
                current_inv, 0, effective_pending, None, demand_monthly,
                forecast_demand_monthly, demand_source, confidence if forecast else None,
                blend_weight, False,  # learning_adjustment_applied
                safety_stock, reorder_point, order_month, days_in_month,
                lead_time_days, None, None, None, None,
                urgency, 0, None, False, None, None, None
            ))

    process_time = time.time() - process_start
    print(f"[BATCHED] Processing completed in {process_time:.2f}s")

    # ============================================================================
    # STEP 3: BATCH INSERT ALL RESULTS (1 query)
    # ============================================================================
    print(f"[BATCHED] Batch inserting {len(results)} results...")
    insert_start = time.time()

    if results:
        insert_query = """
            INSERT INTO supplier_order_confirmations (
                sku_id, warehouse, suggested_qty, confirmed_qty, supplier,
                current_inventory, pending_orders_raw, pending_orders_effective, pending_breakdown,
                corrected_demand_monthly, forecast_demand_monthly, demand_source,
                forecast_confidence_score, blend_weight, learning_adjustment_applied,
                safety_stock_qty, reorder_point, order_month, days_in_month,
                lead_time_days_default, lead_time_days_override, expected_arrival_calculated,
                expected_arrival_override, coverage_months, urgency_level, overdue_pending_count,
                stockout_risk_date, is_locked, locked_by, locked_at, notes
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                suggested_qty = VALUES(suggested_qty),
                confirmed_qty = VALUES(confirmed_qty),
                current_inventory = VALUES(current_inventory),
                pending_orders_effective = VALUES(pending_orders_effective),
                corrected_demand_monthly = VALUES(corrected_demand_monthly),
                forecast_demand_monthly = VALUES(forecast_demand_monthly),
                demand_source = VALUES(demand_source),
                forecast_confidence_score = VALUES(forecast_confidence_score),
                blend_weight = VALUES(blend_weight),
                safety_stock_qty = VALUES(safety_stock_qty),
                reorder_point = VALUES(reorder_point),
                urgency_level = VALUES(urgency_level),
                updated_at = CURRENT_TIMESTAMP
        """

        rows_affected = execute_many(insert_query, results)
        print(f"[BATCHED] Inserted/updated {rows_affected} rows")

    insert_time = time.time() - insert_start
    total_time = time.time() - start_time

    print(f"[BATCHED] Batch insert completed in {insert_time:.2f}s")
    print(f"[BATCHED] TOTAL TIME: {total_time:.2f}s")
    print(f"[BATCHED] Summary: {summary}")

    # Return response with keys expected by API
    return {
        'order_month': order_month,
        'total_processed': len(results),
        'must_order_count': summary['must_order'],
        'should_order_count': summary['should_order'],
        'optional_count': summary['optional'],
        'skip_count': summary['skip']
    }
