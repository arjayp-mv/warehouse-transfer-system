-- V7.3 Phase 3A: Add new growth_rate_source ENUM values
-- Purpose: Fix growth_rate_source persistence bug for pattern-detected new SKUs
-- Date: 2025-10-20
-- Issue: Code was setting 'new_sku_methodology' and 'proven_demand_stockout'
--        but database ENUM only had: manual_override, sku_trend, category_trend, growth_status, default

-- Add new ENUM values to support V7.3 pattern detection functionality
ALTER TABLE forecast_details
MODIFY COLUMN growth_rate_source
  ENUM(
    'manual_override',        -- User manually set growth rate
    'sku_trend',              -- Calculated from SKU's historical trend
    'category_trend',         -- Fallback to category average trend
    'growth_status',          -- Based on skus.growth_status field (viral/declining)
    'default',                -- No growth rate applied (0%)
    'new_sku_methodology',    -- New SKU with limited data (< 12 months)
    'proven_demand_stockout'  -- New SKU pattern: early stockout proves high demand
  )
  DEFAULT 'default';
