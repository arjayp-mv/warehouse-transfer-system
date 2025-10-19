-- ================================================
-- Warehouse Transfer Planning Tool
-- Database Migration: Forecasting Tables
-- Version: 7.0
-- Date: 2025-10-18
-- ================================================
--
-- This migration adds three tables for the 12-month sales forecasting system:
-- 1. forecast_runs - Master table tracking forecast generation runs
-- 2. forecast_details - Detailed monthly forecasts for each SKU/warehouse
-- 3. forecast_adjustments - Log of manual forecast adjustments
--
-- Usage:
-- 1. Open phpMyAdmin (http://localhost/phpmyadmin)
-- 2. Select warehouse_transfer database
-- 3. Import this file via SQL tab
-- 4. Verify all tables created successfully
-- ================================================

-- Table structure for forecast_runs
-- Master table tracking each forecast generation run
CREATE TABLE IF NOT EXISTS `forecast_runs` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `forecast_name` VARCHAR(100) NOT NULL COMMENT 'User-friendly name for this forecast',
  `forecast_date` DATE NOT NULL COMMENT 'Date when forecast was generated',
  `forecast_type` ENUM('monthly', 'quarterly', 'annual') DEFAULT 'monthly' COMMENT 'Forecast granularity',
  `status` ENUM('pending', 'running', 'completed', 'failed', 'cancelled') DEFAULT 'pending' COMMENT 'Current status of forecast generation',
  `growth_assumption` DECIMAL(5,2) DEFAULT 0.00 COMMENT 'Manual growth rate override (percentage)',
  `created_by` VARCHAR(100) DEFAULT 'system' COMMENT 'User who created this forecast',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp of forecast creation',
  `started_at` TIMESTAMP NULL COMMENT 'When forecast generation started',
  `completed_at` TIMESTAMP NULL COMMENT 'When forecast generation completed',
  `approved_by` VARCHAR(100) NULL COMMENT 'User who approved this forecast',
  `approved_at` TIMESTAMP NULL COMMENT 'When forecast was approved',
  `notes` TEXT NULL COMMENT 'User notes about this forecast',
  `total_skus` INT DEFAULT 0 COMMENT 'Total SKUs to process',
  `processed_skus` INT DEFAULT 0 COMMENT 'SKUs processed so far',
  `failed_skus` INT DEFAULT 0 COMMENT 'SKUs that failed to process',
  `duration_seconds` DECIMAL(8,2) NULL COMMENT 'Total processing time in seconds',
  `error_message` TEXT NULL COMMENT 'Error details if status is failed',
  INDEX `idx_forecast_status` (`status`),
  INDEX `idx_forecast_date` (`forecast_date`),
  INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='Master table tracking forecast generation runs';

-- Table structure for forecast_details
-- Stores detailed monthly forecasts for each SKU and warehouse
CREATE TABLE IF NOT EXISTS `forecast_details` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `forecast_run_id` INT NOT NULL COMMENT 'Links to forecast_runs table',
  `sku_id` VARCHAR(50) NOT NULL COMMENT 'Links to skus table',
  `warehouse` ENUM('burnaby', 'kentucky', 'combined') NOT NULL COMMENT 'Warehouse location',

  -- Monthly quantity forecasts (next 12 months)
  `month_1_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 1',
  `month_2_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 2',
  `month_3_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 3',
  `month_4_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 4',
  `month_5_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 5',
  `month_6_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 6',
  `month_7_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 7',
  `month_8_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 8',
  `month_9_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 9',
  `month_10_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 10',
  `month_11_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 11',
  `month_12_qty` INT DEFAULT 0 COMMENT 'Forecast quantity for month 12',

  -- Monthly revenue forecasts (next 12 months)
  `month_1_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 1',
  `month_2_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 2',
  `month_3_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 3',
  `month_4_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 4',
  `month_5_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 5',
  `month_6_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 6',
  `month_7_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 7',
  `month_8_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 8',
  `month_9_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 9',
  `month_10_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 10',
  `month_11_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 11',
  `month_12_rev` DECIMAL(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 12',

  -- Summary statistics (calculated columns)
  `total_qty_forecast` INT GENERATED ALWAYS AS (
    month_1_qty + month_2_qty + month_3_qty + month_4_qty +
    month_5_qty + month_6_qty + month_7_qty + month_8_qty +
    month_9_qty + month_10_qty + month_11_qty + month_12_qty
  ) STORED COMMENT 'Total forecasted quantity for 12 months',

  `total_rev_forecast` DECIMAL(14,2) GENERATED ALWAYS AS (
    month_1_rev + month_2_rev + month_3_rev + month_4_rev +
    month_5_rev + month_6_rev + month_7_rev + month_8_rev +
    month_9_rev + month_10_rev + month_11_rev + month_12_rev
  ) STORED COMMENT 'Total forecasted revenue for 12 months',

  `avg_monthly_qty` DECIMAL(10,2) GENERATED ALWAYS AS (
    total_qty_forecast / 12
  ) STORED COMMENT 'Average monthly quantity',

  `avg_monthly_rev` DECIMAL(12,2) GENERATED ALWAYS AS (
    total_rev_forecast / 12
  ) STORED COMMENT 'Average monthly revenue',

  -- Forecast metadata
  `base_demand_used` DECIMAL(10,2) NULL COMMENT 'Base monthly demand before adjustments',
  `seasonal_pattern_applied` VARCHAR(20) NULL COMMENT 'Seasonal pattern type applied',
  `growth_rate_applied` DECIMAL(5,2) DEFAULT 0.00 COMMENT 'Growth rate used in forecast',
  `confidence_score` DECIMAL(3,2) DEFAULT 0.00 COMMENT 'Forecast confidence (0-1 scale)',
  `method_used` VARCHAR(50) NULL COMMENT 'Forecasting method based on ABC/XYZ',
  `manual_override` BOOLEAN DEFAULT FALSE COMMENT 'Whether user manually adjusted',
  `override_reason` TEXT NULL COMMENT 'Reason for manual adjustment',

  FOREIGN KEY (`forecast_run_id`) REFERENCES `forecast_runs`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`sku_id`) REFERENCES `skus`(`sku_id`) ON DELETE CASCADE,
  INDEX `idx_forecast_sku` (`forecast_run_id`, `sku_id`, `warehouse`),
  INDEX `idx_warehouse` (`warehouse`),
  INDEX `idx_confidence` (`confidence_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='Detailed monthly forecasts for each SKU and warehouse';

-- Table structure for forecast_adjustments
-- Logs manual adjustments made to forecasts
CREATE TABLE IF NOT EXISTS `forecast_adjustments` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `forecast_run_id` INT NOT NULL COMMENT 'Links to forecast_runs table',
  `sku_id` VARCHAR(50) NOT NULL COMMENT 'Links to skus table',
  `warehouse` ENUM('burnaby', 'kentucky', 'combined') NOT NULL COMMENT 'Warehouse location',
  `adjustment_type` ENUM('manual', 'event', 'promotion', 'phase_out') NOT NULL COMMENT 'Type of adjustment',
  `month_affected` INT NULL COMMENT 'Month number (1-12) if single month affected',
  `original_value` DECIMAL(10,2) NULL COMMENT 'Original forecasted value',
  `adjusted_value` DECIMAL(10,2) NULL COMMENT 'New adjusted value',
  `adjustment_reason` TEXT NULL COMMENT 'User explanation for adjustment',
  `adjusted_by` VARCHAR(100) NOT NULL COMMENT 'User who made the adjustment',
  `adjusted_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When adjustment was made',
  FOREIGN KEY (`forecast_run_id`) REFERENCES `forecast_runs`(`id`) ON DELETE CASCADE,
  FOREIGN KEY (`sku_id`) REFERENCES `skus`(`sku_id`) ON DELETE CASCADE,
  INDEX `idx_adjustment_run` (`forecast_run_id`),
  INDEX `idx_adjustment_sku` (`sku_id`),
  INDEX `idx_adjustment_type` (`adjustment_type`),
  INDEX `idx_adjusted_at` (`adjusted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
COMMENT='Log of manual forecast adjustments';

-- ================================================
-- Verification Queries
-- ================================================
-- Run these queries after migration to verify success:
--
-- 1. Check tables were created:
-- SHOW TABLES LIKE 'forecast%';
--
-- 2. Verify table structure:
-- DESCRIBE forecast_runs;
-- DESCRIBE forecast_details;
-- DESCRIBE forecast_adjustments;
--
-- 3. Check indexes:
-- SHOW INDEX FROM forecast_runs;
-- SHOW INDEX FROM forecast_details;
-- SHOW INDEX FROM forecast_adjustments;
--
-- 4. Test generated columns with sample data:
-- INSERT INTO forecast_runs (forecast_name, forecast_date)
-- VALUES ('Test Forecast', CURDATE());
--
-- INSERT INTO forecast_details (forecast_run_id, sku_id, warehouse,
--   month_1_qty, month_2_qty, month_3_qty, month_4_qty, month_5_qty, month_6_qty,
--   month_7_qty, month_8_qty, month_9_qty, month_10_qty, month_11_qty, month_12_qty)
-- SELECT 1, sku_id, 'kentucky', 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210
-- FROM skus LIMIT 1;
--
-- SELECT sku_id, total_qty_forecast, avg_monthly_qty
-- FROM forecast_details WHERE forecast_run_id = 1;
-- ================================================
