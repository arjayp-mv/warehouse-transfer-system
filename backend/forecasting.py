"""
12-Month Sales Forecasting Engine

This module generates 12-month sales forecasts for SKUs using historical data,
seasonal patterns, and ABC/XYZ classification-based methodologies.

Core Forecasting Methods by ABC/XYZ Classification:
- AX, BX: Weighted Moving Average (6 months, 70% recent, high confidence)
- AY, BY: Weighted Moving Average (3 months, 60% recent, medium confidence)
- AZ, BZ: Simple Moving Average (3 months, lower confidence)
- CX: Simple Moving Average (6 months)
- CY, CZ: Simple Moving Average (3 months, lowest confidence)

The engine uses EXISTING corrected_demand fields from sku_demand_stats table
which already account for stockouts. It applies seasonal adjustments and
optional growth rates to generate monthly forecasts.
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime, date, timedelta
from decimal import Decimal
import statistics
from backend.database import execute_query
from backend.seasonal_calculator import get_monthly_factors, calculate_seasonal_pattern


class ForecastEngine:
    """
    Main forecasting engine that generates 12-month sales forecasts.

    The engine selects appropriate forecasting methods based on ABC/XYZ
    classification, applies seasonal adjustments, and stores results
    in the forecast_details table.
    """

    # Forecasting method configuration by ABC/XYZ classification
    METHOD_CONFIG = {
        'AX': {'method': 'weighted', 'months': 6, 'confidence': 0.90, 'recent_weight': 0.70},
        'AY': {'method': 'weighted', 'months': 3, 'confidence': 0.75, 'recent_weight': 0.60},
        'AZ': {'method': 'simple', 'months': 3, 'confidence': 0.60, 'recent_weight': 0.50},
        'BX': {'method': 'weighted', 'months': 6, 'confidence': 0.85, 'recent_weight': 0.70},
        'BY': {'method': 'weighted', 'months': 3, 'confidence': 0.70, 'recent_weight': 0.60},
        'BZ': {'method': 'simple', 'months': 3, 'confidence': 0.55, 'recent_weight': 0.50},
        'CX': {'method': 'simple', 'months': 6, 'confidence': 0.75, 'recent_weight': 0.50},
        'CY': {'method': 'simple', 'months': 3, 'confidence': 0.50, 'recent_weight': 0.50},
        'CZ': {'method': 'simple', 'months': 3, 'confidence': 0.40, 'recent_weight': 0.50}
    }

    def __init__(self, forecast_run_id: int, manual_growth_override: Optional[float] = None):
        """
        Initialize forecast engine for a specific forecast run.

        Args:
            forecast_run_id: ID of the forecast run from forecast_runs table
            manual_growth_override: Optional manual growth rate override (e.g., 0.05 for 5% growth)
                                   If None, growth rates are calculated per SKU using trend analysis
        """
        self.forecast_run_id = forecast_run_id
        self.manual_growth_override = manual_growth_override

    def calculate_sku_growth_rate(self, sku_id: str, warehouse: str, sku_info: Dict,
                                   lookback_months: int = 12) -> Tuple[float, str]:
        """
        Calculate annualized growth rate using weighted linear regression.

        Uses exponential weighting (0.5^(n-i)) to favor recent months for better
        trend detection. Falls back to category-level trend if insufficient data.

        Expert recommendation: Requires 6-12 months of data for reliable trend analysis.

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location ('burnaby', 'kentucky', 'combined')
            sku_info: SKU information dictionary (contains category, growth_status)
            lookback_months: Number of months to analyze (default: 12)

        Returns:
            Tuple[float, str]: (annualized_growth_rate, source)
            - annualized_growth_rate: Growth rate capped at ±50% (-0.5 to 0.5)
            - source: 'sku_trend', 'category_trend', 'growth_status', or 'default'
        """
        # If manual override is set, use it
        if self.manual_growth_override is not None:
            return (self.manual_growth_override, 'manual_override')

        # Get historical sales data for trend analysis
        if warehouse == 'combined':
            sales_column = 'corrected_demand_burnaby + corrected_demand_kentucky'
        else:
            sales_column = f'corrected_demand_{warehouse}'

        query = f"""
            SELECT
                `year_month`,
                {sales_column} as demand
            FROM monthly_sales
            WHERE sku_id = %s
            AND {sales_column} IS NOT NULL
            ORDER BY `year_month` DESC
            LIMIT %s
        """

        results = execute_query(query, (sku_id, lookback_months), fetch_all=True)

        # Expert recommendation: Need at least 6 months for reliable trend
        if len(results) < 6:
            # Fallback to category-level growth rate
            return self._get_category_growth_rate(sku_info.get('category'), warehouse)

        # Reverse to chronological order (oldest first) for regression
        results = list(reversed(results))
        n = len(results)

        # Check if SKU has significant seasonality - if so, deseasonalize first
        seasonal_info = self._get_seasonal_info(sku_id, warehouse)
        has_seasonality = seasonal_info.get('cv', 0) > 0.25  # CV > 25% indicates seasonality

        # Extract values and optionally deseasonalize
        x_values = []  # Month indices (0, 1, 2, ...)
        y_values = []  # Demand values (deseasonalized if seasonal pattern exists)
        weights = []   # Weights based on XYZ classification

        for i, row in enumerate(results):
            demand = float(row['demand'])
            if demand > 0:  # Skip zero-demand months (stockouts)
                # Deseasonalize if SKU has significant seasonal pattern
                if has_seasonality and 'factors' in seasonal_info and len(seasonal_info['factors']) > 0:
                    # Extract month number from year_month (YYYY-MM format)
                    month_num = int(row['year_month'].split('-')[1])
                    seasonal_factor = seasonal_info['factors'].get(month_num, 1.0)

                    # Deseasonalize: divide by seasonal factor to get underlying trend
                    if seasonal_factor > 0:
                        demand = demand / seasonal_factor

                x_values.append(i)
                y_values.append(demand)
                weights.append(1.0)  # Temporary weight, will be recalculated below

        # Need at least 6 valid data points after filtering zeros
        if len(x_values) < 6:
            return self._get_category_growth_rate(sku_info.get('category'), warehouse)

        # XYZ-Adaptive Weighting Strategy
        xyz_code = sku_info.get('xyz_code', 'Z')

        if xyz_code == 'X':
            # Stable SKUs: Linear weighting (recent = 2x oldest)
            # Example for 12 months: oldest=1.0, newest=2.0
            n_points = len(x_values)
            max_weight = 2.0
            min_weight = 1.0
            weights = [min_weight + (max_weight - min_weight) * (i / (n_points - 1))
                      for i in range(n_points)]
        elif xyz_code == 'Y':
            # Moderate volatility: Gentler exponential (0.75^(n-i))
            n_points = len(x_values)
            weights = [0.75 ** (n_points - i - 1) for i in range(n_points)]
        else:  # Z - High volatility
            # Volatile SKUs: Aggressive exponential (0.5^(n-i)) - original behavior
            n_points = len(x_values)
            weights = [0.5 ** (n_points - i - 1) for i in range(n_points)]

        # Outlier Detection for Stable SKUs Only
        # Removes data points >2 standard deviations from mean (likely stockouts/errors)
        if xyz_code == 'X' and len(y_values) >= 6:
            mean_demand = statistics.mean(y_values)
            std_demand = statistics.stdev(y_values)

            # Filter outliers (>2 std dev from mean)
            filtered_data = []
            for i in range(len(x_values)):
                if abs(y_values[i] - mean_demand) <= 2 * std_demand:
                    filtered_data.append((x_values[i], y_values[i], weights[i]))

            # Need at least 3 points after filtering
            if len(filtered_data) >= 3:
                # Rebuild arrays with filtered data
                x_values = [d[0] for d in filtered_data]
                y_values = [d[1] for d in filtered_data]
                weights = [d[2] for d in filtered_data]

        # Weighted Linear Regression: y = mx + b
        # Calculate slope (m) using weighted least squares
        sum_w = sum(weights)
        sum_wx = sum(w * x for w, x in zip(weights, x_values))
        sum_wy = sum(w * y for w, y in zip(weights, y_values))
        sum_wx2 = sum(w * x * x for w, x in zip(weights, x_values))
        sum_wxy = sum(w * x * y for w, x, y in zip(weights, x_values, y_values))

        # Calculate weighted averages
        avg_x = sum_wx / sum_w
        avg_y = sum_wy / sum_w

        # Calculate slope using weighted covariance formula
        numerator = sum_wxy - sum_w * avg_x * avg_y
        denominator = sum_wx2 - sum_w * avg_x * avg_x

        if abs(denominator) < 0.001:  # Avoid division by zero
            return self._get_category_growth_rate(sku_info.get('category'), warehouse)

        slope = numerator / denominator

        # Convert slope to monthly rate, then annualize
        # Monthly rate = slope / average demand
        # Annualized rate = monthly rate * 12
        monthly_rate = slope / avg_y if avg_y > 0 else 0.0
        annualized_rate = monthly_rate * 12

        # Cap at ±50% per expert recommendation
        annualized_rate = max(-0.50, min(0.50, annualized_rate))

        # Integrate growth_status field from skus table if available
        growth_status = sku_info.get('growth_status', 'unknown')
        source_suffix = f'_{xyz_code}_seasonal' if has_seasonality else f'_{xyz_code}'

        if growth_status == 'viral' and annualized_rate < 0.20:
            # Ensure minimum 20% growth for viral products
            return (0.20, f'growth_status{source_suffix}')
        elif growth_status == 'declining' and annualized_rate > -0.10:
            # Cap decline at -10% for marked declining products
            return (-0.10, f'growth_status{source_suffix}')

        return (annualized_rate, f'sku_trend{source_suffix}')

    def _get_seasonal_info(self, sku_id: str, warehouse: str) -> Dict:
        """
        Get seasonal pattern information for a SKU.

        Checks if SKU has significant seasonality and returns seasonal factors
        for deseasonalization during growth rate calculation.

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location

        Returns:
            Dictionary with 'cv', 'pattern', and 'factors' keys
            Returns empty dict if no significant seasonality detected
        """
        try:
            # Try to get existing seasonal pattern info
            seasonal_pattern = calculate_seasonal_pattern(sku_id, warehouse)

            # Only return factors if significant seasonality (CV > 25%)
            if seasonal_pattern.get('cv', 0) > 0.25:
                return {
                    'cv': seasonal_pattern['cv'],
                    'pattern': seasonal_pattern['pattern'],
                    'factors': seasonal_pattern.get('factors', {})
                }
        except (ValueError, Exception):
            # SKU doesn't have enough data for seasonal analysis
            pass

        return {}

    def _get_category_growth_rate(self, category: Optional[str], warehouse: str) -> Tuple[float, str]:
        """
        Calculate category-level growth rate as fallback for SKUs with insufficient data.

        Uses weighted average of all SKUs in the same category with sufficient historical data.

        Args:
            category: Product category (e.g., 'Batteries', 'Chargers')
            warehouse: Warehouse location

        Returns:
            Tuple[float, str]: (category_growth_rate, 'category_trend') or (0.0, 'default')
        """
        if not category:
            return (0.0, 'default')

        # Get all SKUs in the same category with sufficient data
        if warehouse == 'combined':
            sales_column = 'corrected_demand_burnaby + corrected_demand_kentucky'
        else:
            sales_column = f'corrected_demand_{warehouse}'

        query = f"""
            SELECT
                ms.sku_id,
                ms.`year_month`,
                {sales_column} as demand
            FROM monthly_sales ms
            JOIN skus s ON ms.sku_id = s.sku_id
            WHERE s.category = %s
            AND {sales_column} IS NOT NULL
            AND {sales_column} > 0
            ORDER BY ms.sku_id, ms.`year_month` DESC
        """

        results = execute_query(query, (category,), fetch_all=True)

        if not results:
            return (0.0, 'default')

        # Group by SKU and calculate individual growth rates
        sku_data = {}
        for row in results:
            sku_id = row['sku_id']
            if sku_id not in sku_data:
                sku_data[sku_id] = []
            sku_data[sku_id].append(float(row['demand']))

        # Calculate average growth rate across all SKUs with 6+ months data
        growth_rates = []
        for sku_id, demands in sku_data.items():
            if len(demands) >= 6:
                # Simple linear regression for each SKU
                n = len(demands)
                demands = list(reversed(demands))  # Chronological order

                x_values = list(range(n))
                sum_x = sum(x_values)
                sum_y = sum(demands)
                sum_xy = sum(x * y for x, y in zip(x_values, demands))
                sum_x2 = sum(x * x for x in x_values)

                avg_y = sum_y / n
                numerator = n * sum_xy - sum_x * sum_y
                denominator = n * sum_x2 - sum_x ** 2

                if abs(denominator) > 0.001 and avg_y > 0:
                    slope = numerator / denominator
                    monthly_rate = slope / avg_y
                    annualized_rate = monthly_rate * 12
                    growth_rates.append(max(-0.50, min(0.50, annualized_rate)))

        if growth_rates:
            avg_category_growth = sum(growth_rates) / len(growth_rates)
            return (avg_category_growth, 'category_trend')

        return (0.0, 'default')

    def generate_forecast_for_sku(self, sku_id: str, warehouse: str = 'combined') -> Dict:
        """
        Generate 12-month forecast for a single SKU.

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location ('burnaby', 'kentucky', 'combined')

        Returns:
            Dictionary containing monthly forecasts and metadata

        Raises:
            ValueError: If SKU not found or insufficient data
        """
        # Get SKU information
        sku_info = self._get_sku_info(sku_id)
        if not sku_info:
            raise ValueError(f"SKU {sku_id} not found")

        # Get base demand (already stockout-corrected from sku_demand_stats)
        # Returns tuple: (base_demand, metadata) where metadata is None for established SKUs
        base_demand, demand_metadata = self._get_base_demand(sku_id, warehouse, sku_info)

        # Get forecasting method based on ABC/XYZ classification
        classification = f"{sku_info['abc_code']}{sku_info['xyz_code']}"
        method_config = self.METHOD_CONFIG.get(
            classification,
            self.METHOD_CONFIG['CZ']  # Default to most conservative method
        )

        # Override method and confidence if demand_metadata provided (new SKU)
        if demand_metadata:
            method_used = demand_metadata.get('method_used', f"{method_config['method']}_ma_{method_config['months']}mo")
            confidence_score = demand_metadata.get('confidence', method_config['confidence'])
        else:
            # Use classification-based defaults for established SKUs
            method_used = f"{method_config['method']}_ma_{method_config['months']}mo"
            confidence_score = method_config['confidence']

        # Calculate SKU-specific growth rate (or use manual override)
        growth_rate, growth_source = self.calculate_sku_growth_rate(sku_id, warehouse, sku_info)

        # Override growth_rate_source if demand_metadata provided
        if demand_metadata and 'growth_rate_source' in demand_metadata:
            growth_source = demand_metadata['growth_rate_source']

        # Get seasonal factors
        seasonal_factors = get_monthly_factors(sku_id, warehouse)

        # Generate 12 monthly forecasts
        monthly_forecasts = self._calculate_monthly_forecasts(
            base_demand,
            seasonal_factors,
            method_config,
            sku_info,
            growth_rate
        )

        # Extract month labels for frontend display
        month_labels = [f['date'] for f in monthly_forecasts]  # e.g., ['2024-10', '2024-11', ...]
        forecast_start_date = monthly_forecasts[0]['date'] if monthly_forecasts else None

        # Package results
        return {
            'sku_id': sku_id,
            'warehouse': warehouse,
            'monthly_forecasts': monthly_forecasts,
            'base_demand_used': base_demand,
            'method_used': method_used,
            'confidence_score': confidence_score,
            'seasonal_pattern': sku_info.get('seasonal_pattern', 'unknown'),
            'growth_rate_applied': growth_rate,
            'growth_rate_source': growth_source,
            'forecast_start_date': forecast_start_date,
            'month_labels': month_labels
        }

    def _get_sku_info(self, sku_id: str) -> Optional[Dict]:
        """Get SKU information including ABC/XYZ classification."""
        query = """
            SELECT sku_id, abc_code, xyz_code, seasonal_pattern,
                   cost_per_unit, status, growth_status, category
            FROM skus
            WHERE sku_id = %s
        """
        result = execute_query(query, (sku_id,), fetch_all=True)
        return result[0] if result else None

    def _get_base_demand(self, sku_id: str, warehouse: str, sku_info: Dict) -> tuple[float, Optional[Dict]]:
        """
        Get base monthly demand using EXISTING corrected_demand from sku_demand_stats.

        This uses the corrected_demand fields which already account for stockouts.
        No additional stockout correction is needed.

        For new SKUs (< 12 months), applies "Test & Learn" pattern detection and returns
        metadata about the methodology used.

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location
            sku_info: SKU information dictionary

        Returns:
            Tuple of (base_demand, metadata) where metadata is:
            - Dict with method_used, growth_rate_source, confidence for new SKUs
            - None for established SKUs using standard classification-based methods
        """
        # First check if this is a new SKU (< 12 months of data in database)
        print(f"[DEBUG V7.3] Checking total months for SKU: {sku_id}")  # TEMPORARY VERIFICATION
        data_check_query = """
            SELECT COUNT(*) as total_months
            FROM monthly_sales
            WHERE sku_id = %s
        """
        data_check_result = execute_query(data_check_query, (sku_id,), fetch_all=True)
        total_months_available = data_check_result[0]['total_months'] if data_check_result else 0
        print(f"[DEBUG V7.3] SKU {sku_id} has {total_months_available} months of data")  # TEMPORARY VERIFICATION

        # If new SKU (< 12 months of data), use limited data methodology
        if total_months_available < 12:
            # Returns tuple: (base_demand, metadata)
            return self._handle_limited_data_sku(sku_id, warehouse, sku_info, total_months_available)

        # For established SKUs (>= 12 months), use normal forecasting method
        classification = f"{sku_info['abc_code']}{sku_info['xyz_code']}"
        method_config = self.METHOD_CONFIG.get(classification, self.METHOD_CONFIG['CZ'])

        # Get recent months of corrected demand
        months_to_fetch = method_config['months'] * 2  # Fetch extra for robustness

        # Calculate cutoff date in Python to avoid SQL escaping issues
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        cutoff_date = (datetime.now() - relativedelta(months=months_to_fetch)).strftime('%Y-%m')

        if warehouse == 'combined':
            query = """
                SELECT
                    corrected_demand_burnaby + corrected_demand_kentucky as total_demand
                FROM monthly_sales
                WHERE sku_id = %s
                  AND `year_month` >= %s
                  AND (corrected_demand_burnaby > 0 OR corrected_demand_kentucky > 0)
                ORDER BY `year_month` DESC
                LIMIT %s
            """
        else:
            demand_column = f'corrected_demand_{warehouse}'
            query = f"""
                SELECT {demand_column} as total_demand
                FROM monthly_sales
                WHERE sku_id = %s
                  AND `year_month` >= %s
                  AND {demand_column} > 0
                ORDER BY `year_month` DESC
                LIMIT %s
            """

        params = (sku_id, cutoff_date, method_config['months'])
        results = execute_query(query, params, fetch_all=True)

        # New SKU check already done at start of method
        # This code path is only reached for established SKUs (>= 12 months of data)
        demands = [float(row['total_demand']) for row in results]

        # Check for empty demands list (can happen if all recent months have zero demand)
        if not demands:
            # Fallback to limited data methodology for data-scarce situations
            # Returns tuple: (base_demand, metadata)
            return self._handle_limited_data_sku(sku_id, warehouse, sku_info, 0)

        # Apply forecasting method (established SKU path)
        if method_config['method'] == 'weighted':
            base_demand = self._weighted_moving_average(demands, method_config['recent_weight'])
        else:
            base_demand = statistics.mean(demands)

        # Return tuple with None metadata for established SKUs
        return base_demand, None

    def _get_demand_from_stats(self, sku_id: str, warehouse: str) -> float:
        """
        Fallback method to get demand from sku_demand_stats table.

        Uses demand_6mo_weighted which is the 6-month weighted moving average.
        """
        query = """
            SELECT demand_6mo_weighted as avg_demand
            FROM sku_demand_stats
            WHERE sku_id = %s AND warehouse = %s
        """

        result = execute_query(query, (sku_id, warehouse), fetch_all=True)
        return float(result[0]['avg_demand']) if result and result[0]['avg_demand'] else 0.0

    def _weighted_moving_average(self, values: List[float], recent_weight: float) -> float:
        """
        Calculate weighted moving average with more weight on recent values.

        Args:
            values: List of historical values (most recent first)
            recent_weight: Weight for most recent value (e.g., 0.70 for 70%)

        Returns:
            Weighted average
        """
        if not values:
            return 0.0

        if len(values) == 1:
            return values[0]

        # Distribute remaining weight evenly across older values
        remaining_weight = 1.0 - recent_weight
        older_weight = remaining_weight / (len(values) - 1)

        weights = [recent_weight] + [older_weight] * (len(values) - 1)
        weighted_sum = sum(v * w for v, w in zip(values, weights))

        return weighted_sum

    def _calculate_monthly_forecasts(
        self,
        base_demand: float,
        seasonal_factors: Dict[int, float],
        method_config: Dict,
        sku_info: Dict,
        growth_rate: float
    ) -> List[Dict]:
        """
        Calculate 12 monthly forecasts with seasonal adjustments.

        Args:
            base_demand: Base monthly demand (stockout-corrected)
            seasonal_factors: Monthly seasonal adjustment factors
            method_config: Forecasting method configuration
            sku_info: SKU information
            growth_rate: Annualized growth rate to apply (-0.5 to 0.5)

        Returns:
            List of 12 monthly forecast dictionaries
        """
        forecasts = []

        # Get latest sales data month (only months with actual sales, not empty placeholders)
        # and start forecast from the NEXT month
        query = """
            SELECT MAX(`year_month`) as latest_month
            FROM monthly_sales
            WHERE (burnaby_sales + kentucky_sales) > 0
        """
        result = execute_query(query, fetch_all=True)

        if result and result[0]['latest_month']:
            from dateutil.relativedelta import relativedelta
            latest_month = datetime.strptime(result[0]['latest_month'], '%Y-%m')
            current_date = latest_month + relativedelta(months=1)
        else:
            # Fallback to current month if no sales data (shouldn't happen)
            current_date = datetime.now().replace(day=1)

        for month_offset in range(12):
            future_date = current_date + relativedelta(months=month_offset)
            month_num = future_date.month

            # Apply seasonal adjustment
            seasonal_factor = float(seasonal_factors.get(month_num, 1.0))
            adjusted_demand = base_demand * seasonal_factor

            # Apply growth rate (compound monthly growth)
            # Convert annual growth rate to monthly compound rate
            # Example: 32% annual = (1.32)^(1/12) = 1.0235 monthly = 2.35% per month
            if growth_rate != 0:
                monthly_growth_rate = (1 + growth_rate) ** (1/12) - 1
                monthly_growth = (1 + monthly_growth_rate) ** month_offset
            else:
                monthly_growth = 1.0

            final_demand = adjusted_demand * monthly_growth

            # Round to integer quantities
            quantity = max(0, round(final_demand))

            # Calculate revenue estimate
            cost_per_unit = float(sku_info.get('cost_per_unit', 0))
            revenue = quantity * cost_per_unit

            forecasts.append({
                'month': month_offset + 1,
                'date': future_date.strftime('%Y-%m'),
                'quantity': quantity,
                'revenue': round(revenue, 2),
                'seasonal_factor': seasonal_factor,
                'growth_factor': round(monthly_growth, 3)
            })

        return forecasts

    def save_forecast(self, forecast_data: Dict) -> bool:
        """
        Save forecast results to forecast_details table.

        Args:
            forecast_data: Forecast dictionary from generate_forecast_for_sku()

        Returns:
            True if successful, False otherwise
        """
        monthly = forecast_data['monthly_forecasts']

        # Extract monthly quantities and revenues
        qty_values = [m['quantity'] for m in monthly]
        rev_values = [m['revenue'] for m in monthly]

        query = """
            INSERT INTO forecast_details
            (forecast_run_id, sku_id, warehouse,
             month_1_qty, month_2_qty, month_3_qty, month_4_qty,
             month_5_qty, month_6_qty, month_7_qty, month_8_qty,
             month_9_qty, month_10_qty, month_11_qty, month_12_qty,
             month_1_rev, month_2_rev, month_3_rev, month_4_rev,
             month_5_rev, month_6_rev, month_7_rev, month_8_rev,
             month_9_rev, month_10_rev, month_11_rev, month_12_rev,
             base_demand_used, seasonal_pattern_applied,
             growth_rate_applied, growth_rate_source, confidence_score, method_used)
            VALUES
            (%s, %s, %s,
             %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
             %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
             %s, %s, %s, %s, %s, %s)
        """

        # Debug logging for V7.3 Phase 3A - verify growth_rate_source persistence
        print(f"[DEBUG V7.3] Saving forecast for {forecast_data['sku_id']}: "
              f"method={forecast_data['method_used']}, "
              f"growth_rate_source={forecast_data.get('growth_rate_source', 'NOT SET')}")

        params = (
            self.forecast_run_id,
            forecast_data['sku_id'],
            forecast_data['warehouse'],
            *qty_values,
            *rev_values,
            forecast_data['base_demand_used'],
            forecast_data['seasonal_pattern'],
            forecast_data['growth_rate_applied'],
            forecast_data['growth_rate_source'],
            forecast_data['confidence_score'],
            forecast_data['method_used']
        )

        try:
            execute_query(query, params, fetch_all=False)
            return True
        except Exception as e:
            print(f"Error saving forecast for {forecast_data['sku_id']}: {e}")
            return False

    def _handle_limited_data_sku(
        self,
        sku_id: str,
        warehouse: str,
        sku_info: Dict,
        available_months: int
    ) -> tuple[float, Dict]:
        """
        Multi-technique forecasting for SKUs with < 12 months data.

        Implements "Test & Learn" pattern for new SKU launches:
        - Detects launch → stockout → recovery patterns
        - Filters stockout noise (< 30% availability months)
        - Applies launch phase adjustments and stockout boosts
        - Uses similar SKU analysis for cross-reference

        Incorporates expert recommendations:
        - View v_sku_demand_analysis for pre-calculated metrics
        - Seasonal factors from seasonal_factors table
        - Growth status from skus.growth_status field
        - Pending inventory check to avoid over-ordering
        - Similar SKU analysis for cross-reference

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location
            sku_info: SKU information dictionary
            available_months: Number of months with data

        Returns:
            Tuple of (base_demand, metadata_dict) where metadata contains:
            - method_used: String describing the methodology applied
            - growth_rate_source: String describing growth rate origin
            - confidence: Confidence score for the forecast
            - launch_pattern_detected: Boolean if test launch pattern found
        """
        # Initialize metadata
        metadata = {
            'method_used': 'limited_data_multi_technique',
            'growth_rate_source': 'new_sku_methodology',
            'confidence': 0.45,  # Lower confidence for new SKUs
            'launch_pattern_detected': False
        }

        # STEP 0: Detect "Test & Learn" launch pattern (EXPERT RECOMMENDATION)
        # Query monthly sales with availability to detect stockout patterns
        if warehouse == 'combined':
            pattern_query = """
                SELECT
                    `year_month`,
                    (corrected_demand_burnaby + corrected_demand_kentucky) as total_demand,
                    CASE
                        WHEN (burnaby_stockout_days + kentucky_stockout_days) >= 20 THEN 0.0
                        WHEN (burnaby_stockout_days + kentucky_stockout_days) >= 10 THEN 0.3
                        WHEN (burnaby_sales + kentucky_sales) > 0 THEN 1.0
                        ELSE 0.5
                    END as availability_rate
                FROM monthly_sales
                WHERE sku_id = %s
                  AND (corrected_demand_burnaby > 0 OR corrected_demand_kentucky > 0
                       OR burnaby_stockout_days > 0 OR kentucky_stockout_days > 0)
                ORDER BY `year_month` ASC
            """
        else:
            demand_col = f'corrected_demand_{warehouse}'
            sales_col = f'{warehouse}_sales'
            stockout_col = f'{warehouse}_stockout_days'
            pattern_query = f"""
                SELECT
                    `year_month`,
                    {demand_col} as total_demand,
                    CASE
                        WHEN {stockout_col} >= 20 THEN 0.0
                        WHEN {stockout_col} >= 10 THEN 0.3
                        WHEN {sales_col} > 0 THEN 1.0
                        ELSE 0.5
                    END as availability_rate
                FROM monthly_sales
                WHERE sku_id = %s
                  AND ({demand_col} > 0 OR {stockout_col} > 0)
                ORDER BY `year_month` ASC
            """

        pattern_data = execute_query(pattern_query, (sku_id,), fetch_all=True)

        # Analyze pattern for Test & Learn characteristics
        had_early_stockout = False
        clean_months_demand = []
        launch_spike_detected = False

        print(f"[DEBUG V7.4 PATTERN] {sku_id}: Found {len(pattern_data) if pattern_data else 0} months of pattern data")

        if pattern_data and len(pattern_data) >= 2:
            # Filter out stockout months (< 30% availability)
            clean_months = [
                float(row['total_demand'])
                for row in pattern_data
                if row['availability_rate'] >= 0.3 and float(row['total_demand']) > 0
            ]

            if clean_months:
                clean_months_demand = clean_months
                print(f"[DEBUG V7.4 PATTERN] {sku_id}: Clean months (availability >= 30%): {clean_months_demand}")

                # Detect launch spike (any month significantly higher than average of others)
                if len(clean_months) >= 2:
                    max_month = max(clean_months)
                    others = [m for m in clean_months if m != max_month]
                    if others:  # Only if there are other months besides max
                        avg_without_max = statistics.mean(others)
                        if max_month > avg_without_max * 1.3:  # 30% higher = spike
                            launch_spike_detected = True
                        print(f"[DEBUG V7.4 PATTERN] {sku_id}: Launch spike check - max={max_month:.2f}, avg_others={avg_without_max:.2f}, threshold={avg_without_max * 1.3:.2f}, detected={launch_spike_detected}")
                    else:
                        print(f"[DEBUG V7.4 PATTERN] {sku_id}: All clean months have same value ({max_month:.2f}), no spike detected")

                # Detect stockout in first 3 months OR first 50% of available data
                check_months = max(3, len(pattern_data) // 2)
                for i, row in enumerate(pattern_data[:check_months]):
                    if row['availability_rate'] < 0.3:
                        had_early_stockout = True
                        print(f"[DEBUG V7.4 PATTERN] {sku_id}: Early stockout found at month {i+1} ({row['year_month']}), availability={row['availability_rate']}")
                        break

                if not had_early_stockout:
                    print(f"[DEBUG V7.4 PATTERN] {sku_id}: No early stockout in first {check_months} months")

        # Apply Test & Learn adjustments if pattern detected
        if had_early_stockout or launch_spike_detected:
            metadata['launch_pattern_detected'] = True
            metadata['method_used'] = 'limited_data_test_launch'
            metadata['confidence'] = 0.55  # Higher confidence when pattern is clear
            print(f"[DEBUG V7.4 PATTERN] {sku_id}: Pattern detected! spike={launch_spike_detected}, stockout={had_early_stockout}")

            # Calculate baseline with launch pattern logic
            if clean_months_demand:
                if len(clean_months_demand) <= 3:
                    # Still in launch phase - adjust for inflated early demand
                    launch_multiplier = 1.5 if launch_spike_detected else 1.2
                    baseline_from_pattern = max(clean_months_demand) / launch_multiplier
                    print(f"[DEBUG V7.4 PATTERN] {sku_id}: Launch phase - max={max(clean_months_demand):.2f} / {launch_multiplier} = {baseline_from_pattern:.2f}")
                else:
                    # Post-launch stabilization - use weighted average
                    # More weight to recent months (70% recent, 30% older)
                    if len(clean_months_demand) >= 6:
                        recent = clean_months_demand[-3:]
                        older = clean_months_demand[:-3]
                        baseline_from_pattern = (statistics.mean(recent) * 0.7) + (statistics.mean(older) * 0.3)
                        print(f"[DEBUG V7.4 PATTERN] {sku_id}: Post-launch weighted - recent={statistics.mean(recent):.2f}, older={statistics.mean(older):.2f}, baseline={baseline_from_pattern:.2f}")
                    else:
                        baseline_from_pattern = statistics.mean(clean_months_demand)
                        print(f"[DEBUG V7.4 PATTERN] {sku_id}: Simple average baseline={baseline_from_pattern:.2f}")

                # Apply stockout boost if stockout occurred in first 3 months
                # Stockout = POSITIVE signal that demand exceeded supply
                if had_early_stockout:
                    baseline_before_boost = baseline_from_pattern
                    baseline_from_pattern *= 1.2
                    metadata['growth_rate_source'] = 'proven_demand_stockout'
                    print(f"[DEBUG V7.4 PATTERN] {sku_id}: Stockout boost applied - {baseline_before_boost:.2f} * 1.2 = {baseline_from_pattern:.2f}")
            else:
                baseline_from_pattern = None
                print(f"[DEBUG V7.4 PATTERN] {sku_id}: Pattern detected but no clean months - baseline=None")
        else:
            baseline_from_pattern = None
            print(f"[DEBUG V7.4 PATTERN] {sku_id}: No pattern detected - baseline=None")

        # STEP 1: Try to use v_sku_demand_analysis view (EXPERT RECOMMENDATION)
        query = """
            SELECT
                demand_3mo_weighted,
                demand_6mo_weighted,
                coefficient_variation,
                volatility_class
            FROM v_sku_demand_analysis
            WHERE sku_id = %s
        """

        view_data = execute_query(query, (sku_id,), fetch_all=True)

        if view_data and view_data[0]['demand_3mo_weighted']:
            base_from_actual = float(view_data[0]['demand_3mo_weighted'])
        else:
            # Fallback to simple average if view doesn't have data
            base_from_actual = self._calculate_simple_average(sku_id, warehouse, available_months)

        # STEP 2: Find similar SKUs and get their average demand
        similar_skus = self._find_similar_skus(sku_id, sku_info, warehouse)

        if similar_skus:
            similar_demands = []
            for similar_sku_id in similar_skus[:5]:  # Top 5 similar SKUs
                # Use v_sku_demand_analysis for similar SKUs too
                similar_query = "SELECT demand_6mo_weighted FROM v_sku_demand_analysis WHERE sku_id = %s"
                similar_result = execute_query(similar_query, (similar_sku_id,), fetch_all=True)

                if similar_result and similar_result[0]['demand_6mo_weighted']:
                    similar_demands.append(float(similar_result[0]['demand_6mo_weighted']))

            if similar_demands:
                base_from_similar = statistics.mean(similar_demands)

                # V7.3 Phase 3A: Similar SKU Seasonal Factor Averaging
                # For new SKUs with limited data (< 12 months), we apply seasonal patterns
                # from similar SKUs (same category, ABC code) that have established patterns.
                # This helps new products follow expected seasonal trends before they have
                # their own historical data. The seasonal boost is applied in STEP 4 below.
                # Note: Growth rates from similar SKUs are NOT used (user decision - needs validation)
                seasonal_boost = self._get_average_seasonal_factor(similar_skus, warehouse)
            else:
                base_from_similar = 0.0
                seasonal_boost = 1.0
        else:
            base_from_similar = 0.0
            seasonal_boost = 1.0

        # STEP 3: Combine actual and similar data with intelligent weighting
        # Prioritize baseline_from_pattern if Test & Learn pattern was detected
        if baseline_from_pattern is not None:
            # Use pattern-based calculation WITHOUT blending
            # Pattern already includes stockout boost (1.2x) and launch adjustments (1.2-1.5x)
            base_demand = baseline_from_pattern
            print(f"[DEBUG V7.3] Using pattern baseline: {base_demand:.2f} (no blending)")

        elif base_from_actual > 0 and base_from_similar > 0:
            # More weight to actual data as months increase
            weight_actual = min(0.5 + (available_months * 0.1), 0.8)
            weight_similar = 1.0 - weight_actual
            base_demand = (base_from_actual * weight_actual) + (base_from_similar * weight_similar)
            print(f"[DEBUG V7.3] Blended baseline: actual={base_from_actual:.2f}, similar={base_from_similar:.2f}, result={base_demand:.2f}")

        elif base_from_actual > 0:
            base_demand = base_from_actual
            print(f"[DEBUG V7.3] Using actual only: {base_demand:.2f}")

        elif base_from_similar > 0:
            base_demand = base_from_similar
            print(f"[DEBUG V7.3] Using similar only: {base_demand:.2f}")

        else:
            # Last resort: category average
            base_demand = self._get_category_average(sku_info.get('category', 'unknown'), warehouse)
            print(f"[DEBUG V7.3] Using category average: {base_demand:.2f}")

        # STEP 4: Apply seasonal boost (if from similar SKUs)
        base_demand *= seasonal_boost

        # STEP 5: Integrate growth_status from skus table (EXPERT RECOMMENDATION)
        growth_multiplier = 1.0
        growth_status = sku_info.get('growth_status')

        if growth_status == 'viral':
            growth_multiplier = 1.2  # 20% boost for viral products
        elif growth_status == 'declining':
            growth_multiplier = 0.8  # 20% reduction for declining products

        base_demand *= growth_multiplier

        # STEP 6: Check pending inventory to avoid over-ordering (EXPERT RECOMMENDATION)
        pending_qty = self._get_pending_quantity(sku_id, warehouse)

        # Only apply large safety multiplier if NOT using pattern-based forecast
        if baseline_from_pattern is None:
            # Standard path for non-pattern SKUs
            if pending_qty > 0:
                # Reduce safety multiplier if significant inventory pending
                pending_coverage = pending_qty / base_demand if base_demand > 0 else 0

                if pending_coverage >= 3.0:  # 3+ months coverage pending
                    safety_multiplier = 0.9  # Reduce buffer significantly
                elif pending_coverage >= 1.5:  # 1.5+ months pending
                    safety_multiplier = 1.0  # No additional buffer
                else:
                    # Normal safety multipliers for new SKUs
                    safety_multiplier = 1.5 if available_months < 3 else 1.3
            else:
                # No pending inventory - use standard safety multipliers
                safety_multiplier = 1.5 if available_months < 3 else 1.3
        else:
            # Pattern-based forecast - minimal safety multiplier
            # Pattern already includes 1.2x stockout boost, avoid double-counting
            safety_multiplier = 1.1
            print(f"[DEBUG V7.3] Pattern detected - using minimal safety multiplier: {safety_multiplier}")

        print(f"[DEBUG V7.3] pending_qty={pending_qty}, safety_multiplier={safety_multiplier}")
        adjusted_base_demand = base_demand * safety_multiplier
        print(f"[DEBUG V7.3] adjusted_base_demand: {adjusted_base_demand:.2f}")

        # STEP 7: Check similar SKU stockout patterns (EXPERT RECOMMENDATION)
        if similar_skus:
            stockout_risk = self._check_stockout_patterns(similar_skus)
            if stockout_risk > 0.5:  # High stockout risk
                adjusted_base_demand *= 1.1  # Additional 10% buffer

        # Return both the adjusted base demand and metadata
        return adjusted_base_demand, metadata

    def _calculate_simple_average(self, sku_id: str, warehouse: str, months: int) -> float:
        """
        Calculate simple average demand from available monthly_sales data.

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location
            months: Number of months to average

        Returns:
            Simple average of available demand data
        """
        if warehouse == 'combined':
            query = """
                SELECT corrected_demand_burnaby + corrected_demand_kentucky as total_demand
                FROM monthly_sales
                WHERE sku_id = %s
                  AND (corrected_demand_burnaby > 0 OR corrected_demand_kentucky > 0)
                ORDER BY `year_month` DESC
                LIMIT %s
            """
        else:
            demand_column = f'corrected_demand_{warehouse}'
            query = f"""
                SELECT {demand_column} as total_demand
                FROM monthly_sales
                WHERE sku_id = %s
                  AND {demand_column} > 0
                ORDER BY `year_month` DESC
                LIMIT %s
            """

        results = execute_query(query, (sku_id, months), fetch_all=True)

        if not results:
            return 0.0

        demands = [float(row['total_demand']) for row in results]
        return statistics.mean(demands) if demands else 0.0

    def _find_similar_skus(self, sku_id: str, sku_info: Dict, warehouse: str) -> List[str]:
        """
        Find similar SKUs based on category, ABC/XYZ classification, and demand patterns.

        V7.3 Phase 3A: This function is used to find comparable SKUs for new products
        with limited historical data. Similar SKUs must match on:
        - Same category (e.g., "Motorcycle Battery")
        - Same ABC code (value classification: A/B/C)
        - Active status only

        The returned SKUs are used to:
        1. Apply seasonal patterns to new SKUs (via _get_average_seasonal_factor)
        2. Calculate baseline demand from similar product performance

        Args:
            sku_id: Current SKU identifier
            sku_info: SKU information dictionary
            warehouse: Warehouse location

        Returns:
            List of similar SKU IDs (max 10)
        """
        # Find SKUs with same category and similar classification
        query = """
            SELECT sku_id
            FROM skus
            WHERE sku_id != %s
              AND category = %s
              AND abc_code = %s
              AND status = 'Active'
            ORDER BY sku_id
            LIMIT 10
        """

        results = execute_query(
            query,
            (sku_id, sku_info.get('category', 'unknown'), sku_info.get('abc_code', 'C')),
            fetch_all=True
        )

        return [row['sku_id'] for row in results] if results else []

    def _get_average_seasonal_factor(self, similar_sku_ids: List[str], warehouse: str) -> float:
        """
        Get average seasonal factor from similar SKUs for current month.

        Uses existing seasonal_factors table to apply seasonality to new SKUs.

        Args:
            similar_sku_ids: List of similar SKU IDs
            warehouse: Warehouse location

        Returns:
            Average seasonal factor (1.0 = no adjustment)
        """
        if not similar_sku_ids:
            return 1.0

        current_month = datetime.now().month

        placeholders = ','.join(['%s'] * len(similar_sku_ids))
        query = f"""
            SELECT AVG(seasonal_factor) as avg_factor
            FROM seasonal_factors
            WHERE sku_id IN ({placeholders})
              AND warehouse = %s
              AND month_number = %s
              AND confidence_level >= 0.5
        """

        params = similar_sku_ids + [warehouse, current_month]
        result = execute_query(query, tuple(params), fetch_all=True)

        if result and result[0]['avg_factor']:
            return float(result[0]['avg_factor'])

        return 1.0  # No seasonal adjustment

    def _get_pending_quantity(self, sku_id: str, warehouse: str) -> int:
        """
        Check pending inventory to avoid over-ordering.

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location

        Returns:
            Total quantity pending arrival
        """
        query = """
            SELECT SUM(quantity) as total_pending
            FROM pending_inventory
            WHERE sku_id = %s
              AND destination = %s
              AND status IN ('ordered', 'shipped', 'pending')
              AND expected_arrival >= CURDATE()
        """

        result = execute_query(query, (sku_id, warehouse), fetch_all=True)

        if result and result[0]['total_pending']:
            return int(result[0]['total_pending'])

        return 0

    def _check_stockout_patterns(self, similar_sku_ids: List[str]) -> float:
        """
        Check if similar SKUs have chronic stockout patterns.

        Returns risk score 0.0-1.0 based on stockout frequency.

        Args:
            similar_sku_ids: List of similar SKU IDs

        Returns:
            Stockout risk score (0.0 = low risk, 1.0 = high risk)
        """
        if not similar_sku_ids:
            return 0.0

        placeholders = ','.join(['%s'] * len(similar_sku_ids))
        query = f"""
            SELECT AVG(frequency_score) as avg_frequency
            FROM stockout_patterns
            WHERE sku_id IN ({placeholders})
              AND pattern_type IN ('chronic', 'seasonal')
        """

        result = execute_query(query, tuple(similar_sku_ids), fetch_all=True)

        if result and result[0]['avg_frequency']:
            return float(result[0]['avg_frequency'])

        return 0.0  # No stockout pattern data

    def _get_category_average(self, category: str, warehouse: str) -> float:
        """
        Get category-wide average demand as last resort fallback.

        Args:
            category: Product category
            warehouse: Warehouse location

        Returns:
            Average demand for the category
        """
        query = """
            SELECT AVG(demand_6mo_weighted) as avg_demand
            FROM v_sku_demand_analysis vda
            JOIN skus s ON vda.sku_id = s.sku_id
            WHERE s.category = %s
              AND s.status = 'Active'
        """

        result = execute_query(query, (category,), fetch_all=True)

        if result and result[0]['avg_demand']:
            return float(result[0]['avg_demand'])

        return 100.0  # Conservative fallback if no category data


def create_forecast_run(forecast_name: str, growth_assumption: float = 0.0, warehouse: str = 'combined', status: str = 'pending') -> int:
    """
    Create a new forecast run entry.

    V7.3 Phase 4: Added status parameter to support queued forecasts.

    Args:
        forecast_name: User-friendly name for this forecast
        growth_assumption: Manual growth rate override (0.0-1.0)
        warehouse: Warehouse location ('burnaby', 'kentucky', 'combined')
        status: Initial status ('pending' or 'queued')

    Returns:
        ID of the created forecast run
    """
    import pymysql
    from .database import get_database_connection

    # Use direct connection to ensure INSERT and LAST_INSERT_ID() use same connection
    connection = get_database_connection()
    try:
        with connection.cursor() as cursor:
            query = """
                INSERT INTO forecast_runs
                (forecast_name, forecast_date, status, warehouse, growth_assumption, created_by)
                VALUES (%s, CURDATE(), %s, %s, %s, 'system')
            """
            cursor.execute(query, (forecast_name, status, warehouse, growth_assumption))
            connection.commit()

            # Get the inserted ID from the same connection
            return cursor.lastrowid
    finally:
        connection.close()


def update_forecast_run_status(
    run_id: int,
    status: str,
    total_skus: int = None,
    processed_skus: int = None,
    failed_skus: int = None,
    error_message: str = None
) -> None:
    """
    Update forecast run status and progress.

    Args:
        run_id: Forecast run ID
        status: New status (pending, running, completed, failed, cancelled)
        total_skus: Total SKUs to process (optional)
        processed_skus: SKUs processed so far (optional)
        failed_skus: SKUs that failed (optional)
        error_message: Error details if failed (optional)
    """
    updates = ['status = %s']
    params = [status]

    if total_skus is not None:
        updates.append('total_skus = %s')
        params.append(total_skus)

    if processed_skus is not None:
        updates.append('processed_skus = %s')
        params.append(processed_skus)

    if failed_skus is not None:
        updates.append('failed_skus = %s')
        params.append(failed_skus)

    if error_message is not None:
        updates.append('error_message = %s')
        params.append(error_message)

    # Set timestamps based on status
    if status == 'running':
        updates.append('started_at = CURRENT_TIMESTAMP')
    elif status in ['completed', 'failed', 'cancelled']:
        updates.append('completed_at = CURRENT_TIMESTAMP')
        updates.append('duration_seconds = TIMESTAMPDIFF(SECOND, started_at, CURRENT_TIMESTAMP)')

    params.append(run_id)

    query = f"""
        UPDATE forecast_runs
        SET {', '.join(updates)}
        WHERE id = %s
    """

    execute_query(query, tuple(params), fetch_all=False)
