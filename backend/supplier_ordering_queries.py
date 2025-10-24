"""
Supplier Ordering SQL Query Helpers

Helper functions for building complex SQL queries used in the supplier
ordering API endpoints. Separates query construction logic from API handlers.
"""

from typing import Dict, List, Tuple


def build_orders_query(
    order_month: str,
    warehouse: str = None,
    supplier: str = None,
    urgency: str = None,
    search: str = None,
    sort_by: str = "urgency_level",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 50
) -> Tuple[str, Tuple, str, Tuple]:
    """
    Build paginated and filtered query for supplier order confirmations.

    Args:
        order_month: Order month in YYYY-MM format
        warehouse: Optional warehouse filter
        supplier: Optional supplier filter
        urgency: Optional urgency level filter
        search: Optional search query for SKU ID or description
        sort_by: Column to sort by
        sort_order: Sort direction (asc/desc)
        page: Page number (1-indexed)
        page_size: Items per page

    Returns:
        Tuple of (data_query, data_params, count_query, count_params)
    """
    # Build base query with explicit column selection
    base_query = """
        SELECT
            soc.id,
            soc.sku_id,
            s.description,
            soc.warehouse,
            soc.supplier,
            soc.current_inventory,
            soc.pending_orders_effective,
            soc.suggested_qty,
            soc.confirmed_qty,
            COALESCE(soc.lead_time_days_override, soc.lead_time_days_default) as lead_time_days,
            COALESCE(soc.expected_arrival_override, soc.expected_arrival_calculated) as expected_arrival,
            soc.coverage_months,
            soc.urgency_level,
            soc.stockout_risk_date,
            soc.is_locked,
            soc.locked_by,
            soc.locked_at,
            soc.notes,
            soc.pending_breakdown,
            soc.overdue_pending_count,
            s.abc_code,
            s.xyz_code,
            s.cost_per_unit,
            s.status as sku_status,
            (soc.suggested_qty * s.cost_per_unit) as suggested_value,
            (soc.confirmed_qty * s.cost_per_unit) as confirmed_value
        FROM supplier_order_confirmations soc
        JOIN skus s ON soc.sku_id = s.sku_id
        WHERE soc.order_month = %s
    """

    # Build filter conditions
    conditions = []
    params = [order_month]

    if warehouse:
        conditions.append("soc.warehouse = %s")
        params.append(warehouse)

    if supplier:
        conditions.append("soc.supplier = %s")
        params.append(supplier)

    if urgency:
        conditions.append("soc.urgency_level = %s")
        params.append(urgency)

    if search:
        conditions.append("(soc.sku_id LIKE %s OR s.description LIKE %s)")
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    # Add conditions to query
    where_clause = base_query
    if conditions:
        where_clause += " AND " + " AND ".join(conditions)

    # Build count query (same params)
    count_query = f"SELECT COUNT(*) FROM ({where_clause}) as subquery"
    count_params = tuple(params)

    # Validate and build sort clause
    valid_sort_columns = [
        "sku_id", "warehouse", "supplier", "urgency_level",
        "suggested_qty", "confirmed_qty", "coverage_months",
        "stockout_risk_date", "suggested_value", "confirmed_value"
    ]

    if sort_by not in valid_sort_columns:
        sort_by = "urgency_level"

    if sort_order.lower() not in ["asc", "desc"]:
        sort_order = "desc"

    # Custom urgency sorting (must > should > optional > skip)
    if sort_by == "urgency_level":
        order_clause = f"""
            ORDER BY
                CASE urgency_level
                    WHEN 'must_order' THEN 1
                    WHEN 'should_order' THEN 2
                    WHEN 'optional' THEN 3
                    WHEN 'skip' THEN 4
                END {sort_order}
        """
    else:
        order_clause = f"ORDER BY {sort_by} {sort_order}"

    # Add pagination
    final_query = where_clause + " " + order_clause + " LIMIT %s OFFSET %s"
    params.append(page_size)
    params.append((page - 1) * page_size)

    return final_query, tuple(params), count_query, count_params


def build_summary_queries() -> Tuple[str, str]:
    """
    Build queries for summary statistics.

    Returns:
        Tuple of (stats_query, supplier_query)
    """
    stats_query = """
        SELECT
            COUNT(*) as total_skus,
            SUM(CASE WHEN urgency_level = 'must_order' THEN 1 ELSE 0 END) as must_order,
            SUM(CASE WHEN urgency_level = 'should_order' THEN 1 ELSE 0 END) as should_order,
            SUM(CASE WHEN urgency_level = 'optional' THEN 1 ELSE 0 END) as optional,
            SUM(CASE WHEN urgency_level = 'skip' THEN 1 ELSE 0 END) as skip,
            COALESCE(SUM(suggested_qty * s.cost_per_unit), 0) as total_suggested,
            COALESCE(SUM(confirmed_qty * s.cost_per_unit), 0) as total_confirmed,
            SUM(CASE WHEN is_locked = TRUE THEN 1 ELSE 0 END) as locked,
            SUM(overdue_pending_count) as overdue_pending
        FROM supplier_order_confirmations soc
        JOIN skus s ON soc.sku_id = s.sku_id
        WHERE order_month = %s
    """

    supplier_query = """
        SELECT
            supplier,
            COUNT(*) as sku_count,
            SUM(suggested_qty) as total_suggested_qty,
            SUM(confirmed_qty) as total_confirmed_qty,
            COALESCE(SUM(suggested_qty * s.cost_per_unit), 0) as suggested_value,
            COALESCE(SUM(confirmed_qty * s.cost_per_unit), 0) as confirmed_value,
            SUM(CASE WHEN urgency_level = 'must_order' THEN 1 ELSE 0 END) as must_order_count
        FROM supplier_order_confirmations soc
        JOIN skus s ON soc.sku_id = s.sku_id
        WHERE order_month = %s
        GROUP BY supplier
        ORDER BY confirmed_value DESC
    """

    return stats_query, supplier_query
