"""
Core business logic and calculations for transfer recommendations
Implements stockout correction and ABC-XYZ classification algorithms
Enhanced with seasonal pattern detection and viral growth analysis
"""
import math
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
try:
    from . import database
    from .weighted_demand import WeightedDemandCalculator
    from .cache_manager import create_cache_manager
except ImportError:
    import database
    from weighted_demand import WeightedDemandCalculator
    from cache_manager import create_cache_manager
import logging

logger = logging.getLogger(__name__)

def get_pending_quantities(sku_id: str, destination: str) -> dict:
    """
    Get time-weighted pending quantities for transfer calculations

    This function implements time-weighted pending quantity logic where:
    - Immediate arrivals (0-30 days) count 100% toward current position
    - Near-term arrivals (31-60 days) count 80%
    - Medium-term arrivals (61-90 days) count 60%
    - Long-term arrivals (>90 days) count 40%

    Args:
        sku_id: SKU identifier
        destination: 'burnaby' or 'kentucky'

    Returns:
        dict: {
            'immediate': qty (0-30 days, weight=1.0),
            'near_term': qty (31-60 days, weight=0.8),
            'medium_term': qty (61-90 days, weight=0.6),
            'long_term': qty (>90 days, weight=0.4),
            'total_weighted': float,
            'earliest_arrival': date,
            'latest_arrival': date,
            'shipment_count': int
        }

    Example:
        >>> get_pending_quantities('SKU1', 'kentucky')
        {
            'immediate': 50,    # 30 days
            'near_term': 150,   # 60 days
            'long_term': 200,   # 120 days
            'total_weighted': 250.0,  # 50*1.0 + 150*0.8 + 200*0.4
            'earliest_arrival': datetime.date(2025, 10, 14),
            'latest_arrival': datetime.date(2026, 1, 12),
            'shipment_count': 3
        }
    """
    try:
        db = database.get_database_connection()
        cursor = db.cursor(database.pymysql.cursors.DictCursor)

        # Query to get pending orders with days until arrival
        query = """
        SELECT
            quantity,
            expected_arrival,
            is_estimated,
            DATEDIFF(expected_arrival, CURDATE()) as days_until_arrival
        FROM pending_inventory
        WHERE sku_id = %s
            AND destination = %s
            AND status IN ('ordered', 'shipped', 'pending')
            AND expected_arrival >= CURDATE()
        ORDER BY expected_arrival ASC
        """

        cursor.execute(query, (sku_id, destination))
        pending_orders = cursor.fetchall()

        cursor.close()
        db.close()

        if not pending_orders:
            return {
                'immediate': 0,
                'near_term': 0,
                'medium_term': 0,
                'long_term': 0,
                'total_weighted': 0.0,
                'earliest_arrival': None,
                'latest_arrival': None,
                'shipment_count': 0
            }

        # Initialize counters
        immediate_qty = 0      # 0-30 days
        near_term_qty = 0      # 31-60 days
        medium_term_qty = 0    # 61-90 days
        long_term_qty = 0      # >90 days

        earliest_arrival = None
        latest_arrival = None

        for order in pending_orders:
            days_until = order['days_until_arrival']
            quantity = order['quantity']
            arrival_date = order['expected_arrival']

            # Track earliest and latest arrival dates
            if earliest_arrival is None or arrival_date < earliest_arrival:
                earliest_arrival = arrival_date
            if latest_arrival is None or arrival_date > latest_arrival:
                latest_arrival = arrival_date

            # Apply confidence weighting for estimated dates
            confidence_weight = 0.8 if order['is_estimated'] else 1.0
            weighted_qty = quantity * confidence_weight

            # Categorize by time window
            if days_until <= 30:
                immediate_qty += weighted_qty
            elif days_until <= 60:
                near_term_qty += weighted_qty
            elif days_until <= 90:
                medium_term_qty += weighted_qty
            else:
                long_term_qty += weighted_qty

        # Calculate total weighted quantity for transfer calculations
        # Time weights: immediate=1.0, near=0.8, medium=0.6, long=0.4
        total_weighted = (
            immediate_qty * 1.0 +
            near_term_qty * 0.8 +
            medium_term_qty * 0.6 +
            long_term_qty * 0.4
        )

        return {
            'immediate': round(immediate_qty),
            'near_term': round(near_term_qty),
            'medium_term': round(medium_term_qty),
            'long_term': round(long_term_qty),
            'total_weighted': round(total_weighted, 2),
            'earliest_arrival': earliest_arrival,
            'latest_arrival': latest_arrival,
            'shipment_count': len(pending_orders)
        }

    except Exception as e:
        logger.error(f"Error calculating pending quantities for {sku_id} ({destination}): {e}")
        # Return empty result on error to avoid breaking transfer calculations
        return {
            'immediate': 0,
            'near_term': 0,
            'medium_term': 0,
            'long_term': 0,
            'total_weighted': 0.0,
            'earliest_arrival': None,
            'latest_arrival': None,
            'shipment_count': 0
        }


def calculate_burnaby_coverage_multiplier(sku_id: str) -> float:
    """
    Calculate Burnaby coverage multiplier based on pending arrivals

    Adjusts minimum retention requirements based on when new inventory
    is expected to arrive at Burnaby warehouse.

    Args:
        sku_id: SKU identifier to check pending orders for

    Returns:
        float: Coverage multiplier (0.8 = aggressive, 1.0 = normal, 1.5 = conservative)

    Example:
        >>> calculate_burnaby_coverage_multiplier('SKU1')
        0.8  # Can be more aggressive - inventory arriving in 30 days
    """
    try:
        pending = get_pending_quantities(sku_id, 'burnaby')

        if pending['immediate'] > 0:
            # Inventory arriving within 30 days - can be more aggressive
            return 0.8
        elif pending['near_term'] > 0:
            # Inventory arriving in 31-60 days - normal retention
            return 1.0
        else:
            # No near-term inventory - be conservative
            return 1.5

    except Exception as e:
        logger.error(f"Error calculating Burnaby coverage multiplier for {sku_id}: {e}")
        # Default to conservative on error
        return 1.5


class StockoutCorrector:
    """
    Handles stockout detection and demand correction calculations
    Enhanced with year-over-year lookups and category averages
    """

    @staticmethod
    def correct_monthly_demand(monthly_sales: int, stockout_days: int, days_in_month: int = 30) -> float:
        """
        Calculate stockout-corrected demand using the simplified monthly approach
        
        Args:
            monthly_sales: Actual units sold in the month
            stockout_days: Number of days out of stock in the month
            days_in_month: Total days in the month (default 30)
        
        Returns:
            Corrected demand accounting for stockout periods
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

    @staticmethod
    def correct_monthly_demand_enhanced(sku_id: str, monthly_sales: int, stockout_days: int,
                                      year_month: str = None, days_in_month: int = 30) -> float:
        """
        Enhanced stockout correction with year-over-year and category fallbacks

        Args:
            sku_id: SKU identifier for historical lookup
            monthly_sales: Actual units sold in the month
            stockout_days: Number of days out of stock in the month
            year_month: Period for analysis (defaults to current)
            days_in_month: Total days in the month

        Returns:
            Corrected demand accounting for stockout periods with historical context
        """
        try:
            # Handle zero sales with significant stockout period
            if monthly_sales == 0 and stockout_days > 20:
                logger.info(f"Zero sales with {stockout_days} stockout days for {sku_id}, using enhanced logic")

                # Try year-over-year lookup first
                yoy_demand = StockoutCorrector.get_same_month_last_year(sku_id, year_month)
                if yoy_demand > 0:
                    # Apply growth factor for year-over-year data
                    return round(yoy_demand * 1.1, 2)  # 10% growth assumption

                # Fall back to category average
                category_avg = StockoutCorrector.get_category_average(sku_id)
                if category_avg > 0:
                    return round(category_avg, 2)

                # Final fallback to basic correction
                return 10.0  # Minimum viable demand estimate

            # Use standard correction for all other cases
            return StockoutCorrector.correct_monthly_demand(monthly_sales, stockout_days, days_in_month)

        except Exception as e:
            logger.error(f"Enhanced correction failed for {sku_id}: {e}")
            return StockoutCorrector.correct_monthly_demand(monthly_sales, stockout_days, days_in_month)

    @staticmethod
    def get_same_month_last_year(sku_id: str, current_year_month: str = None) -> float:
        """
        Get demand from the same month in the previous year for seasonal comparison

        Args:
            sku_id: SKU identifier
            current_year_month: Current period (format: YYYY-MM)

        Returns:
            Previous year demand for same month, 0 if not found
        """
        try:
            if not current_year_month:
                # Get the latest month for this SKU
                query = """
                SELECT MAX(year_month) as latest_month
                FROM monthly_sales
                WHERE sku_id = %s
                """
                result = database.execute_query(query, (sku_id,), fetch_one=True)
                current_year_month = result['latest_month'] if result else None

            if not current_year_month:
                return 0.0

            # Calculate previous year month
            year, month = current_year_month.split('-')
            prev_year = int(year) - 1
            prev_year_month = f"{prev_year}-{month}"

            # Query for previous year data
            query = """
            SELECT kentucky_sales, corrected_demand_kentucky
            FROM monthly_sales
            WHERE sku_id = %s AND year_month = %s
            """

            result = database.execute_query(query, (sku_id, prev_year_month), fetch_one=True)

            if result:
                # Use corrected demand if available, otherwise raw sales
                demand = result['corrected_demand_kentucky'] or result['kentucky_sales'] or 0
                logger.debug(f"Found {prev_year_month} demand for {sku_id}: {demand}")
                return float(demand)

            return 0.0

        except Exception as e:
            logger.error(f"Year-over-year lookup failed for {sku_id}: {e}")
            return 0.0

    @staticmethod
    def get_category_average(sku_id: str) -> float:
        """
        Get category average demand for SKUs without historical data

        Args:
            sku_id: SKU identifier to get category for

        Returns:
            Average category demand, 0 if not available
        """
        try:
            # Get SKU category
            sku_query = """
            SELECT category FROM skus WHERE sku_id = %s AND category IS NOT NULL
            """
            sku_result = database.execute_query(sku_query, (sku_id,), fetch_one=True)

            if not sku_result or not sku_result['category']:
                logger.debug(f"No category found for {sku_id}")
                return 0.0

            category = sku_result['category']

            # Get category average from view
            avg_query = """
            SELECT avg_corrected_demand, avg_monthly_sales
            FROM v_category_averages
            WHERE category = %s
            """

            avg_result = database.execute_query(avg_query, (category,), fetch_one=True)

            if avg_result:
                # Use corrected demand average if available, otherwise sales average
                avg_demand = avg_result['avg_corrected_demand'] or avg_result['avg_monthly_sales'] or 0
                logger.debug(f"Category {category} average for {sku_id}: {avg_demand}")
                return float(avg_demand)

            return 0.0

        except Exception as e:
            logger.error(f"Category average lookup failed for {sku_id}: {e}")
            return 0.0

class ABCXYZClassifier:
    """Handles ABC-XYZ classification for inventory management"""
    
    @staticmethod
    def classify_abc_batch(sku_values: List[tuple]) -> Dict[str, str]:
        """
        Classify all SKUs based on cumulative annual value (Pareto 80/15/5 rule)

        Args:
            sku_values: List of (sku_id, annual_value) tuples

        Returns:
            Dictionary mapping sku_id to ABC classification ('A', 'B', or 'C')
        """
        if not sku_values:
            return {}

        # Sort by annual value descending
        sorted_skus = sorted(sku_values, key=lambda x: x[1], reverse=True)
        total_value = sum(value for _, value in sorted_skus)

        if total_value == 0:
            return {sku_id: 'C' for sku_id, _ in sorted_skus}

        classifications = {}
        cumulative_value = 0

        for sku_id, annual_value in sorted_skus:
            cumulative_value += annual_value
            cumulative_percentage = (cumulative_value / total_value) * 100

            if cumulative_percentage <= 80:  # Top 80% of cumulative value
                classifications[sku_id] = 'A'
            elif cumulative_percentage <= 95:  # Next 15% of cumulative value
                classifications[sku_id] = 'B'
            else:  # Bottom 5% of cumulative value
                classifications[sku_id] = 'C'

        return classifications

    @staticmethod
    def classify_abc(annual_value: float, total_value: float) -> str:
        """
        Legacy method - kept for backward compatibility
        Note: This method is flawed and should not be used for new implementations
        Use classify_abc_batch() instead for proper ABC classification
        """
        if total_value == 0:
            return 'C'

        percentage = (annual_value / total_value) * 100

        if percentage >= 80:  # Top 80% of value
            return 'A'
        elif percentage >= 15:  # Next 15% of value
            return 'B'
        else:  # Bottom 5% of value
            return 'C'
    
    @staticmethod
    def classify_xyz(sales_data: List[float]) -> str:
        """
        Classify SKU based on demand variability (coefficient of variation)
        
        Args:
            sales_data: List of monthly sales figures
        
        Returns:
            XYZ classification ('X', 'Y', or 'Z')
        """
        if len(sales_data) < 2:
            return 'Z'  # Insufficient data = irregular
        
        mean_sales = sum(sales_data) / len(sales_data)
        if mean_sales == 0:
            return 'Z'
        
        # Calculate standard deviation
        variance = sum((x - mean_sales) ** 2 for x in sales_data) / (len(sales_data) - 1)
        std_dev = math.sqrt(variance)
        
        # Coefficient of variation
        cv = std_dev / mean_sales
        
        if cv < 0.25:
            return 'X'  # Stable demand
        elif cv < 0.50:
            return 'Y'  # Variable demand
        else:
            return 'Z'  # Irregular demand


class SeasonalPatternDetector:
    """
    Detects seasonal patterns in SKU demand using historical data analysis
    Classifies patterns as spring_summer, fall_winter, holiday, or year_round
    """

    @staticmethod
    def detect_seasonal_pattern(sku_id: str) -> str:
        """
        Analyze 2+ years of monthly data to classify seasonal patterns

        Args:
            sku_id: SKU identifier to analyze

        Returns:
            Seasonal pattern classification string
        """
        try:
            # Get historical monthly sales data (2+ years)
            query = """
            SELECT
                `year_month`,
                kentucky_sales,
                corrected_demand_kentucky,
                MONTH(STR_TO_DATE(CONCAT(`year_month`, '-01'), '%%Y-%%m-%%d')) as month_num,
                YEAR(STR_TO_DATE(CONCAT(`year_month`, '-01'), '%%Y-%%m-%%d')) as year_num
            FROM monthly_sales
            WHERE sku_id = %s
                AND `year_month` >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 24 MONTH), '%%Y-%%m')
            ORDER BY `year_month`
            """

            sales_data = database.execute_query(query, (sku_id,))

            if not sales_data or len(sales_data) < 12:
                logger.debug(f"Insufficient data for seasonal analysis: {sku_id}")
                return 'year_round'  # Default when insufficient data

            # Aggregate sales by month across years
            monthly_totals = defaultdict(list)
            for record in sales_data:
                month = record['month_num']
                sales = record['corrected_demand_kentucky'] or record['kentucky_sales'] or 0
                monthly_totals[month].append(sales)

            # Calculate average sales by month
            monthly_averages = {}
            for month in range(1, 13):
                if month in monthly_totals and monthly_totals[month]:
                    monthly_averages[month] = np.mean(monthly_totals[month])
                else:
                    monthly_averages[month] = 0

            # Analyze patterns
            pattern = SeasonalPatternDetector._classify_pattern(monthly_averages)
            logger.info(f"Detected seasonal pattern for {sku_id}: {pattern}")

            return pattern

        except Exception as e:
            logger.error(f"Seasonal pattern detection failed for {sku_id}: {e}")
            return 'year_round'

    @staticmethod
    def _classify_pattern(monthly_averages: Dict[int, float]) -> str:
        """
        Classify seasonal pattern based on monthly averages

        Args:
            monthly_averages: Dict mapping month number to average sales

        Returns:
            Pattern classification string
        """
        if not monthly_averages or all(v == 0 for v in monthly_averages.values()):
            return 'year_round'

        total_avg = np.mean(list(monthly_averages.values()))
        if total_avg == 0:
            return 'year_round'

        # Calculate seasonal indicators
        spring_summer = np.mean([monthly_averages[m] for m in [3, 4, 5, 6, 7, 8]])  # Mar-Aug
        fall_winter = np.mean([monthly_averages[m] for m in [9, 10, 11, 12, 1, 2]])  # Sep-Feb
        holiday = np.mean([monthly_averages[m] for m in [11, 12]])  # Nov-Dec

        # Normalize by total average to get relative strength
        spring_summer_ratio = spring_summer / total_avg if total_avg > 0 else 1
        fall_winter_ratio = fall_winter / total_avg if total_avg > 0 else 1
        holiday_ratio = holiday / total_avg if total_avg > 0 else 1

        # Classification thresholds
        SEASONAL_THRESHOLD = 1.3  # 30% above average
        HOLIDAY_THRESHOLD = 1.5   # 50% above average for holiday

        # Classification logic
        if holiday_ratio >= HOLIDAY_THRESHOLD:
            return 'holiday'
        elif spring_summer_ratio >= SEASONAL_THRESHOLD and spring_summer_ratio > fall_winter_ratio:
            return 'spring_summer'
        elif fall_winter_ratio >= SEASONAL_THRESHOLD and fall_winter_ratio > spring_summer_ratio:
            return 'fall_winter'
        else:
            return 'year_round'

    @staticmethod
    def get_seasonal_multiplier(pattern: str, current_month: int) -> float:
        """
        Get seasonal adjustment multiplier based on pattern and month

        Args:
            pattern: Seasonal pattern classification
            current_month: Current month number (1-12)

        Returns:
            Multiplier for seasonal adjustment (typically 0.8-1.5)
        """
        # Define seasonal multipliers by pattern and month
        multipliers = {
            'spring_summer': {
                1: 0.8, 2: 0.8, 3: 1.1, 4: 1.2, 5: 1.3, 6: 1.3,
                7: 1.2, 8: 1.1, 9: 0.9, 10: 0.9, 11: 0.8, 12: 0.8
            },
            'fall_winter': {
                1: 1.2, 2: 1.1, 3: 0.9, 4: 0.8, 5: 0.8, 6: 0.8,
                7: 0.8, 8: 0.9, 9: 1.1, 10: 1.2, 11: 1.3, 12: 1.2
            },
            'holiday': {
                1: 0.8, 2: 0.8, 3: 0.9, 4: 0.9, 5: 0.9, 6: 0.9,
                7: 0.9, 8: 0.9, 9: 1.0, 10: 1.1, 11: 1.4, 12: 1.5
            },
            'year_round': {month: 1.0 for month in range(1, 13)}
        }

        return multipliers.get(pattern, multipliers['year_round']).get(current_month, 1.0)


class ViralGrowthDetector:
    """
    Detects viral growth patterns in SKU demand
    Compares recent 3 months to previous 3 months to identify rapid growth
    """

    @staticmethod
    def detect_viral_growth(sku_id: str) -> str:
        """
        Compare recent 3 months to previous 3 months to detect viral growth

        Args:
            sku_id: SKU identifier to analyze

        Returns:
            Growth status: 'viral', 'normal', or 'declining'
        """
        try:
            # Get last 6 months of sales data (MariaDB compatible)
            query = """
            SELECT
                `year_month`,
                kentucky_sales,
                corrected_demand_kentucky
            FROM monthly_sales
            WHERE sku_id = %s
                AND `year_month` >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 6 MONTH), '%Y-%m')
            ORDER BY `year_month` DESC
            LIMIT 6
            """

            sales_data = database.execute_query(query, (sku_id,))

            if not sales_data or len(sales_data) < 6:
                logger.debug(f"Insufficient data for viral growth analysis: {sku_id}")
                return 'normal'

            # Split into recent 3 months vs previous 3 months using Python indexing
            recent_sales = []
            previous_sales = []

            for i, record in enumerate(sales_data):
                sales = record['corrected_demand_kentucky'] or record['kentucky_sales'] or 0
                if i < 3:  # First 3 records are most recent (due to ORDER BY DESC)
                    recent_sales.append(sales)
                else:  # Last 3 records are previous months
                    previous_sales.append(sales)

            # Calculate averages
            recent_avg = np.mean(recent_sales) if recent_sales else 0
            previous_avg = np.mean(previous_sales) if previous_sales else 0

            # Determine growth status
            growth_status = ViralGrowthDetector._classify_growth(recent_avg, previous_avg)
            logger.info(f"Growth analysis for {sku_id}: recent={recent_avg:.1f}, previous={previous_avg:.1f}, status={growth_status}")

            return growth_status

        except Exception as e:
            logger.error(f"Viral growth detection failed for {sku_id}: {e}")
            return 'normal'

    @staticmethod
    def _classify_growth(recent_avg: float, previous_avg: float) -> str:
        """
        Classify growth based on recent vs previous averages

        Args:
            recent_avg: Average demand in recent 3 months
            previous_avg: Average demand in previous 3 months

        Returns:
            Growth classification: 'viral', 'normal', or 'declining'
        """
        if previous_avg == 0:
            return 'viral' if recent_avg > 10 else 'normal'  # New product with demand

        growth_ratio = recent_avg / previous_avg

        # Classification thresholds
        VIRAL_THRESHOLD = 2.0      # 100% growth = viral
        DECLINING_THRESHOLD = 0.5  # 50% decline = declining

        if growth_ratio >= VIRAL_THRESHOLD:
            return 'viral'
        elif growth_ratio <= DECLINING_THRESHOLD:
            return 'declining'
        else:
            return 'normal'

    @staticmethod
    def get_growth_multiplier(growth_status: str) -> float:
        """
        Get demand multiplier based on growth status

        Args:
            growth_status: Growth classification

        Returns:
            Multiplier for demand adjustment
        """
        multipliers = {
            'viral': 1.5,      # Increase demand estimates for viral products
            'normal': 1.0,     # No adjustment for normal growth
            'declining': 0.8   # Reduce demand estimates for declining products
        }

        return multipliers.get(growth_status, 1.0)

class TransferCalculator:
    """
    Main calculator for transfer recommendations
    Enhanced with seasonal patterns and viral growth detection
    """

    # Burnaby retention configuration parameters
    BURNABY_MIN_COVERAGE_MONTHS = 2.0    # Never go below this threshold
    BURNABY_TARGET_COVERAGE_MONTHS = 6.0  # Default target retention
    BURNABY_COVERAGE_WITH_PENDING = 1.5   # When pending arrivals < 45 days

    def __init__(self):
        self.corrector = StockoutCorrector()
        self.classifier = ABCXYZClassifier()
        self.seasonal_detector = SeasonalPatternDetector()
        self.growth_detector = ViralGrowthDetector()
        self.weighted_demand_calculator = WeightedDemandCalculator()
        self.cache_manager = create_cache_manager()
    
    def get_coverage_target(self, abc_class: str, xyz_class: str) -> float:
        """
        Get coverage target in months based on ABC-XYZ classification
        
        Args:
            abc_class: ABC classification ('A', 'B', 'C')
            xyz_class: XYZ classification ('X', 'Y', 'Z')
        
        Returns:
            Target coverage in months
        """
        # Coverage matrix from PRD - Updated C-level targets for better inventory management
        # C-level items need higher coverage due to slower turnover and longer lead times
        coverage_matrix = {
            'AX': 4, 'AY': 5, 'AZ': 6,
            'BX': 3, 'BY': 4, 'BZ': 5,
            'CX': 4, 'CY': 5, 'CZ': 6
        }
        
        key = f"{abc_class}{xyz_class}"
        return coverage_matrix.get(key, 6)  # Default 6 months if unknown
    
    def round_to_multiple(self, quantity: int, multiple: int, max_available: int = None) -> int:
        """
        Round transfer quantity to appropriate multiple

        Args:
            quantity: Calculated transfer quantity
            multiple: Transfer multiple (25, 50, 100)
            max_available: Maximum available inventory (optional)

        Returns:
            Rounded quantity respecting minimum transfer of 10 units and available inventory
        """
        if quantity < 10:
            return 0  # Below minimum transfer threshold

        rounded = math.ceil(quantity / multiple) * multiple

        # Never exceed available inventory
        if max_available is not None and rounded > max_available:
            # Round down to largest multiple that fits within available inventory
            rounded = math.floor(max_available / multiple) * multiple
            # If rounded down below minimum, return 0
            if rounded < 10:
                rounded = 0

        return rounded

    def get_pending_orders_data(self, sku_id: str) -> Dict[str, Any]:
        """
        Get pending orders data for a specific SKU from database views

        Args:
            sku_id: SKU identifier

        Returns:
            Dictionary with pending orders information
        """
        try:
            db = database.get_database_connection()
            import pymysql
            cursor = db.cursor(pymysql.cursors.DictCursor)

            # Query the pending quantities view
            query = """
            SELECT
                burnaby_pending,
                kentucky_pending,
                total_pending,
                earliest_arrival
            FROM v_pending_quantities
            WHERE sku_id = %s
            """

            cursor.execute(query, (sku_id,))
            result = cursor.fetchone()
            cursor.close()
            db.close()

            if result:
                # Calculate days until arrival
                days_until_arrival = None
                if result['earliest_arrival']:
                    days_until_arrival = (result['earliest_arrival'] - datetime.now().date()).days

                return {
                    'burnaby_pending': result['burnaby_pending'] or 0,
                    'kentucky_pending': result['kentucky_pending'] or 0,
                    'total_pending': result['total_pending'] or 0,
                    'earliest_arrival': result['earliest_arrival'],
                    'days_until_arrival': days_until_arrival
                }

            return {
                'burnaby_pending': 0,
                'kentucky_pending': 0,
                'total_pending': 0,
                'earliest_arrival': None,
                'days_until_arrival': None
            }

        except Exception as e:
            logger.error(f"Failed to get pending orders for {sku_id}: {e}")
            return {
                'burnaby_pending': 0,
                'kentucky_pending': 0,
                'total_pending': 0,
                'earliest_arrival': None,
                'days_until_arrival': None
            }

    def _get_pending_data_fallback(self, sku_id: str, kentucky_qty: float) -> Dict[str, Any]:
        """
        Helper method to retrieve pending data in fallback/exception scenarios

        Args:
            sku_id: SKU identifier
            kentucky_qty: Current Kentucky quantity for fallback calculation

        Returns:
            Dictionary with pending data fields for use with dictionary unpacking
        """
        try:
            pending_data = self.get_pending_orders_data(sku_id)
            kentucky_pending = pending_data.get('kentucky_pending', 0)
            burnaby_pending = pending_data.get('burnaby_pending', 0)
            days_until_arrival = pending_data.get('days_until_arrival')

            return {
                'kentucky_pending': kentucky_pending,
                'burnaby_pending': burnaby_pending,
                'days_until_arrival': days_until_arrival,
                'pending_orders_included': True if (kentucky_pending > 0 or burnaby_pending > 0) else False,
                'current_position_with_pending': kentucky_qty + kentucky_pending
            }
        except Exception as e:
            logger.warning(f"Could not retrieve pending data in fallback for {sku_id}: {e}")
            return {
                'kentucky_pending': 0,
                'burnaby_pending': 0,
                'days_until_arrival': None,
                'pending_orders_included': False,
                'current_position_with_pending': kentucky_qty
            }

    def check_stockout_override(self, sku_id: str, warehouse: str = 'kentucky') -> Dict[str, Any]:
        """
        Check if a SKU is marked as out-of-stock in stockout_dates table

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse to check ('kentucky' or 'burnaby')

        Returns:
            Dictionary with override information
        """
        try:
            db = database.get_database_connection()
            import pymysql
            cursor = db.cursor(pymysql.cursors.DictCursor)

            # Check for active stockouts (no date_back_in or future date)
            query = """
            SELECT COUNT(*) as active_stockouts
            FROM stockout_dates
            WHERE sku_id = %s
            AND warehouse = %s
            AND (date_back_in IS NULL OR date_back_in > CURDATE())
            """

            cursor.execute(query, (sku_id, warehouse))
            result = cursor.fetchone()
            cursor.close()
            db.close()

            active_stockouts = result['active_stockouts'] if result else 0

            return {
                'is_overridden': active_stockouts > 0,
                'override_reason': f"Active stockout in {warehouse}" if active_stockouts > 0 else None
            }

        except Exception as e:
            logger.error(f"Failed to check stockout override for {sku_id}: {e}")
            return {
                'is_overridden': False,
                'override_reason': None
            }

    def calculate_burnaby_retention(self, burnaby_qty: int, burnaby_demand: float,
                                   pending_data: Dict[str, Any], abc_class: str = 'C',
                                   xyz_class: str = 'Z') -> Dict[str, Any]:
        """
        Calculate how much inventory Burnaby should retain based on ABC-XYZ classification and pending orders

        Uses dynamic retention targets based on ABC-XYZ classification instead of fixed coverage months.
        High-value or erratic items (A-class, Z-class) get higher retention targets for safety.

        Args:
            burnaby_qty: Current Burnaby inventory
            burnaby_demand: Monthly demand for Burnaby
            pending_data: Pending orders data from get_pending_orders_data()
            abc_class: ABC classification ('A', 'B', 'C') for determining retention importance
            xyz_class: XYZ classification ('X', 'Y', 'Z') for demand variability

        Returns:
            Dictionary with retention calculation details including classification-based targets
        """
        try:
            days_until_arrival = pending_data.get('days_until_arrival')
            burnaby_pending = pending_data.get('burnaby_pending', 0)

            # Dynamic retention based on supplier lead time and pending order status
            # Account for full replenishment cycle when no orders are pending

            # Lead time parameters based on business requirements
            supplier_lead_time_days = 100  # Average of 80-120 days supplier lead time
            review_period_days = 7  # Weekly ordering cycle
            total_replen_time_months = (supplier_lead_time_days + review_period_days) / 30  # ~3.5 months

            if days_until_arrival is None or days_until_arrival > 60 or burnaby_pending == 0:
                # NO PENDING ORDERS or too far away - Need full pipeline coverage
                base_coverage_months = total_replen_time_months + 1.0  # 3.5 + 1 = 4.5 months safety

                # Adjust based on KY/CA demand ratio - if KY sells considerably more, can be more aggressive
                demand_ratio = 1.0
                if kentucky_demand and kentucky_demand > 0 and burnaby_demand > 0:
                    demand_ratio = kentucky_demand / burnaby_demand
                    if demand_ratio > 2.0:  # KY sells 2x+ more than CA
                        base_coverage_months *= 0.7  # Reduce to ~3.15 months
                    elif demand_ratio > 1.5:  # KY sells 1.5x+ more than CA
                        base_coverage_months *= 0.85  # Reduce to ~3.8 months

                burnaby_min_retain = burnaby_demand * base_coverage_months
                retention_reason = f"No pending orders - {base_coverage_months:.1f}m retention (KY/CA ratio: {demand_ratio:.1f}, {abc_class}{xyz_class})"

            elif days_until_arrival <= 30:
                # Orders arriving soon - can be aggressive but add buffer for delays
                base_coverage_months = 2.5  # 1.5 base + 1.0 delay buffer
                confidence_factor = 0.8  # High confidence for near-term orders
                base_retention = base_coverage_months * burnaby_demand
                pending_reduction = burnaby_pending * confidence_factor

                # Minimum retention of 1.0 months to account for potential delays
                min_retention = 1.0 * burnaby_demand
                burnaby_min_retain = max(min_retention, base_retention - pending_reduction)

                retention_reason = f"Pending arrival in {days_until_arrival}d - {burnaby_min_retain/burnaby_demand:.1f}m retention ({abc_class}{xyz_class})"

            else:  # 31-60 days away
                # Orders in pipeline but not imminent - moderate retention with delay buffer
                base_coverage_months = 3.5  # 2.5 base + 1.0 delay buffer
                confidence_factor = 0.5  # Medium confidence for medium-term orders
                base_retention = base_coverage_months * burnaby_demand
                pending_reduction = burnaby_pending * confidence_factor

                # Minimum retention of 1.5 months for distant orders
                min_retention = 1.5 * burnaby_demand
                burnaby_min_retain = max(min_retention, base_retention - pending_reduction)

                retention_reason = f"Pending arrival in {days_until_arrival}d - {burnaby_min_retain/burnaby_demand:.1f}m retention ({abc_class}{xyz_class})"

            # Calculate available for transfer
            available_for_transfer = max(0, burnaby_qty - burnaby_min_retain)

            # Calculate coverage after considering pending
            total_available = burnaby_qty + burnaby_pending
            coverage_with_pending = total_available / max(burnaby_demand, 1)

            return {
                'burnaby_min_retain': int(burnaby_min_retain),
                'available_for_transfer': int(available_for_transfer),
                'retention_reason': retention_reason,
                'coverage_with_pending': round(coverage_with_pending, 1),
                'burnaby_pending': burnaby_pending,
                'abc_class': abc_class,
                'xyz_class': xyz_class,
                'base_coverage_months': base_coverage_months
            }

        except Exception as e:
            logger.error(f"Burnaby retention calculation failed: {e}")
            # Safe fallback using classification if possible, otherwise use default
            try:
                fallback_coverage = self.get_coverage_target(abc_class, xyz_class)
            except:
                fallback_coverage = 2.0  # Safe fallback

            burnaby_min_retain = burnaby_demand * fallback_coverage
            return {
                'burnaby_min_retain': int(burnaby_min_retain),
                'available_for_transfer': max(0, int(burnaby_qty - burnaby_min_retain)),
                'retention_reason': f"Fallback retention calculation ({abc_class}{xyz_class}: {fallback_coverage} months)",
                'abc_class': abc_class,
                'xyz_class': xyz_class,
                'base_coverage_months': fallback_coverage,
                'coverage_with_pending': burnaby_qty / max(burnaby_demand, 1),
                'burnaby_pending': 0
            }

    def calculate_transfer_recommendation(self, sku_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate transfer recommendation for a single SKU
        
        Args:
            sku_data: Dictionary containing SKU information
        
        Returns:
            Dictionary with transfer recommendation
        """
        try:
            # Extract data
            sku_id = sku_data['sku_id']
            burnaby_qty = sku_data.get('burnaby_qty', 0)
            kentucky_qty = sku_data.get('kentucky_qty', 0)
            kentucky_sales = sku_data.get('kentucky_sales', 0)
            burnaby_sales = sku_data.get('burnaby_sales', 0)
            kentucky_stockout_days = sku_data.get('kentucky_stockout_days', 0)
            burnaby_stockout_days = sku_data.get('burnaby_stockout_days', 0)
            abc_class = sku_data.get('abc_code', 'C')
            xyz_class = sku_data.get('xyz_code', 'Z')
            transfer_multiple = sku_data.get('transfer_multiple', 50)

            # Calculate corrected demand for Kentucky using enhanced method
            kentucky_corrected_demand = self.corrector.correct_monthly_demand_enhanced(
                sku_id, kentucky_sales, kentucky_stockout_days, '2024-03'
            )

            # Calculate corrected demand for Burnaby using its own stockout data
            burnaby_corrected_demand = self.corrector.correct_monthly_demand_enhanced(
                sku_id, burnaby_sales, burnaby_stockout_days, '2024-03'
            )

            # Update database with corrected demand for both warehouses
            database.update_corrected_demand(sku_id, '2024-03', kentucky_corrected_demand, 'kentucky')
            database.update_corrected_demand(sku_id, '2024-03', burnaby_corrected_demand, 'burnaby')

            # Calculate target inventory using Kentucky demand (since we're transferring TO Kentucky)
            coverage_months = self.get_coverage_target(abc_class, xyz_class)
            target_inventory = kentucky_corrected_demand * coverage_months

            # Account for pending inventory with time-weighted quantities
            kentucky_pending = get_pending_quantities(sku_id, 'kentucky')
            pending_qty = kentucky_pending['total_weighted']

            # Calculate transfer need considering weighted pending orders
            current_position = kentucky_qty + pending_qty
            transfer_need = target_inventory - current_position

            # Calculate Burnaby availability using Burnaby-specific corrected demand for retention
            burnaby_coverage_multiplier = calculate_burnaby_coverage_multiplier(sku_id)
            burnaby_min_retain = burnaby_corrected_demand * 2 * burnaby_coverage_multiplier  # 2 months base coverage

            # Available for transfer from Burnaby (never go below minimum retention)
            burnaby_available = max(0, burnaby_qty - burnaby_min_retain)
            available_to_transfer = min(transfer_need, burnaby_available)
            
            # Round to multiple, ensuring we don't exceed available inventory
            recommended_qty = self.round_to_multiple(available_to_transfer, transfer_multiple, burnaby_qty)
            
            # Calculate priority using Kentucky corrected demand
            if kentucky_qty == 0:
                priority = "CRITICAL"
            elif kentucky_qty / max(kentucky_corrected_demand, 1) < 1:  # Less than 1 month coverage
                priority = "HIGH"
            elif kentucky_qty / max(kentucky_corrected_demand, 1) < 2:  # Less than 2 months coverage
                priority = "MEDIUM"
            else:
                priority = "LOW"

            # Create reason with warehouse-specific stockout information
            reason_parts = []
            if kentucky_stockout_days > 0:
                reason_parts.append(f"Kentucky stockout correction applied ({kentucky_stockout_days} days out)")
            if burnaby_stockout_days > 0:
                reason_parts.append(f"Burnaby stockout correction applied ({burnaby_stockout_days} days out)")
            if kentucky_qty == 0:
                reason_parts.append("Currently out of stock")
            elif kentucky_qty / max(kentucky_corrected_demand, 1) < coverage_months:
                reason_parts.append(f"Below target coverage ({coverage_months:.1f} months)")

            reason = "; ".join(reason_parts) if reason_parts else "Maintain optimal stock level"
            
            # Get Burnaby pending data for coverage calculations
            burnaby_pending = get_pending_quantities(sku_id, 'burnaby')

            return {
                'sku_id': sku_id,
                'description': sku_data.get('description', ''),
                'supplier': sku_data.get('supplier', ''),
                'status': sku_data.get('status', 'Active'),
                'current_kentucky_qty': kentucky_qty,
                'current_burnaby_qty': burnaby_qty,
                'corrected_monthly_demand': kentucky_corrected_demand,
                'corrected_burnaby_demand': burnaby_corrected_demand,
                'recommended_transfer_qty': recommended_qty,
                'coverage_months': round(kentucky_qty / max(kentucky_corrected_demand, 1), 1),
                'target_coverage_months': coverage_months,
                'priority': priority,
                'reason': reason,
                'abc_class': abc_class,
                'xyz_class': xyz_class,
                'transfer_multiple': transfer_multiple,
                'kentucky_stockout_days': kentucky_stockout_days,
                'burnaby_stockout_days': burnaby_stockout_days,

                # Pending orders data
                'pending_kentucky_qty': kentucky_pending['total_weighted'],
                'pending_burnaby_qty': burnaby_pending['total_weighted'],
                'pending_kentucky_timeline': {
                    'immediate': kentucky_pending['immediate'],
                    'near_term': kentucky_pending['near_term'],
                    'medium_term': kentucky_pending['medium_term'],
                    'long_term': kentucky_pending['long_term'],
                    'earliest_arrival': kentucky_pending['earliest_arrival'],
                    'shipment_count': kentucky_pending['shipment_count']
                },
                'pending_burnaby_timeline': {
                    'immediate': burnaby_pending['immediate'],
                    'near_term': burnaby_pending['near_term'],
                    'medium_term': burnaby_pending['medium_term'],
                    'long_term': burnaby_pending['long_term'],
                    'earliest_arrival': burnaby_pending['earliest_arrival'],
                    'shipment_count': burnaby_pending['shipment_count']
                },
                'pending_impact_on_transfer': f"KY position adjusted by +{kentucky_pending['total_weighted']:.0f} (weighted), Burnaby coverage multiplier: {burnaby_coverage_multiplier}x",

                # Enhanced coverage calculations
                'current_position_with_pending': current_position,
                'burnaby_coverage_multiplier': burnaby_coverage_multiplier,
                'burnaby_min_retain': burnaby_min_retain,
                'burnaby_available_for_transfer': burnaby_available
            }
            
        except Exception as e:
            logger.error(f"Calculation failed for SKU {sku_data.get('sku_id', 'unknown')}: {e}")
            return None

    def calculate_enhanced_transfer_recommendation(self, sku_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate transfer recommendation with enhanced seasonal and growth adjustments

        Args:
            sku_data: Dictionary containing SKU information

        Returns:
            Dictionary with enhanced transfer recommendation
        """
        try:
            # Get basic recommendation first
            basic_rec = self.calculate_transfer_recommendation(sku_data)
            if not basic_rec:
                return None

            sku_id = sku_data['sku_id']
            current_month = datetime.now().month
            stockout_days = sku_data.get('kentucky_stockout_days', 0)

            # Detect and apply seasonal patterns
            seasonal_pattern = self.seasonal_detector.detect_seasonal_pattern(sku_id)
            seasonal_multiplier = self.seasonal_detector.get_seasonal_multiplier(seasonal_pattern, current_month)

            # Detect and apply growth patterns
            growth_status = self.growth_detector.detect_viral_growth(sku_id)
            growth_multiplier = self.growth_detector.get_growth_multiplier(growth_status)

            # Apply enhancements to demand
            base_demand = basic_rec['corrected_monthly_demand']
            enhanced_demand = base_demand * seasonal_multiplier * growth_multiplier

            # Recalculate target inventory with enhanced demand
            coverage_months = self.get_coverage_target(basic_rec['abc_class'], basic_rec['xyz_class'])
            enhanced_target = enhanced_demand * coverage_months

            # Recalculate transfer need
            kentucky_qty = basic_rec['current_kentucky_qty']
            transfer_need = enhanced_target - kentucky_qty
            available_to_transfer = min(transfer_need, basic_rec['current_burnaby_qty'])
            enhanced_transfer_qty = self.round_to_multiple(available_to_transfer, basic_rec['transfer_multiple'], basic_rec['current_burnaby_qty'])

            # Check for seasonal pre-positioning needs
            seasonal_positioning = self.get_seasonal_pre_positioning(sku_id, seasonal_pattern, current_month)

            # Apply seasonal pre-positioning multiplier if needed
            final_demand = enhanced_demand
            if seasonal_positioning['needs_pre_positioning']:
                pre_position_multiplier = seasonal_positioning['multiplier']
                final_demand = enhanced_demand * pre_position_multiplier

                # Recalculate transfer need with pre-positioning
                coverage_months = self.get_coverage_target(basic_rec['abc_class'], basic_rec['xyz_class'])
                pre_position_target = final_demand * coverage_months
                transfer_need = pre_position_target - kentucky_qty
                available_to_transfer = min(transfer_need, basic_rec['current_burnaby_qty'])
                enhanced_transfer_qty = self.round_to_multiple(available_to_transfer, basic_rec['transfer_multiple'], basic_rec['current_burnaby_qty'])

            # Calculate priority score using new scoring system
            score_data = {
                'kentucky_stockout_days': stockout_days,
                'kentucky_qty': kentucky_qty,
                'corrected_demand': final_demand,
                'abc_code': basic_rec['abc_class'],
                'growth_status': growth_status
            }
            priority_analysis = self.calculate_priority_score(score_data)
            enhanced_priority = priority_analysis['priority_level']

            # Generate detailed transfer reason
            reason_factors = {
                'base_reason': basic_rec['reason'],
                'stockout_days': stockout_days,
                'growth_status': growth_status,
                'seasonal_info': seasonal_positioning,
                'current_coverage': kentucky_qty / max(final_demand, 1),
                'target_coverage': coverage_months,
                'abc_class': basic_rec['abc_class'],
                'kentucky_qty': kentucky_qty
            }
            enhanced_reason = self.generate_detailed_transfer_reason(reason_factors)

            # Update database with patterns
            self._update_sku_patterns(sku_id, seasonal_pattern, growth_status)

            # Create enhanced recommendation
            enhanced_rec = basic_rec.copy()
            enhanced_rec.update({
                'corrected_monthly_demand': round(final_demand, 2),
                'recommended_transfer_qty': enhanced_transfer_qty,
                'priority': enhanced_priority,
                'reason': enhanced_reason,
                'seasonal_pattern': seasonal_pattern,
                'growth_status': growth_status,
                'seasonal_multiplier': round(seasonal_multiplier, 2),
                'growth_multiplier': round(growth_multiplier, 2),
                'coverage_months': round(kentucky_qty / max(final_demand, 1), 1),
                'enhanced_calculation': True,
                'seasonal_positioning': seasonal_positioning,
                'priority_analysis': priority_analysis
            })

            return enhanced_rec

        except Exception as e:
            logger.error(f"Enhanced calculation failed for SKU {sku_data.get('sku_id', 'unknown')}: {e}")
            # Fallback to basic calculation
            return self.calculate_transfer_recommendation(sku_data)

    def calculate_enhanced_transfer_with_economic_validation(self, sku_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate transfer recommendation with economic validation and weighted demand calculations

        This enhanced method now uses sophisticated weighted moving averages instead of single-month
        calculations to provide more stable and accurate demand predictions. It prevents transfers
        that would leave the source warehouse (Burnaby) understocked while incorporating pending
        orders data for accurate transfer calculations.

        Key Features:
        - Weighted demand integration: Uses WeightedDemandCalculator for stable demand predictions
        - Fallback mechanisms: Gracefully handles insufficient data with single-month calculations
        - Economic validation: prevents transfers when CA demand > KY demand * 1.5
        - Pending orders integration: accounts for incoming inventory in transfer calculations
        - Enhanced retention logic: adjusts Burnaby retention based on pending arrivals
        - Time-weighted pending calculations: considers arrival timing for accurate positioning
        - Comprehensive coverage calculations including pending orders
        - Detailed business justification with pending orders context

        Weighted Demand Integration:
        1. Attempts to calculate weighted demand for both Kentucky and Burnaby warehouses
        2. Uses 6-month weighted average for stable SKUs (ABC class A/B)
        3. Uses 3-month weighted average for volatile SKUs (XYZ class Z)
        4. Falls back to single-month stockout-corrected calculation for new SKUs
        5. Applies exponential decay weights to recent months for better forecasting
        6. Logs calculation method used for debugging and quality assurance

        Business Logic:
        1. Calculates weighted demand using WeightedDemandCalculator
        2. Retrieves pending orders data from v_pending_quantities view
        3. Calculates current position as kentucky_qty + kentucky_pending
        4. Adjusts Burnaby retention if significant pending arrivals expected
        5. Determines transfer need considering pending orders already in transit
        6. Provides comprehensive coverage metrics including pending orders impact

        Args:
            sku_data: Dictionary containing SKU information including sales and inventory data

        Returns:
            Dictionary with enhanced transfer recommendation including:
            - Weighted demand calculations for both warehouses
            - All economic validation fields
            - Pending orders data (kentucky_pending, burnaby_pending, days_until_arrival)
            - Coverage calculations with and without pending orders
            - Flag indicating if pending orders were successfully included
            - 6-month supply calculations for UI display

        Raises:
            ValueError: If required SKU data is missing or invalid

        Note:
            If weighted demand calculation fails, falls back to database values or single-month
            calculations. If pending orders data cannot be retrieved, continues with pending
            quantities = 0 and sets pending_orders_included = False for transparency.
        """
        try:
            # Extract SKU data with proper null handling
            sku_id = sku_data['sku_id']
            burnaby_qty = sku_data.get('burnaby_qty') or 0
            kentucky_qty = sku_data.get('kentucky_qty') or 0
            kentucky_sales = sku_data.get('kentucky_sales') or 0
            burnaby_sales = sku_data.get('burnaby_sales') or 0
            stockout_days = sku_data.get('kentucky_stockout_days') or 0
            burnaby_stockout_days = sku_data.get('burnaby_stockout_days') or 0
            abc_class = sku_data.get('abc_code', 'C')
            xyz_class = sku_data.get('xyz_code', 'Z')
            transfer_multiple = sku_data.get('transfer_multiple', 50)

            # Step 1: Get pending orders data for comprehensive calculations
            print(f"DEBUG: Processing SKU {sku_id} in calculate_enhanced_transfer_with_economic_validation")
            try:
                pending_data = self.get_pending_orders_data(sku_id)
                kentucky_pending = float(pending_data.get('kentucky_pending', 0))
                burnaby_pending = float(pending_data.get('burnaby_pending', 0))
                days_until_arrival = pending_data.get('days_until_arrival')
                pending_orders_included = True
                print(f"DEBUG: {sku_id} pending data retrieved: KY={kentucky_pending}, BY={burnaby_pending}")
            except Exception as e:
                logger.warning(f"Could not retrieve pending orders for SKU {sku_id}: {e}")
                # Fallback: continue without pending orders
                kentucky_pending = 0
                burnaby_pending = 0
                days_until_arrival = None
                pending_orders_included = False

            # Step 2: Use weighted demand calculations for more stable predictions
            # This replaces single-month calculations with weighted moving averages to reduce
            # the impact of monthly anomalies and provide more accurate demand forecasting
            try:
                # Get enhanced demand using WeightedDemandCalculator
                # Uses 6-month weighted average for stable SKUs, 3-month for volatile SKUs
                # Applies exponential decay weights (recent months weighted higher)
                kentucky_enhanced_result = self.weighted_demand_calculator.get_enhanced_demand_calculation(
                    sku_id, abc_class, xyz_class, kentucky_sales, stockout_days, warehouse='kentucky'
                )
                kentucky_corrected_demand = float(kentucky_enhanced_result.get('enhanced_demand', 0))

                # Fallback mechanism: If weighted calculation returns 0 or insufficient data,
                # use single-month calculation with stockout correction
                if kentucky_corrected_demand == 0 and kentucky_sales > 0:
                    current_month = datetime.now().strftime('%Y-%m')
                    kentucky_corrected_demand = self.corrector.correct_monthly_demand_enhanced(
                        sku_id, kentucky_sales, stockout_days, current_month
                    )
                    print(f"DEBUG: {sku_id} KY - fallback to single-month: {kentucky_corrected_demand:.2f}")
                else:
                    print(f"DEBUG: {sku_id} KY - using weighted demand: {kentucky_corrected_demand:.2f}")

            except Exception as e:
                logger.warning(f"WeightedDemandCalculator failed for KY {sku_id}: {e}")
                # Final fallback: Use database value or calculate single-month with stockout correction
                kentucky_corrected_demand = float(sku_data.get('corrected_demand_kentucky', 0) or 0)
                if kentucky_corrected_demand == 0 and kentucky_sales > 0:
                    current_month = datetime.now().strftime('%Y-%m')
                    kentucky_corrected_demand = self.corrector.correct_monthly_demand_enhanced(
                        sku_id, kentucky_sales, stockout_days, current_month
                    )

            # Calculate Burnaby demand using weighted calculation where applicable
            try:
                burnaby_enhanced_result = self.weighted_demand_calculator.get_enhanced_demand_calculation(
                    sku_id, abc_class, xyz_class, burnaby_sales, burnaby_stockout_days, warehouse='burnaby'
                )
                burnaby_corrected_demand = float(burnaby_enhanced_result.get('enhanced_demand', 0))

                # If weighted calculation returns 0 or fails, fallback to single-month with stockout correction
                if burnaby_corrected_demand == 0 and burnaby_sales > 0:
                    current_month = datetime.now().strftime('%Y-%m')
                    burnaby_corrected_demand = self.corrector.correct_monthly_demand_enhanced(
                        sku_id, burnaby_sales, burnaby_stockout_days, current_month
                    )
                    print(f"DEBUG: {sku_id} BY - fallback to single-month: {burnaby_corrected_demand:.2f}")
                else:
                    print(f"DEBUG: {sku_id} BY - using weighted demand: {burnaby_corrected_demand:.2f}")

            except Exception as e:
                logger.warning(f"WeightedDemandCalculator failed for BY {sku_id}: {e}")
                # Fallback to database value or single-month calculation
                burnaby_corrected_demand = float(sku_data.get('corrected_demand_burnaby', 0) or 0)
                if burnaby_corrected_demand == 0 and burnaby_sales > 0:
                    current_month = datetime.now().strftime('%Y-%m')
                    burnaby_corrected_demand = self.corrector.correct_monthly_demand_enhanced(
                        sku_id, burnaby_sales, burnaby_stockout_days, current_month
                    )

            # Step 3: Economic Validation - Don't transfer if CA demand significantly higher than KY
            economic_validation_passed = True
            economic_reason = ""

            if burnaby_corrected_demand > kentucky_corrected_demand * 1.5:
                economic_validation_passed = False
                economic_reason = f"CA demand ({burnaby_corrected_demand:.0f}) too high vs KY demand ({kentucky_corrected_demand:.0f}). Transfer would risk CA stockout."

            # Step 4: Calculate Burnaby minimum retention using dynamic approach
            # Same logic as calculate_burnaby_retention function

            # Lead time parameters based on business requirements
            supplier_lead_time_days = 100  # Average of 80-120 days supplier lead time
            review_period_days = 7  # Weekly ordering cycle
            total_replen_time_months = (supplier_lead_time_days + review_period_days) / 30  # ~3.5 months

            if days_until_arrival is None or days_until_arrival > 60 or burnaby_pending == 0:
                # NO PENDING ORDERS or too far away - Need full pipeline coverage
                burnaby_base_coverage = total_replen_time_months + 1.0  # 3.5 + 1 = 4.5 months safety

                # Adjust based on KY/CA demand ratio - if KY sells considerably more, can be more aggressive
                demand_ratio = 1.0
                if kentucky_corrected_demand > 0 and burnaby_corrected_demand > 0:
                    demand_ratio = kentucky_corrected_demand / burnaby_corrected_demand
                    if demand_ratio > 2.0:  # KY sells 2x+ more than CA
                        burnaby_base_coverage *= 0.7  # Reduce to ~3.15 months
                    elif demand_ratio > 1.5:  # KY sells 1.5x+ more than CA
                        burnaby_base_coverage *= 0.85  # Reduce to ~3.8 months

                burnaby_min_retain = burnaby_corrected_demand * burnaby_base_coverage

            elif days_until_arrival <= 30:
                # Orders arriving soon - can be aggressive but add buffer for delays
                burnaby_base_coverage = 2.5  # 1.5 base + 1.0 delay buffer
                confidence_factor = 0.8  # High confidence for near-term orders
                base_retention = burnaby_base_coverage * burnaby_corrected_demand
                pending_reduction = burnaby_pending * confidence_factor

                # Minimum retention of 1.0 months to account for potential delays
                min_retention = 1.0 * burnaby_corrected_demand
                burnaby_min_retain = max(min_retention, base_retention - pending_reduction)

            else:  # 31-60 days away
                # Orders in pipeline but not imminent - moderate retention with delay buffer
                burnaby_base_coverage = 3.5  # 2.5 base + 1.0 delay buffer
                confidence_factor = 0.5  # Medium confidence for medium-term orders
                base_retention = burnaby_base_coverage * burnaby_corrected_demand
                pending_reduction = burnaby_pending * confidence_factor

                # Minimum retention of 1.5 months for distant orders
                min_retention = 1.5 * burnaby_corrected_demand
                burnaby_min_retain = max(min_retention, base_retention - pending_reduction)

            available_for_transfer = max(0, burnaby_qty - burnaby_min_retain)

            # Step 5: Calculate transfer need for Kentucky considering pending orders
            coverage_months = self.get_coverage_target(abc_class, xyz_class)
            target_inventory = float(kentucky_corrected_demand) * float(coverage_months)
            current_position = float(kentucky_qty) + float(kentucky_pending)  # Include pending in current position
            transfer_need = max(0, target_inventory - current_position)

            # Step 6: Determine final transfer quantity
            if not economic_validation_passed:
                # Economic validation failed - no transfer
                final_transfer_qty = 0
                priority = "LOW"
                reason = economic_reason
            elif available_for_transfer <= 0:
                # Insufficient inventory after retention
                final_transfer_qty = 0
                priority = "LOW" if kentucky_qty > kentucky_corrected_demand else "MEDIUM"
                # Calculate actual retention period for message
                actual_retention_months = burnaby_min_retain / burnaby_corrected_demand if burnaby_corrected_demand > 0 else 0
                reason = f"Insufficient CA inventory for transfer. CA needs {burnaby_min_retain:.0f} for {actual_retention_months:.1f}-month coverage, only has {burnaby_qty}"
            else:
                # Normal transfer calculation
                recommended_qty = min(transfer_need, available_for_transfer)
                final_transfer_qty = self.round_to_multiple(recommended_qty, transfer_multiple, burnaby_qty)

                # Calculate priority based on Kentucky situation
                if kentucky_qty == 0:
                    priority = "CRITICAL"
                elif kentucky_qty < kentucky_corrected_demand:
                    priority = "HIGH"
                elif kentucky_qty < kentucky_corrected_demand * 2:
                    priority = "MEDIUM"
                else:
                    priority = "LOW"

                # Generate comprehensive reason
                if final_transfer_qty > 0:
                    # Calculate actual CA retention after transfer (not minimum requirement)
                    ca_remaining_qty = burnaby_qty - final_transfer_qty
                    ca_coverage_months = ca_remaining_qty / burnaby_corrected_demand if burnaby_corrected_demand > 0 else 0
                    reason = f"Transfer {final_transfer_qty} units. CA retains {ca_remaining_qty:.0f} for {ca_coverage_months:.1f}-month coverage. Economic validation passed."
                else:
                    reason = f"No transfer needed. KY has {kentucky_qty} units vs {kentucky_corrected_demand:.0f} monthly demand."

            # Step 7: Calculate coverage after transfer
            burnaby_coverage_after = (burnaby_qty - final_transfer_qty) / max(burnaby_corrected_demand, 1)
            kentucky_coverage_after = (kentucky_qty + final_transfer_qty) / max(kentucky_corrected_demand, 1)
            # Coverage including pending orders
            kentucky_coverage_with_pending = (current_position + final_transfer_qty) / max(kentucky_corrected_demand, 1)

            # Step 8: Return comprehensive recommendation including pending orders and confirmation data
            return {
                'sku_id': sku_id,
                'description': sku_data.get('description', ''),
                'supplier': sku_data.get('supplier', ''),
                'status': sku_data.get('status', 'Active'),
                'current_burnaby_qty': burnaby_qty,
                'current_kentucky_qty': kentucky_qty,
                'corrected_monthly_demand': kentucky_corrected_demand,
                'kentucky_6month_supply': round(kentucky_corrected_demand * 6, 0),
                'burnaby_corrected_demand': burnaby_corrected_demand,
                'burnaby_monthly_demand': burnaby_corrected_demand,
                'burnaby_6month_supply': round(burnaby_corrected_demand * 6, 0),
                'recommended_transfer_qty': final_transfer_qty,
                'transfer_multiple': transfer_multiple,
                'priority': priority,
                'reason': reason,
                'abc_class': abc_class,
                'xyz_class': xyz_class,
                'stockout_days': stockout_days,
                'coverage_months': kentucky_qty / max(kentucky_corrected_demand, 1),
                'target_coverage_months': coverage_months,
                'burnaby_coverage_after_transfer': round(burnaby_coverage_after, 1),
                'kentucky_coverage_after_transfer': round(kentucky_coverage_after, 1),
                'kentucky_coverage_with_pending': round(kentucky_coverage_with_pending, 1),
                'economic_validation_passed': economic_validation_passed,
                'available_from_burnaby': available_for_transfer,
                'burnaby_min_retain': burnaby_min_retain,

                # Pending orders data
                'kentucky_pending': kentucky_pending,
                'burnaby_pending': burnaby_pending,
                'days_until_arrival': days_until_arrival,
                'pending_orders_included': pending_orders_included,
                'current_position_with_pending': current_position,

                # Transfer confirmation data
                'confirmed_qty': sku_data.get('confirmed_qty'),
                'original_suggested_qty': sku_data.get('original_suggested_qty'),
                'confirmed_by': sku_data.get('confirmed_by'),
                'confirmed_at': sku_data.get('confirmed_at'),
                'confirmation_notes': sku_data.get('confirmation_notes'),
                'ca_order_qty': sku_data.get('ca_order_qty'),
                'ky_order_qty': sku_data.get('ky_order_qty'),
                'variance_percent': sku_data.get('variance_percent', 0),
                'is_confirmed': bool(sku_data.get('confirmed_qty') is not None),
                'has_significant_variance': abs(sku_data.get('variance_percent', 0)) > 20,
                'has_major_variance': abs(sku_data.get('variance_percent', 0)) > 50,

                # Stockout status data
                'kentucky_stockout': bool(sku_data.get('kentucky_stockout', 0)),
                'burnaby_stockout': bool(sku_data.get('burnaby_stockout', 0))
            }

        except Exception as e:
            import traceback
            logger.error(f"Enhanced transfer calculation with economic validation failed for SKU {sku_id}: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Return safe fallback
            return {
                'sku_id': sku_id,
                'description': sku_data.get('description', ''),
                'supplier': sku_data.get('supplier', ''),
                'status': sku_data.get('status', 'Active'),
                'current_burnaby_qty': burnaby_qty,
                'current_kentucky_qty': kentucky_qty,
                'corrected_monthly_demand': 0,
                'burnaby_corrected_demand': 0,
                'burnaby_monthly_demand': 0,
                'burnaby_6month_supply': 0,
                'recommended_transfer_qty': 0,
                'transfer_multiple': transfer_multiple,
                'priority': "LOW",
                'reason': f"Calculation error: {str(e)}",
                'abc_class': abc_class,
                'xyz_class': xyz_class,
                'stockout_days': 0,
                'coverage_months': 0,
                'target_coverage_months': self.get_coverage_target(abc_class, xyz_class),
                'burnaby_coverage_after_transfer': 0,
                'kentucky_coverage_after_transfer': 0,
                'kentucky_coverage_with_pending': 0,
                'economic_validation_passed': False,
                'available_from_burnaby': 0,
                'burnaby_min_retain': 0,

                # Pending orders data - retrieve actual values even in exception case
                # Try to fetch from database since we're in fallback mode
                **self._get_pending_data_fallback(sku_id, kentucky_qty),

                # Transfer confirmation data (fallback values)
                'confirmed_qty': sku_data.get('confirmed_qty'),
                'original_suggested_qty': sku_data.get('original_suggested_qty'),
                'confirmed_by': sku_data.get('confirmed_by'),
                'confirmed_at': sku_data.get('confirmed_at'),
                'confirmation_notes': sku_data.get('confirmation_notes'),
                'ca_order_qty': sku_data.get('ca_order_qty'),
                'ky_order_qty': sku_data.get('ky_order_qty'),
                'variance_percent': sku_data.get('variance_percent', 0),
                'is_confirmed': bool(sku_data.get('confirmed_qty') is not None),
                'has_significant_variance': abs(sku_data.get('variance_percent', 0)) > 20,
                'has_major_variance': abs(sku_data.get('variance_percent', 0)) > 50,

                # Stockout status data (fallback values)
                'kentucky_stockout': bool(sku_data.get('kentucky_stockout', 0)),
                'burnaby_stockout': bool(sku_data.get('burnaby_stockout', 0))
            }

    def calculate_enhanced_transfer_with_pending(self, sku_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate transfer recommendation with full pending orders and stockout override support

        This method incorporates:
        - Pending orders data from v_pending_quantities view
        - Burnaby retention logic with configurable coverage
        - Stockout overrides for Kentucky quantities
        - Enhanced seasonal and growth patterns
        - Comprehensive priority scoring

        Args:
            sku_data: Dictionary containing SKU information

        Returns:
            Dictionary with comprehensive transfer recommendation
        """
        try:
            sku_id = sku_data['sku_id']
            burnaby_qty = sku_data.get('burnaby_qty', 0)
            kentucky_qty = sku_data.get('kentucky_qty', 0)
            kentucky_sales = sku_data.get('kentucky_sales', 0)
            burnaby_sales = sku_data.get('burnaby_sales', 0)
            stockout_days = sku_data.get('kentucky_stockout_days', 0)
            burnaby_stockout_days = sku_data.get('burnaby_stockout_days', 0)
            abc_class = sku_data.get('abc_code', 'C')
            xyz_class = sku_data.get('xyz_code', 'Z')
            transfer_multiple = sku_data.get('transfer_multiple', 50)

            # Step 1: Get pending orders data
            pending_data = self.get_pending_orders_data(sku_id)

            # Step 2: Check for stockout overrides
            kentucky_override = self.check_stockout_override(sku_id, 'kentucky')
            burnaby_override = self.check_stockout_override(sku_id, 'burnaby')

            # Step 3: Apply stockout overrides to quantities
            effective_kentucky_qty = 0 if kentucky_override['is_overridden'] else kentucky_qty
            effective_burnaby_qty = 0 if burnaby_override['is_overridden'] else burnaby_qty

            # Step 4: Calculate enhanced demand for Kentucky using weighted averages
            kentucky_enhanced_result = self.weighted_demand_calculator.get_enhanced_demand_calculation(
                sku_id, abc_class, xyz_class, kentucky_sales, stockout_days
            )
            kentucky_corrected_demand = kentucky_enhanced_result['enhanced_demand']

            # Store weighted demand calculation details for transparency
            weighted_demand_info = {
                'calculation_method': kentucky_enhanced_result.get('calculation_method', 'unknown'),
                'volatility_class': kentucky_enhanced_result.get('volatility_class', 'unknown'),
                'data_quality_score': kentucky_enhanced_result.get('data_quality_score', 0.0),
                'strategy_reason': kentucky_enhanced_result.get('strategy_reason', '')
            }

            # Calculate Burnaby demand for retention calculation (keep existing method for now)
            burnaby_corrected_demand = self.corrector.correct_monthly_demand_enhanced(
                sku_id, burnaby_sales, burnaby_stockout_days, datetime.now().strftime('%Y-%m')
            )

            # Step 5: Calculate Burnaby retention with pending orders and ABC-XYZ classification
            burnaby_retention = self.calculate_burnaby_retention(
                effective_burnaby_qty, burnaby_corrected_demand, pending_data, abc_class, xyz_class
            )

            # Step 6: Apply seasonal and growth patterns
            current_month = datetime.now().month
            seasonal_pattern = self.seasonal_detector.detect_seasonal_pattern(sku_id)
            seasonal_multiplier = self.seasonal_detector.get_seasonal_multiplier(seasonal_pattern, current_month)

            growth_status = self.growth_detector.detect_viral_growth(sku_id)
            growth_multiplier = self.growth_detector.get_growth_multiplier(growth_status)

            # Apply enhancements to demand
            enhanced_kentucky_demand = kentucky_corrected_demand * seasonal_multiplier * growth_multiplier

            # Step 7: Calculate target inventory considering pending orders
            coverage_months = self.get_coverage_target(abc_class, xyz_class)
            target_inventory = enhanced_kentucky_demand * coverage_months

            # Account for pending Kentucky orders
            kentucky_pending = pending_data.get('kentucky_pending', 0)
            current_position = effective_kentucky_qty + kentucky_pending

            # Step 8: Calculate transfer need
            transfer_need = max(0, target_inventory - current_position)

            # Step 9: Apply Burnaby availability constraint
            available_from_burnaby = burnaby_retention['available_for_transfer']
            recommended_qty = min(transfer_need, available_from_burnaby)

            # Step 10: Round to multiple and apply minimum threshold, ensuring availability
            final_transfer_qty = self.round_to_multiple(recommended_qty, transfer_multiple, burnaby_qty)

            # Step 11: Calculate priority with comprehensive scoring
            score_data = {
                'kentucky_stockout_days': stockout_days,
                'kentucky_qty': effective_kentucky_qty,
                'corrected_demand': enhanced_kentucky_demand,
                'abc_code': abc_class,
                'growth_status': growth_status
            }
            priority_analysis = self.calculate_priority_score(score_data)

            # Step 12: Calculate coverage metrics
            current_coverage = effective_kentucky_qty / max(enhanced_kentucky_demand, 1)
            coverage_after_transfer = (effective_kentucky_qty + final_transfer_qty) / max(enhanced_kentucky_demand, 1)
            coverage_after_pending = (current_position + final_transfer_qty) / max(enhanced_kentucky_demand, 1)

            # Step 13: Generate comprehensive reason
            reason_factors = {
                'pending_orders': pending_data,
                'stockout_overrides': {
                    'kentucky': kentucky_override,
                    'burnaby': burnaby_override
                },
                'burnaby_retention': burnaby_retention,
                'stockout_days': stockout_days,
                'growth_status': growth_status,
                'seasonal_info': {
                    'pattern': seasonal_pattern,
                    'multiplier': seasonal_multiplier
                },
                'current_coverage': current_coverage,
                'target_coverage': coverage_months,
                'abc_class': abc_class,
                'kentucky_qty': effective_kentucky_qty
            }
            comprehensive_reason = self.generate_comprehensive_transfer_reason(reason_factors)

            # Step 14: Assemble comprehensive result
            result = {
                'sku_id': sku_id,
                'description': sku_data.get('description', ''),
                'supplier': sku_data.get('supplier', ''),
                'status': sku_data.get('status', 'Active'),

                # Current state
                'current_kentucky_qty': kentucky_qty,
                'effective_kentucky_qty': effective_kentucky_qty,
                'current_burnaby_qty': burnaby_qty,
                'effective_burnaby_qty': effective_burnaby_qty,

                # Pending orders
                'kentucky_pending': kentucky_pending,
                'burnaby_pending': pending_data.get('burnaby_pending', 0),
                'days_until_arrival': pending_data.get('days_until_arrival'),

                # Demand calculations
                'corrected_monthly_demand': round(enhanced_kentucky_demand, 2),
                'kentucky_6month_supply': round(enhanced_kentucky_demand * 6, 0),  # Add 6-month supply for UI display
                'seasonal_multiplier': round(seasonal_multiplier, 2),
                'growth_multiplier': round(growth_multiplier, 2),

                # Transfer recommendation
                'recommended_transfer_qty': final_transfer_qty,
                'available_from_burnaby': available_from_burnaby,
                'burnaby_min_retain': burnaby_retention['burnaby_min_retain'],

                # Coverage analysis
                'coverage_months': round(current_coverage, 1),
                'coverage_after_transfer': round(coverage_after_transfer, 1),
                'coverage_after_pending': round(coverage_after_pending, 1),
                'target_coverage_months': coverage_months,

                # Priority and classification
                'priority': priority_analysis['priority_level'],
                'priority_score': priority_analysis.get('total_score', 0),
                'abc_class': abc_class,
                'xyz_class': xyz_class,

                # Additional metadata
                'seasonal_pattern': seasonal_pattern,
                'growth_status': growth_status,
                'stockout_days': stockout_days,
                'transfer_multiple': transfer_multiple,
                'reason': comprehensive_reason,
                'enhanced_calculation': True,
                'pending_orders_included': True,
                'weighted_demand_enabled': True,
                'stockout_overrides_applied': kentucky_override['is_overridden'] or burnaby_override['is_overridden'],

                # Weighted demand calculation details
                'weighted_demand_info': weighted_demand_info,

                # Override details
                'kentucky_override': kentucky_override,
                'burnaby_override': burnaby_override,
                'burnaby_retention_details': burnaby_retention
            }

            # Update database with detected patterns
            self._update_sku_patterns(sku_id, seasonal_pattern, growth_status)

            return result

        except Exception as e:
            logger.error(f"Comprehensive enhanced calculation failed for SKU {sku_data.get('sku_id', 'unknown')}: {e}")
            # Fallback to existing enhanced calculation
            return self.calculate_enhanced_transfer_recommendation(sku_data)

    def generate_comprehensive_transfer_reason(self, factors: Dict[str, Any]) -> str:
        """
        Generate detailed transfer reason incorporating all enhancement factors

        Args:
            factors: Dictionary containing all reason factors

        Returns:
            Comprehensive reason string
        """
        try:
            reason_parts = []

            # Stockout override information
            kentucky_override = factors.get('stockout_overrides', {}).get('kentucky', {})
            if kentucky_override.get('is_overridden'):
                reason_parts.append("🚨 Kentucky marked as out-of-stock (quantity overridden to 0)")

            # Stockout correction information
            stockout_days = factors.get('stockout_days', 0)
            if stockout_days > 20:
                reason_parts.append(f"📊 Severe stockout correction applied ({stockout_days} days out)")
            elif stockout_days > 10:
                reason_parts.append(f"📊 Stockout correction applied ({stockout_days} days out)")

            # Pending orders impact
            pending_orders = factors.get('pending_orders', {})
            kentucky_pending = pending_orders.get('kentucky_pending', 0)
            days_until_arrival = pending_orders.get('days_until_arrival')

            if kentucky_pending > 0 and days_until_arrival:
                if days_until_arrival < 15:
                    reason_parts.append(f"📦 Pending order ({kentucky_pending} units) arriving in {days_until_arrival} days")
                elif days_until_arrival < 45:
                    reason_parts.append(f"📦 Pending order ({kentucky_pending} units) arriving in {days_until_arrival} days")

            # Burnaby retention impact
            burnaby_retention = factors.get('burnaby_retention', {})
            retention_reason = burnaby_retention.get('retention_reason', '')
            if 'Reduced retention' in retention_reason:
                reason_parts.append("🏭 Burnaby retention reduced due to imminent pending arrival")

            # Growth pattern
            growth_status = factors.get('growth_status', 'normal')
            if growth_status == 'viral':
                reason_parts.append("📈 Viral growth detected - increased priority")
            elif growth_status == 'declining':
                reason_parts.append("📉 Declining trend noted")

            # Seasonal information
            seasonal_info = factors.get('seasonal_info', {})
            seasonal_pattern = seasonal_info.get('pattern', 'year_round')
            seasonal_multiplier = seasonal_info.get('multiplier', 1.0)

            if seasonal_pattern != 'year_round' and seasonal_multiplier > 1.1:
                reason_parts.append(f"🌟 Seasonal peak approaching ({seasonal_pattern} pattern)")

            # Coverage analysis
            current_coverage = factors.get('current_coverage', 0)
            target_coverage = factors.get('target_coverage', 6)
            abc_class = factors.get('abc_class', 'C')

            if factors.get('kentucky_qty', 0) == 0:
                reason_parts.append("🔴 Currently out of stock")
            elif current_coverage < 1:
                reason_parts.append(f"⚠️ Below 1 month coverage (Class {abc_class}: target {target_coverage:.1f} months)")
            elif current_coverage < target_coverage:
                reason_parts.append(f"📊 Below target coverage (Class {abc_class}: target {target_coverage:.1f} months)")

            # Combine all reasons
            if reason_parts:
                return " | ".join(reason_parts)
            else:
                return "📊 Maintain optimal stock level with pending orders consideration"

        except Exception as e:
            logger.error(f"Failed to generate comprehensive reason: {e}")
            return "📊 Enhanced transfer calculation with pending orders"

    def _calculate_enhanced_priority(self, kentucky_qty: int, enhanced_demand: float,
                                   growth_status: str, seasonal_pattern: str, stockout_days: int) -> str:
        """
        Calculate priority with enhanced factors

        Args:
            kentucky_qty: Current Kentucky quantity
            enhanced_demand: Enhanced demand calculation
            growth_status: Growth status (viral, normal, declining)
            seasonal_pattern: Seasonal pattern
            stockout_days: Stockout days

        Returns:
            Priority level string
        """
        if kentucky_qty == 0:
            return "CRITICAL"

        # Calculate coverage in months
        coverage_months = kentucky_qty / max(enhanced_demand, 1)

        # Base priority on coverage
        if coverage_months < 0.5:
            base_priority = "CRITICAL"
        elif coverage_months < 1.0:
            base_priority = "HIGH"
        elif coverage_months < 2.0:
            base_priority = "MEDIUM"
        else:
            base_priority = "LOW"

        # Upgrade priority for special cases
        if growth_status == 'viral' and base_priority != "CRITICAL":
            # Upgrade viral products by one level
            priority_upgrade = {"LOW": "MEDIUM", "MEDIUM": "HIGH", "HIGH": "CRITICAL"}
            base_priority = priority_upgrade.get(base_priority, base_priority)

        if stockout_days > 15 and base_priority in ["MEDIUM", "LOW"]:
            # Upgrade items with long stockout history
            base_priority = "HIGH"

        return base_priority

    def _generate_enhanced_reason(self, base_reason: str, seasonal_pattern: str, growth_status: str,
                                seasonal_multiplier: float, growth_multiplier: float) -> str:
        """
        Generate enhanced reason string with pattern information

        Args:
            base_reason: Original reason
            seasonal_pattern: Detected seasonal pattern
            growth_status: Growth status
            seasonal_multiplier: Seasonal adjustment factor
            growth_multiplier: Growth adjustment factor

        Returns:
            Enhanced reason string
        """
        reason_parts = [base_reason]

        # Add seasonal information
        if seasonal_pattern != 'year_round' and seasonal_multiplier != 1.0:
            if seasonal_multiplier > 1.1:
                reason_parts.append(f"Seasonal peak period ({seasonal_pattern})")
            elif seasonal_multiplier < 0.9:
                reason_parts.append(f"Seasonal low period ({seasonal_pattern})")

        # Add growth information
        if growth_status == 'viral':
            reason_parts.append("Viral growth detected (2x recent demand)")
        elif growth_status == 'declining':
            reason_parts.append("Declining trend detected")

        # Add adjustment information if significant
        total_adjustment = seasonal_multiplier * growth_multiplier
        if total_adjustment > 1.2:
            reason_parts.append(f"Demand adjusted up {(total_adjustment-1)*100:.0f}%")
        elif total_adjustment < 0.8:
            reason_parts.append(f"Demand adjusted down {(1-total_adjustment)*100:.0f}%")

        return "; ".join(reason_parts)

    def get_seasonal_pre_positioning(self, sku_id: str, seasonal_pattern: str, current_month: int) -> Dict[str, Any]:
        """
        Determine if SKU needs seasonal pre-positioning for upcoming peak seasons

        Args:
            sku_id: SKU identifier
            seasonal_pattern: Detected seasonal pattern
            current_month: Current month (1-12)

        Returns:
            Dictionary with pre-positioning recommendation
        """
        try:
            # Define peak months for each seasonal pattern
            peak_months = {
                'spring_summer': [4, 5, 6, 7],  # Apr-Jul
                'fall_winter': [10, 11, 12, 1, 2],  # Oct-Feb
                'holiday': [11, 12],  # Nov-Dec
                'year_round': []  # No specific peaks
            }

            if seasonal_pattern not in peak_months:
                return {'needs_pre_positioning': False, 'reason': 'No seasonal pattern detected'}

            peaks = peak_months[seasonal_pattern]
            if not peaks:
                return {'needs_pre_positioning': False, 'reason': 'Year-round demand pattern'}

            # Check if we're 1-2 months before a peak
            needs_positioning = False
            upcoming_peak = None
            months_ahead = 0

            for peak_month in peaks:
                # Calculate months ahead (handle year wrap-around)
                if peak_month >= current_month:
                    diff = peak_month - current_month
                else:
                    diff = (12 - current_month) + peak_month

                # Pre-position 1-2 months ahead
                if 1 <= diff <= 2:
                    needs_positioning = True
                    upcoming_peak = peak_month
                    months_ahead = diff
                    break

            if needs_positioning:
                season_name = seasonal_pattern.replace('_', ' ').title()
                peak_month_name = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][upcoming_peak]

                return {
                    'needs_pre_positioning': True,
                    'seasonal_pattern': seasonal_pattern,
                    'upcoming_peak_month': upcoming_peak,
                    'months_ahead': months_ahead,
                    'reason': f"Pre-position for {season_name} season (peak in {peak_month_name})",
                    'multiplier': 1.3 if months_ahead == 1 else 1.2  # Stronger positioning closer to peak
                }
            else:
                return {'needs_pre_positioning': False, 'reason': 'No upcoming seasonal peak within 2 months'}

        except Exception as e:
            logger.error(f"Seasonal pre-positioning check failed for {sku_id}: {e}")
            return {'needs_pre_positioning': False, 'reason': 'Error in seasonal analysis'}

    def generate_detailed_transfer_reason(self, factors: Dict[str, Any]) -> str:
        """
        Generate detailed, contextual transfer reason with business justification

        Args:
            factors: Dictionary containing various factors affecting the transfer decision
                - base_reason: Original transfer reason
                - stockout_days: Number of stockout days
                - growth_status: Growth classification (viral, normal, declining)
                - seasonal_info: Pre-positioning information
                - current_coverage: Coverage months
                - abc_class: ABC classification
                - kentucky_qty: Current Kentucky quantity

        Returns:
            Detailed transfer reason string
        """
        try:
            reason_components = []

            # Start with urgency level based on current stock
            kentucky_qty = factors.get('kentucky_qty', 0)
            if kentucky_qty == 0:
                reason_components.append("CRITICAL: Currently out of stock")
            elif factors.get('current_coverage', 0) < 0.5:
                reason_components.append("URGENT: Less than 2 weeks coverage remaining")

            # Add stockout impact
            stockout_days = factors.get('stockout_days', 0)
            if stockout_days > 0:
                if stockout_days >= 20:
                    reason_components.append(f"Severe stockout impact: {stockout_days} days out of stock last month")
                elif stockout_days >= 10:
                    reason_components.append(f"Moderate stockout impact: {stockout_days} days out of stock")
                else:
                    reason_components.append(f"Recent stockout: {stockout_days} days affected")

            # Add seasonal pre-positioning
            seasonal_info = factors.get('seasonal_info', {})
            if seasonal_info.get('needs_pre_positioning'):
                reason_components.append(seasonal_info['reason'])

            # Add growth context
            growth_status = factors.get('growth_status', 'normal')
            if growth_status == 'viral':
                reason_components.append("High priority: Viral growth detected (2x+ demand increase)")
            elif growth_status == 'declining':
                reason_components.append("Trend alert: Declining demand pattern")

            # Add business importance context
            abc_class = factors.get('abc_class', 'C')
            if abc_class == 'A':
                reason_components.append("High-value item (Class A)")

            # Add coverage context if relevant
            coverage = factors.get('current_coverage', 0)
            target_coverage = factors.get('target_coverage', 6)
            if coverage < target_coverage * 0.5:
                reason_components.append(f"Below minimum coverage (target: {target_coverage:.1f} months)")

            # Fallback to base reason if no specific components
            if not reason_components and factors.get('base_reason'):
                reason_components.append(factors['base_reason'])

            # Join components with proper formatting
            if not reason_components:
                return "Maintain optimal inventory levels"

            return " | ".join(reason_components)

        except Exception as e:
            logger.error(f"Failed to generate detailed transfer reason: {e}")
            return factors.get('base_reason', 'Transfer recommended')

    def calculate_priority_score(self, sku_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate weighted priority score for stockout-affected SKUs

        Args:
            sku_data: Dictionary containing SKU information including:
                - kentucky_stockout_days: Stockout days
                - kentucky_qty: Current Kentucky quantity
                - corrected_demand: Monthly corrected demand
                - abc_code: ABC classification
                - growth_status: Growth status
                - last_stockout_date: Most recent stockout date

        Returns:
            Dictionary with priority score and breakdown
        """
        try:
            # Initialize scoring components
            stockout_score = 0
            coverage_score = 0
            abc_score = 0
            growth_score = 0

            # 1. Stockout Days Score (40% weight) - 0-40 points
            stockout_days = sku_data.get('kentucky_stockout_days', 0)
            if stockout_days >= 25:
                stockout_score = 40  # Severe stockout
            elif stockout_days >= 15:
                stockout_score = 32  # Major stockout
            elif stockout_days >= 10:
                stockout_score = 24  # Moderate stockout
            elif stockout_days >= 5:
                stockout_score = 16  # Minor stockout
            elif stockout_days > 0:
                stockout_score = 8   # Minimal stockout
            # 0 stockout days = 0 points

            # 2. Coverage Ratio Score (30% weight) - 0-30 points
            kentucky_qty = sku_data.get('kentucky_qty', 0)
            corrected_demand = sku_data.get('corrected_demand', 1)

            if kentucky_qty == 0:
                coverage_score = 30  # Out of stock
            else:
                coverage_months = kentucky_qty / max(corrected_demand, 1)
                if coverage_months < 0.5:
                    coverage_score = 25  # Less than 2 weeks
                elif coverage_months < 1.0:
                    coverage_score = 20  # Less than 1 month
                elif coverage_months < 2.0:
                    coverage_score = 15  # Less than 2 months
                elif coverage_months < 4.0:
                    coverage_score = 10  # Less than 4 months
                else:
                    coverage_score = 0   # Adequate coverage

            # 3. ABC Classification Score (20% weight) - 0-20 points
            abc_code = sku_data.get('abc_code', 'C')
            abc_scores = {'A': 20, 'B': 12, 'C': 5}
            abc_score = abc_scores.get(abc_code, 5)

            # 4. Growth Status Score (10% weight) - 0-10 points
            growth_status = sku_data.get('growth_status', 'normal')
            growth_scores = {'viral': 10, 'normal': 5, 'declining': 0}
            growth_score = growth_scores.get(growth_status, 5)

            # Calculate total score
            total_score = stockout_score + coverage_score + abc_score + growth_score

            # Convert score to priority level
            if total_score >= 80:
                priority_level = "CRITICAL"
            elif total_score >= 60:
                priority_level = "HIGH"
            elif total_score >= 40:
                priority_level = "MEDIUM"
            else:
                priority_level = "LOW"

            return {
                'total_score': total_score,
                'priority_level': priority_level,
                'score_breakdown': {
                    'stockout_score': stockout_score,
                    'coverage_score': coverage_score,
                    'abc_score': abc_score,
                    'growth_score': growth_score
                },
                'score_details': {
                    'stockout_days': stockout_days,
                    'coverage_months': round(kentucky_qty / max(corrected_demand, 1), 1),
                    'abc_class': abc_code,
                    'growth_status': growth_status
                }
            }

        except Exception as e:
            logger.error(f"Priority score calculation failed for SKU {sku_data.get('sku_id', 'unknown')}: {e}")
            return {
                'total_score': 50,
                'priority_level': "MEDIUM",
                'score_breakdown': {'error': str(e)},
                'score_details': {}
            }

    def _update_sku_patterns(self, sku_id: str, seasonal_pattern: str, growth_status: str):
        """
        Update SKU record with detected patterns

        Args:
            sku_id: SKU identifier
            seasonal_pattern: Detected seasonal pattern
            growth_status: Growth status
        """
        try:
            update_query = """
            UPDATE skus
            SET seasonal_pattern = %s, growth_status = %s, updated_at = NOW()
            WHERE sku_id = %s
            """

            db = database.get_database_connection()
            cursor = db.cursor()
            cursor.execute(update_query, (seasonal_pattern, growth_status, sku_id))
            db.close()

            logger.debug(f"Updated patterns for {sku_id}: {seasonal_pattern}, {growth_status}")

        except Exception as e:
            logger.error(f"Failed to update patterns for {sku_id}: {e}")

    def consolidate_discontinued_items(self) -> List[Dict[str, Any]]:
        """
        Generate consolidation recommendations for discontinued items

        Returns:
            List of consolidation recommendations
        """
        try:
            # Get discontinued items with inventory in both warehouses
            query = """
            SELECT
                s.sku_id,
                s.description,
                ic.burnaby_qty,
                ic.kentucky_qty,
                s.cost_per_unit,
                COALESCE(ms.kentucky_sales, 0) as recent_kentucky_sales,
                COALESCE(ms.burnaby_sales, 0) as recent_burnaby_sales
            FROM skus s
            INNER JOIN inventory_current ic ON s.sku_id = ic.sku_id
            LEFT JOIN monthly_sales ms ON s.sku_id = ms.sku_id AND ms.year_month = '2024-03'
            WHERE s.status IN ('Death Row', 'Discontinued')
                AND ic.burnaby_qty > 0
                AND ic.kentucky_qty > 0
            ORDER BY (ic.kentucky_qty * s.cost_per_unit) DESC
            """

            discontinued_items = database.execute_query(query)
            recommendations = []

            for item in discontinued_items:
                # Determine consolidation direction based on recent sales
                kentucky_sales = item['recent_kentucky_sales'] or 0
                burnaby_sales = item['recent_burnaby_sales'] or 0

                if kentucky_sales >= burnaby_sales:
                    # Keep in Kentucky, transfer from Burnaby
                    transfer_qty = item['burnaby_qty']
                    destination = "Kentucky"
                    reason = f"Consolidate discontinued item to higher-selling warehouse (KY: {kentucky_sales}, BC: {burnaby_sales})"
                else:
                    # Keep in Burnaby, no transfer needed (this tool focuses on transfers to Kentucky)
                    continue

                recommendations.append({
                    'sku_id': item['sku_id'],
                    'description': item['description'],
                    'consolidation_type': 'discontinued',
                    'recommended_transfer_qty': transfer_qty,
                    'destination': destination,
                    'reason': reason,
                    'priority': 'MEDIUM',
                    'current_kentucky_qty': item['kentucky_qty'],
                    'current_burnaby_qty': item['burnaby_qty'],
                    'value_impact': round(transfer_qty * (item['cost_per_unit'] or 0), 2)
                })

            logger.info(f"Generated {len(recommendations)} discontinued item consolidation recommendations")
            return recommendations

        except Exception as e:
            logger.error(f"Discontinued item consolidation failed: {e}")
            return []

def calculate_all_transfer_recommendations(use_enhanced: bool = True) -> List[Dict[str, Any]]:
    """
    Calculate transfer recommendations for all active SKUs with integrated weighted demand calculations

    This function now integrates the WeightedDemandCalculator to replace single-month demand
    calculations with sophisticated weighted moving averages, providing more stable and accurate
    transfer recommendations for the main planning interface.

    Key Enhancements:
    - Weighted demand integration: Calculates 6-month and 3-month weighted averages
    - Intelligent fallback: Uses single-month calculations for SKUs with insufficient history
    - 6-month supply calculations: Provides UI-ready 6-month supply estimates
    - Comprehensive error handling: Graceful degradation for calculation failures
    - Strategy selection: Uses ABC-XYZ classification to select optimal weighting strategy

    Weighted Demand Process:
    1. Queries all active SKUs with latest sales and inventory data
    2. For each SKU, calculates weighted demand for both Kentucky and Burnaby warehouses
    3. Replaces database corrected_demand values with weighted calculations
    4. Adds 6-month supply calculations for UI display formatting
    5. Falls back to database values for SKUs where weighted calculation fails
    6. Logs calculation improvements for quality assurance and debugging

    Integration Benefits:
    - Reduces impact of monthly demand anomalies
    - Provides more stable transfer recommendations
    - Improves forecasting accuracy for seasonal and volatile SKUs
    - Maintains backward compatibility with existing data structures
    - Enables better inventory planning with smoothed demand patterns

    Args:
        use_enhanced: Whether to use enhanced calculations with seasonal/growth analysis

    Returns:
        List of transfer recommendations sorted by priority, each containing:
        - Enhanced demand calculations using weighted averages
        - 6-month supply estimates for UI display (kentucky_6month_supply, burnaby_6month_supply)
        - All existing fields for backward compatibility
        - Priority scoring based on weighted demand calculations

    Note:
        The function maintains full backward compatibility while enhancing demand accuracy.
        SKUs with insufficient history (<3 months) automatically fall back to single-month
        calculations with stockout correction.
    """
    try:
        print("DEBUG: calculate_all_transfer_recommendations called")

        # DUPLICATE SKU FIX (TASK-097):
        # Replaced LEFT JOIN with stockout_dates table with EXISTS subqueries to prevent duplicate rows.
        #
        # Problem: When SKUs had multiple stockout records (different warehouses or unresolved events),
        # the LEFT JOIN created duplicate rows in the result set, causing SKUs to appear multiple times
        # in the transfer planning interface.
        #
        # Solution: Using EXISTS subqueries to check stockout status without creating duplicates:
        # - EXISTS returns TRUE/FALSE based on whether matching records exist
        # - Does not multiply the number of result rows like JOINs do
        # - Maintains accurate stockout status information (kentucky_stockout, burnaby_stockout)
        # - More efficient than DISTINCT as it prevents duplicates rather than removing them
        #
        # Performance Impact: EXISTS subqueries are typically more efficient than LEFT JOINs
        # for boolean checks, as they can stop execution once the first matching record is found.
        query = """
        SELECT
            s.sku_id,
            s.description,
            s.supplier,
            s.status,
            s.abc_code,
            s.xyz_code,
            s.transfer_multiple,
            ic.burnaby_qty,
            ic.kentucky_qty,
            COALESCE(ms.kentucky_sales, 0) as kentucky_sales,
            COALESCE(ms.kentucky_stockout_days, 0) as kentucky_stockout_days,
            COALESCE(ms.burnaby_sales, 0) as burnaby_sales,
            COALESCE(ms.burnaby_stockout_days, 0) as burnaby_stockout_days,
            COALESCE(ms.corrected_demand_kentucky, 0) as corrected_demand_kentucky,
            COALESCE(ms.corrected_demand_burnaby, 0) as corrected_demand_burnaby,
            tc.confirmed_qty,
            tc.original_suggested_qty,
            tc.confirmed_by,
            tc.confirmed_at,
            tc.notes as confirmation_notes,
            tc.ca_order_qty,
            tc.ky_order_qty,
            CASE
                WHEN tc.original_suggested_qty > 0 THEN
                    ROUND(((tc.confirmed_qty - tc.original_suggested_qty) / tc.original_suggested_qty) * 100, 2)
                ELSE 0
            END as variance_percent,
            CASE WHEN EXISTS (
                SELECT 1 FROM stockout_dates sd_ky
                WHERE sd_ky.sku_id = s.sku_id
                AND sd_ky.warehouse = 'kentucky'
                AND sd_ky.is_resolved = FALSE
            ) THEN TRUE ELSE FALSE END as kentucky_stockout,
            CASE WHEN EXISTS (
                SELECT 1 FROM stockout_dates sd_ca
                WHERE sd_ca.sku_id = s.sku_id
                AND sd_ca.warehouse = 'burnaby'
                AND sd_ca.is_resolved = FALSE
            ) THEN TRUE ELSE FALSE END as burnaby_stockout
        FROM skus s
        LEFT JOIN inventory_current ic ON s.sku_id = ic.sku_id
        LEFT JOIN monthly_sales ms ON s.sku_id = ms.sku_id AND ms.`year_month` = (
            SELECT MAX(`year_month`)
            FROM monthly_sales ms2
            WHERE ms2.sku_id = s.sku_id
            AND (ms2.kentucky_sales > 0 OR ms2.burnaby_sales > 0)
        )
        LEFT JOIN transfer_confirmations tc ON s.sku_id = tc.sku_id
        ORDER BY s.sku_id
        """
        
        sku_data_list = database.execute_query(query)
        print(f"DEBUG: Query returned {len(sku_data_list) if sku_data_list else 0} SKUs from database")

        if not sku_data_list:
            return []
        
        calculator = TransferCalculator()
        recommendations = []

        # Process each SKU and calculate weighted demand with caching for improved performance
        # This integration uses the CacheManager to prevent connection exhaustion while
        # providing sophisticated weighted moving averages for better forecasting accuracy
        for sku_data in sku_data_list:
            # TRUST THE CACHE - Use cached weighted demand for fast page loads
            # Cache contains all advanced features: stockout correction, seasonal adjustments, volatility analysis
            try:
                # Get cached result - this should exist after initial population
                kentucky_weighted_result = calculator.cache_manager.get_cached_weighted_demand(
                    sku_data['sku_id'], 'kentucky'
                )

                if kentucky_weighted_result:
                    # TRUST THE CACHE - don't recalculate!
                    sku_data['corrected_demand_kentucky'] = kentucky_weighted_result['enhanced_demand']
                    sku_data['kentucky_6month_supply'] = round(kentucky_weighted_result['enhanced_demand'] * 6, 0)
                    logger.debug(f"SKU {sku_data['sku_id']} KY: Using cached weighted demand {kentucky_weighted_result['enhanced_demand']:.1f}")
                else:
                    # Only calculate if truly no cache (should rarely happen after population)
                    logger.warning(f"No cache found for {sku_data['sku_id']} Kentucky - using database fallback")
                    current_demand = sku_data.get('corrected_demand_kentucky', 0) or 0
                    sku_data['kentucky_6month_supply'] = round(float(current_demand) * 6, 0)

            except Exception as e:
                logger.warning(f"Failed to calculate Kentucky weighted demand for {sku_data['sku_id']}: {e}")
                # Fallback to database value
                current_demand = sku_data.get('corrected_demand_kentucky', 0) or 0
                sku_data['kentucky_6month_supply'] = round(float(current_demand) * 6, 0)

            # TRUST THE CACHE - Use cached weighted demand for fast page loads
            try:
                # Get cached result - this should exist after initial population
                burnaby_weighted_result = calculator.cache_manager.get_cached_weighted_demand(
                    sku_data['sku_id'], 'burnaby'
                )

                if burnaby_weighted_result:
                    # TRUST THE CACHE - don't recalculate!
                    sku_data['corrected_demand_burnaby'] = burnaby_weighted_result['enhanced_demand']
                    sku_data['burnaby_6month_supply'] = round(burnaby_weighted_result['enhanced_demand'] * 6, 0)
                    logger.debug(f"SKU {sku_data['sku_id']} BY: Using cached weighted demand {burnaby_weighted_result['enhanced_demand']:.1f}")
                else:
                    # Only calculate if truly no cache (should rarely happen after population)
                    logger.warning(f"No cache found for {sku_data['sku_id']} Burnaby - using database fallback")
                    current_demand = sku_data.get('corrected_demand_burnaby', 0) or 0
                    sku_data['burnaby_6month_supply'] = round(float(current_demand) * 6, 0)

            except Exception as e:
                logger.warning(f"Failed to calculate Burnaby weighted demand for {sku_data['sku_id']}: {e}")
                # Fallback to database value
                current_demand = sku_data.get('corrected_demand_burnaby', 0) or 0
                sku_data['burnaby_6month_supply'] = round(float(current_demand) * 6, 0)


        for sku_data in sku_data_list:
            # Use the new economic validation method to prevent stockouts
            recommendation = calculator.calculate_enhanced_transfer_with_economic_validation(sku_data)

            # Always include all SKUs, even those with zero transfer recommendations
            if recommendation:
                recommendations.append(recommendation)
            else:
                # Create a minimal recommendation for SKUs that failed calculation
                # Use the weighted demand values that were calculated above
                ky_demand = float(sku_data.get('corrected_demand_kentucky', 0) or 0)
                ca_demand = float(sku_data.get('corrected_demand_burnaby', 0) or 0)

                minimal_rec = {
                    'sku_id': sku_data['sku_id'],
                    'description': sku_data.get('description', ''),
                    'supplier': sku_data.get('supplier', ''),
                    'status': sku_data.get('status', 'Active'),
                    'abc_class': sku_data.get('abc_code', 'C'),
                    'xyz_class': sku_data.get('xyz_code', 'Z'),
                    'current_kentucky_qty': sku_data.get('kentucky_qty', 0),
                    'current_burnaby_qty': sku_data.get('burnaby_qty', 0),
                    'corrected_monthly_demand': ky_demand,
                    'kentucky_6month_supply': sku_data.get('kentucky_6month_supply', round(ky_demand * 6, 0)),
                    'burnaby_monthly_demand': ca_demand,
                    'burnaby_6month_supply': sku_data.get('burnaby_6month_supply', round(ca_demand * 6, 0)),
                    'recommended_transfer_qty': 0,
                    'priority': 'LOW',
                    'reason': 'Calculation failed or no recommendation needed',
                    'transfer_multiple': sku_data.get('transfer_multiple', 50),
                    'coverage_months': 0,
                    'enhanced_calculation': False,

                    # Transfer confirmation data
                    'confirmed_qty': sku_data.get('confirmed_qty'),
                    'original_suggested_qty': sku_data.get('original_suggested_qty'),
                    'confirmed_by': sku_data.get('confirmed_by'),
                    'confirmed_at': sku_data.get('confirmed_at'),
                    'confirmation_notes': sku_data.get('confirmation_notes'),
                    'ca_order_qty': sku_data.get('ca_order_qty'),
                    'ky_order_qty': sku_data.get('ky_order_qty'),
                    'variance_percent': sku_data.get('variance_percent', 0),
                    'is_confirmed': bool(sku_data.get('confirmed_qty') is not None),
                    'has_significant_variance': abs(sku_data.get('variance_percent', 0)) > 20,
                    'has_major_variance': abs(sku_data.get('variance_percent', 0)) > 50,

                    # Stockout status data
                    'kentucky_stockout': bool(sku_data.get('kentucky_stockout', 0)),
                    'burnaby_stockout': bool(sku_data.get('burnaby_stockout', 0))
                }

                # Retrieve pending orders for minimal_rec fallback
                try:
                    pending_data = calculator.get_pending_orders_data(sku_data['sku_id'])
                    minimal_rec['kentucky_pending'] = pending_data.get('kentucky_pending', 0)
                    minimal_rec['burnaby_pending'] = pending_data.get('burnaby_pending', 0)
                    minimal_rec['days_until_arrival'] = pending_data.get('days_until_arrival')
                    minimal_rec['pending_orders_included'] = True
                    minimal_rec['current_position_with_pending'] = (
                        sku_data.get('kentucky_qty', 0) + pending_data.get('kentucky_pending', 0)
                    )
                except Exception as e:
                    logger.warning(f"Could not retrieve pending for {sku_data['sku_id']} in fallback: {e}")
                    minimal_rec['kentucky_pending'] = 0
                    minimal_rec['burnaby_pending'] = 0
                    minimal_rec['days_until_arrival'] = None
                    minimal_rec['pending_orders_included'] = False
                    minimal_rec['current_position_with_pending'] = sku_data.get('kentucky_qty', 0)

                recommendations.append(minimal_rec)
        
        # Sort by priority (CRITICAL -> HIGH -> MEDIUM -> LOW)
        priority_order = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
        recommendations.sort(key=lambda x: (
            priority_order.get(x['priority'], 5),
            -x['corrected_monthly_demand']  # Higher demand first within same priority
        ))
        
        logger.info(f"Generated {len(recommendations)} transfer recommendations")
        return recommendations
        
    except Exception as e:
        logger.error(f"Failed to calculate transfer recommendations: {e}")
        raise

def update_abc_xyz_classifications():
    """
    Update ABC-XYZ classifications for all SKUs based on recent sales data

    Uses the last 12 months of combined warehouse sales data for accurate classification.
    Automatically determines the recent period to ensure sufficient data for analysis.
    Should be called after sales data import to keep classifications current.

    Returns:
        bool: True if classifications updated successfully, False otherwise
    """
    try:
        from datetime import datetime, timedelta
        import calendar

        # Calculate 12 months back from the most recent sales data
        current_month_query = "SELECT MAX(`year_month`) as latest_month FROM monthly_sales"
        latest_data = database.execute_query(current_month_query)

        if not latest_data or not latest_data[0]['latest_month']:
            logger.warning("No sales data found for classification update")
            return False

        latest_month = latest_data[0]['latest_month']

        # Calculate 12 months back (accounting for year boundary)
        try:
            year, month = map(int, latest_month.split('-'))
            if month > 12:
                start_year = year
                start_month = month - 12
            else:
                start_year = year - 1
                start_month = month + 12 - 12
            start_date = f"{start_year:04d}-{start_month:02d}"
        except:
            # Fallback to simple calculation
            start_date = "2024-01"

        # Get combined sales data for classification (both warehouses)
        sales_query = """
        SELECT
            s.sku_id,
            s.cost_per_unit,
            ms.kentucky_sales,
            ms.burnaby_sales,
            ms.`year_month`
        FROM skus s
        LEFT JOIN monthly_sales ms ON s.sku_id = ms.sku_id
        WHERE s.status = 'Active'
            AND ms.`year_month` >= %s
            AND (ms.kentucky_sales > 0 OR ms.burnaby_sales > 0)
        ORDER BY s.sku_id, ms.`year_month`
        """

        sales_data = database.execute_query(sales_query, (start_date,))

        if not sales_data:
            logger.warning(f"No sales data found from {start_date} onwards")
            return False

        # Group by SKU and combine warehouse sales
        sku_sales = {}
        for row in sales_data:
            sku_id = row['sku_id']
            if sku_id not in sku_sales:
                sku_sales[sku_id] = {
                    'cost_per_unit': row['cost_per_unit'] or 0,
                    'sales': []
                }
            # Combine both warehouse sales for total demand
            total_monthly_sales = (row['kentucky_sales'] or 0) + (row['burnaby_sales'] or 0)
            sku_sales[sku_id]['sales'].append(total_monthly_sales)
        
        classifier = ABCXYZClassifier()
        
        # Calculate total annual value for ABC classification
        total_annual_value = 0
        for sku_data in sku_sales.values():
            # Use actual 12-month sales data (no extrapolation needed)
            annual_sales = sum(sku_data['sales'])
            annual_value = annual_sales * sku_data['cost_per_unit']
            total_annual_value += annual_value

        updated_count = 0

        # Calculate ABC classifications using correct batch method
        sku_values = []
        for sku_id, sku_data in sku_sales.items():
            annual_sales = sum(sku_data['sales'])
            annual_value = annual_sales * sku_data['cost_per_unit']
            sku_values.append((sku_id, annual_value))

        abc_classifications = classifier.classify_abc_batch(sku_values)

        # Update classifications in batch for better performance
        updates = []
        for sku_id, sku_data in sku_sales.items():
            abc_class = abc_classifications.get(sku_id, 'C')
            xyz_class = classifier.classify_xyz(sku_data['sales'])

            updates.append((abc_class, xyz_class, sku_id))

        # Batch update for better performance
        if updates:
            db = database.get_database_connection()
            cursor = db.cursor()
            try:
                update_query = """
                UPDATE skus
                SET abc_code = %s, xyz_code = %s, updated_at = NOW()
                WHERE sku_id = %s
                """
                cursor.executemany(update_query, updates)
                db.commit()
                updated_count = len(updates)
                logger.info(f"Successfully updated ABC-XYZ classifications for {updated_count} SKUs")
                logger.info(f"Classification period: {start_date} to {latest_month}")

            except Exception as e:
                db.rollback()
                logger.error(f"Database error updating classifications: {e}")
                return False
            finally:
                cursor.close()
                db.close()

        return True

    except Exception as e:
        logger.error(f"Failed to update ABC-XYZ classifications: {e}")
        return False


def update_all_seasonal_and_growth_patterns():
    """
    Update seasonal patterns and growth status for all active SKUs
    This should be run monthly after new sales data is imported
    """
    try:
        # Get all active SKUs
        query = """
        SELECT sku_id FROM skus WHERE status = 'Active' ORDER BY sku_id
        """

        sku_list = database.execute_query(query)
        if not sku_list:
            logger.warning("No active SKUs found for pattern update")
            return False

        detector = SeasonalPatternDetector()
        growth_detector = ViralGrowthDetector()
        updated_count = 0

        for sku_record in sku_list:
            sku_id = sku_record['sku_id']

            try:
                # Detect patterns
                seasonal_pattern = detector.detect_seasonal_pattern(sku_id)
                growth_status = growth_detector.detect_viral_growth(sku_id)

                # Update database
                update_query = """
                UPDATE skus
                SET seasonal_pattern = %s, growth_status = %s, updated_at = NOW()
                WHERE sku_id = %s
                """

                db = database.get_database_connection()
                cursor = db.cursor()
                cursor.execute(update_query, (seasonal_pattern, growth_status, sku_id))
                db.close()

                updated_count += 1
                logger.debug(f"Updated patterns for {sku_id}: {seasonal_pattern}, {growth_status}")

            except Exception as e:
                logger.error(f"Failed to update patterns for {sku_id}: {e}")
                continue

        logger.info(f"Updated seasonal and growth patterns for {updated_count} SKUs")
        return True

    except Exception as e:
        logger.error(f"Failed to update seasonal and growth patterns: {e}")
        return False


def test_enhanced_calculations():
    """
    Test the enhanced calculation system with sample data
    Returns test results for validation
    """
    try:
        logger.info("Starting enhanced calculation tests...")

        # Test 1: Year-over-year lookup
        corrector = StockoutCorrector()
        yoy_result = corrector.get_same_month_last_year('CHG-001', '2024-03')
        logger.info(f"Test 1 - Year-over-year lookup for CHG-001: {yoy_result}")

        # Test 2: Category average
        category_result = corrector.get_category_average('CHG-001')
        logger.info(f"Test 2 - Category average for CHG-001: {category_result}")

        # Test 3: Enhanced correction for zero sales with stockout
        enhanced_result = corrector.correct_monthly_demand_enhanced('CHG-001', 0, 25, '2024-03')
        logger.info(f"Test 3 - Enhanced correction (0 sales, 25 stockout days): {enhanced_result}")

        # Test 4: Seasonal pattern detection
        seasonal_detector = SeasonalPatternDetector()
        seasonal_pattern = seasonal_detector.detect_seasonal_pattern('CHG-001')
        logger.info(f"Test 4 - Seasonal pattern for CHG-001: {seasonal_pattern}")

        # Test 5: Viral growth detection
        growth_detector = ViralGrowthDetector()
        growth_status = growth_detector.detect_viral_growth('CHG-001')
        logger.info(f"Test 5 - Growth status for CHG-001: {growth_status}")

        # Test 6: Enhanced transfer recommendation
        calculator = TransferCalculator()
        sample_sku_data = {
            'sku_id': 'CHG-001',
            'description': 'USB-C Fast Charger 65W',
            'burnaby_qty': 500,
            'kentucky_qty': 0,
            'kentucky_sales': 0,
            'kentucky_stockout_days': 25,
            'abc_code': 'A',
            'xyz_code': 'X',
            'transfer_multiple': 25
        }

        enhanced_recommendation = calculator.calculate_enhanced_transfer_recommendation(sample_sku_data)
        logger.info(f"Test 6 - Enhanced recommendation for CHG-001: {enhanced_recommendation}")

        # Test 7: Performance test with multiple calculations
        start_time = datetime.now()
        test_recommendations = calculate_all_transfer_recommendations(use_enhanced=True)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"Test 7 - Performance test: {len(test_recommendations)} recommendations in {duration:.2f}s")

        test_results = {
            'yoy_lookup': yoy_result,
            'category_average': category_result,
            'enhanced_correction': enhanced_result,
            'seasonal_pattern': seasonal_pattern,
            'growth_status': growth_status,
            'enhanced_recommendation': enhanced_recommendation is not None,
            'performance_test': {
                'recommendations_count': len(test_recommendations),
                'duration_seconds': duration,
                'meets_target': duration < 5.0  # Target: <5 seconds
            }
        }

        logger.info("Enhanced calculation tests completed successfully")
        return test_results

    except Exception as e:
        logger.error(f"Enhanced calculation tests failed: {e}")
        return {'error': str(e)}