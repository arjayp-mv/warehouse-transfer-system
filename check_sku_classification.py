"""
Check how SKUs would be classified under the new 12-month rule
"""
from backend.database import execute_query

skus_to_check = ['UB-YTX7A-BS', 'UB-YTX14-BS', 'WF-DA29-00020B', 'CSC-R55']

print("\n" + "="*100)
print("SKU Classification Analysis - 12 Month Rule")
print("="*100)

for sku_id in skus_to_check:
    # Count months with non-zero sales
    query = """
        SELECT COUNT(*) as months_with_sales
        FROM monthly_sales
        WHERE sku_id = %s
          AND (corrected_demand_burnaby > 0 OR corrected_demand_kentucky > 0)
    """
    result = execute_query(query, (sku_id,), fetch_all=True)
    months_with_sales = result[0]['months_with_sales'] if result else 0

    # Get total months in database
    query2 = """
        SELECT COUNT(*) as total_months
        FROM monthly_sales
        WHERE sku_id = %s
    """
    result2 = execute_query(query2, (sku_id,), fetch_all=True)
    total_months = result2[0]['total_months'] if result2 else 0

    # Get ABC/XYZ classification
    query3 = """
        SELECT abc_code, xyz_code, status
        FROM skus
        WHERE sku_id = %s
    """
    result3 = execute_query(query3, (sku_id,), fetch_all=True)
    abc_code = result3[0]['abc_code'] if result3 else 'Unknown'
    xyz_code = result3[0]['xyz_code'] if result3 else 'Unknown'
    status = result3[0]['status'] if result3 else 'Unknown'

    classification = "NEW SKU" if months_with_sales < 12 else "ESTABLISHED"
    method = "Limited Data Methodology" if months_with_sales < 12 else "Normal Forecasting"

    print(f"\n{sku_id}:")
    print(f"  - Total months in DB: {total_months}")
    print(f"  - Months with sales (non-zero): {months_with_sales}")
    print(f"  - ABC-XYZ: {abc_code}{xyz_code}")
    print(f"  - Status: {status}")
    print(f"  - Classification: {classification}")
    print(f"  - Forecasting Method: {method}")

print("\n" + "="*100)
print("Summary: SKUs with < 12 months of non-zero sales = NEW SKU (use limited data methodology)")
print("="*100 + "\n")
