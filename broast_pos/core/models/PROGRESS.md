# 📁 core/models — PROGRESS

## 🎯 Goal

Define all business entities as **pure Python dataclasses** — no database logic, no UI dependencies. These models represent the exact shape of data flowing through the entire system.

---

## ✅ Tasks

### 1. Order Model (`order.py`)

- **What**: Define `Order`, `OrderItem`, `OrderStatus`, `OrderType`, `PaymentMethod` classes
- **Details**:
  - `OrderType` enum: صالة (Dine-in), تيك اواي (Takeaway), دليفري (Delivery), استلام محل (Pickup)
  - `OrderStatus` enum: جديد → قيد التحضير → جاهز → خارج للتوصيل → تم التوصيل → مكتمل / ملغي
  - `PaymentMethod` enum: **كاش, فيزا, اونلاين** (3 methods only)
  - `is_prepaid` property: True for اونلاين, False for كاش/فيزا
  - **Visa NOT available for delivery** — only at restaurant counter
  - `OrderItem`: product_id, product_name, quantity (**int**), unit_price, notes (str)
  - `Order`: full order with financial breakdown (subtotal, discount, delivery_fee, service, tax, total)
  - Computed properties: `subtotal`, `discount_amount`, `total`, `restaurant_revenue`
  - Cancellation fields: cancelled_by_id, cancelled_by_name, cancel_reason, cancelled_at
  - `can_be_cancelled()` and `is_delivery()` helper methods
- **Why**: The `restaurant_revenue` property (total minus delivery_fee) is critical for correct shift reports and driver settlement.
- **Important**: OrderItem has **NO modifiers list** — each product variation is a separate product. Notes field is used for per-item special instructions (e.g., "3 pieces cold").
- **Status**: `To Review`

### 2. OrderItem Model (inside `order.py`)

- **What**: Define `OrderItem` dataclass
- **Details**:
  - Links a product to a quantity with optional notes
  - Fields: `product_id`, `product_name`, `quantity` (int), `unit_price`, `notes` (str)
  - `total_price` property: `quantity × unit_price`
  - **No modifiers** — the product name itself contains the variation (e.g., "تشيكن فرايز حار")
  - Notes are per-item free text (e.g., "3 pieces cold" when ordering "9 Pieces Hot")
- **Status**: `To Review`

### 3. User Model (`user.py`)

- **What**: Define `User` and `UserRole` classes
- **Details**:
  - `UserRole` enum:
    - `CASHIER` — order creation, driver check-in/out, settlement
    - `MANAGER` — owner: discounts, cancellations, products, drivers, shifts, reports
    - `ADMIN` — developer: full access including user management
  - `User` fields:
    - id, username, display_name, avatar_path (optional)
    - pin_hash (SHA-256, **unique per user** — can identify user by PIN alone)
    - role (UserRole)
    - is_active (bool)
    - cashier_slot (1 or 2, **nullable for drivers**) — determines receipt printer routing. Drivers don't print receipts, so their slot is NULL
  - Manager override: `verify_pin(pin)` returns the user if PIN matches a MANAGER or ADMIN
- **Why**: PIN uniqueness enables the manager override pattern — manager types PIN on cashier device, system knows who authorized it. Avatar is shown on login screen tiles.
- **Status**: `To Review`

### 4. Product Model (`product.py`)

- **What**: Define `Product` and `Category` classes
- **Details**:
  - `Product`: id, name, price, category_id, is_active, sort_order
  - `Category`: id, name, sort_order, is_active
  - Products belong to categories
  - **No Modifier model** — each product variation is a separate product entry
    - Example: "تشيكن فرايز حار" and "تشيكن فرايز عادي" are two distinct products
  - Sort order matters — the POS grid must display products in the exact order configured
- **Why**: Removing modifiers dramatically simplifies the POS flow — tap product, it goes directly to the order panel. No popup dialog needed.
- **Status**: `To Review`

### 5. Customer Model (`customer.py`)

- **What**: Define `Customer`, `CustomerAddress`, and `Zone` classes
- **Details**:
  - `Customer` fields:
    - id, name, phone (11-digit Egyptian, starts with 01, **unique lookup key**)
    - notes (optional)
    - created_at
  - `CustomerAddress` fields:
    - id, customer_id (FK)
    - street_name (text — just the street, e.g., "شارع المشالي")
    - zone_id (FK → Zone)
    - zone_name (denormalized for display)
    - delivery_fee (copied from zone at creation time)
  - `Zone` fields:
    - id, name (e.g., "مدينة فاقوس", "شارع الانتاج", "الغابة")
    - delivery_fee (fixed per zone, e.g., 20, 15, 80)
    - is_active (bool)
  - One customer can have **multiple addresses** (home, work, etc.)
  - Zone delivery fee is **fixed** — cashier cannot change it per order
- **Why**: Phone is the primary key for customer lookup. Zone-based fees ensure pricing consistency. Street name is enough — no building numbers needed.
- **Status**: `To Review`

### 6. Delivery Model (`delivery.py`)

- **What**: Define `DeliveryTrip`, `DriverAttendance`, `DriverStatus` classes
- **Details**:
  - `DriverStatus` enum: `CHECKED_OUT` (not working), `AVAILABLE` (checked in, ready), `OUT` (on a delivery trip)
  - `DeliveryTrip` fields:
    - id, driver_id, driver_name
    - order_ids[] (list of order IDs on this trip)
    - created_at, dispatched_at, returned_at, settled_at
    - cash_collected (**calculated and stored at settlement time** — snapshot of sum of order_total WHERE payment = كاش)
    - total_delivery_fees (**calculated and stored at settlement time** — snapshot of sum of delivery_fee for ALL orders)
    - is_settled (bool — can be false even after return, settlement happens separately)
  - `DriverAttendance` fields:
    - id, driver_id, check_in_at, check_out_at
  - **Trip lifecycle**: created → dispatched → returned → settled (each step independent)
  - **No settlement blocking**: driver can go on new trips with unsettled previous trips
- **Why**: Settlement depends on payment method. Cash orders: driver collected the money. Online orders: driver collected nothing. Driver earns fees from ALL orders, paid at end of day as expense.
- **Status**: `To Review`

### 7. Financial Model (`financial.py`)

- **What**: Define `Shift`, `ShiftTransfer`, `CashTransaction`, `ShiftSummary` classes
- **Details**:
  - `Shift` fields:
    - id, opened_by (user_id), opened_at
    - closed_by (user_id, nullable), closed_at (nullable)
    - next_invoice_no (int, starts at 1)
    - is_active (bool)
  - `ShiftTransfer` fields:
    - id, shift_id, from_user_id, to_user_id
    - timestamp, summary_snapshot (JSON — sales, expenses, pending at transfer time)
  - `CashTransaction` fields:
    - id, shift_id, type (`expense` only), amount, description, category
    - timestamp, user_id
    - **Immutable** — cannot be edited after creation
  - `ShiftSummary` (computed, not stored):
    - total_sales (all completed orders)
    - total_expenses (all cash-out entries)
    - pending_delivery (unsettled driver orders — money not yet in drawer)
    - pending_dinein (unpaid dine-in tables)
    - pending_kitchen (orders still being prepared)
    - expected_cash = total_sales - total_expenses - all_pending
    - order_breakdown: dict by type (count + revenue)
- **Why**: Expected cash accounts for money that hasn't been collected yet. Pending orders are deducted because the cash isn't physically in the drawer.
- **Status**: `To Review`

---

## 📝 Notes

- **All models are pure** — NO `import sqlite3`, NO `import PyQt6`
- Use Python `dataclasses` with `@dataclass` decorator
- Use `Enum` for all status/type fields (not magic strings)
- Use `Optional[T]` for nullable fields
- Use `@property` for computed values (subtotal, total, etc.)
- **NO Modifier model** — removed entirely. Product variations are separate products.
- **Quantity is int** — you don't sell 0.5 chickens
- **Notes are per-item strings** — for special instructions
- Financial amounts use `float` with `round(..., 2)`

## 📌 Order Type Requirements

| Type | Arabic | Requires |
|------|--------|----------|
| Dine-In | صالة | Table number |
| Delivery | دليفري | Phone, Address, Zone |
| Takeaway | تيك اواي | Nothing extra — customer is standing and waiting |
| Pickup | استلام محل | Phone — customer ordered by phone, will come to collect |

## 📌 Payment Method Availability

| Method | Dine-In | Takeaway | Pickup | Delivery |
|--------|---------|----------|--------|----------|
| كاش | ✅ | ✅ | ✅ | ✅ driver collects ALL |
| فيزا | ✅ | ✅ | ✅ | ❌ NOT available |
| اونلاين | ✅ | ✅ | ✅ | ✅ driver collects NOTHING |
