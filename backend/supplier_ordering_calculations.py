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
import time
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
            COALESCE(expected_arrival, DATE_ADD(order_date, INTERVAL lead_time_days DAY)) as expected_arrival,
            lead_time_days,
            status,
            is_estimated,
            DATEDIFF(COALESCE(expected_arrival, DATE_ADD(order_date, INTERVAL lead_time_days DAY)), CURDATE()) as days_until_arrival,
            CASE
                WHEN COALESCE(expected_arrival, DATE_ADD(order_date, INTERVAL lead_time_days DAY)) < CURDATE() AND status != 'received' THEN 1
                ELSE 0
            END as is_late,
            CASE WHEN is_estimated = 1 THEN 0.65 ELSE 0.85 END as base_confidence
        FROM pending_inventory
        WHERE sku_id = %s
          AND destination = %s
          AND order_type = 'supplier'
          AND status IN ('ordered', 'shipped')
        ORDER BY COALESCE(expected_arrival, DATE_ADD(order_date, INTERVAL lead_time_days DAY))
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
        # Apply 80% time-based confidence for overdue orders, combined with base confidence
        time_confidence = 0.8
        base_conf = float(order.get('base_confidence', 0.85))
        confidence = time_confidence * base_conf
        effective_qty = order['quantity'] * confidence
        effective_pending += effective_qty

        pending_detail.append({
            'order_id': order['id'],
            'quantity': order['quantity'],
            'confidence': round(confidence, 2),
            'category': 'overdue',
            'expected_arrival': str(order['expected_arrival']),
            'reason': f"Overdue by {-order['days_until_arrival']} days (estimated={order.get('is_estimated', 0)})"
        })

    # Process imminent orders (arriving within review period)
    for order in pending['imminent']:
        # 100% time-based confidence for imminent orders, combined with base confidence
        time_confidence = 1.0
        base_conf = float(order.get('base_confidence', 0.85))
        confidence = time_confidence * base_conf
        effective_qty = order['quantity'] * confidence
        effective_pending += effective_qty

        pending_detail.append({
            'order_id': order['id'],
            'quantity': order['quantity'],
            'confidence': round(confidence, 2),
            'category': 'imminent',
            'expected_arrival': str(order['expected_arrival']),
            'reason': f"Arriving in {order['days_until_arrival']} days (estimated={order.get('is_estimated', 0)})"
        })

    # Process covered orders (arriving during lead time)
    for order in pending['covered']:
        # Confidence based on supplier reliability, time distance, and base confidence
        time_factor = 1 - (order['days_until_arrival'] / planning_horizon) * 0.2
        base_conf = float(order.get('base_confidence', 0.85))
        confidence = reliability_score * time_factor * base_conf
        effective_qty = order['quantity'] * confidence
        effective_pending += effective_qty

        pending_detail.append({
            'order_id': order['id'],
            'quantity': order['quantity'],
            'confidence': round(confidence, 2),
            'category': 'covered',
            'expected_arrival': str(order['expected_arrival']),
            'reason': f"Lead time coverage, {int(reliability_score*100)}% reliability (estimated={order.get('is_estimated', 0)})"
        })

    # Calculate future ignored quantity
    future_ignored = sum(o['quantity'] for o in pending['future'])

    return {
        'total_effective': round(effective_pending),
        'detail': pending_detail,
        'overdue_count': len(pending['overdue']),
        'future_ignored': future_ignored
    }


def get_forecast_demand(sku_id: str, warehouse: str) -> Optional[Dict]:
    """
    Get forecast-based demand with learning adjustments and confidence-based blending.

    Implements tiered confidence approach:
    - < 0.5: Use historical corrected_demand only
    - 0.5-0.75: Blend forecast with historical (weighted by confidence)
    - > 0.75: Use forecast only

    Uses latest completed forecast run and applies learning adjustments where applied=TRUE.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse code (burnaby or kentucky)

    Returns:
        {
            'demand_monthly': float (blended or pure forecast),
            'demand_source': str ('forecast', 'blended', or 'historical'),
            'forecast_confidence': float (ABC/XYZ-based: 0.40-0.90),
            'learning_applied': bool,
            'learning_adjustment': float,
            'forecast_run_id': int,
            'blend_weight': float (if blended, otherwise None)
        } or None if no forecast available
    """
    # Query latest completed forecast with learning adjustments
    forecast_query = """
        SELECT
            fd.sku_id,
            fd.warehouse,
            fd.forecast_run_id,
            fd.avg_monthly_qty,
            fd.method_used,
            fd.confidence_score,
            fr.forecast_date,
            COALESCE(SUM(CASE WHEN fla.applied = 1 THEN fla.adjustment_magnitude ELSE 0 END), 0) as total_learning_adjustment,
            CASE WHEN SUM(CASE WHEN fla.applied = 1 THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END as has_learning
        FROM forecast_details fd
        JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
        LEFT JOIN forecast_learning_adjustments fla ON fd.sku_id = fla.sku_id AND fla.applied = 1
        WHERE fd.sku_id = %s
            AND fd.warehouse = %s
            AND fd.forecast_run_id = (
                SELECT MAX(forecast_run_id)
                FROM forecast_details
                WHERE sku_id = %s
                    AND warehouse = %s
                    AND forecast_run_id IN (
                        SELECT id FROM forecast_runs WHERE status = 'completed'
                    )
            )
        GROUP BY fd.sku_id, fd.warehouse, fd.forecast_run_id, fd.avg_monthly_qty,
                 fd.method_used, fd.confidence_score, fr.forecast_date
        LIMIT 1
    """

    forecast_result = execute_query(
        forecast_query,
        (sku_id, warehouse, sku_id, warehouse),
        fetch_one=True,
        fetch_all=False
    )

    # If no forecast available, return None (will trigger historical fallback)
    if not forecast_result or not forecast_result.get('avg_monthly_qty'):
        return None

    # Extract forecast data
    forecast_avg_monthly = float(forecast_result.get('avg_monthly_qty'))
    confidence_score = float(forecast_result.get('confidence_score') or 0.75)
    learning_adjustment = float(forecast_result.get('total_learning_adjustment') or 0)
    has_learning = bool(forecast_result.get('has_learning'))

    # Apply learning adjustments to forecast
    if has_learning and learning_adjustment != 0:
        forecast_avg_monthly = forecast_avg_monthly * (1 + learning_adjustment)

    # Get historical corrected_demand for blending (if needed)
    historical_query = """
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
    historical_result = execute_query(
        historical_query,
        (warehouse, warehouse, sku_id),
        fetch_one=True,
        fetch_all=False
    )
    historical_corrected = float(historical_result.get('corrected_demand')) if historical_result and historical_result.get('corrected_demand') else 0

    # Apply confidence-based blending logic
    if confidence_score < 0.5:
        # Very low confidence - use historical only
        final_demand = historical_corrected
        demand_source = 'historical'
        blend_weight = None

    elif confidence_score < 0.75:
        # Moderate confidence - blend forecast with historical (weighted by confidence)
        if historical_corrected > 0:
            blend_weight = confidence_score
            final_demand = (forecast_avg_monthly * blend_weight) + (historical_corrected * (1 - blend_weight))
            demand_source = 'blended'
        else:
            # No historical data - use forecast only
            final_demand = forecast_avg_monthly
            demand_source = 'forecast'
            blend_weight = None

    else:
        # High confidence - trust forecast
        final_demand = forecast_avg_monthly
        demand_source = 'forecast'
        blend_weight = None

    return {
        'demand_monthly': round(final_demand, 2),
        'demand_source': demand_source,
        'forecast_confidence': round(confidence_score, 2),
        'learning_applied': has_learning,
        'learning_adjustment': round(learning_adjustment, 4),
        'forecast_run_id': forecast_result.get('forecast_run_id'),
        'forecast_method': forecast_result.get('method_used'),
        'blend_weight': round(blend_weight, 2) if blend_weight is not None else None
    }


def get_seasonal_adjustment_factor(sku_id: str, warehouse: str, order_month: int) -> Dict:
    """
    Get seasonal pattern adjustment for safety stock.
    Uses dynamic multiplier based on pattern strength (Claude KB recommendation).

    Pattern Reliability Criteria (ALL required):
    - pattern_strength > 0.3 (from seasonal_factors.py:50)
    - overall_confidence > 0.6 (from seasonal_analysis.py:59)
    - statistical_significance = TRUE (p < 0.15)

    Dynamic Multipliers:
    - Strong pattern (strength >= 0.5): 1.3x
    - Moderate pattern (strength >= 0.3): 1.2x
    - Weak pattern (strength < 0.3): 1.15x (but filtered out by min threshold)

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse code (burnaby or kentucky)
        order_month: Month number (1-12) for which order is being placed

    Returns:
        {
            'pattern_type': str or None,
            'adjustment_factor': float (1.0 if no adjustment, 1.15-1.3 if adjusted),
            'approaching_peak': bool,
            'pattern_strength': float,
            'overall_confidence': float,
            'statistical_significance': bool,
            'peak_months': str or None
        }
    """
    # Query seasonal pattern summary
    pattern_query = """
        SELECT
            pattern_type,
            pattern_strength,
            overall_confidence,
            statistical_significance,
            peak_months,
            low_months
        FROM seasonal_patterns_summary
        WHERE sku_id = %s
            AND warehouse = %s
        LIMIT 1
    """

    pattern_result = execute_query(
        pattern_query,
        (sku_id, warehouse),
        fetch_one=True,
        fetch_all=False
    )

    # Default response if no pattern found
    if not pattern_result:
        return {
            'pattern_type': None,
            'adjustment_factor': 1.0,
            'approaching_peak': False,
            'pattern_strength': 0.0,
            'overall_confidence': 0.0,
            'statistical_significance': False,
            'peak_months': None
        }

    # Extract pattern data
    pattern_type = pattern_result.get('pattern_type')
    pattern_strength = float(pattern_result.get('pattern_strength') or 0)
    overall_confidence = float(pattern_result.get('overall_confidence') or 0)
    statistical_significance = bool(pattern_result.get('statistical_significance'))
    peak_months_str = pattern_result.get('peak_months')

    # Check if approaching peak (current month or next month is in peak_months)
    approaching_peak = False
    if peak_months_str:
        try:
            peak_months = [int(m.strip()) for m in peak_months_str.split(',') if m.strip()]
            next_month = (order_month % 12) + 1  # Wrap December to January
            if order_month in peak_months or next_month in peak_months:
                approaching_peak = True
        except (ValueError, AttributeError):
            peak_months = []

    # Validate ALL three reliability criteria
    meets_strength_threshold = pattern_strength > 0.3
    meets_confidence_threshold = overall_confidence > 0.6
    has_statistical_significance = statistical_significance

    # Only apply adjustment if ALL criteria met and approaching peak
    if (approaching_peak and
        meets_strength_threshold and
        meets_confidence_threshold and
        has_statistical_significance):

        # Dynamic multiplier based on pattern strength
        if pattern_strength >= 0.5:
            adjustment_factor = 1.3  # Strong seasonal pattern
        elif pattern_strength >= 0.3:
            adjustment_factor = 1.2  # Moderate seasonal pattern
        else:
            adjustment_factor = 1.15  # Weak but detectable (shouldn't reach here due to threshold)
    else:
        adjustment_factor = 1.0  # No adjustment

    return {
        'pattern_type': pattern_type,
        'adjustment_factor': adjustment_factor,
        'approaching_peak': approaching_peak,
        'pattern_strength': pattern_strength,
        'overall_confidence': overall_confidence,
        'statistical_significance': statistical_significance,
        'peak_months': peak_months_str
    }


def calculate_safety_stock_monthly(
    sku_id: str,
    warehouse: str,
    daily_demand: float,
    lead_time_days: int,
    order_month: str
) -> int:
    """
    Calculate safety stock for monthly ordering cycle.

    Uses enhanced formula accounting for:
    - Monthly review period (30 days vs daily/weekly)
    - Demand variability (coefficient of variation)
    - Lead time variability
    - ABC-XYZ service level requirements
    - Seasonal patterns with dynamic multipliers (Phase 2 Intelligence Layer)

    Formula: Z * sqrt((demand_std^2 * period) + (demand^2 * lt_cv^2 * period))
    Then applies ABC buffers and seasonal adjustments.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse code
        daily_demand: Average daily demand
        lead_time_days: P95 lead time in days
        order_month: Month in YYYY-MM format for seasonal pattern detection

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

    # Apply seasonal adjustment if approaching peak (Phase 2 Intelligence Layer)
    # Extract month number from order_month (YYYY-MM format)
    try:
        year, month_str = order_month.split('-')
        month_num = int(month_str)
    except (ValueError, AttributeError):
        month_num = datetime.now().month  # Fallback to current month

    seasonal = get_seasonal_adjustment_factor(sku_id, warehouse, month_num)

    # Apply dynamic multiplier if ALL reliability criteria met and approaching peak
    if (seasonal['approaching_peak'] and
        seasonal['pattern_strength'] > 0.3 and
        seasonal['overall_confidence'] > 0.6 and
        seasonal['statistical_significance']):

        # Dynamic multiplier based on pattern strength
        safety_stock *= seasonal['adjustment_factor']

    return round(safety_stock)


def check_stockout_urgency(sku_id: str, order_month: int) -> Dict:
    """
    Check if stockout patterns warrant urgency escalation.
    Uses conservative thresholds from Claude KB recommendations.

    Thresholds:
    - Chronic: frequency_score > 70 AND confidence_level = 'high'
    - Seasonal: frequency_score > 50 AND approaching season AND confidence >= 'medium'

    Args:
        sku_id: SKU identifier
        order_month: Month number (1-12) for which order is being placed

    Returns:
        {
            'has_chronic_pattern': bool,
            'has_seasonal_pattern': bool,
            'frequency_score': float (0-100),
            'confidence_level': str,
            'escalate_urgency': bool (for chronic),
            'increase_buffer': bool (for seasonal),
            'pattern_details': str
        }
    """
    # Query stockout patterns
    pattern_query = """
        SELECT
            pattern_type,
            pattern_value,
            frequency_score,
            confidence_level,
            last_detected
        FROM stockout_patterns
        WHERE sku_id = %s
        ORDER BY frequency_score DESC
        LIMIT 10
    """

    pattern_results = execute_query(
        pattern_query,
        (sku_id,),
        fetch_one=False,
        fetch_all=True
    ) or []

    # Initialize response
    has_chronic = False
    has_seasonal = False
    max_frequency = 0.0
    confidence = 'low'
    pattern_details = []
    escalate_urgency = False
    increase_buffer = False

    for pattern in pattern_results:
        pattern_type = pattern.get('pattern_type')
        pattern_value = pattern.get('pattern_value')
        freq_score = float(pattern.get('frequency_score') or 0)
        conf_level = pattern.get('confidence_level') or 'low'

        max_frequency = max(max_frequency, freq_score)

        # Check for chronic pattern
        if pattern_type == 'chronic':
            has_chronic = True
            confidence = conf_level
            pattern_details.append(f"Chronic stockouts (freq={freq_score:.1f}, conf={conf_level})")

            # Escalate if frequency > 70 AND high confidence
            if freq_score > 70 and conf_level == 'high':
                escalate_urgency = True

        # Check for seasonal pattern
        elif pattern_type == 'seasonal' and pattern_value:
            has_seasonal = True

            # Parse pattern_value (e.g., "april,may,june" or "4,5,6")
            try:
                # Try numeric month parsing first
                seasonal_months = [int(m.strip()) for m in pattern_value.split(',') if m.strip().isdigit()]

                # If no numeric months, try month name parsing
                if not seasonal_months:
                    month_names = {'january': 1, 'february': 2, 'march': 3, 'april': 4,
                                   'may': 5, 'june': 6, 'july': 7, 'august': 8,
                                   'september': 9, 'october': 10, 'november': 11, 'december': 12}
                    seasonal_months = [month_names.get(m.strip().lower()) for m in pattern_value.split(',')]
                    seasonal_months = [m for m in seasonal_months if m is not None]

                # Check if approaching seasonal stockout period
                next_month = (order_month % 12) + 1
                is_approaching = order_month in seasonal_months or next_month in seasonal_months

                if is_approaching and freq_score > 50 and conf_level in ['medium', 'high']:
                    increase_buffer = True
                    pattern_details.append(f"Seasonal stockouts approaching (months={pattern_value}, freq={freq_score:.1f})")

            except (ValueError, AttributeError):
                pass

    # Combine pattern details
    combined_details = "; ".join(pattern_details) if pattern_details else "No significant stockout patterns"

    return {
        'has_chronic_pattern': has_chronic,
        'has_seasonal_pattern': has_seasonal,
        'frequency_score': round(max_frequency, 2),
        'confidence_level': confidence,
        'escalate_urgency': escalate_urgency,
        'increase_buffer': increase_buffer,
        'pattern_details': combined_details
    }


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

    # Get monthly demand - try forecast first, fallback to historical (Phase 2 Intelligence Layer)
    forecast_result = get_forecast_demand(sku_id, warehouse)

    if forecast_result:
        # Forecast available - use blended or pure based on confidence
        demand_monthly = float(forecast_result['demand_monthly'])
        demand_source = forecast_result['demand_source']  # 'forecast', 'blended', or 'historical'
        confidence_score = forecast_result['forecast_confidence']
        blend_weight = forecast_result.get('blend_weight')
        learning_applied = forecast_result['learning_applied']
        forecast_run_id = forecast_result.get('forecast_run_id')
        forecast_method = forecast_result.get('forecast_method')
    else:
        # No forecast available - fallback to historical corrected_demand
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
        demand_monthly = float(demand_result.get('corrected_demand')) if demand_result and demand_result.get('corrected_demand') else 0
        demand_source = 'historical'
        confidence_score = 0.75  # Default confidence for historical
        blend_weight = None
        learning_applied = False
        forecast_run_id = None
        forecast_method = None

    corrected_demand_monthly = demand_monthly  # Keep this for backward compatibility

    # Get actual days in this month
    year, month = order_month.split('-')
    days_in_month = calendar.monthrange(int(year), int(month))[1]

    # Calculate daily demand using actual days
    daily_demand = demand_monthly / days_in_month if days_in_month > 0 else 0

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

    # Check stockout patterns for urgency escalation (Phase 2 Intelligence Layer)
    try:
        year, month_str = order_month.split('-')
        month_num = int(month_str)
    except (ValueError, AttributeError):
        month_num = datetime.now().month

    stockout_check = check_stockout_urgency(sku_id, month_num)

    # Escalate urgency for chronic stockout patterns (frequency > 70, high confidence)
    if stockout_check['escalate_urgency']:
        if urgency == 'optional':
            urgency = 'should_order'
            decision = 'SHOULD_ORDER'
        elif urgency == 'should_order':
            urgency = 'must_order'
            decision = 'MUST_ORDER'

    # Calculate order quantity if not skipping
    order_qty = 0
    stockout_risk_date = None
    coverage_months = days_of_coverage / 30 if daily_demand > 0 else None

    if decision != 'SKIP':
        # Target coverage: lead time + 60 days (2 months)
        target_coverage_days = lead_time_days + 60
        target_inventory = daily_demand * target_coverage_days

        # Add safety stock (with seasonal adjustment if applicable)
        safety_stock = calculate_safety_stock_monthly(sku_id, warehouse, daily_demand, lead_time_days, order_month)
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
        'safety_stock_qty': calculate_safety_stock_monthly(sku_id, warehouse, daily_demand, lead_time_days, order_month),
        # Phase 2 Intelligence Layer metadata
        'forecast_demand_monthly': demand_monthly if demand_source in ['forecast', 'blended'] else None,
        'demand_source': demand_source,
        'forecast_confidence_score': confidence_score,
        'blend_weight': blend_weight,
        'learning_adjustment_applied': learning_applied
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

            # Small delay to prevent socket exhaustion on Windows (WinError 10048)
            time.sleep(0.001)  # 1ms delay per SKU-warehouse combination

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
                    stockout_risk_date,
                    forecast_demand_monthly, demand_source, forecast_confidence_score,
                    blend_weight, learning_adjustment_applied
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s,
                    %s, %s, %s,
                    %s, %s
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
                    forecast_demand_monthly = VALUES(forecast_demand_monthly),
                    demand_source = VALUES(demand_source),
                    forecast_confidence_score = VALUES(forecast_confidence_score),
                    blend_weight = VALUES(blend_weight),
                    learning_adjustment_applied = VALUES(learning_adjustment_applied),
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
                result['stockout_risk_date'],
                result.get('forecast_demand_monthly'),
                result.get('demand_source'),
                result.get('forecast_confidence_score'),
                result.get('blend_weight'),
                result.get('learning_adjustment_applied', False)
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
