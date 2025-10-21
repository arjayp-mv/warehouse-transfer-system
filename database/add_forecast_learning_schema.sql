-- ============================================================================
-- V8.0 Forecast Learning & Accuracy System - Database Schema Migration
-- ============================================================================
-- This migration adds support for the forecast learning and accuracy tracking
-- system. It enhances the existing forecast_accuracy table with context fields
-- and creates a new table for tracking system-learned adjustments.
--
-- TASKS: TASK-511, TASK-512, TASK-513
-- Created: 2025-10-20
-- Safe to run: YES - All additions are non-breaking (new columns have defaults)
-- ============================================================================

USE warehouse_transfer;

-- ============================================================================
-- PART 1: Enhance forecast_accuracy Table
-- ============================================================================
-- Add context fields to capture SKU state at time of forecast.
-- These fields allow us to understand forecast performance in context and
-- distinguish true forecast errors from expected variability or data quality issues.

ALTER TABLE forecast_accuracy
ADD COLUMN stockout_affected BOOLEAN DEFAULT FALSE
    COMMENT 'TRUE if stockout occurred during forecast period, causing under-sales. Used to avoid penalizing forecast when supply constraint caused low sales, not poor demand prediction.',
ADD COLUMN volatility_at_forecast DECIMAL(5,2) DEFAULT NULL
    COMMENT 'coefficient_variation from sku_demand_stats at time of forecast. Helps understand if high MAPE was expected due to inherent SKU volatility (XYZ class).',
ADD COLUMN data_quality_score DECIMAL(3,2) DEFAULT NULL
    COMMENT 'Data quality score (0.00-1.00) at time of forecast from sku_demand_stats. Indicates completeness and reliability of historical data used for prediction.',
ADD COLUMN seasonal_confidence_at_forecast DECIMAL(5,4) DEFAULT NULL
    COMMENT 'confidence_level from seasonal_factors at time of forecast. Shows how confident we were in seasonal pattern at prediction time.',
ADD COLUMN learning_applied BOOLEAN DEFAULT FALSE
    COMMENT 'TRUE if learning adjustment was applied to this SKU after analyzing this forecast performance. Tracks which SKUs have benefited from learning.',
ADD COLUMN learning_applied_date TIMESTAMP NULL DEFAULT NULL
    COMMENT 'When learning adjustment was applied. NULL if learning_applied is FALSE.';

-- ============================================================================
-- PART 2: Add Performance Indexes
-- ============================================================================
-- These indexes optimize common queries in the learning system:
-- - Finding forecasts that need learning applied
-- - Looking up forecasts for specific periods that have actuals
-- - SKU-level accuracy analysis queries

ALTER TABLE forecast_accuracy
ADD INDEX idx_learning_status (learning_applied, forecast_date)
    COMMENT 'Optimize queries for finding forecasts pending learning adjustments',
ADD INDEX idx_period_recorded (forecast_period_start, is_actual_recorded)
    COMMENT 'Optimize monthly accuracy update job that finds forecasts for specific periods',
ADD INDEX idx_sku_recorded (sku_id, is_actual_recorded, forecast_period_start)
    COMMENT 'Optimize SKU-level accuracy queries and learning analysis';

-- ============================================================================
-- PART 3: Create forecast_learning_adjustments Table
-- ============================================================================
-- This table tracks system-learned adjustments separate from manual user
-- adjustments (which are in the forecast_adjustments table).
--
-- Workflow:
-- 1. Learning engine analyzes forecast errors and creates recommendations
-- 2. Records inserted with applied=FALSE (pending)
-- 3. High-confidence adjustments can be auto-applied
-- 4. Low-confidence adjustments require user approval
-- 5. When applied, applied=TRUE and applied_date is set

CREATE TABLE forecast_learning_adjustments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku_id VARCHAR(50) NOT NULL,
    adjustment_type ENUM(
        'growth_rate',
        'seasonal_factor',
        'method_switch',
        'volatility_adjustment',
        'category_default'
    ) NOT NULL
    COMMENT 'Type of adjustment: growth_rate=change growth rate parameter, seasonal_factor=adjust seasonal multiplier, method_switch=change from weighted_avg to seasonal_adj or vice versa, volatility_adjustment=change safety stock or coverage months, category_default=use category average for new SKUs',

    original_value DECIMAL(10,4) DEFAULT NULL
    COMMENT 'Value before adjustment (e.g., growth_rate=0.05, seasonal_factor=1.25)',

    adjusted_value DECIMAL(10,4) NOT NULL
    COMMENT 'Recommended value after adjustment. This is what the learning system calculated.',

    adjustment_magnitude DECIMAL(10,4) NOT NULL
    COMMENT 'Absolute size of adjustment for tracking and filtering (e.g., 0.03 for 3% change)',

    learning_reason TEXT NOT NULL
    COMMENT 'Human-readable explanation of why this adjustment is recommended. Example: "Consistent 15% over-forecasting for 3 months suggests growth rate should decrease from 0.10 to 0.07"',

    confidence_score DECIMAL(3,2) NOT NULL
    COMMENT 'Confidence in this adjustment (0.00-1.00). Based on: data quality, consistency of error direction, number of forecast periods analyzed. High confidence (>0.8) can be auto-applied.',

    mape_before DECIMAL(5,2) DEFAULT NULL
    COMMENT 'Average MAPE before this adjustment. Used to track learning impact.',

    mape_expected DECIMAL(5,2) DEFAULT NULL
    COMMENT 'Expected MAPE after adjustment based on simulation. Used to prioritize high-impact adjustments.',

    applied BOOLEAN DEFAULT FALSE
    COMMENT 'TRUE when adjustment has been applied to future forecasts. FALSE when pending approval or testing.',

    applied_date TIMESTAMP NULL DEFAULT NULL
    COMMENT 'When adjustment was applied. NULL if not yet applied.',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    COMMENT 'When learning system generated this recommendation',

    FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    INDEX idx_applied (applied, created_at)
        COMMENT 'Find pending adjustments ordered by age',

    INDEX idx_sku_type (sku_id, adjustment_type)
        COMMENT 'Get all adjustments for a SKU by type',

    INDEX idx_confidence (confidence_score DESC, created_at DESC)
        COMMENT 'Find high-confidence adjustments for auto-application'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='System-learned adjustments to forecast parameters based on accuracy analysis. Separate from manual forecast_adjustments table.';

-- ============================================================================
-- PART 4: Verification Queries
-- ============================================================================
-- Run these queries after migration to verify success

-- Verify new columns exist in forecast_accuracy
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'warehouse_transfer'
  AND TABLE_NAME = 'forecast_accuracy'
  AND COLUMN_NAME IN (
      'stockout_affected',
      'volatility_at_forecast',
      'data_quality_score',
      'seasonal_confidence_at_forecast',
      'learning_applied',
      'learning_applied_date'
  )
ORDER BY COLUMN_NAME;

-- Verify indexes were created
SELECT
    INDEX_NAME,
    INDEX_TYPE,
    GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) as COLUMNS
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'warehouse_transfer'
  AND TABLE_NAME = 'forecast_accuracy'
  AND INDEX_NAME IN (
      'idx_learning_status',
      'idx_period_recorded',
      'idx_sku_recorded'
  )
GROUP BY INDEX_NAME, INDEX_TYPE;

-- Verify forecast_learning_adjustments table was created
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'warehouse_transfer'
  AND TABLE_NAME = 'forecast_learning_adjustments'
ORDER BY ORDINAL_POSITION;

-- ============================================================================
-- Migration Complete
-- ============================================================================
-- Next Steps:
-- 1. Verify all columns and indexes created successfully using queries above
-- 2. Test that existing forecast generation still works (no breaking changes)
-- 3. Proceed to Phase 1: Implement backend/forecast_accuracy.py module
-- 4. Update database/schema.sql with these changes for documentation
-- ============================================================================
