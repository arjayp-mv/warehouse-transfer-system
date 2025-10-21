-- V8.0.1 Database Migration: Add warehouse column to forecast_accuracy table
--
-- Issue: forecast_accuracy table was missing warehouse column, causing:
--   1. Warehouse information to be silently lost when recording forecasts
--   2. Inability to track separate accuracy for burnaby vs kentucky vs combined
--   3. Incorrect actual demand matching (always used combined demand)
--
-- This migration:
--   - Adds warehouse ENUM column
--   - Updates existing records to 'combined' (matches current behavior)
--   - Updates UNIQUE constraint to include warehouse
--   - Adds warehouse-specific index for performance
--
-- Date: 2025-10-21
-- Author: Warehouse Transfer Planning Tool V8.0
-- Related Tasks: TASK-526 (Phase 2 accuracy update)

USE warehouse_transfer;

-- Step 1: Add warehouse column to forecast_accuracy
-- Default to 'combined' for existing records (matches current behavior)
ALTER TABLE forecast_accuracy
ADD COLUMN warehouse ENUM('burnaby', 'kentucky', 'combined') NOT NULL DEFAULT 'combined'
COMMENT 'Warehouse for this forecast (burnaby, kentucky, or combined)'
AFTER sku_id;

-- Step 2: Update existing records to 'combined'
-- (All existing 12 test records are for combined forecasts)
UPDATE forecast_accuracy
SET warehouse = 'combined'
WHERE warehouse IS NULL OR warehouse = '';

-- Step 3: Drop old unique key that doesn't include warehouse
-- This prevents duplicate forecasts for different warehouses
ALTER TABLE forecast_accuracy
DROP KEY unique_forecast;

-- Step 4: Add new unique key that includes warehouse
-- Ensures one forecast per (sku_id, warehouse, forecast_date, period_start)
ALTER TABLE forecast_accuracy
ADD UNIQUE KEY unique_forecast (sku_id, warehouse, forecast_date, forecast_period_start);

-- Step 5: Add index for warehouse-specific accuracy queries
-- Optimizes queries filtering by warehouse and period
ALTER TABLE forecast_accuracy
ADD KEY idx_warehouse_period (warehouse, forecast_period_start, is_actual_recorded);

-- Verification queries (run manually to verify migration):
--
-- Check warehouse distribution:
-- SELECT warehouse, COUNT(*) FROM forecast_accuracy GROUP BY warehouse;
--
-- Check unique constraint works:
-- SELECT sku_id, warehouse, forecast_date, forecast_period_start, COUNT(*)
-- FROM forecast_accuracy
-- GROUP BY sku_id, warehouse, forecast_date, forecast_period_start
-- HAVING COUNT(*) > 1;
--
-- Expected result: No duplicates

-- Migration complete
SELECT 'V8.0.1 Migration Complete: warehouse column added to forecast_accuracy' AS status;
