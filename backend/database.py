"""
Database connection and utility functions

This module provides database connectivity with both legacy PyMySQL support
and new SQLAlchemy connection pooling for improved performance.

Connection Pooling:
- Uses SQLAlchemy connection pooling to prevent connection exhaustion
- Falls back to direct PyMySQL connections if pooling fails
- Configurable pool size and overflow handling
"""
import pymysql
import pymysql.cursors
import os
from typing import Optional, Union, List, Dict, Any
import logging
import time

# Import the new connection pool
try:
    from .database_pool import get_connection_pool, execute_pooled_query, DatabaseConnectionPool
    POOLING_AVAILABLE = True
except ImportError:
    # Fallback if SQLAlchemy is not available
    POOLING_AVAILABLE = False
    print("Warning: SQLAlchemy not available, using direct connections")

# Database configuration for legacy connections
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'warehouse_transfer'),
    'charset': 'utf8mb4',
    'autocommit': True
}

logger = logging.getLogger(__name__)

# Configuration for connection pooling
USE_CONNECTION_POOLING = os.getenv('USE_CONNECTION_POOLING', 'true').lower() == 'true'


def get_database_connection():
    """
    Create and return a database connection (legacy method)

    This is kept for backward compatibility. New code should use execute_query()
    which automatically uses connection pooling when available.
    """
    try:
        connection = pymysql.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise


def test_connection() -> bool:
    """
    Test if database connection is working

    Tests both connection pooling (if available) and direct connections.
    """
    try:
        if POOLING_AVAILABLE and USE_CONNECTION_POOLING:
            # Test using connection pool
            result = execute_pooled_query("SELECT 1 as test", fetch_one=True)
            return result is not None and result.get('test') == 1
        else:
            # Test using direct connection
            db = get_database_connection()
            cursor = db.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            db.close()
            return True

    except Exception as e:
        logger.error(f"Database test failed: {e}")
        return False


def execute_query(query: str,
                 params: Optional[tuple] = None,
                 fetch_one: bool = False,
                 fetch_all: bool = True) -> Optional[Union[List[Dict], Dict, int]]:
    """
    Execute a database query with automatic connection pooling

    This function automatically uses connection pooling when available,
    falling back to direct connections if pooling is disabled or fails.

    Args:
        query: SQL query string
        params: Query parameters tuple
        fetch_one: Return single result
        fetch_all: Return all results (default)

    Returns:
        Query results or None

    Raises:
        Exception: If query execution fails
    """
    # Try using connection pooling first
    if POOLING_AVAILABLE and USE_CONNECTION_POOLING:
        try:
            return execute_pooled_query(query, params, fetch_one, fetch_all)
        except Exception as e:
            logger.warning(f"Connection pool failed, falling back to direct connection: {e}")

    # Fallback to direct connection (legacy method)
    return _execute_query_direct(query, params, fetch_one, fetch_all)


def _execute_query_direct(query: str,
                         params: Optional[tuple] = None,
                         fetch_one: bool = False,
                         fetch_all: bool = True) -> Optional[Union[List[Dict], Dict, int]]:
    """
    Execute a database query using direct PyMySQL connection (legacy method)

    This is the original implementation kept for fallback purposes.
    """
    try:
        db = get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(query, params)

        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        else:
            result = None

        db.close()
        return result

    except Exception as e:
        logger.error("Query execution failed: " + str(e))
        raise


def execute_many(query: str, params_list: List[tuple]) -> int:
    """
    Execute a query multiple times with different parameters (batch insert/update)

    This is optimized for bulk INSERT/UPDATE operations and uses executemany
    for better performance than multiple individual queries.

    Args:
        query: SQL query with placeholders
        params_list: List of tuples, each containing parameters for one execution

    Returns:
        Number of rows affected

    Example:
        query = "INSERT INTO table (col1, col2) VALUES (%s, %s)"
        params = [(val1a, val2a), (val1b, val2b), (val1c, val2c)]
        rows_affected = execute_many(query, params)
    """
    try:
        db = get_database_connection()
        cursor = db.cursor()
        cursor.executemany(query, params_list)
        rows_affected = cursor.rowcount
        db.commit()
        db.close()
        return rows_affected

    except Exception as e:
        logger.error(f"Batch query execution failed: {e}")
        raise


def get_connection_pool_status() -> Dict[str, Any]:
    """
    Get connection pool status and statistics

    Returns:
        Dictionary containing pool status, or error info if pooling unavailable
    """
    if not POOLING_AVAILABLE:
        return {
            'pooling_available': False,
            'error': 'SQLAlchemy not installed'
        }

    if not USE_CONNECTION_POOLING:
        return {
            'pooling_available': True,
            'pooling_enabled': False,
            'reason': 'Disabled via configuration'
        }

    try:
        pool = get_connection_pool()
        status = pool.get_pool_status()
        status['pooling_available'] = True
        status['pooling_enabled'] = True
        return status
    except Exception as e:
        return {
            'pooling_available': True,
            'pooling_enabled': True,
            'error': str(e)
        }

def get_current_stock_status():
    """
    Get current stock status for all active SKUs
    """
    query = """
    SELECT 
        s.sku_id,
        s.description,
        s.supplier,
        s.abc_code,
        s.xyz_code,
        s.transfer_multiple,
        ic.burnaby_qty,
        ic.kentucky_qty,
        CASE 
            WHEN ic.kentucky_qty = 0 THEN 'OUT_OF_STOCK'
            WHEN ic.kentucky_qty < 100 THEN 'LOW_STOCK'
            ELSE 'IN_STOCK'
        END as stock_status
    FROM skus s
    LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id
    WHERE s.status = 'Active'
    ORDER BY 
        CASE 
            WHEN ic.kentucky_qty = 0 THEN 1
            WHEN ic.kentucky_qty < 100 THEN 2
            ELSE 3
        END,
        s.sku_id
    """
    return execute_query(query)

def get_monthly_sales_data(sku_id: Optional[str] = None, year_month: Optional[str] = None):
    """
    Get monthly sales data with optional filters
    """
    query = """
    SELECT 
        ms.`year_month`,
        ms.sku_id,
        s.description,
        ms.burnaby_sales,
        ms.kentucky_sales,
        ms.burnaby_stockout_days,
        ms.kentucky_stockout_days,
        ms.corrected_demand_kentucky,
        (ms.burnaby_sales + ms.kentucky_sales) as total_sales
    FROM monthly_sales ms
    JOIN skus s ON ms.sku_id = s.sku_id
    WHERE 1=1
    """
    
    params = []
    if sku_id:
        query += " AND ms.sku_id = %s"
        params.append(sku_id)
    if year_month:
        query += " AND ms.`year_month` = %s"
        params.append(year_month)
        
    query += " ORDER BY ms.`year_month` DESC, ms.sku_id"
    
    return execute_query(query, tuple(params) if params else None)

def get_out_of_stock_skus():
    """
    Get all SKUs that are currently out of stock in Kentucky
    """
    query = """
    SELECT 
        s.sku_id,
        s.description,
        s.abc_code,
        s.xyz_code,
        ic.burnaby_qty,
        ms.kentucky_sales as last_month_sales,
        ms.kentucky_stockout_days,
        sd.stockout_date,
        DATEDIFF(CURDATE(), sd.stockout_date) as days_out_of_stock
    FROM skus s
    JOIN inventory_current ic ON s.sku_id = ic.sku_id
    LEFT JOIN monthly_sales ms ON s.sku_id = ms.sku_id AND ms.`year_month` = '2024-03'
    LEFT JOIN stockout_dates sd ON s.sku_id = sd.sku_id 
        AND sd.warehouse = 'kentucky' 
        AND sd.is_resolved = FALSE
    WHERE ic.kentucky_qty = 0 AND s.status = 'Active'
    ORDER BY sd.stockout_date ASC
    """
    return execute_query(query)

def update_corrected_demand(sku_id: str, year_month: str, corrected_demand: float, warehouse: str = 'kentucky'):
    """
    Update the corrected demand for a specific SKU and month
    """
    field = f'corrected_demand_{warehouse}'
    query = f"""
    UPDATE monthly_sales
    SET {field} = %s
    WHERE sku_id = %s AND `year_month` = %s
    """

    try:
        db = get_database_connection()
        cursor = db.cursor()
        cursor.execute(query, (corrected_demand, sku_id, year_month))
        db.close()
        return True
    except Exception as e:
        logger.error(f"Update corrected demand failed: {e}")
        return False


def get_historical_demand_when_in_stock(sku_id: str, warehouse: str,
                                       lookback_months: int = 6,
                                       min_availability: float = 0.8) -> Optional[float]:
    """
    Get average demand from recent months when SKU had good availability

    This function looks back at recent months to find periods when the SKU
    was adequately stocked and calculates the average demand from those periods.
    Used for correcting severe stockouts based on proven demand patterns.

    Args:
        sku_id: SKU identifier to lookup
        warehouse: 'burnaby' or 'kentucky'
        lookback_months: Number of months to search back (default: 6)
        min_availability: Minimum availability rate to consider "in stock" (default: 0.8)

    Returns:
        Average demand from months with good availability, or None if insufficient data

    Business Logic:
        - Finds months where availability >= min_availability (80% by default)
        - Calculates average demand from those "good" months
        - Requires at least 2 qualifying months to return a value
        - Excludes months with zero sales even if availability is good

    Example:
        >>> get_historical_demand_when_in_stock('LP-12V-NICD-13', 'kentucky', 6, 0.8)
        85.5  # Average from July (68 sales) and April (125 sales) when in stock
    """
    try:
        # Query recent months with sales and stockout data
        query = f"""
        SELECT
            `year_month`,
            {warehouse}_sales as sales,
            {warehouse}_stockout_days as stockout_days,
            YEAR(`year_month`) as year,
            MONTH(`year_month`) as month
        FROM monthly_sales
        WHERE sku_id = %s
            AND {warehouse}_sales > 0
            AND `year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
        ORDER BY `year_month` DESC
        LIMIT %s
        """

        db = get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(query, (sku_id, lookback_months, lookback_months))
        records = cursor.fetchall()
        cursor.close()
        db.close()

        if not records:
            return None

        # Filter for months with good availability
        good_months = []

        for record in records:
            sales = record['sales'] or 0
            stockout_days = record['stockout_days'] or 0
            year = record['year'] or 2025
            month = record['month'] or 1

            # Calculate days in month
            if month in [1, 3, 5, 7, 8, 10, 12]:
                days_in_month = 31
            elif month in [4, 6, 9, 11]:
                days_in_month = 30
            else:  # February
                if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                    days_in_month = 29
                else:
                    days_in_month = 28

            # Calculate availability rate
            availability_rate = (days_in_month - stockout_days) / days_in_month

            # Include months with good availability and sales > 0
            if availability_rate >= min_availability and sales > 0:
                good_months.append(sales)

        # Require at least 2 good months for reliable average
        if len(good_months) >= 2:
            return round(sum(good_months) / len(good_months), 2)

        return None

    except Exception as e:
        logger.error(f"Historical demand lookup failed for {sku_id} {warehouse}: {e}")
        return None


def correct_monthly_demand_graduated(monthly_sales: int, stockout_days: int, days_in_month: int = 30) -> float:
    """
    Calculate stockout-corrected demand using graduated floor approach

    This is the new graduated floor algorithm that applies different floors
    based on stockout severity to provide more accurate corrections.

    Args:
        monthly_sales: Actual sales for the month
        stockout_days: Number of days the item was out of stock
        days_in_month: Total days in the month (default 30)

    Returns:
        Corrected demand using graduated floor based on stockout severity

    Business Logic:
        - Availability >= 50%: No floor (trust actual data)
        - Availability 20-50%: 20% floor for moderate protection
        - Availability < 20%: 10% floor with 3x cap for severe stockouts

    Example:
        >>> correct_monthly_demand_graduated(13, 27, 31)  # 87% stockout
        39.0  # 13 / 0.129 = 100.78, capped at 13 * 3 = 39
    """
    if stockout_days == 0 or monthly_sales == 0:
        return float(monthly_sales)

    # Calculate availability rate
    availability_rate = (days_in_month - stockout_days) / days_in_month

    if availability_rate < 1.0:
        # Graduated floor based on stockout severity
        if availability_rate >= 0.5:
            # Mild stockout (< 50% out): No floor, trust the math
            correction_factor = availability_rate
        elif availability_rate >= 0.2:
            # Moderate stockout (50-80% out): 20% floor
            correction_factor = max(availability_rate, 0.2)
        else:
            # Severe stockout (> 80% out): 10% floor with cap
            correction_factor = max(availability_rate, 0.1)
            corrected_demand = monthly_sales / correction_factor
            # Cap at 3x for extreme cases (instead of 1.5x)
            corrected_demand = min(corrected_demand, monthly_sales * 3)
            return round(corrected_demand, 2)

        corrected_demand = monthly_sales / correction_factor
        return round(corrected_demand, 2)

    return float(monthly_sales)


def correct_monthly_demand_hybrid(monthly_sales: int, stockout_days: int,
                                days_in_month: int, sku_id: str,
                                warehouse: str, year_month: str) -> float:
    """
    Calculate stockout-corrected demand using hybrid historical + graduated approach

    Attempts historical lookup for severe stockouts, falls back to graduated floor
    algorithm. This provides more accurate corrections for Kentucky warehouse's
    frequent severe stockouts by using proven demand patterns when available.

    Args:
        monthly_sales: Actual sales for the month
        stockout_days: Number of days item was out of stock
        days_in_month: Total days in month (28-31)
        sku_id: SKU identifier for historical lookup
        warehouse: 'burnaby' or 'kentucky'
        year_month: YYYY-MM format for context

    Returns:
        Corrected demand accounting for stockout period

    Business Logic:
        1. For severe stockouts (>80%), try historical average first
        2. Use graduated floor based on stockout severity as fallback
        3. Log which method was used for transparency

    Example:
        >>> correct_monthly_demand_hybrid(13, 27, 31, 'LP-12V-NICD-13',
        ...                              'kentucky', '2025-08')
        75.0  # Based on historical average when in stock
    """
    if stockout_days == 0 or monthly_sales == 0:
        return float(monthly_sales)

    # Calculate availability rate
    availability_rate = (days_in_month - stockout_days) / days_in_month

    # For severe stockouts (> 80% out), try historical data first
    if availability_rate < 0.2:
        historical_demand = get_historical_demand_when_in_stock(
            sku_id, warehouse, lookback_months=6, min_availability=0.8
        )

        if historical_demand is not None:
            logger.info(f"Using historical demand for {sku_id} {warehouse} {year_month}: {historical_demand}")
            return historical_demand
        else:
            logger.info(f"No historical data for {sku_id} {warehouse} {year_month}, using graduated floor")

    # Fall back to graduated floor algorithm
    return correct_monthly_demand_graduated(monthly_sales, stockout_days, days_in_month)


def correct_monthly_demand(monthly_sales: int, stockout_days: int, days_in_month: int = 30) -> float:
    """
    Calculate stockout-corrected demand using the simplified monthly approach

    Args:
        monthly_sales: Actual sales for the month
        stockout_days: Number of days the item was out of stock
        days_in_month: Total days in the month (default 30)

    Returns:
        Corrected demand accounting for stockout period

    Business Logic:
        - If no stockouts or no sales, return raw sales
        - Calculate availability rate: (days_in_month - stockout_days) / days_in_month
        - Apply 30% floor to prevent overcorrection
        - Cap at 50% increase for very low availability (safeguard)
    """
    if stockout_days == 0 or monthly_sales == 0:
        return float(monthly_sales)

    # Calculate availability rate
    availability_rate = (days_in_month - stockout_days) / days_in_month

    if availability_rate < 1.0:
        # Apply correction with 30% floor to prevent overcorrection
        correction_factor = max(availability_rate, 0.3)
        corrected_demand = monthly_sales / correction_factor

        # Cap at 50% increase for very low availability (safeguard)
        if availability_rate < 0.3:
            corrected_demand = min(corrected_demand, monthly_sales * 1.5)

        return round(corrected_demand, 2)

    return float(monthly_sales)


def recalculate_all_corrected_demands():
    """
    Recalculate and update corrected demand for all SKUs and months using hybrid algorithm

    This function reads all monthly sales data, applies the new hybrid stockout correction
    algorithm that combines historical demand lookup with graduated floor fallback.
    Stores corrected values in corrected_demand_burnaby and corrected_demand_kentucky fields.

    The hybrid approach:
    1. For severe stockouts (>80%), attempts historical demand lookup first
    2. Falls back to graduated floor algorithm based on stockout severity
    3. Provides more accurate corrections for Kentucky warehouse's frequent stockouts

    Returns:
        Dict with success status and processing statistics including:
        - success: Boolean indicating completion
        - updated_records: Number of monthly_sales records updated
        - errors: List of any errors encountered
        - duration_seconds: Time taken to complete recalculation

    Example:
        result = recalculate_all_corrected_demands()
        # Expected: Kentucky LP-12V-NICD-13 corrected from ~30 to ~70-100
    """
    start_time = time.time()

    try:
        db = get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Get all monthly sales records with stockout days
        query = """
        SELECT sku_id, `year_month`,
               burnaby_sales, kentucky_sales,
               burnaby_stockout_days, kentucky_stockout_days,
               YEAR(`year_month`) as year, MONTH(`year_month`) as month
        FROM monthly_sales
        WHERE burnaby_sales > 0 OR kentucky_sales > 0
           OR burnaby_stockout_days > 0 OR kentucky_stockout_days > 0
        ORDER BY sku_id, `year_month` DESC
        """

        cursor.execute(query)
        records = cursor.fetchall()

        updated_records = 0
        errors = []

        for record in records:
            sku_id = record['sku_id']
            year_month = record['year_month']
            year = record['year'] or 2025  # Default if None
            month = record['month'] or 1   # Default if None

            # Calculate days in month
            if month in [1, 3, 5, 7, 8, 10, 12]:
                days_in_month = 31
            elif month in [4, 6, 9, 11]:
                days_in_month = 30
            else:  # February
                # Check for leap year
                if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                    days_in_month = 29
                else:
                    days_in_month = 28

            # Calculate corrected demand for Burnaby using hybrid algorithm
            burnaby_sales = record['burnaby_sales'] or 0
            burnaby_stockout_days = record['burnaby_stockout_days'] or 0
            corrected_burnaby = correct_monthly_demand_hybrid(
                burnaby_sales, burnaby_stockout_days, days_in_month,
                sku_id, 'burnaby', str(year_month)
            )

            # Calculate corrected demand for Kentucky using hybrid algorithm
            kentucky_sales = record['kentucky_sales'] or 0
            kentucky_stockout_days = record['kentucky_stockout_days'] or 0
            corrected_kentucky = correct_monthly_demand_hybrid(
                kentucky_sales, kentucky_stockout_days, days_in_month,
                sku_id, 'kentucky', str(year_month)
            )

            # Update the record
            update_query = """
            UPDATE monthly_sales
            SET corrected_demand_burnaby = %s, corrected_demand_kentucky = %s
            WHERE sku_id = %s AND `year_month` = %s
            """

            try:
                cursor.execute(update_query, (corrected_burnaby, corrected_kentucky, sku_id, year_month))
                updated_records += 1
            except Exception as e:
                error_msg = f"Failed to update {sku_id} {year_month}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        db.commit()
        cursor.close()
        db.close()

        duration = time.time() - start_time

        return {
            "success": True,
            "updated_records": updated_records,
            "errors": errors,
            "duration_seconds": round(duration, 2)
        }

    except Exception as e:
        logger.error(f"Recalculate corrected demands failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "duration_seconds": round(time.time() - start_time, 2)
        }


def aggregate_stockout_days_for_month(sku_id: str, year_month: str, warehouse: str) -> int:
    """
    Calculate the number of stockout days for a specific SKU, month, and warehouse

    This function aggregates stockout periods from the stockout_dates table
    and calculates how many days within the specified month the SKU was out of stock.

    Business Logic:
    - Handles partial stockout periods that span month boundaries
    - Counts only days within the target month
    - Handles overlapping stockout periods by using date ranges
    - Returns 0 if no stockouts occurred in the specified month

    Args:
        sku_id: The SKU identifier
        year_month: Target month in YYYY-MM format (e.g., '2025-08')
        warehouse: Warehouse name ('kentucky' or 'burnaby')

    Returns:
        int: Number of days out of stock within the specified month (0-31)

    Example:
        # SKU was out from Aug 21 to Sep 2
        days = aggregate_stockout_days_for_month('UB-YTX14AH-BS', '2025-08', 'burnaby')
        # Returns 11 (Aug 21-31 = 11 days)

        days = aggregate_stockout_days_for_month('UB-YTX14AH-BS', '2025-09', 'burnaby')
        # Returns 2 (Sep 1-2 = 2 days)
    """
    try:
        # Parse year and month
        year, month = year_month.split('-')
        year, month = int(year), int(month)

        # Calculate month start and end dates
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

        month_start = f"{year:04d}-{month:02d}-01"
        month_end = f"{next_year:04d}-{next_month:02d}-01"

        # Query stockout periods that overlap with the target month
        query = """
        SELECT
            stockout_date,
            COALESCE(resolved_date, CURDATE()) as end_date,
            is_resolved
        FROM stockout_dates
        WHERE sku_id = %s
            AND warehouse = %s
            AND stockout_date < %s
            AND COALESCE(resolved_date, CURDATE()) >= %s
        ORDER BY stockout_date
        """

        db = get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)
        cursor.execute(query, (sku_id, warehouse, month_end, month_start))
        stockout_periods = cursor.fetchall()
        cursor.close()
        db.close()

        if not stockout_periods:
            return 0

        # Calculate total days within the month
        total_days = 0

        for period in stockout_periods:
            period_start = period['stockout_date']
            period_end = period['end_date']

            # Convert to string format for comparison
            period_start_str = period_start.strftime('%Y-%m-%d')
            period_end_str = period_end.strftime('%Y-%m-%d')

            # Find the overlap between stockout period and target month
            overlap_start = max(period_start_str, month_start)
            overlap_end = min(period_end_str, month_end)

            # Calculate days in overlap (if any)
            if overlap_start < overlap_end:
                from datetime import datetime
                start_date = datetime.strptime(overlap_start, '%Y-%m-%d')
                end_date = datetime.strptime(overlap_end, '%Y-%m-%d')
                days_in_period = (end_date - start_date).days
                total_days += days_in_period

        # Cap at maximum days in month (safety check)
        import calendar
        max_days = calendar.monthrange(year, month)[1]
        return min(total_days, max_days)

    except Exception as e:
        logger.error(f"Stockout aggregation failed for {sku_id} {year_month} {warehouse}: {e}")
        return 0


def sync_all_stockout_days() -> Dict[str, Any]:
    """
    Synchronize all stockout days from stockout_dates table to monthly_sales table

    This function processes all stockout periods and updates the monthly_sales table
    with the correct stockout day counts for both warehouses. It handles:
    - All SKUs that have stockout records
    - All months that are affected by stockout periods
    - Both Burnaby and Kentucky warehouses
    - Proper aggregation of overlapping periods

    Returns:
        Dict containing:
        - success: boolean indicating if operation completed
        - processed_records: number of monthly_sales records updated
        - processed_skus: number of unique SKUs processed
        - errors: list of any errors encountered
        - duration_seconds: time taken to complete

    Example:
        result = sync_all_stockout_days()
        # {
        #     "success": True,
        #     "processed_records": 1234,
        #     "processed_skus": 567,
        #     "errors": [],
        #     "duration_seconds": 5.23
        # }
    """
    import time
    from datetime import datetime, timedelta

    start_time = time.time()
    processed_records = 0
    processed_skus = set()
    errors = []

    try:
        logger.info("Starting stockout days synchronization")

        # Get all unique SKU-warehouse combinations that have stockout data
        db = get_database_connection()
        cursor = db.cursor(pymysql.cursors.DictCursor)

        # Find all month-year combinations that need updating
        query = """
        SELECT DISTINCT
            sd.sku_id,
            sd.warehouse,
            DATE_FORMAT(sd.stockout_date, '%Y-%m') as start_month,
            DATE_FORMAT(COALESCE(sd.resolved_date, CURDATE()), '%Y-%m') as end_month
        FROM stockout_dates sd
        JOIN skus s ON sd.sku_id = s.sku_id
        WHERE s.status = 'Active'
        ORDER BY sd.sku_id, sd.warehouse, start_month
        """

        cursor.execute(query)
        stockout_records = cursor.fetchall()

        if not stockout_records:
            cursor.close()
            db.close()
            return {
                "success": True,
                "processed_records": 0,
                "processed_skus": 0,
                "errors": ["No stockout records found"],
                "duration_seconds": time.time() - start_time
            }

        # Process each stockout record and generate all affected months
        months_to_update = set()

        for record in stockout_records:
            sku_id = record['sku_id']
            warehouse = record['warehouse']
            start_month = record['start_month']
            end_month = record['end_month']

            processed_skus.add(sku_id)

            # Generate all months between start and end
            current_date = datetime.strptime(start_month + '-01', '%Y-%m-%d')
            end_date = datetime.strptime(end_month + '-01', '%Y-%m-%d')

            while current_date <= end_date:
                year_month = current_date.strftime('%Y-%m')
                months_to_update.add((sku_id, warehouse, year_month))

                # Move to next month
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)

        logger.info(f"Found {len(months_to_update)} month-warehouse combinations to update")

        # Update each month's stockout days
        for sku_id, warehouse, year_month in months_to_update:
            try:
                # Calculate stockout days for this month
                stockout_days = aggregate_stockout_days_for_month(sku_id, year_month, warehouse)

                # Determine which field to update
                field = f"{warehouse}_stockout_days"

                # Update or insert monthly_sales record
                update_query = f"""
                INSERT INTO monthly_sales (sku_id, `year_month`, {field})
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE {field} = VALUES({field})
                """

                cursor.execute(update_query, (sku_id, year_month, stockout_days))
                processed_records += 1

                if processed_records % 100 == 0:
                    logger.info(f"Processed {processed_records} records...")

            except Exception as e:
                error_msg = f"Failed to update {sku_id} {year_month} {warehouse}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)

        cursor.close()
        db.close()

        duration = time.time() - start_time
        logger.info(f"Stockout synchronization completed: {processed_records} records, {len(processed_skus)} SKUs in {duration:.2f}s")

        return {
            "success": True,
            "processed_records": processed_records,
            "processed_skus": len(processed_skus),
            "errors": errors,
            "duration_seconds": round(duration, 2)
        }

    except Exception as e:
        error_msg = f"Stockout synchronization failed: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "processed_records": processed_records,
            "processed_skus": len(processed_skus),
            "errors": errors + [error_msg],
            "duration_seconds": time.time() - start_time
        }