"""
Query UB-YTX7A-BS historical sales data to analyze data availability
"""
from backend.database import execute_query

# Get all historical sales for UB-YTX7A-BS
query = """
    SELECT
        `year_month`,
        burnaby_sales,
        burnaby_stockout_days,
        corrected_demand_burnaby,
        kentucky_sales,
        kentucky_stockout_days,
        corrected_demand_kentucky,
        (corrected_demand_burnaby + corrected_demand_kentucky) as combined_demand
    FROM monthly_sales
    WHERE sku_id = 'UB-YTX7A-BS'
    ORDER BY `year_month`
"""

results = execute_query(query, fetch_all=True)

print("\n" + "="*80)
print("UB-YTX7A-BS Historical Sales Data")
print("="*80)
print(f"\nTotal months in database: {len(results)}")
print("\nDetailed breakdown:\n")

months_with_sales = 0
total_sales = 0

for row in results:
    month = row['year_month']
    burnaby = row['burnaby_sales'] or 0
    kentucky = row['kentucky_sales'] or 0
    combined = row['combined_demand'] or 0
    burnaby_stockout = row['burnaby_stockout_days'] or 0
    kentucky_stockout = row['kentucky_stockout_days'] or 0

    has_sales = (burnaby + kentucky) > 0
    if has_sales:
        months_with_sales += 1
        total_sales += (burnaby + kentucky)

    print(f"{month}: Burnaby={burnaby:4d} (stockout:{burnaby_stockout:2d}d), "
          f"Kentucky={kentucky:4d} (stockout:{kentucky_stockout:2d}d), "
          f"Combined Demand={combined:6.1f} {'<-- HAS SALES' if has_sales else ''}")

print(f"\n" + "="*80)
print(f"Summary:")
print(f"  - Total months in database: {len(results)}")
print(f"  - Months with actual sales (non-zero): {months_with_sales}")
print(f"  - Total units sold: {total_sales}")
print(f"  - Average per selling month: {total_sales / months_with_sales if months_with_sales > 0 else 0:.1f}")
print("="*80)
