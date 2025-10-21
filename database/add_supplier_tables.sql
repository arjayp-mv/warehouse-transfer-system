-- Add Supplier Master Tables to Existing Database
-- This script adds the supplier normalization tables to support intelligent supplier name matching
-- Run this after the main schema.sql has been applied

-- Create suppliers master table
CREATE TABLE IF NOT EXISTS suppliers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    supplier_code VARCHAR(50) UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    legal_name VARCHAR(100),
    normalized_name VARCHAR(100) NOT NULL,
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state_province VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(100) DEFAULT 'Canada',
    default_lead_time INT DEFAULT 30,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_suppliers_normalized_name (normalized_name),
    INDEX idx_suppliers_display_name (display_name),
    INDEX idx_suppliers_active (is_active),
    INDEX idx_suppliers_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Master supplier table with normalized names for consistent matching';

-- Create supplier aliases table for name variations
CREATE TABLE IF NOT EXISTS supplier_aliases (
    id INT PRIMARY KEY AUTO_INCREMENT,
    supplier_id INT NOT NULL,
    alias_name VARCHAR(100) NOT NULL,
    normalized_alias VARCHAR(100) NOT NULL,
    usage_count INT DEFAULT 1,
    confidence_score DECIMAL(5,2) DEFAULT 100.00,
    is_primary BOOLEAN DEFAULT FALSE,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) ON DELETE CASCADE,
    UNIQUE KEY unique_supplier_alias (supplier_id, normalized_alias),
    INDEX idx_aliases_normalized (normalized_alias),
    INDEX idx_aliases_supplier_id (supplier_id),
    INDEX idx_aliases_usage_count (usage_count DESC),
    INDEX idx_aliases_confidence (confidence_score DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Supplier name aliases for fuzzy matching and name variations';

-- Show tables created
SELECT 'Supplier tables created successfully' AS Status;