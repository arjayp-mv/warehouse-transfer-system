-- Add supplier column to pending_inventory table
-- This fixes the issue where supplier names from CSV imports were being lost
-- The CSV column "order_type" actually contains supplier names, not order types

ALTER TABLE pending_inventory
ADD COLUMN supplier VARCHAR(100) NULL COMMENT 'Supplier name from order' AFTER order_type;

-- Add index for better query performance
CREATE INDEX idx_pending_supplier ON pending_inventory(supplier);

-- Migration completed
SELECT 'Supplier column added to pending_inventory table' AS status;
