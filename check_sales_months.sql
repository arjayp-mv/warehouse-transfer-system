-- Check actual sales data months
SELECT
    `year_month`,
    COUNT(*) as sku_count,
    SUM(burnaby_sales + kentucky_sales) as total_sales
FROM monthly_sales
WHERE `year_month` >= '2025-08'
GROUP BY `year_month`
ORDER BY `year_month` DESC;
