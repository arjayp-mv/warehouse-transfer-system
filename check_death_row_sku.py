"""
Check a Death Row SKU's sales pattern to understand the "zeros" issue
"""
from backend.database import execute_query

sku_id = 'AP-131965300'  # Death Row SKU

# Get all historical sales
query = """
    SELECT
        `year_month`,
        burnaby_sales,
        kentucky_sales,
        (corrected_demand_burnaby + corrected_demand_kentucky) as combined_demand
    FROM monthly_sales
    WHERE sku_id = %s
    ORDER BY `year_month` DESC
    LIMIT 24
"""

results = execute_query(query, (sku_id,), fetch_all=True)

print("\n" + "="*80)
print(f"{sku_id} - Death Row SKU Sales Pattern")
print("="*80)

if results:
    print(f"\nLast 24 months (most recent first):\n")

    months_with_sales = 0
    months_with_zeros = 0
    last_month_with_sales = None

    for row in results:
        month = row['year_month']
        combined = row['combined_demand'] or 0

        if combined > 0:
            months_with_sales += 1
            if last_month_with_sales is None:
                last_month_with_sales = month
        else:
            months_with_zeros += 1

        indicator = "<-- HAS SALES" if combined > 0 else "<-- ZERO"
        print(f"{month}: Combined Demand = {combined:6.1f} {indicator}")

    print(f"\n" + "="*80)
    print(f"Summary:")
    print(f"  - Total months shown: {len(results)}")
    print(f"  - Months with sales (non-zero): {months_with_sales}")
    print(f"  - Months with zeros: {months_with_zeros}")
    print(f"  - Last month with actual sales: {last_month_with_sales or 'NEVER'}")
    print("="*80)
else:
    print("No data found!")
