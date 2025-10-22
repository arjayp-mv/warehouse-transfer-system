
  What Was Completed

  1. Database Migration ✅

  - Added archived BOOLEAN column to forecast_runs table (default: FALSE)
  - Added idx_archived index for query performance
  - Updated database/schema.sql to reflect changes
  - Migration executed successfully

  2. Backend API Endpoints ✅

  File: backend/forecasting_api.py
  - POST /api/forecasts/runs/{run_id}/archive - Archive single forecast (lines 734-790)
  - POST /api/forecasts/runs/{run_id}/unarchive - Restore from archive (lines 793-840)
  - POST /api/forecasts/runs/bulk-archive - Archive multiple forecasts with validation (lines 843-921)
  - GET /api/forecasts/runs/archived - List archived forecasts only (lines 924-966)

  File: backend/forecast_jobs.py
  - Updated get_active_forecast_runs() function (line 516) to add WHERE archived = 0 filter

  3. Archive Page ✅

  File: frontend/forecast-archive.html (NEW)
  - Complete standalone page for viewing archived forecasts
  - DataTables with sorting/filtering
  - Bulk unarchive functionality (checkboxes + "Restore Selected" button)
  - Individual "Restore" buttons per forecast
  - "View" buttons that redirect to main forecasting page with run_id parameter
  - Simple confirmation for restore operations (no safety warnings since reversible)

  4. Main UI Updates ✅

  File: frontend/forecasting.html
  - Added "Archive" link to navbar (line 139-141)
  - Added "Archive Selected (N)" button next to "Delete Selected" button (lines 282-284)

  File: frontend/forecasting.js
  - Updated renderRunActions() to add archive buttons for:
    - Completed forecasts (with View/Export buttons)
    - Failed forecasts (standalone archive button)
    - Cancelled forecasts (standalone archive button)
  - Updated updateBulkDeleteButton() to also show/hide bulk archive button (lines 948-966)
  - Added archiveForecast(runId, name) function (lines 1084-1105)
  - Added bulkArchiveForecasts() function with safety confirmations (lines 1111-1191):
    - Warns for forecasts <7 days old
    - Requires typing "ARCHIVE" for 10+ items
    - Simple confirmation for smaller batches
    - Validates running/queued forecasts cannot be archived

  5. Testing Completed ✅

  Single Archive Test:
  - ✅ Clicked archive button on "Combine Forecast 102225"
  - ✅ Confirmation dialog appeared correctly
  - ✅ Success message: "Forecast 'Combine Forecast 102225' archived successfully"
  - ✅ Forecast removed from main list (45 → 44 entries)
  - ✅ Table auto-refreshed

  Bulk Archive Test:
  - ✅ Selected 2 forecasts using checkboxes (Modal Test Forecast A & B)
  - ✅ Bulk buttons appeared with correct counters (1 → 2)
  - ✅ First safety dialog: Recent forecast warning (<7 days)
  - ✅ Second safety dialog: Standard confirmation
  - ✅ Success message: "Successfully archived 2 forecast(s)"
  - ✅ Both forecasts removed (44 → 42 entries)
  - ✅ Bulk buttons hidden after operation

  What Needs to be Fixed 🔧

  CRITICAL BUG: Archive Page API Error

  File: frontend/forecast-archive.html

  Symptom:
  - Archive page loads but shows error: "Failed to load archived forecasts"
  - Console shows: "422 (Unprocessable Content)" error
  - Table displays "No data available"

  Root Cause:
  The archive page JavaScript is calling the bulk unarchive API incorrectly. Looking at line 374-379 in forecast-archive.html:

  // Call unarchive endpoint for each forecast
  const promises = runIds.map(runId =>
      fetch(`${API_BASE}/runs/${runId}/unarchive`, { method: 'POST' })
  );

  This is making multiple individual API calls instead of using a bulk endpoint. However, there is NO bulk unarchive endpoint in the backend    
   - we only created:
  - Single unarchive: POST /api/forecasts/runs/{run_id}/unarchive ✅
  - Bulk archive: POST /api/forecasts/runs/bulk-archive ✅
  - But missing: POST /api/forecasts/runs/bulk-unarchive ❌

  Also check: The archive page may be failing to load initially because the GET /api/forecasts/runs/archived endpoint might have an issue.      
  Check server logs for details.

  Fix Required:
  1. Check why GET /api/forecasts/runs/archived returns 422 error
  2. Either:
    - Option A: Keep multiple individual unarchive calls (simpler, works for small batches)
    - Option B: Add POST /api/forecasts/runs/bulk-unarchive endpoint for consistency

  Testing Still Needed

  1. Archive Page Load - Fix the 422 error and verify archived forecasts display
  2. Single Unarchive - Click "Restore" button on archived forecast
  3. Bulk Unarchive - Select multiple and click "Restore Selected (N)"
  4. Navigation Flow - Verify "Back to Forecasts" link works
  5. View Archived Forecast - Click "View" button to see forecast details

  Key Implementation Details

  Safety Validations (Applied to Archive)

  - Cannot archive running/queued forecasts (backend validation)
  - Warning for forecasts <7 days old (frontend check)
  - Require typing "ARCHIVE" for batches of 10+ items
  - Simple confirmation for smaller batches

  Database State

  - 3 forecasts currently archived (IDs: 50, 40, 41)
  - 42 forecasts visible in main list
  - Archive column successfully filtering forecasts from main view

  File Changes Summary

  - database/add_archived_column.sql (NEW)
  - database/schema.sql (MODIFIED - added archived column + index)
  - backend/forecasting_api.py (MODIFIED - added 4 endpoints: lines 734-966)
  - backend/forecast_jobs.py (MODIFIED - line 516 added WHERE filter)
  - frontend/forecast-archive.html (NEW - complete archive page)
  - frontend/forecasting.html (MODIFIED - navbar link + bulk buttons)
  - frontend/forecasting.js (MODIFIED - archive functions + UI updates)

  Next Steps for New Instance

  1. Debug Archive Page 422 Error:
    - Check server logs: BashOutput for bash_id e29f95
    - Test API directly: fetch('/api/forecasts/runs/archived')
    - Check for parameter issues in archive page JavaScript
  2. Complete Archive Page Testing once 422 is fixed
  3. Update Todo List and mark Phase 3 as completed
  4. Optional Enhancement: Add bulk unarchive endpoint for consistency (not required, but nice to have)

  All core functionality is implemented and working except for the archive page load issue!