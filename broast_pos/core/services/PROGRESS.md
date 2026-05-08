# 📁 core/services — PROGRESS

## 🎯 Goal

Handle **all business logic** — rules, validations, workflows. Services are the brain of the system. They talk to repositories for data and to infrastructure for printing. They **never** talk to the UI directly.

---

## ✅ Tasks

### 1. Order Service (`order_service.py`)

- **What**: Full order lifecycle management
- **Details**:
  - `create_order(order, cashier_id, cashier_name)` → **check shift active** → validate → save → auto-print kitchen ticket
    - **First step**: calls `financial_service.ensure_shift_active()` — blocks if no open shift
    - Takeaway: returns signal to immediately show Payment Dialog
    - Delivery (online): marks as paid at save time
    - Others: save without payment
  - `amend_order(order_id, added_items, removed_items, manager_pin=None)` → edit saved order:
    - Adding items: allowed freely
    - Removing items: requires manager PIN (prevents revenue leakage)
    - Updates totals in database
    - Prints **amendment kitchen ticket** (تابع — Order #X) showing only changes
  - `complete_order(order_id, payment_method, amount_received)` → mark paid → auto-print receipt
  - `cancel_order(order_id, manager_pin, reason)` → verify PIN → audit trail
  - `apply_discount(order, value, type, manager_pin)` → verify PIN → set discount fields
  - `get_order_by_table(table_number)` → load existing order for dine-in pay/edit flow
  - Private `_validate_order()` enforces: items required, delivery needs phone+address, pickup needs phone
- **Business Rules**:
  - No empty orders can be saved
  - Dine-in requires table number
  - Delivery orders require phone + address
  - Pickup orders require phone
  - Takeaway requires nothing extra
  - Completed/cancelled orders cannot be modified
  - Adding items to saved order = free. Removing items = manager PIN
  - Discount requires manager or admin PIN
  - Cancellation requires manager or admin PIN + reason
  - **Payment validation**: فيزا is NOT allowed for delivery orders
  - **3 payment methods only**: كاش / فيزا / اونلاين
  - Prices locked at order creation — admin price changes don't affect existing orders
- **Status**: `Not started`

### 2. Auth Service (`auth_service.py`)

- **What**: Login, session management, permission checking, manager override
- **Details**:
  - `get_all_users()` → return all active users for login screen tiles (avatar + username)
  - `login(user_id, pin)` → hash PIN → compare with stored hash → create session
  - `logout()` → clear active session → return to login screen
  - `verify_pin(pin)` → hash PIN → find matching user → return user if MANAGER or ADMIN
    - Used for manager overrides (discount, cancel, remove item)
    - PIN is unique per user → system identifies WHO authorized the action
  - `get_current_user()` → return active session user
  - `check_permission(user, action)` → role-based access control
  - **No fast switch** — full logout/login every time (Option A)
- **Permission Matrix**:
  - `create_order` → CASHIER, MANAGER, ADMIN
  - `apply_discount` → MANAGER, ADMIN (cashier needs override)
  - `cancel_order` → MANAGER, ADMIN (cashier needs override)
  - `remove_order_item` → MANAGER, ADMIN (cashier needs override)
  - `manage_products` → MANAGER, ADMIN
  - `add_drivers` → MANAGER, ADMIN
  - `check_in_out_drivers` → CASHIER, MANAGER, ADMIN
  - `open_close_shift` → MANAGER, ADMIN
  - `view_reports` → MANAGER, ADMIN
  - `manage_users` → ADMIN only
- **Why**: Two cashiers on separate devices. Session determines which cashier slot → which receipt printer. Manager override = manager walks to cashier's device and types their PIN.
- **Status**: `Not started`

### 3. Delivery Service (`delivery_service.py`)

- **What**: Driver lifecycle, trip dispatch, tracking, and financial settlement
- **Details**:
  - **Driver lifecycle**:
    - `check_in_driver(driver_id)` → activate driver for this shift (cashier action)
    - `check_out_driver(driver_id)` → deactivate driver (cashier action)
    - `get_active_drivers()` → only checked-in drivers for dispatch list
  - **Trip management**:
    - `create_trip(order_ids, driver_id)` → manually selected orders → create trip
    - `mark_dispatched(trip_id)` → driver leaves, timestamp recorded
    - `mark_returned(trip_id)` → driver back, orders marked DELIVERED
    - **No settlement blocking**: driver goes on new trip even with unsettled trips
  - **Settlement**:
    - `settle_trip(trip_id)` → cashier confirms cash handover:
      - `cash_collected` = sum of order_total WHERE payment = كاش
      - `total_delivery_fees` = sum of delivery_fee for ALL orders
      - `amount_to_hand_over` = `cash_collected`
      - System always records as fully delivered (no shortage tracking)
    - `get_unsettled_trips(driver_id)` → trips returned but not yet settled
  - **End-of-day**:
    - `get_all_drivers_daily_summary(date)` → all drivers with trip count, order count, fees earned
    - `get_driver_daily_summary(driver_id, date)` → single driver detail
- **Permissions**: Adding drivers = manager. Check-in/out + dispatching = cashier.
- **Status**: `Not started`

### 4. Product Service (`product_service.py`)

- **What**: Product and category CRUD
- **Details**:
  - `get_categories()` → sorted list for POS grid tabs
  - `get_products_by_category(category_id)` → sorted products for grid
  - `search_products(query)` → fast text search for cashier
  - `create/update/delete_product(...)` → manager-only operations
  - ~~`get_modifiers_for_product()`~~ — **REMOVED** (no modifiers)
  - Each product variation is a separate entry (e.g., "تشيكن فرايز حار", "تشيكن فرايز عادي")
- **Why**: Product search is essential at 300+ orders/day. Search must be instant (<100ms).
- **Status**: `Not started`

### 5. Customer Service (`customer_service.py`)

- **What**: Phone-based customer lookup, address management, and zone configuration
- **Details**:
  - **Phone lookup** (exact match, no partial search):
    - `find_by_phone(phone)` → exact 11-digit match → return customer with all addresses, or None
    - Cashier types full phone → system checks → found or new
  - **New customer flow** (phone not found):
    - `create_customer(name, phone)` → create record
    - `add_address(customer_id, street_name, zone_id)` → save address with zone's delivery fee
    - Both happen in a single dialog when phone is new
  - **Returning customer flow** (phone found):
    - If 1 address → auto-select it, fill street + zone + fee
    - If multiple addresses → show colored address cards, cashier picks one
    - Cashier can add new address to existing customer
  - **Zone management** (manager only):
    - `get_all_zones()` → for dropdown in customer panel
    - `create_zone(name, delivery_fee)` → manager only
    - `update_zone(zone_id, name, delivery_fee)` → manager only
    - `deactivate_zone(zone_id)` → soft delete
  - **Validation**:
    - Phone must be 11 digits starting with "01"
    - Zone is required for delivery orders
    - Delivery fee comes from zone — cannot be manually changed
- **Why**: Exact phone match is faster and simpler than partial search. Zone-based fixed fees prevent cashier mistakes.
- **Status**: `Not started`

### 6. Financial Service (`financial_service.py`)

- **What**: Shift lifecycle, expense tracking, and cash reconciliation
- **Details**:
  - **Open shift**:
    - `open_shift(user_id)` → create new shift, **reset invoice counter to #1**
    - Any role can open (CASHIER, MANAGER, ADMIN)
    - Cannot open if another shift is already active
    - No opening cash amount — shift just starts
  - **Shift transfer** (mid-day handover):
    - `transfer_shift(from_user_id, to_user_id, manager_pin)` → manager only
    - Records a `ShiftTransfer` checkpoint with current state snapshot:
      - Sales so far, expenses so far, pending orders
    - Shift stays open — continues with new cashier
    - Invoice numbering continues (does NOT reset)
  - **Close shift** (end of day):
    - `close_shift(shift_id, manager_pin)` → **manager only** with confirmation
    - **Prerequisites** (system checks before allowing close):
      - All driver accounts must be settled (no unsettled trips)
      - Daily summary report must be printed at least once
    - Calculates final summary:
      - total_sales, total_expenses
      - pending_delivery, pending_dinein, pending_kitchen
      - expected_cash = sales - expenses - all_pending
    - Next shift open will reset invoice counter to #1
  - **Expense entry**:
    - `add_expense(shift_id, amount, description, category, user_id)` → cash-out entry
    - **Cash-out only** — no cash-in entries
    - **Immutable** — once entered, cannot be edited or deleted
    - Categories: delivery_fees, supplies, other
  - **Invoice counter**:
    - `get_next_invoice_number()` → returns next sequential int for current shift
    - Continues across shift transfers within the same day
    - Resets to #1 only on `open_shift()` (new day)
  - **Shift guard**:
    - `ensure_shift_active()` → called by OrderService before creating any order
    - Throws error if no active shift → blocks order creation
- **Status**: `Not started`

### 7. Report Service (`report_service.py`)

- **What**: All report data generation and formatting
- **Details**:
  - **Daily reports**:
    - `generate_daily_sales(date)` → order type breakdown (count + revenue), matches receipt photo
    - `generate_payment_breakdown(date)` → sales split by كاش / فيزا / اونلاين
    - `generate_cancelled_orders(date)` → cancelled order count + reasons
    - `generate_product_sales(date)` → qty sold per product, sorted by popularity
    - `generate_driver_summary(date)` → per-driver trip/order/fee totals
  - **Shift reports**:
    - `generate_shift_transfer(shift_id)` → snapshot: sales, expenses, pending, expected cash
    - `generate_shift_close(shift_id)` → final summary for end of day
  - **Monthly dashboard**:
    - `generate_monthly_summary(year, month)` → total sales, total expenses, daily breakdown
    - `generate_monthly_bestsellers(year, month)` → top products by qty sold
    - `generate_monthly_expenses(year, month)` → expense breakdown by category
  - **Yearly overview**:
    - `generate_yearly_summary(year)` → 12-month sales + expenses overview
    - `generate_yearly_bestsellers(year)` → top products for the year
  - Data is returned as plain dicts/dataclasses — **NO print logic here**
  - All data is stored permanently — nothing deleted on shift close
- **Status**: `Not started`

---

## 📝 Notes

- **Services MUST NOT depend on UI** — no `import PyQt6` ever
- **Services MUST NOT call SQLite directly** — they go through repositories
- All Arabic error messages are returned as `ValueError` / `PermissionError`
- **No modifier logic** — products are self-contained
- **No draft system** — unsaved orders are in-memory only
- Printing failures are logged but **never block** the cashier
- Amendment = تابع (follow-up), prints only the changes to kitchen
- Invoice numbers reset to #1 per shift (daily)
