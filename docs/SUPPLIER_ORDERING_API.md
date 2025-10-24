# Supplier Ordering API Reference

**Version:** 9.0
**Last Updated:** 2025-10-22
**Base URL:** `http://localhost:8000`

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Endpoints](#endpoints)
   - [Generate Recommendations](#post-apisupplier-ordersgenerate)
   - [Get Orders List](#get-apisupplier-ordersorder_month)
   - [Update Order](#put-apisupplier-ordersorder_id)
   - [Lock Order](#post-apisupplier-ordersorder_idlock)
   - [Unlock Order](#post-apisupplier-ordersorder_idunlock)
   - [Get Summary](#get-apisupplier-ordersorder_monthsummary)
   - [Export to Excel](#get-apisupplier-ordersorder_monthexcel)
4. [Data Models](#data-models)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [Examples](#examples)

---

## Overview

The Supplier Ordering API provides endpoints for managing monthly supplier order recommendations. The system analyzes inventory levels, pending orders, forecasted demand, and generates intelligent order suggestions with urgency prioritization.

### Key Features

- **Automated Recommendation Generation:** Analyzes all active SKUs across warehouses
- **Intelligent Urgency Levels:** Must Order, Should Order, Optional, Skip
- **Inline Editing:** Update quantities, lead times, and dates via API
- **Order Locking:** Prevent accidental changes to confirmed orders
- **Excel Export:** Professional formatted exports grouped by supplier
- **Pagination & Filtering:** Efficient data retrieval with multiple filter options

### Workflow

```
1. POST /generate       → Generate monthly recommendations
2. GET /{month}         → Retrieve and filter recommendations
3. PUT /{order_id}      → Adjust quantities and dates
4. POST /{id}/lock      → Lock confirmed orders
5. GET /{month}/excel   → Export for supplier ordering
```

---

## Authentication

**Current Version:** No authentication required (development mode)

**Production:** Will implement JWT token-based authentication

```http
Authorization: Bearer {token}
```

---

## Endpoints

### POST /api/supplier-orders/generate

Generate monthly supplier order recommendations for all active SKUs.

**Request Body:**

```json
{
  "order_month": "2025-11"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| order_month | string | Yes | Order month in YYYY-MM format |

**Response:** `200 OK`

```json
{
  "success": true,
  "order_month": "2025-11",
  "total_generated": 1247,
  "must_order_count": 24,
  "should_order_count": 45,
  "optional_count": 82,
  "skip_count": 1096,
  "execution_time_seconds": 12.34,
  "message": "Successfully generated 1247 order recommendations"
}
```

**Error Responses:**

- `400 Bad Request` - Invalid order_month format
- `500 Internal Server Error` - Generation failed

**Example:**

```bash
curl -X POST http://localhost:8000/api/supplier-orders/generate \
  -H "Content-Type: application/json" \
  -d '{"order_month": "2025-11"}'
```

---

### GET /api/supplier-orders/{order_month}

Retrieve paginated list of supplier order recommendations with filtering and sorting.

**URL Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| order_month | string | Yes | - | Order month (YYYY-MM) |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| page | integer | No | 1 | Page number (1-indexed) |
| page_size | integer | No | 50 | Items per page (max 500) |
| warehouse | string | No | - | Filter by warehouse (burnaby/kentucky) |
| supplier | string | No | - | Filter by supplier name |
| urgency | string | No | - | Filter by urgency (must_order/should_order/optional/skip) |
| search | string | No | - | Search SKU ID or description |
| sort_by | string | No | urgency_level | Sort column |
| sort_order | string | No | desc | Sort direction (asc/desc) |

**Valid sort_by values:**
- `sku_id`, `warehouse`, `supplier`, `urgency_level`
- `suggested_qty`, `confirmed_qty`, `coverage_months`
- `stockout_risk_date`, `suggested_value`, `confirmed_value`

**Response:** `200 OK`

```json
{
  "total": 1247,
  "page": 1,
  "page_size": 50,
  "total_pages": 25,
  "orders": [
    {
      "id": 12345,
      "sku_id": "UB-YTX14-BS",
      "description": "12V 14Ah AGM Battery",
      "warehouse": "kentucky",
      "supplier": "Upstart Battery",
      "current_inventory": 12,
      "pending_orders_raw": 100,
      "pending_orders_effective": 75,
      "pending_breakdown": {
        "total_qty": 100,
        "order_count": 2,
        "earliest_arrival": "2025-11-15",
        "overdue_count": 0,
        "confidence_avg": 0.85
      },
      "corrected_demand_monthly": 45.5,
      "safety_stock_qty": 15,
      "reorder_point": 60,
      "suggested_qty": 100,
      "confirmed_qty": 100,
      "order_month": "2025-11",
      "days_in_month": 30,
      "lead_time_days_default": 60,
      "lead_time_days_override": null,
      "expected_arrival_calculated": "2026-01-10",
      "expected_arrival_override": null,
      "effective_lead_time": 60,
      "coverage_months": 4.2,
      "urgency_level": "should_order",
      "overdue_pending_count": 0,
      "stockout_risk_date": "2025-12-15",
      "is_locked": false,
      "locked_by": null,
      "locked_at": null,
      "notes": null,
      "abc_code": "A",
      "xyz_code": "Y",
      "unit_cost": 24.50,
      "sku_status": "Active",
      "suggested_value": 2450.00,
      "confirmed_value": 2450.00,
      "created_at": "2025-10-22T10:30:00",
      "updated_at": "2025-10-22T10:30:00"
    }
  ]
}
```

**Error Responses:**

- `400 Bad Request` - Invalid order_month format or parameters
- `404 Not Found` - No orders found for specified month

**Example:**

```bash
# Get first page of must-order items for Kentucky
curl "http://localhost:8000/api/supplier-orders/2025-11?\
page=1&page_size=50&warehouse=kentucky&urgency=must_order"
```

---

### PUT /api/supplier-orders/{order_id}

Update order quantities, lead time overrides, expected arrival dates, and notes.

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| order_id | integer | Yes | Order confirmation ID |

**Request Body:**

```json
{
  "confirmed_qty": 150,
  "lead_time_days_override": 45,
  "expected_arrival_override": "2025-12-15",
  "notes": "Rush order - confirmed with supplier"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| confirmed_qty | integer | No | Confirmed order quantity |
| lead_time_days_override | integer | No | Custom lead time in days |
| expected_arrival_override | string | No | Custom arrival date (YYYY-MM-DD) |
| notes | string | No | Order notes or instructions |

**Note:** At least one field must be provided.

**Response:** `200 OK`

```json
{
  "message": "Order updated successfully",
  "order_id": 12345
}
```

**Error Responses:**

- `400 Bad Request` - No fields to update or invalid values
- `403 Forbidden` - Order is locked
- `404 Not Found` - Order not found

**Example:**

```bash
curl -X PUT http://localhost:8000/api/supplier-orders/12345 \
  -H "Content-Type: application/json" \
  -d '{
    "confirmed_qty": 150,
    "notes": "Increased quantity due to promotion"
  }'
```

---

### POST /api/supplier-orders/{order_id}/lock

Lock an order to prevent further editing.

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| order_id | integer | Yes | Order confirmation ID |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| username | string | Yes | User performing the lock |

**Response:** `200 OK`

```json
{
  "message": "Order locked successfully",
  "order_id": 12345,
  "locked_by": "john.doe"
}
```

**Error Responses:**

- `400 Bad Request` - Username not provided
- `404 Not Found` - Order not found
- `409 Conflict` - Order already locked

**Example:**

```bash
curl -X POST "http://localhost:8000/api/supplier-orders/12345/lock?username=john.doe"
```

---

### POST /api/supplier-orders/{order_id}/unlock

Unlock a previously locked order.

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| order_id | integer | Yes | Order confirmation ID |

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| username | string | Yes | User performing the unlock |

**Response:** `200 OK`

```json
{
  "message": "Order unlocked successfully",
  "order_id": 12345,
  "unlocked_by": "john.doe"
}
```

**Error Responses:**

- `400 Bad Request` - Username not provided
- `404 Not Found` - Order not found
- `409 Conflict` - Order not locked

**Example:**

```bash
curl -X POST "http://localhost:8000/api/supplier-orders/12345/unlock?username=john.doe"
```

---

### GET /api/supplier-orders/{order_month}/summary

Get summary statistics for a specific order month.

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| order_month | string | Yes | Order month (YYYY-MM) |

**Response:** `200 OK`

```json
{
  "order_month": "2025-11",
  "total_skus": 1247,
  "must_order_count": 24,
  "should_order_count": 45,
  "optional_count": 82,
  "skip_count": 1096,
  "total_suggested_value": 245678.50,
  "total_confirmed_value": 238450.25,
  "locked_orders": 12,
  "overdue_pending_total": 3,
  "suppliers": [
    {
      "supplier": "Upstart Battery",
      "sku_count": 145,
      "total_suggested_qty": 5420,
      "total_confirmed_qty": 5280,
      "suggested_value": 125678.50,
      "confirmed_value": 122340.00,
      "must_order_count": 8
    },
    {
      "supplier": "Yuasa",
      "sku_count": 98,
      "total_suggested_qty": 3210,
      "total_confirmed_qty": 3150,
      "suggested_value": 78456.00,
      "confirmed_value": 76890.00,
      "must_order_count": 5
    }
  ]
}
```

**Error Responses:**

- `400 Bad Request` - Invalid order_month format

**Example:**

```bash
curl "http://localhost:8000/api/supplier-orders/2025-11/summary"
```

---

### GET /api/supplier-orders/{order_month}/excel

Export supplier order recommendations to Excel with supplier grouping.

**URL Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| order_month | string | Yes | Order month (YYYY-MM) |

**Response:** `200 OK`

**Content-Type:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

**Headers:**
```
Content-Disposition: attachment; filename=supplier_orders_2025-11.xlsx
```

**Excel File Structure:**

**Sheet 1: Supplier Orders**
- Orders grouped by supplier
- Color-coded urgency levels (red/orange/yellow/green)
- Editable fields highlighted in light blue
- Frozen header row

**Columns:**
1. SKU ID
2. Description
3. Warehouse
4. Supplier
5. Current Stock
6. Pending (Eff)
7. Suggested Qty
8. Confirmed Qty (editable)
9. Lead Time (days) (editable)
10. Expected Arrival (editable)
11. Coverage (months)
12. Urgency Level
13. Notes (editable)

**Sheet 2: Legend & Instructions**
- Urgency level definitions
- Editable field descriptions
- Ordering instructions

**Error Responses:**

- `400 Bad Request` - Invalid order_month format
- `500 Internal Server Error` - Excel generation failed

**Example:**

```bash
# Download Excel file
curl "http://localhost:8000/api/supplier-orders/2025-11/excel" \
  -o supplier_orders_2025-11.xlsx
```

---

## Data Models

### OrderConfirmation

```typescript
interface OrderConfirmation {
  id: number;                          // Auto-increment primary key
  sku_id: string;                      // Product identifier
  warehouse: "burnaby" | "kentucky";   // Destination warehouse
  suggested_qty: number;               // System recommendation
  confirmed_qty: number;               // User-confirmed quantity
  supplier: string;                    // Supplier name
  current_inventory: number;           // On-hand inventory
  pending_orders_raw: number;          // Total pending quantity
  pending_orders_effective: number;    // Time-weighted pending
  pending_breakdown: PendingBreakdown | null;  // Pending details
  corrected_demand_monthly: number;    // Stockout-corrected demand
  safety_stock_qty: number;            // Safety stock level
  reorder_point: number;               // Reorder trigger point
  order_month: string;                 // YYYY-MM format
  days_in_month: number;               // Days in order month
  lead_time_days_default: number;      // Default lead time
  lead_time_days_override: number | null;  // Custom lead time
  expected_arrival_calculated: string | null;  // YYYY-MM-DD
  expected_arrival_override: string | null;    // YYYY-MM-DD
  coverage_months: number;             // Months of coverage
  urgency_level: UrgencyLevel;         // Priority level
  overdue_pending_count: number;       // Count of overdue orders
  stockout_risk_date: string | null;   // YYYY-MM-DD
  is_locked: boolean;                  // Lock status
  locked_by: string | null;            // User who locked
  locked_at: string | null;            // Timestamp of lock
  notes: string | null;                // Order notes
  created_at: string;                  // ISO timestamp
  updated_at: string;                  // ISO timestamp
}
```

### PendingBreakdown

```typescript
interface PendingBreakdown {
  total_qty: number;           // Sum of all pending orders
  order_count: number;         // Number of pending orders
  earliest_arrival: string;    // YYYY-MM-DD of first arrival
  overdue_count: number;       // Count of overdue orders
  confidence_avg: number;      // Average confidence score (0-1)
}
```

### UrgencyLevel

```typescript
type UrgencyLevel = "must_order" | "should_order" | "optional" | "skip";
```

**Definitions:**
- **must_order:** Critical - will run out before next order cycle
- **should_order:** Recommended - low stock, order soon
- **optional:** Stock adequate but could benefit from ordering
- **skip:** Well stocked, no order needed

### GenerateRecommendationsResponse

```typescript
interface GenerateRecommendationsResponse {
  success: boolean;
  order_month: string;
  total_generated: number;
  must_order_count: number;
  should_order_count: number;
  optional_count: number;
  skip_count: number;
  execution_time_seconds: number;
  message: string;
}
```

### SummaryResponse

```typescript
interface SummaryResponse {
  order_month: string;
  total_skus: number;
  must_order_count: number;
  should_order_count: number;
  optional_count: number;
  skip_count: number;
  total_suggested_value: number;
  total_confirmed_value: number;
  locked_orders: number;
  overdue_pending_total: number;
  suppliers: SupplierSummary[];
}

interface SupplierSummary {
  supplier: string;
  sku_count: number;
  total_suggested_qty: number;
  total_confirmed_qty: number;
  suggested_value: number;
  confirmed_value: number;
  must_order_count: number;
}
```

---

## Error Handling

### Error Response Format

```json
{
  "detail": "Error message describing the issue"
}
```

### HTTP Status Codes

| Code | Description | Common Causes |
|------|-------------|---------------|
| 200 | Success | Request completed successfully |
| 400 | Bad Request | Invalid parameters, malformed JSON |
| 403 | Forbidden | Attempting to edit locked order |
| 404 | Not Found | Order or month not found |
| 409 | Conflict | Lock/unlock operation conflict |
| 500 | Internal Server Error | Database error, calculation failure |

### Common Error Scenarios

**Invalid Date Format:**
```json
{
  "detail": "Invalid order_month format. Use YYYY-MM"
}
```

**Locked Order Edit Attempt:**
```json
{
  "detail": "Order is locked by john.doe"
}
```

**No Fields to Update:**
```json
{
  "detail": "No fields to update"
}
```

**Generation Failure:**
```json
{
  "detail": "Failed to generate recommendations: Database connection error"
}
```

---

## Rate Limiting

**Current Version:** No rate limiting implemented

**Future Implementation:**
- 100 requests per minute per IP
- 1000 requests per hour per user
- Bulk operations counted as single request

---

## Examples

### Complete Workflow Example

```python
import requests
import json

BASE_URL = "http://localhost:8000/api/supplier-orders"

# Step 1: Generate recommendations
response = requests.post(f"{BASE_URL}/generate", json={
    "order_month": "2025-11"
})
print(f"Generated {response.json()['total_generated']} recommendations")

# Step 2: Get summary
summary = requests.get(f"{BASE_URL}/2025-11/summary").json()
print(f"Must order: {summary['must_order_count']} SKUs")

# Step 3: Get must-order items
orders = requests.get(f"{BASE_URL}/2025-11", params={
    "urgency": "must_order",
    "page": 1,
    "page_size": 50
}).json()

# Step 4: Update an order
if orders['orders']:
    order_id = orders['orders'][0]['id']
    update = requests.put(f"{BASE_URL}/{order_id}", json={
        "confirmed_qty": 150,
        "notes": "Increased for promotion"
    })
    print(f"Updated order {order_id}: {update.json()['message']}")

    # Step 5: Lock the order
    lock = requests.post(f"{BASE_URL}/{order_id}/lock", params={
        "username": "api_user"
    })
    print(f"Locked order: {lock.json()['message']}")

# Step 6: Export to Excel
response = requests.get(f"{BASE_URL}/2025-11/excel")
with open("supplier_orders_2025-11.xlsx", "wb") as f:
    f.write(response.content)
print("Excel file downloaded")
```

### JavaScript/Fetch Example

```javascript
// Generate recommendations
async function generateOrders(month) {
    const response = await fetch('/api/supplier-orders/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_month: month })
    });
    return await response.json();
}

// Get filtered orders
async function getOrders(month, filters = {}) {
    const params = new URLSearchParams({
        page: 1,
        page_size: 50,
        ...filters
    });

    const response = await fetch(`/api/supplier-orders/${month}?${params}`);
    return await response.json();
}

// Update order
async function updateOrder(orderId, updates) {
    const response = await fetch(`/api/supplier-orders/${orderId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
    });
    return await response.json();
}

// Usage
const result = await generateOrders('2025-11');
const mustOrders = await getOrders('2025-11', { urgency: 'must_order' });
await updateOrder(12345, { confirmed_qty: 150 });
```

---

## Changelog

### V9.0 (2025-10-22)
- Initial release of Supplier Ordering API
- Generate recommendations endpoint
- CRUD operations for orders
- Lock/unlock functionality
- Excel export with supplier grouping
- Comprehensive filtering and pagination

### Future Enhancements
- Excel import (re-import edited orders)
- Bulk update operations
- WebSocket support for real-time updates
- API authentication and authorization
- Webhook notifications for order events
- GraphQL endpoint option

---

## Support

For API issues or questions:
- **Documentation:** This file + SUPPLIER_ORDERING_USER_GUIDE.md
- **Code Reference:** backend/supplier_ordering_api.py
- **Database Schema:** Run `DESCRIBE supplier_order_confirmations;`
- **Bug Reports:** Create issue with API request/response details

---

**Document Version:** 1.0
**Task:** TASK-390 - V9.0 Supplier Ordering API Documentation
