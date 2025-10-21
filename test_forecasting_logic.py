"""
Test if the new SKU detection logic is actually running
"""
import sys
sys.path.insert(0, 'C:\\Users\\Arjay\\Downloads\\warehouse-transfer')

from backend.forecasting import ForecastEngine
from backend.database import execute_query

# Create a forecast engine instance
engine = ForecastEngine(forecast_run_id=999, manual_growth_override=None)

# Get SKU info for UB-YTX7A-BS
sku_id = 'UB-YTX7A-BS'
query = "SELECT sku_id, abc_code, xyz_code, seasonal_pattern, cost_per_unit, status, growth_status, category FROM skus WHERE sku_id = %s"
sku_info = execute_query(query, (sku_id,), fetch_all=True)[0]

print(f"\nTesting forecasting logic for {sku_id}")
print(f"SKU Classification: {sku_info['abc_code']}{sku_info['xyz_code']}")

# Call the _get_base_demand method directly to see what path it takes
try:
    base_demand = engine._get_base_demand(sku_id, 'combined', sku_info)
    print(f"Base demand calculated: {base_demand}")
    print(f"\nIf this shows a number around 19.63, it's using OLD logic (simple average)")
    print(f"If it shows something different, it's using NEW logic (limited data methodology)")
except Exception as e:
    print(f"Error: {e}")
