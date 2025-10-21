"""
Test script for V7.3 SKU-specific growth rate calculation

This script tests the new weighted linear regression growth rate calculation
for UB-YTX14-BS, which expert analysis shows has a declining trend.
"""

import sys
sys.path.append('backend')

from forecasting import ForecastEngine
from database import execute_query

# Test SKUs:
# - UB-YTX14-BS: Should show declining trend (expert confirmed -37% from historical data)
# - WF-DA29-00020B: Should show growth if any
test_skus = ['UB-YTX14-BS', 'WF-DA29-00020B']
warehouse = 'burnaby'

print("=" * 80)
print("V7.3 GROWTH RATE CALCULATION TEST")
print("=" * 80)
print()

# Create forecast engine without manual override
engine = ForecastEngine(forecast_run_id=0, manual_growth_override=None)

for sku_id in test_skus:
    print(f"\nTesting SKU: {sku_id}")
    print("-" * 80)

    # Get SKU info
    sku_info_query = """
        SELECT sku_id, abc_code, xyz_code, category, growth_status, seasonal_pattern
        FROM skus
        WHERE sku_id = %s
    """
    sku_info_result = execute_query(sku_info_query, (sku_id,), fetch_all=True)

    if not sku_info_result:
        print(f"ERROR: SKU {sku_id} not found in database")
        continue

    sku_info = sku_info_result[0]
    print(f"Classification: {sku_info['abc_code']}{sku_info['xyz_code']}")
    print(f"Category: {sku_info['category']}")
    print(f"Growth Status: {sku_info['growth_status']}")
    print()

    # Get historical sales data
    if warehouse == 'combined':
        sales_column = 'corrected_demand_burnaby + corrected_demand_kentucky'
    else:
        sales_column = f'corrected_demand_{warehouse}'

    history_query = f"""
        SELECT
            `year_month`,
            {sales_column} as demand
        FROM monthly_sales
        WHERE sku_id = %s
        AND {sales_column} IS NOT NULL
        ORDER BY `year_month` DESC
        LIMIT 12
    """

    history = execute_query(history_query, (sku_id,), fetch_all=True)

    if history:
        print("Historical Demand (Last 12 months):")
        total_demand = 0
        for row in history:
            demand = float(row['demand'])
            total_demand += demand
            print(f"  {row['year_month']}: {demand:,.0f} units")
        print(f"  Average: {total_demand / len(history):,.0f} units/month")
        print()

    # Calculate growth rate
    try:
        growth_rate, growth_source = engine.calculate_sku_growth_rate(
            sku_id, warehouse, sku_info
        )

        print(f"CALCULATED GROWTH RATE:")
        print(f"  Annualized Rate: {growth_rate:+.2%}")
        print(f"  Source: {growth_source}")
        print(f"  Monthly Compound: {((1 + growth_rate) ** (1/12) - 1):+.4%}")

        # Interpretation
        if growth_rate > 0.10:
            trend = "STRONG GROWTH"
        elif growth_rate > 0.05:
            trend = "Moderate Growth"
        elif growth_rate > -0.05:
            trend = "Stable"
        elif growth_rate > -0.10:
            trend = "Moderate Decline"
        else:
            trend = "STRONG DECLINE"

        print(f"  Trend: {trend}")

        # Compare with manual calculation if available
        if sku_id == 'UB-YTX14-BS':
            print()
            print("EXPERT VALIDATION:")
            print("  Expert analysis showed ~37% decline from Apr-Sep 2025")
            print("  (1105 → 693 units = -37.3% over 6 months)")
            if growth_rate < -0.20:
                print("  ✓ Algorithm correctly detected declining trend")
            else:
                print(f"  ! Algorithm detected {growth_rate:.2%}, may need adjustment")

    except Exception as e:
        print(f"ERROR calculating growth rate: {e}")
        import traceback
        traceback.print_exc()

print()
print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
