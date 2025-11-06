"""
Supplier Performance Analysis Module

Retrieves and analyzes supplier performance metrics including lead times,
delivery reliability, and order history for a specific SKU and supplier.

This module supports V10.0 Phase 3 supplier performance visualization features.

Database Tables Used:
- supplier_lead_times: Pre-calculated lead time statistics
- supplier_shipments: Historical shipment data
- pending_inventory: Current pending orders
- skus: Supplier information
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal
from backend.database import execute_query


def get_supplier_performance(
    sku_id: str,
    warehouse: str
) -> Dict:
    """
    Get comprehensive supplier performance metrics for a SKU/warehouse combination.

    Retrieves:
    - Lead time statistics (average, median, P95, variability)
    - Recent shipment history (last 12 months)
    - Pending orders count and quantities
    - Delivery reliability metrics

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name ('burnaby' or 'kentucky')

    Returns:
        Dictionary containing:
        - supplier_name: Name of the supplier
        - lead_time_stats: Dict with avg, median, p95, min, max, std_dev
        - reliability_score: Supplier reliability score (0-100)
        - recent_shipments: List of recent shipments with lead times
        - pending_orders: List of current pending orders
        - on_time_delivery_rate: Percentage of on-time deliveries
        - total_shipments: Total number of shipments in history

    Raises:
        ValueError: If warehouse is invalid or SKU not found
    """

    # Validate warehouse parameter
    if warehouse not in ['burnaby', 'kentucky']:
        raise ValueError(f"Invalid warehouse: {warehouse}. Must be 'burnaby' or 'kentucky'")

    # Get SKU supplier information
    supplier_name = _get_sku_supplier(sku_id)

    if not supplier_name:
        return {
            'sku_id': sku_id,
            'warehouse': warehouse,
            'error': 'SKU not found or has no supplier assigned'
        }

    # Get lead time statistics
    lead_time_stats = _get_lead_time_statistics(supplier_name, warehouse)

    # Get recent shipments (last 12 months)
    recent_shipments = _get_recent_shipments(supplier_name, warehouse, months_back=12)

    # Get pending orders for this SKU
    pending_orders = _get_pending_orders(sku_id, warehouse, supplier_name)

    # Calculate on-time delivery rate from recent shipments
    on_time_rate = _calculate_on_time_delivery_rate(recent_shipments, lead_time_stats)

    return {
        'sku_id': sku_id,
        'warehouse': warehouse,
        'supplier_name': supplier_name,
        'lead_time_stats': lead_time_stats,
        'recent_shipments': recent_shipments,
        'pending_orders': pending_orders,
        'on_time_delivery_rate': on_time_rate,
        'total_shipments': len(recent_shipments),
        'reliability_score': lead_time_stats.get('reliability_score', 0)
    }


def _get_sku_supplier(sku_id: str) -> Optional[str]:
    """
    Get the supplier name for a SKU.

    Args:
        sku_id: SKU identifier

    Returns:
        Supplier name or None if not found
    """
    query = """
        SELECT supplier
        FROM skus
        WHERE sku_id = %s
    """

    result = execute_query(query, (sku_id,), fetch_one=True, fetch_all=False)

    if result:
        return result.get('supplier')
    return None


def _get_lead_time_statistics(supplier: str, warehouse: str) -> Dict:
    """
    Get lead time statistics from supplier_lead_times table, with fallback to
    on-the-fly calculation from supplier_shipments.

    Args:
        supplier: Supplier name
        warehouse: Warehouse destination

    Returns:
        Dictionary with lead time statistics:
        - avg_lead_time: Average lead time in days
        - median_lead_time: Median lead time
        - p95_lead_time: 95th percentile lead time
        - min_lead_time: Minimum observed lead time
        - max_lead_time: Maximum observed lead time
        - std_dev_lead_time: Standard deviation
        - coefficient_variation: CV for variability assessment
        - reliability_score: Overall reliability score (0-100)
        - shipment_count: Number of shipments used for calculation
        - data_source: 'pre_calculated' or 'real_time'
    """
    # Try pre-calculated stats first
    query = """
        SELECT
            avg_lead_time,
            median_lead_time,
            p95_lead_time,
            min_lead_time,
            max_lead_time,
            std_dev_lead_time,
            coefficient_variation,
            reliability_score,
            shipment_count,
            calculation_period,
            last_calculated
        FROM supplier_lead_times
        WHERE supplier = %s
          AND destination = %s
    """

    result = execute_query(
        query,
        (supplier, warehouse),
        fetch_one=True,
        fetch_all=False
    )

    if result and result.get('shipment_count', 0) > 0:
        return {
            'avg_lead_time': float(result.get('avg_lead_time', 0)) if result.get('avg_lead_time') else 0,
            'median_lead_time': float(result.get('median_lead_time', 0)) if result.get('median_lead_time') else 0,
            'p95_lead_time': float(result.get('p95_lead_time', 0)) if result.get('p95_lead_time') else 0,
            'min_lead_time': int(result.get('min_lead_time', 0)) if result.get('min_lead_time') else 0,
            'max_lead_time': int(result.get('max_lead_time', 0)) if result.get('max_lead_time') else 0,
            'std_dev_lead_time': float(result.get('std_dev_lead_time', 0)) if result.get('std_dev_lead_time') else 0,
            'coefficient_variation': float(result.get('coefficient_variation', 0)) if result.get('coefficient_variation') else 0,
            'reliability_score': int(result.get('reliability_score', 0)) if result.get('reliability_score') else 0,
            'shipment_count': int(result.get('shipment_count', 0)) if result.get('shipment_count') else 0,
            'calculation_period': result.get('calculation_period', 'unknown'),
            'last_calculated': result['last_calculated'].strftime('%Y-%m-%d') if result.get('last_calculated') else None,
            'data_source': 'pre_calculated'
        }

    # Fallback: Calculate on-the-fly from supplier_shipments (like supplier_analytics.py does)
    return _calculate_lead_time_stats_from_shipments(supplier, warehouse)


def _calculate_lead_time_stats_from_shipments(supplier: str, warehouse: str) -> Dict:
    """
    Calculate lead time statistics on-the-fly from supplier_shipments table.

    This is a fallback when supplier_lead_times table is empty.
    Uses the same approach as supplier_analytics.py for consistency.

    Args:
        supplier: Supplier name
        warehouse: Warehouse destination

    Returns:
        Dictionary with calculated lead time statistics
    """
    query = """
        SELECT
            AVG(actual_lead_time) as avg_lead_time,
            STDDEV(actual_lead_time) as std_dev_lead_time,
            MIN(actual_lead_time) as min_lead_time,
            MAX(actual_lead_time) as max_lead_time,
            COUNT(*) as shipment_count
        FROM supplier_shipments
        WHERE supplier = %s
          AND destination = %s
          AND actual_lead_time IS NOT NULL
          AND order_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
    """

    result = execute_query(
        query,
        (supplier, warehouse),
        fetch_one=True,
        fetch_all=False
    )

    if result and result.get('shipment_count', 0) > 0:
        avg = float(result.get('avg_lead_time', 0)) if result.get('avg_lead_time') else 0
        std_dev = float(result.get('std_dev_lead_time', 0)) if result.get('std_dev_lead_time') else 0

        # Calculate coefficient of variation
        cv = (std_dev / avg) if avg > 0 else 0

        # Calculate reliability score (100 = perfect consistency)
        # Score decreases with higher CV
        reliability = max(0, min(100, int(100 - (cv * 100))))

        # Estimate P95 using normal distribution approximation (avg + 1.645 * std_dev)
        p95 = avg + (1.645 * std_dev) if std_dev > 0 else avg

        # Estimate median (for normal distribution, median ≈ mean)
        median = avg

        return {
            'avg_lead_time': round(avg, 1),
            'median_lead_time': round(median, 1),
            'p95_lead_time': round(p95, 1),
            'min_lead_time': int(result.get('min_lead_time', 0)),
            'max_lead_time': int(result.get('max_lead_time', 0)),
            'std_dev_lead_time': round(std_dev, 1),
            'coefficient_variation': round(cv, 3),
            'reliability_score': reliability,
            'shipment_count': int(result.get('shipment_count', 0)),
            'calculation_period': '12_months',
            'last_calculated': datetime.now().strftime('%Y-%m-%d'),
            'data_source': 'real_time'
        }

    # No shipment data available at all
    return {
        'avg_lead_time': 0,
        'median_lead_time': 0,
        'p95_lead_time': 0,
        'min_lead_time': 0,
        'max_lead_time': 0,
        'std_dev_lead_time': 0,
        'coefficient_variation': 0,
        'reliability_score': 0,
        'shipment_count': 0,
        'calculation_period': 'no_data',
        'last_calculated': None,
        'data_source': 'none'
    }


def _get_recent_shipments(supplier: str, warehouse: str, months_back: int = 12) -> List[Dict]:
    """
    Get recent shipment history for a supplier/warehouse combination.

    Args:
        supplier: Supplier name
        warehouse: Warehouse destination
        months_back: How many months of history to retrieve

    Returns:
        List of shipment records with:
        - po_number: Purchase order number
        - order_date: Date order was placed
        - received_date: Date order was received
        - actual_lead_time: Calculated lead time in days
        - was_partial: Whether delivery was partial
        - notes: Any notes about the shipment
    """
    cutoff_date = datetime.now() - timedelta(days=months_back * 30)

    query = """
        SELECT
            po_number,
            order_date,
            received_date,
            actual_lead_time,
            was_partial,
            notes
        FROM supplier_shipments
        WHERE supplier = %s
          AND destination = %s
          AND order_date >= %s
        ORDER BY received_date DESC
        LIMIT 50
    """

    results = execute_query(
        query,
        (supplier, warehouse, cutoff_date.strftime('%Y-%m-%d')),
        fetch_one=False,
        fetch_all=True
    )

    shipments = []
    if results:
        for row in results:
            shipments.append({
                'po_number': row['po_number'],
                'order_date': row['order_date'].strftime('%Y-%m-%d') if hasattr(row['order_date'], 'strftime') else str(row['order_date']),
                'received_date': row['received_date'].strftime('%Y-%m-%d') if hasattr(row['received_date'], 'strftime') else str(row['received_date']),
                'actual_lead_time': int(row.get('actual_lead_time', 0)),
                'was_partial': bool(row.get('was_partial', False)),
                'notes': row.get('notes', '')
            })

    return shipments


def _get_pending_orders(sku_id: str, warehouse: str, supplier: str) -> List[Dict]:
    """
    Get current pending orders for a SKU/warehouse/supplier combination.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse destination
        supplier: Supplier name

    Returns:
        List of pending order records with:
        - quantity: Order quantity
        - order_date: Date order was placed
        - expected_arrival: Expected arrival date
        - lead_time_days: Estimated lead time
        - status: Current order status
        - days_until_arrival: Days remaining until expected arrival
    """
    query = """
        SELECT
            quantity,
            order_date,
            expected_arrival,
            lead_time_days,
            status,
            CASE
                WHEN expected_arrival IS NOT NULL THEN
                    DATEDIFF(expected_arrival, CURDATE())
                ELSE
                    DATEDIFF(DATE_ADD(order_date, INTERVAL lead_time_days DAY), CURDATE())
            END as days_until_arrival
        FROM pending_inventory
        WHERE sku_id = %s
          AND destination = %s
          AND supplier = %s
          AND status NOT IN ('received', 'cancelled')
        ORDER BY
            CASE
                WHEN expected_arrival IS NOT NULL THEN expected_arrival
                ELSE DATE_ADD(order_date, INTERVAL lead_time_days DAY)
            END ASC
    """

    results = execute_query(
        query,
        (sku_id, warehouse, supplier),
        fetch_one=False,
        fetch_all=True
    )

    pending = []
    if results:
        for row in results:
            pending.append({
                'quantity': int(row['quantity']),
                'order_date': row['order_date'].strftime('%Y-%m-%d') if hasattr(row['order_date'], 'strftime') else str(row['order_date']),
                'expected_arrival': row['expected_arrival'].strftime('%Y-%m-%d') if row.get('expected_arrival') and hasattr(row['expected_arrival'], 'strftime') else 'Estimated',
                'lead_time_days': int(row.get('lead_time_days', 0)),
                'status': row.get('status', 'unknown'),
                'days_until_arrival': int(row.get('days_until_arrival', 0)) if row.get('days_until_arrival') is not None else 0
            })

    return pending


def _calculate_on_time_delivery_rate(shipments: List[Dict], lead_time_stats: Dict) -> float:
    """
    Calculate on-time delivery rate from recent shipments.

    A shipment is considered "on-time" if actual_lead_time <= avg_lead_time * 1.1
    (10% tolerance above average)

    Args:
        shipments: List of shipment records
        lead_time_stats: Dictionary with lead time statistics

    Returns:
        On-time delivery rate as percentage (0-100)
    """
    if not shipments or not lead_time_stats.get('avg_lead_time'):
        return 0.0

    avg_lead_time = lead_time_stats['avg_lead_time']
    on_time_threshold = avg_lead_time * 1.1  # 10% tolerance

    on_time_count = 0
    total_count = len(shipments)

    for shipment in shipments:
        if shipment['actual_lead_time'] <= on_time_threshold:
            on_time_count += 1

    if total_count > 0:
        return round((on_time_count / total_count) * 100, 1)

    return 0.0
