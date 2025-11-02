SELECT `year_month`, corrected_demand_burnaby
FROM monthly_sales
WHERE sku_id = 'ACF-10134'
ORDER BY `year_month` DESC
LIMIT 1;
