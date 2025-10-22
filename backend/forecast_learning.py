"""
Forecast Learning Module

Implements self-improving algorithms that adjust forecasting parameters
based on observed accuracy patterns.

This module leverages existing infrastructure:
- ABC/XYZ classification for learning rate tuning
- growth_status (viral/declining/normal) for strategy selection
- stockout_affected filtering to exclude supply-constrained periods
- Category patterns for new SKU fallback

Key Features:
- ABC/XYZ-specific learning rates (AX: careful, CZ: aggressive)
- Growth status-aware adjustments (viral/declining/normal strategies)
- Method effectiveness analysis across SKU classifications
- Problem SKU identification with diagnostic recommendations
- Category-level learning for new/sparse SKUs

Business Rules:
- All adjustments logged as recommendations (applied=FALSE by default)
- Excludes stockout_affected periods from learning analysis
- Requires minimum 3 forecast periods before learning
- Different strategies for different growth statuses

V8.0 Phase 3 - Multi-Dimensional Learning
"""

from typing import Dict, List, Optional, Tuple
from backend.database import execute_query
import statistics
import logging

logger = logging.getLogger(__name__)


class ForecastLearningEngine:
    """
    Comprehensive learning system with multiple strategies.

    Uses ABC/XYZ-specific learning rates, growth status awareness,
    and category-level intelligence for continuous improvement.

    The engine analyzes forecast accuracy patterns and generates
    recommendations for parameter adjustments. Adjustments are
    logged but not automatically applied for safety.

    Attributes:
        learning_rates: Dictionary mapping ABC/XYZ class to learning rates

    Example:
        engine = ForecastLearningEngine()
        growth_result = engine.learn_growth_adjustments()
        method_result = engine.learn_method_effectiveness()
    """

    def __init__(self):
        """
        Initialize learning engine with ABC/XYZ-specific rates.
        """
        self.learning_rates = self._initialize_learning_rates()
        logger.info("ForecastLearningEngine initialized with ABC/XYZ learning rates")

    def _initialize_learning_rates(self) -> Dict[str, Dict[str, float]]:
        """
        ABC/XYZ specific learning rates.

        Rationale:
        - High-value, stable SKUs (AX): Careful adjustments to avoid costly mistakes
        - Low-value, volatile SKUs (CZ): Aggressive learning to improve erratic forecasts
        - Medium combinations: Moderate approach

        Learning rates control how aggressively the system adjusts parameters:
        - Growth rate learning: Applied to growth rate bias corrections
        - Seasonal learning: Applied to seasonal factor adjustments

        Returns:
            Dictionary mapping ABC/XYZ classification to learning rates
            Example: {'AX': {'growth': 0.02, 'seasonal': 0.05}, ...}
        """
        return {
            'AX': {'growth': 0.02, 'seasonal': 0.05},  # Stable, careful
            'AY': {'growth': 0.03, 'seasonal': 0.08},
            'AZ': {'growth': 0.05, 'seasonal': 0.10},
            'BX': {'growth': 0.03, 'seasonal': 0.06},
            'BY': {'growth': 0.04, 'seasonal': 0.09},
            'BZ': {'growth': 0.07, 'seasonal': 0.12},
            'CX': {'growth': 0.05, 'seasonal': 0.08},
            'CY': {'growth': 0.08, 'seasonal': 0.12},
            'CZ': {'growth': 0.10, 'seasonal': 0.15},  # Volatile, aggressive
        }

    def learn_growth_adjustments(self) -> Dict:
        """
        Learn growth rate adjustments by SKU characteristics.

        Analyzes forecast bias patterns to detect consistent over/under-forecasting
        and recommends growth rate adjustments. Uses different strategies based on
        growth status (viral/declining/normal).

        ENHANCED: Growth status-aware (viral/declining/normal strategies)
        Excludes stockout-affected periods from analysis.

        Process:
        1. Query forecast_accuracy for SKUs with consistent bias (>10% avg_bias)
        2. Apply growth status-specific adjustment strategies
        3. Log recommendations to forecast_learning_adjustments table
        4. Do NOT auto-apply (safety measure)

        Returns:
            Dictionary with analysis results:
            {
                'skus_analyzed': int - Number of SKUs with bias patterns
                'adjustments_logged': int - Number of recommendations created
                'message': str - Summary message
            }

        Example:
            result = engine.learn_growth_adjustments()
            # result = {'skus_analyzed': 65, 'adjustments_logged': 65, ...}
        """
        logger.info("Starting growth rate adjustment analysis...")

        # Analyze by growth status
        # IMPORTANT: Exclude stockout_affected periods
        growth_analysis_query = """
            SELECT
                s.sku_id,
                s.growth_status,
                s.abc_code,
                s.xyz_code,
                fd.growth_rate_source,
                fd.growth_rate_applied,
                AVG(fa.percentage_error) as avg_bias,
                STDDEV(fa.percentage_error) as bias_std,
                COUNT(*) as sample_size
            FROM forecast_accuracy fa
            JOIN skus s ON fa.sku_id = s.sku_id
            JOIN forecast_details fd ON fa.sku_id = fd.sku_id
            JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
            WHERE fa.is_actual_recorded = 1
                AND fa.stockout_affected = 0
                AND fa.forecast_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                AND DATE_FORMAT(fa.forecast_period_start, '%Y-%m') =
                    DATE_FORMAT(fr.forecast_date, '%Y-%m')
            GROUP BY s.sku_id, s.growth_status, fd.growth_rate_source, fd.growth_rate_applied
            HAVING sample_size >= 3 AND ABS(avg_bias) > 10
        """

        try:
            results = execute_query(growth_analysis_query, fetch_all=True)
        except Exception as e:
            logger.error(f"Growth analysis query failed: {e}")
            return {
                'skus_analyzed': 0,
                'adjustments_logged': 0,
                'error': str(e)
            }

        logger.info(f"Found {len(results)} SKUs with consistent forecast bias")

        adjustments_made = 0

        for row in results:
            sku_id = row['sku_id']
            classification = f"{row['abc_code']}{row['xyz_code']}"
            avg_bias = float(row['avg_bias'])
            growth_status = row['growth_status']
            current_growth_rate = float(row['growth_rate_applied'])

            # ENHANCED: Different strategies for different growth statuses
            if growth_status == 'viral':
                # Viral products need faster adaptation
                adjustment = min(0.10, avg_bias / 100)  # More aggressive
                direction = 'increase' if avg_bias > 0 else 'decrease'
                reason = f"Viral product with {avg_bias:.2f}% bias - aggressive {direction}"

            elif growth_status == 'declining':
                # Declining products need conservative adjustments
                adjustment = min(0.05, avg_bias / 200)  # More conservative
                direction = 'decrease' if avg_bias < 0 else 'increase'
                reason = f"Declining product with {avg_bias:.2f}% bias - conservative {direction}"

            else:
                # Normal products use standard ABC/XYZ-based learning
                learning_rate = self.learning_rates.get(classification, {}).get('growth', 0.05)
                adjustment = min(0.10, max(-0.10, avg_bias / 100 * learning_rate))
                direction = 'increase' if avg_bias > 0 else 'decrease'
                reason = f"Normal product ({classification}) with {avg_bias:.2f}% bias - {direction} by {abs(adjustment):.3f}"

            # Log adjustment to forecast_learning_adjustments table
            success = self._log_learning_adjustment(
                sku_id=sku_id,
                adjustment_type='growth_rate',
                original_value=current_growth_rate,
                adjustment=adjustment,
                reason=reason,
                mape_before=abs(avg_bias),
                confidence=min(1.0, row['sample_size'] / 10)  # More samples = higher confidence
            )

            if success:
                adjustments_made += 1

        logger.info(f"Growth learning complete: {adjustments_made} adjustments logged")

        return {
            'skus_analyzed': len(results),
            'adjustments_logged': adjustments_made,
            'message': f'Growth rate adjustments logged to forecast_learning_adjustments table'
        }

    def _log_learning_adjustment(
        self,
        sku_id: str,
        adjustment_type: str,
        original_value: float,
        adjustment: float,
        reason: str,
        mape_before: float = None,
        confidence: float = 0.5
    ) -> bool:
        """
        Log learning adjustment to forecast_learning_adjustments table.

        Adjustments are logged as recommendations (applied=FALSE).
        Future enhancement: auto-apply high-confidence adjustments.

        Args:
            sku_id: SKU identifier
            adjustment_type: Type of adjustment ('growth_rate', 'seasonal_factor', etc.)
            original_value: Current parameter value
            adjustment: Size of recommended adjustment (positive or negative)
            reason: Explanation of why adjustment is recommended
            mape_before: Current MAPE before adjustment (optional)
            confidence: Confidence score 0-1 (default: 0.5)

        Returns:
            True if successful, False otherwise
        """
        adjusted_value = original_value + adjustment

        log_query = """
            INSERT INTO forecast_learning_adjustments
            (sku_id, adjustment_type, original_value, adjusted_value,
             adjustment_magnitude, learning_reason, confidence_score,
             mape_before, applied)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE)
        """

        try:
            execute_query(
                log_query,
                (sku_id, adjustment_type, original_value, adjusted_value,
                 adjustment, reason, confidence, mape_before),
                fetch_all=False
            )
            logger.debug(f"Adjustment logged for {sku_id}: {adjustment_type} by {adjustment:.3f}")
            return True

        except Exception as e:
            logger.error(f"Failed to log adjustment for {sku_id}: {e}")
            return False

    def learn_method_effectiveness(self) -> Dict:
        """
        Determine best forecasting method by SKU characteristics.

        Analyzes forecasting method performance across ABC/XYZ classifications,
        seasonal patterns, and growth statuses. Builds recommendation matrix
        for future method switching.

        Process:
        1. Query forecast_accuracy grouped by ABC/XYZ and method
        2. Calculate average MAPE and standard deviation per method
        3. Identify best-performing method for each classification
        4. Build recommendation matrix with confidence scores

        Returns:
            Dictionary with method effectiveness analysis:
            {
                'total_method_classifications': int - Number of method/class combos analyzed
                'best_methods_by_class': dict - Recommendation matrix
            }

        Example:
            result = engine.learn_method_effectiveness()
            # best_methods_by_class = {
            #     ('A', 'X', 'year-round', 'normal'): {
            #         'method': 'weighted_ma_6mo',
            #         'mape': 12.3,
            #         'confidence': 0.85
            #     },
            #     ...
            # }
        """
        logger.info("Analyzing forecasting method performance...")

        method_effectiveness_query = """
            SELECT
                s.abc_code,
                s.xyz_code,
                s.seasonal_pattern,
                s.growth_status,
                fa.forecast_method,
                AVG(fa.absolute_percentage_error) as avg_mape,
                STDDEV(fa.absolute_percentage_error) as mape_std,
                COUNT(DISTINCT fa.sku_id) as sku_count,
                COUNT(*) as forecast_count
            FROM forecast_accuracy fa
            JOIN skus s ON fa.sku_id = s.sku_id
            WHERE fa.is_actual_recorded = 1
                AND fa.stockout_affected = 0
            GROUP BY s.abc_code, s.xyz_code, s.seasonal_pattern,
                     s.growth_status, fa.forecast_method
            HAVING forecast_count >= 10
            ORDER BY s.abc_code, s.xyz_code, avg_mape ASC
        """

        try:
            results = execute_query(method_effectiveness_query, fetch_all=True)
        except Exception as e:
            logger.error(f"Method effectiveness query failed: {e}")
            return {
                'total_method_classifications': 0,
                'best_methods_by_class': {},
                'error': str(e)
            }

        # Build recommendation matrix
        best_methods = {}

        for row in results:
            key = (
                row['abc_code'],
                row['xyz_code'],
                row['seasonal_pattern'],
                row['growth_status']
            )

            # Keep only the best method for each classification
            if key not in best_methods or row['avg_mape'] < best_methods[key]['mape']:
                # Calculate confidence based on standard deviation
                mape_std = float(row['mape_std']) if row['mape_std'] else 0
                confidence = max(0.0, 1.0 - (mape_std / 100)) if mape_std else 0.5

                best_methods[key] = {
                    'method': row['forecast_method'],
                    'mape': float(row['avg_mape']),
                    'confidence': round(confidence, 2),
                    'sku_count': row['sku_count'],
                    'forecast_count': row['forecast_count']
                }

        logger.info(f"Identified best methods for {len(best_methods)} classifications")

        # Log summary statistics
        if best_methods:
            avg_mape = sum(m['mape'] for m in best_methods.values()) / len(best_methods)
            logger.info(f"Average MAPE across best methods: {avg_mape:.2f}%")

        return {
            'total_method_classifications': len(results),
            'best_methods_by_class': best_methods
        }

    def learn_from_categories(self) -> Dict:
        """
        Category-level learning for new/sparse SKUs.

        Use category patterns as fallback when SKU has insufficient history.
        This provides reasonable defaults for new SKUs based on similar
        products in the same category.

        Process:
        1. Aggregate category-level patterns (growth rates, seasonal patterns)
        2. Calculate average MAPE by category
        3. Store patterns for use with new SKUs (future enhancement)

        Returns:
            Dictionary with category analysis:
            {
                'categories_analyzed': int - Number of categories with patterns
                'message': str - Summary message
            }

        Example:
            result = engine.learn_from_categories()
            # result = {'categories_analyzed': 15, 'message': '...'}
        """
        logger.info("Analyzing category patterns for new SKU fallback...")

        category_patterns_query = """
            SELECT
                s.category,
                s.seasonal_pattern,
                AVG(fd.growth_rate_applied) as avg_growth_rate,
                AVG(fa.absolute_percentage_error) as category_mape,
                COUNT(DISTINCT s.sku_id) as sku_count
            FROM skus s
            JOIN forecast_details fd ON s.sku_id = fd.sku_id
            JOIN forecast_runs fr ON fd.forecast_run_id = fr.id
            JOIN forecast_accuracy fa ON s.sku_id = fa.sku_id
                AND DATE_FORMAT(fa.forecast_period_start, '%Y-%m') =
                    DATE_FORMAT(fr.forecast_date, '%Y-%m')
            WHERE fa.is_actual_recorded = 1
            GROUP BY s.category, s.seasonal_pattern
            HAVING sku_count >= 5
        """

        try:
            results = execute_query(category_patterns_query, fetch_all=True)
        except Exception as e:
            logger.error(f"Category patterns query failed: {e}")
            return {
                'categories_analyzed': 0,
                'error': str(e)
            }

        # Log category patterns for visibility
        for row in results:
            logger.info(
                f"Category {row['category']} ({row['seasonal_pattern']}): "
                f"avg growth {float(row['avg_growth_rate']):.3f}, "
                f"MAPE {float(row['category_mape']):.1f}%"
            )

        logger.info(f"Category learning complete: {len(results)} patterns identified")

        return {
            'categories_analyzed': len(results),
            'message': 'Category patterns available for new SKU fallback'
        }


def identify_problem_skus(mape_threshold: float = 30.0) -> List[Dict]:
    """
    Identify SKUs with consistently poor forecast accuracy.

    Flags SKUs where MAPE exceeds threshold over multiple periods,
    providing diagnostic information and actionable recommendations.

    Excludes stockout-affected periods from analysis to focus on
    true forecasting issues rather than supply constraints.

    Args:
        mape_threshold: MAPE above which SKU is considered problematic (default: 30%)

    Returns:
        List of problematic SKUs with diagnostic info and recommendations

    Example:
        problems = identify_problem_skus(mape_threshold=30.0)
        # [
        #     {
        #         'sku_id': 'ABC-123',
        #         'avg_mape': 35.2,
        #         'avg_bias': -15.3,
        #         'xyz_code': 'Z',
        #         'recommendations': [
        #             'High volatility (XYZ=Z): Consider shorter forecast window',
        #             'Consistent under-forecasting: Increase growth rate'
        #         ]
        #     },
        #     ...
        # ]
    """
    logger.info(f"Identifying problem SKUs (MAPE > {mape_threshold}%)...")

    problem_query = """
        SELECT
            fa.sku_id,
            s.description,
            s.abc_code,
            s.xyz_code,
            s.seasonal_pattern,
            COUNT(*) as forecast_periods,
            AVG(fa.absolute_percentage_error) as avg_mape,
            AVG(fa.percentage_error) as avg_bias,
            fa.forecast_method
        FROM forecast_accuracy fa
        JOIN skus s ON fa.sku_id = s.sku_id
        WHERE fa.is_actual_recorded = 1
          AND fa.stockout_affected = 0
          AND fa.forecast_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
        GROUP BY fa.sku_id, fa.forecast_method
        HAVING AVG(fa.absolute_percentage_error) > %s
           AND COUNT(*) >= 3
        ORDER BY avg_mape DESC
        LIMIT 50
    """

    try:
        problems = execute_query(problem_query, (mape_threshold,), fetch_all=True)
    except Exception as e:
        logger.error(f"Problem SKU query failed: {e}")
        return []

    logger.info(f"Found {len(problems)} problem SKUs")

    # Add diagnostic recommendations
    for problem in problems:
        recommendations = []

        # High volatility diagnosis
        if problem['xyz_code'] == 'Z':
            recommendations.append(
                "High volatility (XYZ=Z): Consider shorter forecast window or ensemble methods"
            )

        # Bias diagnosis
        avg_bias = float(problem['avg_bias'])
        if abs(avg_bias) > 20:
            if avg_bias > 0:
                recommendations.append(
                    f"Consistent over-forecasting ({avg_bias:.1f}%): Reduce growth rate"
                )
            else:
                recommendations.append(
                    f"Consistent under-forecasting ({avg_bias:.1f}%): Increase growth rate"
                )

        # Seasonal pattern diagnosis
        if problem['seasonal_pattern'] == 'unknown':
            recommendations.append(
                "No seasonal pattern: Verify sales history length or recalculate seasonality"
            )

        # Method diagnosis
        if problem['forecast_method'] == 'fallback':
            recommendations.append(
                "Using fallback method: SKU may have insufficient history for advanced methods"
            )

        # Convert to regular dict if needed
        problem['recommendations'] = recommendations
        problem['avg_mape'] = float(problem['avg_mape'])
        problem['avg_bias'] = avg_bias

    return problems
