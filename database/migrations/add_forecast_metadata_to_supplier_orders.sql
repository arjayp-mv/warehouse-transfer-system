-- Add forecast intelligence layer metadata to supplier_order_confirmations table
-- Phase 2 V10.0: Intelligence Layer Integration
-- This migration adds columns to track forecast-based demand, confidence scores, and blending

ALTER TABLE supplier_order_confirmations
ADD COLUMN forecast_demand_monthly DECIMAL(10,2) DEFAULT NULL
    COMMENT 'Monthly demand from forecast system (before blending)'
    AFTER corrected_demand_monthly,
ADD COLUMN demand_source ENUM('forecast', 'blended', 'historical') DEFAULT 'historical'
    COMMENT 'Source of demand: pure forecast, blended, or historical fallback'
    AFTER forecast_demand_monthly,
ADD COLUMN forecast_confidence_score DECIMAL(3,2) DEFAULT NULL
    COMMENT 'ABC/XYZ-based confidence score (0.40-0.90)'
    AFTER demand_source,
ADD COLUMN blend_weight DECIMAL(3,2) DEFAULT NULL
    COMMENT 'Forecast weight in blending (NULL if not blended)'
    AFTER forecast_confidence_score,
ADD COLUMN learning_adjustment_applied TINYINT(1) DEFAULT 0
    COMMENT 'Whether forecast learning adjustments were applied'
    AFTER blend_weight;

-- Add index for demand source analysis queries
CREATE INDEX idx_demand_source ON supplier_order_confirmations(demand_source);

-- Add index for confidence score filtering
CREATE INDEX idx_forecast_confidence ON supplier_order_confirmations(forecast_confidence_score);

-- Migration completed
SELECT 'Forecast metadata columns added to supplier_order_confirmations table' AS status;
