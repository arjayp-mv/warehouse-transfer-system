/**
 * 12-Month Sales Forecasting Dashboard - Frontend Logic
 *
 * Handles:
 * - Forecast generation via background jobs
 * - Real-time progress tracking with polling
 * - Paginated results display with DataTables
 * - Monthly forecast visualization with Chart.js
 * - CSV export functionality
 *
 * Performance: Follows best practices with pagination and caching
 */

const API_BASE = '/api/forecasts';
let currentRunId = null;
let progressInterval = null;
let forecastRunsTable = null;
let forecastResultsTable = null;
let monthlyChart = null;
let currentPage = 1;
let totalPages = 1;
let monthLabels = [];

// Initialize on page load
$(document).ready(function() {
    initializeTables();
    loadForecastRuns();
    setupEventHandlers();
});

/**
 * Initialize DataTables for forecast runs and results
 */
function initializeTables() {
    // Forecast Runs Table
    forecastRunsTable = $('#forecastRunsTable').DataTable({
        pageLength: 10,
        order: [[5, 'desc']], // Sort by created date descending (shifted by 1 for checkbox column)
        columns: [
            {
                data: null,
                render: renderCheckbox,
                orderable: false,
                className: 'select-checkbox'
            },
            { data: 'name' },
            { data: 'status', render: renderStatusBadge },
            { data: 'progress_percent', render: renderProgress },
            { data: 'total_skus' },
            {
                data: 'created_at',
                render: function(data, type, row) {
                    // Use raw ISO timestamp for sorting, formatted date for display
                    if (type === 'sort' || type === 'type') {
                        return data || '';
                    }
                    return renderDate(data);
                }
            },
            { data: 'duration_seconds', render: renderDuration },
            { data: null, render: renderRunActions, orderable: false }
        ]
    });

    // Forecast Results Table (initialized but not loaded)
    forecastResultsTable = $('#forecastResultsTable').DataTable({
        pageLength: 100,
        searching: false, // Disable client-side search (using server-side)
        order: [[4, 'desc']], // Sort by total quantity descending
        columns: [
            { data: 'sku_id' },
            { data: 'description' },
            { data: 'abc_code' },
            { data: 'xyz_code' },
            { data: 'total_qty_forecast', render: $.fn.dataTable.render.number(',', '.', 0) },
            { data: 'total_rev_forecast', render: renderCurrency },
            { data: 'confidence_score', render: renderConfidence },
            { data: 'method_used' },
            { data: null, render: renderGrowthRate, orderable: false },
            { data: null, render: renderResultActions, orderable: false }
        ]
    });

    // Add event delegation for details buttons (fixes CSC-R55 issue)
    // Using row index instead of inline JSON to avoid special character issues
    $('#forecastResultsTable tbody').on('click', 'button[data-row-index]', function() {
        const rowIndex = $(this).data('row-index');
        const rowData = forecastResultsTable.row(rowIndex).data();
        showMonthlyDetails(rowData);
    });
}

/**
 * Setup event handlers for user interactions
 */
function setupEventHandlers() {
    // Generate Forecast Form
    $('#generateForecastForm').on('submit', function(e) {
        e.preventDefault();
        generateForecast();
    });

    // Cancel Job Button
    $('#cancelJobBtn').on('click', function() {
        if (currentRunId) {
            cancelForecast(currentRunId);
        }
    });

    // Close Results Button
    $('#closeResultsBtn').on('click', function() {
        $('#resultsSection').hide();
    });

    // Export CSV Button
    $('#exportCsvBtn').on('click', function() {
        if (currentRunId) {
            exportForecastCSV(currentRunId);
        }
    });

    // Pagination buttons
    $('#prevPageBtn').on('click', function() {
        if (currentPage > 1) {
            loadResultsPage(currentRunId, currentPage - 1);
        }
    });

    $('#nextPageBtn').on('click', function() {
        if (currentPage < totalPages) {
            loadResultsPage(currentRunId, currentPage + 1);
        }
    });

    // Search input with debouncing (wait 500ms after user stops typing)
    let searchTimeout = null;
    $('#resultsSearchInput').on('input', function() {
        clearTimeout(searchTimeout);
        const searchTerm = $(this).val().trim();

        searchTimeout = setTimeout(function() {
            if (currentRunId) {
                searchForecastResults(currentRunId, searchTerm);
            }
        }, 500);
    });

    // Clear search button
    $('#clearSearchBtn').on('click', function() {
        $('#resultsSearchInput').val('');
        if (currentRunId) {
            searchForecastResults(currentRunId, '');
        }
    });

    // V7.3 Phase 4: Queue Forecast Confirmation Button
    $('#confirmQueueBtn').on('click', function() {
        // Close the modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('queueConfirmModal'));
        modal.hide();

        // Show success message
        showSuccess('Forecast queued successfully! It will start when the current job completes.');

        // Reset form
        $('#generateForecastForm')[0].reset();

        // Clear pending run ID
        window.pendingQueuedRunId = null;
    });

    // Initialize status filter
    initializeStatusFilter();
}

/**
 * Initialize status filter dropdown functionality
 */
function initializeStatusFilter() {
    const selectAllCheckbox = document.getElementById('status-select-all');
    const statusCheckboxes = document.querySelectorAll('.status-checkbox');
    const dropdown = document.getElementById('status-filter-dropdown');

    // Handle Select All checkbox
    selectAllCheckbox.addEventListener('change', function() {
        const isChecked = this.checked;
        statusCheckboxes.forEach(checkbox => {
            checkbox.checked = isChecked;
        });
        updateStatusFilterText();
    });

    // Handle individual status checkboxes
    statusCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            updateSelectAllState();
            updateStatusFilterText();
        });
    });

    // Prevent dropdown from closing when clicking checkboxes
    dropdown.addEventListener('click', function(e) {
        e.stopPropagation();
    });

    // Initialize filter text
    updateStatusFilterText();
}

/**
 * Update Select All checkbox state based on individual selections
 */
function updateSelectAllState() {
    const statusCheckboxes = document.querySelectorAll('.status-checkbox');
    const checkedBoxes = document.querySelectorAll('.status-checkbox:checked');
    const selectAllCheckbox = document.getElementById('status-select-all');

    if (checkedBoxes.length === statusCheckboxes.length) {
        selectAllCheckbox.checked = true;
        selectAllCheckbox.indeterminate = false;
    } else if (checkedBoxes.length === 0) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    } else {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = true;
    }
}

/**
 * Update status filter button text based on selections
 */
function updateStatusFilterText() {
    const checkedBoxes = document.querySelectorAll('.status-checkbox:checked');
    const statusFilterText = document.getElementById('statusFilterText');
    const statusCheckboxes = document.querySelectorAll('.status-checkbox');

    if (checkedBoxes.length === 0) {
        statusFilterText.textContent = 'No Statuses';
    } else if (checkedBoxes.length === statusCheckboxes.length) {
        statusFilterText.textContent = 'All Statuses';
    } else {
        const selectedStatuses = Array.from(checkedBoxes).map(cb => cb.value);
        statusFilterText.textContent = selectedStatuses.join(', ');
    }
}

/**
 * Get currently selected status values from the filter
 * @returns {Array<string>} Array of selected status values
 */
function getSelectedStatuses() {
    const checkedBoxes = document.querySelectorAll('.status-checkbox:checked');
    return Array.from(checkedBoxes).map(checkbox => checkbox.value);
}

/**
 * Generate a new forecast via API
 */
async function generateForecast() {
    // Get selected statuses from filter
    const selectedStatuses = getSelectedStatuses();

    // Validate at least one status is selected
    if (selectedStatuses.length === 0) {
        showError('Please select at least one SKU status to forecast');
        return;
    }

    const formData = {
        forecast_name: $('#forecastName').val(),
        warehouse: $('#warehouse').val(),
        growth_rate: parseFloat($('#growthRate').val()) / 100, // Convert percentage to decimal
        abc_filter: $('#abcFilter').val() || null,
        xyz_filter: null, // Could add XYZ filter to UI if needed
        status_filter: selectedStatuses
    };

    try {
        const response = await fetch(`${API_BASE}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        // Debug logging to verify API response
        console.log('Generate Forecast API Response:', data);

        if (response.ok) {
            // V7.3 Phase 4: Check if forecast was queued or started
            if (data.status === 'queued') {
                // Forecast was queued - show confirmation modal
                console.log('Forecast queued at position:', data.queue_position);
                $('#queuePositionText').text(data.queue_position);
                const estimatedWait = `${data.queue_position * 15}-${data.queue_position * 20} minutes`;
                $('#estimatedWaitText').text(estimatedWait);

                // Store run_id for potential cancellation
                window.pendingQueuedRunId = data.run_id;

                // Show modal
                const modal = new bootstrap.Modal(document.getElementById('queueConfirmModal'));
                modal.show();

                // Reload runs table to show queued forecast
                loadForecastRuns();
            } else if (data.status === 'started' || data.status === 'pending') {
                // Forecast started immediately
                console.log('Forecast started immediately with run_id:', data.run_id);
                showSuccess('Forecast generation started!');
                currentRunId = data.run_id;

                // Show progress section and start polling
                $('#currentJobSection').show();
                startProgressPolling(data.run_id);

                // Reload runs table
                loadForecastRuns();

                // Reset form
                $('#generateForecastForm')[0].reset();
            } else {
                // Unexpected status - log warning and show generic success
                console.warn('Unexpected forecast status:', data.status);
                showSuccess('Forecast request processed successfully');
                loadForecastRuns();
            }
        } else {
            showError(data.detail || 'Failed to start forecast generation');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}

/**
 * Start polling for job progress
 */
function startProgressPolling(runId) {
    // Clear any existing interval
    if (progressInterval) {
        clearInterval(progressInterval);
    }

    // Poll every 2 seconds
    progressInterval = setInterval(async () => {
        await updateJobProgress(runId);
    }, 2000);
}

/**
 * Update job progress display
 */
async function updateJobProgress(runId) {
    try {
        const response = await fetch(`${API_BASE}/runs/${runId}`);
        const job = await response.json();

        if (response.ok) {
            // Update progress bar
            const progress = job.progress_percent || 0;
            $('#progressBar').css('width', `${progress}%`).text(`${progress.toFixed(1)}%`);

            // Update progress info
            const info = `
                <strong>${job.name}</strong><br>
                Status: <span class="badge ${getStatusClass(job.status)}">${job.status.toUpperCase()}</span> |
                Processed: ${job.processed_skus}/${job.total_skus} SKUs |
                Failed: ${job.failed_skus}
            `;
            $('#jobProgressInfo').html(info);

            // Stop polling if completed
            if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
                clearInterval(progressInterval);
                progressInterval = null;

                if (job.status === 'completed') {
                    showSuccess('Forecast generation completed!');
                    setTimeout(() => $('#currentJobSection').hide(), 3000);
                } else if (job.status === 'failed') {
                    showError('Forecast generation failed: ' + (job.error_message || 'Unknown error'));
                } else {
                    showWarning('Forecast generation was cancelled');
                    $('#currentJobSection').hide();
                }

                loadForecastRuns(); // Refresh runs table
            }
        }
    } catch (error) {
        console.error('Error updating job progress:', error);
    }
}

/**
 * Load forecast runs list
 */
async function loadForecastRuns() {
    try {
        const response = await fetch(`${API_BASE}/runs?page=1&page_size=50`);
        const runs = await response.json();

        if (response.ok) {
            forecastRunsTable.clear();
            forecastRunsTable.rows.add(runs);
            forecastRunsTable.draw();
        }
    } catch (error) {
        console.error('Error loading forecast runs:', error);
    }
}

/**
 * Load forecast results for a specific run (wrapper for first page)
 */
async function viewForecastResults(runId) {
    currentRunId = runId;
    currentPage = 1;
    await loadResultsPage(runId, 1);
}

/**
 * Search forecast results (server-side search)
 * @param {number} runId - Forecast run ID
 * @param {string} searchTerm - Search query
 */
async function searchForecastResults(runId, searchTerm) {
    try {
        let url = `${API_BASE}/runs/${runId}/results?page=1&page_size=100`;

        if (searchTerm) {
            url += `&search=${encodeURIComponent(searchTerm)}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        if (response.ok) {
            // Store month labels if available
            if (data.month_labels && data.month_labels.length > 0) {
                monthLabels = data.month_labels;
            }

            // Load results into table
            forecastResultsTable.clear();
            forecastResultsTable.rows.add(data.forecasts);
            forecastResultsTable.draw();

            // Update pagination controls
            currentPage = data.pagination.page;
            totalPages = data.pagination.total_pages;
            updatePaginationControls();

            // Show result count
            if (searchTerm) {
                showSuccess(`Found ${data.pagination.total_count} matching SKU(s)`);
            }
        } else {
            showError('Failed to search forecast results');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}

/**
 * Load a specific page of forecast results
 * @param {number} runId - Forecast run ID
 * @param {number} page - Page number to load
 */
async function loadResultsPage(runId, page) {
    try {
        // Check if search is active
        const searchTerm = $('#resultsSearchInput').val().trim();
        let url = `${API_BASE}/runs/${runId}/results?page=${page}&page_size=100`;

        if (searchTerm) {
            url += `&search=${encodeURIComponent(searchTerm)}`;
        }

        const response = await fetch(url);
        const data = await response.json();

        if (response.ok) {
            // Store month labels if available
            if (data.month_labels && data.month_labels.length > 0) {
                monthLabels = data.month_labels;
            }

            // Update summary metrics (only on first page)
            if (page === 1) {
                updateSummaryMetrics(data.forecasts);

                // Get forecast run info
                const runResponse = await fetch(`${API_BASE}/runs/${runId}`);
                const runInfo = await runResponse.json();
                $('#resultsForecastName').text(runInfo.name);

                // Show results section
                $('#resultsSection').show();

                // Scroll to results
                $('html, body').animate({
                    scrollTop: $('#resultsSection').offset().top - 20
                }, 500);
            }

            // Load results into table
            forecastResultsTable.clear();
            forecastResultsTable.rows.add(data.forecasts);
            forecastResultsTable.draw();

            // Update pagination controls
            currentPage = page;
            totalPages = data.pagination.total_pages;
            updatePaginationControls();

        } else {
            showError('Failed to load forecast results');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}

/**
 * Update pagination button states and display
 */
function updatePaginationControls() {
    // Update page display
    $('#currentPageDisplay').text(currentPage);
    $('#totalPagesDisplay').text(totalPages);

    // Update button states
    $('#prevPageBtn').prop('disabled', currentPage === 1);
    $('#nextPageBtn').prop('disabled', currentPage === totalPages);

    // Show/hide pagination controls
    if (totalPages > 1) {
        $('#paginationControls').show();
    } else {
        $('#paginationControls').hide();
    }
}

/**
 * Update summary metrics from forecast data
 */
function updateSummaryMetrics(forecasts) {
    const totalSKUs = forecasts.length;
    const totalQty = forecasts.reduce((sum, f) => sum + f.total_qty_forecast, 0);
    const totalRev = forecasts.reduce((sum, f) => sum + f.total_rev_forecast, 0);
    const avgConfidence = forecasts.reduce((sum, f) => sum + f.confidence_score, 0) / totalSKUs;

    $('#summaryTotalSKUs').text(totalSKUs.toLocaleString());
    $('#summaryTotalQty').text(totalQty.toLocaleString());
    $('#summaryTotalRevenue').text('$' + totalRev.toLocaleString(undefined, {minimumFractionDigits: 2}));
    $('#summaryAvgConfidence').text((avgConfidence * 100).toFixed(1) + '%');
}

/**
 * Format month label from YYYY-MM format to short display format
 * @param {string} monthStr - Month in YYYY-MM format (e.g., "2024-10")
 * @returns {string} Formatted month (e.g., "Oct 2024")
 */
function formatMonthLabel(monthStr) {
    if (!monthStr) return '';
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const [year, month] = monthStr.split('-');
    const monthIndex = parseInt(month) - 1;
    return `${monthNames[monthIndex]} ${year}`;
}

/**
 * Show monthly forecast details in modal with chart and historical comparison
 */
async function showMonthlyDetails(forecast) {
    $('#modalSKU').text(`${forecast.sku_id} - ${forecast.description}`);

    // Generate month labels from stored API data or use defaults
    const formattedMonths = monthLabels.length > 0
        ? monthLabels.map(m => formatMonthLabel(m))
        : ['Month 1', 'Month 2', 'Month 3', 'Month 4', 'Month 5', 'Month 6',
           'Month 7', 'Month 8', 'Month 9', 'Month 10', 'Month 11', 'Month 12'];

    // Show modal first with loading indicator
    const modal = new bootstrap.Modal(document.getElementById('monthlyDetailsModal'));
    modal.show();

    // Show loading state
    $('#monthlyGrid').html('<div class="text-center p-3"><i class="fas fa-spinner fa-spin"></i> Loading historical data...</div>');

    // Fetch historical data
    let historicalData = null;
    try {
        const response = await fetch(`${API_BASE}/runs/${currentRunId}/historical/${forecast.sku_id}`);
        if (response.ok) {
            historicalData = await response.json();
        }
    } catch (error) {
        console.error('Failed to fetch historical data:', error);
    }

    // Create monthly data grid with historical comparison
    let gridHTML = '';
    for (let i = 0; i < 12; i++) {
        const forecastQty = forecast.monthly_qty[i];
        const forecastRev = forecast.monthly_rev[i];

        // Get corresponding historical data if available
        let historyInfo = '';
        if (historicalData && historicalData.quantities && historicalData.quantities[i] !== undefined) {
            const histQty = historicalData.quantities[i];
            const histRev = historicalData.revenues[i];
            const historicalMonth = historicalData.months[i] ? formatMonthLabel(historicalData.months[i]) : '';
            historyInfo = `
                <div class="text-muted small" style="border-top: 1px solid #dee2e6; margin-top: 4px; padding-top: 4px;">
                    <strong>${historicalMonth}</strong><br>
                    ${histQty.toLocaleString()} units<br>
                    $${histRev.toFixed(0)}
                </div>
            `;
        }

        gridHTML += `
            <div class="month-cell">
                <div class="month-label">${formattedMonths[i]}</div>
                <div class="month-value">${forecastQty.toLocaleString()}</div>
                <div class="text-muted small">$${forecastRev.toFixed(0)}</div>
                ${historyInfo}
            </div>
        `;
    }
    $('#monthlyGrid').html(gridHTML);

    // Create chart with historical and forecast datasets
    const ctx = document.getElementById('monthlyForecastChart').getContext('2d');

    // Destroy existing chart if any
    if (monthlyChart) {
        monthlyChart.destroy();
    }

    // Prepare datasets
    const datasets = [{
        label: 'Forecast',
        data: forecast.monthly_qty,
        borderColor: '#007bff',
        backgroundColor: 'rgba(0, 123, 255, 0.1)',
        tension: 0.4,
        fill: true
    }];

    // Add historical dataset if available
    if (historicalData && historicalData.quantities && historicalData.quantities.length > 0) {
        datasets.unshift({
            label: 'Historical (Last Year)',
            data: historicalData.quantities,
            borderColor: '#fd7e14',
            backgroundColor: 'rgba(253, 126, 20, 0.1)',
            tension: 0.4,
            fill: true,
            borderDash: [5, 5]
        });
    }

    // Determine forecast period for chart title
    const forecastPeriod = monthLabels.length > 0
        ? `${formattedMonths[0]} - ${formattedMonths[11]}`
        : '12-Month Forecast';

    monthlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: formattedMonths,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: `${forecast.sku_id} - ${forecastPeriod}`
                },
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return value.toLocaleString();
                        }
                    }
                }
            }
        }
    });
}

/**
 * Cancel a pending, running, or queued forecast
 * @param {number} runId - The forecast run ID to cancel
 * @param {string} status - The current status ('pending', 'running', or 'queued')
 */
async function cancelForecast(runId, status) {
    let confirmMessage;
    if (status === 'queued') {
        confirmMessage = 'Are you sure you want to remove this forecast from the queue?';
    } else if (status === 'pending') {
        confirmMessage = 'Are you sure you want to cancel this pending forecast?';
    } else {
        confirmMessage = 'Are you sure you want to cancel this forecast generation?';
    }

    if (!confirm(confirmMessage)) {
        return;
    }

    try {
        // Use different endpoints for running/pending vs queued forecasts
        const endpoint = status === 'queued'
            ? `${API_BASE}/queue/${runId}`  // DELETE /api/forecasts/queue/{run_id}
            : `${API_BASE}/runs/${runId}/cancel`;  // POST /api/forecasts/runs/{run_id}/cancel

        const method = status === 'queued' ? 'DELETE' : 'POST';

        const response = await fetch(endpoint, { method });

        if (response.ok) {
            const data = await response.json();
            showSuccess(data.message || 'Forecast cancelled successfully');

            // Clear progress polling if canceling running forecast
            if (status === 'running') {
                clearInterval(progressInterval);
                $('#currentJobSection').hide();
            }

            loadForecastRuns();
        } else {
            const errorData = await response.json().catch(() => ({}));
            showError(errorData.detail || 'Failed to cancel forecast');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}

/**
 * Bulk delete selected forecasts
 * Includes safety confirmations for recent forecasts and large batches
 */
async function bulkDeleteForecasts() {
    const checked = document.querySelectorAll('.forecast-checkbox:checked');
    const runIds = Array.from(checked).map(cb => parseInt(cb.dataset.runId));

    if (runIds.length === 0) {
        showError('No forecasts selected');
        return;
    }

    // Get forecast data to check for recent forecasts
    const forecastData = [];
    forecastRunsTable.rows().every(function() {
        const data = this.data();
        if (runIds.includes(data.run_id)) {
            forecastData.push(data);
        }
    });

    // Check for recent forecasts (<7 days old)
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const recentForecasts = forecastData.filter(f => {
        const createdDate = new Date(f.created_at);
        return createdDate > sevenDaysAgo;
    });

    // Enhanced confirmation for recent forecasts
    if (recentForecasts.length > 0) {
        const recentNames = recentForecasts.map(f => f.name).join(', ');
        const confirmMsg = `WARNING: ${recentForecasts.length} of the selected forecast(s) were created within the last 7 days:\n\n${recentNames}\n\nAre you sure you want to delete these recent forecasts?`;
        if (!confirm(confirmMsg)) {
            return;
        }
    }

    // For large batches (>=10), require typing "DELETE"
    if (runIds.length >= 10) {
        const userInput = prompt(`You are about to delete ${runIds.length} forecasts.\n\nTo confirm this bulk deletion, please type DELETE (in capital letters):`);
        if (userInput !== 'DELETE') {
            showError('Bulk deletion cancelled. You must type "DELETE" to confirm.');
            return;
        }
    } else {
        // Simple confirmation for smaller batches
        const confirmMsg = `Are you sure you want to delete ${runIds.length} forecast(s)?\nThis action cannot be undone.`;
        if (!confirm(confirmMsg)) {
            return;
        }
    }

    try {
        const response = await fetch(`${API_BASE}/runs/bulk-delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(runIds)
        });

        if (response.ok) {
            const data = await response.json();
            showSuccess(data.message || `Successfully deleted ${data.deleted_count} forecast(s)`);

            // Clear selections and reload table
            document.getElementById('selectAllCheckbox').checked = false;
            updateBulkDeleteButton();
            loadForecastRuns();
        } else {
            const errorData = await response.json().catch(() => ({}));
            if (errorData.detail && errorData.detail.blocked) {
                // Show detailed error for blocked forecasts
                const blockedNames = errorData.detail.blocked.map(b => b.name).join(', ');
                showError(`Cannot delete running/queued forecasts: ${blockedNames}`);
            } else {
                showError(errorData.detail || 'Failed to delete forecasts');
            }
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}

/**
 * Export forecast to CSV
 */
function exportForecastCSV(runId) {
    window.location.href = `${API_BASE}/runs/${runId}/export`;
}

// Rendering Functions
function renderStatusBadge(status, type, row) {
    const statusClass = getStatusClass(status);

    // V7.3 Phase 4: Show queue position for queued forecasts
    if (status === 'queued' && row && row.queue_position) {
        return `<span class="badge ${statusClass}">QUEUED (Position ${row.queue_position})</span>`;
    }

    return `<span class="badge ${statusClass}">${status.toUpperCase()}</span>`;
}

function getStatusClass(status) {
    const classes = {
        'pending': 'status-pending',
        'queued': 'bg-info',  // V7.3 Phase 4: Blue badge for queued status
        'running': 'status-running',
        'completed': 'status-completed',
        'failed': 'status-failed',
        'cancelled': 'status-cancelled'
    };
    return classes[status] || 'bg-secondary';
}

function renderProgress(progress, type, row) {
    if (row.status === 'completed') return '100%';
    if (row.status === 'pending') return '0%';
    if (row.status === 'queued') return 'Queued';  // V7.3 Phase 4
    return progress.toFixed(1) + '%';
}

function renderDate(dateStr) {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleString();
}

function renderDuration(seconds) {
    if (!seconds) return '-';
    if (seconds < 60) return seconds.toFixed(1) + 's';
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}m ${secs}s`;
}

function renderRunActions(data, type, row) {
    let html = '';

    if (row.status === 'completed') {
        html += `<button class="btn btn-sm btn-primary me-1" onclick="viewForecastResults(${row.run_id})">
                    <i class="fas fa-eye"></i> View
                 </button>`;
        html += `<button class="btn btn-sm btn-success me-1" onclick="exportForecastCSV(${row.run_id})">
                    <i class="fas fa-download"></i> Export
                 </button>`;
        html += `<button class="btn btn-sm btn-warning" onclick="archiveForecast(${row.run_id}, '${row.name}')">
                    <i class="fas fa-archive"></i> Archive
                 </button>`;
    } else if (row.status === 'running') {
        html += `<button class="btn btn-sm btn-danger" onclick="cancelForecast(${row.run_id}, 'running')">
                    <i class="fas fa-times"></i> Cancel
                 </button>`;
    } else if (row.status === 'queued') {
        html += `<button class="btn btn-sm btn-warning" onclick="cancelForecast(${row.run_id}, 'queued')">
                    <i class="fas fa-times"></i> Remove from Queue
                 </button>`;
    } else if (row.status === 'pending') {
        html += `<button class="btn btn-sm btn-secondary" onclick="cancelForecast(${row.run_id}, 'pending')">
                    <i class="fas fa-times"></i> Cancel
                 </button>`;
    } else if (row.status === 'failed' || row.status === 'cancelled') {
        // Show archive button for failed/cancelled forecasts
        html += `<button class="btn btn-sm btn-warning" onclick="archiveForecast(${row.run_id}, '${row.name}')">
                    <i class="fas fa-archive"></i> Archive
                 </button>`;
    }

    return html;
}

function renderCheckbox(data, type, row) {
    // Don't show checkbox for running or queued forecasts
    if (row.status === 'running' || row.status === 'queued') {
        return '';
    }
    return `<input type="checkbox" class="forecast-checkbox" data-run-id="${row.run_id}" onchange="updateBulkDeleteButton()">`;
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAllCheckbox');
    const checkboxes = document.querySelectorAll('.forecast-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
    });
    updateBulkDeleteButton();
}

function updateBulkDeleteButton() {
    const checked = document.querySelectorAll('.forecast-checkbox:checked');
    const count = checked.length;
    const deleteBtn = document.getElementById('bulkDeleteBtn');
    const archiveBtn = document.getElementById('bulkArchiveBtn');
    const countSpan = document.getElementById('selectedCount');
    const archiveCountSpan = document.getElementById('selectedArchiveCount');

    if (count > 0) {
        deleteBtn.style.display = 'inline-block';
        archiveBtn.style.display = 'inline-block';
        countSpan.textContent = count;
        archiveCountSpan.textContent = count;
    } else {
        deleteBtn.style.display = 'none';
        archiveBtn.style.display = 'none';
        document.getElementById('selectAllCheckbox').checked = false;
    }
}

function renderResultActions(data, type, row, meta) {
    // Use row index to avoid JSON.stringify issues with special characters
    // This fixes the CSC-R55 details button issue where descriptions with quotes broke the onclick
    return `<button class="btn btn-sm btn-info" data-row-index="${meta.row}">
                <i class="fas fa-calendar-alt"></i> Details
            </button>`;
}

function renderCurrency(value) {
    return '$' + parseFloat(value).toLocaleString(undefined, {minimumFractionDigits: 2});
}

function renderConfidence(score) {
    const percent = (score * 100).toFixed(0) + '%';
    const color = score >= 0.75 ? 'confidence-high' : score >= 0.50 ? 'confidence-medium' : 'confidence-low';

    // Add warning icon for low confidence (new SKUs or insufficient data)
    if (score < 0.50) {
        return `<span class="${color}" title="Low confidence - New SKU or insufficient historical data">
                    <i class="fas fa-exclamation-triangle me-1"></i>${percent}
                </span>`;
    }

    return `<span class="${color}">${percent}</span>`;
}

function renderGrowthRate(data, type, row) {
    const rate = row.growth_rate_applied || 0;
    const source = row.growth_rate_source || 'default';

    // Format percentage
    const ratePercent = (rate * 100).toFixed(1) + '%';

    // Determine color and icon based on rate
    let rateColor = 'text-secondary';
    let rateIcon = 'fa-minus';
    if (rate > 0.05) {
        rateColor = 'text-success';
        rateIcon = 'fa-arrow-trend-up';
    } else if (rate < -0.05) {
        rateColor = 'text-danger';
        rateIcon = 'fa-arrow-trend-down';
    }

    // Source badge and tooltip
    let sourceBadge = '';
    let sourceTooltip = '';
    let sourceBadgeClass = 'bg-secondary';

    switch(source) {
        case 'manual_override':
            sourceBadge = 'Manual';
            sourceTooltip = 'User-specified growth rate';
            sourceBadgeClass = 'bg-primary';
            break;
        case 'sku_trend':
            sourceBadge = 'Auto';
            sourceTooltip = 'Calculated from SKU historical trend using weighted regression';
            sourceBadgeClass = 'bg-success';
            break;
        case 'category_trend':
            sourceBadge = 'Category';
            sourceTooltip = 'Insufficient SKU data - using category average trend';
            sourceBadgeClass = 'bg-warning text-dark';
            break;
        case 'growth_status':
            sourceBadge = 'Status';
            sourceTooltip = 'Applied from SKU growth status (viral/declining)';
            sourceBadgeClass = 'bg-info';
            break;
        case 'default':
            sourceBadge = 'Default';
            sourceTooltip = 'No data available - using 0% growth';
            sourceBadgeClass = 'bg-secondary';
            break;
    }

    return `<span class="${rateColor}" title="${sourceTooltip}">
                <i class="fas ${rateIcon} me-1"></i>${ratePercent}
                <span class="badge ${sourceBadgeClass} ms-1" style="font-size: 0.7rem;">${sourceBadge}</span>
            </span>`;
}

// Notification Functions
function showSuccess(message) {
    showNotification(message, 'success');
}

function showError(message) {
    showNotification(message, 'danger');
}

function showWarning(message) {
    showNotification(message, 'warning');
}

function showNotification(message, type) {
    const alertHTML = `
        <div class="alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3"
             style="z-index: 9999; max-width: 500px;" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    $('body').append(alertHTML);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        $('.alert').alert('close');
    }, 5000);
}

/**
 * Archive single forecast
 * Moves forecast to archive view (hidden from main list)
 */
async function archiveForecast(runId, name) {
    if (!confirm(`Archive "${name}"?\n\nArchived forecasts can be restored from the Archive page.`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/runs/${runId}/archive`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();
            showSuccess(data.message || 'Forecast archived successfully');
            loadForecastRuns();
        } else {
            const errorData = await response.json().catch(() => ({}));
            showError(errorData.detail || 'Failed to archive forecast');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}

/**
 * Bulk archive forecasts with safety confirmations
 * Same safety rules as bulk delete (warn for recent, require typing for 10+)
 */
async function bulkArchiveForecasts() {
    const checked = document.querySelectorAll('.forecast-checkbox:checked');
    const runIds = Array.from(checked).map(cb => parseInt(cb.dataset.runId));

    if (runIds.length === 0) {
        showError('No forecasts selected');
        return;
    }

    // Get forecast data to check for recent forecasts
    const forecastData = [];
    forecastRunsTable.rows().every(function() {
        const data = this.data();
        if (runIds.includes(data.run_id)) {
            forecastData.push(data);
        }
    });

    // Check for recent forecasts (<7 days old)
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const recentForecasts = forecastData.filter(f => {
        const createdDate = new Date(f.created_at);
        return createdDate > sevenDaysAgo;
    });

    // Enhanced confirmation for recent forecasts
    if (recentForecasts.length > 0) {
        const recentNames = recentForecasts.map(f => f.name).join(', ');
        const confirmMsg = `WARNING: ${recentForecasts.length} of the selected forecast(s) were created within the last 7 days:\n\n${recentNames}\n\nAre you sure you want to archive these recent forecasts?`;
        if (!confirm(confirmMsg)) {
            return;
        }
    }

    // For large batches (>=10), require typing "ARCHIVE"
    if (runIds.length >= 10) {
        const userInput = prompt(`You are about to archive ${runIds.length} forecasts.\n\nTo confirm this bulk archive, please type ARCHIVE (in capital letters):`);
        if (userInput !== 'ARCHIVE') {
            showError('Bulk archive cancelled. You must type "ARCHIVE" to confirm.');
            return;
        }
    } else {
        // Simple confirmation for smaller batches
        const confirmMsg = `Are you sure you want to archive ${runIds.length} forecast(s)?\n\nYou can restore them later from the Archive page.`;
        if (!confirm(confirmMsg)) {
            return;
        }
    }

    try {
        const response = await fetch(`${API_BASE}/runs/bulk-archive`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(runIds)
        });

        if (response.ok) {
            const data = await response.json();
            showSuccess(data.message || `Successfully archived ${data.archived_count} forecast(s)`);

            // Clear selections and reload table
            document.getElementById('selectAllCheckbox').checked = false;
            updateBulkDeleteButton();
            loadForecastRuns();
        } else {
            const errorData = await response.json().catch(() => ({}));
            if (errorData.detail && errorData.detail.blocked) {
                const blockedNames = errorData.detail.blocked.map(b => b.name).join(', ');
                showError(`Cannot archive running/queued forecasts: ${blockedNames}`);
            } else {
                showError(errorData.detail || 'Failed to archive forecasts');
            }
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    }
}
