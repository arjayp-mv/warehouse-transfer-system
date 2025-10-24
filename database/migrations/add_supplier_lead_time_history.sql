-- =====================================================
-- V9.0: Monthly Supplier Ordering System
-- Migration: Add supplier_lead_time_history audit table
-- Created: 2025-01-22
-- =====================================================

-- Purpose: Track all changes to supplier lead times for audit trail
--          and historical analysis. Provides accountability and enables
--          review of lead time adjustments over time.

CREATE TABLE IF NOT EXISTS `supplier_lead_time_history` (
  -- Primary Key
  `id` INT PRIMARY KEY AUTO_INCREMENT,

  -- Supplier Identification
  `supplier` VARCHAR(100) NOT NULL COMMENT 'Supplier name (normalized)',

  -- Lead Time Change Tracking
  `old_p95_lead_time` INT DEFAULT NULL COMMENT 'Previous P95 lead time (NULL for new suppliers)',
  `new_p95_lead_time` INT NOT NULL COMMENT 'New P95 lead time in days',

  -- Change Metadata
  `updated_by` VARCHAR(100) NOT NULL COMMENT 'Username who made the change',
  `notes` TEXT DEFAULT NULL COMMENT 'Reason for change or additional context',
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When change was made',

  -- Indexes for Performance
  INDEX `idx_supplier_history` (`supplier`, `updated_at`),
  INDEX `idx_updated_at` (`updated_at`)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_general_ci
  COMMENT='Audit trail for supplier lead time changes';

-- =====================================================
-- End of Migration
-- =====================================================
