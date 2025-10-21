from backend.database import execute_query

# Check monthly_sales for Test Case 2
result = execute_query(
    "SELECT sku_id, corrected_demand_burnaby, corrected_demand_kentucky FROM monthly_sales WHERE sku_id = %s AND `year_month` = %s",
    ('AP-240338001', '2025-08'),
    fetch_all=True
)

print("Monthly Sales for AP-240338001 in 2025-08:")
if result:
    for row in result:
        burnaby = float(row['corrected_demand_burnaby'] or 0)
        kentucky = float(row['corrected_demand_kentucky'] or 0)
        combined = burnaby + kentucky
        print(f"  Burnaby: {burnaby}, Kentucky: {kentucky}, Combined: {combined}")
else:
    print("  NO DATA FOUND")

# Check forecast_accuracy for Test Case 2
result2 = execute_query(
    "SELECT sku_id, warehouse, predicted_demand, actual_demand, stockout_affected, is_actual_recorded FROM forecast_accuracy WHERE sku_id = %s AND forecast_period_start = %s",
    ('AP-240338001', '2025-08-01'),
    fetch_all=True
)

print("\nForecast Accuracy for AP-240338001 in 2025-08:")
if result2:
    for row in result2:
        print(f"  Warehouse: {row['warehouse']}")
        print(f"  Predicted: {row['predicted_demand']}")
        print(f"  Actual: {row['actual_demand']}")
        print(f"  Stockout Affected: {row['stockout_affected']}")
        print(f"  Recorded: {row['is_actual_recorded']}")
else:
    print("  NO DATA FOUND")
