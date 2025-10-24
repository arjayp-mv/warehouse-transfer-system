-- =====================================================
-- V9.0: Monthly Supplier Ordering System
-- Migration: Add supplier_order_confirmations table
-- Created: 2025-01-22
-- =====================================================

-- Purpose: Store monthly supplier order recommendations with time-phased
--          pending analysis, confidence scoring, and editable lead times.
--          Replaces manual Excel-based supplier ordering process.

CREATE TABLE IF NOT EXISTS `supplier_order_confirmations` (
  -- Primary Key
  `id` INT PRIMARY KEY AUTO_INCREMENT,

  -- SKU Identification
  `sku_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT 'SKU identifier',
  `warehouse` ENUM('burnaby', 'kentucky') NOT NULL COMMENT 'Destination warehouse',

  -- Order Quantities
  `suggested_qty` INT NOT NULL COMMENT 'System-calculated order quantity based on reorder point',
  `confirmed_qty` INT NOT NULL COMMENT 'User-editable final order quantity',
  `supplier` VARCHAR(100) NOT NULL COMMENT 'Supplier name from skus.supplier',

  -- Calculation Transparency Fields
  `current_inventory` INT NOT NULL COMMENT 'Stock on hand at time of calculation',
  `pending_orders_raw` INT NOT NULL DEFAULT 0 COMMENT 'Total pending qty (unadjusted)',
  `pending_orders_effective` INT NOT NULL DEFAULT 0 COMMENT 'Time-phased pending with confidence scoring',
  `pending_breakdown` JSON DEFAULT NULL COMMENT 'Array of pending orders with confidence details',
  `corrected_demand_monthly` DECIMAL(10,2) DEFAULT NULL COMMENT 'Stockout-corrected monthly demand from monthly_sales',
  `safety_stock_qty` INT NOT NULL COMMENT 'Calculated safety stock for monthly ordering cycle',
  `reorder_point` INT NOT NULL COMMENT 'Reorder point = demand_during_period + safety_stock',

  -- Monthly Ordering Specifics
  `order_month` VARCHAR(7) NOT NULL COMMENT 'Order month in YYYY-MM format',
  `days_in_month` TINYINT NOT NULL COMMENT 'Actual calendar days (28-31) via calendar.monthrange()',
  `lead_time_days_default` INT DEFAULT NULL COMMENT 'Default P95 lead time from supplier_lead_times',
  `lead_time_days_override` INT DEFAULT NULL COMMENT 'User-editable lead time override (applies to this order only)',
  `expected_arrival_calculated` DATE DEFAULT NULL COMMENT 'Auto-calculated: order_date + lead_time_days',
  `expected_arrival_override` DATE DEFAULT NULL COMMENT 'User-editable arrival date override',
  `coverage_months` DECIMAL(4,2) DEFAULT NULL COMMENT 'Months of coverage AFTER this order arrives',
  `urgency_level` ENUM('skip', 'optional', 'should_order', 'must_order') DEFAULT 'optional' COMMENT 'Order urgency based on coverage vs lead time',

  -- Stockout Context
  `overdue_pending_count` INT DEFAULT 0 COMMENT 'Number of pending orders past expected_arrival',
  `stockout_risk_date` DATE DEFAULT NULL COMMENT 'Projected date when SKU will run out if no order placed',

  -- User Actions
  `is_locked` BOOLEAN DEFAULT FALSE COMMENT 'Lock prevents editing (for confirmed orders)',
  `locked_by` VARCHAR(100) DEFAULT NULL COMMENT 'Username who locked this order',
  `locked_at` TIMESTAMP NULL DEFAULT NULL COMMENT 'When order was locked',
  `notes` TEXT DEFAULT NULL COMMENT 'User notes or special instructions',

  -- Audit Timestamps
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When recommendation was generated',
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last modification time',

  -- Foreign Keys
  CONSTRAINT `fk_supplier_orders_sku`
    FOREIGN KEY (`sku_id`)
    REFERENCES `skus`(`sku_id`)
    ON DELETE CASCADE,

  -- Indexes for Performance (comments moved to inline above)
  INDEX `idx_order_month_wh_supplier` (`order_month`, `warehouse`, `supplier`),
  INDEX `idx_urgency_month` (`urgency_level`, `order_month`),
  INDEX `idx_locked_orders` (`is_locked`, `locked_at`),
  INDEX `idx_stockout_risk` (`stockout_risk_date`, `urgency_level`),

  -- Unique Constraint: One recommendation per SKU per warehouse per month
  UNIQUE KEY `unique_sku_warehouse_month` (`sku_id`, `warehouse`, `order_month`)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_general_ci
  COMMENT='Monthly supplier order recommendations with time-phased pending analysis';

-- =====================================================
-- End of Migration
-- =====================================================
