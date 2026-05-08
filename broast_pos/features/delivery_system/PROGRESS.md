# 🚚 feature/delivery_system — PROGRESS

## 🎯 Goal

Manage delivery **driver lifecycle, trip assignment, and financial settlement**. Settlement logic depends on **payment method** — cash orders require driver collection, online orders are fully prepaid. Driver earns delivery fees from ALL orders, paid as expense at end of day.

---

## ✅ Tasks

### 1. Driver Management (System-Level)

- **What**: Add, edit, activate/deactivate drivers in the system
- **Details**:
  - **Adding a driver to the system**: Manager only (via Users view)
  - **Driver check-in** (shift start): Cashier activates the driver when they arrive
  - **Driver check-out** (shift end): Cashier deactivates when shift ends
  - Only checked-in drivers appear in the dispatch list
  - Record attendance: `DriverAttendance` (driver_id, check_in_at, check_out_at)
- **Why**: The system needs to know which drivers are currently available. Only active drivers can be assigned trips.
- **Touches**: `core/services/delivery_service.py`, `ui/views/delivery_view.py`, `core/models/delivery.py`
- **Status**: `Not started`

### 2. Assign Driver to Trip (Manual)

- **What**: Cashier manually selects delivery orders and assigns them to a driver
- **Details**:
  - Delivery View shows a list of **checked-in drivers** (active this shift)
  - Separately shows a list of **unassigned delivery orders** (from both cashiers)
  - Cashier manually selects one or more orders → selects a driver → creates trip
  - **Cross-cashier trips allowed**: orders from Cashier 1 and Cashier 2 can go on the same trip
  - **No automatic grouping** — cashier decides which orders go together
  - Create `DeliveryTrip` record linking driver + orders
  - Update each order's `delivery_driver_id` and `delivery_driver_name`
  - **Mixed payment trips**: a single trip can have both cash and online orders
- **Touches**: `core/services/delivery_service.py`, `ui/views/delivery_view.py`
- **Status**: `Not started`

### 3. Mark Out for Delivery

- **What**: Cashier marks the trip as dispatched when driver physically leaves
- **Details**:
  - Record `dispatched_at` timestamp on the trip
  - Update all linked orders to `OUT_FOR_DELIVERY` status
  - Driver status changes to "out"
  - **Driver can have multiple active trips** — no blocking
- **Touches**: `core/services/delivery_service.py`, `ui/views/delivery_view.py`
- **Status**: `Not started`

### 4. Mark Returned (Trip End)

- **What**: When driver comes back from a trip
- **Details**:
  - Record `returned_at` timestamp on the trip
  - Driver status changes back to "available" (can take new trips immediately)
  - Update all linked orders to `DELIVERED` status
  - **No settlement blocking**: driver can go on a new trip before previous trip is settled
  - Settlement is triggered separately by cashier when ready
- **Touches**: `core/services/delivery_service.py`, `ui/views/delivery_view.py`
- **Status**: `Not started`

### 5. Per-Trip Settlement — 🔥 CRITICAL LOGIC

- **What**: Record the cash handover when driver gives collected money to cashier
- **Details**:
  - Cashier opens settlement for a returned (unsettled) trip
  - System shows:
    - List of orders on this trip: invoice #, total, payment method
    - For each order:
      - If كاش → driver collected `order_total` (food + delivery fee)
      - If اونلاين → driver collected `0` (everything prepaid)
    - `cash_collected` = sum of order_total WHERE payment = كاش
    - `total_delivery_fees` = sum of delivery_fee for ALL orders
    - `amount_to_hand_over` = `cash_collected`
  - Cashier confirms → trip marked as `settled`
  - **System records as fully delivered** — no shortage tracking (manager handles discrepancies offline)
  - Print settlement receipt (optional, triggered by cashier)
  - **Settlement can happen anytime** — immediately on return or later

- **Financial Examples**:

  **Example 1: All Cash Trip**
  ```
  Order #5: food 435 + delivery 15 = 450 (كاش)
  Order #8: food 300 + delivery 20 = 320 (كاش)
  
  cash_collected       = 770   ← driver hands over this
  total_delivery_fees  = 35    ← driver earns this (paid at end of day)
  ```

  **Example 2: Mixed Trip (Cash + Online)**
  ```
  Order #5: food 435 + delivery 15 = 450 (كاش)    → collected 450
  Order #8: food 300 + delivery 20 = 320 (اونلاين)  → collected 0
  
  cash_collected       = 450   ← driver hands over this
  total_delivery_fees  = 35    ← driver earns this (paid at end of day)
  online_revenue       = 320   ← already in restaurant account
  ```

  **Example 3: All Online Trip**
  ```
  Order #5: food 435 + delivery 15 = 450 (اونلاين) → collected 0
  Order #8: food 300 + delivery 20 = 320 (اونلاين) → collected 0
  
  cash_collected       = 0     ← driver hands over nothing
  total_delivery_fees  = 35    ← driver earns this (paid at end of day)
  ```

- **Touches**: `core/services/delivery_service.py`, `core/models/delivery.py`
- **Status**: `Not started`

### 6. Settlement Receipt (Print)

- **What**: Per-trip printed receipt for driver cash accountability
- **Details**:
  - Triggered manually by cashier after confirming settlement
  - Header: driver name, date, trip number
  - Table of orders:
    - Cash orders: invoice #, total, "كاش", collected amount
    - Online orders: invoice #, total, "اونلاين", collected = 0
  - Summary:
    - Cash collected: {total cash}
    - Delivery fees earned: {total fees}
    - Amount to hand over: {total cash}
  - Printed on current cashier's thermal printer
- **Touches**: `infrastructure/printing/receipt_templates.py`
- **Status**: `Not started`

### 7. End-of-Day Driver Summary — 🔥 IMPORTANT

- **What**: Aggregate ALL trips for ALL drivers in one day
- **Details**:
  - Shows each driver with their daily totals:
    ```
    Mohamed:  5 trips, 15 orders, fees earned: 275
    Ahmed:    3 trips, 8 orders, fees earned: 160
    ─────────────────────────────
    Total driver expenses: 435
    ```
  - Per driver breakdown:
    - Number of trips
    - Number of orders delivered
    - Total cash collected across all trips
    - Total delivery fees earned (from ALL orders — cash + online)
  - Grand total: sum of all delivery fees = total driver expenses for the day
  - **Printable**: thermal print format for manager records
  - **Future**: this total will be auto-recorded as expense + synced to Google Sheets
  - **Current (v1)**: manager sees the number and manually records expense
- **Why**: At end of day, the manager needs to know how much to pay EACH driver. The system calculates it; the manager pays and records it manually for now.
- **Touches**: `core/services/report_service.py`, `ui/views/delivery_view.py`
- **Status**: `Not started`

### 8. Expense Entry (Manual — v1)

- **What**: Simple manual expense logging by cashier
- **Details**:
  - Cashier can enter daily expenses: description, amount, category
  - Categories: delivery fees, supplies, other
  - Manager can view, print, or export expenses to Excel/CSV
  - **Future**: automatic expense entry from driver settlement + Google Sheets upload
  - **Current (v1)**: manual entry, print/export only
- **Touches**: `core/services/financial_service.py`, `ui/views/financial_view.py`
- **Status**: `Not started`

---

## 📊 Complete Delivery Flow (Step by Step)

```
1. Manager adds driver "Mohamed" to system (one-time setup)
2. Shift starts → Cashier checks in Mohamed (driver activated)
3. Cashier 1 creates delivery Order #5 (كاش, 450 total)
4. Cashier 2 creates delivery Order #8 (اونلاين, 320 total)
5. Kitchen prepares both orders
6. Cashier selects Order #5 + Order #8 → assigns to Mohamed → Trip #1 created
7. Cashier marks Trip #1 as "Out for Delivery"
8. [Mohamed delivers...]
   - Order #5 (كاش): collects 450 from customer
   - Order #8 (اونلاين): collects nothing (prepaid)
9. Mohamed returns → Cashier marks Trip #1 as "Returned"
10. Mohamed can immediately go on Trip #2 (no settlement blocking)
11. When cashier is ready → opens Trip #1 settlement:
    - Cash collected: 450
    - Delivery fees earned: 35 (15 + 20)
    - Amount to hand over: 450
12. Mohamed hands over 450 → Cashier confirms settlement → prints receipt
13. [More trips throughout the day...]
14. End of day → Manager views Driver Summary:
    - Mohamed: 5 trips, 15 orders, fees earned: 275
    - Ahmed: 3 trips, 8 orders, fees earned: 160
    - Total driver expenses: 435
15. Manager pays Mohamed 275, Ahmed 160 → records manually as expense
16. Cashier checks out Mohamed and Ahmed (shift over)
```

---

## 📊 Delivery Payment Rules

| Payment | Food Paid? | Del. Fee Paid? | Driver Collects | Driver Hands Over |
|---------|-----------|---------------|-----------------|-------------------|
| **كاش** | ❌ | ❌ | food + delivery_fee | everything |
| **اونلاين** | ✅ | ✅ | **nothing** | nothing |
| **فيزا** | — | — | ❌ NOT AVAILABLE FOR DELIVERY | — |

---

## 📝 Notes

- Driver hands over **only what they physically collected** (cash orders only)
- Online orders: driver collected nothing — money is in restaurant's account
- Delivery fees earned by driver from ALL orders regardless of payment method
- Settlement per trip — but driver can go on new trips without settling previous ones
- **No shortage tracking** — system always records as fully delivered; discrepancies handled offline
- Adding drivers = manager. Dispatching trips = cashier. Check-in/out = cashier.
- Cross-cashier trips allowed — orders from both cashiers on the same trip
- Manual order selection (no automatic grouping)
- **Visa NOT available for delivery** — only at restaurant counter
- End-of-day driver expense is manual for v1 (future: automatic + Google Sheets)
