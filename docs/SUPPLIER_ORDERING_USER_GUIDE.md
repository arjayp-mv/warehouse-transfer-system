# Supplier Ordering System - User Guide

**Version:** 9.0
**Last Updated:** 2025-10-22
**Feature:** Monthly Supplier Order Recommendations

---

## Table of Contents

1. [Overview](#overview)
2. [Accessing the System](#accessing-the-system)
3. [Monthly Ordering Workflow](#monthly-ordering-workflow)
4. [Understanding the Interface](#understanding-the-interface)
5. [Working with Recommendations](#working-with-recommendations)
6. [SKU Details and Analysis](#sku-details-and-analysis)
7. [Exporting Orders](#exporting-orders)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)
10. [FAQ](#faq)

---

## Overview

The Supplier Ordering System automates monthly supplier order recommendations based on:
- Current inventory levels at both warehouses (Burnaby and Kentucky)
- Pending supplier orders already in the pipeline
- Forecasted demand with stockout corrections
- Historical sales patterns
- ABC-XYZ product classification
- Supplier lead times (P95 statistical vs. supplier estimates)

### Key Benefits

- **Time Savings:** Reduces ordering time from hours to under 30 minutes
- **Data-Driven:** Uses advanced forecasting with stockout correction
- **Intelligent Prioritization:** Urgency levels highlight critical orders
- **Supplier Grouping:** Excel exports organized by supplier for easy ordering
- **Audit Trail:** Tracks all changes with locked order confirmation

---

## Accessing the System

### Navigation

1. **From Dashboard:** Click the "Supplier Ordering" button in Quick Actions
2. **Direct URL:** Navigate to `http://localhost:8000/static/supplier-ordering.html`
3. **From Transfer Planning:** Use the navigation bar link "Supplier Ordering"

### System Requirements

- Modern web browser (Chrome, Firefox, Edge, Safari)
- Network access to the application server
- Recommended screen resolution: 1920x1080 or higher

---

## Monthly Ordering Workflow

### Step 1: Generate Recommendations

1. **Select Order Month**
   - Click the month selector at the top of the page
   - Choose the month you want to generate orders for (typically next month)

2. **Click "Generate Recommendations"**
   - System analyzes all active SKUs across both warehouses
   - Calculations typically complete in 5-15 seconds depending on SKU count
   - Progress shown via loading overlay

3. **Review Summary Cards**
   - After generation, summary cards display:
     - **Must Order** (Red): Critical - will run out before next cycle
     - **Should Order** (Orange): Recommended - low stock
     - **Optional** (Yellow): Could benefit from ordering
     - **Skip** (Green): Well stocked, no order needed

### Step 2: Filter and Review

Use the filter controls to focus on specific segments:

- **Warehouse Filter:** Burnaby or Kentucky
- **Supplier Filter:** Select specific supplier
- **Urgency Filter:** Must Order, Should Order, Optional, or Skip
- **Search Box:** Find specific SKU by ID or description

### Step 3: Adjust Quantities

1. **Review Suggested Quantities**
   - System suggests quantities based on:
     - Forecasted demand
     - Current inventory position
     - Pending orders in pipeline
     - Target coverage months (varies by ABC-XYZ class)

2. **Modify Confirmed Quantities**
   - Click the "Confirmed Qty" field (light blue background)
   - Enter your adjusted quantity
   - System auto-saves after 500ms
   - Coverage months recalculate automatically

3. **Override Lead Times** (if needed)
   - Click "Lead Time (days)" field
   - Enter supplier-specific lead time
   - Expected arrival date updates automatically

4. **Set Custom Arrival Dates**
   - Click "Expected Arrival" field
   - Select date from calendar picker
   - Useful when you have confirmed delivery dates

5. **Add Notes**
   - Click "Notes" field
   - Add special instructions or order details
   - Examples: "Rush order", "Split delivery", "Special packaging"

### Step 4: Lock Confirmed Orders

1. **Lock Orders**
   - Click the lock icon next to each confirmed order
   - Locked orders cannot be edited (prevents accidental changes)
   - Locked orders are ready for submission to suppliers

2. **Unlock if Needed**
   - Click the locked icon to unlock
   - Make any necessary adjustments
   - Re-lock when confirmed

### Step 5: Export and Order

1. **Click "Export to Excel"**
   - Generates formatted Excel file
   - Orders grouped by supplier
   - Color-coded urgency levels
   - Editable fields highlighted

2. **Review Excel File**
   - Sheet 1: Supplier Orders (grouped by supplier)
   - Sheet 2: Legend & Instructions
   - Use for placing actual orders with suppliers

3. **Place Orders**
   - Contact suppliers or use their online systems
   - Reference the Excel export
   - Update order statuses in system as orders are placed

---

## Understanding the Interface

### Summary Cards (Top of Page)

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ Must Order  │Should Order │  Optional   │    Skip     │
│    (Red)    │  (Orange)   │  (Yellow)   │   (Green)   │
│     24      │     45      │     82      │     156     │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

- **Must Order:** Immediate action required - stockout risk
- **Should Order:** Recommended to order soon - low coverage
- **Optional:** Stock adequate but could benefit from ordering
- **Skip:** Well stocked - no order needed this cycle

### Main Data Table

| Column | Description | Editable |
|--------|-------------|----------|
| SKU | Product identifier | No |
| Description | Product name | No |
| Warehouse | Burnaby or Kentucky | No |
| Supplier | Supplier name | No |
| Current Stock | On-hand inventory | No |
| Pending (Eff) | Effective pending orders | No |
| Suggested Qty | System recommendation | No |
| Confirmed Qty | Your adjusted quantity | **Yes** |
| Lead Time (days) | Days until delivery | **Yes** |
| Expected Arrival | Projected delivery date | **Yes** |
| Coverage (mo) | Months of stock after order | No |
| Urgency | Priority level | No |
| Actions | Lock/unlock buttons | **Yes** |

### Color Coding

- **Red Row Background:** Must Order urgency
- **Orange Row Background:** Should Order urgency
- **Yellow Row Background:** Optional urgency
- **Green Row Background:** Skip urgency
- **Light Blue Cell Background:** Editable field

---

## Working with Recommendations

### Understanding Urgency Levels

**Must Order (Critical)**
- Current + pending inventory will run out before next order cycle
- Stockout risk date is within lead time + safety buffer
- **Action Required:** Order immediately or increase confirmed quantity

**Should Order (Recommended)**
- Coverage is below target but not critical
- Current trajectory suggests ordering now is optimal
- **Action Required:** Review and confirm suggested quantity

**Optional (Consider)**
- Stock adequate but could benefit from ordering
- Economic order quantity or supplier minimum may apply
- **Action Required:** Evaluate based on supplier terms and cash flow

**Skip (Well Stocked)**
- Current + pending inventory exceeds target coverage
- No order needed this cycle
- **Action Required:** Verify and skip to next SKU

### Coverage Months Explained

Coverage months = (Current Inventory + Pending + Confirmed Order) / Monthly Demand

**Target Coverage by Classification:**
- **A-X (High value, stable demand):** 3-4 months
- **A-Y (High value, variable demand):** 4-6 months
- **A-Z (High value, erratic demand):** 6-8 months
- **B-X (Medium value, stable demand):** 4-5 months
- **B-Y (Medium value, variable demand):** 5-7 months
- **B-Z (Medium value, erratic demand):** 7-9 months
- **C-X (Low value, stable demand):** 6-9 months
- **C-Y (Low value, variable demand):** 9-12 months
- **C-Z (Low value, erratic demand):** 12+ months

### Pending Orders Confidence

The system displays "Pending (Eff)" which accounts for:
- **Time-based confidence scoring:** Orders arriving soon have higher weight
- **Statistical lead time (P95):** Uses 95th percentile, not supplier estimate
- **Overdue orders:** Flagged and de-weighted in calculations

---

## SKU Details and Analysis

### Opening SKU Details Modal

Click any SKU ID link in the main table to open detailed analysis.

### Overview Tab

Displays key metrics:
- Current stock levels at both warehouses
- Pending orders with arrival timeline
- Latest forecast values
- ABC-XYZ classification
- Supplier information and lead times

### Pending Orders Tab

Visual timeline of all pending orders:
- Order date and expected arrival
- Quantity and destination
- Confidence score (based on timing)
- Overdue flag if applicable

**Example Timeline:**
```
Order #1234 - 500 units
├── Ordered: 2025-09-15
├── Expected: 2025-10-30 (P95: 45 days)
├── Status: On track
└── Confidence: 95%

Order #1235 - 300 units
├── Ordered: 2025-08-20
├── Expected: 2025-09-25 (Overdue by 27 days)
├── Status: Overdue
└── Confidence: 40%
```

### 12-Month Forecast Tab

Interactive Chart.js line chart showing:
- Forecasted demand for next 12 months
- Seasonal patterns if detected
- Growth trends if applicable
- Method used (min-max, Holt-Winters, ARIMA, etc.)

**Interpretation:**
- **Flat line:** Stable demand (XYZ: X)
- **Regular waves:** Seasonal pattern detected
- **Upward trend:** Growing demand
- **Downward trend:** Declining demand

### Stockout History Tab

Historical stockout incidents:
- Stockout start date
- Resolution date (if resolved)
- Days out of stock
- Impact assessment (High/Medium/Low)

**Use this to:**
- Identify chronic stockout issues
- Validate stockout correction factors
- Adjust coverage targets for problem SKUs

---

## Exporting Orders

### Excel Export Features

**Sheet 1: Supplier Orders**
- Orders grouped by supplier (visual separator rows)
- Color-coded urgency levels (red/orange/yellow/green)
- Editable fields highlighted in light blue
- Frozen header row for easy scrolling
- Pre-sized columns for readability

**Sheet 2: Legend & Instructions**
- Urgency level definitions
- Editable field descriptions
- Step-by-step ordering instructions
- Quick reference guide

### Using the Excel Export

1. **For Supplier Communication:**
   - Filter to specific supplier in Excel
   - Copy/paste relevant rows into email or PO system
   - Include notes column for special instructions

2. **For Review Meetings:**
   - Print or share Excel file
   - Use as discussion document
   - Highlight critical must-order items

3. **For Record Keeping:**
   - Save monthly exports with date stamp
   - Track changes month-over-month
   - Audit historical ordering decisions

**Future Enhancement:** Excel import back to system (coming soon)

---

## Best Practices

### Monthly Ordering Cycle

**Recommended Timeline:**
1. **Day 1-2:** Generate recommendations for next month
2. **Day 3-5:** Review and adjust quantities
3. **Day 6-7:** Lock confirmed orders
4. **Day 8-10:** Export and place orders with suppliers
5. **Day 11+:** Track order confirmations and update arrival dates

### Tips for Efficient Ordering

1. **Start with Must Orders:**
   - Filter by urgency level = "Must Order"
   - Confirm these first to prevent stockouts
   - Lock them immediately

2. **Review by Supplier:**
   - Filter by supplier to batch orders
   - Check for supplier minimums or MOQ
   - Negotiate combined shipping if possible

3. **Consider Cash Flow:**
   - Optional items can be deferred if cash is tight
   - Balance inventory investment with stockout risk
   - Discuss payment terms with suppliers

4. **Override When Needed:**
   - System suggestions are data-driven but not perfect
   - Use your expertise on seasonal promotions
   - Adjust for known supplier issues or quality concerns

5. **Document Decisions:**
   - Use Notes field to explain deviations from suggestions
   - Track special arrangements or custom lead times
   - Create audit trail for future reference

### Working with Seasonal Products

For products with strong seasonality:
- System applies seasonal multipliers automatically
- Review 12-month forecast in SKU details
- Consider ordering early for peak season
- Adjust coverage targets for off-season

### Handling New Products

For new SKUs without historical data:
- System uses category averages or defaults
- Monitor closely for first 3-6 months
- Adjust coverage targets as data accumulates
- Consider supplier flexibility for new items

---

## Troubleshooting

### Common Issues

**Problem:** "No recommendations generated"
- **Cause:** No active SKUs or no sales data
- **Solution:** Verify SKUs are marked "Active" in system
- **Solution:** Check that sales data has been imported recently

**Problem:** "Suggested quantity seems too high/low"
- **Cause:** May be due to recent stockout correction or unusual demand
- **Solution:** Check SKU details modal for forecast explanation
- **Solution:** Review stockout history for correction factors
- **Solution:** Override with your judgment and add note

**Problem:** "Cannot edit confirmed quantity"
- **Cause:** Order is locked
- **Solution:** Click lock icon to unlock
- **Solution:** Verify you have edit permissions

**Problem:** "Excel export fails or is empty"
- **Cause:** No orders for selected month
- **Solution:** Verify orders exist for that month
- **Solution:** Try refreshing page and re-exporting
- **Solution:** Check browser console for errors

**Problem:** "Pending orders not showing in calculations"
- **Cause:** Pending orders may be marked as received or cancelled
- **Solution:** Verify order status in pending inventory
- **Solution:** Re-import pending orders CSV if needed

### Performance Issues

**Slow Loading (>10 seconds):**
- Clear browser cache
- Reduce page size (use filters)
- Contact admin if issue persists (may need database optimization)

**Auto-save not working:**
- Check network connection
- Verify you're not in a locked order row
- Wait full 500ms before clicking away from field

---

## FAQ

**Q: How often should I generate recommendations?**
A: Typically once per month, 7-10 days before you need to place orders. For bi-weekly busy seasons, generate every 2 weeks.

**Q: Can I change the coverage target for a specific SKU?**
A: Not currently in the UI, but contact admin to adjust ABC-XYZ classification or custom coverage settings in database.

**Q: What happens if I enter a negative confirmed quantity?**
A: System validation will reject negative values. Minimum is 0 (skip ordering).

**Q: Why does the system suggest ordering when we have pending orders?**
A: Pending orders are factored in, but if they arrive late or total coverage is still below target, additional orders may be needed.

**Q: How do I handle split shipments from suppliers?**
A: You can enter multiple confirmed quantities and use Notes to indicate "Part 1 of 2" or similar. Alternatively, create separate pending order records.

**Q: What if a supplier has a minimum order quantity?**
A: Adjust confirmed quantity to meet MOQ and add note. System will recalculate coverage automatically.

**Q: Can I import the Excel file back into the system?**
A: Not yet - this feature is planned for V9.1. Currently, you need to manually enter changes from Excel back into the UI.

**Q: How accurate is the P95 lead time vs. supplier estimate?**
A: P95 is based on historical actual arrivals and is typically more reliable than supplier estimates. It accounts for delays and variability.

**Q: What's the difference between 'Current Stock' and 'Pending (Eff)'?**
A: Current Stock is on-hand now. Pending (Eff) is time-weighted pending orders - orders arriving soon have more weight than distant orders.

**Q: Why does urgency level change after I adjust confirmed quantity?**
A: Urgency recalculates based on total coverage. If you order enough to reach target, urgency may downgrade from "must" to "should" or "skip".

---

## Support

For technical issues or questions:
- **Documentation:** Check CLAUDE.md and PRD-v2.md in docs folder
- **API Reference:** See SUPPLIER_ORDERING_API.md
- **Bug Reports:** Create issue in project repository
- **Feature Requests:** Discuss with product team

---

**Document Version:** 1.0
**Created:** 2025-10-22
**Task:** TASK-389 - V9.0 Supplier Ordering User Guide
