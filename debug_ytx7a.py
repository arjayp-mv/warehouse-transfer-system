"""
Debug why UB-YTX7A-BS is not using limited data methodology
"""
from backend.database import execute_query

sku_id = 'UB-YTX7A-BS'

# Check total months of data
query = """
    SELECT COUNT(*) as total_months
    FROM monthly_sales
    WHERE sku_id = %s
"""
result = execute_query(query, (sku_id,), fetch_all=True)
total_months = result[0]['total_months'] if result else 0

print(f"\nUB-YTX7A-BS Data Check:")
print(f"Total months in monthly_sales: {total_months}")
print(f"Should use limited data? {total_months < 12}")
print(f"Expected: < 12 months → Limited data methodology")
print(f"Actual behavior: Using simple_ma_3mo (normal forecasting)")

# Get SKU classification
query2 = """
    SELECT sku_id, abc_code, xyz_code, status
    FROM skus
    WHERE sku_id = %s
"""
result2 = execute_query(query2, (sku_id,), fetch_all=True)
if result2:
    print(f"\nSKU Classification: {result2[0]['abc_code']}{result2[0]['xyz_code']}")
    print(f"Status: {result2[0]['status']}")
