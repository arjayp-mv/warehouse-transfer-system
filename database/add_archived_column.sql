-- Add archived column to forecast_runs table
-- Migration for Phase 3: Archive System
-- Date: 2025-10-22

-- Add archived column with default FALSE (not archived)
ALTER TABLE forecast_runs
ADD COLUMN archived BOOLEAN DEFAULT FALSE AFTER status;

-- Add index for performance when filtering archived forecasts
ALTER TABLE forecast_runs
ADD INDEX idx_archived (archived);

-- Verify the changes
DESCRIBE forecast_runs;
