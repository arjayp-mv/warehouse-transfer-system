"""
Seasonal Analysis Script for Warehouse Transfer Planning

Analyzes 2-3 years of historical sales data to calculate data-driven seasonal factors
instead of using fixed multipliers. This approach follows inventory management best
practices by deriving seasonal patterns from actual sales history.

Key Features:
- Calculates monthly seasonal factors: seasonal_factor = month_average / yearly_average
- Identifies statistically significant seasonal patterns
- Generates seasonal factor tables for each SKU with seasonal_pattern flag
- Provides confidence intervals and pattern strength metrics
- Exports results to seasonal_factors database table

Usage:
    python seasonal_analysis.py --sku UB-YTX14-BS --years 3
    python seasonal_analysis.py --all-seasonal --min-confidence 0.7
"""

import argparse
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from scipy import stats
import pymysql
from decimal import Decimal

try:
    from . import database
except ImportError:
    import database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SeasonalAnalyzer:
    """
    Analyzes historical sales data to identify and quantify seasonal patterns

    This class implements data-driven seasonal factor calculation using historical
    sales patterns rather than assumptions. It calculates seasonal factors as:
    seasonal_factor[month] = average_sales_for_month / average_sales_overall

    Attributes:
        min_months_required: Minimum months of data needed for analysis
        significance_threshold: P-value threshold for statistical significance
        min_confidence_level: Minimum confidence level for pattern validation
    """

    def __init__(self, min_months_required: int = 18, significance_threshold: float = 0.15,
                 min_confidence_level: float = 0.6):
        """
        Initialize the Seasonal Analyzer

        Args:
            min_months_required: Minimum months of data required for analysis
            significance_threshold: P-value threshold for statistical significance
            min_confidence_level: Minimum confidence level for reliable patterns
        """
        self.min_months_required = min_months_required
        self.significance_threshold = significance_threshold
        self.min_confidence_level = min_confidence_level

        logger.info(f"SeasonalAnalyzer initialized with min_months={min_months_required}, "
                   f"significance_threshold={significance_threshold}")

    def get_historical_sales_data(self, sku_id: str, years_back: int = 3,
                                warehouse: str = 'kentucky') -> pd.DataFrame:
        """
        Retrieve historical sales data for a specific SKU and warehouse

        Args:
            sku_id: SKU identifier to analyze
            years_back: Number of years of historical data to retrieve
            warehouse: Warehouse to analyze ('kentucky' or 'burnaby')

        Returns:
            DataFrame with columns: year_month, sales, corrected_demand, stockout_days

        Raises:
            ValueError: If insufficient data is available for analysis
        """
        try:
            # Calculate date range for historical data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=years_back * 365)
            start_year_month = start_date.strftime('%Y-%m')

            logger.info(f"Retrieving {years_back} years of data for {sku_id} ({warehouse}) "
                       f"from {start_year_month}")

            # Dynamic column selection based on warehouse
            if warehouse.lower() == 'burnaby':
                sales_col = 'burnaby_sales'
                demand_col = 'corrected_demand_burnaby'
                stockout_col = 'burnaby_stockout_days'
            else:
                sales_col = 'kentucky_sales'
                demand_col = 'corrected_demand_kentucky'
                stockout_col = 'kentucky_stockout_days'

            query = f"""
            SELECT
                `year_month`,
                {sales_col} as sales,
                {demand_col} as corrected_demand,
                {stockout_col} as stockout_days
            FROM monthly_sales
            WHERE sku_id = %s
                AND `year_month` >= %s
                AND ({sales_col} > 0 OR {demand_col} > 0)
            ORDER BY `year_month` ASC
            """

            # Execute query and convert to DataFrame
            db = database.get_database_connection()
            cursor = db.cursor(pymysql.cursors.DictCursor)
            cursor.execute(query, (sku_id, start_year_month))
            raw_data = cursor.fetchall()
            cursor.close()
            db.close()

            if not raw_data:
                raise ValueError(f"No sales data found for {sku_id} in {warehouse}")

            # Convert to DataFrame and add date parsing
            df = pd.DataFrame(raw_data)
            df['year_month'] = pd.to_datetime(df['year_month'] + '-01')
            df['month'] = df['year_month'].dt.month
            df['year'] = df['year_month'].dt.year

            # Use corrected demand where available, otherwise use sales
            df['demand'] = df.apply(
                lambda row: float(row['corrected_demand'] or row['sales'] or 0), axis=1
            )

            logger.info(f"Retrieved {len(df)} months of data for {sku_id}")

            if len(df) < self.min_months_required:
                raise ValueError(f"Insufficient data: {len(df)} months available, "
                               f"{self.min_months_required} required")

            return df

        except Exception as e:
            logger.error(f"Failed to retrieve historical data for {sku_id}: {e}")
            raise

    def calculate_seasonal_factors(self, sales_data: pd.DataFrame) -> Dict:
        """
        Calculate seasonal factors from historical sales data

        Uses the formula: seasonal_factor[month] = month_average / yearly_average
        This approach identifies actual seasonal patterns from historical data.

        Args:
            sales_data: DataFrame with demand data by month

        Returns:
            Dictionary containing seasonal factors and statistical analysis
        """
        try:
            # Calculate monthly averages
            monthly_averages = sales_data.groupby('month')['demand'].agg([
                'mean', 'std', 'count'
            ]).round(2)

            # Calculate overall average (yearly average)
            yearly_average = sales_data['demand'].mean()

            if yearly_average == 0:
                logger.warning("Zero yearly average - cannot calculate seasonal factors")
                return self._get_default_seasonal_result()

            # Calculate seasonal factors
            seasonal_factors = {}
            factor_confidence = {}

            for month in range(1, 13):
                if month in monthly_averages.index:
                    month_avg = monthly_averages.loc[month, 'mean']
                    month_std = monthly_averages.loc[month, 'std']
                    month_count = monthly_averages.loc[month, 'count']

                    # Calculate seasonal factor
                    seasonal_factor = month_avg / yearly_average

                    # Calculate confidence based on data stability
                    if month_count >= 2 and month_std > 0:
                        # Coefficient of variation as stability measure
                        cv = month_std / month_avg if month_avg > 0 else float('inf')
                        confidence = max(0.0, min(1.0, 1.0 - (cv / 2.0)))
                    else:
                        confidence = 0.5  # Default confidence for single data points

                    seasonal_factors[month] = round(float(seasonal_factor), 3)
                    factor_confidence[month] = round(float(confidence), 3)
                else:
                    # No data for this month - use neutral factor
                    seasonal_factors[month] = 1.0
                    factor_confidence[month] = 0.0

            # Perform statistical significance test
            statistical_analysis = self._perform_statistical_tests(sales_data)

            # Calculate pattern strength
            pattern_strength = self._calculate_pattern_strength(seasonal_factors)

            # Determine seasonal pattern type
            pattern_type = self._classify_seasonal_pattern(seasonal_factors)

            result = {
                'seasonal_factors': seasonal_factors,
                'factor_confidence': factor_confidence,
                'yearly_average': round(float(yearly_average), 2),
                'monthly_averages': {int(k): {str(inner_k): float(inner_v) if isinstance(inner_v, (int, float, np.number)) else inner_v
                                           for inner_k, inner_v in v.items()}
                                   for k, v in monthly_averages.to_dict('index').items()},
                'pattern_strength': float(pattern_strength),
                'pattern_type': pattern_type,
                'statistical_significance': statistical_analysis,
                'data_months': int(len(sales_data)),
                'analysis_date': datetime.now().isoformat()
            }

            logger.info(f"Calculated seasonal factors with pattern strength: {pattern_strength:.3f}")
            return result

        except Exception as e:
            logger.error(f"Failed to calculate seasonal factors: {e}")
            return self._get_default_seasonal_result()

    def _perform_statistical_tests(self, sales_data: pd.DataFrame) -> Dict:
        """
        Perform statistical tests to validate seasonal pattern significance

        Uses one-way ANOVA to test if there are statistically significant differences
        between monthly demand patterns. All numpy types are converted to Python
        native types to ensure JSON serialization compatibility.

        Args:
            sales_data: DataFrame with demand data containing 'month' and 'demand' columns

        Returns:
            Dictionary with statistical test results including:
            - test_type: Type of statistical test performed
            - f_statistic: F-statistic value (converted to Python float)
            - p_value: P-value of the test (converted to Python float)
            - is_significant: Boolean indicating statistical significance
            - confidence_level: Confidence level of the result
            - groups_tested: Number of monthly groups in the test

        Note:
            Fixed numpy.bool_ serialization by explicitly converting to Python bool
        """
        try:
            # Group by month for ANOVA test
            monthly_groups = [
                sales_data[sales_data['month'] == month]['demand'].values
                for month in range(1, 13)
                if month in sales_data['month'].values
            ]

            # Remove empty groups
            monthly_groups = [group for group in monthly_groups if len(group) > 0]

            if len(monthly_groups) < 3:
                return {
                    'test_type': 'insufficient_data',
                    'p_value': 1.0,
                    'is_significant': False,
                    'confidence_level': 0.0
                }

            # Perform one-way ANOVA to test for seasonal differences
            f_statistic, p_value = stats.f_oneway(*monthly_groups)

            # Determine significance (convert numpy.bool_ to Python bool for JSON serialization)
            is_significant = bool(p_value < self.significance_threshold)
            confidence_level = 1.0 - p_value if p_value < 1.0 else 0.0

            return {
                'test_type': 'one_way_anova',
                'f_statistic': round(float(f_statistic), 4),
                'p_value': round(float(p_value), 4),
                'is_significant': is_significant,
                'confidence_level': round(float(confidence_level), 3),
                'groups_tested': len(monthly_groups)
            }

        except Exception as e:
            logger.error(f"Statistical test failed: {e}")
            return {
                'test_type': 'error',
                'p_value': 1.0,
                'is_significant': False,
                'confidence_level': 0.0,
                'error': str(e)
            }

    def _calculate_pattern_strength(self, seasonal_factors: Dict[int, float]) -> float:
        """
        Calculate the strength of the seasonal pattern

        Args:
            seasonal_factors: Dictionary of seasonal factors by month

        Returns:
            Pattern strength score (0.0 to 1.0)
        """
        try:
            factors = list(seasonal_factors.values())

            # Calculate coefficient of variation as pattern strength indicator
            mean_factor = np.mean(factors)
            std_factor = np.std(factors)

            if mean_factor == 0:
                return 0.0

            # Pattern strength based on how much factors deviate from 1.0
            deviations = [abs(f - 1.0) for f in factors]
            max_deviation = max(deviations)

            # Normalize to 0-1 scale (max possible deviation is from 0 to 2)
            pattern_strength = min(1.0, max_deviation / 1.0)

            return pattern_strength

        except Exception as e:
            logger.error(f"Pattern strength calculation failed: {e}")
            return 0.0

    def _classify_seasonal_pattern(self, seasonal_factors: Dict[int, float]) -> str:
        """
        Classify the type of seasonal pattern based on factors

        Args:
            seasonal_factors: Dictionary of seasonal factors by month

        Returns:
            Pattern classification string
        """
        try:
            # Find months with highest and lowest factors
            factors_by_month = sorted(seasonal_factors.items(), key=lambda x: x[1])
            low_months = [month for month, factor in factors_by_month[:3]]
            high_months = [month for month, factor in factors_by_month[-3:]]

            # Classification logic
            if any(month in [4, 5, 6, 7, 8, 9] for month in high_months):
                if any(month in [10, 11, 12, 1, 2, 3] for month in low_months):
                    return 'spring_summer'

            if any(month in [10, 11, 12, 1, 2, 3] for month in high_months):
                if any(month in [4, 5, 6, 7, 8, 9] for month in low_months):
                    return 'fall_winter'

            if any(month in [11, 12] for month in high_months):
                return 'holiday'

            # Check if pattern is relatively flat (year-round)
            max_factor = max(seasonal_factors.values())
            min_factor = min(seasonal_factors.values())
            if (max_factor - min_factor) < 0.3:
                return 'year_round'

            return 'custom'

        except Exception as e:
            logger.error(f"Pattern classification failed: {e}")
            return 'unknown'

    def _get_default_seasonal_result(self) -> Dict:
        """Return default seasonal analysis result for error cases"""
        return {
            'seasonal_factors': {month: 1.0 for month in range(1, 13)},
            'factor_confidence': {month: 0.0 for month in range(1, 13)},
            'yearly_average': 0.0,
            'monthly_averages': {},
            'pattern_strength': 0.0,
            'pattern_type': 'unknown',
            'statistical_significance': {
                'test_type': 'none',
                'p_value': 1.0,
                'is_significant': False,
                'confidence_level': 0.0
            },
            'data_months': 0,
            'analysis_date': datetime.now().isoformat(),
            'error': 'insufficient_data'
        }

    def analyze_sku_seasonality(self, sku_id: str, years_back: int = 3,
                              warehouse: str = 'kentucky') -> Dict:
        """
        Complete seasonal analysis for a single SKU

        Args:
            sku_id: SKU identifier to analyze
            years_back: Years of historical data to analyze
            warehouse: Warehouse to analyze

        Returns:
            Complete seasonal analysis results
        """
        try:
            logger.info(f"Starting seasonal analysis for {sku_id} ({warehouse})")

            # Get historical data
            sales_data = self.get_historical_sales_data(sku_id, years_back, warehouse)

            # Calculate seasonal factors
            analysis_result = self.calculate_seasonal_factors(sales_data)

            # Add metadata
            analysis_result.update({
                'sku_id': sku_id,
                'warehouse': warehouse,
                'years_analyzed': years_back,
                'date_range': {
                    'start': sales_data['year_month'].min().strftime('%Y-%m'),
                    'end': sales_data['year_month'].max().strftime('%Y-%m')
                }
            })

            # Log key results
            pattern_strength = analysis_result['pattern_strength']
            pattern_type = analysis_result['pattern_type']
            is_significant = analysis_result['statistical_significance']['is_significant']

            logger.info(f"Analysis complete for {sku_id}: pattern={pattern_type}, "
                       f"strength={pattern_strength:.3f}, significant={is_significant}")

            return analysis_result

        except Exception as e:
            logger.error(f"Seasonal analysis failed for {sku_id}: {e}")
            result = self._get_default_seasonal_result()
            result.update({
                'sku_id': sku_id,
                'warehouse': warehouse,
                'error': str(e)
            })
            return result

    def analyze_all_seasonal_skus(self, min_confidence: float = 0.6) -> List[Dict]:
        """
        Analyze seasonal patterns for all SKUs marked with seasonal_pattern

        Args:
            min_confidence: Minimum confidence threshold for reliable patterns

        Returns:
            List of seasonal analysis results for all seasonal SKUs
        """
        try:
            logger.info(f"Starting bulk seasonal analysis with min_confidence={min_confidence}")

            # Get all SKUs with seasonal patterns
            query = """
            SELECT sku_id, seasonal_pattern, description, category
            FROM skus
            WHERE seasonal_pattern != 'unknown'
                AND seasonal_pattern IS NOT NULL
                AND status = 'Active'
            ORDER BY abc_code, sku_id
            """

            db = database.get_database_connection()
            cursor = db.cursor(pymysql.cursors.DictCursor)
            cursor.execute(query)
            seasonal_skus = cursor.fetchall()
            cursor.close()
            db.close()

            logger.info(f"Found {len(seasonal_skus)} SKUs with seasonal patterns")

            results = []
            successful = 0
            errors = 0

            for sku_record in seasonal_skus:
                try:
                    sku_id = sku_record['sku_id']

                    # Analyze both warehouses
                    for warehouse in ['kentucky', 'burnaby']:
                        analysis = self.analyze_sku_seasonality(sku_id, warehouse=warehouse)

                        # Include original pattern for comparison
                        analysis['original_pattern'] = sku_record['seasonal_pattern']
                        analysis['description'] = sku_record['description']
                        analysis['category'] = sku_record['category']

                        results.append(analysis)

                    successful += 1

                    # Progress logging
                    if successful % 20 == 0:
                        logger.info(f"Processed {successful}/{len(seasonal_skus)} seasonal SKUs")

                except Exception as e:
                    errors += 1
                    logger.error(f"Failed to analyze {sku_record.get('sku_id', 'unknown')}: {e}")

            logger.info(f"Bulk analysis complete: {successful} successful, {errors} errors")
            return results

        except Exception as e:
            logger.error(f"Bulk seasonal analysis failed: {e}")
            return []


def main():
    """
    Command-line interface for seasonal analysis
    """
    parser = argparse.ArgumentParser(description='Analyze seasonal patterns in sales data')
    parser.add_argument('--sku', help='Analyze specific SKU')
    parser.add_argument('--warehouse', default='kentucky', choices=['kentucky', 'burnaby'],
                       help='Warehouse to analyze')
    parser.add_argument('--years', type=int, default=3, help='Years of historical data')
    parser.add_argument('--all-seasonal', action='store_true',
                       help='Analyze all SKUs with seasonal patterns')
    parser.add_argument('--min-confidence', type=float, default=0.6,
                       help='Minimum confidence for pattern reliability')
    parser.add_argument('--export-csv', help='Export results to CSV file')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    analyzer = SeasonalAnalyzer()

    try:
        if args.all_seasonal:
            # Analyze all seasonal SKUs
            logger.info("Starting bulk seasonal analysis")
            results = analyzer.analyze_all_seasonal_skus(args.min_confidence)

            # Print summary
            reliable_patterns = [r for r in results
                               if r['statistical_significance']['confidence_level'] >= args.min_confidence]

            print(f"\n=== SEASONAL ANALYSIS SUMMARY ===")
            print(f"Total SKUs analyzed: {len(results)}")
            print(f"Reliable patterns (confidence >= {args.min_confidence}): {len(reliable_patterns)}")

            # Pattern type distribution
            pattern_types = {}
            for result in reliable_patterns:
                pattern_type = result['pattern_type']
                pattern_types[pattern_type] = pattern_types.get(pattern_type, 0) + 1

            print(f"\nPattern Type Distribution:")
            for pattern_type, count in sorted(pattern_types.items()):
                print(f"  {pattern_type}: {count}")

            # Export if requested
            if args.export_csv:
                import pandas as pd
                df = pd.DataFrame(results)
                df.to_csv(args.export_csv, index=False)
                print(f"\nResults exported to: {args.export_csv}")

        elif args.sku:
            # Analyze specific SKU
            logger.info(f"Analyzing seasonal pattern for {args.sku}")
            result = analyzer.analyze_sku_seasonality(args.sku, args.years, args.warehouse)

            print(f"\n=== SEASONAL ANALYSIS: {args.sku} ({args.warehouse}) ===")
            print(f"Pattern Type: {result['pattern_type']}")
            print(f"Pattern Strength: {result['pattern_strength']:.3f}")
            print(f"Statistical Significance: {result['statistical_significance']['is_significant']}")
            print(f"Confidence Level: {result['statistical_significance']['confidence_level']:.3f}")
            print(f"Data Months: {result['data_months']}")

            print(f"\nSeasonal Factors by Month:")
            for month, factor in result['seasonal_factors'].items():
                confidence = result['factor_confidence'][month]
                month_name = datetime(2024, month, 1).strftime('%B')
                print(f"  {month_name:>9}: {factor:>5.3f} (confidence: {confidence:.3f})")

        else:
            parser.print_help()
            print("\nExamples:")
            print("  python seasonal_analysis.py --sku UB-YTX14-BS --years 3")
            print("  python seasonal_analysis.py --all-seasonal --min-confidence 0.7")

    except KeyboardInterrupt:
        logger.info("Analysis interrupted by user")
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())