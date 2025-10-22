"""
Forecast Accuracy Tracking Module

Handles recording forecasts with comprehensive context, comparing actuals,
calculating errors, and supporting continuous learning improvements.

This module integrates with existing infrastructure:
- stockout_dates: For stockout-aware accuracy tracking
- monthly_sales.corrected_demand: For true demand (stockout-adjusted)
- sku_demand_stats: For volatility and data quality context
- seasonal_factors: For seasonal confidence context

Part of V8.0 Forecast Learning & Accuracy System
"""

from typing import Dict, List, Optional
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from backend.database import execute_query
import logging

logger = logging.getLogger(__name__)


def record_forecast_for_accuracy_tracking(
    forecast_run_id: int,
    sku_id: str,
    warehouse: str,
    forecast_data: Dict
) -> bool:
    """
    Record forecast predictions to forecast_accuracy table with comprehensive context.

    Creates 12 separate records (one per month) for later comparison with actual sales.
    Captures SKU state at time of forecast (volatility, data quality, seasonal confidence)
    to understand forecast performance in context.

    Args:
        forecast_run_id: ID of the forecast run
        sku_id: SKU identifier
        warehouse: Warehouse location ('burnaby', 'kentucky', 'combined')
        forecast_data: Dictionary from ForecastEngine.generate_forecast_for_sku()
                      Contains: monthly_forecasts, method_used, confidence_score, etc.

    Returns:
        True if successful, False otherwise

    Example forecast_data structure:
        {
            'sku_id': 'UB-YTX14-BS',
            'warehouse': 'combined',
            'monthly_forecasts': [
                {'month': 1, 'date': '2025-10', 'quantity': 950, 'revenue': 92625.00},
                {'month': 2, 'date': '2025-11', 'quantity': 980, 'revenue': 95550.00},
                ...
            ],
            'method_used': 'weighted_ma_6mo',
            'confidence_score': 0.72,
            'seasonal_pattern': 'year-round',
            'base_demand_used': 950.0,
            'growth_rate_applied': 0.10
        }

    Raises:
        No exceptions raised - errors are logged and False is returned

    Notes:
        - This function is called automatically by ForecastEngine.save_forecast()
        - Failures here do NOT prevent forecast from being saved to forecast_details
        - All errors are logged for debugging but treated as non-critical
        - Context fields (volatility, data_quality, seasonal_confidence) may be NULL
          if SKU lacks historical data or seasonal patterns
    """
    try:
        # Get forecast run metadata
        run_query = """
            SELECT forecast_date, created_at
            FROM forecast_runs
            WHERE id = %s
        """
        run_result = execute_query(run_query, (forecast_run_id,), fetch_all=True)

        if not run_result:
            logger.error(f"Forecast run {forecast_run_id} not found in forecast_runs table")
            return False

        forecast_date = run_result[0]['forecast_date']

        # Get SKU classification for tracking
        # Used for ABC/XYZ-specific learning rates in Phase 3
        sku_query = """
            SELECT abc_code, xyz_code, seasonal_pattern
            FROM skus
            WHERE sku_id = %s
        """
        sku_result = execute_query(sku_query, (sku_id,), fetch_all=True)

        if not sku_result:
            logger.warning(f"SKU {sku_id} not found in skus table - using NULL classification")
            abc_class = None
            xyz_class = None
            seasonal_pattern = None
        else:
            abc_class = sku_result[0]['abc_code']
            xyz_class = sku_result[0]['xyz_code']
            seasonal_pattern = sku_result[0]['seasonal_pattern']

        # Enhanced V8.0: Get comprehensive context for each month
        # This captures SKU state at time of forecast for later analysis
        # Helps distinguish true forecast errors from expected variability
        #
        # For 'combined' warehouse forecasts (burnaby + kentucky total demand),
        # we need to query both warehouses and average their metrics
        if warehouse == 'combined':
            context_query = """
                SELECT
                    s.abc_code, s.xyz_code, s.seasonal_pattern, s.growth_status,
                    AVG(sds.coefficient_variation) as coefficient_variation,
                    AVG(sds.data_quality_score) as data_quality_score,
                    AVG(sf.seasonal_factor) as seasonal_factor,
                    AVG(sf.confidence_level) as seasonal_confidence,
                    AVG(sps.pattern_strength) as pattern_strength,
                    AVG(sps.statistical_significance) as statistical_significance
                FROM skus s
                LEFT JOIN sku_demand_stats sds ON s.sku_id = sds.sku_id
                    AND sds.warehouse IN ('burnaby', 'kentucky')
                LEFT JOIN seasonal_factors sf ON s.sku_id = sf.sku_id
                    AND sf.warehouse IN ('burnaby', 'kentucky') AND sf.month_number = %s
                LEFT JOIN seasonal_patterns_summary sps ON s.sku_id = sps.sku_id
                    AND sps.warehouse IN ('burnaby', 'kentucky')
                WHERE s.sku_id = %s
                GROUP BY s.abc_code, s.xyz_code, s.seasonal_pattern, s.growth_status
            """
        else:
            # For single warehouse forecasts, use that warehouse's specific data
            context_query = """
                SELECT
                    s.abc_code, s.xyz_code, s.seasonal_pattern, s.growth_status,
                    sds.coefficient_variation, sds.data_quality_score,
                    sf.seasonal_factor, sf.confidence_level as seasonal_confidence,
                    sps.pattern_strength, sps.statistical_significance
                FROM skus s
                LEFT JOIN sku_demand_stats sds ON s.sku_id = sds.sku_id
                    AND sds.warehouse = %s
                LEFT JOIN seasonal_factors sf ON s.sku_id = sf.sku_id
                    AND sf.warehouse = %s AND sf.month_number = %s
                LEFT JOIN seasonal_patterns_summary sps ON s.sku_id = sps.sku_id
                    AND sps.warehouse = %s
                WHERE s.sku_id = %s
            """

        monthly_forecasts = forecast_data.get('monthly_forecasts', [])
        method_used = forecast_data.get('method_used', 'unknown')

        if not monthly_forecasts:
            logger.warning(f"No monthly_forecasts found in forecast_data for {sku_id}")
            return False

        # Insert one record per month (12 total)
        for month_forecast in monthly_forecasts:
            try:
                # Parse date (format: '2025-10')
                forecast_period_date = datetime.strptime(month_forecast['date'], '%Y-%m')
                month_number = forecast_period_date.month

                # Get context for this specific month (seasonal factors are month-specific)
                if warehouse == 'combined':
                    # Combined warehouse: only needs month_number and sku_id (averages both warehouses)
                    context_result = execute_query(
                        context_query,
                        (month_number, sku_id),
                        fetch_all=True
                    )
                else:
                    # Single warehouse: needs warehouse repeated 3 times, month_number, and sku_id
                    context_result = execute_query(
                        context_query,
                        (warehouse, warehouse, month_number, warehouse, sku_id),
                        fetch_all=True
                    )

                context = context_result[0] if context_result else {}

                # Period is the whole month
                forecast_period_start = forecast_period_date.date()
                forecast_period_end = (
                    forecast_period_date + relativedelta(months=1) - relativedelta(days=1)
                ).date()

                predicted_qty = month_forecast['quantity']

                # Enhanced insert with context fields (V8.0.1: Now includes warehouse)
                # V8.0.1 Phase 4.1: Use ON DUPLICATE KEY UPDATE to allow forecast regeneration
                insert_query = """
                    INSERT INTO forecast_accuracy
                    (sku_id, warehouse, forecast_date, forecast_period_start, forecast_period_end,
                     predicted_demand, forecast_method, abc_class, xyz_class,
                     seasonal_pattern, volatility_at_forecast, data_quality_score,
                     seasonal_confidence_at_forecast, is_actual_recorded)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE
                        predicted_demand = VALUES(predicted_demand),
                        forecast_date = VALUES(forecast_date),
                        forecast_method = VALUES(forecast_method),
                        abc_class = VALUES(abc_class),
                        xyz_class = VALUES(xyz_class),
                        seasonal_pattern = VALUES(seasonal_pattern),
                        volatility_at_forecast = VALUES(volatility_at_forecast),
                        data_quality_score = VALUES(data_quality_score),
                        seasonal_confidence_at_forecast = VALUES(seasonal_confidence_at_forecast),
                        is_actual_recorded = 0,
                        learning_applied = 0,
                        learning_applied_date = NULL
                """

                execute_query(
                    insert_query,
                    (sku_id, warehouse, forecast_date, forecast_period_start, forecast_period_end,
                     predicted_qty, method_used,
                     context.get('abc_code'), context.get('xyz_code'),
                     context.get('seasonal_pattern'),
                     context.get('coefficient_variation'),  # Volatility at forecast time
                     context.get('data_quality_score'),     # Data quality at forecast time
                     context.get('seasonal_confidence')),   # Seasonal confidence at forecast time
                    fetch_all=False
                )

            except Exception as month_error:
                logger.error(
                    f"Error recording month {month_forecast.get('month', '?')} for {sku_id}: {month_error}"
                )
                # Continue with remaining months even if one fails
                continue

        logger.info(f"Recorded {len(monthly_forecasts)} periods with context for {sku_id}")
        return True

    except Exception as e:
        logger.error(f"Error recording forecast for {sku_id}: {e}", exc_info=True)
        return False


def update_monthly_accuracy(target_month: Optional[str] = None) -> Dict:
    """
    Compare actual sales to forecast predictions for a specific month.

    ENHANCED V8.0: Stockout-aware accuracy tracking.
    - Uses corrected_demand from monthly_sales (already accounts for stockouts)
    - Marks forecasts as stockout_affected when stockouts occurred during period
    - Doesn't penalize forecasts when stockout caused under-sales

    This function runs monthly (typically on the 1st) to:
    1. Find forecast_accuracy records with is_actual_recorded = 0
    2. Look up actual sales from monthly_sales for that period
    3. Check stockout_dates for stockouts during forecast period
    4. Calculate errors: absolute_error, percentage_error, MAPE
    5. Update forecast_accuracy with actuals and errors
    6. Mark stockout_affected periods separately

    Args:
        target_month: Month to update in 'YYYY-MM' format.
                     If None, updates previous month (default).

    Returns:
        Dictionary with update statistics:
        {
            'month_updated': '2025-10',
            'total_forecasts': 1768,
            'actuals_found': 1650,
            'missing_actuals': 118,
            'avg_mape': 18.5,
            'stockout_affected_count': 45,
            'errors': []
        }

    Raises:
        No exceptions raised - errors are returned in result dict

    Example:
        # Run on Nov 1st to update October actuals
        result = update_monthly_accuracy(target_month='2025-10')
        print(f"Average MAPE: {result['avg_mape']}%")
        print(f"Stockout-affected: {result['stockout_affected_count']}")

    Notes:
        - Stockout-affected logic: If stockout occurred AND actual < predicted,
          mark stockout_affected=TRUE but don't count error in MAPE
        - Rationale: Forecast was correct, but supply constraint prevented sales
        - MAPE calculation excludes stockout-affected forecasts for accuracy
    """
    # Determine target month
    if target_month is None:
        # Default: previous month
        last_month = datetime.now() - relativedelta(months=1)
        target_month = last_month.strftime('%Y-%m')

    logger.info(f"Starting stockout-aware accuracy update for month: {target_month}")

    # Parse target month
    try:
        target_date = datetime.strptime(target_month, '%Y-%m')
        period_start = target_date.date()
        period_end = (target_date + relativedelta(months=1) - relativedelta(days=1)).date()
    except ValueError as ve:
        logger.error(f"Invalid target_month format: {target_month}. Use YYYY-MM format. Error: {ve}")
        return {'error': f'Invalid month format: {target_month}. Use YYYY-MM'}

    # Find unrecorded forecasts for this period WITH stockout context
    # ENHANCED V8.0.1: Now includes warehouse for proper actual matching
    # ENHANCED: Check stockout_dates table for stockouts during forecast period
    find_forecasts_query = """
        SELECT
            fa.id,
            fa.sku_id,
            fa.warehouse,
            fa.forecast_period_start,
            fa.forecast_period_end,
            fa.predicted_demand,
            fa.forecast_method,
            fa.abc_class,
            fa.xyz_class,
            fa.volatility_at_forecast,
            (SELECT COUNT(*) FROM stockout_dates sd
             WHERE sd.sku_id = fa.sku_id
             AND sd.stockout_date BETWEEN fa.forecast_period_start
                 AND fa.forecast_period_end
             AND sd.is_resolved = 0) as stockout_days
        FROM forecast_accuracy fa
        WHERE fa.forecast_period_start = %s
          AND fa.forecast_period_end = %s
          AND fa.is_actual_recorded = 0
        ORDER BY fa.sku_id, fa.warehouse
    """

    try:
        forecasts = execute_query(
            find_forecasts_query,
            (period_start, period_end),
            fetch_all=True
        )
    except Exception as e:
        logger.error(f"Error finding forecasts for {target_month}: {e}", exc_info=True)
        return {
            'error': f'Database error finding forecasts: {str(e)}',
            'month_updated': target_month
        }

    total_forecasts = len(forecasts)
    logger.info(f"Found {total_forecasts} unrecorded forecasts for {target_month}")

    if total_forecasts == 0:
        return {
            'month_updated': target_month,
            'total_forecasts': 0,
            'message': 'No unrecorded forecasts found for this month'
        }

    # Get actual sales for all SKUs in this month
    # ENHANCED V8.0.1: Now separates burnaby, kentucky, and combined actuals
    # ENHANCED: Use corrected_demand (your existing stockout-adjusted demand!)
    actuals_query = """
        SELECT
            sku_id,
            corrected_demand_burnaby as actual_burnaby,
            corrected_demand_kentucky as actual_kentucky,
            (corrected_demand_burnaby + corrected_demand_kentucky) as actual_combined,
            burnaby_sales,
            kentucky_sales,
            burnaby_stockout_days + kentucky_stockout_days as total_stockout_days
        FROM monthly_sales
        WHERE `year_month` = %s
    """

    try:
        actuals = execute_query(actuals_query, (target_month,), fetch_all=True)
    except Exception as e:
        logger.error(f"Error retrieving actuals for {target_month}: {e}", exc_info=True)
        return {
            'error': f'Database error retrieving actuals: {str(e)}',
            'month_updated': target_month,
            'total_forecasts': total_forecasts
        }

    # Create lookup dictionary for fast access
    # V8.0.1: Now includes warehouse-specific actuals
    actuals_dict = {
        row['sku_id']: {
            'actual_burnaby': float(row['actual_burnaby'] or 0),
            'actual_kentucky': float(row['actual_kentucky'] or 0),
            'actual_combined': float(row['actual_combined'] or 0),
            'actual_sales': int(row['burnaby_sales'] or 0) + int(row['kentucky_sales'] or 0),
            'total_stockout_days': int(row['total_stockout_days'] or 0)
        }
        for row in actuals
    }

    logger.info(f"Retrieved actuals for {len(actuals_dict)} SKUs")

    actuals_found = 0
    missing_actuals = 0
    stockout_affected_count = 0
    errors_list = []
    mape_values = []

    for forecast in forecasts:
        sku_id = forecast['sku_id']
        warehouse = forecast['warehouse']  # V8.0.1: Get warehouse type
        predicted = float(forecast['predicted_demand'])
        stockout_days = forecast['stockout_days']
        stockout_affected = stockout_days > 0

        if sku_id in actuals_dict:
            # V8.0.1: Match actual to warehouse type
            if warehouse == 'burnaby':
                actual = actuals_dict[sku_id]['actual_burnaby']
            elif warehouse == 'kentucky':
                actual = actuals_dict[sku_id]['actual_kentucky']
            else:  # 'combined'
                actual = actuals_dict[sku_id]['actual_combined']

            # Calculate errors
            absolute_error = abs(actual - predicted)

            # Handle division by zero for percentage error
            if actual > 0:
                percentage_error = ((actual - predicted) / actual) * 100
                absolute_percentage_error = abs(percentage_error)
            else:
                # Actual is 0 - special case
                if predicted > 0:
                    # We predicted demand but there was none
                    percentage_error = -100.0  # Over-forecast
                    absolute_percentage_error = 100.0
                else:
                    # Both are 0 - perfect forecast
                    percentage_error = 0.0
                    absolute_percentage_error = 0.0

            # ENHANCED STOCKOUT LOGIC:
            # If stockout affected AND we under-sold (actual < predicted),
            # mark as stockout_affected but don't count error against forecast quality
            # Rationale: Forecast was correct, but supply constraint prevented sales
            try:
                if stockout_affected and actual < predicted:
                    # Stockout caused lower sales than forecast predicted
                    # Still record the error, but mark it as supply-constrained
                    update_query = """
                        UPDATE forecast_accuracy
                        SET actual_demand = %s,
                            absolute_error = %s,
                            percentage_error = %s,
                            absolute_percentage_error = %s,
                            stockout_affected = TRUE,
                            is_actual_recorded = 1
                        WHERE id = %s
                    """
                    # Note: stockout_affected is hard-coded to TRUE in query above
                    execute_query(
                        update_query,
                        (actual, absolute_error, percentage_error,
                         absolute_percentage_error, forecast['id']),
                        fetch_all=False
                    )
                    stockout_affected_count += 1
                    # Don't add to mape_values (exclude from accuracy metrics)
                else:
                    # Normal accuracy update (no stockout, or stockout but over-sold)
                    update_query = """
                        UPDATE forecast_accuracy
                        SET actual_demand = %s,
                            absolute_error = %s,
                            percentage_error = %s,
                            absolute_percentage_error = %s,
                            stockout_affected = %s,
                            is_actual_recorded = 1
                        WHERE id = %s
                    """
                    execute_query(
                        update_query,
                        (actual, absolute_error, percentage_error,
                         absolute_percentage_error, stockout_affected, forecast['id']),
                        fetch_all=False
                    )
                    mape_values.append(absolute_percentage_error)

                actuals_found += 1

            except Exception as update_error:
                logger.error(
                    f"Error updating forecast_accuracy for {sku_id}: {update_error}",
                    exc_info=True
                )
                errors_list.append(f"Update failed for SKU {sku_id}: {str(update_error)}")
                continue

        else:
            # No actual sales data for this SKU this month
            # This can happen for new SKUs or SKUs with zero sales
            missing_actuals += 1
            errors_list.append(f"No actuals for SKU {sku_id}")

    # Calculate aggregate MAPE (excluding stockout-affected forecasts)
    avg_mape = sum(mape_values) / len(mape_values) if mape_values else 0.0

    logger.info(f"Accuracy update complete: {actuals_found} updated, {missing_actuals} missing")
    logger.info(f"Stockout-affected forecasts: {stockout_affected_count}")
    logger.info(f"Average MAPE (excluding stockout-affected): {avg_mape:.2f}%")

    return {
        'month_updated': target_month,
        'total_forecasts': total_forecasts,
        'actuals_found': actuals_found,
        'missing_actuals': missing_actuals,
        'avg_mape': round(avg_mape, 2),
        'stockout_affected_count': stockout_affected_count,
        'errors': errors_list[:10]  # First 10 errors
    }
