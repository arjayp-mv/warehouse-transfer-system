-- V7.3 Phase 3A COMPLETE FIX: Add all growth_rate_source ENUM values
-- Purpose: Fix growth_rate_source persistence bug for ALL suffix combinations
-- Date: 2025-10-20
-- Issue: Code generates suffix combinations (_X, _Y, _Z, _seasonal) that weren't in original ENUM
--        Result: 1,211 SKUs had empty growth_rate_source in forecast run 35

-- Code generates these patterns (lines 215-224 in forecasting.py):
-- source_suffix = f'_{xyz_code}_seasonal' if has_seasonality else f'_{xyz_code}'
-- return (annualized_rate, f'sku_trend{source_suffix}')
-- return (annualized_rate, f'growth_status{source_suffix}')

ALTER TABLE forecast_details
MODIFY COLUMN growth_rate_source
  ENUM(
    -- Original values from V7.2
    'manual_override',        -- User manually set growth rate
    'default',                -- No growth rate applied (0%)

    -- V7.3 Phase 3A: New SKU methodologies
    'new_sku_methodology',    -- New SKU with limited data (< 12 months)
    'proven_demand_stockout', -- New SKU pattern: early stockout proves high demand

    -- V7.3 Phase 3A: SKU trend with XYZ suffix combinations
    'sku_trend',              -- Base SKU trend (no suffix)
    'sku_trend_X',            -- SKU trend for X-class (low variability)
    'sku_trend_Y',            -- SKU trend for Y-class (medium variability)
    'sku_trend_Z',            -- SKU trend for Z-class (high variability)
    'sku_trend_X_seasonal',   -- SKU trend X-class with seasonality
    'sku_trend_Y_seasonal',   -- SKU trend Y-class with seasonality
    'sku_trend_Z_seasonal',   -- SKU trend Z-class with seasonality

    -- V7.3 Phase 3A: Growth status with XYZ suffix combinations
    'growth_status',          -- Base growth status (viral/declining)
    'growth_status_X',        -- Growth status for X-class
    'growth_status_Y',        -- Growth status for Y-class
    'growth_status_Z',        -- Growth status for Z-class
    'growth_status_X_seasonal', -- Growth status X-class with seasonality
    'growth_status_Y_seasonal', -- Growth status Y-class with seasonality
    'growth_status_Z_seasonal', -- Growth status Z-class with seasonality

    -- V7.3 Phase 3A: Category trend with XYZ suffix combinations
    'category_trend',         -- Base category trend (no suffix)
    'category_trend_X',       -- Category trend for X-class
    'category_trend_Y',       -- Category trend for Y-class
    'category_trend_Z',       -- Category trend for Z-class
    'category_trend_X_seasonal', -- Category trend X-class with seasonality
    'category_trend_Y_seasonal', -- Category trend Y-class with seasonality
    'category_trend_Z_seasonal'  -- Category trend Z-class with seasonality
  )
  DEFAULT 'default';
