# Pending Orders Management Interface - Task Tracker

**Feature**: Full Pending Orders Management System
**Task Range**: TASK-378 to TASK-395
**Status**: IN PROGRESS
**Start Date**: 2025-11-09

---

## Overview

Replace the "coming soon" placeholder with a comprehensive pending orders management interface that provides full CRUD operations, advanced filtering, SKU search, and bulk operations.

**Business Value**:
- Reduce time spent managing pending orders from 15+ minutes to <2 minutes
- Provide visibility into all pending orders across both warehouses
- Enable quick identification of overdue orders
- Support bulk operations for efficiency

**Technical Approach**:
- Create dedicated page (`pending-orders.html`) following `sku-listing.html` pattern
- Leverage existing backend APIs (no backend changes needed)
- Use DataTables for powerful table features
- Implement comprehensive filtering and search

---

## Phase 1: Page Structure and Layout

### TASK-378: Create pending-orders.html base structure
**Status**: [ ] Pending
**Description**: Create new HTML file with Bootstrap 5 layout, navigation, and basic structure
**Components**:
- HTML5 doctype and meta tags
- Bootstrap 5 CSS/JS includes
- DataTables CSS/JS includes
- Font Awesome icons
- Navigation header with breadcrumb
- Main content container

**Acceptance Criteria**:
- Page loads without errors
- Navigation breadcrumb shows: Dashboard > Pending Orders
- Responsive layout works on desktop and tablet

---

### TASK-379: Implement summary metrics cards section
**Status**: [ ] Pending
**Description**: Create 4 metric cards showing real-time pending order statistics
**Cards**:
1. Total Pending Orders (blue, fa-box icon)
2. Kentucky-Bound Orders (green, fa-warehouse icon)
3. Burnaby-Bound Orders (purple, fa-warehouse icon)
4. Overdue Orders (red, fa-exclamation-triangle icon)

**API Endpoint**: `GET /api/pending-orders/summary`

**Acceptance Criteria**:
- Cards display correct counts from API
- Cards update when filters are applied
- Color coding matches design spec
- Icons display correctly

---

### TASK-380: Create filter controls section
**Status**: [ ] Pending
**Description**: Build comprehensive filter controls with dropdowns and date pickers
**Controls**:
- Status dropdown (All, Ordered, Shipped, Received, Cancelled)
- Destination dropdown (All, Kentucky, Burnaby)
- Order Type dropdown (All, Supplier, Transfer)
- Order Date From/To date pickers
- Expected Arrival From/To date pickers
- Overdue Only checkbox toggle
- Apply Filters button (btn-primary)
- Clear Filters button (btn-secondary)

**Acceptance Criteria**:
- All dropdowns populate with correct options
- Date pickers use HTML5 date input or datepicker library
- Clear button resets all filters to defaults
- Filter section is visually organized and easy to use

---

### TASK-381: Create action buttons toolbar
**Status**: [ ] Pending
**Description**: Implement action buttons for bulk operations and data import/export
**Buttons**:
- Add New Order (btn-success, fa-plus)
- Import CSV (btn-info, fa-file-upload)
- Export to CSV (btn-primary, fa-file-download)
- Bulk Delete by SKU (btn-warning, fa-trash-alt)
- Clear All Orders (btn-danger, fa-exclamation-triangle)

**Acceptance Criteria**:
- Buttons are visually distinct with appropriate colors
- Icons display correctly
- Buttons are responsive and aligned properly
- Tooltips explain each button's function

---

## Phase 2: DataTable Implementation

### TASK-382: Initialize DataTables with pending orders data
**Status**: [ ] Pending
**Description**: Set up DataTables with proper columns, pagination, and sorting
**Columns**:
1. SKU ID (text-start, sortable)
2. Quantity (text-end, sortable)
3. Destination (text-center, sortable)
4. Order Date (text-center, sortable)
5. Expected Arrival (text-center, sortable)
6. Days Until (text-center, sortable, calculated)
7. Status (text-center, sortable, badge)
8. Order Type (text-center, sortable)
9. Notes (text-start, truncated)
10. Actions (text-center, buttons)

**DataTables Config**:
- pageLength: 25
- lengthMenu: [25, 50, 100]
- order: [[3, 'desc']] (Order Date descending)
- Global search enabled
- Column sorting enabled

**Acceptance Criteria**:
- Table displays all pending orders correctly
- Pagination works with proper page sizes
- Sorting works on all columns
- Global search filters across SKU ID and notes
- Table is responsive

---

### TASK-383: Implement status badge formatting
**Status**: [ ] Pending
**Description**: Create color-coded status badges in DataTable
**Badge Colors**:
- Ordered: badge-info (blue)
- Shipped: badge-warning (yellow)
- Received: badge-success (green)
- Cancelled: badge-danger (red)

**Implementation**:
```javascript
function formatStatus(status) {
    const badges = {
        'ordered': 'badge-info',
        'shipped': 'badge-warning',
        'received': 'badge-success',
        'cancelled': 'badge-danger'
    };
    return `<span class="badge ${badges[status] || 'badge-secondary'}">${status.toUpperCase()}</span>`;
}
```

**Acceptance Criteria**:
- Status badges display with correct colors
- Badge text is uppercase
- Badges are easily readable

---

### TASK-384: Implement "Days Until Arrival" calculation and color coding
**Status**: [ ] Pending
**Description**: Calculate and display days until expected arrival with color warnings
**Logic**:
- If expected_arrival is null: Display "Not Set" (gray)
- If date is in past: Display "OVERDUE" in red bold with warning icon
- If >30 days: Display in green
- If 7-30 days: Display in yellow/orange
- If <7 days: Display in red

**Implementation**:
```javascript
function calculateDaysUntil(expectedDate) {
    if (!expectedDate) return '<span class="text-muted">Not Set</span>';

    const today = new Date();
    const expected = new Date(expectedDate);
    const diffTime = expected - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays < 0) {
        return `<span class="text-danger fw-bold"><i class="fas fa-exclamation-circle"></i> OVERDUE (${Math.abs(diffDays)} days)</span>`;
    } else if (diffDays > 30) {
        return `<span class="text-success">${diffDays} days</span>`;
    } else if (diffDays >= 7) {
        return `<span class="text-warning">${diffDays} days</span>`;
    } else {
        return `<span class="text-danger">${diffDays} days</span>`;
    }
}
```

**Acceptance Criteria**:
- Days calculation is accurate
- Color coding matches urgency levels
- Overdue orders clearly highlighted
- Icons display for overdue items

---

### TASK-385: Add action buttons to each table row
**Status**: [ ] Pending
**Description**: Implement Edit and Delete buttons in Actions column
**Buttons**:
- Edit: btn-sm btn-primary, fa-edit icon, opens edit modal
- Delete: btn-sm btn-danger, fa-trash icon, shows confirmation

**Implementation**:
```javascript
function formatActions(orderId) {
    return `
        <button class="btn btn-sm btn-primary me-1" onclick="showEditOrderModal(${orderId})" title="Edit Order">
            <i class="fas fa-edit"></i>
        </button>
        <button class="btn btn-sm btn-danger" onclick="deleteOrder(${orderId})" title="Delete Order">
            <i class="fas fa-trash"></i>
        </button>
    `;
}
```

**Acceptance Criteria**:
- Buttons are properly sized and spaced
- Tooltips show on hover
- Click events trigger correct functions
- Buttons are accessible via keyboard

---

## Phase 3: Data Loading and API Integration

### TASK-386: Implement loadPendingOrders() function
**Status**: [ ] Pending
**Description**: Fetch pending orders from backend API with filter parameters
**API Endpoint**: `GET /api/pending-orders`
**Query Parameters**:
- status: string
- destination: string
- order_type: string
- overdue_only: boolean
- order_date_from: YYYY-MM-DD
- order_date_to: YYYY-MM-DD
- expected_arrival_from: YYYY-MM-DD
- expected_arrival_to: YYYY-MM-DD

**Implementation**:
```javascript
async function loadPendingOrders() {
    try {
        showLoading(true);

        // Build query string from filter values
        const params = new URLSearchParams();
        const status = document.getElementById('statusFilter').value;
        const destination = document.getElementById('destinationFilter').value;
        // ... add all filter parameters

        const response = await fetch(`/api/pending-orders?${params.toString()}`);
        if (!response.ok) throw new Error('Failed to load pending orders');

        const data = await response.json();
        displayPendingOrders(data);

    } catch (error) {
        console.error('Error loading pending orders:', error);
        showToast('Failed to load pending orders', 'danger');
    } finally {
        showLoading(false);
    }
}
```

**Acceptance Criteria**:
- API call includes all active filters
- Loading indicator shows during fetch
- Data populates DataTable correctly
- Error handling shows user-friendly message
- Empty results show "No pending orders found"

---

### TASK-387: Implement loadSummaryMetrics() function
**Status**: [ ] Pending
**Description**: Load and display summary statistics in metric cards
**API Endpoint**: `GET /api/pending-orders/summary`

**Response Format**:
```json
{
    "total_orders": 145,
    "total_skus": 87,
    "by_destination": {
        "kentucky": 98,
        "burnaby": 47
    },
    "by_status": {
        "ordered": 52,
        "shipped": 68,
        "received": 20,
        "cancelled": 5
    },
    "overdue_count": 12
}
```

**Acceptance Criteria**:
- Metric cards update with API data
- Cards reflect current filter state
- Counts are accurate
- Loading state is shown during fetch

---

### TASK-388: Implement applyFilters() and clearFilters() functions
**Status**: [ ] Pending
**Description**: Handle filter application and reset functionality
**Functions**:
1. `applyFilters()`: Read all filter inputs, reload data and metrics
2. `clearFilters()`: Reset all inputs to defaults, reload with no filters

**Acceptance Criteria**:
- Apply Filters button triggers reload with filter params
- Clear Filters resets all dropdowns to "All" and date pickers to empty
- Table and metrics update after filter changes
- Filter state is reflected in URL (optional)

---

## Phase 4: CRUD Operations

### TASK-389: Create Add/Edit Order modal
**Status**: [ ] Pending
**Description**: Build modal dialog for creating and editing pending orders
**Form Fields**:
- SKU ID (text input, required)
- Quantity (number input, required, min=1)
- Destination (select: Burnaby, Kentucky, required)
- Order Date (date input, required)
- Expected Arrival (date input, optional)
- Order Type (select: Supplier, Transfer, required)
- Status (select: Ordered, Shipped, Received, Cancelled, required)
- Supplier (text input, optional)
- Notes (textarea, optional)

**Modal Features**:
- Title changes based on Add/Edit mode
- Form validation before submit
- Save button triggers API call
- Cancel button clears and closes modal

**Acceptance Criteria**:
- Modal opens properly for both add and edit modes
- Form fields populate with existing data in edit mode
- Validation prevents invalid submissions
- Modal closes after successful save

---

### TASK-390: Implement saveOrder() function
**Status**: [ ] Pending
**Description**: Save new or updated order via API
**API Endpoints**:
- Create: `POST /api/pending-orders`
- Update: `PUT /api/pending-orders/{order_id}`

**Validation Rules**:
- SKU ID: Required, non-empty
- Quantity: Required, positive integer
- Destination: Required, valid enum
- Order Date: Required, not in future
- Expected Arrival: If provided, must be >= order_date

**Implementation**:
```javascript
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
        notes: document.getElementById('notes').value.trim()
    };

    // Validate
    if (!validateOrderData(orderData)) return;

    try {
        const url = isEdit ? `/api/pending-orders/${orderId}` : '/api/pending-orders';
        const method = isEdit ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData)
        });

        if (!response.ok) throw new Error('Failed to save order');

        showToast(`Order ${isEdit ? 'updated' : 'created'} successfully`, 'success');
        closeOrderModal();
        loadPendingOrders();
        loadSummaryMetrics();

    } catch (error) {
        console.error('Error saving order:', error);
        showToast('Failed to save order', 'danger');
    }
}
```

**Acceptance Criteria**:
- New orders are created successfully
- Existing orders are updated successfully
- Validation prevents invalid data submission
- Success/error messages display appropriately
- Table refreshes after save

---

### TASK-391: Implement deleteOrder() function
**Status**: [ ] Pending
**Description**: Delete individual pending order with confirmation
**API Endpoint**: `DELETE /api/pending-orders/{order_id}`

**Implementation**:
```javascript
async function deleteOrder(orderId) {
    if (!confirm('Are you sure you want to delete this pending order?')) {
        return;
    }

    try {
        const response = await fetch(`/api/pending-orders/${orderId}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Failed to delete order');

        showToast('Order deleted successfully', 'success');
        loadPendingOrders();
        loadSummaryMetrics();

    } catch (error) {
        console.error('Error deleting order:', error);
        showToast('Failed to delete order', 'danger');
    }
}
```

**Acceptance Criteria**:
- Confirmation dialog appears before deletion
- Order is removed from database
- Table refreshes after deletion
- Metrics update to reflect deletion
- Error handling works properly

---

## Phase 5: Bulk Operations

### TASK-392: Implement Bulk Delete by SKU
**Status**: [ ] Pending
**Description**: Delete all pending orders for a specific SKU
**API Endpoint**: `DELETE /api/pending-orders/clear-sku/{sku_id}`

**UI Flow**:
1. Click "Bulk Delete by SKU" button
2. Modal opens with SKU input field
3. User enters SKU ID
4. Confirmation dialog shows count of orders to be deleted
5. If confirmed, delete all orders for that SKU

**Implementation**:
```javascript
async function bulkDeleteBySku() {
    const skuId = document.getElementById('bulkDeleteSkuInput').value.trim();

    if (!skuId) {
        showToast('Please enter a SKU ID', 'warning');
        return;
    }

    // First, get count of orders for this SKU
    const orders = await fetch(`/api/pending-orders?sku_id=${skuId}`).then(r => r.json());

    if (orders.length === 0) {
        showToast('No pending orders found for this SKU', 'info');
        return;
    }

    if (!confirm(`Delete ${orders.length} pending order(s) for SKU ${skuId}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/pending-orders/clear-sku/${skuId}`, {
            method: 'DELETE'
        });

        if (!response.ok) throw new Error('Failed to delete orders');

        showToast(`Deleted ${orders.length} orders for SKU ${skuId}`, 'success');
        closeBulkDeleteModal();
        loadPendingOrders();
        loadSummaryMetrics();

    } catch (error) {
        console.error('Error bulk deleting:', error);
        showToast('Failed to delete orders', 'danger');
    }
}
```

**Acceptance Criteria**:
- Modal opens with clear input field
- Validation ensures SKU is entered
- Shows count before confirming deletion
- All orders for SKU are deleted
- Table and metrics refresh after deletion

---

### TASK-393: Implement Export to CSV
**Status**: [ ] Pending
**Description**: Export current filtered view to CSV file
**Functionality**:
- Exports all visible rows (respecting current filters)
- Includes all columns except Actions
- Formats dates as YYYY-MM-DD
- Calculates and includes Days Until column
- Downloads as `pending_orders_YYYYMMDD.csv`

**Implementation**:
```javascript
function exportToCSV() {
    const table = document.getElementById('pendingOrdersTable');
    const rows = table.querySelectorAll('tbody tr');

    if (rows.length === 0) {
        showToast('No data to export', 'warning');
        return;
    }

    let csv = 'SKU ID,Quantity,Destination,Order Date,Expected Arrival,Days Until,Status,Order Type,Notes\n';

    rows.forEach(row => {
        const cells = row.querySelectorAll('td');
        const rowData = [
            cells[0].textContent.trim(), // SKU ID
            cells[1].textContent.trim(), // Quantity
            cells[2].textContent.trim(), // Destination
            cells[3].textContent.trim(), // Order Date
            cells[4].textContent.trim(), // Expected Arrival
            cells[5].textContent.trim(), // Days Until (strip HTML)
            cells[6].textContent.trim(), // Status (strip badge)
            cells[7].textContent.trim(), // Order Type
            `"${cells[8].textContent.trim()}"` // Notes (quoted for commas)
        ];
        csv += rowData.join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pending_orders_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    showToast('CSV exported successfully', 'success');
}
```

**Acceptance Criteria**:
- Export includes current filtered data only
- CSV format is valid and opens in Excel
- Filename includes current date
- Empty table shows warning instead of exporting
- Success message displays after download

---

### TASK-394: Implement Clear All Orders with confirmation
**Status**: [ ] Pending
**Description**: Admin function to delete all pending orders
**API Endpoint**: `POST /api/admin/clear-pending-orders`

**Security**:
- Double confirmation required
- Admin-only function (consider adding password prompt)
- Shows total count before clearing

**Implementation**:
```javascript
async function clearAllOrders() {
    const firstConfirm = confirm('WARNING: This will delete ALL pending orders. Are you absolutely sure?');
    if (!firstConfirm) return;

    // Get total count
    const summary = await fetch('/api/pending-orders/summary').then(r => r.json());

    const secondConfirm = confirm(`This will permanently delete ${summary.total_orders} pending orders. This cannot be undone. Continue?`);
    if (!secondConfirm) return;

    try {
        const response = await fetch('/api/admin/clear-pending-orders', {
            method: 'POST'
        });

        if (!response.ok) throw new Error('Failed to clear orders');

        showToast('All pending orders cleared', 'success');
        loadPendingOrders();
        loadSummaryMetrics();

    } catch (error) {
        console.error('Error clearing orders:', error);
        showToast('Failed to clear orders', 'danger');
    }
}
```

**Acceptance Criteria**:
- Requires two confirmation dialogs
- Shows total count in second confirmation
- Clears all orders from database
- Table shows "No orders found" after clearing
- Metrics all show zero

---

## Phase 6: Navigation and Integration

### TASK-395: Update data-management.html navigation
**Status**: [ ] Pending
**Description**: Update placeholder function to navigate to new page
**File**: `frontend/data-management.html`
**Line**: 1897

**Change**:
```javascript
// OLD:
function showAllPendingOrders() {
    alert('Full pending orders management interface coming soon!');
}

// NEW:
function showAllPendingOrders() {
    window.location.href = '/static/pending-orders.html';
}
```

**Acceptance Criteria**:
- "View All" button navigates to new page
- Navigation occurs without errors
- Browser history works (back button returns to data-management)

---

## Testing Phase

### Browser Testing with Playwright

**Test Scenarios**:
1. Page loads and displays data correctly
2. Summary metrics match database counts
3. Global SKU search filters table
4. Status filter dropdown works
5. Destination filter dropdown works
6. Date range filters work
7. Overdue toggle works
8. Apply Filters updates table and metrics
9. Clear Filters resets everything
10. Add New Order creates order successfully
11. Edit Order updates order successfully
12. Delete Order removes order with confirmation
13. Bulk Delete by SKU removes all orders for SKU
14. Export CSV downloads valid file
15. Clear All Orders removes all orders (with double confirm)
16. DataTable sorting works on all columns
17. DataTable pagination works
18. Status badges display correct colors
19. Days Until calculation is accurate
20. Overdue orders highlighted correctly

---

## Success Metrics

**Performance**:
- Page load time: <2 seconds
- Filter application: <1 second
- Export CSV: <5 seconds (for 200+ orders)
- API response times: <500ms

**Functionality**:
- All CRUD operations work correctly
- Filters produce accurate results
- Bulk operations complete successfully
- No JavaScript console errors

**User Experience**:
- Interface is intuitive and requires no training
- Color coding makes status immediately visible
- Search and filters are fast and responsive
- Error messages are clear and actionable

---

## Files Modified/Created

### New Files:
- `frontend/pending-orders.html` (~850 lines)

### Modified Files:
- `frontend/data-management.html` (line 1897)
- `frontend/index.html` (optional: add navigation link)

### No Backend Changes:
All API endpoints already exist in `backend/main.py`

---

## Next Steps After Completion

1. User acceptance testing
2. Performance optimization if needed
3. Consider adding:
   - Batch status updates (select multiple rows, update status)
   - Received date tracking
   - Order history/audit log
   - Email notifications for overdue orders
   - Integration with forecasting system

---

## Notes

- Follow project coding standards (no emojis)
- Add comprehensive code documentation
- Test with 200+ pending orders for performance
- Ensure responsive design works on tablet
- Consider future enhancement: direct SKU linking to SKU details page

---

**Last Updated**: 2025-11-09
**Next Task**: TASK-378 (Create base HTML structure)
