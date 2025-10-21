-- Migration script to populate supplier master tables with existing data
-- This script extracts unique suppliers from existing tables and creates
-- normalized supplier records and aliases for consistent data management

-- =====================================================================
-- Supplier Master Data Migration Script
-- =====================================================================

-- This script:
-- 1. Extracts unique suppliers from existing tables
-- 2. Creates normalized supplier records in the suppliers table
-- 3. Sets up initial aliases for consistency
-- 4. Provides statistics on the migration

START TRANSACTION;

-- Temporary table to collect unique supplier names from all sources
DROP TEMPORARY TABLE IF EXISTS temp_unique_suppliers;
CREATE TEMPORARY TABLE temp_unique_suppliers (
    original_name VARCHAR(100) NOT NULL,
    normalized_name VARCHAR(100) NOT NULL,
    usage_count INT DEFAULT 1,
    first_seen DATE DEFAULT NULL,
    last_seen DATE DEFAULT NULL,
    PRIMARY KEY (original_name)
);

-- Extract suppliers from supplier_shipments table
INSERT INTO temp_unique_suppliers (original_name, normalized_name, usage_count, first_seen, last_seen)
SELECT
    supplier AS original_name,
    LOWER(TRIM(REPLACE(REPLACE(REPLACE(supplier, '.', ''), ',', ''), '  ', ' '))) AS normalized_name,
    COUNT(*) AS usage_count,
    MIN(order_date) AS first_seen,
    MAX(order_date) AS last_seen
FROM supplier_shipments
WHERE supplier IS NOT NULL
  AND TRIM(supplier) != ''
  AND UPPER(TRIM(supplier)) NOT IN ('N/A', 'NA', 'NONE', 'NULL', 'UNKNOWN', 'TBD', 'PENDING', 'SUPPLIER', 'VENDOR')
GROUP BY supplier
ON DUPLICATE KEY UPDATE
    usage_count = usage_count + VALUES(usage_count),
    first_seen = LEAST(first_seen, VALUES(first_seen)),
    last_seen = GREATEST(last_seen, VALUES(last_seen));

-- Extract suppliers from supplier_lead_times table if it has different suppliers
INSERT INTO temp_unique_suppliers (original_name, normalized_name, usage_count, first_seen, last_seen)
SELECT
    supplier AS original_name,
    LOWER(TRIM(REPLACE(REPLACE(REPLACE(supplier, '.', ''), ',', ''), '  ', ' '))) AS normalized_name,
    1 AS usage_count,
    CURDATE() AS first_seen,
    CURDATE() AS last_seen
FROM supplier_lead_times
WHERE supplier IS NOT NULL
  AND TRIM(supplier) != ''
  AND UPPER(TRIM(supplier)) NOT IN ('N/A', 'NA', 'NONE', 'NULL', 'UNKNOWN', 'TBD', 'PENDING', 'SUPPLIER', 'VENDOR')
  AND supplier NOT IN (SELECT original_name FROM temp_unique_suppliers)
GROUP BY supplier
ON DUPLICATE KEY UPDATE
    usage_count = usage_count + VALUES(usage_count);

-- Extract suppliers from skus table if it has supplier information
INSERT INTO temp_unique_suppliers (original_name, normalized_name, usage_count, first_seen, last_seen)
SELECT
    supplier AS original_name,
    LOWER(TRIM(REPLACE(REPLACE(REPLACE(supplier, '.', ''), ',', ''), '  ', ' '))) AS normalized_name,
    1 AS usage_count,
    CURDATE() AS first_seen,
    CURDATE() AS last_seen
FROM skus
WHERE supplier IS NOT NULL
  AND TRIM(supplier) != ''
  AND UPPER(TRIM(supplier)) NOT IN ('N/A', 'NA', 'NONE', 'NULL', 'UNKNOWN', 'TBD', 'PENDING', 'SUPPLIER', 'VENDOR')
  AND supplier NOT IN (SELECT original_name FROM temp_unique_suppliers)
GROUP BY supplier
ON DUPLICATE KEY UPDATE
    usage_count = usage_count + VALUES(usage_count);

-- Show statistics before migration
SELECT
    'Pre-Migration Statistics' AS info,
    COUNT(*) AS unique_suppliers_found,
    SUM(usage_count) AS total_usage_count,
    MIN(first_seen) AS earliest_supplier_date,
    MAX(last_seen) AS latest_supplier_date
FROM temp_unique_suppliers;

-- Create supplier master records
-- Group by normalized name to handle variations
INSERT INTO suppliers (display_name, normalized_name, created_by, created_at)
SELECT
    -- Use the most frequently used original name as display name
    SUBSTRING_INDEX(GROUP_CONCAT(original_name ORDER BY usage_count DESC SEPARATOR '|'), '|', 1) AS display_name,
    normalized_name,
    'migration_script' AS created_by,
    NOW() AS created_at
FROM temp_unique_suppliers
WHERE normalized_name != ''  -- Exclude empty normalized names
GROUP BY normalized_name
ORDER BY SUM(usage_count) DESC;

-- Create aliases for all variations that map to the same normalized name
INSERT INTO supplier_aliases (supplier_id, alias_name, normalized_alias, usage_count, confidence_score, created_by, created_at)
SELECT
    s.id AS supplier_id,
    t.original_name AS alias_name,
    t.normalized_name AS normalized_alias,
    t.usage_count,
    100.0 AS confidence_score,  -- High confidence for exact matches from migration
    'migration_script' AS created_by,
    NOW() AS created_at
FROM temp_unique_suppliers t
JOIN suppliers s ON t.normalized_name = s.normalized_name
WHERE t.original_name != s.display_name  -- Don't create alias for display name itself
ORDER BY t.usage_count DESC;

-- Show post-migration statistics
SELECT
    'Post-Migration Statistics' AS info,
    (SELECT COUNT(*) FROM suppliers WHERE created_by = 'migration_script') AS suppliers_created,
    (SELECT COUNT(*) FROM supplier_aliases WHERE created_by = 'migration_script') AS aliases_created,
    (SELECT SUM(usage_count) FROM supplier_aliases WHERE created_by = 'migration_script') AS total_alias_usage;

-- Show top 10 suppliers by usage
SELECT
    'Top 10 Suppliers by Usage' AS info,
    s.display_name,
    s.normalized_name,
    COALESCE(SUM(sa.usage_count), 0) + 1 AS total_usage,  -- +1 for display name usage
    COUNT(sa.id) AS alias_count
FROM suppliers s
LEFT JOIN supplier_aliases sa ON s.id = sa.supplier_id
WHERE s.created_by = 'migration_script'
GROUP BY s.id, s.display_name, s.normalized_name
ORDER BY total_usage DESC
LIMIT 10;

-- Show examples of aliases created
SELECT
    'Sample Aliases Created' AS info,
    s.display_name AS master_supplier,
    sa.alias_name AS alias_variation,
    sa.usage_count,
    sa.confidence_score
FROM supplier_aliases sa
JOIN suppliers s ON sa.supplier_id = s.id
WHERE sa.created_by = 'migration_script'
ORDER BY sa.usage_count DESC
LIMIT 10;

-- Validation queries to ensure migration was successful
SELECT
    'Migration Validation' AS info,
    CASE
        WHEN (SELECT COUNT(*) FROM suppliers WHERE created_by = 'migration_script') > 0
        THEN 'SUCCESS: Suppliers created'
        ELSE 'ERROR: No suppliers created'
    END AS suppliers_status,
    CASE
        WHEN (SELECT COUNT(DISTINCT normalized_name) FROM temp_unique_suppliers) =
             (SELECT COUNT(*) FROM suppliers WHERE created_by = 'migration_script')
        THEN 'SUCCESS: All unique normalized names migrated'
        ELSE 'WARNING: Normalized name count mismatch'
    END AS normalization_status;

-- Clean up temporary table
DROP TEMPORARY TABLE temp_unique_suppliers;

-- Optimization: Update statistics for better query performance
ANALYZE TABLE suppliers;
ANALYZE TABLE supplier_aliases;

COMMIT;

-- =====================================================================
-- Post-Migration Notes
-- =====================================================================

-- After running this migration:
-- 1. The suppliers table contains one record per unique normalized supplier name
-- 2. The supplier_aliases table contains mappings for all name variations
-- 3. Future imports can use the new supplier mapping system
-- 4. Existing supplier names in other tables remain unchanged for backward compatibility
-- 5. The new system will automatically handle supplier name variations

-- To verify the migration worked correctly, run:
-- SELECT COUNT(*) FROM suppliers WHERE created_by = 'migration_script';
-- SELECT COUNT(*) FROM supplier_aliases WHERE created_by = 'migration_script';

-- To see all suppliers and their aliases:
-- SELECT s.display_name, s.normalized_name,
--        GROUP_CONCAT(sa.alias_name SEPARATOR ', ') as aliases
-- FROM suppliers s
-- LEFT JOIN supplier_aliases sa ON s.id = sa.supplier_id
-- WHERE s.created_by = 'migration_script'
-- GROUP BY s.id, s.display_name, s.normalized_name
-- ORDER BY s.display_name;