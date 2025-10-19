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
        order: [[4, 'desc']], // Sort by created date descending
        columns: [
            { data: 'name' },
            { data: 'status', render: renderStatusBadge },
            { data: 'progress_percent', render: renderProgress },
            { data: 'total_skus' },
            { data: 'created_at', render: renderDate },
            { data: 'duration_seconds', render: renderDuration },
            { data: null, render: renderRunActions, orderable: false }
        ]
    });

    // Forecast Results Table (initialized but not loaded)
    forecastResultsTable = $('#forecastResultsTable').DataTable({
        pageLength: 100,
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
            { data: null, render: renderResultActions, orderable: false }
        ]
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
}

/**
 * Generate a new forecast via API
 */
async function generateForecast() {
    const formData = {
        forecast_name: $('#forecastName').val(),
        warehouse: $('#warehouse').val(),
        growth_rate: parseFloat($('#growthRate').val()) / 100, // Convert percentage to decimal
        abc_filter: $('#abcFilter').val() || null,
        xyz_filter: null // Could add XYZ filter to UI if needed
    };

    try {
        const response = await fetch(`${API_BASE}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (response.ok) {
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
 * Load forecast results for a specific run
 */
async function viewForecastResults(runId) {
    try {
        currentRunId = runId;

        const response = await fetch(`${API_BASE}/runs/${runId}/results?page=1&page_size=100`);
        const data = await response.json();

        if (response.ok) {
            // Update summary metrics
            updateSummaryMetrics(data.forecasts);

            // Load results into table
            forecastResultsTable.clear();
            forecastResultsTable.rows.add(data.forecasts);
            forecastResultsTable.draw();

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
        } else {
            showError('Failed to load forecast results');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
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
 * Show monthly forecast details in modal with chart
 */
function showMonthlyDetails(forecast) {
    $('#modalSKU').text(`${forecast.sku_id} - ${forecast.description}`);

    // Create monthly data grid
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    let gridHTML = '';

    for (let i = 0; i < 12; i++) {
        const qty = forecast.monthly_qty[i];
        const rev = forecast.monthly_rev[i];
        gridHTML += `
            <div class="month-cell">
                <div class="month-label">${months[i]}</div>
                <div class="month-value">${qty.toLocaleString()}</div>
                <div class="text-muted small">$${rev.toFixed(0)}</div>
            </div>
        `;
    }
    $('#monthlyGrid').html(gridHTML);

    // Create chart
    const ctx = document.getElementById('monthlyForecastChart').getContext('2d');

    // Destroy existing chart if any
    if (monthlyChart) {
        monthlyChart.destroy();
    }

    monthlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: months,
            datasets: [{
                label: 'Forecasted Quantity',
                data: forecast.monthly_qty,
                borderColor: '#007bff',
                backgroundColor: 'rgba(0, 123, 255, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: `12-Month Forecast - ${forecast.sku_id}`
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

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('monthlyDetailsModal'));
    modal.show();
}

/**
 * Cancel a running forecast
 */
async function cancelForecast(runId) {
    if (!confirm('Are you sure you want to cancel this forecast generation?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/runs/${runId}/cancel`, {
            method: 'POST'
        });

        if (response.ok) {
            showSuccess('Forecast cancelled');
            clearInterval(progressInterval);
            $('#currentJobSection').hide();
            loadForecastRuns();
        } else {
            showError('Failed to cancel forecast');
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
function renderStatusBadge(status) {
    const statusClass = getStatusClass(status);
    return `<span class="badge ${statusClass}">${status.toUpperCase()}</span>`;
}

function getStatusClass(status) {
    const classes = {
        'pending': 'status-pending',
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
        html += `<button class="btn btn-sm btn-success" onclick="exportForecastCSV(${row.run_id})">
                    <i class="fas fa-download"></i> Export
                 </button>`;
    } else if (row.status === 'running') {
        html += `<button class="btn btn-sm btn-danger" onclick="cancelForecast(${row.run_id})">
                    <i class="fas fa-times"></i> Cancel
                 </button>`;
    }

    return html;
}

function renderResultActions(data, type, row) {
    return `<button class="btn btn-sm btn-info" onclick='showMonthlyDetails(${JSON.stringify(row)})'>
                <i class="fas fa-calendar-alt"></i> Details
            </button>`;
}

function renderCurrency(value) {
    return '$' + parseFloat(value).toLocaleString(undefined, {minimumFractionDigits: 2});
}

function renderConfidence(score) {
    const percent = (score * 100).toFixed(0) + '%';
    const color = score >= 0.75 ? 'confidence-high' : score >= 0.50 ? 'confidence-medium' : 'confidence-low';
    return `<span class="${color}">${percent}</span>`;
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
