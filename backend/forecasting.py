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
from backend.seasonal_calculator import get_monthly_factors


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

    def __init__(self, forecast_run_id: int, growth_rate: float = 0.0):
        """
        Initialize forecast engine for a specific forecast run.

        Args:
            forecast_run_id: ID of the forecast run from forecast_runs table
            growth_rate: Optional manual growth rate override (e.g., 0.05 for 5% growth)
        """
        self.forecast_run_id = forecast_run_id
        self.growth_rate = growth_rate

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
        base_demand = self._get_base_demand(sku_id, warehouse, sku_info)

        # Get forecasting method based on ABC/XYZ classification
        classification = f"{sku_info['abc_code']}{sku_info['xyz_code']}"
        method_config = self.METHOD_CONFIG.get(
            classification,
            self.METHOD_CONFIG['CZ']  # Default to most conservative method
        )

        # Get seasonal factors
        seasonal_factors = get_monthly_factors(sku_id, warehouse)

        # Generate 12 monthly forecasts
        monthly_forecasts = self._calculate_monthly_forecasts(
            base_demand,
            seasonal_factors,
            method_config,
            sku_info
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
            'method_used': f"{method_config['method']}_ma_{method_config['months']}mo",
            'confidence_score': method_config['confidence'],
            'seasonal_pattern': sku_info.get('seasonal_pattern', 'unknown'),
            'growth_rate_applied': self.growth_rate,
            'forecast_start_date': forecast_start_date,
            'month_labels': month_labels
        }

    def _get_sku_info(self, sku_id: str) -> Optional[Dict]:
        """Get SKU information including ABC/XYZ classification."""
        query = """
            SELECT sku_id, abc_code, xyz_code, seasonal_pattern,
                   cost_per_unit, status, growth_status
            FROM skus
            WHERE sku_id = %s
        """
        result = execute_query(query, (sku_id,), fetch_all=True)
        return result[0] if result else None

    def _get_base_demand(self, sku_id: str, warehouse: str, sku_info: Dict) -> float:
        """
        Get base monthly demand using EXISTING corrected_demand from sku_demand_stats.

        This uses the corrected_demand fields which already account for stockouts.
        No additional stockout correction is needed.

        Args:
            sku_id: SKU identifier
            warehouse: Warehouse location
            sku_info: SKU information dictionary

        Returns:
            Base monthly demand (stockout-corrected)
        """
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

        if not results:
            # Fallback to weighted average from sku_demand_stats if no recent data
            return self._get_demand_from_stats(sku_id, warehouse)

        demands = [float(row['total_demand']) for row in results]

        # Apply forecasting method
        if method_config['method'] == 'weighted':
            return self._weighted_moving_average(demands, method_config['recent_weight'])
        else:
            return statistics.mean(demands)

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
        sku_info: Dict
    ) -> List[Dict]:
        """
        Calculate 12 monthly forecasts with seasonal adjustments.

        Args:
            base_demand: Base monthly demand (stockout-corrected)
            seasonal_factors: Monthly seasonal adjustment factors
            method_config: Forecasting method configuration
            sku_info: SKU information

        Returns:
            List of 12 monthly forecast dictionaries
        """
        forecasts = []

        # Get latest sales data month and start forecast from the NEXT month
        # This ensures alignment with actual data availability
        query = "SELECT MAX(`year_month`) as latest_month FROM monthly_sales"
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
            monthly_growth = (1 + self.growth_rate) ** month_offset
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
             growth_rate_applied, confidence_score, method_used)
            VALUES
            (%s, %s, %s,
             %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
             %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
             %s, %s, %s, %s, %s)
        """

        params = (
            self.forecast_run_id,
            forecast_data['sku_id'],
            forecast_data['warehouse'],
            *qty_values,
            *rev_values,
            forecast_data['base_demand_used'],
            forecast_data['seasonal_pattern'],
            forecast_data['growth_rate_applied'],
            forecast_data['confidence_score'],
            forecast_data['method_used']
        )

        try:
            execute_query(query, params, fetch_all=False)
            return True
        except Exception as e:
            print(f"Error saving forecast for {forecast_data['sku_id']}: {e}")
            return False


def create_forecast_run(forecast_name: str, growth_assumption: float = 0.0) -> int:
    """
    Create a new forecast run entry.

    Args:
        forecast_name: User-friendly name for this forecast
        growth_assumption: Manual growth rate override (0.0-1.0)

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
                (forecast_name, forecast_date, status, growth_assumption, created_by)
                VALUES (%s, CURDATE(), 'pending', %s, 'system')
            """
            cursor.execute(query, (forecast_name, growth_assumption))
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
