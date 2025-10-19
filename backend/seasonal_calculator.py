"""
Seasonal Pattern Calculator Module

This module calculates seasonal patterns for SKUs based on historical sales data.
It analyzes monthly sales to identify seasonal trends and stores them in the
seasonal_factors table for use in forecasting.

Key Functions:
- calculate_seasonal_pattern: Determines if a SKU has a seasonal sales pattern
- get_monthly_factors: Calculates seasonal adjustment factors for each month
- detect_peak_months: Identifies months with highest sales activity
- calculate_on_the_fly: Generates seasonal factors for SKUs missing them
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime, date
import statistics
from backend.database import execute_query


def calculate_seasonal_pattern(sku_id: str, warehouse: str = 'combined') -> Dict:
    """
    Calculate seasonal pattern for a SKU based on historical sales data.

    This function analyzes at least 12 months of sales data to identify seasonal
    trends. It uses coefficient of variation (CV) and peak month analysis to
    determine the seasonal pattern type.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse location ('burnaby', 'kentucky', 'combined')

    Returns:
        Dictionary containing:
        - pattern: Seasonal pattern type (spring_summer, fall_winter, holiday, year_round, unknown)
        - factors: Dict of monthly factors (1-12) where 1.0 is average
        - peak_months: List of peak month numbers
        - confidence: Confidence score (0-1) based on data quality
        - cv: Coefficient of variation of monthly sales

    Raises:
        ValueError: If insufficient historical data (< 12 months)
    """
    # Get historical monthly sales for the past 24 months
    # Note: year_month is in YYYY-MM format, extract month number from it

    # Calculate cutoff date in Python to avoid SQL escaping issues
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    cutoff_date = (datetime.now() - relativedelta(months=24)).strftime('%Y-%m')

    query = """
        SELECT
            CAST(SUBSTRING(`year_month`, 6, 2) AS UNSIGNED) as month,
            AVG(burnaby_sales + kentucky_sales) as avg_sales,
            COUNT(*) as data_points
        FROM monthly_sales
        WHERE sku_id = %s
          AND `year_month` >= %s
          AND (burnaby_sales > 0 OR kentucky_sales > 0)
        GROUP BY CAST(SUBSTRING(`year_month`, 6, 2) AS UNSIGNED)
        ORDER BY month
    """

    monthly_data = execute_query(query, (sku_id, cutoff_date), fetch_all=True)

    if len(monthly_data) < 12:
        raise ValueError(f"Insufficient data for SKU {sku_id}: only {len(monthly_data)} months available")

    # Calculate monthly averages and coefficient of variation
    monthly_sales = {row['month']: row['avg_sales'] for row in monthly_data}
    sales_values = list(monthly_sales.values())

    avg_sales = statistics.mean(sales_values)
    std_sales = statistics.stdev(sales_values) if len(sales_values) > 1 else 0
    cv = std_sales / avg_sales if avg_sales > 0 else 0

    # Calculate seasonal factors (ratio to average)
    factors = {month: (sales / avg_sales) if avg_sales > 0 else 1.0
               for month, sales in monthly_sales.items()}

    # Fill missing months with 1.0 (average)
    for month in range(1, 13):
        if month not in factors:
            factors[month] = 1.0

    # Identify peak months (> 1.2x average)
    peak_months = [month for month, factor in factors.items() if factor > 1.2]

    # Determine seasonal pattern type
    pattern = _classify_seasonal_pattern(peak_months, cv)

    # Calculate confidence based on data consistency
    data_points_per_month = [row['data_points'] for row in monthly_data]
    avg_data_points = statistics.mean(data_points_per_month)
    confidence = min(1.0, avg_data_points / 12.0)  # Higher confidence with more data

    return {
        'pattern': pattern,
        'factors': factors,
        'peak_months': peak_months,
        'confidence': round(confidence, 2),
        'cv': round(cv, 3)
    }


def _classify_seasonal_pattern(peak_months: List[int], cv: float) -> str:
    """
    Classify seasonal pattern based on peak months and variability.

    Args:
        peak_months: List of months with peak sales (1-12)
        cv: Coefficient of variation

    Returns:
        Pattern type: spring_summer, fall_winter, holiday, year_round, unknown
    """
    if cv < 0.15:
        return 'year_round'  # Low variability = consistent year-round sales

    if not peak_months:
        return 'unknown'

    # Spring/Summer: March-August (3-8)
    spring_summer_months = set(range(3, 9))
    # Fall/Winter: September-February (9-12, 1-2)
    fall_winter_months = set([1, 2, 9, 10, 11, 12])
    # Holiday: November-December (11-12)
    holiday_months = set([11, 12])

    peak_set = set(peak_months)

    # Check for holiday pattern (strong November-December peak)
    if holiday_months.issubset(peak_set) and cv > 0.3:
        return 'holiday'

    # Check for spring/summer dominance
    spring_summer_overlap = len(peak_set & spring_summer_months)
    fall_winter_overlap = len(peak_set & fall_winter_months)

    if spring_summer_overlap > fall_winter_overlap:
        return 'spring_summer'
    elif fall_winter_overlap > spring_summer_overlap:
        return 'fall_winter'

    return 'unknown'


def get_monthly_factors(sku_id: str, warehouse: str = 'combined') -> Dict[int, float]:
    """
    Get seasonal adjustment factors for each month (1-12).

    First checks if factors exist in seasonal_factors table. If not found,
    calculates them on-the-fly and optionally stores them.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse location

    Returns:
        Dictionary mapping month number (1-12) to seasonal factor
        Factor of 1.0 = average month, >1.0 = above average, <1.0 = below average

    Example:
        {1: 0.8, 2: 0.9, 3: 1.1, 4: 1.2, ..., 12: 1.3}
    """
    # Check if seasonal factors already exist
    # Note: The existing seasonal_factors table uses month_number/seasonal_factor columns (one row per month)
    query = """
        SELECT month_number, seasonal_factor
        FROM seasonal_factors
        WHERE sku_id = %s AND warehouse = %s
        ORDER BY month_number
    """

    result = execute_query(query, (sku_id, warehouse), fetch_all=True)

    if result and len(result) == 12:
        # Return existing factors
        return {int(row['month_number']): float(row['seasonal_factor']) for row in result}

    # Calculate on-the-fly if not found
    try:
        pattern_data = calculate_seasonal_pattern(sku_id, warehouse)
        return pattern_data['factors']
    except ValueError:
        # Insufficient data - return neutral factors
        return {i: 1.0 for i in range(1, 13)}


def detect_peak_months(sku_id: str, threshold: float = 1.2) -> List[int]:
    """
    Detect peak sales months for a SKU.

    Args:
        sku_id: SKU identifier
        threshold: Factor threshold for peak detection (default 1.2 = 20% above average)

    Returns:
        List of month numbers (1-12) with sales above threshold

    Example:
        [11, 12] indicates November-December peaks (holiday pattern)
    """
    factors = get_monthly_factors(sku_id)
    return [month for month, factor in factors.items() if factor >= threshold]


def calculate_missing_seasonal_factors(batch_size: int = 100) -> Dict:
    """
    Calculate seasonal factors for SKUs that don't have them yet.

    This is a batch operation that processes SKUs without seasonal factors.
    It should be run as a background job to populate the seasonal_factors table.

    Args:
        batch_size: Number of SKUs to process in this batch

    Returns:
        Dictionary with:
        - processed: Number of SKUs processed
        - successful: Number successfully calculated
        - failed: Number that failed
        - errors: List of error messages
    """
    # Get SKUs without seasonal factors
    query = """
        SELECT DISTINCT s.sku_id
        FROM skus s
        LEFT JOIN seasonal_factors sf ON s.sku_id = sf.sku_id
        WHERE sf.sku_id IS NULL
          AND s.status = 'Active'
        LIMIT %s
    """

    skus_to_process = execute_query(query, (batch_size,), fetch_all=True)

    results = {
        'processed': 0,
        'successful': 0,
        'failed': 0,
        'errors': []
    }

    for row in skus_to_process:
        sku_id = row['sku_id']
        results['processed'] += 1

        try:
            # Calculate pattern for combined warehouse
            pattern_data = calculate_seasonal_pattern(sku_id, 'combined')

            # Store in seasonal_factors table
            _store_seasonal_factors(sku_id, 'combined', pattern_data)

            results['successful'] += 1

        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"{sku_id}: {str(e)}")

    return results


def _store_seasonal_factors(sku_id: str, warehouse: str, pattern_data: Dict) -> None:
    """
    Store calculated seasonal factors in the database.

    Args:
        sku_id: SKU identifier
        warehouse: Warehouse location
        pattern_data: Dictionary from calculate_seasonal_pattern()
    """
    factors = pattern_data['factors']

    # Delete existing factors for this SKU/warehouse
    delete_query = "DELETE FROM seasonal_factors WHERE sku_id = %s AND warehouse = %s"
    execute_query(delete_query, (sku_id, warehouse), fetch_all=False)

    # Insert one row per month (12 rows total)
    # Note: The existing seasonal_factors table uses month_number/seasonal_factor columns
    insert_query = """
        INSERT INTO seasonal_factors
        (sku_id, warehouse, month_number, seasonal_factor,
         pattern_type, confidence_level, pattern_strength, data_points_used)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    # Prepare all 12 rows
    for month_num in range(1, 13):
        params = (
            sku_id,
            warehouse,
            month_num,
            factors[month_num],
            pattern_data['pattern'],
            pattern_data['confidence'],
            pattern_data['confidence'],  # Using confidence as pattern_strength
            12  # Assume 12 data points used
        )
        execute_query(insert_query, params, fetch_all=False)


def get_seasonal_adjustment(sku_id: str, target_month: int, warehouse: str = 'combined') -> float:
    """
    Get seasonal adjustment factor for a specific month.

    Args:
        sku_id: SKU identifier
        target_month: Month number (1-12)
        warehouse: Warehouse location

    Returns:
        Seasonal factor for the specified month (1.0 = average)

    Example:
        factor = get_seasonal_adjustment('ABC123', 12, 'kentucky')
        # Returns 1.3 if December is typically 30% above average
    """
    if target_month < 1 or target_month > 12:
        raise ValueError(f"Invalid month: {target_month}. Must be 1-12")

    factors = get_monthly_factors(sku_id, warehouse)
    return factors.get(target_month, 1.0)
