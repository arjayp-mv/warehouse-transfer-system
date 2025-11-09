/**
 * Pending Orders Management JavaScript
 * Handles all functionality for pending orders interface
 */
let dataTable = null;
let allOrders = [];

$(document).ready(function() {
    initializeDataTable();
    loadPendingOrders();
});

async function loadSummaryMetrics() {
    try {
        const response = await fetch('/api/pending-orders/summary');
        if (!response.ok) throw new Error('Failed to load summary');

        const data = await response.json();
        document.getElementById('totalOrders').textContent = data.total_orders || 0;
        document.getElementById('kentuckyOrders').textContent = data.kentucky_orders || 0;
        document.getElementById('burnabyOrders').textContent = data.burnaby_orders || 0;

        const overdueCount = allOrders.filter(o => {
            if (!o.expected_arrival) return false;
            return new Date(o.expected_arrival) < new Date();
        }).length;
        document.getElementById('overdueOrders').textContent = overdueCount;
    } catch (error) {
        console.error('Error loading summary:', error);
        showToast('Failed to load summary metrics', 'danger');
    }
}

async function loadPendingOrders() {
    try {
        showLoading(true);
        const params = new URLSearchParams();
        const status = document.getElementById('statusFilter').value;
        const destination = document.getElementById('destinationFilter').value;
        const orderType = document.getElementById('orderTypeFilter').value;
        const overdueOnly = document.getElementById('overdueFilter').checked;

        if (status) params.append('status', status);
        if (destination) params.append('destination', destination);
        if (orderType) params.append('order_type', orderType);
        if (overdueOnly) params.append('overdue_only', 'true');

        const response = await fetch(`/api/pending-orders?${params.toString()}`);
        if (!response.ok) throw new Error('Failed to load pending orders');

        const result = await response.json();
        allOrders = result.data || [];
        displayPendingOrders(allOrders);
        loadSummaryMetrics();
    } catch (error) {
        console.error('Error loading orders:', error);
        showToast('Failed to load pending orders', 'danger');
    } finally {
        showLoading(false);
    }
}

function displayPendingOrders(orders) {
    if (dataTable) dataTable.clear();
    const tbody = document.getElementById('ordersTableBody');
    tbody.innerHTML = '';

    if (orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No pending orders found</td></tr>';
        return;
    }

    orders.forEach(order => {
        const row = tbody.insertRow();
        row.insertCell(0).textContent = order.sku_id;
        row.insertCell(1).innerHTML = `<span class="text-end d-block">${order.quantity}</span>`;
        row.insertCell(2).innerHTML = formatDestination(order.destination);
        row.insertCell(3).textContent = order.order_date || '-';

        const isEstimated = !order.expected_arrival;
        const displayDate = order.calculated_arrival_date || 'Not Set';
        const badge = isEstimated
            ? '<span class="badge bg-warning text-dark ms-1">Est.</span>'
            : '<span class="badge bg-success text-white ms-1">Conf.</span>';
        row.insertCell(4).innerHTML = displayDate !== 'Not Set' ? `${displayDate} ${badge}` : displayDate;

        row.insertCell(5).innerHTML = calculateDaysUntil(order.calculated_arrival_date);
        row.insertCell(6).innerHTML = formatStatus(order.status);
        row.insertCell(7).innerHTML = `<span class="badge bg-secondary">${order.order_type.toUpperCase()}</span>`;
        row.insertCell(8).textContent = order.notes ? (order.notes.length > 30 ? order.notes.substring(0, 30) + '...' : order.notes) : '-';
        row.insertCell(9).innerHTML = formatActions(order.id);
    });

    if (dataTable) dataTable.rows.add($(tbody).find('tr')).draw();
}

function initializeDataTable() {
    if (dataTable) dataTable.destroy();
    dataTable = $('#pendingOrdersTable').DataTable({
        pageLength: 25,
        lengthMenu: [25, 50, 100],
        order: [[3, 'desc']],
        columnDefs: [
            { targets: [1], className: 'text-end' },
            { targets: [2, 5, 6, 7, 9], className: 'text-center' },
            { targets: [9], orderable: false }
        ]
    });
}

function applyFilters() {
    loadPendingOrders();
    loadSummaryMetrics();
}

function clearFilters() {
    document.getElementById('statusFilter').value = '';
    document.getElementById('destinationFilter').value = '';
    document.getElementById('orderTypeFilter').value = '';
    document.getElementById('overdueFilter').checked = false;
    loadPendingOrders();
    loadSummaryMetrics();
}

function formatStatus(status) {
    const badges = {'ordered': 'bg-info', 'shipped': 'bg-warning', 'received': 'bg-success', 'cancelled': 'bg-danger'};
    return `<span class="badge ${badges[status] || 'bg-secondary'}">${status.toUpperCase()}</span>`;
}

function formatDestination(destination) {
    const icons = {
        'kentucky': '<i class="fas fa-warehouse text-success me-1"></i>',
        'burnaby': '<i class="fas fa-warehouse text-primary me-1"></i>'
    };
    return `${icons[destination] || ''}<span>${destination.charAt(0).toUpperCase() + destination.slice(1)}</span>`;
}

function calculateDaysUntil(expectedDate) {
    if (!expectedDate) return '<span class="text-muted">Not Set</span>';
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const expected = new Date(expectedDate);
    expected.setHours(0, 0, 0, 0);
    const diffDays = Math.ceil((expected - today) / (1000 * 60 * 60 * 24));

    if (diffDays < 0) return `<span class="text-danger fw-bold"><i class="fas fa-exclamation-circle"></i> OVERDUE (${Math.abs(diffDays)} days)</span>`;
    if (diffDays > 30) return `<span class="text-success">${diffDays} days</span>`;
    if (diffDays >= 7) return `<span class="text-warning">${diffDays} days</span>`;
    return `<span class="text-danger">${diffDays} days</span>`;
}

function formatActions(orderId) {
    return `<button class="btn btn-sm btn-primary me-1" onclick="showEditOrderModal(${orderId})" title="Edit"><i class="fas fa-edit"></i></button>
            <button class="btn btn-sm btn-danger" onclick="deleteOrder(${orderId})" title="Delete"><i class="fas fa-trash"></i></button>`;
}

function showAddOrderModal() {
    document.getElementById('orderModalTitle').textContent = 'Add Pending Order';
    ['orderId', 'skuId', 'quantity', 'destination', 'orderDate', 'expectedArrival', 'orderType', 'supplier', 'notes'].forEach(id => {
        document.getElementById(id).value = '';
    });
    document.getElementById('status').value = 'ordered';
    new bootstrap.Modal(document.getElementById('orderModal')).show();
}

async function showEditOrderModal(orderId) {
    try {
        const response = await fetch(`/api/pending-orders/${orderId}`);
        if (!response.ok) throw new Error('Failed to load order details');
        const order = await response.json();

        document.getElementById('orderModalTitle').textContent = 'Edit Pending Order';
        document.getElementById('orderId').value = order.id;
        document.getElementById('skuId').value = order.sku_id;
        document.getElementById('quantity').value = order.quantity;
        document.getElementById('destination').value = order.destination;
        document.getElementById('orderDate').value = order.order_date;
        document.getElementById('expectedArrival').value = order.expected_arrival || '';
        document.getElementById('orderType').value = order.order_type;
        document.getElementById('status').value = order.status;
        document.getElementById('supplier').value = order.supplier || '';
        document.getElementById('notes').value = order.notes || '';

        new bootstrap.Modal(document.getElementById('orderModal')).show();
    } catch (error) {
        console.error('Error loading order:', error);
        showToast('Failed to load order details', 'danger');
    }
}

async function saveOrder() {
    const orderId = document.getElementById('orderId').value;
    const isEdit = orderId !== '';
    const orderData = {
        sku_id: document.getElementById('skuId').value.trim(),
        quantity: parseInt(document.getElementById('quantity').value),
        destination: document.getElementById('destination').value,
        order_date: document.getElementById('orderDate').value,
        expected_arrival: document.getElementById('expectedArrival').value || null,
        order_type: document.getElementById('orderType').value,
        status: document.getElementById('status').value,
        supplier: document.getElementById('supplier').value.trim() || null,
        notes: document.getElementById('notes').value.trim() || null
    };

    if (!validateOrderData(orderData)) return;

    try {
        showLoading(true);
        const response = await fetch(isEdit ? `/api/pending-orders/${orderId}` : '/api/pending-orders', {
            method: isEdit ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save order');
        }

        showToast(`Order ${isEdit ? 'updated' : 'created'} successfully`, 'success');
        bootstrap.Modal.getInstance(document.getElementById('orderModal')).hide();
        loadPendingOrders();
        loadSummaryMetrics();
    } catch (error) {
        console.error('Error saving order:', error);
        showToast(error.message || 'Failed to save order', 'danger');
    } finally {
        showLoading(false);
    }
}

function validateOrderData(data) {
    if (!data.sku_id) return showToast('SKU ID is required', 'warning'), false;
    if (!data.quantity || data.quantity < 1) return showToast('Quantity must be at least 1', 'warning'), false;
    if (!data.destination) return showToast('Destination is required', 'warning'), false;
    if (!data.order_date) return showToast('Order date is required', 'warning'), false;

    const orderDate = new Date(data.order_date);
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (orderDate > today) return showToast('Order date cannot be in the future', 'warning'), false;
    if (data.expected_arrival && data.expected_arrival < data.order_date) {
        return showToast('Expected arrival must be after order date', 'warning'), false;
    }
    if (!data.order_type) return showToast('Order type is required', 'warning'), false;
    return true;
}

async function deleteOrder(orderId) {
    if (!confirm('Are you sure you want to delete this pending order?')) return;

    try {
        showLoading(true);
        const response = await fetch(`/api/pending-orders/${orderId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Failed to delete order');

        showToast('Order deleted successfully', 'success');
        loadPendingOrders();
        loadSummaryMetrics();
    } catch (error) {
        console.error('Error deleting order:', error);
        showToast('Failed to delete order', 'danger');
    } finally {
        showLoading(false);
    }
}

function showBulkDeleteModal() {
    document.getElementById('bulkDeleteSkuInput').value = '';
    new bootstrap.Modal(document.getElementById('bulkDeleteModal')).show();
}

async function bulkDeleteBySku() {
    const skuId = document.getElementById('bulkDeleteSkuInput').value.trim();
    if (!skuId) return showToast('Please enter a SKU ID', 'warning');

    try {
        showLoading(true);
        const ordersForSku = allOrders.filter(o => o.sku_id === skuId);

        if (ordersForSku.length === 0) {
            showToast('No pending orders found for this SKU', 'info');
            showLoading(false);
            return;
        }

        if (!confirm(`Delete ${ordersForSku.length} pending order(s) for SKU ${skuId}?`)) {
            showLoading(false);
            return;
        }

        const response = await fetch(`/api/pending-orders/clear-sku/${encodeURIComponent(skuId)}`, { method: 'DELETE' });
        if (!response.ok) throw new Error('Failed to delete orders');

        showToast(`Deleted ${ordersForSku.length} orders for SKU ${skuId}`, 'success');
        bootstrap.Modal.getInstance(document.getElementById('bulkDeleteModal')).hide();
        loadPendingOrders();
        loadSummaryMetrics();
    } catch (error) {
        console.error('Error bulk deleting:', error);
        showToast('Failed to delete orders', 'danger');
    } finally {
        showLoading(false);
    }
}

async function clearAllOrders() {
    if (!confirm('WARNING: This will delete ALL pending orders. Are you absolutely sure?')) return;
    const totalOrders = document.getElementById('totalOrders').textContent;
    if (!confirm(`This will permanently delete ${totalOrders} pending orders. This cannot be undone. Continue?`)) return;

    try {
        showLoading(true);
        const response = await fetch('/api/admin/clear-pending-orders', { method: 'POST' });
        if (!response.ok) throw new Error('Failed to clear orders');

        showToast('All pending orders cleared', 'success');
        loadPendingOrders();
        loadSummaryMetrics();
    } catch (error) {
        console.error('Error clearing orders:', error);
        showToast('Failed to clear orders', 'danger');
    } finally {
        showLoading(false);
    }
}

function exportToCSV() {
    if (allOrders.length === 0) return showToast('No data to export', 'warning');

    let csv = 'SKU ID,Quantity,Destination,Order Date,Expected Arrival,Status,Order Type,Supplier,Notes\n';
    allOrders.forEach(order => {
        csv += [
            order.sku_id, order.quantity, order.destination,
            order.order_date || '', order.expected_arrival || '',
            order.status, order.order_type, order.supplier || '',
            `"${(order.notes || '').replace(/"/g, '""')}"`
        ].join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `pending_orders_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    showToast('CSV exported successfully', 'success');
}

function showLoading(show) {
    document.getElementById('loadingOverlay').classList[show ? 'add' : 'remove']('show');
}

function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer');
    const toastId = 'toast-' + Date.now();
    const bgClass = {'success': 'bg-success', 'danger': 'bg-danger', 'warning': 'bg-warning', 'info': 'bg-info'}[type] || 'bg-info';

    toastContainer.insertAdjacentHTML('beforeend', `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `);

    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
    toast.show();
    toastElement.addEventListener('hidden.bs.toast', () => toastElement.remove());
}
