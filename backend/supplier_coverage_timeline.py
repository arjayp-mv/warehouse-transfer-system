"""
Supplier Order Coverage Timeline Module

Calculates inventory coverage timeline to predict when SKUs will run out of stock.
Uses current inventory, pending orders, and forecast demand to project future
inventory levels and identify potential stockout dates.

This module supports V10.0 Phase 3 visualization features.

Database Schema Notes:
- inventory_current has {warehouse}_qty columns (burnaby_qty, kentucky_qty)
- pending_inventory has destination column (not warehouse)
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from backend.database import execute_query


def calculate_coverage_timeline(
    sku_id: str,
    warehouse: str,
    projection_days: int = 180
) -> Dict:
    """
    Calculate inventory coverage timeline for a SKU/warehouse combination.

    Projects inventory levels day-by-day for the next N days, accounting for:
    - Current inventory
    - Pending orders (with arrival dates)
    - Forecast demand (converted from monthly to daily)
    - Actual daily sales for recent history

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name ('burnaby' or 'kentucky')
        projection_days: Number of days to project forward (default: 180 = 6 months)

    Returns:
        Dictionary containing:
        - timeline: List of daily inventory levels with dates
        - stockout_date: Predicted stockout date (or None if covered)
        - coverage_days: Number of days until stockout
        - current_inventory: Starting inventory level
        - pending_arrivals: List of pending orders with dates
        - daily_demand: Average daily demand used for projection
        - forecast_source: Where demand came from (forecast/historical)

    Raises:
        ValueError: If warehouse is invalid or SKU not found
    """

    # Validate warehouse parameter
    if warehouse not in ['burnaby', 'kentucky']:
        raise ValueError(f"Invalid warehouse: {warehouse}. Must be 'burnaby' or 'kentucky'")

    # Get current inventory
    current_inventory = _get_current_inventory(sku_id, warehouse)

    # Get pending orders with arrival dates
    pending_arrivals = _get_pending_arrivals(sku_id, warehouse, projection_days)

    # Get daily demand from forecast or historical data
    daily_demand, forecast_source = _get_daily_demand(sku_id, warehouse)

    # Build day-by-day timeline
    timeline = _build_timeline(
        starting_inventory=current_inventory,
        pending_arrivals=pending_arrivals,
        daily_demand=daily_demand,
        projection_days=projection_days
    )

    # Find stockout date
    stockout_date, coverage_days = _find_stockout_date(timeline)

    return {
        'sku_id': sku_id,
        'warehouse': warehouse,
        'timeline': timeline,
        'stockout_date': stockout_date,
        'coverage_days': coverage_days,
        'current_inventory': current_inventory,
        'pending_arrivals': pending_arrivals,
        'daily_demand': round(daily_demand, 2),
        'forecast_source': forecast_source,
        'projection_start_date': datetime.now().strftime('%Y-%m-%d'),
        'projection_end_date': (datetime.now() + timedelta(days=projection_days)).strftime('%Y-%m-%d')
    }


def _get_current_inventory(sku_id: str, warehouse: str) -> int:
    """
    Get current inventory quantity for SKU/warehouse.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name

    Returns:
        Current inventory quantity (0 if not found)
    """
    # inventory_current table has separate columns for each warehouse
    col_name = f"{warehouse}_qty"

    query = f"""
        SELECT {col_name} as qty
        FROM inventory_current
        WHERE sku_id = %s
    """

    result = execute_query(query, (sku_id,), fetch_one=True, fetch_all=False)

    if result:
        return int(result.get('qty', 0))
    return 0


def _get_pending_arrivals(sku_id: str, warehouse: str, days_ahead: int) -> List[Dict]:
    """
    Get pending inventory arrivals within projection window.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name
        days_ahead: Number of days to look ahead

    Returns:
        List of pending arrivals with format:
        [
            {'arrival_date': '2025-11-15', 'quantity': 500, 'supplier': 'Yuasa'},
            ...
        ]
    """
    end_date = datetime.now() + timedelta(days=days_ahead)

    query = """
        SELECT
            expected_arrival as arrival_date,
            quantity,
            supplier
        FROM pending_inventory
        WHERE sku_id = %s
          AND destination = %s
          AND expected_arrival <= %s
          AND quantity > 0
          AND status NOT IN ('cancelled', 'received')
        ORDER BY expected_arrival ASC
    """

    results = execute_query(
        query,
        (sku_id, warehouse, end_date.strftime('%Y-%m-%d')),
        fetch_one=False,
        fetch_all=True
    )

    arrivals = []
    if results:
        for row in results:
            arrivals.append({
                'arrival_date': row['arrival_date'].strftime('%Y-%m-%d') if hasattr(row['arrival_date'], 'strftime') else str(row['arrival_date']),
                'quantity': int(row['quantity']),
                'supplier': row.get('supplier', 'Unknown')
            })

    return arrivals


def _get_daily_demand(sku_id: str, warehouse: str) -> Tuple[float, str]:
    """
    Get average daily demand from forecast or historical data.

    Prioritizes forecast data over historical, falls back to monthly sales.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse name

    Returns:
        Tuple of (daily_demand, source_description)
        Example: (12.5, 'forecast (confidence: 0.85)')
    """

    # Try to get forecast demand (most recent completed forecast)
    forecast_query = """
        SELECT
            fd.avg_monthly_qty,
            fd.confidence_score,
            fr.forecast_name
        FROM forecast_details fd
        JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
        WHERE fd.sku_id = %s
          AND fd.warehouse = %s
          AND fr.status = 'completed'
        ORDER BY fr.forecast_date DESC
        LIMIT 1
    """

    forecast = execute_query(
        forecast_query,
        (sku_id, warehouse),
        fetch_one=True,
        fetch_all=False
    )

    if forecast and forecast.get('avg_monthly_qty'):
        monthly_demand = float(forecast['avg_monthly_qty'])
        daily_demand = monthly_demand / 30.0
        confidence = float(forecast.get('confidence_score', 0.75))
        forecast_name = forecast.get('forecast_name', 'Unknown')

        source = f"forecast (confidence: {confidence:.2f}, {forecast_name})"
        return daily_demand, source

    # Fallback to historical corrected demand
    historical_query = """
        SELECT corrected_demand_burnaby, corrected_demand_kentucky
        FROM monthly_sales
        WHERE sku_id = %s
        ORDER BY year_month DESC
        LIMIT 3
    """

    historical = execute_query(
        historical_query,
        (sku_id,),
        fetch_one=False,
        fetch_all=True
    )

    if historical:
        # Use warehouse-specific column
        col_name = f'corrected_demand_{warehouse}'
        demands = [float(row.get(col_name, 0)) for row in historical if row.get(col_name)]

        if demands:
            avg_monthly = sum(demands) / len(demands)
            daily_demand = avg_monthly / 30.0
            source = f"historical (3-month avg)"
            return daily_demand, source

    # Last resort: use 0 demand with warning
    return 0.0, "no data available (using 0)"


def _build_timeline(
    starting_inventory: int,
    pending_arrivals: List[Dict],
    daily_demand: float,
    projection_days: int
) -> List[Dict]:
    """
    Build day-by-day inventory timeline projection.

    Args:
        starting_inventory: Current inventory level
        pending_arrivals: List of pending orders with arrival dates
        daily_demand: Average daily demand (units per day)
        projection_days: Number of days to project

    Returns:
        List of daily inventory records:
        [
            {
                'date': '2025-11-02',
                'inventory': 450,
                'demand': 12.5,
                'arrivals': 0,
                'days_coverage': 36
            },
            ...
        ]
    """

    # Create lookup for pending arrivals by date
    arrivals_by_date = {}
    for arrival in pending_arrivals:
        date_str = arrival['arrival_date']
        arrivals_by_date[date_str] = arrivals_by_date.get(date_str, 0) + arrival['quantity']

    # Build timeline day by day
    timeline = []
    current_inventory = float(starting_inventory)
    current_date = datetime.now()

    for day in range(projection_days + 1):
        date_str = current_date.strftime('%Y-%m-%d')

        # Check for arrivals on this date
        arrivals_today = arrivals_by_date.get(date_str, 0)
        current_inventory += arrivals_today

        # Calculate days of coverage remaining at this inventory level
        days_coverage = int(current_inventory / daily_demand) if daily_demand > 0 else 999

        # Record the day
        timeline.append({
            'date': date_str,
            'inventory': max(0, round(current_inventory, 1)),
            'demand': round(daily_demand, 2),
            'arrivals': arrivals_today,
            'days_coverage': days_coverage
        })

        # Subtract daily demand
        current_inventory -= daily_demand

        # Stop if we hit zero and no more arrivals coming
        if current_inventory <= 0 and day < projection_days:
            # Check if any arrivals are coming after this date
            future_arrivals = any(
                datetime.strptime(arrival['arrival_date'], '%Y-%m-%d') > current_date
                for arrival in pending_arrivals
            )
            if not future_arrivals:
                break

        # Move to next day
        current_date += timedelta(days=1)

    return timeline


def _find_stockout_date(timeline: List[Dict]) -> Tuple[Optional[str], Optional[int]]:
    """
    Find the date when inventory hits zero (stockout date).

    Args:
        timeline: List of daily inventory records

    Returns:
        Tuple of (stockout_date, coverage_days)
        - stockout_date: ISO date string when stockout occurs (or None if covered)
        - coverage_days: Number of days until stockout (or None if covered entire projection)
    """

    for idx, day in enumerate(timeline):
        if day['inventory'] <= 0:
            return day['date'], idx

    # If we made it through entire timeline without stockout
    return None, len(timeline)
