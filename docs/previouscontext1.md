     Executive Summary

     Build a monthly supplier ordering system that leverages your existing forecast accuracy learning, stockout tracking, and supplier lead       
     time statistics. The system will calculate separate order recommendations for Burnaby and Kentucky warehouses with editable lead times       
     and arrival dates.

     ---
     Phase 1: Database Schema (Week 1, Days 1-2)

     Task 1.1: Create supplier_order_confirmations Table

     Enhanced schema with monthly ordering and editability:

     CREATE TABLE supplier_order_confirmations (
       id INT PRIMARY KEY AUTO_INCREMENT,
       sku_id VARCHAR(50) NOT NULL,
       warehouse ENUM('burnaby', 'kentucky') NOT NULL,

       -- Core quantities
       suggested_qty INT NOT NULL COMMENT 'System-calculated quantity',
       confirmed_qty INT NOT NULL COMMENT 'User-editable quantity',
       supplier VARCHAR(100) NOT NULL,

       -- Calculation transparency
       current_inventory INT NOT NULL,
       pending_orders INT NOT NULL COMMENT 'Raw pending total',
       effective_pending INT NOT NULL COMMENT 'Time-phased adjusted pending',
       corrected_demand_monthly DECIMAL(10,2) COMMENT 'Stockout-corrected monthly demand',
       forecasted_demand_period DECIMAL(10,2) COMMENT 'Demand during lead time + review period',
       safety_stock_qty INT NOT NULL,
       reorder_point INT NOT NULL,

       -- Monthly ordering specific
       review_period_days INT DEFAULT 30 COMMENT 'Fixed at 30 for monthly ordering',
       lead_time_days INT NOT NULL COMMENT 'P95 lead time used for calculation',
       editable_lead_time INT COMMENT 'User-override lead time',
       expected_arrival DATE COMMENT 'Calculated or user-edited arrival date',
       coverage_months DECIMAL(4,2) COMMENT 'Coverage after order arrives',
       urgency_level ENUM('skip', 'optional', 'should_order', 'must_order') DEFAULT 'optional',

       -- Pending order details (JSON for transparency)
       pending_breakdown JSON COMMENT 'Time-phased pending order analysis',
       overdue_orders INT DEFAULT 0 COMMENT 'Count of overdue pending orders',
       ignored_future_qty INT DEFAULT 0 COMMENT 'Pending qty beyond planning horizon',

       -- Order context
       order_date DATE NOT NULL COMMENT 'Month this order plan was created',
       order_month VARCHAR(7) COMMENT 'YYYY-MM format for grouping monthly plans',
       stockout_risk_date DATE COMMENT 'Projected stockout if no order placed',

       -- User tracking
       is_locked BOOLEAN DEFAULT FALSE,
       locked_by VARCHAR(100),
       locked_at TIMESTAMP NULL,
       notes TEXT,

       -- Audit
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

       FOREIGN KEY (sku_id) REFERENCES skus(sku_id) ON DELETE CASCADE,
       INDEX idx_order_month (order_month, warehouse, supplier),
       INDEX idx_sku_warehouse_month (sku_id, warehouse, order_month),
       INDEX idx_urgency (urgency_level, order_month),
       INDEX idx_locked (is_locked, order_month)
     ) ENGINE=InnoDB COMMENT='Monthly supplier order recommendations with editable lead times';

     ---
     Phase 2: Backend Calculation Engine (Week 1-2, Days 3-7)

     Task 2.1: Monthly Order Calculation with Stockout Correction

     File: backend/supplier_ordering_calculations.py

     Key functions to implement:

     def calculate_monthly_order_recommendation(sku_id, warehouse, supplier, order_month):
         """
         Calculate order recommendation accounting for monthly constraint.
         
         Args:
             sku_id: SKU identifier
             warehouse: 'burnaby' or 'kentucky'
             supplier: Supplier name
             order_month: YYYY-MM format (e.g., '2025-11')
         
         Returns:
             dict with all calculation components
         """

         # 1. Get corrected demand using stockout_patterns table
         corrected_demand = get_stockout_corrected_demand(sku_id, warehouse)

         # 2. Get current inventory position
         current_inventory = get_current_inventory(sku_id, warehouse)

         # 3. Get time-phased pending inventory (with confidence scoring)
         pending_result = get_effective_pending_with_timing(sku_id, warehouse, supplier)

         # 4. Get dynamic lead time from supplier_lead_times
         lead_time_data = get_supplier_lead_time_stats(supplier, warehouse)
         planning_lead_time = lead_time_data['p95_lead_time']

         # 5. Calculate days of coverage
         daily_demand = corrected_demand / get_days_in_month(order_month)
         current_position = current_inventory + pending_result['effective_pending']
         days_of_coverage = current_position / daily_demand if daily_demand > 0 else 999

         # 6. Determine urgency based on monthly constraint
         urgency = determine_monthly_urgency(
             days_of_coverage,
             planning_lead_time,
             warehouse
         )

         # 7. Calculate order quantity if needed
         if urgency != 'skip':
             order_qty = calculate_monthly_order_quantity(
                 corrected_demand,
                 current_position,
                 planning_lead_time,
                 sku_id,
                 warehouse,
                 lead_time_data
             )
         else:
             order_qty = 0

         # 8. Calculate expected arrival (editable by user later)
         order_date = get_order_date_for_month(order_month)
         expected_arrival = order_date + timedelta(days=planning_lead_time)

         return {
             'suggested_qty': order_qty,
             'current_inventory': current_inventory,
             'effective_pending': pending_result['effective_pending'],
             'pending_breakdown': pending_result['detail'],
             'corrected_demand_monthly': corrected_demand,
             'urgency_level': urgency,
             'lead_time_days': planning_lead_time,
             'expected_arrival': expected_arrival,
             # ... all other transparency fields
         }


     def get_stockout_corrected_demand(sku_id, warehouse):
         """
         Use stockout_patterns to correct forecasted demand.
         Leverages existing tables: stockout_patterns, monthly_sales
         """
         # Query latest forecast with learning adjustments if available
         forecast = query("""
             SELECT fd.avg_monthly_qty,
                    fla.adjusted_value
             FROM forecast_details fd
             LEFT JOIN forecast_learning_adjustments fla 
                 ON fd.sku_id = fla.sku_id AND fla.applied = TRUE
             WHERE fd.sku_id = %s AND fd.warehouse = %s
             AND fd.forecast_run_id = (SELECT MAX(id) FROM forecast_runs)
         """, [sku_id, warehouse])

         base_demand = forecast['adjusted_value'] or forecast['avg_monthly_qty']

         # Check for recent stockouts
         stockout_data = query("""
             SELECT COUNT(*) as recent_stockouts,
                    SUM(DATEDIFF(COALESCE(resolved_date, CURDATE()), stockout_date)) as total_days
             FROM stockout_dates
             WHERE sku_id = %s AND warehouse = %s
             AND stockout_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
         """, [sku_id, warehouse])

         if stockout_data['recent_stockouts'] > 0:
             # Apply stockout correction (30% floor to prevent overcorrection)
             availability_rate = max(0.3, 1 - (stockout_data['total_days'] / 90))
             corrected_demand = base_demand / availability_rate
             # Cap at 50% uplift for extreme cases
             corrected_demand = min(corrected_demand, base_demand * 1.5)
         else:
             corrected_demand = base_demand

         return corrected_demand


     def get_effective_pending_with_timing(sku_id, warehouse, supplier):
         """
         Time-phased pending orders with confidence scoring.
         Only count orders arriving within planning horizon.
         """
         # Get planning horizon
         lead_time_data = get_supplier_lead_time_stats(supplier, warehouse)
         planning_horizon_days = lead_time_data['p95_lead_time'] + 30  # Lead time + review period

         # Query pending orders with timing
         pending_orders = query("""
             SELECT *,
                    DATEDIFF(expected_arrival, CURDATE()) as days_until_arrival,
                    CASE WHEN expected_arrival < CURDATE() AND status != 'received'
                        THEN 1 ELSE 0 END as is_overdue
             FROM pending_inventory
             WHERE sku_id = %s AND destination = %s
             AND order_type = 'supplier'
             AND status IN ('ordered', 'shipped', 'pending')
             ORDER BY expected_arrival
         """, [sku_id, warehouse])

         effective_pending = 0
         detail = []
         overdue_count = 0

         for order in pending_orders:
             days_to_arrival = order['days_until_arrival']

             # Categorize by timing
             if order['is_overdue']:
                 # Overdue orders: 80% confidence
                 confidence = 0.8
                 effective_pending += order['quantity'] * confidence
                 overdue_count += 1
                 detail.append({
                     'id': order['id'],
                     'quantity': order['quantity'],
                     'confidence': confidence,
                     'reason': f"Overdue by {-days_to_arrival} days"
                 })
             elif days_to_arrival <= 30:
                 # Imminent (within review period): 100% confidence
                 confidence = 1.0
                 effective_pending += order['quantity']
                 detail.append({
                     'id': order['id'],
                     'quantity': order['quantity'],
                     'confidence': confidence,
                     'reason': f"Arriving in {days_to_arrival} days"
                 })
             elif days_to_arrival <= planning_horizon_days:
                 # Within planning horizon: confidence based on supplier reliability
                 reliability = lead_time_data['reliability_score'] / 100
                 time_discount = 1 - (days_to_arrival / planning_horizon_days) * 0.2
                 confidence = reliability * time_discount
                 effective_pending += order['quantity'] * confidence
                 detail.append({
                     'id': order['id'],
                     'quantity': order['quantity'],
                     'confidence': confidence,
                     'reason': f"Lead time coverage, {reliability*100:.0f}% reliability"
                 })
             # Else: Beyond planning horizon, don't count

         return {
             'effective_pending': round(effective_pending),
             'detail': detail,
             'overdue_count': overdue_count
         }


     def calculate_monthly_order_quantity(corrected_demand, current_position, 
                                           lead_time_days, sku_id, warehouse, lead_time_data):
         """
         Order quantity calculation for monthly ordering cycle.
         Must cover: lead time + 60 days (2 months).
         """
         # Target coverage: lead time + 2 months (to last until next order arrives)
         target_coverage_days = lead_time_days + 60
         target_demand = (corrected_demand / 30) * target_coverage_days

         # Enhanced safety stock for monthly ordering
         safety_stock = calculate_monthly_safety_stock(
             sku_id,
             corrected_demand / 30,  # daily demand
             lead_time_days,
             lead_time_data
         )

         # Reorder point
         reorder_point = target_demand + safety_stock

         # Order quantity
         order_qty = max(0, reorder_point - current_position)

         # Round to multiples (same as transfer planning)
         if order_qty > 0:
             order_qty = round_to_multiple(sku_id, order_qty)

         return order_qty


     def calculate_monthly_safety_stock(sku_id, daily_demand, lead_time_days, lead_time_data):
         """
         Enhanced safety stock for monthly ordering.
         Accounts for: ABC-XYZ class, demand volatility, supplier reliability, monthly buffer.
         """
         # Get SKU characteristics
         sku_data = query("""
             SELECT s.abc_code, s.xyz_code, s.status,
                    sds.coefficient_variation as demand_cv
             FROM skus s
             LEFT JOIN sku_demand_stats sds ON s.sku_id = sds.sku_id
             WHERE s.sku_id = %s
         """, [sku_id])

         # Service levels by ABC-XYZ combination
         service_levels = {
             'AX': 2.33, 'AY': 2.05, 'AZ': 1.65,  # A-class: 99%, 98%, 95%
             'BX': 1.65, 'BY': 1.28, 'BZ': 1.04,  # B-class: 95%, 90%, 85%
             'CX': 1.04, 'CY': 0.84, 'CZ': 0.67   # C-class: 85%, 80%, 75%
         }

         abc_xyz = f"{sku_data['abc_code']}{sku_data['xyz_code']}"
         z_score = service_levels.get(abc_xyz, 1.65)  # Default 95%

         # Total period for safety stock calculation (lead time + review period)
         total_period_days = lead_time_days + 30

         # Demand uncertainty
         demand_cv = sku_data['demand_cv'] or 0.3
         demand_std_daily = daily_demand * demand_cv
         demand_std_period = demand_std_daily * math.sqrt(total_period_days)

         # Lead time uncertainty
         lt_cv = lead_time_data['coefficient_variation'] or 0.2

         # Combined safety stock formula
         safety_stock = z_score * math.sqrt(
             (demand_std_period ** 2) +
             ((daily_demand ** 2) * (lt_cv ** 2) * total_period_days)
         )

         # Monthly ordering buffer (extra week for critical items)
         if sku_data['abc_code'] == 'A':
             monthly_buffer = daily_demand * 7
             safety_stock += monthly_buffer

         # Reduce for Death Row items
         if sku_data['status'] == 'Death Row':
             safety_stock *= 0.5

         return math.ceil(safety_stock)


     def determine_monthly_urgency(days_of_coverage, lead_time_days, warehouse):
         """
         Determine if SKU must/should/can/skip ordering this month.
         Based on whether inventory will last until next month's order arrives.
         """
         if days_of_coverage < lead_time_days + 30:
             return 'must_order'  # Won't last until next month's order arrives
         elif days_of_coverage < lead_time_days + 60:
             return 'should_order'  # Cutting it close
         elif days_of_coverage < lead_time_days + 90:
             return 'optional'  # Could wait but safer to order
         else:
             return 'skip'  # Plenty of stock


     def get_days_in_month(year_month_str):
         """
         Get actual days in month (28-31, not fixed 30).
         Args: year_month_str in format 'YYYY-MM'
         """
         from calendar import monthrange
         year, month = map(int, year_month_str.split('-'))
         return monthrange(year, month)[1]

     ---
     Phase 3: API Endpoints (Week 2, Days 8-10)

     Task 3.1: Supplier Ordering API

     File: backend/supplier_ordering_api.py

     @app.get("/api/supplier-orders/recommendations")
     async def get_supplier_order_recommendations(
         order_month: str = Query(None, description="YYYY-MM format, defaults to current month"),
         supplier: str = None,
         status: str = None,
         warehouse: str = None,
         urgency: str = None
     ):
         """
         Get order recommendations for all SKUs for the specified month.
         Filters: supplier, status (Active/Death Row/Discontinued), warehouse, urgency
         """
         if not order_month:
             order_month = datetime.now().strftime('%Y-%m')

         # Check if recommendations already exist for this month
         existing = query("""
             SELECT COUNT(*) as count FROM supplier_order_confirmations
             WHERE order_month = %s
         """, [order_month])

         if existing['count'] == 0:
             # Generate recommendations for all SKUs
             generate_monthly_recommendations(order_month)

         # Fetch with filters
         where_clauses = ["soc.order_month = %s"]
         params = [order_month]

         if supplier:
             where_clauses.append("soc.supplier = %s")
             params.append(supplier)
         if status:
             where_clauses.append("s.status = %s")
             params.append(status)
         if warehouse:
             where_clauses.append("soc.warehouse = %s")
             params.append(warehouse)
         if urgency:
             where_clauses.append("soc.urgency_level = %s")
             params.append(urgency)

         results = query(f"""
             SELECT soc.*, s.description, s.category, s.abc_code, s.xyz_code, s.status
             FROM supplier_order_confirmations soc
             JOIN skus s ON soc.sku_id = s.sku_id
             WHERE {' AND '.join(where_clauses)}
             ORDER BY soc.urgency_level DESC, s.abc_code ASC, soc.suggested_qty DESC
         """, params)

         # Group by SKU (combine CA and KY data)
         grouped = group_by_sku(results)

         return {"success": True, "data": grouped, "order_month": order_month}


     @app.post("/api/supplier-orders/confirm")
     async def confirm_supplier_order(
         sku_id: str,
         warehouse: str,
         confirmed_qty: int,
         order_month: str,
         is_locked: bool = False,
         notes: str = None,
         editable_lead_time: int = None,
         editable_arrival: str = None  # YYYY-MM-DD format
     ):
         """
         Update confirmed quantity and lock status.
         Allows editing lead time and expected arrival date.
         """
         # Update record
         update_query = """
             UPDATE supplier_order_confirmations
             SET confirmed_qty = %s,
                 is_locked = %s,
                 notes = %s,
                 editable_lead_time = %s,
                 expected_arrival = %s,
                 locked_at = CASE WHEN %s THEN NOW() ELSE NULL END
             WHERE sku_id = %s AND warehouse = %s AND order_month = %s
         """

         execute(update_query, [
             confirmed_qty, is_locked, notes,
             editable_lead_time, editable_arrival,
             is_locked, sku_id, warehouse, order_month
         ])

         return {"success": True, "message": f"Order confirmed for {sku_id} ({warehouse})"}


     @app.post("/api/supplier-orders/update-arrival")
     async def update_expected_arrival(
         sku_id: str,
         warehouse: str,
         order_month: str,
         new_arrival_date: str,  # YYYY-MM-DD
         new_lead_time: int = None
     ):
         """
         Update expected arrival date and/or lead time.
         Recalculates urgency based on new timing.
         """
         # Update expected arrival
         query("""
             UPDATE supplier_order_confirmations
             SET expected_arrival = %s,
                 editable_lead_time = %s
             WHERE sku_id = %s AND warehouse = %s AND order_month = %s
         """, [new_arrival_date, new_lead_time, sku_id, warehouse, order_month])

         return {"success": True}


     @app.post("/api/supplier-orders/export")
     async def export_supplier_orders(
         order_month: str,
         format: str = "excel",  # excel or csv
         supplier: str = None,
         include_locked_only: bool = False,
         warehouses: list = ["burnaby", "kentucky"]
     ):
         """
         Export order plan to Excel/CSV grouped by supplier.
         """
         # Implementation for Excel/CSV export
         # Group by supplier, show CA and KY columns side by side
         # Include editable columns for lead time and arrival date
         pass

     ---
     Phase 4: Frontend UI (Week 2-3, Days 11-15)

     Task 4.1: Supplier Ordering Page

     File: frontend/supplier-ordering.html

     Key UI features:

     1. Month Selector - Choose which month to plan orders for
     2. Urgency Filtering - Filter by MUST_ORDER, SHOULD_ORDER, OPTIONAL, SKIP
     3. Editable Columns:
       - Confirmed Quantity (numeric input)
       - Expected Arrival Date (date picker)
       - Lead Time Days (numeric input)
     4. Dual Warehouse Columns:
       - CA Current / Pending / Position / To Order / Confirmed / Lock
       - KY Current / Pending / Position / To Order / Confirmed / Lock
     5. Time-Phased Pending Details - Expandable row showing pending order breakdown
     6. Lock/Unlock - Per warehouse per SKU
     7. Export - Excel with editable arrival dates

     Task 4.2: Enhanced SKU Details Modal

     Add tabs:
     - Pending Orders Timeline - Visual timeline of when pending orders arrive
     - Coverage Projection - Day-by-day inventory projection
     - Monthly Forecast - 12-month forecast from forecast_details

     ---
     Phase 5: Testing & Validation (Week 3-4, Days 16-20)

     Task 5.1: Calculation Validation

     1. Test with SKUs that have recent stockouts - verify demand correction
     2. Test with overdue pending orders - verify confidence discounting
     3. Test monthly coverage calculation - verify calendar-aware calculations
     4. Test urgency levels - verify MUST/SHOULD/OPTIONAL/SKIP logic

     Task 5.2: User Acceptance Testing

     1. Test editing lead times and recalculating orders
     2. Test lock/unlock workflow for monthly order cycle
     3. Test Excel export with editable fields
     4. Test with 4000+ SKUs for performance

     ---
     Implementation Notes

     Differences from Original Plan:
     - ✅ Uses EXISTING forecast_learning_adjustments (don't reinvent)
     - ✅ Uses EXISTING stockout_patterns (don't reinvent)
     - ✅ Uses EXISTING supplier_lead_times statistics
     - ✅ Fixed 30-day review period (monthly ordering constraint)
     - ✅ Calendar-aware calculations (actual month days)
     - ✅ Editable lead times and arrival dates
     - ✅ Time-phased pending orders with confidence scoring

     NOT Implementing (Not Relevant):
     - ❌ Dynamic review period optimization (you order monthly, period)
     - ❌ Continuous ordering workflows (you batch monthly)
     - ❌ Real-time inventory updates (you upload monthly)

     Total Estimated Time: 3-4 weeks with 1 developer