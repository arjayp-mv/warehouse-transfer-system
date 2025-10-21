"""
Sales Analytics Module

This module provides comprehensive sales analytics calculations and metrics
for the warehouse transfer planning tool. It handles multi-SKU analysis,
revenue trends, warehouse comparisons, and high-level sales insights.

This module is completely separate from transfer planning calculations
to maintain system stability and modularity.
"""

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from decimal import Decimal
import statistics
import logging
from .database import execute_query

logger = logging.getLogger(__name__)

class SalesAnalytics:
    """
    Core sales analytics engine for multi-SKU analysis and reporting.

    Provides methods for:
    - Revenue trend analysis
    - Growth rate calculations
    - Warehouse performance comparison
    - ABC-XYZ classification
    - Top/bottom performer identification
    """

    def __init__(self):
        """Initialize sales analytics with database connection."""
        pass

    def get_revenue_trends(
        self,
        months_back: int = 12,
        warehouse: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate revenue trends over specified time period.

        Args:
            months_back: Number of months to analyze (default: 12)
            warehouse: Optional warehouse filter ('burnaby', 'kentucky', or None for both)

        Returns:
            Dictionary containing revenue trends, growth rates, and metrics
        """
        try:
            # Build warehouse filter condition
            warehouse_filter = ""
            if warehouse == 'burnaby':
                warehouse_filter = "AND burnaby_revenue > 0"
            elif warehouse == 'kentucky':
                warehouse_filter = "AND kentucky_revenue > 0"

            # Get monthly revenue trends
            query = """
            SELECT
                `year_month`,
                SUM(COALESCE(burnaby_revenue, 0)) as burnaby_revenue,
                SUM(COALESCE(kentucky_revenue, 0)) as kentucky_revenue,
                SUM(COALESCE(burnaby_revenue, 0) + COALESCE(kentucky_revenue, 0)) as total_revenue,
                COUNT(DISTINCT sku_id) as sku_count,
                SUM(COALESCE(burnaby_sales, 0) + COALESCE(kentucky_sales, 0)) as total_units
            FROM monthly_sales
            WHERE `year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
            {}
            GROUP BY `year_month`
            ORDER BY `year_month` ASC
            """.format(warehouse_filter)

            monthly_data = execute_query(query, (months_back,))

            if not monthly_data:
                return {
                    'monthly_trends': [],
                    'total_revenue': 0,
                    'growth_rate': 0,
                    'average_monthly': 0
                }

            # Calculate growth rate (current vs previous period)
            total_current = sum(row['total_revenue'] or 0 for row in monthly_data[-6:])
            total_previous = sum(row['total_revenue'] or 0 for row in monthly_data[-12:-6])

            growth_rate = 0
            if total_previous > 0:
                growth_rate = ((total_current - total_previous) / total_previous) * 100

            total_revenue = sum(row['total_revenue'] or 0 for row in monthly_data)
            avg_monthly = total_revenue / len(monthly_data) if monthly_data else 0

            return {
                'monthly_trends': monthly_data,
                'total_revenue': total_revenue,
                'growth_rate': round(growth_rate, 2),
                'average_monthly': round(avg_monthly, 2),
                'period_months': len(monthly_data)
            }

        except Exception as e:
            logger.error(f"Error calculating revenue trends: {e}")
            raise

    def get_top_performers(
        self,
        limit: int = 10,
        metric: str = 'revenue',
        period_months: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Get top performing SKUs by specified metric.

        Args:
            limit: Number of top performers to return
            metric: Metric to rank by ('revenue', 'units', 'growth')
            period_months: Time period for analysis

        Returns:
            List of top performer dictionaries with metrics
        """
        try:
            # Build ORDER BY clause based on metric
            if metric == 'revenue':
                order_by = "total_revenue DESC"
            elif metric == 'units':
                order_by = "total_units DESC"
            elif metric == 'growth':
                order_by = "growth_rate DESC"
            else:
                order_by = "total_revenue DESC"

            query = f"""
            SELECT
                s.sku_id,
                s.description,
                s.category,
                s.abc_code,
                s.xyz_code,
                SUM(COALESCE(ms.burnaby_revenue, 0) + COALESCE(ms.kentucky_revenue, 0)) as total_revenue,
                SUM(COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0)) as total_units,
                AVG(CASE WHEN (COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0)) > 0
                    THEN (COALESCE(ms.burnaby_revenue, 0) + COALESCE(ms.kentucky_revenue, 0)) / (COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0))
                    ELSE 0 END) as avg_selling_price,
                COUNT(ms.`year_month`) as months_with_sales
            FROM skus s
            JOIN monthly_sales ms ON s.sku_id = ms.sku_id
            WHERE ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
              AND s.status = 'Active'
            GROUP BY s.sku_id, s.description, s.category, s.abc_code, s.xyz_code
            HAVING total_revenue > 0
            ORDER BY {order_by}
            LIMIT %s
            """

            performers = execute_query(query, (period_months, limit))

            # Calculate additional metrics
            for performer in performers:
                performer['avg_monthly_revenue'] = (
                    performer['total_revenue'] / period_months if period_months > 0 else 0
                )
                performer['avg_monthly_units'] = (
                    performer['total_units'] / period_months if period_months > 0 else 0
                )

            return performers or []

        except Exception as e:
            logger.error(f"Error getting top performers: {e}")
            return []

    def analyze_warehouse_split(self, months_back: int = 12) -> Dict[str, Any]:
        """
        Analyze sales distribution between Burnaby and Kentucky warehouses.

        Args:
            months_back: Number of months to analyze

        Returns:
            Dictionary with warehouse comparison metrics
        """
        try:
            query = """
            SELECT
                SUM(COALESCE(burnaby_revenue, 0)) as burnaby_total_revenue,
                SUM(COALESCE(kentucky_revenue, 0)) as kentucky_total_revenue,
                SUM(COALESCE(burnaby_sales, 0)) as burnaby_total_units,
                SUM(COALESCE(kentucky_sales, 0)) as kentucky_total_units,
                COUNT(DISTINCT CASE WHEN burnaby_sales > 0 THEN sku_id END) as burnaby_sku_count,
                COUNT(DISTINCT CASE WHEN kentucky_sales > 0 THEN sku_id END) as kentucky_sku_count,
                COUNT(DISTINCT sku_id) as total_sku_count
            FROM monthly_sales
            WHERE `year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
            """

            result = execute_query(query, (months_back,), fetch_one=True)

            if not result:
                return {}

            # Calculate percentages and metrics
            total_revenue = (result['burnaby_total_revenue'] or 0) + (result['kentucky_total_revenue'] or 0)
            total_units = (result['burnaby_total_units'] or 0) + (result['kentucky_total_units'] or 0)

            burnaby_revenue_pct = ((result['burnaby_total_revenue'] or 0) / total_revenue * 100) if total_revenue > 0 else 0
            kentucky_revenue_pct = ((result['kentucky_total_revenue'] or 0) / total_revenue * 100) if total_revenue > 0 else 0

            burnaby_asp = ((result['burnaby_total_revenue'] or 0) / (result['burnaby_total_units'] or 0)) if (result['burnaby_total_units'] or 0) > 0 else 0
            kentucky_asp = ((result['kentucky_total_revenue'] or 0) / (result['kentucky_total_units'] or 0)) if (result['kentucky_total_units'] or 0) > 0 else 0

            # Find SKUs exclusive to each warehouse
            exclusive_query = """
            SELECT
                COUNT(DISTINCT CASE WHEN burnaby_sales > 0 AND kentucky_sales = 0 THEN sku_id END) as burnaby_exclusive,
                COUNT(DISTINCT CASE WHEN kentucky_sales > 0 AND burnaby_sales = 0 THEN sku_id END) as kentucky_exclusive,
                COUNT(DISTINCT CASE WHEN burnaby_sales > 0 AND kentucky_sales > 0 THEN sku_id END) as both_warehouses
            FROM (
                SELECT sku_id, SUM(COALESCE(burnaby_sales, 0)) as burnaby_sales, SUM(COALESCE(kentucky_sales, 0)) as kentucky_sales
                FROM monthly_sales
                WHERE `year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
                GROUP BY sku_id
            ) as sku_totals
            """

            exclusivity = execute_query(exclusive_query, (months_back,), fetch_one=True)

            return {
                'burnaby': {
                    'revenue': result['burnaby_total_revenue'] or 0,
                    'revenue_percentage': round(burnaby_revenue_pct, 1),
                    'units': result['burnaby_total_units'] or 0,
                    'avg_selling_price': round(burnaby_asp, 2),
                    'sku_count': result['burnaby_sku_count'] or 0,
                    'exclusive_skus': (exclusivity['burnaby_exclusive'] if exclusivity else 0) or 0
                },
                'kentucky': {
                    'revenue': result['kentucky_total_revenue'] or 0,
                    'revenue_percentage': round(kentucky_revenue_pct, 1),
                    'units': result['kentucky_total_units'] or 0,
                    'avg_selling_price': round(kentucky_asp, 2),
                    'sku_count': result['kentucky_sku_count'] or 0,
                    'exclusive_skus': (exclusivity['kentucky_exclusive'] if exclusivity else 0) or 0
                },
                'shared_skus': (exclusivity['both_warehouses'] if exclusivity else 0) or 0,
                'total_skus': result['total_sku_count'] or 0,
                'total_revenue': total_revenue,
                'total_units': total_units
            }

        except Exception as e:
            logger.error(f"Error analyzing warehouse split: {e}")
            return {}

    def calculate_stockout_impact(self, months_back: int = 12) -> List[Dict[str, Any]]:
        """
        Calculate the revenue impact of stockouts across all SKUs using historical data.

        This method calculates lost sales by comparing historical demand from non-stockout
        periods with current stockout periods. Uses proper historical baselines to estimate
        what could have been sold during stockout periods.

        Args:
            months_back: Number of months to analyze (default: 12)

        Returns:
            List with stockout impact data for each affected SKU including:
            - sku_id: SKU identifier
            - description: SKU description
            - total_stockout_days: Total days out of stock (both warehouses)
            - actual_sales: Units actually sold during analysis period
            - potential_sales: Estimated units based on historical data
            - lost_sales: Calculated lost revenue
        """
        try:
            # Helper function to get historical sales baseline from NON-stockout periods
            def get_historical_baseline(sku_id: str) -> tuple[float, float]:
                """Get historical average monthly sales and price from periods WITHOUT stockouts."""
                historical_query = """
                SELECT
                    AVG(kentucky_sales + burnaby_sales) as avg_historical_sales,
                    AVG(CASE WHEN (kentucky_sales + burnaby_sales) > 0
                        THEN (kentucky_revenue + burnaby_revenue) / (kentucky_sales + burnaby_sales)
                        ELSE 0 END) as avg_historical_price,
                    COUNT(*) as months_analyzed
                FROM monthly_sales ms
                WHERE ms.sku_id = %s
                    AND ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 24 MONTH), '%%Y-%%m')
                    AND COALESCE(kentucky_stockout_days, 0) = 0
                    AND COALESCE(burnaby_stockout_days, 0) = 0
                    AND (kentucky_sales + burnaby_sales) > 0
                """

                try:
                    historical_result = execute_query(historical_query, (sku_id,), fetch_one=True)
                    if historical_result and historical_result.get('months_analyzed', 0) > 0:
                        avg_sales = historical_result.get('avg_historical_sales', 0) or 0
                        avg_price = historical_result.get('avg_historical_price', 0) or 0
                        return float(avg_sales), float(avg_price)
                    else:
                        return 0.0, 0.0
                except Exception as e:
                    logger.warning(f"Error calculating historical baseline for {sku_id}: {e}")
                    return 0.0, 0.0

            # Get SKUs with stockout data from both warehouses
            query = """
            SELECT
                ms.sku_id,
                s.description,
                s.category,
                SUM(COALESCE(ms.kentucky_stockout_days, 0) + COALESCE(ms.burnaby_stockout_days, 0)) as total_stockout_days,
                SUM(COALESCE(ms.kentucky_sales, 0) + COALESCE(ms.burnaby_sales, 0)) as actual_sales,
                CASE
                    WHEN SUM(COALESCE(ms.kentucky_sales, 0) + COALESCE(ms.burnaby_sales, 0)) > 0
                    THEN SUM(COALESCE(ms.kentucky_revenue, 0) + COALESCE(ms.burnaby_revenue, 0)) / SUM(COALESCE(ms.kentucky_sales, 0) + COALESCE(ms.burnaby_sales, 0))
                    ELSE 0
                END as avg_selling_price
            FROM monthly_sales ms
            JOIN skus s ON ms.sku_id = s.sku_id
            WHERE ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
                AND s.status = 'Active'
                AND (COALESCE(ms.kentucky_stockout_days, 0) > 0 OR COALESCE(ms.burnaby_stockout_days, 0) > 0)
            GROUP BY ms.sku_id, s.description, s.category
            HAVING total_stockout_days > 0
            ORDER BY total_stockout_days DESC
            """

            stockout_data = execute_query(query, (months_back,))
            if not stockout_data:
                return []

            result = []
            for sku_data in stockout_data:
                sku_id = sku_data.get('sku_id')
                total_stockout_days = sku_data.get('total_stockout_days', 0) or 0
                avg_price = sku_data.get('avg_selling_price', 0) or 0
                actual_sales = sku_data.get('actual_sales', 0) or 0

                # Convert Decimal values to float for calculations
                total_stockout_days = float(total_stockout_days)
                avg_price = float(avg_price)
                actual_sales = float(actual_sales)

                # Get historical sales baseline from non-stockout periods
                historical_avg_sales, historical_avg_price = get_historical_baseline(sku_id)

                if total_stockout_days > 0 and historical_avg_sales > 0:
                    # Calculate lost units based on historical monthly average × (stockout days ÷ 30)
                    potential_sales = historical_avg_sales * (total_stockout_days / 30.0) + actual_sales

                    # Use historical price if current price is missing
                    if avg_price == 0 and historical_avg_price > 0:
                        avg_price = historical_avg_price
                    elif avg_price == 0:
                        # Category-based fallback pricing
                        category = sku_data.get('category', '').lower()
                        if 'battery' in category:
                            avg_price = 25.0
                        elif 'charger' in category or 'cable' in category:
                            avg_price = 15.0
                        else:
                            avg_price = 20.0

                    lost_revenue = (potential_sales - actual_sales) * avg_price

                elif total_stockout_days > 0:
                    # Fallback for SKUs without historical data
                    category = sku_data.get('category', '').lower()
                    if 'battery' in category:
                        estimated_monthly = 10.0  # 10 units/month baseline
                        avg_price = avg_price or 25.0
                    elif 'charger' in category or 'cable' in category:
                        estimated_monthly = 20.0  # 20 units/month baseline
                        avg_price = avg_price or 15.0
                    else:
                        estimated_monthly = 5.0   # 5 units/month baseline
                        avg_price = avg_price or 20.0

                    lost_units = estimated_monthly * (total_stockout_days / 30.0)
                    potential_sales = actual_sales + lost_units
                    lost_revenue = lost_units * avg_price
                else:
                    potential_sales = actual_sales
                    lost_revenue = 0

                result.append({
                    'sku_id': sku_id,
                    'description': sku_data.get('description', ''),
                    'total_stockout_days': str(total_stockout_days),
                    'actual_sales': str(actual_sales),
                    'potential_sales': f"{potential_sales:.2f}",
                    'lost_sales': f"{lost_revenue:.2f}"
                })

            # Sort by lost sales descending and limit to top 100
            result.sort(key=lambda x: float(x['lost_sales']), reverse=True)
            return result[:100]

        except Exception as e:
            logger.error(f"Error calculating stockout impact: {e}")
            return []

    def get_abc_xyz_distribution(self) -> List[Dict[str, Any]]:
        """
        Get the distribution of SKUs across ABC-XYZ classification matrix.

        This method retrieves the 9-box ABC-XYZ matrix data showing how SKUs
        are distributed by revenue importance (A/B/C) and demand volatility (X/Y/Z).
        The data is used to populate the interactive matrix visualization.

        Returns:
            List of classification data with counts and revenue for each combination:
            - abc_code: Revenue classification (A=High, B=Medium, C=Low)
            - xyz_code: Volatility classification (X=Stable, Y=Variable, Z=Erratic)
            - classification: Combined code (e.g., 'AX', 'BY', 'CZ')
            - sku_count: Number of SKUs in this classification
            - total_revenue: Total revenue for this classification
            - avg_revenue_per_sku: Average revenue per SKU
            - total_units: Total units sold for this classification
        """
        try:
            # Use the optimized view for better performance
            query = """
            SELECT * FROM v_abc_xyz_matrix
            ORDER BY abc_code, xyz_code
            """

            matrix_data = execute_query(query)

            # Ensure all 9 possible combinations are represented (A/B/C x X/Y/Z)
            all_combinations = []
            for abc in ['A', 'B', 'C']:
                for xyz in ['X', 'Y', 'Z']:
                    classification = abc + xyz

                    # Find existing data for this combination
                    existing = next((item for item in (matrix_data or [])
                                   if item['abc_code'] == abc and item['xyz_code'] == xyz), None)

                    if existing:
                        all_combinations.append({
                            'abc_code': abc,
                            'xyz_code': xyz,
                            'classification': classification,
                            'sku_count': existing.get('sku_count', 0) or 0,
                            'total_revenue': existing.get('total_revenue', 0) or 0,
                            'avg_revenue_per_sku': existing.get('avg_revenue_per_sku', 0) or 0,
                            'total_units': existing.get('total_units', 0) or 0
                        })
                    else:
                        # Add empty combination for completeness
                        all_combinations.append({
                            'abc_code': abc,
                            'xyz_code': xyz,
                            'classification': classification,
                            'sku_count': 0,
                            'total_revenue': 0,
                            'avg_revenue_per_sku': 0,
                            'total_units': 0
                        })

            return all_combinations

        except Exception as e:
            logger.error(f"Error getting ABC-XYZ distribution: {e}")
            return []


def get_sales_summary(months_back: int = 12) -> Dict[str, Any]:
    """
    Get high-level sales summary for dashboard display with enhanced calculations.

    This function returns comprehensive sales metrics including revenue averages,
    stockout impact estimates, and growth indicators needed for the dashboard KPIs.

    Args:
        months_back: Number of months to analyze (default: 12)

    Returns:
        Dictionary containing key sales metrics and insights including:
        - total_skus: Count of unique SKUs with sales
        - total_units: Total units sold across all warehouses
        - total_revenue: Total revenue across all warehouses
        - average_monthly_revenue: Average monthly revenue (not sales units)
        - estimated_stockout_loss: Estimated revenue lost due to stockouts
        - monthly_growth_rate: Growth rate comparison for recent periods
        - period_analyzed_months: Number of months included in analysis
    """
    try:
        # Use the new sales summary view for performance
        base_query = """
        SELECT * FROM v_sales_summary_12m
        """

        base_result = execute_query(base_query, fetch_one=True)

        if not base_result:
            return {}

        # Calculate additional metrics that aren't in the view
        # Get growth rate by comparing recent 3 months vs previous 3 months
        growth_query = """
        SELECT
            SUM(CASE
                WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 3 MONTH), '%%Y-%%m')
                THEN COALESCE(ms.burnaby_revenue, 0) + COALESCE(ms.kentucky_revenue, 0)
                ELSE 0
            END) as recent_revenue,
            SUM(CASE
                WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 6 MONTH), '%%Y-%%m')
                AND ms.`year_month` < DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 3 MONTH), '%%Y-%%m')
                THEN COALESCE(ms.burnaby_revenue, 0) + COALESCE(ms.kentucky_revenue, 0)
                ELSE 0
            END) as previous_revenue
        FROM monthly_sales ms
        WHERE ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 6 MONTH), '%%Y-%%m')
        """

        growth_result = execute_query(growth_query, fetch_one=True)

        # Calculate growth rate
        growth_rate = 0
        if growth_result and growth_result['previous_revenue'] and growth_result['previous_revenue'] > 0:
            growth_rate = ((growth_result['recent_revenue'] - growth_result['previous_revenue']) /
                          growth_result['previous_revenue'] * 100)

        # Calculate estimated lost revenue from stockouts
        lost_revenue_ky = 0
        lost_revenue_ca = 0

        if base_result.get('estimated_lost_sales_ky', 0) > 0:
            # Estimate lost revenue using average selling price
            avg_price_query = """
            SELECT
                AVG(CASE
                    WHEN (COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0)) > 0
                    THEN (COALESCE(ms.burnaby_revenue, 0) + COALESCE(ms.kentucky_revenue, 0)) /
                         (COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0))
                    ELSE 0
                END) as avg_selling_price
            FROM monthly_sales ms
            WHERE ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
                AND (COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0)) > 0
            """

            avg_price_result = execute_query(avg_price_query, (months_back,), fetch_one=True)
            avg_price = avg_price_result['avg_selling_price'] if avg_price_result else 0

            if avg_price > 0:
                lost_revenue_ky = base_result.get('estimated_lost_sales_ky', 0) * avg_price
                lost_revenue_ca = base_result.get('estimated_lost_sales_ca', 0) * avg_price

        total_lost_revenue = lost_revenue_ky + lost_revenue_ca

        return {
            'total_skus': base_result.get('total_skus', 0),
            'total_units': base_result.get('total_units', 0),
            'total_revenue': base_result.get('total_revenue', 0),
            'average_monthly_revenue': base_result.get('avg_monthly_revenue', 0),  # Fixed: return revenue not sales
            'estimated_stockout_loss': round(total_lost_revenue, 2),  # Fixed: calculate actual loss
            'monthly_growth_rate': round(growth_rate, 2),
            'period_analyzed_months': months_back,
            'total_stockout_days': (base_result.get('total_stockout_days_ky', 0) +
                                   base_result.get('total_stockout_days_ca', 0)),
            'estimated_lost_sales_units': (base_result.get('estimated_lost_sales_ky', 0) +
                                         base_result.get('estimated_lost_sales_ca', 0))
        }

    except Exception as e:
        logger.error(f"Error getting sales summary: {e}")
        return {}


def calculate_growth_rates(
    periods: List[int] = [3, 6, 12],
    warehouse: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate comprehensive growth rate analysis for multiple time periods.

    This function provides YoY, QoQ, MoM growth calculations with trend analysis
    and acceleration/deceleration indicators for strategic planning.

    Args:
        periods: List of month periods to analyze (default: [3, 6, 12])
        warehouse: Optional warehouse filter ('kentucky', 'burnaby', or None for both)

    Returns:
        Dictionary containing growth rates, trends, and comparative analysis
    """
    try:
        logger.info(f"Calculating growth rates for periods: {periods}, warehouse: {warehouse}")

        # Determine warehouse columns
        if warehouse and warehouse.lower() == 'burnaby':
            revenue_col = 'burnaby_revenue'
            sales_col = 'burnaby_sales'
            warehouse_filter = "AND COALESCE(ms.burnaby_revenue, 0) > 0"
        elif warehouse and warehouse.lower() == 'kentucky':
            revenue_col = 'kentucky_revenue'
            sales_col = 'kentucky_sales'
            warehouse_filter = "AND COALESCE(ms.kentucky_revenue, 0) > 0"
        else:
            revenue_col = '(COALESCE(ms.burnaby_revenue, 0) + COALESCE(ms.kentucky_revenue, 0))'
            sales_col = '(COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0))'
            warehouse_filter = ""

        results = {}
        trend_data = []

        # Calculate growth rates for each period
        for period_months in periods:
            current_period_months = period_months
            previous_period_months = period_months * 2  # Compare with previous equivalent period

            growth_query = f"""
            SELECT
                -- Current period (most recent X months)
                SUM(CASE
                    WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {current_period_months} MONTH), '%%Y-%%m')
                    THEN {revenue_col}
                    ELSE 0
                END) as current_period_revenue,

                SUM(CASE
                    WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {current_period_months} MONTH), '%%Y-%%m')
                    THEN {sales_col}
                    ELSE 0
                END) as current_period_units,

                -- Previous period (previous X months before current period)
                SUM(CASE
                    WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {previous_period_months} MONTH), '%%Y-%%m')
                    AND ms.`year_month` < DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {current_period_months} MONTH), '%%Y-%%m')
                    THEN {revenue_col}
                    ELSE 0
                END) as previous_period_revenue,

                SUM(CASE
                    WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {previous_period_months} MONTH), '%%Y-%%m')
                    AND ms.`year_month` < DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {current_period_months} MONTH), '%%Y-%%m')
                    THEN {sales_col}
                    ELSE 0
                END) as previous_period_units,

                -- Year-over-year comparison (same months from previous year)
                SUM(CASE
                    WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {current_period_months + 12} MONTH), '%%Y-%%m')
                    AND ms.`year_month` < DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 12 MONTH), '%%Y-%%m')
                    THEN {revenue_col}
                    ELSE 0
                END) as yoy_previous_revenue,

                -- Count months with data for reliability scoring
                COUNT(DISTINCT CASE
                    WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {current_period_months} MONTH), '%%Y-%%m')
                    AND {revenue_col} > 0
                    THEN ms.`year_month`
                END) as current_months_with_data,

                COUNT(DISTINCT CASE
                    WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {previous_period_months} MONTH), '%%Y-%%m')
                    AND ms.`year_month` < DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {current_period_months} MONTH), '%%Y-%%m')
                    AND {revenue_col} > 0
                    THEN ms.`year_month`
                END) as previous_months_with_data

            FROM monthly_sales ms
            WHERE ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {previous_period_months + 12} MONTH), '%%Y-%%m')
            {warehouse_filter}
            """

            result = execute_query(growth_query, fetch_one=True)

            if not result:
                continue

            # Calculate growth metrics
            period_analysis = {
                'period_months': period_months,
                'current_revenue': result.get('current_period_revenue', 0) or 0,
                'previous_revenue': result.get('previous_period_revenue', 0) or 0,
                'current_units': result.get('current_period_units', 0) or 0,
                'previous_units': result.get('previous_period_units', 0) or 0,
                'yoy_previous_revenue': result.get('yoy_previous_revenue', 0) or 0,
                'data_reliability': {
                    'current_months': result.get('current_months_with_data', 0),
                    'previous_months': result.get('previous_months_with_data', 0),
                    'expected_months': period_months
                }
            }

            # Period-over-period growth rate
            pop_growth_rate = 0
            if period_analysis['previous_revenue'] > 0:
                pop_growth_rate = ((period_analysis['current_revenue'] - period_analysis['previous_revenue']) /
                                 period_analysis['previous_revenue'] * 100)

            # Year-over-year growth rate
            yoy_growth_rate = 0
            if period_analysis['yoy_previous_revenue'] > 0:
                yoy_growth_rate = ((period_analysis['current_revenue'] - period_analysis['yoy_previous_revenue']) /
                                 period_analysis['yoy_previous_revenue'] * 100)

            # Units growth rate
            units_growth_rate = 0
            if period_analysis['previous_units'] > 0:
                units_growth_rate = ((period_analysis['current_units'] - period_analysis['previous_units']) /
                                   period_analysis['previous_units'] * 100)

            # Average selling price analysis
            current_asp = 0
            previous_asp = 0
            if period_analysis['current_units'] > 0:
                current_asp = period_analysis['current_revenue'] / period_analysis['current_units']
            if period_analysis['previous_units'] > 0:
                previous_asp = period_analysis['previous_revenue'] / period_analysis['previous_units']

            asp_change = 0
            if previous_asp > 0:
                asp_change = ((current_asp - previous_asp) / previous_asp * 100)

            # Determine trend classification
            trend_classification = "stable"
            if abs(pop_growth_rate) >= 10:
                trend_classification = "high_growth" if pop_growth_rate > 0 else "declining"
            elif abs(pop_growth_rate) >= 5:
                trend_classification = "moderate_growth" if pop_growth_rate > 0 else "moderate_decline"
            elif abs(pop_growth_rate) >= 2:
                trend_classification = "slow_growth" if pop_growth_rate > 0 else "slow_decline"

            period_analysis.update({
                'pop_growth_rate': round(pop_growth_rate, 2),
                'yoy_growth_rate': round(yoy_growth_rate, 2),
                'units_growth_rate': round(units_growth_rate, 2),
                'asp_current': round(current_asp, 2),
                'asp_previous': round(previous_asp, 2),
                'asp_change_percent': round(asp_change, 2),
                'trend_classification': trend_classification,
                'reliability_score': min(1.0, (period_analysis['data_reliability']['current_months'] +
                                             period_analysis['data_reliability']['previous_months']) /
                                            (period_months * 2))
            })

            results[f"{period_months}_month"] = period_analysis
            trend_data.append({
                'period': period_months,
                'growth_rate': pop_growth_rate,
                'classification': trend_classification
            })

        # Calculate trend acceleration/deceleration
        trend_direction = "stable"
        trend_strength = "weak"

        if len(trend_data) >= 2:
            # Compare short-term vs long-term growth
            short_term = next((t for t in trend_data if t['period'] == 3), None)
            long_term = next((t for t in trend_data if t['period'] == 12), None)

            if short_term and long_term:
                if short_term['growth_rate'] > long_term['growth_rate'] + 5:
                    trend_direction = "accelerating"
                elif short_term['growth_rate'] < long_term['growth_rate'] - 5:
                    trend_direction = "decelerating"

                # Determine strength based on consistency
                growth_rates = [t['growth_rate'] for t in trend_data]
                if all(rate > 5 for rate in growth_rates):
                    trend_strength = "strong_positive"
                elif all(rate < -5 for rate in growth_rates):
                    trend_strength = "strong_negative"
                elif all(rate > 0 for rate in growth_rates):
                    trend_strength = "consistent_positive"
                elif all(rate < 0 for rate in growth_rates):
                    trend_strength = "consistent_negative"
                else:
                    trend_strength = "mixed"

        return {
            'periods': results,
            'trend_analysis': {
                'direction': trend_direction,
                'strength': trend_strength,
                'trend_data': trend_data
            },
            'analysis_parameters': {
                'warehouse': warehouse or 'both',
                'periods_analyzed': periods,
                'analysis_date': datetime.now().isoformat()
            },
            'summary': {
                'best_performing_period': max(results.keys(),
                                            key=lambda k: results[k]['pop_growth_rate']) if results else None,
                'worst_performing_period': min(results.keys(),
                                             key=lambda k: results[k]['pop_growth_rate']) if results else None,
                'average_growth_rate': round(sum(r['pop_growth_rate'] for r in results.values()) / len(results), 2) if results else 0
            }
        }

    except Exception as e:
        logger.error(f"Error calculating growth rates: {e}")
        return {
            'periods': {},
            'trend_analysis': {
                'direction': 'unknown',
                'strength': 'unknown',
                'trend_data': []
            },
            'error': str(e)
        }


def calculate_detailed_stockout_impact(
    months_back: int = 12,
    warehouse: Optional[str] = None,
    min_impact: float = 0.0
) -> Dict[str, Any]:
    """
    Calculate detailed stockout impact analysis with SKU-level breakdown and recovery estimates.

    This function provides comprehensive stockout analysis including revenue loss projections,
    recovery time estimates, and prioritization for inventory investment decisions.

    Enhanced to ensure meaningful results by showing top 20 affected SKUs regardless of
    min_impact threshold, addressing the issue where high thresholds filtered out all results.

    Args:
        months_back: Number of months to analyze for impact calculation (default: 12)
        warehouse: Optional warehouse filter ('kentucky', 'burnaby', or None for both)
        min_impact: Minimum estimated revenue loss threshold for inclusion (default: 0.0)
                   Changed from 100.0 to show all stockout impacts

    Returns:
        Dictionary containing detailed stockout impact analysis with recovery projections.
        Always includes at least top 20 SKUs by impact value even if below min_impact.

    Algorithm Enhancement:
        - Calculates impact for all affected SKUs
        - Sorts by impact value descending
        - Includes SKUs that meet min_impact OR are in top 20
        - Ensures Pareto chart has meaningful data for analysis
    """
    try:
        logger.info(f"Calculating detailed stockout impact for {months_back} months, warehouse: {warehouse}")

        # Determine warehouse columns for filtering
        if warehouse and warehouse.lower() == 'burnaby':
            stockout_filter = "AND COALESCE(ms.burnaby_stockout_days, 0) > 0"
            sales_col = 'ms.burnaby_sales'
            revenue_col = 'ms.burnaby_revenue'
            demand_col = 'ms.corrected_demand_burnaby'
            stockout_col = 'ms.burnaby_stockout_days'
        elif warehouse and warehouse.lower() == 'kentucky':
            stockout_filter = "AND COALESCE(ms.kentucky_stockout_days, 0) > 0"
            sales_col = 'ms.kentucky_sales'
            revenue_col = 'ms.kentucky_revenue'
            demand_col = 'ms.corrected_demand_kentucky'
            stockout_col = 'ms.kentucky_stockout_days'
        else:
            stockout_filter = "AND (COALESCE(ms.kentucky_stockout_days, 0) > 0 OR COALESCE(ms.burnaby_stockout_days, 0) > 0)"
            sales_col = '(COALESCE(ms.burnaby_sales, 0) + COALESCE(ms.kentucky_sales, 0))'
            revenue_col = '(COALESCE(ms.burnaby_revenue, 0) + COALESCE(ms.kentucky_revenue, 0))'
            demand_col = '(COALESCE(ms.corrected_demand_kentucky, 0) + COALESCE(ms.corrected_demand_burnaby, 0))'
            stockout_col = '(COALESCE(ms.kentucky_stockout_days, 0) + COALESCE(ms.burnaby_stockout_days, 0))'

        # Main stockout impact query
        stockout_query = f"""
        SELECT
            s.sku_id,
            s.description,
            s.category,
            s.abc_code,
            s.xyz_code,
            s.supplier,

            -- Current inventory levels
            COALESCE(ic_ky.quantity, 0) as current_kentucky_qty,
            COALESCE(ic_ca.quantity, 0) as current_burnaby_qty,

            -- Stockout metrics
            SUM({stockout_col}) as total_stockout_days,
            COUNT(DISTINCT CASE WHEN {stockout_col} > 0 THEN ms.`year_month` END) as months_with_stockouts,
            AVG({stockout_col}) as avg_stockout_days_per_month,
            MAX({stockout_col}) as worst_stockout_month,

            -- Sales and demand analysis
            SUM({sales_col}) as total_actual_sales,
            SUM({demand_col}) as total_corrected_demand,
            SUM({revenue_col}) as total_actual_revenue,
            AVG({sales_col}) as avg_monthly_sales,
            AVG({demand_col}) as avg_monthly_demand,

            -- Lost sales calculation - Use historical performance to estimate potential sales
            -- Key insight: Look at this SKU's historical sales rate during NON-stockout periods
            0 as estimated_lost_units,  -- Temporarily set to 0, will calculate in Python

            -- Average selling price calculation
            CASE
                WHEN SUM({sales_col}) > 0
                THEN SUM({revenue_col}) / SUM({sales_col})
                ELSE 0
            END as avg_selling_price,

            -- Frequency and severity metrics
            COUNT(DISTINCT ms.`year_month`) as total_months_analyzed,
            ROUND((COUNT(DISTINCT CASE WHEN {stockout_col} > 0 THEN ms.`year_month` END) * 100.0) /
                  COUNT(DISTINCT ms.`year_month`), 2) as stockout_frequency_percent,

            -- Recent stockout trend (last 3 months vs previous 3 months)
            SUM(CASE
                WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 3 MONTH), '%%Y-%%m')
                THEN {stockout_col}
                ELSE 0
            END) as recent_stockout_days,

            SUM(CASE
                WHEN ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 6 MONTH), '%%Y-%%m')
                AND ms.`year_month` < DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 3 MONTH), '%%Y-%%m')
                THEN {stockout_col}
                ELSE 0
            END) as previous_stockout_days

        FROM skus s
        JOIN monthly_sales ms ON s.sku_id = ms.sku_id
        LEFT JOIN inventory_current ic_ky ON s.sku_id = ic_ky.sku_id AND ic_ky.warehouse = 'Kentucky'
        LEFT JOIN inventory_current ic_ca ON s.sku_id = ic_ca.sku_id AND ic_ca.warehouse = 'Burnaby'
        WHERE s.status = 'Active'
            AND ms.`year_month` >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL %s MONTH), '%%Y-%%m')
            {stockout_filter}
        GROUP BY s.sku_id, s.description, s.category, s.abc_code, s.xyz_code, s.supplier,
                 ic_ky.quantity, ic_ca.quantity
        HAVING SUM({stockout_col}) > 0
        ORDER BY SUM({stockout_col}) DESC
        """

        stockout_data = execute_query(stockout_query, (months_back,))

        if not stockout_data:
            return {
                'skus': [],
                'summary': {
                    'total_affected_skus': 0,
                    'total_estimated_lost_revenue': 0,
                    'total_estimated_lost_units': 0,
                    'avg_recovery_time_days': 0
                },
                'message': 'No significant stockout impacts found'
            }

        # Helper function to get historical sales baseline from NON-stockout periods
        def get_historical_baseline(sku_id: str) -> tuple[float, float]:
            """
            Get historical average monthly sales and price from periods WITHOUT stockouts.

            Args:
                sku_id: SKU identifier to analyze

            Returns:
                Tuple of (avg_monthly_sales, avg_historical_price)
            """
            historical_query = f"""
            SELECT
                AVG({sales_col}) as avg_historical_sales,
                AVG(CASE WHEN {sales_col} > 0
                    THEN {revenue_col} / {sales_col}
                    ELSE 0 END) as avg_historical_price,
                COUNT(*) as months_analyzed
            FROM monthly_sales ms
            WHERE ms.sku_id = %s
                AND ms.year_month >= DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 24 MONTH), '%%Y-%%m')
                AND COALESCE({stockout_col}, 0) = 0  -- Only months WITHOUT stockouts
                AND {sales_col} > 0  -- Only months with actual sales
            """

            try:
                historical_result = execute_query(historical_query, (sku_id,), fetch_one=True)
                if historical_result and historical_result.get('months_analyzed', 0) > 0:
                    avg_sales = historical_result.get('avg_historical_sales', 0) or 0
                    avg_price = historical_result.get('avg_historical_price', 0) or 0
                    return float(avg_sales), float(avg_price)
                else:
                    return 0.0, 0.0
            except Exception as e:
                logger.warning(f"Error calculating historical baseline for {sku_id}: {e}")
                return 0.0, 0.0

        # Process and enhance each SKU record
        # Enhanced algorithm: Pre-calculate impact for all SKUs and sort by impact
        # This ensures we show the most affected SKUs even with high min_impact thresholds
        all_skus_with_impact = []

        for sku_data in stockout_data:
            # Calculate estimated lost units using historical performance from NON-stockout periods
            sku_id = sku_data.get('sku_id')
            total_stockout_days = sku_data.get('total_stockout_days', 0) or 0
            avg_price = sku_data.get('avg_selling_price', 0) or 0

            # Get historical sales baseline from non-stockout periods
            historical_avg_sales, historical_avg_price = get_historical_baseline(sku_id)

            if total_stockout_days > 0 and historical_avg_sales > 0:
                # Calculate lost units based on historical monthly average × (stockout days ÷ 30)
                lost_units = historical_avg_sales * (total_stockout_days / 30.0)

                # Use historical price if current price is missing or zero
                if avg_price == 0 and historical_avg_price > 0:
                    avg_price = historical_avg_price
                elif avg_price == 0:
                    # Ultimate fallback: category-based minimum pricing
                    category = sku_data.get('category', '').lower()
                    if 'battery' in category:
                        avg_price = 25.0  # Battery average
                    elif 'charger' in category or 'cable' in category:
                        avg_price = 15.0  # Accessory average
                    else:
                        avg_price = 20.0  # General fallback

            elif total_stockout_days > 0:
                # Fallback for SKUs without historical data but with stockouts
                # Use category-based demand estimation
                category = sku_data.get('category', '').lower()
                if 'battery' in category:
                    # Batteries: estimate 10 units/month baseline
                    lost_units = 10.0 * (total_stockout_days / 30.0)
                    avg_price = avg_price or 25.0
                elif 'charger' in category or 'cable' in category:
                    # Accessories: estimate 20 units/month baseline
                    lost_units = 20.0 * (total_stockout_days / 30.0)
                    avg_price = avg_price or 15.0
                else:
                    # General: estimate 5 units/month baseline
                    lost_units = 5.0 * (total_stockout_days / 30.0)
                    avg_price = avg_price or 20.0
            else:
                lost_units = 0

            estimated_lost_revenue = lost_units * avg_price

            # Store calculated impact for consistent sorting and filtering
            sku_data['calculated_impact'] = estimated_lost_revenue
            all_skus_with_impact.append(sku_data)

        # Sort by impact descending to identify highest-impact stockouts first
        all_skus_with_impact.sort(key=lambda x: x.get('calculated_impact', 0), reverse=True)

        # Enhanced filtering logic: Ensure meaningful results for Pareto analysis
        # Include SKUs that meet minimum threshold OR are in top 20 by impact
        # This prevents empty results when min_impact is set too high
        enhanced_skus = []
        total_lost_revenue = 0
        total_lost_units = 0
        recovery_times = []

        for i, sku_data in enumerate(all_skus_with_impact):
            estimated_lost_revenue = sku_data.get('calculated_impact', 0)

            # Core filtering logic: min_impact threshold OR top 20 guarantee
            if estimated_lost_revenue >= min_impact or i < 20:
                # Calculate stockout severity score (0-100)
                stockout_frequency = sku_data.get('stockout_frequency_percent', 0) or 0
                avg_stockout_days = sku_data.get('avg_stockout_days_per_month', 0) or 0
                severity_score = min(100, (stockout_frequency * 0.6) + (avg_stockout_days * 2))

                # Estimate recovery time based on historical patterns
                total_stockout_days = sku_data.get('total_stockout_days', 0) or 0
                months_with_stockouts = sku_data.get('months_with_stockouts', 0) or 1
                avg_recovery_time = max(7, total_stockout_days / months_with_stockouts)  # Minimum 7 days

                # Adjust recovery time based on ABC classification and current inventory
                current_inventory = (sku_data.get('current_kentucky_qty', 0) or 0) + (sku_data.get('current_burnaby_qty', 0) or 0)
                abc_code = sku_data.get('abc_code', 'C')

                if abc_code == 'A':
                    recovery_multiplier = 0.8  # Prioritized restocking
                elif abc_code == 'B':
                    recovery_multiplier = 1.0  # Standard restocking
                else:
                    recovery_multiplier = 1.5  # Lower priority

                if current_inventory > 0:
                    recovery_multiplier *= 0.7  # Existing inventory speeds recovery

                estimated_recovery_days = int(avg_recovery_time * recovery_multiplier)

                # Calculate trend direction
                recent_days = sku_data.get('recent_stockout_days', 0) or 0
                previous_days = sku_data.get('previous_stockout_days', 0) or 0

                if previous_days > 0:
                    trend_change = ((recent_days - previous_days) / previous_days) * 100
                else:
                    trend_change = 0 if recent_days == 0 else 100

                if trend_change > 20:
                    trend_direction = "worsening"
                elif trend_change < -20:
                    trend_direction = "improving"
                else:
                    trend_direction = "stable"

                # Priority classification for action
                if severity_score >= 70 and abc_code == 'A':
                    priority = "critical"
                elif severity_score >= 50 or abc_code == 'A':
                    priority = "high"
                elif severity_score >= 30 or abc_code == 'B':
                    priority = "medium"
                else:
                    priority = "low"

                enhanced_sku = {
                    **sku_data,
                    'estimated_lost_revenue': round(estimated_lost_revenue, 2),
                    'severity_score': round(severity_score, 2),
                    'estimated_recovery_days': estimated_recovery_days,
                    'trend_direction': trend_direction,
                    'trend_change_percent': round(trend_change, 2),
                    'priority': priority,
                    'recommended_actions': []
                }

                # Generate specific recommendations
                if estimated_lost_revenue > 10000:
                    enhanced_sku['recommended_actions'].append("Immediate inventory replenishment required")

                if stockout_frequency > 40:
                    enhanced_sku['recommended_actions'].append("Review minimum stock levels and reorder points")

                if trend_direction == "worsening":
                    enhanced_sku['recommended_actions'].append("Investigate root cause of increasing stockouts")

                if current_inventory == 0:
                    enhanced_sku['recommended_actions'].append("Emergency stock transfer or expedited procurement")

                if not enhanced_sku['recommended_actions']:
                    enhanced_sku['recommended_actions'].append("Monitor for continued improvement")

                enhanced_skus.append(enhanced_sku)
                total_lost_revenue += estimated_lost_revenue
                total_lost_units += lost_units
                recovery_times.append(estimated_recovery_days)

        # Calculate summary metrics
        avg_recovery_time = sum(recovery_times) / len(recovery_times) if recovery_times else 0

        # Priority breakdown
        priority_counts = {}
        for sku in enhanced_skus:
            priority = sku['priority']
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        return {
            'skus': enhanced_skus[:100],  # Limit to top 100 for API response size
            'summary': {
                'total_affected_skus': len(enhanced_skus),
                'total_estimated_lost_revenue': round(total_lost_revenue, 2),
                'total_estimated_lost_units': round(total_lost_units, 2),
                'avg_recovery_time_days': round(avg_recovery_time, 1),
                'priority_breakdown': priority_counts
            },
            'analysis_parameters': {
                'months_analyzed': months_back,
                'warehouse': warehouse or 'both',
                'min_impact_threshold': min_impact,
                'analysis_date': datetime.now().isoformat()
            },
            'recommendations': {
                'immediate_action_skus': len([s for s in enhanced_skus if s['priority'] == 'critical']),
                'total_recoverable_revenue': round(total_lost_revenue * 0.8, 2),  # Assume 80% recoverable
                'estimated_roi_improvement': round((total_lost_revenue * 0.8) / max(1, total_lost_revenue * 0.1), 2)
            }
        }

    except Exception as e:
        logger.error(f"Error calculating detailed stockout impact: {e}")
        return {
            'skus': [],
            'summary': {
                'total_affected_skus': 0,
                'total_estimated_lost_revenue': 0,
                'total_estimated_lost_units': 0,
                'avg_recovery_time_days': 0
            },
            'error': str(e)
        }


def identify_bottom_performers(
    months_back: int = 12,
    warehouse: Optional[str] = None,
    velocity_threshold: float = 2.0,
    turnover_threshold: float = 1.0,
    margin_threshold: float = 0.15
) -> Dict[str, Any]:
    """
    Identify SKUs that are candidates for liquidation or discontinuation.

    This analysis helps identify slow-moving inventory that ties up cash
    and storage space. Uses multiple criteria to score liquidation priority.

    Args:
        months_back: Number of months to analyze (default: 12)
        warehouse: Warehouse to analyze ('burnaby', 'kentucky', or None for both)
        velocity_threshold: Units per month threshold for slow-moving (default: 2.0)
        turnover_threshold: Annual turnover rate threshold (default: 1.0)
        margin_threshold: Gross margin threshold for profitability (default: 0.15)

    Returns:
        Dictionary containing bottom performers ranked by liquidation priority
    """
    logger.info(f"Identifying bottom performers for {warehouse or 'all warehouses'}, {months_back} months")

    try:
        warehouse_filter = ""
        params = [months_back]

        if warehouse:
            warehouse_filter = "AND s.warehouse = %s"
            params.append(warehouse)

        # Complex query to identify poor performers across multiple dimensions
        query = f"""
        SELECT
            s.sku_id,
            s.warehouse,
            -- Sales velocity metrics
            AVG(s.units_sold) as avg_monthly_velocity,
            SUM(s.units_sold) as total_units_sold,
            COUNT(CASE WHEN s.units_sold > 0 THEN 1 END) as months_with_sales,
            COUNT(*) as months_tracked,

            -- Revenue and profitability
            AVG(s.revenue) as avg_monthly_revenue,
            SUM(s.revenue) as total_revenue,
            AVG(s.unit_price) as avg_unit_price,
            AVG(s.cost_of_goods) as avg_cogs,
            AVG((s.unit_price - s.cost_of_goods) / NULLIF(s.unit_price, 0)) as avg_margin_rate,

            -- Inventory turnover (approximation)
            AVG(s.units_sold) * 12 / NULLIF(AVG(i.kentucky_qty + i.burnaby_qty), 0) as estimated_turnover,
            AVG(i.kentucky_qty + i.burnaby_qty) as avg_inventory_level,

            -- Trend analysis
            CASE WHEN
                AVG(CASE WHEN s.sales_month >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH) THEN s.units_sold END) <
                AVG(CASE WHEN s.sales_month >= DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH)
                         AND s.sales_month < DATE_SUB(CURRENT_DATE(), INTERVAL 3 MONTH) THEN s.units_sold END)
            THEN 'declining' ELSE 'stable_or_growing' END as sales_trend,

            -- Days since last sale
            DATEDIFF(CURRENT_DATE(), MAX(CASE WHEN s.units_sold > 0 THEN s.sales_month END)) as days_since_last_sale,

            -- Death row indicator (discontinued or being phased out)
            COALESCE(p.death_row_date IS NOT NULL, FALSE) as is_death_row,
            COALESCE(p.discontinuation_reason, 'active') as discontinuation_reason

        FROM sales_history s
        LEFT JOIN inventory_current i ON s.sku_id = i.sku_id
        LEFT JOIN products p ON s.sku_id = p.sku_id
        WHERE s.sales_month >= DATE_SUB(CURRENT_DATE(), INTERVAL %s MONTH) {warehouse_filter}
        GROUP BY s.sku_id, s.warehouse
        HAVING total_units_sold > 0  -- Exclude completely dormant SKUs
        ORDER BY avg_monthly_velocity ASC, estimated_turnover ASC
        LIMIT 200
        """

        results = execute_query(query, params)

        bottom_performers = []
        liquidation_candidates = []
        total_tied_up_value = 0

        for row in results:
            # Calculate performance scores (0-1, higher is worse for liquidation)
            velocity_score = min((velocity_threshold - (row['avg_monthly_velocity'] or 0)) / velocity_threshold, 1.0)
            if velocity_score < 0:
                velocity_score = 0

            turnover_score = min((turnover_threshold - (row['estimated_turnover'] or 0)) / turnover_threshold, 1.0)
            if turnover_score < 0:
                turnover_score = 0

            margin_score = min((margin_threshold - (row['avg_margin_rate'] or 0)) / margin_threshold, 1.0)
            if margin_score < 0:
                margin_score = 0

            # Sales frequency penalty
            sales_frequency = (row['months_with_sales'] or 0) / (row['months_tracked'] or 1)
            frequency_score = 1 - sales_frequency

            # Recency penalty (no sales in last 90 days)
            recency_score = min((row['days_since_last_sale'] or 0) / 90, 1.0) if row['days_since_last_sale'] else 0

            # Death row bonus (automatic high priority)
            death_row_bonus = 0.5 if row['is_death_row'] else 0

            # Calculate composite liquidation score (0-1, higher means more urgent)
            score_components = {
                'velocity': velocity_score * 0.25,      # 25% - units moved per month
                'turnover': turnover_score * 0.25,     # 25% - inventory turnover rate
                'margin': margin_score * 0.15,         # 15% - profitability
                'frequency': frequency_score * 0.15,   # 15% - consistency of sales
                'recency': recency_score * 0.15,       # 15% - time since last sale
                'death_row': death_row_bonus           # 5% - discontinuation status
            }
            liquidation_score = sum(score_components.values())

            # Calculate financial impact
            inventory_value = (row['avg_inventory_level'] or 0) * (row['avg_unit_price'] or 0)
            carrying_cost_monthly = inventory_value * 0.02  # Assume 2% monthly carrying cost
            annual_carrying_cost = carrying_cost_monthly * 12

            # Liquidation recommendations
            urgency_level = 'critical' if liquidation_score > 0.7 else 'high' if liquidation_score > 0.5 else 'medium'

            recommendations = []
            if row['is_death_row']:
                recommendations.append("IMMEDIATE: Already marked for discontinuation")
            if liquidation_score > 0.8:
                recommendations.append("Consider liquidation sale (50% off)")
            elif liquidation_score > 0.6:
                recommendations.append("Mark down pricing (25-30% off)")
            if (row['days_since_last_sale'] or 0) > 180:
                recommendations.append("Investigate demand - possible obsolete inventory")
            if (row['estimated_turnover'] or 0) < 0.5:
                recommendations.append("Review minimum stock levels")

            performer_data = {
                'sku_id': row['sku_id'],
                'warehouse': row['warehouse'],
                'performance_metrics': {
                    'avg_monthly_velocity': round(row['avg_monthly_velocity'] or 0, 2),
                    'total_units_sold': row['total_units_sold'],
                    'avg_monthly_revenue': round(row['avg_monthly_revenue'] or 0, 2),
                    'estimated_turnover': round(row['estimated_turnover'] or 0, 2),
                    'avg_margin_rate': round(row['avg_margin_rate'] or 0, 3),
                    'sales_frequency': round(sales_frequency, 3),
                    'days_since_last_sale': row['days_since_last_sale']
                },
                'financial_impact': {
                    'inventory_value': round(inventory_value, 2),
                    'annual_carrying_cost': round(annual_carrying_cost, 2),
                    'avg_inventory_level': round(row['avg_inventory_level'] or 0, 1),
                    'avg_unit_price': round(row['avg_unit_price'] or 0, 2)
                },
                'liquidation_analysis': {
                    'liquidation_score': round(liquidation_score, 3),
                    'score_components': {k: round(v, 3) for k, v in score_components.items()},
                    'urgency_level': urgency_level,
                    'sales_trend': row['sales_trend']
                },
                'status': {
                    'is_death_row': bool(row['is_death_row']),
                    'discontinuation_reason': row['discontinuation_reason'],
                    'recommended_actions': recommendations
                }
            }

            bottom_performers.append(performer_data)
            total_tied_up_value += inventory_value

            # Mark high-priority liquidation candidates
            if liquidation_score > 0.5 or row['is_death_row']:
                liquidation_candidates.append(performer_data)

        # Sort by liquidation score (highest first)
        bottom_performers.sort(key=lambda x: x['liquidation_analysis']['liquidation_score'], reverse=True)
        liquidation_candidates.sort(key=lambda x: x['liquidation_analysis']['liquidation_score'], reverse=True)

        # Calculate summary statistics
        total_skus = len(bottom_performers)
        critical_count = len([p for p in bottom_performers if p['liquidation_analysis']['urgency_level'] == 'critical'])
        avg_liquidation_score = statistics.mean([p['liquidation_analysis']['liquidation_score'] for p in bottom_performers]) if bottom_performers else 0

        # Strategic insights
        insights = []
        if critical_count > total_skus * 0.3:
            insights.append("High number of critical liquidation candidates - review procurement practices")
        if total_tied_up_value > 1000000:
            insights.append(f"Over ${total_tied_up_value:,.0f} tied up in slow-moving inventory")
        death_row_count = len([p for p in bottom_performers if p['status']['is_death_row']])
        if death_row_count > 0:
            insights.append(f"{death_row_count} death row items need immediate liquidation")

        return {
            'summary': {
                'total_bottom_performers': total_skus,
                'critical_liquidation_candidates': critical_count,
                'total_inventory_value_tied_up': round(total_tied_up_value, 2),
                'average_liquidation_score': round(avg_liquidation_score, 3),
                'analysis_period_months': months_back,
                'warehouse_filter': warehouse or 'all_warehouses',
                'death_row_items': death_row_count
            },
            'liquidation_candidates': liquidation_candidates[:50],  # Top 50 most urgent
            'all_bottom_performers': bottom_performers,
            'thresholds_used': {
                'velocity_threshold': velocity_threshold,
                'turnover_threshold': turnover_threshold,
                'margin_threshold': margin_threshold
            },
            'strategic_insights': insights,
            'liquidation_strategies': [
                "Implement tiered discount structure based on urgency level",
                "Bundle slow-moving items with popular products",
                "Consider outlet sales or clearance events",
                "Evaluate supplier return policies for death row items",
                "Review procurement policies to prevent future accumulation"
            ]
        }

    except Exception as e:
        logger.error(f"Error identifying bottom performers: {str(e)}")
        return {
            'error': f'Failed to identify bottom performers: {str(e)}',
            'summary': {'total_bottom_performers': 0}
        }