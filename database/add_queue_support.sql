-- V7.3 Phase 4: Add Queue Management Support
-- Purpose: Enable concurrent forecast request handling with FIFO queue system
-- Date: 2025-10-20
-- Issue: Users get "job already running" error when trying to generate forecasts simultaneously

-- Add queue_position column to track position in queue
ALTER TABLE forecast_runs
ADD COLUMN queue_position INT NULL COMMENT 'Position in forecast generation queue (NULL if not queued)' AFTER status;

-- Add queued_at timestamp to track when forecast was queued
ALTER TABLE forecast_runs
ADD COLUMN queued_at TIMESTAMP NULL COMMENT 'Timestamp when forecast was added to queue' AFTER created_at;

-- Update status ENUM to include 'queued' state
-- Status flow: pending → queued (if job running) → running → completed/failed/cancelled
ALTER TABLE forecast_runs
MODIFY COLUMN status ENUM('pending', 'queued', 'running', 'completed', 'failed', 'cancelled')
DEFAULT 'pending'
COMMENT 'Current status of forecast generation';

-- Add index on queue_position for efficient queue queries
CREATE INDEX idx_queue_position ON forecast_runs(queue_position);

-- Add index on queued_at for queue ordering
CREATE INDEX idx_queued_at ON forecast_runs(queued_at);
