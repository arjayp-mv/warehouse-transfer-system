"""
Supplier Ordering Calculations Module

This module implements the core calculation engine for the Monthly Supplier Ordering System.
It provides functions for:
- Time-phased pending order analysis with confidence scoring
- Enhanced safety stock calculation for monthly ordering cycles
- Urgency level determination (must_order, should_order, optional, skip)
- Monthly order quantity recommendations

Key Dependencies:
- supplier_lead_times: P95 lead time, reliability scores, coefficient of variation
- pending_inventory: Expected arrival dates, order quantities
- monthly_sales: Stockout-corrected demand (corrected_demand_burnaby/kentucky)
- inventory_current: Current stock levels
- sku_demand_stats: Coefficient of variation for safety stock

Author: Warehouse Transfer Planning Tool
Version: V9.0
Created: 2025-01-22
"""

import calendar
from datetime import datetime, date, timedelta
from decimal import Decimal
from math import sqrt
from typing import Dict, List, Optional, Tuple
import json

from backend.database import execute_query

# Service level Z-scores for ABC-XYZ classification
SERVICE_LEVELS = {
    ('A', 'X'): 2.33,  # 99% service level
    ('A', 'Y'): 2.05,  # 98% service level
    ('A', 'Z'): 2.05,  # 98% service level
    ('B', 'X'): 1.88,  # 97% service level
    ('B', 'Y'): 1.65,  # 95% service level
    ('B', 'Z'): 1.28,  # 90% service level
    ('C', 'X'): 1.28,  # 90% service level
    ('C', 'Y'): 1.28,  # 90% service level
    ('C', 'Z'): 0.84,  # 80% service level
}

# Fixed monthly review period (orders processed once per month)
REVIEW_PERIOD_DAYS = 30


def get_time_phased_pending_orders(
    sku_id: str,
    warehouse: str,
    planning_horizon_days: int
) -> Dict[str, List[Dict]]:
    """
    Categorize pending orders by arrival timing relative to planning needs.

    Args:
        sku_id: SKU identifier
        warehouse: Destination warehouse (burnaby or kentucky)
        planning_horizon_days: How far ahead to consider (lead_time + review_period)

    Returns:
        Dict with categorized pending orders:
        - overdue: Past expected_arrival but not received
        - imminent: Arriving within review period (30 days)
        - covered: Arriving within planning horizon
        - future: Beyond planning horizon (ignored)
    """
    query = """
        SELECT
            id,
            quantity,
            order_date,
            expected_arrival,
            lead_time_days,
            status,
            is_estimated,
            DATEDIFF(expected_arrival, CURDATE()) as days_until_arrival,
            CASE
                WHEN expected_arrival < CURDATE() AND status != 'received' THEN 1
                ELSE 0
            END as is_late
        FROM pending_inventory
        WHERE sku_id = %s
          AND destination = %s
          AND order_type = 'supplier'
          AND status IN ('ordered', 'shipped')
          AND expected_arrival IS NOT NULL
        ORDER BY expected_arrival
    """

    pending_orders = execute_query(query, (sku_id, warehouse), fetch_one=False, fetch_all=True) or []

    # Categorize orders by timing
    categorized = {
        'overdue': [],
        'imminent': [],
        'covered': [],
        'future': []
    }

    for order in pending_orders:
        days_to_arrival = order['days_until_arrival']

        if order['is_late']:
            categorized['overdue'].append(order)
        elif days_to_arrival <= REVIEW_PERIOD_DAYS:
            categorized['imminent'].append(order)
        elif days_to_arrival <= planning_horizon_days:
            categorized['covered'].append(order)
        else:
            categorized['future'].append(order)

    return categorized


def calculate_effective_pending_inventory(
    sku_id: str,
    warehouse: str,
    supplier: str
) -> Dict:
    """
    Calculate time-phased pending inventory with confidence scoring.

    Applies confidence factors based on arrival timing and supplier reliability:
    - Overdue orders: 80% confidence (may be delayed further or cancelled)
    - Imminent orders: 100% confidence (arriving soon)
    - Covered orders: reliability_score * time_factor
    - Future orders: 0% (ignored - beyond planning horizon)

    Args:
        sku_id: SKU identifier
        warehouse: Destination warehouse
        supplier: Supplier name (for reliability lookup)

    Returns:
        Dict with:
        - total_effective: Weighted sum of pending quantities
        - detail: Array of pending orders with confidence scores
        - overdue_count: Number of late orders
        - future_ignored: Total quantity beyond planning horizon
    """
    # Get supplier lead time for planning horizon
    lt_query = """
        SELECT p95_lead_time, reliability_score
        FROM supplier_lead_times
        WHERE supplier = %s
          AND destination = %s
    """
    lt_result = execute_query(lt_query, (supplier, warehouse), fetch_one=True, fetch_all=False)

    if not lt_result:
        # Default fallback if no lead time data
        p95_lead_time = 60
        reliability_score = 0.7
    else:
        p95_lead_time = lt_result.get('p95_lead_time') or 60
        reliability_score = float(lt_result.get('reliability_score') or 70) / 100

    planning_horizon = p95_lead_time + REVIEW_PERIOD_DAYS

    # Get categorized pending orders
    pending = get_time_phased_pending_orders(sku_id, warehouse, planning_horizon)

    effective_pending = 0
    pending_detail = []

    # Process overdue orders
    for order in pending['overdue']:
        # Apply 80% confidence for overdue orders
        confidence = 0.8
        effective_qty = order['quantity'] * confidence
        effective_pending += effective_qty

        pending_detail.append({
            'order_id': order['id'],
            'quantity': order['quantity'],
            'confidence': confidence,
            'category': 'overdue',
            'expected_arrival': str(order['expected_arrival']),
            'reason': f"Overdue by {-order['days_until_arrival']} days"
        })

    # Process imminent orders (arriving within review period)
    for order in pending['imminent']:
        # 100% confidence for imminent orders
        confidence = 1.0
        effective_qty = order['quantity'] * confidence
        effective_pending += effective_qty

        pending_detail.append({
            'order_id': order['id'],
            'quantity': order['quantity'],
            'confidence': confidence,
            'category': 'imminent',
            'expected_arrival': str(order['expected_arrival']),
            'reason': f"Arriving in {order['days_until_arrival']} days"
        })

    # Process covered orders (arriving during lead time)
    for order in pending['covered']:
        # Confidence based on supplier reliability and time distance
        time_factor = 1 - (order['days_until_arrival'] / planning_horizon) * 0.2
        confidence = reliability_score * time_factor
        effective_qty = order['quantity'] * confidence
        effective_pending += effective_qty

        pending_detail.append({
            'order_id': order['id'],
            'quantity': order['quantity'],
            'confidence': round(confidence, 2),
            'category': 'covered',
            'expected_arrival': str(order['expected_arrival']),
            'reason': f"Lead time coverage, {int(reliability_score*100)}% reliability"
        })

    # Calculate future ignored quantity
    future_ignored = sum(o['quantity'] for o in pending['future'])

    return {
        'total_effective': round(effective_pending),
        'detail': pending_detail,
        'overdue_count': len(pending['overdue']),
        'future_ignored': future_ignored
    }


def calculate_safety_stock_monthly(
    sku_id: str,
    warehouse: str,
    daily_demand: float,
    lead_time_days: int
) -> int:
    """
    Calculate safety stock for monthly ordering cycle.

    Uses enhanced formula accounting for:
    - Monthly review period (30 days vs daily/weekly)
    - Demand variability (coefficient of variation)
    - Lead time variability
    - ABC-XYZ service level requirements

    Formula: Z * sqrt((demand_std^2 * period) + (demand^2 * lt_cv^2 * period))

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse code
        daily_demand: Average daily demand
        lead_time_days: P95 lead time in days

    Returns:
        Safety stock quantity (integer)
    """
    # Get SKU characteristics for service level and variability
    sku_query = """
        SELECT
            s.abc_code,
            s.xyz_code,
            sds.coefficient_variation
        FROM skus s
        LEFT JOIN sku_demand_stats sds ON s.sku_id = sds.sku_id AND sds.warehouse = %s
        WHERE s.sku_id = %s
    """
    sku_result = execute_query(sku_query, (warehouse, sku_id), fetch_one=True, fetch_all=False)

    if not sku_result:
        # Defaults if SKU not found
        abc_code = 'C'
        xyz_code = 'Z'
        cv = 0.5
    else:
        abc_code = sku_result.get('abc_code') or 'C'
        xyz_code = sku_result.get('xyz_code') or 'Z'
        cv = float(sku_result.get('coefficient_variation') or 0.5)

    # Get Z-score based on ABC-XYZ classification
    z_score = SERVICE_LEVELS.get((abc_code, xyz_code), 1.28)

    # Calculate total period (lead time + review period)
    total_period = lead_time_days + REVIEW_PERIOD_DAYS

    # Demand standard deviation
    demand_std = daily_demand * cv

    # Lead time coefficient of variation (assume 20% for now)
    lt_cv = 0.2

    # Safety stock formula
    safety_stock = z_score * sqrt(
        (demand_std ** 2 * total_period) +
        (daily_demand ** 2 * lt_cv ** 2 * total_period)
    )

    # Add monthly buffer for critical A items
    if abc_code == 'A':
        monthly_buffer = daily_demand * 7  # Extra week for A items
        safety_stock += monthly_buffer
    elif abc_code == 'B' and xyz_code in ['Y', 'Z']:
        monthly_buffer = daily_demand * 3.5  # Half week for variable B items
        safety_stock += monthly_buffer

    return round(safety_stock)


def determine_monthly_order_timing(
    sku_id: str,
    warehouse: str,
    supplier: str,
    order_month: str
) -> Dict:
    """
    Determine if SKU needs ordering this month and calculate quantity.

    Decision logic based on coverage vs lead time:
    - must_order: coverage < lead_time + 30 days
    - should_order: coverage < lead_time + 60 days
    - optional: coverage < lead_time + 90 days
    - skip: coverage >= lead_time + 90 days

    Args:
        sku_id: SKU identifier
        warehouse: Destination warehouse
        supplier: Supplier name
        order_month: Month in YYYY-MM format

    Returns:
        Dict with decision, urgency, order_qty, coverage, stockout_risk_date
    """
    # Get current inventory
    inv_query = """
        SELECT
            CASE
                WHEN %s = 'burnaby' THEN burnaby_qty
                WHEN %s = 'kentucky' THEN kentucky_qty
            END as current_stock
        FROM inventory_current
        WHERE sku_id = %s
    """
    inv_result = execute_query(inv_query, (warehouse, warehouse, sku_id), fetch_one=True, fetch_all=False)
    current_stock = inv_result.get('current_stock') if inv_result else 0

    # Get effective pending inventory
    pending_result = calculate_effective_pending_inventory(sku_id, warehouse, supplier)
    effective_pending = pending_result['total_effective']

    # Get corrected monthly demand
    demand_query = """
        SELECT
            CASE
                WHEN %s = 'burnaby' THEN corrected_demand_burnaby
                WHEN %s = 'kentucky' THEN corrected_demand_kentucky
            END as corrected_demand
        FROM monthly_sales
        WHERE sku_id = %s
        ORDER BY `year_month` DESC
        LIMIT 1
    """
    demand_result = execute_query(demand_query, (warehouse, warehouse, sku_id), fetch_one=True, fetch_all=False)
    corrected_demand_monthly = float(demand_result.get('corrected_demand')) if demand_result and demand_result.get('corrected_demand') else 0

    # Get actual days in this month
    year, month = order_month.split('-')
    days_in_month = calendar.monthrange(int(year), int(month))[1]

    # Calculate daily demand using actual days
    daily_demand = corrected_demand_monthly / days_in_month if days_in_month > 0 else 0

    # Get lead time from supplier_lead_times
    lt_query = """
        SELECT p95_lead_time
        FROM supplier_lead_times
        WHERE supplier = %s AND destination = %s
    """
    lt_result = execute_query(lt_query, (supplier, warehouse), fetch_one=True, fetch_all=False)
    lead_time_days = lt_result.get('p95_lead_time') if lt_result and lt_result.get('p95_lead_time') else 60

    # Calculate coverage
    current_position = current_stock + effective_pending
    days_of_coverage = current_position / daily_demand if daily_demand > 0 else 9999

    # Determine urgency level
    if days_of_coverage < lead_time_days + 30:
        urgency = 'must_order'
        decision = 'MUST_ORDER'
    elif days_of_coverage < lead_time_days + 60:
        urgency = 'should_order'
        decision = 'SHOULD_ORDER'
    elif days_of_coverage < lead_time_days + 90:
        urgency = 'optional'
        decision = 'OPTIONAL'
    else:
        urgency = 'skip'
        decision = 'SKIP'

    # Calculate order quantity if not skipping
    order_qty = 0
    stockout_risk_date = None
    coverage_months = days_of_coverage / 30 if daily_demand > 0 else None

    if decision != 'SKIP':
        # Target coverage: lead time + 60 days (2 months)
        target_coverage_days = lead_time_days + 60
        target_inventory = daily_demand * target_coverage_days

        # Add safety stock
        safety_stock = calculate_safety_stock_monthly(sku_id, warehouse, daily_demand, lead_time_days)
        target_inventory += safety_stock

        # Calculate order quantity
        order_qty = max(0, target_inventory - current_position)

        # Calculate stockout risk date
        if daily_demand > 0:
            stockout_risk_date = date.today() + timedelta(days=int(days_of_coverage))

        # Calculate coverage after order
        if order_qty > 0:
            coverage_months = (current_position + order_qty) / (daily_demand * 30) if daily_demand > 0 else None

    return {
        'decision': decision,
        'urgency_level': urgency,
        'order_qty': round(order_qty),
        'days_of_coverage': round(days_of_coverage, 1),
        'coverage_months': round(coverage_months, 2) if coverage_months else None,
        'stockout_risk_date': stockout_risk_date,
        'current_stock': current_stock,
        'effective_pending': effective_pending,
        'pending_detail': pending_result['detail'],
        'overdue_pending_count': pending_result['overdue_count'],
        'corrected_demand_monthly': corrected_demand_monthly,
        'days_in_month': days_in_month,
        'lead_time_days': lead_time_days,
        'safety_stock_qty': calculate_safety_stock_monthly(sku_id, warehouse, daily_demand, lead_time_days)
    }


def generate_monthly_recommendations(
    order_month: Optional[str] = None
) -> Dict:
    """
    Generate supplier order recommendations for all active SKUs.

    Processes all active SKUs for both warehouses (burnaby, kentucky) and
    inserts recommendations into supplier_order_confirmations table.

    Args:
        order_month: Month in YYYY-MM format (defaults to current month)

    Returns:
        Dict with summary statistics (must_order count, should_order count, etc.)
    """
    # Default to current month if not specified
    if not order_month:
        today = date.today()
        order_month = today.strftime('%Y-%m')

    # Get actual days in this month
    year, month = order_month.split('-')
    days_in_month = calendar.monthrange(int(year), int(month))[1]

    # Get all active SKUs
    skus_query = """
        SELECT sku_id, supplier, status, abc_code
        FROM skus
        WHERE status IN ('Active', 'Death Row')
        ORDER BY sku_id
    """
    skus = execute_query(skus_query, None, fetch_one=False, fetch_all=True) or []

    summary = {
        'must_order': 0,
        'should_order': 0,
        'optional': 0,
        'skip': 0,
        'total_processed': 0
    }

    for sku in skus:
        for warehouse in ['burnaby', 'kentucky']:
            # Determine order timing
            result = determine_monthly_order_timing(
                sku['sku_id'], warehouse, sku['supplier'], order_month
            )

            # Special handling for Death Row SKUs
            if sku['status'] == 'Death Row' and result['decision'] != 'MUST_ORDER':
                result['decision'] = 'SKIP'
                result['urgency_level'] = 'skip'
                result['order_qty'] = 0

            # Upgrade A items from optional to should_order
            elif sku['abc_code'] == 'A' and result['urgency_level'] == 'optional':
                result['urgency_level'] = 'should_order'
                result['decision'] = 'SHOULD_ORDER'

            # Insert or update recommendation
            insert_query = """
                INSERT INTO supplier_order_confirmations (
                    sku_id, warehouse, suggested_qty, confirmed_qty, supplier,
                    current_inventory, pending_orders_raw, pending_orders_effective,
                    pending_breakdown, corrected_demand_monthly, safety_stock_qty,
                    reorder_point, order_month, days_in_month, lead_time_days_default,
                    coverage_months, urgency_level, overdue_pending_count,
                    stockout_risk_date
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s
                )
                ON DUPLICATE KEY UPDATE
                    suggested_qty = VALUES(suggested_qty),
                    confirmed_qty = VALUES(confirmed_qty),
                    current_inventory = VALUES(current_inventory),
                    pending_orders_raw = VALUES(pending_orders_raw),
                    pending_orders_effective = VALUES(pending_orders_effective),
                    pending_breakdown = VALUES(pending_breakdown),
                    corrected_demand_monthly = VALUES(corrected_demand_monthly),
                    safety_stock_qty = VALUES(safety_stock_qty),
                    reorder_point = VALUES(reorder_point),
                    days_in_month = VALUES(days_in_month),
                    lead_time_days_default = VALUES(lead_time_days_default),
                    coverage_months = VALUES(coverage_months),
                    urgency_level = VALUES(urgency_level),
                    overdue_pending_count = VALUES(overdue_pending_count),
                    stockout_risk_date = VALUES(stockout_risk_date),
                    updated_at = CURRENT_TIMESTAMP
            """

            execute_query(insert_query, (
                sku['sku_id'],
                warehouse,
                result['order_qty'],
                result['order_qty'],  # Initially same as suggested
                sku['supplier'],
                result['current_stock'],
                sum(p['quantity'] for p in result['pending_detail']),
                result['effective_pending'],
                json.dumps(result['pending_detail']),
                result['corrected_demand_monthly'],
                result['safety_stock_qty'],
                result['effective_pending'] + result['order_qty'],  # Simplified
                order_month,
                days_in_month,
                result['lead_time_days'],
                result['coverage_months'],
                result['urgency_level'],
                result['overdue_pending_count'],
                result['stockout_risk_date']
            ), fetch_one=False, fetch_all=False)

            # Update summary counts
            summary[result['urgency_level']] += 1
            summary['total_processed'] += 1

    return {
        'order_month': order_month,
        'total_processed': summary['total_processed'],
        'must_order_count': summary['must_order'],
        'should_order_count': summary['should_order'],
        'optional_count': summary['optional'],
        'skip_count': summary['skip']
    }
