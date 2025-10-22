-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Generation Time: Oct 21, 2025 at 04:48 AM
-- Server version: 10.4.32-MariaDB
-- PHP Version: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `warehouse_transfer`
--

-- --------------------------------------------------------

--
-- Table structure for table `cache_refresh_log`
--

CREATE TABLE `cache_refresh_log` (
  `id` int(11) NOT NULL,
  `refresh_type` enum('full','partial','sku_specific') NOT NULL,
  `started_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `completed_at` timestamp NULL DEFAULT NULL,
  `duration_seconds` decimal(8,2) DEFAULT NULL,
  `total_skus` int(11) DEFAULT 0,
  `processed_skus` int(11) DEFAULT 0,
  `successful_calculations` int(11) DEFAULT 0,
  `failed_calculations` int(11) DEFAULT 0,
  `error_count` int(11) DEFAULT 0,
  `trigger_reason` varchar(255) DEFAULT NULL,
  `triggered_by` varchar(100) DEFAULT NULL,
  `status` enum('running','completed','failed','cancelled') DEFAULT 'running',
  `error_message` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `demand_calculation_config`
--

CREATE TABLE `demand_calculation_config` (
  `config_key` varchar(50) NOT NULL,
  `config_value` varchar(200) NOT NULL,
  `data_type` enum('string','integer','decimal','boolean') NOT NULL,
  `description` text NOT NULL,
  `default_value` varchar(200) NOT NULL,
  `min_value` varchar(50) DEFAULT NULL,
  `max_value` varchar(50) DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `updated_by` varchar(50) DEFAULT 'system'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Configuration settings for demand calculation algorithms';

-- --------------------------------------------------------

--
-- Table structure for table `forecast_accuracy`
--

CREATE TABLE `forecast_accuracy` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sku_id` varchar(50) NOT NULL,
  `warehouse` enum('burnaby','kentucky','combined') NOT NULL DEFAULT 'combined' COMMENT 'Warehouse for this forecast (burnaby, kentucky, or combined)',
  `forecast_date` date NOT NULL COMMENT 'Date when forecast was made',
  `forecast_period_start` date NOT NULL COMMENT 'Start of forecasted period',
  `forecast_period_end` date NOT NULL COMMENT 'End of forecasted period',
  `predicted_demand` decimal(10,2) NOT NULL COMMENT 'Predicted demand for the period',
  `actual_demand` decimal(10,2) DEFAULT NULL COMMENT 'Actual demand observed (filled later)',
  `absolute_error` decimal(10,2) DEFAULT NULL COMMENT 'ABS(actual - predicted)',
  `percentage_error` decimal(5,2) DEFAULT NULL COMMENT '(actual - predicted) / actual * 100',
  `absolute_percentage_error` decimal(5,2) DEFAULT NULL COMMENT 'ABS(percentage_error)',
  `forecast_method` varchar(50) NOT NULL COMMENT 'Method used: weighted_avg, seasonal_adj, etc.',
  `abc_class` char(1) DEFAULT NULL COMMENT 'ABC class at time of forecast',
  `xyz_class` char(1) DEFAULT NULL COMMENT 'XYZ class at time of forecast',
  `seasonal_pattern` varchar(20) DEFAULT NULL COMMENT 'Seasonal pattern at time of forecast',
  `is_actual_recorded` tinyint(1) DEFAULT 0 COMMENT 'Whether actual demand has been recorded',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `stockout_affected` tinyint(1) DEFAULT 0 COMMENT 'V8.0: TRUE if stockout occurred during forecast period, causing under-sales',
  `volatility_at_forecast` decimal(5,2) DEFAULT NULL COMMENT 'V8.0: coefficient_variation from sku_demand_stats at time of forecast',
  `data_quality_score` decimal(3,2) DEFAULT NULL COMMENT 'V8.0: Data quality score (0.00-1.00) at time of forecast',
  `seasonal_confidence_at_forecast` decimal(5,4) DEFAULT NULL COMMENT 'V8.0: confidence_level from seasonal_factors at time of forecast',
  `learning_applied` tinyint(1) DEFAULT 0 COMMENT 'V8.0: TRUE if learning adjustment was applied to this SKU',
  `learning_applied_date` timestamp NULL DEFAULT NULL COMMENT 'V8.0: When learning adjustment was applied',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_forecast` (`sku_id`,`warehouse`,`forecast_period_start`,`forecast_period_end`),
  KEY `idx_forecast_date` (`forecast_date`),
  KEY `idx_warehouse_period` (`warehouse`,`forecast_period_start`,`is_actual_recorded`),
  KEY `idx_sku_period` (`sku_id`,`forecast_period_start`),
  KEY `idx_accuracy_metrics` (`is_actual_recorded`,`absolute_percentage_error`),
  KEY `idx_abc_xyz_accuracy` (`abc_class`,`xyz_class`,`absolute_percentage_error`),
  KEY `idx_learning_status` (`learning_applied`,`forecast_date`),
  KEY `idx_period_recorded` (`forecast_period_start`,`is_actual_recorded`),
  KEY `idx_sku_recorded` (`sku_id`,`is_actual_recorded`,`forecast_period_start`),
  CONSTRAINT `forecast_accuracy_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Track forecast accuracy over time for continuous improvement. V8.0: Enhanced with context fields and learning system support';

-- --------------------------------------------------------

--
-- Table structure for table `forecast_adjustments`
--

CREATE TABLE `forecast_adjustments` (
  `id` int(11) NOT NULL,
  `forecast_run_id` int(11) NOT NULL COMMENT 'Links to forecast_runs table',
  `sku_id` varchar(50) NOT NULL COMMENT 'Links to skus table',
  `warehouse` enum('burnaby','kentucky','combined') NOT NULL COMMENT 'Warehouse location',
  `adjustment_type` enum('manual','event','promotion','phase_out') NOT NULL COMMENT 'Type of adjustment',
  `month_affected` int(11) DEFAULT NULL COMMENT 'Month number (1-12) if single month affected',
  `original_value` decimal(10,2) DEFAULT NULL COMMENT 'Original forecasted value',
  `adjusted_value` decimal(10,2) DEFAULT NULL COMMENT 'New adjusted value',
  `adjustment_reason` text DEFAULT NULL COMMENT 'User explanation for adjustment',
  `adjusted_by` varchar(100) NOT NULL COMMENT 'User who made the adjustment',
  `adjusted_at` timestamp NOT NULL DEFAULT current_timestamp() COMMENT 'When adjustment was made'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Log of manual forecast adjustments';

-- --------------------------------------------------------

--
-- Table structure for table `forecast_learning_adjustments`
-- V8.0: System-learned adjustments separate from manual forecast_adjustments
--

CREATE TABLE `forecast_learning_adjustments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sku_id` varchar(50) NOT NULL,
  `adjustment_type` enum('growth_rate','seasonal_factor','method_switch','volatility_adjustment','category_default') NOT NULL COMMENT 'Type of adjustment',
  `original_value` decimal(10,4) DEFAULT NULL COMMENT 'Value before adjustment',
  `adjusted_value` decimal(10,4) NOT NULL COMMENT 'Recommended value after adjustment',
  `adjustment_magnitude` decimal(10,4) NOT NULL COMMENT 'Size of adjustment for tracking',
  `learning_reason` text NOT NULL COMMENT 'Why this adjustment is recommended',
  `confidence_score` decimal(3,2) NOT NULL COMMENT 'Confidence in this adjustment (0.00-1.00)',
  `mape_before` decimal(5,2) DEFAULT NULL COMMENT 'MAPE before adjustment',
  `mape_expected` decimal(5,2) DEFAULT NULL COMMENT 'Expected MAPE after adjustment',
  `applied` tinyint(1) DEFAULT 0 COMMENT 'TRUE when adjustment is applied',
  `applied_date` timestamp NULL DEFAULT NULL COMMENT 'When adjustment was applied',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp() COMMENT 'When learning system generated this',
  PRIMARY KEY (`id`),
  KEY `idx_applied` (`applied`,`created_at`),
  KEY `idx_sku_type` (`sku_id`,`adjustment_type`),
  KEY `idx_confidence` (`confidence_score`,`created_at`),
  CONSTRAINT `forecast_learning_adjustments_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='V8.0: System-learned adjustments to forecast parameters based on accuracy analysis';

-- --------------------------------------------------------

--
-- Table structure for table `forecast_details`
--

CREATE TABLE `forecast_details` (
  `id` int(11) NOT NULL,
  `forecast_run_id` int(11) NOT NULL COMMENT 'Links to forecast_runs table',
  `sku_id` varchar(50) NOT NULL COMMENT 'Links to skus table',
  `warehouse` enum('burnaby','kentucky','combined') NOT NULL COMMENT 'Warehouse location',
  `month_1_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 1',
  `month_2_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 2',
  `month_3_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 3',
  `month_4_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 4',
  `month_5_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 5',
  `month_6_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 6',
  `month_7_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 7',
  `month_8_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 8',
  `month_9_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 9',
  `month_10_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 10',
  `month_11_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 11',
  `month_12_qty` int(11) DEFAULT 0 COMMENT 'Forecast quantity for month 12',
  `month_1_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 1',
  `month_2_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 2',
  `month_3_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 3',
  `month_4_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 4',
  `month_5_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 5',
  `month_6_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 6',
  `month_7_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 7',
  `month_8_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 8',
  `month_9_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 9',
  `month_10_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 10',
  `month_11_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 11',
  `month_12_rev` decimal(12,2) DEFAULT 0.00 COMMENT 'Forecast revenue for month 12',
  `total_qty_forecast` int(11) GENERATED ALWAYS AS (`month_1_qty` + `month_2_qty` + `month_3_qty` + `month_4_qty` + `month_5_qty` + `month_6_qty` + `month_7_qty` + `month_8_qty` + `month_9_qty` + `month_10_qty` + `month_11_qty` + `month_12_qty`) STORED COMMENT 'Total forecasted quantity for 12 months',
  `total_rev_forecast` decimal(14,2) GENERATED ALWAYS AS (`month_1_rev` + `month_2_rev` + `month_3_rev` + `month_4_rev` + `month_5_rev` + `month_6_rev` + `month_7_rev` + `month_8_rev` + `month_9_rev` + `month_10_rev` + `month_11_rev` + `month_12_rev`) STORED COMMENT 'Total forecasted revenue for 12 months',
  `avg_monthly_qty` decimal(10,2) GENERATED ALWAYS AS (`total_qty_forecast` / 12) STORED COMMENT 'Average monthly quantity',
  `avg_monthly_rev` decimal(12,2) GENERATED ALWAYS AS (`total_rev_forecast` / 12) STORED COMMENT 'Average monthly revenue',
  `base_demand_used` decimal(10,2) DEFAULT NULL COMMENT 'Base monthly demand before adjustments',
  `seasonal_pattern_applied` varchar(20) DEFAULT NULL COMMENT 'Seasonal pattern type applied',
  `growth_rate_applied` decimal(5,2) DEFAULT 0.00 COMMENT 'Growth rate used in forecast',
  `growth_rate_source` enum('manual_override','default','new_sku_methodology','proven_demand_stockout','sku_trend','sku_trend_X','sku_trend_Y','sku_trend_Z','sku_trend_X_seasonal','sku_trend_Y_seasonal','sku_trend_Z_seasonal','growth_status','growth_status_X','growth_status_Y','growth_status_Z','growth_status_X_seasonal','growth_status_Y_seasonal','growth_status_Z_seasonal','category_trend','category_trend_X','category_trend_Y','category_trend_Z','category_trend_X_seasonal','category_trend_Y_seasonal','category_trend_Z_seasonal') DEFAULT 'default',
  `confidence_score` decimal(3,2) DEFAULT 0.00 COMMENT 'Forecast confidence (0-1 scale)',
  `method_used` varchar(50) DEFAULT NULL COMMENT 'Forecasting method based on ABC/XYZ',
  `manual_override` tinyint(1) DEFAULT 0 COMMENT 'Whether user manually adjusted',
  `override_reason` text DEFAULT NULL COMMENT 'Reason for manual adjustment'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Detailed monthly forecasts for each SKU and warehouse';

-- --------------------------------------------------------

--
-- Table structure for table `forecast_runs`
--

CREATE TABLE `forecast_runs` (
  `id` int(11) NOT NULL,
  `forecast_name` varchar(100) NOT NULL COMMENT 'User-friendly name for this forecast',
  `forecast_date` date NOT NULL COMMENT 'Date when forecast was generated',
  `forecast_type` enum('monthly','quarterly','annual') DEFAULT 'monthly' COMMENT 'Forecast granularity',
  `warehouse` enum('burnaby','kentucky','combined') DEFAULT 'combined',
  `status` enum('pending','queued','running','completed','failed','cancelled') DEFAULT 'pending' COMMENT 'Current status of forecast generation',
  `archived` tinyint(1) DEFAULT 0 COMMENT 'Whether forecast is archived (hidden from main view)',
  `queue_position` int(11) DEFAULT NULL COMMENT 'Position in forecast generation queue (NULL if not queued)',
  `growth_assumption` decimal(5,2) DEFAULT 0.00 COMMENT 'Manual growth rate override (percentage)',
  `created_by` varchar(100) DEFAULT 'system' COMMENT 'User who created this forecast',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp() COMMENT 'Timestamp of forecast creation',
  `queued_at` timestamp NULL DEFAULT NULL COMMENT 'Timestamp when forecast was added to queue',
  `started_at` timestamp NULL DEFAULT NULL COMMENT 'When forecast generation started',
  `completed_at` timestamp NULL DEFAULT NULL COMMENT 'When forecast generation completed',
  `approved_by` varchar(100) DEFAULT NULL COMMENT 'User who approved this forecast',
  `approved_at` timestamp NULL DEFAULT NULL COMMENT 'When forecast was approved',
  `notes` text DEFAULT NULL COMMENT 'User notes about this forecast',
  `total_skus` int(11) DEFAULT 0 COMMENT 'Total SKUs to process',
  `processed_skus` int(11) DEFAULT 0 COMMENT 'SKUs processed so far',
  `failed_skus` int(11) DEFAULT 0 COMMENT 'SKUs that failed to process',
  `duration_seconds` decimal(8,2) DEFAULT NULL COMMENT 'Total processing time in seconds',
  `error_message` text DEFAULT NULL COMMENT 'Error details if status is failed'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Master table tracking forecast generation runs';

-- --------------------------------------------------------

--
-- Table structure for table `inventory_current`
--

CREATE TABLE `inventory_current` (
  `sku_id` varchar(50) NOT NULL,
  `burnaby_qty` int(11) DEFAULT 0,
  `kentucky_qty` int(11) DEFAULT 0,
  `last_updated` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `monthly_sales`
--

CREATE TABLE `monthly_sales` (
  `year_month` varchar(7) NOT NULL,
  `sku_id` varchar(50) NOT NULL,
  `burnaby_sales` int(11) DEFAULT 0,
  `kentucky_sales` int(11) DEFAULT 0,
  `burnaby_stockout_days` int(11) DEFAULT 0,
  `kentucky_stockout_days` int(11) DEFAULT 0,
  `corrected_demand_burnaby` decimal(10,2) DEFAULT 0.00,
  `corrected_demand_kentucky` decimal(10,2) DEFAULT 0.00,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `burnaby_revenue` decimal(12,2) DEFAULT 0.00 COMMENT 'Actual revenue from Burnaby warehouse sales',
  `kentucky_revenue` decimal(12,2) DEFAULT 0.00 COMMENT 'Actual revenue from Kentucky warehouse sales',
  `total_revenue` decimal(12,2) GENERATED ALWAYS AS (`burnaby_revenue` + `kentucky_revenue`) STORED COMMENT 'Total revenue across both warehouses',
  `burnaby_avg_revenue` decimal(10,2) GENERATED ALWAYS AS (case when `burnaby_sales` > 0 then round(`burnaby_revenue` / `burnaby_sales`,2) else 0.00 end) STORED COMMENT 'Average revenue per unit for Burnaby sales',
  `kentucky_avg_revenue` decimal(10,2) GENERATED ALWAYS AS (case when `kentucky_sales` > 0 then round(`kentucky_revenue` / `kentucky_sales`,2) else 0.00 end) STORED COMMENT 'Average revenue per unit for Kentucky sales'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `pending_inventory`
--

CREATE TABLE `pending_inventory` (
  `id` int(11) NOT NULL,
  `sku_id` varchar(50) NOT NULL,
  `quantity` int(11) NOT NULL,
  `destination` enum('burnaby','kentucky') NOT NULL,
  `order_date` date NOT NULL,
  `expected_arrival` date DEFAULT NULL COMMENT 'Expected arrival date (NULL = calculate from order_date + lead_time_days)',
  `actual_arrival` date DEFAULT NULL,
  `order_type` enum('supplier','transfer') DEFAULT 'supplier',
  `status` enum('ordered','shipped','received','cancelled') DEFAULT 'ordered',
  `notes` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `lead_time_days` int(11) DEFAULT 120 COMMENT 'Lead time in days (default 4 months)',
  `is_estimated` tinyint(1) DEFAULT 1 COMMENT 'Whether the arrival date is estimated'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `seasonal_factors`
--

CREATE TABLE `seasonal_factors` (
  `sku_id` varchar(50) NOT NULL,
  `warehouse` enum('kentucky','burnaby') NOT NULL DEFAULT 'kentucky',
  `month_number` tinyint(4) NOT NULL CHECK (`month_number` between 1 and 12),
  `seasonal_factor` decimal(6,4) NOT NULL DEFAULT 1.0000,
  `confidence_level` decimal(5,4) NOT NULL DEFAULT 0.0000,
  `data_points_used` int(11) NOT NULL DEFAULT 0,
  `pattern_type` varchar(20) DEFAULT 'unknown',
  `pattern_strength` decimal(5,4) DEFAULT 0.0000,
  `last_calculated` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Data-driven seasonal factors calculated from historical sales patterns';

-- --------------------------------------------------------

--
-- Table structure for table `seasonal_patterns`
--

CREATE TABLE `seasonal_patterns` (
  `id` int(11) NOT NULL,
  `sku_id` varchar(50) NOT NULL,
  `month_number` int(11) NOT NULL,
  `month_name` varchar(20) NOT NULL,
  `seasonal_index` decimal(10,4) DEFAULT 0.0000,
  `avg_monthly_sales` decimal(15,4) DEFAULT 0.0000,
  `data_points` int(11) DEFAULT 0,
  `last_calculated` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `seasonal_patterns_summary`
--

CREATE TABLE `seasonal_patterns_summary` (
  `sku_id` varchar(50) NOT NULL,
  `warehouse` enum('kentucky','burnaby') NOT NULL DEFAULT 'kentucky',
  `pattern_type` varchar(20) NOT NULL DEFAULT 'unknown',
  `pattern_strength` decimal(5,4) NOT NULL DEFAULT 0.0000,
  `overall_confidence` decimal(5,4) NOT NULL DEFAULT 0.0000,
  `statistical_significance` tinyint(1) NOT NULL DEFAULT 0,
  `f_statistic` decimal(10,4) DEFAULT NULL,
  `p_value` decimal(10,8) DEFAULT NULL,
  `years_analyzed` tinyint(4) NOT NULL DEFAULT 0,
  `months_of_data` int(11) NOT NULL DEFAULT 0,
  `date_range_start` varchar(7) DEFAULT NULL,
  `date_range_end` varchar(7) DEFAULT NULL,
  `yearly_average` decimal(10,2) DEFAULT 0.00,
  `peak_months` varchar(50) DEFAULT NULL,
  `low_months` varchar(50) DEFAULT NULL,
  `last_analyzed` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Summary of seasonal pattern analysis for each SKU and warehouse';

-- --------------------------------------------------------

--
-- Table structure for table `skus`
--

CREATE TABLE `skus` (
  `sku_id` varchar(50) NOT NULL,
  `description` varchar(255) NOT NULL,
  `supplier` varchar(100) DEFAULT NULL,
  `status` enum('Active','Death Row','Discontinued') DEFAULT 'Active',
  `cost_per_unit` decimal(10,2) DEFAULT NULL,
  `transfer_multiple` int(11) DEFAULT 50,
  `abc_code` char(1) DEFAULT 'C',
  `xyz_code` char(1) DEFAULT 'Z',
  `category` varchar(50) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `seasonal_pattern` varchar(20) DEFAULT 'unknown' COMMENT 'Auto-detected seasonal pattern: spring_summer, fall_winter, holiday, year_round, unknown',
  `growth_status` enum('normal','viral','declining','unknown') DEFAULT 'unknown' COMMENT 'Growth pattern: viral (2x+ growth), declining (<50% of previous), normal, unknown',
  `last_stockout_date` date DEFAULT NULL COMMENT 'Most recent stockout date for quick dashboard display',
  `peak_months` varchar(50) DEFAULT NULL COMMENT 'Comma-separated list of peak sales months (1-12)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `sku_demand_stats`
--

CREATE TABLE `sku_demand_stats` (
  `sku_id` varchar(50) NOT NULL,
  `warehouse` varchar(20) NOT NULL DEFAULT 'kentucky',
  `demand_3mo_weighted` decimal(10,2) DEFAULT 0.00 COMMENT '3-month weighted average demand (weights: 0.5, 0.3, 0.2)',
  `demand_6mo_weighted` decimal(10,2) DEFAULT 0.00 COMMENT '6-month weighted average demand with exponential decay',
  `demand_3mo_simple` decimal(10,2) DEFAULT 0.00 COMMENT '3-month simple moving average',
  `demand_6mo_simple` decimal(10,2) DEFAULT 0.00 COMMENT '6-month simple moving average',
  `demand_std_dev` decimal(10,2) DEFAULT 0.00 COMMENT 'Standard deviation of monthly demand',
  `coefficient_variation` decimal(5,2) DEFAULT 0.00 COMMENT 'CV = std_dev / mean_demand',
  `volatility_class` enum('low','medium','high') DEFAULT 'medium' COMMENT 'Volatility classification based on CV',
  `sample_size_months` int(11) DEFAULT 0 COMMENT 'Number of months used in calculations',
  `data_quality_score` decimal(3,2) DEFAULT 0.00 COMMENT 'Quality score 0-1 based on data completeness',
  `has_seasonal_pattern` tinyint(1) DEFAULT 0 COMMENT 'Whether seasonal pattern is detected',
  `last_calculated` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `calculation_method` varchar(50) DEFAULT 'weighted_average' COMMENT 'Method used for demand calculation',
  `cache_valid` tinyint(1) DEFAULT 0,
  `invalidated_at` timestamp NULL DEFAULT NULL,
  `invalidation_reason` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='Store calculated demand statistics for enhanced transfer recommendations';

-- --------------------------------------------------------

--
-- Table structure for table `stockout_dates`
--

CREATE TABLE `stockout_dates` (
  `sku_id` varchar(50) NOT NULL,
  `warehouse` enum('burnaby','kentucky') NOT NULL,
  `stockout_date` date NOT NULL,
  `is_resolved` tinyint(1) DEFAULT 0,
  `resolved_date` date DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `stockout_patterns`
--

CREATE TABLE `stockout_patterns` (
  `id` int(11) NOT NULL,
  `sku_id` varchar(50) NOT NULL,
  `pattern_type` enum('seasonal','day_of_week','monthly','chronic') NOT NULL,
  `pattern_value` varchar(100) NOT NULL COMMENT 'Pattern details (e.g., "april,may,june" or "monday,friday")',
  `frequency_score` decimal(5,2) DEFAULT 0.00 COMMENT 'How often this pattern occurs (0-100)',
  `last_detected` date NOT NULL,
  `confidence_level` enum('low','medium','high') DEFAULT 'medium',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `stockout_updates_log`
--

CREATE TABLE `stockout_updates_log` (
  `id` int(11) NOT NULL,
  `update_batch_id` varchar(36) NOT NULL COMMENT 'UUID for grouping bulk updates',
  `sku_id` varchar(50) NOT NULL,
  `warehouse` enum('burnaby','kentucky') NOT NULL,
  `action` enum('mark_out','mark_in') NOT NULL,
  `previous_status` enum('in_stock','out_of_stock','unknown') DEFAULT 'unknown',
  `new_status` enum('in_stock','out_of_stock') NOT NULL,
  `stockout_date` date NOT NULL,
  `resolution_date` date DEFAULT NULL,
  `update_source` enum('quick_ui','csv_import','api_direct','system_auto') DEFAULT 'quick_ui',
  `user_notes` text DEFAULT NULL,
  `created_by` varchar(100) DEFAULT 'system',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `suppliers`
--

CREATE TABLE `suppliers` (
  `id` int(11) NOT NULL,
  `supplier_code` varchar(50) DEFAULT NULL,
  `display_name` varchar(100) NOT NULL,
  `legal_name` varchar(100) DEFAULT NULL,
  `normalized_name` varchar(100) NOT NULL,
  `contact_email` varchar(255) DEFAULT NULL,
  `contact_phone` varchar(50) DEFAULT NULL,
  `address_line1` varchar(255) DEFAULT NULL,
  `address_line2` varchar(255) DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `state_province` varchar(100) DEFAULT NULL,
  `postal_code` varchar(20) DEFAULT NULL,
  `country` varchar(100) DEFAULT 'Canada',
  `default_lead_time` int(11) DEFAULT 30,
  `is_active` tinyint(1) DEFAULT 1,
  `notes` text DEFAULT NULL,
  `created_by` varchar(100) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_by` varchar(100) DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Master supplier table with normalized names for consistent matching';

-- --------------------------------------------------------

--
-- Table structure for table `supplier_aliases`
--

CREATE TABLE `supplier_aliases` (
  `id` int(11) NOT NULL,
  `supplier_id` int(11) NOT NULL,
  `alias_name` varchar(100) NOT NULL,
  `normalized_alias` varchar(100) NOT NULL,
  `usage_count` int(11) DEFAULT 1,
  `confidence_score` decimal(5,2) DEFAULT 100.00,
  `is_primary` tinyint(1) DEFAULT 0,
  `created_by` varchar(100) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_by` varchar(100) DEFAULT NULL,
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Supplier name aliases for fuzzy matching and name variations';

-- --------------------------------------------------------

--
-- Table structure for table `supplier_lead_times`
--

CREATE TABLE `supplier_lead_times` (
  `id` int(11) NOT NULL,
  `supplier` varchar(100) NOT NULL,
  `lead_time_days` int(11) NOT NULL,
  `destination` enum('burnaby','kentucky') DEFAULT NULL,
  `notes` text DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `avg_lead_time` decimal(10,2) DEFAULT NULL,
  `median_lead_time` decimal(10,2) DEFAULT NULL,
  `p95_lead_time` decimal(10,2) DEFAULT NULL,
  `min_lead_time` int(11) DEFAULT NULL,
  `max_lead_time` int(11) DEFAULT NULL,
  `std_dev_lead_time` decimal(10,2) DEFAULT NULL,
  `coefficient_variation` decimal(10,4) DEFAULT NULL,
  `reliability_score` int(11) DEFAULT NULL,
  `shipment_count` int(11) DEFAULT 0,
  `calculation_period` varchar(20) DEFAULT '12_months',
  `last_calculated` timestamp NULL DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `supplier_shipments`
--

CREATE TABLE `supplier_shipments` (
  `id` int(11) NOT NULL,
  `po_number` varchar(50) NOT NULL,
  `supplier` varchar(100) NOT NULL,
  `order_date` date NOT NULL,
  `received_date` date NOT NULL,
  `destination` enum('burnaby','kentucky') NOT NULL,
  `actual_lead_time` int(11) GENERATED ALWAYS AS (to_days(`received_date`) - to_days(`order_date`)) STORED,
  `was_partial` tinyint(1) DEFAULT 0,
  `notes` text DEFAULT NULL,
  `uploaded_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `uploaded_by` varchar(100) DEFAULT 'system'
) ;

-- --------------------------------------------------------

--
-- Table structure for table `system_config`
--

CREATE TABLE `system_config` (
  `config_key` varchar(100) NOT NULL,
  `config_value` text NOT NULL,
  `data_type` enum('string','int','float','bool','json') DEFAULT 'string',
  `category` varchar(50) DEFAULT 'general',
  `description` text DEFAULT NULL,
  `is_system` tinyint(1) DEFAULT 0,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `transfer_confirmations`
--

CREATE TABLE `transfer_confirmations` (
  `sku_id` varchar(50) NOT NULL,
  `confirmed_qty` int(11) NOT NULL,
  `original_suggested_qty` int(11) DEFAULT NULL,
  `confirmed_by` varchar(100) DEFAULT NULL,
  `confirmed_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `notes` text DEFAULT NULL,
  `variance_percent` decimal(5,2) DEFAULT NULL,
  `ca_order_qty` int(11) DEFAULT NULL COMMENT 'Manual order quantity for CA warehouse',
  `ky_order_qty` int(11) DEFAULT NULL COMMENT 'Manual order quantity for KY warehouse'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Table structure for table `transfer_history`
--

CREATE TABLE `transfer_history` (
  `id` int(11) NOT NULL,
  `sku_id` varchar(50) NOT NULL,
  `recommended_qty` int(11) NOT NULL,
  `actual_qty` int(11) DEFAULT 0,
  `recommendation_date` date NOT NULL,
  `transfer_date` date DEFAULT NULL,
  `burnaby_qty_before` int(11) DEFAULT NULL,
  `kentucky_qty_before` int(11) DEFAULT NULL,
  `reason` varchar(255) DEFAULT NULL,
  `corrected_demand` decimal(10,2) DEFAULT NULL,
  `coverage_days` int(11) DEFAULT NULL,
  `abc_class` char(1) DEFAULT NULL,
  `xyz_class` char(1) DEFAULT NULL,
  `created_by` varchar(50) DEFAULT 'system',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_abc_xyz_matrix`
-- (See below for the actual view)
--
CREATE TABLE `v_abc_xyz_matrix` (
`abc_code` char(1)
,`xyz_code` char(1)
,`classification` varchar(2)
,`sku_count` bigint(21)
,`total_revenue` decimal(57,2)
,`avg_revenue_per_sku` decimal(39,6)
,`total_units` decimal(55,0)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_all_skus_performance`
-- (See below for the actual view)
--
CREATE TABLE `v_all_skus_performance` (
`sku_id` varchar(50)
,`description` varchar(255)
,`category` varchar(50)
,`supplier` varchar(100)
,`abc_code` char(1)
,`xyz_code` char(1)
,`status` enum('Active','Death Row','Discontinued')
,`total_revenue_12m` decimal(35,2)
,`total_units_12m` decimal(33,0)
,`avg_monthly_revenue` decimal(17,6)
,`avg_monthly_units` decimal(15,4)
,`avg_selling_price` decimal(21,10)
,`months_with_sales` bigint(21)
,`stockout_days_total` decimal(33,0)
,`estimated_lost_sales` decimal(37,2)
,`growth_rate_6m` decimal(41,4)
,`current_ky_qty` int(11)
,`current_ca_qty` int(11)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_current_seasonal_factors`
-- (See below for the actual view)
--
CREATE TABLE `v_current_seasonal_factors` (
`sku_id` varchar(50)
,`warehouse` enum('kentucky','burnaby')
,`current_month_factor` decimal(6,4)
,`current_month_confidence` decimal(5,4)
,`pattern_type` varchar(20)
,`pattern_strength` decimal(5,4)
,`overall_confidence` decimal(5,4)
,`statistical_significance` tinyint(1)
,`current_month` int(2)
,`current_month_name` varchar(9)
,`last_calculated` timestamp
,`reliability_rating` varchar(10)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_current_stockouts_enhanced`
-- (See below for the actual view)
--
CREATE TABLE `v_current_stockouts_enhanced` (
`sku_id` varchar(50)
,`description` varchar(255)
,`category` varchar(50)
,`seasonal_pattern` varchar(20)
,`growth_status` enum('normal','viral','declining','unknown')
,`warehouse` enum('burnaby','kentucky')
,`stockout_date` date
,`days_out` int(7)
,`burnaby_qty` int(11)
,`kentucky_qty` int(11)
,`urgency_level` varchar(8)
,`estimated_lost_sales` decimal(20,6)
,`cost_per_unit` decimal(10,2)
,`abc_code` char(1)
,`xyz_code` char(1)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_forecast_accuracy_summary`
-- (See below for the actual view)
--
CREATE TABLE `v_forecast_accuracy_summary` (
`abc_class` char(1)
,`total_forecasts` bigint(21)
,`completed_forecasts` bigint(21)
,`avg_mape` decimal(9,6)
,`mape_std_dev` double(16,6)
,`excellent_forecasts` bigint(21)
,`good_forecasts` bigint(21)
,`poor_forecasts` bigint(21)
,`latest_forecast_date` date
,`earliest_forecast_date` date
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_pending_orders_aggregated`
-- (See below for the actual view)
--
CREATE TABLE `v_pending_orders_aggregated` (
`sku_id` varchar(50)
,`destination` enum('burnaby','kentucky')
,`immediate_qty` decimal(34,1)
,`near_term_qty` decimal(34,1)
,`medium_term_qty` decimal(34,1)
,`long_term_qty` decimal(34,1)
,`total_weighted` decimal(39,2)
,`earliest_arrival` date
,`latest_arrival` date
,`shipment_count` bigint(21)
,`total_raw_quantity` decimal(32,0)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_pending_orders_analysis`
-- (See below for the actual view)
--
CREATE TABLE `v_pending_orders_analysis` (
`id` int(11)
,`sku_id` varchar(50)
,`description` varchar(255)
,`supplier` varchar(100)
,`quantity` int(11)
,`destination` enum('burnaby','kentucky')
,`order_date` date
,`expected_arrival` date
,`lead_time_days` int(11)
,`is_estimated` tinyint(1)
,`order_type` enum('supplier','transfer')
,`status` enum('ordered','shipped','received','cancelled')
,`notes` text
,`calculated_arrival_date` date
,`days_until_arrival` int(7)
,`is_overdue` int(1)
,`priority_score` int(8)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_pending_quantities`
-- (See below for the actual view)
--
CREATE TABLE `v_pending_quantities` (
`sku_id` varchar(50)
,`burnaby_pending` decimal(32,0)
,`kentucky_pending` decimal(32,0)
,`total_pending` decimal(32,0)
,`supplier_orders` bigint(21)
,`transfer_orders` bigint(21)
,`earliest_arrival` date
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_revenue_analysis`
-- (See below for the actual view)
--
CREATE TABLE `v_revenue_analysis` (
`year_month` varchar(7)
,`sku_id` varchar(50)
,`description` varchar(255)
,`cost_per_unit` decimal(10,2)
,`burnaby_sales` int(11)
,`kentucky_sales` int(11)
,`burnaby_revenue` decimal(12,2)
,`kentucky_revenue` decimal(12,2)
,`total_revenue` decimal(12,2)
,`burnaby_avg_revenue` decimal(10,2)
,`kentucky_avg_revenue` decimal(10,2)
,`overall_avg_revenue` decimal(13,2)
,`burnaby_margin_percent` decimal(17,2)
,`kentucky_margin_percent` decimal(17,2)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_revenue_dashboard`
-- (See below for the actual view)
--
CREATE TABLE `v_revenue_dashboard` (
`current_year` int(4)
,`current_month` int(2)
,`revenue_mtd` decimal(34,2)
,`burnaby_revenue_mtd` decimal(34,2)
,`kentucky_revenue_mtd` decimal(34,2)
,`avg_revenue_per_unit_mtd` decimal(35,2)
,`revenue_prev_month` decimal(34,2)
,`revenue_ytd` decimal(34,2)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_sales_summary_12m`
-- (See below for the actual view)
--
CREATE TABLE `v_sales_summary_12m` (
`total_skus` bigint(21)
,`total_units` decimal(33,0)
,`total_revenue` decimal(35,2)
,`avg_monthly_revenue` decimal(17,6)
,`avg_monthly_sales` decimal(15,4)
,`total_stockout_days_ky` decimal(32,0)
,`total_stockout_days_ca` decimal(32,0)
,`estimated_lost_sales_ky` decimal(35,2)
,`estimated_lost_sales_ca` decimal(35,2)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_sku_demand_analysis`
-- (See below for the actual view)
--
CREATE TABLE `v_sku_demand_analysis` (
`sku_id` varchar(50)
,`description` varchar(255)
,`category` varchar(50)
,`abc_code` char(1)
,`xyz_code` char(1)
,`status` enum('Active','Death Row','Discontinued')
,`kentucky_qty` int(11)
,`burnaby_qty` int(11)
,`last_month_sales` int(11)
,`kentucky_stockout_days` int(11)
,`corrected_demand_kentucky` decimal(10,2)
,`demand_3mo_weighted` decimal(10,2)
,`demand_6mo_weighted` decimal(10,2)
,`demand_std_dev` decimal(10,2)
,`coefficient_variation` decimal(5,2)
,`volatility_class` enum('low','medium','high')
,`sample_size_months` int(11)
,`data_quality_score` decimal(3,2)
,`stats_last_calculated` timestamp
,`months_coverage_3mo_avg` decimal(14,1)
,`stockout_risk_level` varchar(11)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_sku_performance_summary`
-- (See below for the actual view)
--
CREATE TABLE `v_sku_performance_summary` (
`sku_id` varchar(50)
,`description` varchar(255)
,`category` varchar(50)
,`supplier` varchar(100)
,`abc_code` char(1)
,`xyz_code` char(1)
,`status` enum('Active','Death Row','Discontinued')
,`total_revenue_12m` decimal(35,2)
,`total_units_12m` decimal(33,0)
,`avg_monthly_revenue` decimal(17,6)
,`avg_monthly_units` decimal(15,4)
,`avg_selling_price` decimal(21,10)
,`months_with_sales` bigint(21)
,`stockout_days_total` decimal(33,0)
,`estimated_lost_sales` decimal(37,2)
,`growth_rate_6m` decimal(41,4)
,`current_ky_qty` int(11)
,`current_ca_qty` int(11)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_stockout_impact`
-- (See below for the actual view)
--
CREATE TABLE `v_stockout_impact` (
`sku_id` varchar(50)
,`description` varchar(255)
,`abc_code` char(1)
,`xyz_code` char(1)
,`total_stockout_days` decimal(33,0)
,`actual_sales` decimal(33,0)
,`potential_sales` decimal(35,2)
,`estimated_lost_units` decimal(37,2)
,`estimated_lost_revenue` decimal(58,12)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_stockout_trends`
-- (See below for the actual view)
--
CREATE TABLE `v_stockout_trends` (
`sku_id` varchar(50)
,`description` varchar(255)
,`category` varchar(50)
,`seasonal_pattern` varchar(20)
,`total_stockout_events` bigint(21)
,`avg_stockout_duration` decimal(10,4)
,`last_stockout_date` date
,`recent_stockouts` bigint(21)
,`stockout_months` mediumtext
,`stockout_days_of_week` mediumtext
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `v_test_simple`
-- (See below for the actual view)
--
CREATE TABLE `v_test_simple` (
`total` bigint(21)
);

-- --------------------------------------------------------

--
-- Structure for view `v_abc_xyz_matrix`
--
DROP TABLE IF EXISTS `v_abc_xyz_matrix`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_abc_xyz_matrix`  AS SELECT `s`.`abc_code` AS `abc_code`, `s`.`xyz_code` AS `xyz_code`, concat(`s`.`abc_code`,`s`.`xyz_code`) AS `classification`, count(distinct `s`.`sku_id`) AS `sku_count`, sum(`revenue_data`.`total_revenue`) AS `total_revenue`, avg(`revenue_data`.`total_revenue`) AS `avg_revenue_per_sku`, sum(`revenue_data`.`total_units`) AS `total_units` FROM (`skus` `s` left join (select `monthly_sales`.`sku_id` AS `sku_id`,sum(coalesce(`monthly_sales`.`burnaby_revenue`,0) + coalesce(`monthly_sales`.`kentucky_revenue`,0)) AS `total_revenue`,sum(coalesce(`monthly_sales`.`burnaby_sales`,0) + coalesce(`monthly_sales`.`kentucky_sales`,0)) AS `total_units` from `monthly_sales` where `monthly_sales`.`year_month` >= date_format(curdate() - interval 12 month,'%Y-%m') group by `monthly_sales`.`sku_id`) `revenue_data` on(`s`.`sku_id` = `revenue_data`.`sku_id`)) WHERE `s`.`status` = 'Active' GROUP BY `s`.`abc_code`, `s`.`xyz_code` ORDER BY `s`.`abc_code` ASC, `s`.`xyz_code` ASC ;

-- --------------------------------------------------------

--
-- Structure for view `v_all_skus_performance`
--
DROP TABLE IF EXISTS `v_all_skus_performance`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_all_skus_performance`  AS SELECT `s`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`category` AS `category`, `s`.`supplier` AS `supplier`, `s`.`abc_code` AS `abc_code`, `s`.`xyz_code` AS `xyz_code`, `s`.`status` AS `status`, coalesce(`perf`.`total_revenue_12m`,0) AS `total_revenue_12m`, coalesce(`perf`.`total_units_12m`,0) AS `total_units_12m`, coalesce(`perf`.`avg_monthly_revenue`,0) AS `avg_monthly_revenue`, coalesce(`perf`.`avg_monthly_units`,0) AS `avg_monthly_units`, coalesce(`perf`.`avg_selling_price`,0) AS `avg_selling_price`, coalesce(`perf`.`months_with_sales`,0) AS `months_with_sales`, coalesce(`perf`.`stockout_days_total`,0) AS `stockout_days_total`, coalesce(`perf`.`estimated_lost_sales`,0) AS `estimated_lost_sales`, coalesce(`perf`.`growth_rate_6m`,0) AS `growth_rate_6m`, coalesce(`ic`.`kentucky_qty`,0) AS `current_ky_qty`, coalesce(`ic`.`burnaby_qty`,0) AS `current_ca_qty` FROM ((`skus` `s` left join (select `ms`.`sku_id` AS `sku_id`,sum(coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) AS `total_revenue_12m`,sum(coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) AS `total_units_12m`,avg(coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) AS `avg_monthly_revenue`,avg(coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) AS `avg_monthly_units`,avg(case when coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) > 0 then (coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) / (coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) else 0 end) AS `avg_selling_price`,count(case when coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) > 0 then 1 end) AS `months_with_sales`,sum(coalesce(`ms`.`kentucky_stockout_days`,0) + coalesce(`ms`.`burnaby_stockout_days`,0)) AS `stockout_days_total`,sum(coalesce(`ms`.`corrected_demand_kentucky`,`ms`.`kentucky_sales`,0) + coalesce(`ms`.`corrected_demand_burnaby`,`ms`.`burnaby_sales`,0) - coalesce(`ms`.`kentucky_sales`,0) - coalesce(`ms`.`burnaby_sales`,0)) AS `estimated_lost_sales`,case when sum(case when `ms`.`year_month` >= date_format(curdate() - interval 6 month,'%Y-%m') and `ms`.`year_month` < date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end) > 0 then (sum(case when `ms`.`year_month` >= date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end) - sum(case when `ms`.`year_month` >= date_format(curdate() - interval 6 month,'%Y-%m') and `ms`.`year_month` < date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end)) / sum(case when `ms`.`year_month` >= date_format(curdate() - interval 6 month,'%Y-%m') and `ms`.`year_month` < date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end) * 100 else 0 end AS `growth_rate_6m` from `monthly_sales` `ms` where `ms`.`year_month` >= date_format(curdate() - interval 12 month,'%Y-%m') group by `ms`.`sku_id`) `perf` on(`s`.`sku_id` = `perf`.`sku_id`)) left join `inventory_current` `ic` on(`s`.`sku_id` = `ic`.`sku_id`)) ;

-- --------------------------------------------------------

--
-- Structure for view `v_current_seasonal_factors`
--
DROP TABLE IF EXISTS `v_current_seasonal_factors`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_current_seasonal_factors`  AS SELECT `sf`.`sku_id` AS `sku_id`, `sf`.`warehouse` AS `warehouse`, `sf`.`seasonal_factor` AS `current_month_factor`, `sf`.`confidence_level` AS `current_month_confidence`, `sps`.`pattern_type` AS `pattern_type`, `sps`.`pattern_strength` AS `pattern_strength`, `sps`.`overall_confidence` AS `overall_confidence`, `sps`.`statistical_significance` AS `statistical_significance`, month(current_timestamp()) AS `current_month`, monthname(current_timestamp()) AS `current_month_name`, `sf`.`last_calculated` AS `last_calculated`, CASE WHEN `sf`.`confidence_level` >= 0.7 AND `sps`.`pattern_strength` >= 0.3 THEN 'reliable' WHEN `sf`.`confidence_level` >= 0.5 AND `sps`.`pattern_strength` >= 0.2 THEN 'moderate' ELSE 'unreliable' END AS `reliability_rating` FROM (`seasonal_factors` `sf` join `seasonal_patterns_summary` `sps` on(`sf`.`sku_id` = `sps`.`sku_id` and `sf`.`warehouse` = `sps`.`warehouse`)) WHERE `sf`.`month_number` = month(current_timestamp()) ORDER BY `sf`.`sku_id` ASC, `sf`.`warehouse` ASC ;

-- --------------------------------------------------------

--
-- Structure for view `v_current_stockouts_enhanced`
--
DROP TABLE IF EXISTS `v_current_stockouts_enhanced`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_current_stockouts_enhanced`  AS SELECT `sd`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`category` AS `category`, `s`.`seasonal_pattern` AS `seasonal_pattern`, `s`.`growth_status` AS `growth_status`, `sd`.`warehouse` AS `warehouse`, `sd`.`stockout_date` AS `stockout_date`, to_days(curdate()) - to_days(`sd`.`stockout_date`) AS `days_out`, `ic`.`burnaby_qty` AS `burnaby_qty`, `ic`.`kentucky_qty` AS `kentucky_qty`, CASE WHEN to_days(curdate()) - to_days(`sd`.`stockout_date`) >= 30 THEN 'CRITICAL' WHEN to_days(curdate()) - to_days(`sd`.`stockout_date`) >= 14 THEN 'HIGH' WHEN to_days(curdate()) - to_days(`sd`.`stockout_date`) >= 7 THEN 'MEDIUM' ELSE 'LOW' END AS `urgency_level`, CASE WHEN `ms`.`corrected_demand_kentucky` > 0 AND `sd`.`warehouse` = 'kentucky' THEN `ms`.`corrected_demand_kentucky`/ 30 * (to_days(curdate()) - to_days(`sd`.`stockout_date`)) WHEN `ms`.`corrected_demand_burnaby` > 0 AND `sd`.`warehouse` = 'burnaby' THEN `ms`.`corrected_demand_burnaby`/ 30 * (to_days(curdate()) - to_days(`sd`.`stockout_date`)) ELSE 0 END AS `estimated_lost_sales`, `s`.`cost_per_unit` AS `cost_per_unit`, `s`.`abc_code` AS `abc_code`, `s`.`xyz_code` AS `xyz_code` FROM (((`stockout_dates` `sd` join `skus` `s` on(`sd`.`sku_id` = `s`.`sku_id`)) left join `inventory_current` `ic` on(`s`.`sku_id` = `ic`.`sku_id`)) left join `monthly_sales` `ms` on(`s`.`sku_id` = `ms`.`sku_id` and `ms`.`year_month` = date_format(curdate(),'%Y-%m'))) WHERE `sd`.`is_resolved` = 0 AND `s`.`status` = 'Active' ORDER BY CASE `urgency_level` WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END ASC, `sd`.`stockout_date` ASC ;

-- --------------------------------------------------------

--
-- Structure for view `v_forecast_accuracy_summary`
--
DROP TABLE IF EXISTS `v_forecast_accuracy_summary`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_forecast_accuracy_summary`  AS SELECT `forecast_accuracy`.`abc_class` AS `abc_class`, count(0) AS `total_forecasts`, count(case when `forecast_accuracy`.`is_actual_recorded` then 1 end) AS `completed_forecasts`, avg(case when `forecast_accuracy`.`is_actual_recorded` then `forecast_accuracy`.`absolute_percentage_error` end) AS `avg_mape`, std(case when `forecast_accuracy`.`is_actual_recorded` then `forecast_accuracy`.`absolute_percentage_error` end) AS `mape_std_dev`, count(case when `forecast_accuracy`.`is_actual_recorded` <> 0 and `forecast_accuracy`.`absolute_percentage_error` <= 10 then 1 end) AS `excellent_forecasts`, count(case when `forecast_accuracy`.`is_actual_recorded` <> 0 and `forecast_accuracy`.`absolute_percentage_error` <= 20 then 1 end) AS `good_forecasts`, count(case when `forecast_accuracy`.`is_actual_recorded` <> 0 and `forecast_accuracy`.`absolute_percentage_error` > 50 then 1 end) AS `poor_forecasts`, max(`forecast_accuracy`.`forecast_date`) AS `latest_forecast_date`, min(`forecast_accuracy`.`forecast_date`) AS `earliest_forecast_date` FROM `forecast_accuracy` GROUP BY `forecast_accuracy`.`abc_class` ;

-- --------------------------------------------------------

--
-- Structure for view `v_pending_orders_aggregated`
--
DROP TABLE IF EXISTS `v_pending_orders_aggregated`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_pending_orders_aggregated`  AS SELECT `pending_with_days`.`sku_id` AS `sku_id`, `pending_with_days`.`destination` AS `destination`, sum(case when `pending_with_days`.`days_until_arrival` <= 30 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end else 0 end) AS `immediate_qty`, sum(case when `pending_with_days`.`days_until_arrival` between 31 and 60 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end else 0 end) AS `near_term_qty`, sum(case when `pending_with_days`.`days_until_arrival` between 61 and 90 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end else 0 end) AS `medium_term_qty`, sum(case when `pending_with_days`.`days_until_arrival` > 90 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end else 0 end) AS `long_term_qty`, sum(case when `pending_with_days`.`days_until_arrival` <= 30 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end * 1.0 else 0 end) + sum(case when `pending_with_days`.`days_until_arrival` between 31 and 60 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end * 0.8 else 0 end) + sum(case when `pending_with_days`.`days_until_arrival` between 61 and 90 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end * 0.6 else 0 end) + sum(case when `pending_with_days`.`days_until_arrival` > 90 then `pending_with_days`.`quantity` * case when `pending_with_days`.`is_estimated` then 0.8 else 1.0 end * 0.4 else 0 end) AS `total_weighted`, min(`pending_with_days`.`expected_arrival`) AS `earliest_arrival`, max(`pending_with_days`.`expected_arrival`) AS `latest_arrival`, count(0) AS `shipment_count`, sum(`pending_with_days`.`quantity`) AS `total_raw_quantity` FROM (select `pending_inventory`.`sku_id` AS `sku_id`,`pending_inventory`.`destination` AS `destination`,`pending_inventory`.`quantity` AS `quantity`,`pending_inventory`.`expected_arrival` AS `expected_arrival`,`pending_inventory`.`is_estimated` AS `is_estimated`,`pending_inventory`.`status` AS `status`,`pending_inventory`.`order_type` AS `order_type`,to_days(`pending_inventory`.`expected_arrival`) - to_days(curdate()) AS `days_until_arrival` from `pending_inventory` where `pending_inventory`.`status` in ('ordered','shipped','pending') and `pending_inventory`.`expected_arrival` >= curdate()) AS `pending_with_days` GROUP BY `pending_with_days`.`sku_id`, `pending_with_days`.`destination` ORDER BY min(`pending_with_days`.`expected_arrival`) ASC, `pending_with_days`.`sku_id` ASC, `pending_with_days`.`destination` ASC ;

-- --------------------------------------------------------

--
-- Structure for view `v_pending_orders_analysis`
--
DROP TABLE IF EXISTS `v_pending_orders_analysis`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_pending_orders_analysis`  AS SELECT `pi`.`id` AS `id`, `pi`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`supplier` AS `supplier`, `pi`.`quantity` AS `quantity`, `pi`.`destination` AS `destination`, `pi`.`order_date` AS `order_date`, `pi`.`expected_arrival` AS `expected_arrival`, `pi`.`lead_time_days` AS `lead_time_days`, `pi`.`is_estimated` AS `is_estimated`, `pi`.`order_type` AS `order_type`, `pi`.`status` AS `status`, `pi`.`notes` AS `notes`, CASE WHEN `pi`.`expected_arrival` is not null THEN `pi`.`expected_arrival` ELSE `pi`.`order_date`+ interval `pi`.`lead_time_days` day END AS `calculated_arrival_date`, CASE WHEN `pi`.`expected_arrival` is not null THEN to_days(`pi`.`expected_arrival`) - to_days(curdate()) ELSE to_days(`pi`.`order_date` + interval `pi`.`lead_time_days` day) - to_days(curdate()) END AS `days_until_arrival`, CASE WHEN `pi`.`expected_arrival` is not null AND `pi`.`expected_arrival` < curdate() AND `pi`.`status` not in ('received','cancelled') THEN 1 WHEN `pi`.`expected_arrival` is null AND `pi`.`order_date` + interval `pi`.`lead_time_days` day < curdate() AND `pi`.`status` not in ('received','cancelled') THEN 1 ELSE 0 END AS `is_overdue`, CASE WHEN `pi`.`status` = 'received' THEN 0 WHEN `pi`.`status` = 'cancelled' THEN 0 ELSE 120 - least(120,greatest(0,case when `pi`.`expected_arrival` is not null then to_days(`pi`.`expected_arrival`) - to_days(curdate()) else to_days(`pi`.`order_date` + interval `pi`.`lead_time_days` day) - to_days(curdate()) end)) END AS `priority_score` FROM (`pending_inventory` `pi` join `skus` `s` on(`pi`.`sku_id` = `s`.`sku_id`)) ORDER BY CASE WHEN `pi`.`status` = 'received' THEN 0 WHEN `pi`.`status` = 'cancelled' THEN 0 ELSE 120 - least(120,greatest(0,case when `pi`.`expected_arrival` is not null then to_days(`pi`.`expected_arrival`) - to_days(curdate()) else to_days(`pi`.`order_date` + interval `pi`.`lead_time_days` day) - to_days(curdate()) end)) END DESC, `pi`.`order_date` ASC ;

-- --------------------------------------------------------

--
-- Structure for view `v_pending_quantities`
--
DROP TABLE IF EXISTS `v_pending_quantities`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_pending_quantities`  AS SELECT `pending_inventory`.`sku_id` AS `sku_id`, sum(case when `pending_inventory`.`destination` = 'burnaby' then `pending_inventory`.`quantity` else 0 end) AS `burnaby_pending`, sum(case when `pending_inventory`.`destination` = 'kentucky' then `pending_inventory`.`quantity` else 0 end) AS `kentucky_pending`, sum(`pending_inventory`.`quantity`) AS `total_pending`, count(case when `pending_inventory`.`order_type` = 'supplier' then 1 end) AS `supplier_orders`, count(case when `pending_inventory`.`order_type` = 'transfer' then 1 end) AS `transfer_orders`, min(case when `pending_inventory`.`expected_arrival` is not null then `pending_inventory`.`expected_arrival` else `pending_inventory`.`order_date` + interval `pending_inventory`.`lead_time_days` day end) AS `earliest_arrival` FROM `pending_inventory` WHERE `pending_inventory`.`status` not in ('received','cancelled') GROUP BY `pending_inventory`.`sku_id` ;

-- --------------------------------------------------------

--
-- Structure for view `v_revenue_analysis`
--
DROP TABLE IF EXISTS `v_revenue_analysis`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_revenue_analysis`  AS SELECT `ms`.`year_month` AS `year_month`, `ms`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`cost_per_unit` AS `cost_per_unit`, `ms`.`burnaby_sales` AS `burnaby_sales`, `ms`.`kentucky_sales` AS `kentucky_sales`, `ms`.`burnaby_revenue` AS `burnaby_revenue`, `ms`.`kentucky_revenue` AS `kentucky_revenue`, `ms`.`total_revenue` AS `total_revenue`, `ms`.`burnaby_avg_revenue` AS `burnaby_avg_revenue`, `ms`.`kentucky_avg_revenue` AS `kentucky_avg_revenue`, CASE WHEN `ms`.`burnaby_sales` + `ms`.`kentucky_sales` > 0 THEN round(`ms`.`total_revenue` / (`ms`.`burnaby_sales` + `ms`.`kentucky_sales`),2) ELSE 0.00 END AS `overall_avg_revenue`, CASE WHEN `ms`.`burnaby_avg_revenue` > 0 AND `s`.`cost_per_unit` > 0 THEN round((`ms`.`burnaby_avg_revenue` - `s`.`cost_per_unit`) / `ms`.`burnaby_avg_revenue` * 100,2) ELSE 0.00 END AS `burnaby_margin_percent`, CASE WHEN `ms`.`kentucky_avg_revenue` > 0 AND `s`.`cost_per_unit` > 0 THEN round((`ms`.`kentucky_avg_revenue` - `s`.`cost_per_unit`) / `ms`.`kentucky_avg_revenue` * 100,2) ELSE 0.00 END AS `kentucky_margin_percent` FROM (`monthly_sales` `ms` join `skus` `s` on(`ms`.`sku_id` = `s`.`sku_id`)) WHERE `s`.`status` = 'Active' ;

-- --------------------------------------------------------

--
-- Structure for view `v_revenue_dashboard`
--
DROP TABLE IF EXISTS `v_revenue_dashboard`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_revenue_dashboard`  AS SELECT year(curdate()) AS `current_year`, month(curdate()) AS `current_month`, sum(case when `ms`.`year_month` = date_format(curdate(),'%Y-%m') then `ms`.`total_revenue` else 0 end) AS `revenue_mtd`, sum(case when `ms`.`year_month` = date_format(curdate(),'%Y-%m') then `ms`.`burnaby_revenue` else 0 end) AS `burnaby_revenue_mtd`, sum(case when `ms`.`year_month` = date_format(curdate(),'%Y-%m') then `ms`.`kentucky_revenue` else 0 end) AS `kentucky_revenue_mtd`, CASE WHEN sum(case when `ms`.`year_month` = date_format(curdate(),'%Y-%m') then `ms`.`burnaby_sales` + `ms`.`kentucky_sales` else 0 end) > 0 THEN round(sum(case when `ms`.`year_month` = date_format(curdate(),'%Y-%m') then `ms`.`total_revenue` else 0 end) / sum(case when `ms`.`year_month` = date_format(curdate(),'%Y-%m') then `ms`.`burnaby_sales` + `ms`.`kentucky_sales` else 0 end),2) ELSE 0.00 END AS `avg_revenue_per_unit_mtd`, sum(case when `ms`.`year_month` = date_format(curdate() - interval 1 month,'%Y-%m') then `ms`.`total_revenue` else 0 end) AS `revenue_prev_month`, sum(case when year(str_to_date(concat(`ms`.`year_month`,'-01'),'%Y-%m-%d')) = year(curdate()) then `ms`.`total_revenue` else 0 end) AS `revenue_ytd` FROM (`monthly_sales` `ms` join `skus` `s` on(`ms`.`sku_id` = `s`.`sku_id`)) WHERE `s`.`status` = 'Active' ;

-- --------------------------------------------------------

--
-- Structure for view `v_sales_summary_12m`
--
DROP TABLE IF EXISTS `v_sales_summary_12m`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_sales_summary_12m`  AS SELECT count(distinct `ms`.`sku_id`) AS `total_skus`, sum(coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) AS `total_units`, sum(coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) AS `total_revenue`, avg(coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) AS `avg_monthly_revenue`, avg(coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) AS `avg_monthly_sales`, sum(coalesce(`ms`.`kentucky_stockout_days`,0)) AS `total_stockout_days_ky`, sum(coalesce(`ms`.`burnaby_stockout_days`,0)) AS `total_stockout_days_ca`, sum(coalesce(`ms`.`corrected_demand_kentucky`,`ms`.`kentucky_sales`,0) - coalesce(`ms`.`kentucky_sales`,0)) AS `estimated_lost_sales_ky`, sum(coalesce(`ms`.`corrected_demand_burnaby`,`ms`.`burnaby_sales`,0) - coalesce(`ms`.`burnaby_sales`,0)) AS `estimated_lost_sales_ca` FROM `monthly_sales` AS `ms` WHERE `ms`.`year_month` >= date_format(curdate() - interval 12 month,'%Y-%m') ;

-- --------------------------------------------------------

--
-- Structure for view `v_sku_demand_analysis`
--
DROP TABLE IF EXISTS `v_sku_demand_analysis`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_sku_demand_analysis`  AS SELECT `s`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`category` AS `category`, `s`.`abc_code` AS `abc_code`, `s`.`xyz_code` AS `xyz_code`, `s`.`status` AS `status`, `ic`.`kentucky_qty` AS `kentucky_qty`, `ic`.`burnaby_qty` AS `burnaby_qty`, `ls`.`last_month_sales` AS `last_month_sales`, `ls`.`kentucky_stockout_days` AS `kentucky_stockout_days`, `ls`.`corrected_demand_kentucky` AS `corrected_demand_kentucky`, `sds`.`demand_3mo_weighted` AS `demand_3mo_weighted`, `sds`.`demand_6mo_weighted` AS `demand_6mo_weighted`, `sds`.`demand_std_dev` AS `demand_std_dev`, `sds`.`coefficient_variation` AS `coefficient_variation`, `sds`.`volatility_class` AS `volatility_class`, `sds`.`sample_size_months` AS `sample_size_months`, `sds`.`data_quality_score` AS `data_quality_score`, `sds`.`last_calculated` AS `stats_last_calculated`, CASE WHEN `sds`.`demand_3mo_weighted` > 0 AND `ic`.`kentucky_qty` > 0 THEN round(`ic`.`kentucky_qty` / `sds`.`demand_3mo_weighted`,1) ELSE 0 END AS `months_coverage_3mo_avg`, CASE WHEN `sds`.`coefficient_variation` is not null AND `sds`.`coefficient_variation` > 0.75 THEN 'High Risk' WHEN `sds`.`coefficient_variation` is not null AND `sds`.`coefficient_variation` < 0.25 THEN 'Low Risk' ELSE 'Medium Risk' END AS `stockout_risk_level` FROM (((`skus` `s` left join `inventory_current` `ic` on(`s`.`sku_id` = `ic`.`sku_id`)) left join (select `ms1`.`sku_id` AS `sku_id`,`ms1`.`kentucky_sales` AS `last_month_sales`,`ms1`.`kentucky_stockout_days` AS `kentucky_stockout_days`,`ms1`.`corrected_demand_kentucky` AS `corrected_demand_kentucky` from `monthly_sales` `ms1` where `ms1`.`year_month` = (select max(`ms2`.`year_month`) from `monthly_sales` `ms2` where `ms2`.`sku_id` = `ms1`.`sku_id`)) `ls` on(`s`.`sku_id` = `ls`.`sku_id`)) left join `sku_demand_stats` `sds` on(`s`.`sku_id` = `sds`.`sku_id`)) WHERE `s`.`status` = 'Active' ;

-- --------------------------------------------------------

--
-- Structure for view `v_sku_performance_summary`
--
DROP TABLE IF EXISTS `v_sku_performance_summary`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_sku_performance_summary`  AS SELECT `s`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`category` AS `category`, `s`.`supplier` AS `supplier`, `s`.`abc_code` AS `abc_code`, `s`.`xyz_code` AS `xyz_code`, `s`.`status` AS `status`, coalesce(`perf`.`total_revenue_12m`,0) AS `total_revenue_12m`, coalesce(`perf`.`total_units_12m`,0) AS `total_units_12m`, coalesce(`perf`.`avg_monthly_revenue`,0) AS `avg_monthly_revenue`, coalesce(`perf`.`avg_monthly_units`,0) AS `avg_monthly_units`, coalesce(`perf`.`avg_selling_price`,0) AS `avg_selling_price`, coalesce(`perf`.`months_with_sales`,0) AS `months_with_sales`, coalesce(`perf`.`stockout_days_total`,0) AS `stockout_days_total`, coalesce(`perf`.`estimated_lost_sales`,0) AS `estimated_lost_sales`, coalesce(`perf`.`growth_rate_6m`,0) AS `growth_rate_6m`, coalesce(`ic`.`kentucky_qty`,0) AS `current_ky_qty`, coalesce(`ic`.`burnaby_qty`,0) AS `current_ca_qty` FROM ((`skus` `s` left join (select `ms`.`sku_id` AS `sku_id`,sum(coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) AS `total_revenue_12m`,sum(coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) AS `total_units_12m`,avg(coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) AS `avg_monthly_revenue`,avg(coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) AS `avg_monthly_units`,avg(case when coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) > 0 then (coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) / (coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) else 0 end) AS `avg_selling_price`,count(case when coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) > 0 then 1 end) AS `months_with_sales`,sum(coalesce(`ms`.`kentucky_stockout_days`,0) + coalesce(`ms`.`burnaby_stockout_days`,0)) AS `stockout_days_total`,sum(coalesce(`ms`.`corrected_demand_kentucky`,`ms`.`kentucky_sales`,0) + coalesce(`ms`.`corrected_demand_burnaby`,`ms`.`burnaby_sales`,0) - coalesce(`ms`.`kentucky_sales`,0) - coalesce(`ms`.`burnaby_sales`,0)) AS `estimated_lost_sales`,case when sum(case when `ms`.`year_month` >= date_format(curdate() - interval 6 month,'%Y-%m') and `ms`.`year_month` < date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end) > 0 then (sum(case when `ms`.`year_month` >= date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end) - sum(case when `ms`.`year_month` >= date_format(curdate() - interval 6 month,'%Y-%m') and `ms`.`year_month` < date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end)) / sum(case when `ms`.`year_month` >= date_format(curdate() - interval 6 month,'%Y-%m') and `ms`.`year_month` < date_format(curdate() - interval 3 month,'%Y-%m') then coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) else 0 end) * 100 else 0 end AS `growth_rate_6m` from `monthly_sales` `ms` where `ms`.`year_month` >= date_format(curdate() - interval 12 month,'%Y-%m') group by `ms`.`sku_id`) `perf` on(`s`.`sku_id` = `perf`.`sku_id`)) left join `inventory_current` `ic` on(`s`.`sku_id` = `ic`.`sku_id`)) WHERE `s`.`status` = 'Active' ;

-- --------------------------------------------------------

--
-- Structure for view `v_stockout_impact`
--
DROP TABLE IF EXISTS `v_stockout_impact`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_stockout_impact`  AS SELECT `s`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`abc_code` AS `abc_code`, `s`.`xyz_code` AS `xyz_code`, sum(coalesce(`ms`.`kentucky_stockout_days`,0) + coalesce(`ms`.`burnaby_stockout_days`,0)) AS `total_stockout_days`, sum(coalesce(`ms`.`kentucky_sales`,0) + coalesce(`ms`.`burnaby_sales`,0)) AS `actual_sales`, sum(coalesce(`ms`.`corrected_demand_kentucky`,`ms`.`kentucky_sales`,0) + coalesce(`ms`.`corrected_demand_burnaby`,`ms`.`burnaby_sales`,0)) AS `potential_sales`, sum(coalesce(`ms`.`corrected_demand_kentucky`,`ms`.`kentucky_sales`,0) + coalesce(`ms`.`corrected_demand_burnaby`,`ms`.`burnaby_sales`,0) - coalesce(`ms`.`kentucky_sales`,0) - coalesce(`ms`.`burnaby_sales`,0)) AS `estimated_lost_units`, sum(coalesce(`ms`.`corrected_demand_kentucky`,`ms`.`kentucky_sales`,0) + coalesce(`ms`.`corrected_demand_burnaby`,`ms`.`burnaby_sales`,0) - coalesce(`ms`.`kentucky_sales`,0) - coalesce(`ms`.`burnaby_sales`,0)) * avg(case when coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) > 0 then (coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) / (coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) else 0 end) AS `estimated_lost_revenue` FROM (`skus` `s` join `monthly_sales` `ms` on(`s`.`sku_id` = `ms`.`sku_id`)) WHERE `ms`.`year_month` >= date_format(curdate() - interval 12 month,'%Y-%m') AND (coalesce(`ms`.`kentucky_stockout_days`,0) > 0 OR coalesce(`ms`.`burnaby_stockout_days`,0) > 0) AND `s`.`status` = 'Active' GROUP BY `s`.`sku_id`, `s`.`description`, `s`.`abc_code`, `s`.`xyz_code` HAVING `total_stockout_days` > 0 AND `estimated_lost_revenue` > 0 ORDER BY sum(coalesce(`ms`.`corrected_demand_kentucky`,`ms`.`kentucky_sales`,0) + coalesce(`ms`.`corrected_demand_burnaby`,`ms`.`burnaby_sales`,0) - coalesce(`ms`.`kentucky_sales`,0) - coalesce(`ms`.`burnaby_sales`,0)) * avg(case when coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0) > 0 then (coalesce(`ms`.`burnaby_revenue`,0) + coalesce(`ms`.`kentucky_revenue`,0)) / (coalesce(`ms`.`burnaby_sales`,0) + coalesce(`ms`.`kentucky_sales`,0)) else 0 end) DESC ;

-- --------------------------------------------------------

--
-- Structure for view `v_stockout_trends`
--
DROP TABLE IF EXISTS `v_stockout_trends`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_stockout_trends`  AS SELECT `s`.`sku_id` AS `sku_id`, `s`.`description` AS `description`, `s`.`category` AS `category`, `s`.`seasonal_pattern` AS `seasonal_pattern`, count(distinct `sd`.`stockout_date`) AS `total_stockout_events`, avg(case when `sd`.`resolved_date` is not null then to_days(`sd`.`resolved_date`) - to_days(`sd`.`stockout_date`) else to_days(curdate()) - to_days(`sd`.`stockout_date`) end) AS `avg_stockout_duration`, max(`sd`.`stockout_date`) AS `last_stockout_date`, count(case when `sd`.`stockout_date` >= curdate() - interval 3 month then 1 end) AS `recent_stockouts`, group_concat(distinct month(`sd`.`stockout_date`) order by month(`sd`.`stockout_date`) ASC separator ',') AS `stockout_months`, group_concat(distinct dayofweek(`sd`.`stockout_date`) order by dayofweek(`sd`.`stockout_date`) ASC separator ',') AS `stockout_days_of_week` FROM (`skus` `s` left join `stockout_dates` `sd` on(`s`.`sku_id` = `sd`.`sku_id`)) WHERE `s`.`status` = 'Active' AND `sd`.`stockout_date` >= curdate() - interval 12 month GROUP BY `s`.`sku_id`, `s`.`description`, `s`.`category`, `s`.`seasonal_pattern` HAVING `total_stockout_events` > 0 ORDER BY count(case when `sd`.`stockout_date` >= curdate() - interval 3 month then 1 end) DESC, count(distinct `sd`.`stockout_date`) DESC ;

-- --------------------------------------------------------

--
-- Structure for view `v_test_simple`
--
DROP TABLE IF EXISTS `v_test_simple`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_test_simple`  AS SELECT count(0) AS `total` FROM `skus` ;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `cache_refresh_log`
--
ALTER TABLE `cache_refresh_log`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_started_at` (`started_at`),
  ADD KEY `idx_status` (`status`),
  ADD KEY `idx_refresh_type` (`refresh_type`),
  ADD KEY `idx_recent_operations` (`started_at`,`status`);

--
-- Indexes for table `demand_calculation_config`
--
ALTER TABLE `demand_calculation_config`
  ADD PRIMARY KEY (`config_key`);

--
-- Indexes for table `forecast_accuracy`
--
ALTER TABLE `forecast_accuracy`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_forecast` (`sku_id`,`forecast_date`,`forecast_period_start`),
  ADD KEY `idx_forecast_date` (`forecast_date`),
  ADD KEY `idx_sku_period` (`sku_id`,`forecast_period_start`),
  ADD KEY `idx_accuracy_metrics` (`is_actual_recorded`,`absolute_percentage_error`),
  ADD KEY `idx_abc_xyz_accuracy` (`abc_class`,`xyz_class`,`absolute_percentage_error`);

--
-- Indexes for table `forecast_adjustments`
--
ALTER TABLE `forecast_adjustments`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_adjustment_run` (`forecast_run_id`),
  ADD KEY `idx_adjustment_sku` (`sku_id`),
  ADD KEY `idx_adjustment_type` (`adjustment_type`),
  ADD KEY `idx_adjusted_at` (`adjusted_at`);

--
-- Indexes for table `forecast_details`
--
ALTER TABLE `forecast_details`
  ADD PRIMARY KEY (`id`),
  ADD KEY `sku_id` (`sku_id`),
  ADD KEY `idx_forecast_sku` (`forecast_run_id`,`sku_id`,`warehouse`),
  ADD KEY `idx_warehouse` (`warehouse`),
  ADD KEY `idx_confidence` (`confidence_score`);

--
-- Indexes for table `forecast_runs`
--
ALTER TABLE `forecast_runs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_forecast_status` (`status`),
  ADD KEY `idx_archived` (`archived`),
  ADD KEY `idx_forecast_date` (`forecast_date`),
  ADD KEY `idx_created_at` (`created_at`),
  ADD KEY `idx_queue_position` (`queue_position`),
  ADD KEY `idx_queued_at` (`queued_at`);

--
-- Indexes for table `inventory_current`
--
ALTER TABLE `inventory_current`
  ADD PRIMARY KEY (`sku_id`),
  ADD KEY `idx_burnaby_qty` (`burnaby_qty`),
  ADD KEY `idx_kentucky_qty` (`kentucky_qty`),
  ADD KEY `idx_last_updated` (`last_updated`);

--
-- Indexes for table `monthly_sales`
--
ALTER TABLE `monthly_sales`
  ADD PRIMARY KEY (`year_month`,`sku_id`),
  ADD KEY `idx_monthly_sales_latest_data` (`sku_id`,`year_month`),
  ADD KEY `idx_burnaby_revenue` (`burnaby_revenue`),
  ADD KEY `idx_kentucky_revenue` (`kentucky_revenue`),
  ADD KEY `idx_total_revenue` (`total_revenue`),
  ADD KEY `idx_monthly_sales_year_month` (`year_month`),
  ADD KEY `idx_monthly_sales_sku_year_month` (`sku_id`,`year_month`),
  ADD KEY `idx_monthly_sales_stockout_analysis` (`kentucky_stockout_days`,`burnaby_stockout_days`),
  ADD KEY `idx_monthly_sales_corrected_demand_analysis` (`corrected_demand_kentucky`,`corrected_demand_burnaby`);

--
-- Indexes for table `pending_inventory`
--
ALTER TABLE `pending_inventory`
  ADD PRIMARY KEY (`id`),
  ADD KEY `sku_id` (`sku_id`),
  ADD KEY `idx_pending_lead_time` (`lead_time_days`),
  ADD KEY `idx_pending_estimated` (`is_estimated`);

--
-- Indexes for table `seasonal_factors`
--
ALTER TABLE `seasonal_factors`
  ADD PRIMARY KEY (`sku_id`,`warehouse`,`month_number`),
  ADD KEY `idx_sku_warehouse` (`sku_id`,`warehouse`),
  ADD KEY `idx_pattern_type` (`pattern_type`),
  ADD KEY `idx_confidence` (`confidence_level`),
  ADD KEY `idx_last_calculated` (`last_calculated`);

--
-- Indexes for table `seasonal_patterns`
--
ALTER TABLE `seasonal_patterns`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_sku_month` (`sku_id`,`month_number`),
  ADD KEY `idx_seasonal_sku` (`sku_id`),
  ADD KEY `idx_seasonal_month` (`month_number`),
  ADD KEY `idx_seasonal_last_calc` (`last_calculated`);

--
-- Indexes for table `seasonal_patterns_summary`
--
ALTER TABLE `seasonal_patterns_summary`
  ADD PRIMARY KEY (`sku_id`,`warehouse`),
  ADD KEY `idx_pattern_type` (`pattern_type`),
  ADD KEY `idx_pattern_strength` (`pattern_strength`),
  ADD KEY `idx_confidence` (`overall_confidence`),
  ADD KEY `idx_significance` (`statistical_significance`),
  ADD KEY `idx_last_analyzed` (`last_analyzed`);

--
-- Indexes for table `skus`
--
ALTER TABLE `skus`
  ADD PRIMARY KEY (`sku_id`),
  ADD KEY `idx_skus_seasonal_pattern` (`seasonal_pattern`,`status`),
  ADD KEY `idx_skus_growth_status` (`growth_status`,`seasonal_pattern`),
  ADD KEY `idx_skus_abc_xyz_classification` (`abc_code`,`xyz_code`,`status`);

--
-- Indexes for table `sku_demand_stats`
--
ALTER TABLE `sku_demand_stats`
  ADD PRIMARY KEY (`sku_id`,`warehouse`),
  ADD UNIQUE KEY `idx_sku_warehouse_cache` (`sku_id`,`warehouse`),
  ADD KEY `idx_volatility_class` (`volatility_class`),
  ADD KEY `idx_last_calculated` (`last_calculated`),
  ADD KEY `idx_data_quality` (`data_quality_score`),
  ADD KEY `idx_cv_score` (`coefficient_variation`),
  ADD KEY `idx_sku_demand_stats_composite` (`volatility_class`,`coefficient_variation`,`data_quality_score`),
  ADD KEY `idx_warehouse` (`warehouse`),
  ADD KEY `idx_cache_lookup` (`sku_id`,`warehouse`,`cache_valid`),
  ADD KEY `idx_invalidation` (`cache_valid`,`invalidated_at`);

--
-- Indexes for table `stockout_dates`
--
ALTER TABLE `stockout_dates`
  ADD PRIMARY KEY (`sku_id`,`warehouse`,`stockout_date`);

--
-- Indexes for table `stockout_patterns`
--
ALTER TABLE `stockout_patterns`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_sku_pattern` (`sku_id`,`pattern_type`,`pattern_value`),
  ADD KEY `idx_pattern_sku` (`sku_id`),
  ADD KEY `idx_pattern_type` (`pattern_type`),
  ADD KEY `idx_pattern_confidence` (`confidence_level`,`frequency_score`);

--
-- Indexes for table `stockout_updates_log`
--
ALTER TABLE `stockout_updates_log`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_update_batch` (`update_batch_id`),
  ADD KEY `idx_update_sku` (`sku_id`,`created_at`),
  ADD KEY `idx_update_source` (`update_source`,`created_at`),
  ADD KEY `idx_update_date` (`created_at`);

--
-- Indexes for table `suppliers`
--
ALTER TABLE `suppliers`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `supplier_code` (`supplier_code`),
  ADD KEY `idx_suppliers_normalized_name` (`normalized_name`),
  ADD KEY `idx_suppliers_display_name` (`display_name`),
  ADD KEY `idx_suppliers_active` (`is_active`),
  ADD KEY `idx_suppliers_created_at` (`created_at`);

--
-- Indexes for table `supplier_aliases`
--
ALTER TABLE `supplier_aliases`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_supplier_alias` (`supplier_id`,`normalized_alias`),
  ADD KEY `idx_aliases_normalized` (`normalized_alias`),
  ADD KEY `idx_aliases_supplier_id` (`supplier_id`),
  ADD KEY `idx_aliases_usage_count` (`usage_count`),
  ADD KEY `idx_aliases_confidence` (`confidence_score`);

--
-- Indexes for table `supplier_lead_times`
--
ALTER TABLE `supplier_lead_times`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_supplier_destination` (`supplier`,`destination`);

--
-- Indexes for table `supplier_shipments`
--
ALTER TABLE `supplier_shipments`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `po_number` (`po_number`),
  ADD KEY `idx_supplier` (`supplier`),
  ADD KEY `idx_order_date` (`order_date`),
  ADD KEY `idx_destination` (`destination`),
  ADD KEY `idx_received_date` (`received_date`);

--
-- Indexes for table `system_config`
--
ALTER TABLE `system_config`
  ADD PRIMARY KEY (`config_key`);

--
-- Indexes for table `transfer_confirmations`
--
ALTER TABLE `transfer_confirmations`
  ADD PRIMARY KEY (`sku_id`),
  ADD KEY `idx_ca_order_qty` (`ca_order_qty`),
  ADD KEY `idx_ky_order_qty` (`ky_order_qty`);

--
-- Indexes for table `transfer_history`
--
ALTER TABLE `transfer_history`
  ADD PRIMARY KEY (`id`),
  ADD KEY `sku_id` (`sku_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `cache_refresh_log`
--
ALTER TABLE `cache_refresh_log`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `forecast_accuracy`
--
ALTER TABLE `forecast_accuracy`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `forecast_adjustments`
--
ALTER TABLE `forecast_adjustments`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `forecast_details`
--
ALTER TABLE `forecast_details`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `forecast_runs`
--
ALTER TABLE `forecast_runs`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `pending_inventory`
--
ALTER TABLE `pending_inventory`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `seasonal_patterns`
--
ALTER TABLE `seasonal_patterns`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `stockout_patterns`
--
ALTER TABLE `stockout_patterns`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `stockout_updates_log`
--
ALTER TABLE `stockout_updates_log`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `suppliers`
--
ALTER TABLE `suppliers`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `supplier_aliases`
--
ALTER TABLE `supplier_aliases`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `supplier_lead_times`
--
ALTER TABLE `supplier_lead_times`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `supplier_shipments`
--
ALTER TABLE `supplier_shipments`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `transfer_history`
--
ALTER TABLE `transfer_history`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `forecast_accuracy`
--
ALTER TABLE `forecast_accuracy`
  ADD CONSTRAINT `forecast_accuracy_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `forecast_adjustments`
--
ALTER TABLE `forecast_adjustments`
  ADD CONSTRAINT `forecast_adjustments_ibfk_1` FOREIGN KEY (`forecast_run_id`) REFERENCES `forecast_runs` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `forecast_adjustments_ibfk_2` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `forecast_details`
--
ALTER TABLE `forecast_details`
  ADD CONSTRAINT `forecast_details_ibfk_1` FOREIGN KEY (`forecast_run_id`) REFERENCES `forecast_runs` (`id`) ON DELETE CASCADE,
  ADD CONSTRAINT `forecast_details_ibfk_2` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `inventory_current`
--
ALTER TABLE `inventory_current`
  ADD CONSTRAINT `inventory_current_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `monthly_sales`
--
ALTER TABLE `monthly_sales`
  ADD CONSTRAINT `monthly_sales_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `pending_inventory`
--
ALTER TABLE `pending_inventory`
  ADD CONSTRAINT `pending_inventory_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `seasonal_patterns`
--
ALTER TABLE `seasonal_patterns`
  ADD CONSTRAINT `seasonal_patterns_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `sku_demand_stats`
--
ALTER TABLE `sku_demand_stats`
  ADD CONSTRAINT `sku_demand_stats_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `stockout_dates`
--
ALTER TABLE `stockout_dates`
  ADD CONSTRAINT `stockout_dates_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `stockout_patterns`
--
ALTER TABLE `stockout_patterns`
  ADD CONSTRAINT `stockout_patterns_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `stockout_updates_log`
--
ALTER TABLE `stockout_updates_log`
  ADD CONSTRAINT `stockout_updates_log_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `supplier_aliases`
--
ALTER TABLE `supplier_aliases`
  ADD CONSTRAINT `supplier_aliases_ibfk_1` FOREIGN KEY (`supplier_id`) REFERENCES `suppliers` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `transfer_confirmations`
--
ALTER TABLE `transfer_confirmations`
  ADD CONSTRAINT `transfer_confirmations_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;

--
-- Constraints for table `transfer_history`
--
ALTER TABLE `transfer_history`
  ADD CONSTRAINT `transfer_history_ibfk_1` FOREIGN KEY (`sku_id`) REFERENCES `skus` (`sku_id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
