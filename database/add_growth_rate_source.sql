-- V7.3 Enhancement: Add growth_rate_source column to track how growth rate was calculated
-- This provides transparency into whether growth rate came from:
--   - manual_override: User explicitly set the rate
--   - sku_trend: Calculated from SKU's own historical data using weighted regression
--   - category_trend: Fallback to category average when SKU has < 6 months data
--   - growth_status: Applied from skus.growth_status field (viral/declining)
--   - default: No data available, used 0% growth

USE warehouse_transfer;

ALTER TABLE forecast_details
ADD COLUMN growth_rate_source ENUM('manual_override', 'sku_trend', 'category_trend', 'growth_status', 'default')
DEFAULT 'default'
AFTER growth_rate_applied;
