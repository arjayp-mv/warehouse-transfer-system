/**
 * Supplier Ordering JavaScript Module
 * Handles API calls, data updates, and UI interactions for the monthly supplier ordering system
 */

// Global variables
let ordersTable = null;
let currentOrderMonth = null;
let searchDebounceTimer = null;

/**
 * Initialize the page when DOM is ready
 */
document.addEventListener('DOMContentLoaded', function() {
    // Set default month to current month
    const today = new Date();
    const currentMonth = today.toISOString().substring(0, 7);
    document.getElementById('order-month-select').value = currentMonth;
    currentOrderMonth = currentMonth;

    // Initialize DataTable
    initializeDataTable();

    // Load recommendations
    loadOrderRecommendations();

    // Setup search box with debounce (uses DataTables built-in search which triggers server-side filtering)
    const searchBox = document.getElementById('search-box');
    if (searchBox) {
        searchBox.addEventListener('input', function() {
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                ordersTable.search(this.value).draw();
            }, 300);
        });
    }

    // Setup filter dropdowns to trigger server-side filtering
    const warehouseFilter = document.getElementById('warehouse-filter');
    const supplierFilter = document.getElementById('supplier-filter');
    const urgencyFilter = document.getElementById('urgency-filter');

    if (warehouseFilter) {
        warehouseFilter.addEventListener('change', function() {
            ordersTable.ajax.reload();
        });
    }

    if (supplierFilter) {
        supplierFilter.addEventListener('change', function() {
            ordersTable.ajax.reload();
        });
    }

    if (urgencyFilter) {
        urgencyFilter.addEventListener('change', function() {
            ordersTable.ajax.reload();
        });
    }

    // Month selector change handler
    document.getElementById('order-month-select').addEventListener('change', function() {
        currentOrderMonth = this.value;
        loadOrderRecommendations();
    });
});

/**
 * Initialize DataTables with server-side processing configuration
 */
function initializeDataTable() {
    ordersTable = $('#orders-table').DataTable({
        serverSide: true,
        processing: true,
        pageLength: 50,
        ajax: function(data, callback, settings) {
            // Build the URL with current month
            const url = `/api/supplier-orders/${currentOrderMonth}`;

            // Map DataTables parameters to backend API format
            const params = new URLSearchParams({
                page: Math.floor(data.start / data.length) + 1,
                page_size: data.length,
                sort_by: data.order && data.order[0] ? getColumnName(data.order[0].column) : 'urgency_level',
                sort_order: data.order && data.order[0] ? data.order[0].dir : 'desc'
            });

            // Add optional filters
            const warehouse = $('#warehouse-filter').val();
            const supplier = $('#supplier-filter').val();
            const urgency = $('#urgency-filter').val();
            const search = data.search.value;

            if (warehouse) params.append('warehouse', warehouse);
            if (supplier) params.append('supplier', supplier);
            if (urgency) params.append('urgency', urgency);
            if (search) params.append('search', search);

            // Fetch data from backend
            fetch(`${url}?${params.toString()}`)
                .then(response => response.json())
                .then(json => {
                    // Update summary cards
                    if (json.summary) {
                        updateSummaryCards(json.summary);
                    }

                    // Return data to DataTables
                    callback({
                        draw: data.draw,
                        recordsTotal: json.recordsTotal || json.total,
                        recordsFiltered: json.recordsFiltered || json.total,
                        data: json.orders || []
                    });
                })
                .catch(error => {
                    console.error('Error loading orders:', error);
                    showError('Failed to load recommendations');
                    callback({
                        draw: data.draw,
                        recordsTotal: 0,
                        recordsFiltered: 0,
                        data: []
                    });
                });
        },
        columns: [
            { data: 'sku_id', render: function(data, type, row) {
                return `<span class="sku-link" onclick="openSKUDetailsModal('${data}', '${row.warehouse}')">${data}</span>`;
            }},
            { data: 'description' },
            { data: 'warehouse', render: function(data) {
                return data.charAt(0).toUpperCase() + data.slice(1);
            }},
            { data: 'supplier' },
            { data: 'current_inventory' },
            { data: 'pending_orders_effective' },
            { data: 'suggested_qty' },
            { data: null, render: function(data, type, row) {
                return createEditableQtyField(row);
            }},
            { data: null, render: function(data, type, row) {
                return createEditableLeadTimeField(row);
            }},
            { data: null, render: function(data, type, row) {
                return createEditableArrivalField(row);
            }},
            { data: 'coverage_months', render: function(data) {
                return data ? data.toFixed(1) : '--';
            }},
            { data: 'urgency_level', render: function(data) {
                return createUrgencyBadge(data);
            }},
            { data: null, render: function(data, type, row) {
                return createActionButtons(row);
            }}
        ],
        columnDefs: [
            { targets: [7, 8, 9, 12], orderable: false } // Editable and action columns
        ],
        order: [[11, 'desc'], [10, 'desc']], // Sort by urgency desc, then coverage desc
        language: {
            emptyTable: "No orders to display. Generate recommendations to get started.",
            zeroRecords: "No matching orders found",
            processing: "Loading recommendations..."
        },
        createdRow: function(row, data) {
            // Apply urgency class to the row
            $(row).addClass(`urgency-${data.urgency_level}`);
        }
    });
}

/**
 * Map DataTables column index to backend column name
 * @param {number} columnIndex - DataTables column index
 * @returns {string} Backend column name
 */
function getColumnName(columnIndex) {
    const columnMap = {
        0: 'sku_id',
        1: 'description',
        2: 'warehouse',
        3: 'supplier',
        4: 'current_inventory',
        5: 'effective_pending',
        6: 'suggested_qty',
        10: 'coverage_months',
        11: 'urgency_level'
    };
    return columnMap[columnIndex] || 'urgency_level';
}

/**
 * Load order recommendations metadata (summary and supplier list)
 * DataTables handles loading the actual table data via server-side processing
 * @returns {Promise<void>}
 */
async function loadOrderRecommendations() {
    try {
        // Get summary and supplier list (lightweight call for metadata only)
        const params = new URLSearchParams({
            order_month: currentOrderMonth,
            page: 1,
            page_size: 1  // Just need summary, not actual data
        });

        const response = await fetch(`/api/supplier-orders/${currentOrderMonth}?${params}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Update summary cards
        updateSummaryCards(data.summary || {});

        // Populate supplier filter from all orders (need separate API or fetch once)
        await loadSupplierFilterOptions();

        // Reload DataTables to fetch data for current month
        if (ordersTable) {
            ordersTable.ajax.reload();
        }

    } catch (error) {
        console.error('Failed to load order recommendations:', error);
        showError('Unable to load order recommendations. Please try again.');
    }
}

/**
 * Load unique suppliers for the current order month to populate filter dropdown
 * @returns {Promise<void>}
 */
async function loadSupplierFilterOptions() {
    try {
        // Fetch one page with large size to get all unique suppliers
        // This is a temporary solution - ideally should be a separate endpoint
        const params = new URLSearchParams({
            order_month: currentOrderMonth,
            page: 1,
            page_size: 5000  // Get all to extract unique suppliers
        });

        const response = await fetch(`/api/supplier-orders/${currentOrderMonth}?${params}`);

        if (!response.ok) {
            return; // Fail silently for filter population
        }

        const data = await response.json();
        const orders = data.orders || [];
        const suppliers = [...new Set(orders.map(o => o.supplier))].sort();

        const select = document.getElementById('supplier-filter');
        select.innerHTML = '<option value="">All Suppliers</option>';

        suppliers.forEach(supplier => {
            const option = document.createElement('option');
            option.value = supplier;
            option.textContent = supplier;
            select.appendChild(option);
        });

    } catch (error) {
        console.error('Failed to load supplier options:', error);
    }
}

/**
 * Generate monthly recommendations by calling the backend API
 * @returns {Promise<void>}
 */
async function generateRecommendations() {
    const confirmed = confirm(`Generate new recommendations for ${currentOrderMonth}? This may take a few minutes for 2000+ SKUs.`);

    if (!confirmed) {
        return;
    }

    try {
        showLoading('Generating recommendations... This may take a few minutes.');

        const response = await fetch('/api/supplier-orders/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                order_month: currentOrderMonth
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();

        showSuccess(`Successfully generated ${result.recommendations_generated} recommendations`);
        await loadOrderRecommendations();

    } catch (error) {
        console.error('Failed to generate recommendations:', error);
        showError('Unable to generate recommendations. Please try again.');
    } finally {
        hideLoading();
    }
}

// populateTable() function removed - DataTables server-side processing handles table population via column.render functions

/**
 * Create editable confirmed quantity field
 * @param {Object} order - Order object
 * @returns {string} HTML for editable quantity field
 */
function createEditableQtyField(order) {
    const disabled = order.is_locked ? 'disabled' : '';
    return `<input type="number"
                   class="editable-qty"
                   value="${order.confirmed_qty || order.suggested_qty}"
                   min="0"
                   ${disabled}
                   onchange="saveOrderChanges(${order.id}, 'confirmed_qty', this.value)"
                   data-order-id="${order.id}">`;
}

/**
 * Create editable lead time field
 * @param {Object} order - Order object
 * @returns {string} HTML for editable lead time field
 */
function createEditableLeadTimeField(order) {
    const disabled = order.is_locked ? 'disabled' : '';
    return `<input type="number"
                   class="editable-qty"
                   value="${order.lead_time_days_override || order.lead_time_days}"
                   min="1"
                   ${disabled}
                   onchange="saveOrderChanges(${order.id}, 'lead_time_days_override', this.value)"
                   data-order-id="${order.id}">`;
}

/**
 * Create editable expected arrival date field
 * @param {Object} order - Order object
 * @returns {string} HTML for editable arrival date field
 */
function createEditableArrivalField(order) {
    const disabled = order.is_locked ? 'disabled' : '';
    const date = order.expected_arrival ? order.expected_arrival.substring(0, 10) : '';
    return `<input type="date"
                   class="editable-date"
                   value="${date}"
                   ${disabled}
                   onchange="saveOrderChanges(${order.id}, 'expected_arrival', this.value)"
                   data-order-id="${order.id}">`;
}

/**
 * Create urgency badge HTML
 * @param {string} urgency - Urgency level
 * @returns {string} HTML for urgency badge
 */
function createUrgencyBadge(urgency) {
    const labels = {
        'must_order': 'Must Order',
        'should_order': 'Should Order',
        'optional': 'Optional',
        'skip': 'Skip'
    };
    return `<span class="badge urgency-${urgency}">${labels[urgency] || urgency}</span>`;
}

/**
 * Create action buttons for each row
 * @param {Object} order - Order object
 * @returns {string} HTML for action buttons
 */
function createActionButtons(order) {
    const lockIcon = order.is_locked ? 'fa-lock' : 'fa-lock-open';
    const lockClass = order.is_locked ? 'locked' : '';

    return `<button class="lock-btn ${lockClass}"
                    onclick="toggleLock(${order.id}, ${order.is_locked})"
                    title="${order.is_locked ? 'Unlock order' : 'Lock order'}">
                <i class="fas ${lockIcon}"></i>
            </button>`;
}

/**
 * Save order changes to backend and reload table
 * @param {number} orderId - Order ID
 * @param {string} field - Field name to update
 * @param {string} value - New value
 * @returns {Promise<void>}
 */
async function saveOrderChanges(orderId, field, value) {
    try {
        const response = await fetch(`/api/supplier-orders/${orderId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                [field]: value
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Reload DataTables to get updated coverage calculations
        if (ordersTable) {
            ordersTable.ajax.reload(null, false); // false = stay on current page
        }

    } catch (error) {
        console.error('Failed to save changes:', error);
        showError('Unable to save changes. Please try again.');

        // Reload to revert changes
        if (ordersTable) {
            ordersTable.ajax.reload(null, false);
        }
    }
}

/**
 * Toggle lock status for an order
 * @param {number} orderId - Order ID
 * @param {boolean} currentlyLocked - Current lock status
 * @returns {Promise<void>}
 */
async function toggleLock(orderId, currentlyLocked) {
    const action = currentlyLocked ? 'unlock' : 'lock';

    try {
        const response = await fetch(`/api/supplier-orders/${orderId}/${action}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP error! status: ${response.status}`);
        }

        showSuccess(`Order ${action}ed successfully`);
        await loadOrderRecommendations();

    } catch (error) {
        console.error(`Failed to ${action} order:`, error);
        showError(`Unable to ${action} order: ${error.message}`);
    }
}

// applyFilters() function removed - DataTables server-side processing handles filtering via ajax.data parameters

/**
 * Update summary cards with counts
 * @param {Object} summary - Summary statistics object
 */
function updateSummaryCards(summary) {
    document.getElementById('must-order-count').textContent = summary.must_order || 0;
    document.getElementById('should-order-count').textContent = summary.should_order || 0;
    document.getElementById('optional-count').textContent = summary.optional || 0;
    document.getElementById('skip-count').textContent = summary.skip || 0;
}

// populateSupplierFilter() function removed - replaced by loadSupplierFilterOptions() in Phase 1.2

/**
 * Export orders to Excel
 * @returns {Promise<void>}
 */
async function exportToExcel() {
    try {
        showLoading('Generating Excel file...');

        const response = await fetch(`/api/supplier-orders/${currentOrderMonth}/excel`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `supplier_orders_${currentOrderMonth}.xlsx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showSuccess('Excel file downloaded successfully');

    } catch (error) {
        console.error('Failed to export to Excel:', error);
        showError('Unable to export to Excel. Please try again.');
    } finally {
        hideLoading();
    }
}

/**
 * Export supplier order recommendations to CSV
 * TASK-603: CSV export functionality
 * Fetches CSV from backend API and triggers browser download
 */
async function exportToCSV() {
    try {
        showLoading('Generating CSV file...');

        const response = await fetch(`/api/supplier-orders/${currentOrderMonth}/csv`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `supplier_orders_${currentOrderMonth}.csv`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showSuccess('CSV file downloaded successfully');

    } catch (error) {
        console.error('Failed to export to CSV:', error);
        showError('Unable to export to CSV. Please try again.');
    } finally {
        hideLoading();
    }
}

/**
 * Open SKU details modal with tabbed interface
 * TASK-384: Enhanced with tabs, pending timeline, forecast chart, and stockout history
 * TASK-601: Updated to pass warehouse parameter for API calls
 * V10: Fixed warehouse filtering - clears content and resets state on each open
 * @param {string} skuId - SKU identifier
 * @param {string} warehouse - Warehouse name (burnaby or kentucky)
 */
function openSKUDetailsModal(skuId, warehouse) {
    const modalElement = document.getElementById('sku-details-modal');
    const modal = new bootstrap.Modal(modalElement);
    document.getElementById('skuDetailsModalLabel').textContent = `SKU Details: ${skuId} - ${warehouse.charAt(0).toUpperCase() + warehouse.slice(1)}`;

    // Clear all tab content from previous modal opens to prevent stale data
    document.getElementById('overview-content').innerHTML = '<p class="text-muted">Loading...</p>';
    document.getElementById('pending-content').innerHTML = '<p class="text-muted">Click to load pending orders...</p>';
    document.getElementById('forecast-content').innerHTML = '<p class="text-muted">Click to load forecast data...</p>';
    document.getElementById('stockout-content').innerHTML = '<p class="text-muted">Click to load stockout history...</p>';
    document.getElementById('coverage-timeline-content').innerHTML = '<p class="text-muted">Click to load coverage timeline...</p>';

    // Reset tab button states - make Overview active, others inactive
    document.getElementById('overview-tab').classList.add('active');
    document.getElementById('pending-tab').classList.remove('active');
    document.getElementById('forecast-tab').classList.remove('active');
    document.getElementById('stockout-tab').classList.remove('active');
    document.getElementById('coverage-timeline-tab').classList.remove('active');
    document.getElementById('supplier-performance-tab').classList.remove('active');

    // Reset tab pane states - make Overview visible, others hidden
    document.getElementById('overview').classList.add('show', 'active');
    document.getElementById('pending').classList.remove('show', 'active');
    document.getElementById('forecast').classList.remove('show', 'active');
    document.getElementById('stockout').classList.remove('show', 'active');
    document.getElementById('coverage-timeline').classList.remove('show', 'active');
    document.getElementById('supplier-performance').classList.remove('show', 'active');

    // Destroy any existing chart instances to prevent memory leaks
    if (window.forecastChartInstance) {
        window.forecastChartInstance.destroy();
        window.forecastChartInstance = null;
    }

    // Load overview data immediately
    loadOverviewTab(skuId);

    // Setup tab click event listeners for lazy loading with warehouse-specific data
    document.getElementById('pending-tab').addEventListener('click', () => loadPendingTab(skuId, warehouse), { once: true });
    document.getElementById('forecast-tab').addEventListener('click', () => loadForecastTab(skuId, warehouse), { once: true });
    document.getElementById('stockout-tab').addEventListener('click', () => loadStockoutTab(skuId, warehouse), { once: true });
    document.getElementById('coverage-timeline-tab').addEventListener('click', () => loadCoverageTimelineTab(skuId, warehouse), { once: true });
    document.getElementById('supplier-performance-tab').addEventListener('click', () => loadSupplierPerformanceTab(skuId, warehouse), { once: true });

    // Add cleanup event listener to clear all content when modal is hidden
    // This ensures fresh data load on next modal open
    modalElement.addEventListener('hidden.bs.modal', function cleanupModal() {
        // Clear all tab content
        document.getElementById('overview-content').innerHTML = '';
        document.getElementById('pending-content').innerHTML = '';
        document.getElementById('forecast-content').innerHTML = '';
        document.getElementById('stockout-content').innerHTML = '';
        document.getElementById('coverage-timeline-content').innerHTML = '';
        document.getElementById('supplier-performance-content').innerHTML = '';

        // Destroy chart instance to free memory
        if (window.forecastChartInstance) {
            window.forecastChartInstance.destroy();
            window.forecastChartInstance = null;
        }

        // Remove this event listener after cleanup (once: true alternative)
        modalElement.removeEventListener('hidden.bs.modal', cleanupModal);
    }, { once: true });

    modal.show();
}

/**
 * Load overview tab content
 * @param {string} skuId - SKU identifier
 * @returns {Promise<void>}
 */
async function loadOverviewTab(skuId) {
    try {
        // Fetch order data from backend for this SKU
        const response = await fetch(`/api/supplier-orders/${currentOrderMonth}?search=${skuId}&page_size=1`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const order = data.orders && data.orders.length > 0 ? data.orders[0] : null;

        if (!order) {
            document.getElementById('overview-content').innerHTML = `<p class="text-danger">Order data not found for ${skuId}</p>`;
            return;
        }

        const html = `
            <div class="basic-info-grid">
                <div class="info-card">
                    <h6>Inventory Position</h6>
                    <p><strong>Current Inventory:</strong> ${order.current_inventory || 0}</p>
                    <p><strong>Pending (Effective):</strong> ${order.pending_orders_effective || 0}</p>
                    <p><strong>Total Available:</strong> ${(order.current_inventory || 0) + (order.pending_orders_effective || 0)}</p>
                </div>
                <div class="info-card">
                    <h6>Order Recommendation</h6>
                    <p><strong>Suggested Qty:</strong> ${order.suggested_qty || 0}</p>
                    <p><strong>Confirmed Qty:</strong> ${order.confirmed_qty || 0}</p>
                    <p><strong>Urgency:</strong> ${createUrgencyBadge(order.urgency_level)}</p>
                </div>
                <div class="info-card">
                    <h6>Lead Time & Arrival</h6>
                    <p><strong>Lead Time:</strong> ${order.lead_time_days || '--'} days</p>
                    <p><strong>Expected Arrival:</strong> ${order.expected_arrival ? new Date(order.expected_arrival).toLocaleDateString() : '--'}</p>
                    <p><strong>Coverage:</strong> ${order.coverage_months ? order.coverage_months.toFixed(1) : '--'} months</p>
                </div>
                <div class="info-card">
                    <h6>Supplier Info</h6>
                    <p><strong>Supplier:</strong> ${order.supplier || '--'}</p>
                    <p><strong>Warehouse:</strong> ${order.warehouse.charAt(0).toUpperCase() + order.warehouse.slice(1)}</p>
                    <p><strong>Description:</strong> ${order.description || '--'}</p>
                </div>
            </div>
        `;

        document.getElementById('overview-content').innerHTML = html;

    } catch (error) {
        console.error('Failed to load overview:', error);
        document.getElementById('overview-content').innerHTML = `<p class="text-danger">Error loading overview data</p>`;
    }
}

/**
 * Load pending orders tab with timeline visualization
 * TASK-601: Updated to pass warehouse parameter to API
 * @param {string} skuId - SKU identifier
 * @param {string} warehouse - Warehouse name (burnaby or kentucky)
 * @returns {Promise<void>}
 */
async function loadPendingTab(skuId, warehouse) {
    try {
        document.getElementById('pending-content').innerHTML = '<p class="text-muted">Loading pending orders...</p>';

        const response = await fetch(`/api/pending-orders/sku/${skuId}?warehouse=${warehouse}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const pending = data.pending_orders || [];

        if (pending.length === 0) {
            document.getElementById('pending-content').innerHTML = '<p class="text-muted">No pending orders for this SKU</p>';
            return;
        }

        let html = '<div class="pending-inventory-section">';

        pending.forEach((order, index) => {
            const arrivalDate = new Date(order.expected_arrival);
            const daysAway = Math.ceil((arrivalDate - new Date()) / (1000 * 60 * 60 * 24));
            const statusClass = order.status === 'received' ? 'success' : daysAway < 0 ? 'danger' : 'info';

            html += `
                <div class="pending-item">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>Order ${index + 1}</strong>
                            <span class="badge bg-${statusClass} ms-2">${order.status}</span>
                        </div>
                        <div class="text-end">
                            <strong>${order.qty} units</strong>
                        </div>
                    </div>
                    <div class="mt-2 text-muted small">
                        <i class="fas fa-calendar me-1"></i>Expected: ${arrivalDate.toLocaleDateString()}
                        ${daysAway >= 0 ? `(${daysAway} days)` : '(Overdue)'}
                    </div>
                </div>
            `;
        });

        html += '</div>';
        document.getElementById('pending-content').innerHTML = html;

    } catch (error) {
        console.error('Failed to load pending orders:', error);
        document.getElementById('pending-content').innerHTML = '<p class="text-danger">Error loading pending orders. Endpoint may not be implemented yet.</p>';
    }
}

/**
 * Load 12-month forecast tab with Chart.js visualization
 * TASK-601: Updated to pass warehouse parameter to API
 * @param {string} skuId - SKU identifier
 * @param {string} warehouse - Warehouse name (burnaby or kentucky)
 * @returns {Promise<void>}
 */
async function loadForecastTab(skuId, warehouse) {
    try {
        // Show loading state
        document.getElementById('forecast-content').innerHTML = '<p class="text-muted text-center">Loading forecast...</p>';

        const response = await fetch(`/api/forecasts/sku/${skuId}/latest?warehouse=${warehouse}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const monthlyForecast = data.monthly_forecast || [];

        if (monthlyForecast.length === 0) {
            document.getElementById('forecast-content').innerHTML = '<p class="text-muted">No forecast data available for this SKU</p>';
            return;
        }

        // Extract data from monthly_forecast array
        const labels = monthlyForecast.map(m => {
            const date = new Date(m.month + '-01');
            return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
        });
        const baseData = monthlyForecast.map(m => Math.round(m.base_qty));
        const adjustedData = monthlyForecast.map(m => Math.round(m.adjusted_qty));
        const adjustmentReasons = monthlyForecast.map(m => m.adjustment_reason || 'No adjustment');

        // Check if any learning adjustments were applied
        const hasAdjustments = monthlyForecast.some(m => m.learning_applied);

        // Build datasets
        const datasets = [{
            label: 'Base Forecast',
            data: baseData,
            borderColor: '#007bff',
            backgroundColor: 'rgba(0, 123, 255, 0.1)',
            tension: 0.4,
            fill: false,
            borderWidth: 2
        }];

        // Add adjusted forecast if there are any adjustments
        if (hasAdjustments) {
            datasets.push({
                label: 'Learning-Adjusted Forecast',
                data: adjustedData,
                borderColor: '#28a745',
                backgroundColor: 'rgba(40, 167, 69, 0.1)',
                tension: 0.4,
                fill: false,
                borderWidth: 2,
                borderDash: [5, 5]
            });
        }

        // Create canvas for chart (replacing loading message) with proper container
        document.getElementById('forecast-content').innerHTML = '<div style="height: 400px; max-height: 400px;"><canvas id="forecast-chart"></canvas></div>';

        // Destroy previous chart instance if it exists
        if (window.forecastChartInstance) {
            window.forecastChartInstance.destroy();
        }

        // Create chart and store instance
        const ctx = document.getElementById('forecast-chart').getContext('2d');
        window.forecastChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: `12-Month Demand Forecast - ${data.forecast_method || 'Unknown Method'}`
                    },
                    legend: {
                        display: hasAdjustments,
                        position: 'bottom'
                    },
                    tooltip: {
                        callbacks: {
                            afterLabel: function(context) {
                                const index = context.dataIndex;
                                if (monthlyForecast[index].learning_applied) {
                                    return adjustmentReasons[index];
                                }
                                return '';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Units per Month'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Month'
                        }
                    }
                }
            }
        });

        // Add forecast metadata below chart (use insertAdjacentHTML to preserve Chart.js instance)
        const metadataHtml = `
            <div class="mt-3 text-muted small">
                <p><strong>Forecast Details:</strong></p>
                <ul>
                    <li>Run ID: ${data.forecast_run_id || 'N/A'}</li>
                    <li>Method: ${data.forecast_method || 'Unknown'}</li>
                    <li>Average Monthly Demand: ${Math.round(data.avg_monthly || 0)} units</li>
                    ${hasAdjustments ? '<li>Learning adjustments applied based on historical patterns</li>' : ''}
                </ul>
            </div>
        `;
        document.getElementById('forecast-content').insertAdjacentHTML('beforeend', metadataHtml);

    } catch (error) {
        console.error('Failed to load forecast:', error);
        document.getElementById('forecast-content').innerHTML = '<p class="text-danger">Error loading forecast data. Endpoint may not be implemented yet.</p>';
    }
}

/**
 * Load stockout history tab
 * @param {string} skuId - SKU identifier
 * @returns {Promise<void>}
 */
async function loadStockoutTab(skuId, warehouse) {
    try {
        document.getElementById('stockout-content').innerHTML = '<p class="text-muted">Loading stockout history...</p>';

        const response = await fetch(`/api/stockouts/sku/${skuId}?warehouse=${warehouse}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const stockouts = data.stockouts || [];

        if (stockouts.length === 0) {
            document.getElementById('stockout-content').innerHTML = '<p class="text-success">No stockout history for this SKU</p>';
            return;
        }

        let html = `
            <table class="table table-striped table-sm">
                <thead>
                    <tr>
                        <th>Stockout Date</th>
                        <th>Resolved Date</th>
                        <th>Days Out</th>
                        <th>Impact</th>
                    </tr>
                </thead>
                <tbody>
        `;

        stockouts.forEach(stockout => {
            const stockoutDate = new Date(stockout.stockout_date);
            const resolvedDate = stockout.resolved_date ? new Date(stockout.resolved_date) : null;
            const daysOut = resolvedDate ?
                Math.ceil((resolvedDate - stockoutDate) / (1000 * 60 * 60 * 24)) :
                Math.ceil((new Date() - stockoutDate) / (1000 * 60 * 60 * 24));

            html += `
                <tr>
                    <td>${stockoutDate.toLocaleDateString()}</td>
                    <td>${resolvedDate ? resolvedDate.toLocaleDateString() : 'Ongoing'}</td>
                    <td>${daysOut}</td>
                    <td><span class="badge bg-${daysOut > 7 ? 'danger' : 'warning'}">${daysOut > 7 ? 'High' : 'Medium'}</span></td>
                </tr>
            `;
        });

        html += `
                </tbody>
            </table>
        `;

        document.getElementById('stockout-content').innerHTML = html;

    } catch (error) {
        console.error('Failed to load stockout history:', error);
        document.getElementById('stockout-content').innerHTML = '<p class="text-danger">Error loading stockout history. Endpoint may not be implemented yet.</p>';
    }
}

/**
 * Load coverage timeline tab (V10.0 Phase 3)
 * Shows day-by-day inventory projection with stockout prediction
 * @param {string} skuId - SKU identifier
 * @param {string} warehouse - Warehouse name (burnaby or kentucky)
 * @returns {Promise<void>}
 */
async function loadCoverageTimelineTab(skuId, warehouse) {
    try {
        document.getElementById('coverage-timeline-content').innerHTML = '<p class="text-muted">Loading coverage timeline...</p>';

        const response = await fetch(`/api/supplier-orders/coverage-timeline/${skuId}?warehouse=${warehouse}&projection_days=90`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        let html = `
            <!-- Summary Cards -->
            <div class="row mb-3">
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title">Current Inventory</h6>
                            <h3 class="text-primary">${data.current_inventory.toLocaleString()}</h3>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title">Daily Demand</h6>
                            <h3 class="text-info">${data.daily_demand}</h3>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title">Coverage Days</h6>
                            <h3 class="${data.coverage_days < 30 ? 'text-danger' : data.coverage_days < 60 ? 'text-warning' : 'text-success'}">
                                ${data.coverage_days}${data.stockout_date ? '' : '+'}
                            </h3>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title">Stockout Date</h6>
                            <h3 class="${data.stockout_date ? 'text-danger' : 'text-success'}">
                                ${data.stockout_date ? new Date(data.stockout_date).toLocaleDateString() : 'None'}
                            </h3>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Forecast Source Info -->
            <div class="alert alert-info">
                <strong>Demand Source:</strong> ${data.forecast_source}
            </div>

            <!-- Pending Arrivals -->
            ${data.pending_arrivals.length > 0 ? `
                <h6 class="mt-3">Pending Arrivals (${data.pending_arrivals.length})</h6>
                <div class="table-responsive" style="max-height: 150px;">
                    <table class="table table-sm table-striped">
                        <thead>
                            <tr>
                                <th>Arrival Date</th>
                                <th>Quantity</th>
                                <th>Supplier</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.pending_arrivals.map(arrival => `
                                <tr>
                                    <td>${new Date(arrival.arrival_date).toLocaleDateString()}</td>
                                    <td>${arrival.quantity.toLocaleString()}</td>
                                    <td>${arrival.supplier}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            ` : '<p class="text-muted">No pending arrivals</p>'}

            <!-- Daily Timeline -->
            <h6 class="mt-4">Daily Inventory Projection (First 30 Days)</h6>
            <div class="table-responsive" style="max-height: 400px;">
                <table class="table table-sm table-striped">
                    <thead style="position: sticky; top: 0; background: white; z-index: 1;">
                        <tr>
                            <th>Date</th>
                            <th>Inventory</th>
                            <th>Demand</th>
                            <th>Arrivals</th>
                            <th>Days Coverage</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.timeline.slice(0, 30).map(day => {
                            const isLowStock = day.days_coverage < 30;
                            const isCritical = day.days_coverage < 7;
                            const rowClass = isCritical ? 'table-danger' : (isLowStock ? 'table-warning' : '');
                            return `
                                <tr class="${rowClass}">
                                    <td>${new Date(day.date).toLocaleDateString()}</td>
                                    <td>${day.inventory.toLocaleString()}</td>
                                    <td>${day.demand}</td>
                                    <td>${day.arrivals > 0 ? `<strong>+${day.arrivals}</strong>` : '-'}</td>
                                    <td>${day.days_coverage}</td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;

        document.getElementById('coverage-timeline-content').innerHTML = html;

    } catch (error) {
        console.error('Failed to load coverage timeline:', error);
        document.getElementById('coverage-timeline-content').innerHTML = '<p class="text-danger">Error loading coverage timeline.</p>';
    }
}

/**
 * Load supplier performance tab (V10.0 Phase 3)
 * Shows supplier lead time statistics, recent shipments, and pending orders
 * @param {string} skuId - SKU identifier
 * @param {string} warehouse - Warehouse name (burnaby or kentucky)
 * @returns {Promise<void>}
 */
async function loadSupplierPerformanceTab(skuId, warehouse) {
    try {
        document.getElementById('supplier-performance-content').innerHTML = '<p class="text-muted">Loading supplier performance...</p>';

        const response = await fetch(`/api/supplier-orders/supplier-performance/${skuId}?warehouse=${warehouse}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Check for error in response
        if (data.error) {
            document.getElementById('supplier-performance-content').innerHTML = `<p class="text-warning">${data.error}</p>`;
            return;
        }

        const stats = data.lead_time_stats;
        const shipments = data.recent_shipments;
        const pending = data.pending_orders;

        let html = `
            <!-- Supplier Header -->
            <div class="alert alert-info">
                <strong>Supplier:</strong> ${data.supplier_name}
                <span class="ms-3"><strong>Warehouse:</strong> ${warehouse.charAt(0).toUpperCase() + warehouse.slice(1)}</span>
                ${stats.data_source ? `<span class="ms-3 badge bg-secondary">${stats.data_source === 'pre_calculated' ? 'Pre-calculated Stats' : 'Real-time Calculation'}</span>` : ''}
            </div>

            <!-- Lead Time Statistics -->
            <h6 class="mt-3">Lead Time Statistics</h6>
            <div class="row mb-3">
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title text-muted small">Average</h6>
                            <h4 class="text-primary">${stats.avg_lead_time.toFixed(1)}</h4>
                            <small class="text-muted">days</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title text-muted small">Median</h6>
                            <h4 class="text-info">${stats.median_lead_time.toFixed(1)}</h4>
                            <small class="text-muted">days</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title text-muted small">P95</h6>
                            <h4 class="text-warning">${stats.p95_lead_time.toFixed(1)}</h4>
                            <small class="text-muted">days</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title text-muted small">Min / Max</h6>
                            <h4 class="text-success">${stats.min_lead_time} / ${stats.max_lead_time}</h4>
                            <small class="text-muted">days</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title text-muted small">Reliability</h6>
                            <h4 class="${stats.reliability_score >= 80 ? 'text-success' : stats.reliability_score >= 60 ? 'text-warning' : 'text-danger'}">${stats.reliability_score}</h4>
                            <small class="text-muted">score</small>
                        </div>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="card">
                        <div class="card-body text-center">
                            <h6 class="card-title text-muted small">On-Time Rate</h6>
                            <h4 class="${data.on_time_delivery_rate >= 80 ? 'text-success' : data.on_time_delivery_rate >= 60 ? 'text-warning' : 'text-danger'}">${data.on_time_delivery_rate.toFixed(1)}%</h4>
                            <small class="text-muted">${data.total_shipments} shipments</small>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Pending Orders -->
            ${pending.length > 0 ? `
                <h6 class="mt-4">Pending Orders (${pending.length})</h6>
                <div class="table-responsive" style="max-height: 200px;">
                    <table class="table table-sm table-striped">
                        <thead style="position: sticky; top: 0; background: white; z-index: 1;">
                            <tr>
                                <th>Quantity</th>
                                <th>Order Date</th>
                                <th>Expected Arrival</th>
                                <th>Lead Time</th>
                                <th>Days Until Arrival</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${pending.map(order => {
                                const isLate = order.days_until_arrival < 0;
                                const isSoon = order.days_until_arrival <= 7 && order.days_until_arrival >= 0;
                                const rowClass = isLate ? 'table-danger' : (isSoon ? 'table-warning' : '');
                                return `
                                    <tr class="${rowClass}">
                                        <td>${order.quantity.toLocaleString()}</td>
                                        <td>${new Date(order.order_date).toLocaleDateString()}</td>
                                        <td>${order.expected_arrival !== 'Estimated' ? new Date(order.expected_arrival).toLocaleDateString() : order.expected_arrival}</td>
                                        <td>${order.lead_time_days} days</td>
                                        <td>${order.days_until_arrival >= 0 ? order.days_until_arrival : 'Late'}</td>
                                        <td><span class="badge bg-primary">${order.status}</span></td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            ` : '<p class="text-muted">No pending orders for this supplier</p>'}

            <!-- Recent Shipments -->
            <h6 class="mt-4">Recent Shipment History (Last 12 Months)</h6>
            ${shipments.length > 0 ? `
                <div class="table-responsive" style="max-height: 300px;">
                    <table class="table table-sm table-striped">
                        <thead style="position: sticky; top: 0; background: white; z-index: 1;">
                            <tr>
                                <th>PO Number</th>
                                <th>Order Date</th>
                                <th>Received Date</th>
                                <th>Lead Time</th>
                                <th>Partial?</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${shipments.map(shipment => {
                                const onTimeThreshold = stats.avg_lead_time * 1.1;
                                const isLate = shipment.actual_lead_time > onTimeThreshold;
                                const rowClass = isLate ? 'table-warning' : '';
                                return `
                                    <tr class="${rowClass}">
                                        <td>${shipment.po_number}</td>
                                        <td>${new Date(shipment.order_date).toLocaleDateString()}</td>
                                        <td>${new Date(shipment.received_date).toLocaleDateString()}</td>
                                        <td><strong>${shipment.actual_lead_time}</strong> days</td>
                                        <td>${shipment.was_partial ? '<span class="badge bg-warning">Yes</span>' : '<span class="badge bg-success">No</span>'}</td>
                                        <td>${shipment.notes || '-'}</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
                <small class="text-muted">
                    Rows highlighted in yellow indicate deliveries that exceeded the on-time threshold (${(stats.avg_lead_time * 1.1).toFixed(1)} days).
                </small>
            ` : '<p class="text-muted">No recent shipment history available</p>'}
        `;

        document.getElementById('supplier-performance-content').innerHTML = html;

    } catch (error) {
        console.error('Failed to load supplier performance:', error);
        document.getElementById('supplier-performance-content').innerHTML = '<p class="text-danger">Error loading supplier performance data.</p>';
    }
}

/**
 * Show loading overlay
 * @param {string} message - Loading message to display
 */
function showLoading(message) {
    document.getElementById('loading-message').textContent = message;
    document.getElementById('loading-overlay').style.display = 'flex';
}

/**
 * Hide loading overlay
 */
function hideLoading() {
    document.getElementById('loading-overlay').style.display = 'none';
}

/**
 * Show success message
 * @param {string} message - Success message
 */
function showSuccess(message) {
    alert(message); // Basic implementation - can be enhanced with toast notifications
}

/**
 * Show error message
 * @param {string} message - Error message
 */
function showError(message) {
    alert(message); // Basic implementation - can be enhanced with toast notifications
}
