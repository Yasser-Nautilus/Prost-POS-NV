# 🖨️ feature/printing_flow — PROGRESS

## 🎯 Goal

Ensure every required document **prints automatically, silently, and correctly routed** to the right printer. Zero dialogs. Ever.

---

## ✅ Tasks

### 1. Kitchen Ticket

- **What**: Auto-print to kitchen printer when order is saved
- **Details**:
  - Triggered automatically by `order_service.create_order()`
  - Routes to shared kitchen printer (both cashiers → same device)
  - Format:
    - Order type in Arabic + English (e.g., صالة / Dining)
    - Station number
    - Table number (dine-in only)
    - Cashier name
    - Print date/time
    - **Order NO: (LARGE BOLD FONT)** — most important for kitchen
    - Items: Qty + Item name (2-column, simple)
    - Notes per item shown below as `ملاحظة: {text}` (e.g., "3 pieces cold")
    - **NO prices** — kitchen doesn't need financial info
    - **NO customer details** — kitchen doesn't need name/phone/zone
  - Auto-cut after printing
- **Why**: The kitchen has no screen. This printed ticket is the ONLY way they know an order exists.
- **Touches**: `infrastructure/printing/printer_manager.py`, `infrastructure/printing/receipt_templates.py`
- **Status**: `Not started`

### 2. Cashier Receipt (Customer Copy) — 4 Variants

- **What**: Auto-print customer receipt when order is paid/completed
- **Details**:
  - Triggered automatically by `order_service.complete_order()`
  - Routes to cashier-specific printer (cashier_1 or cashier_2 based on `cashier_slot`)
  - **Common elements across all 4 types**:
    - Shop header: بروستش / Prostsir
    - Station number, Cashier name, Order number (integer)
    - Items table (RTL columns): Total | Price | Qty | Item
    - Quantity as **integer** (1, 2, 9 — not 1.00)
    - Per-item notes below item line: `ملاحظة: {text}`
    - Service line (configurable %, default 0.00)
    - Total block (black background, white text)
    - Payment method: **كاش / فيزا / اونلاين** (3 methods only)
    - Paid + Change (Change = 0 for Visa and Online)
    - Footer: بروستش في القرمشة مبيهزرش
  - **Per-type differences**:
    - **Dine-In**: shows Table number. No customer info. Payment: كاش / فيزا / اونلاين
    - **Delivery + Cash**: shows customer info + driver. Driver collects **full amount** (food + delivery fee)
    - **Delivery + Online**: shows customer info + driver. **PREPAID** — driver collects nothing
    - **Takeaway**: "TAKEAWAY — انتظار" banner. No customer info. Payment: كاش / فيزا / اونلاين
    - **Pickup**: shows customer (name, phone). "PICKUP — استلام من المحل" banner. Payment: كاش / فيزا / اونلاين
  - **Visa is NOT available for delivery** — only at the restaurant counter
  - Auto-cut after printing
- **Touches**: `infrastructure/printing/receipt_templates.py`, `infrastructure/printing/printer_manager.py`
- **Status**: `Not started`

### 3. Daily Summary Receipt

- **What**: End-of-shift printed summary matching the provided photo format
- **Details**:
  - Triggered manually by manager from Reports view
  - Routes to current cashier's printer
  - **Exact format**:
    - Period: from date/time — to date/time
    - Breakdown (one line per type): صالة, تيك اواي, دليفري, استلام محل
    - Each line: type | count | revenue
    - Grand total: total orders | total revenue
  - Auto-cut after printing
- **Why**: Source of truth at end of day. Must match existing format exactly.
- **Touches**: `infrastructure/printing/receipt_templates.py`, `ui/views/reports_view.py`
- **Status**: `Not started`

### 4. Driver Settlement Receipt

- **What**: Per-trip receipt for driver financial accountability
- **Details**:
  - Triggered manually from Delivery view when settling a trip
  - Routes to current cashier's printer
  - Format:
    - Header: driver name, date, trip #
    - Order list: invoice #, order total, payment method, **amount collected by driver**
    - For each order:
      - If كاش → collected = order_total (food + delivery_fee)
      - If اونلاين → collected = 0 (everything prepaid)
    - Separator
    - Total cash collected by driver (sum of cash orders only)
    - Total delivery fees earned (all orders — cash + online)
    - **Amount to hand over** = total cash collected
  - Auto-cut after printing
- **Why**: Driver accountability. Shows exactly what cash the driver should have.
- **Status**: `Not started`

### 5. Failure Handling

- **What**: Graceful handling when a printer is unavailable or errors
- **Details**:
  - Log every print failure with timestamp and error details
  - Show non-blocking warning indicator in the UI (small badge/icon)
  - **Never show a dialog or block the cashier**
  - Failed prints are noted but the order is still saved
  - On app startup: test printer connections, warn if any are offline
- **Touches**: `infrastructure/printing/printer_manager.py`, `ui/windows/main_window.py`
- **Status**: `Not started`

---

## 📊 Payment Rules Summary

| Order Type | كاش | فيزا | اونلاين |
|-----------|------|------|---------|
| Dine-In | ✅ counter | ✅ counter | ✅ prepaid |
| Takeaway | ✅ counter | ✅ counter | ✅ prepaid |
| Pickup | ✅ counter | ✅ counter | ✅ prepaid |
| Delivery | ✅ driver collects ALL | ❌ not available | ✅ prepaid, driver collects NOTHING |

---

## 📝 Notes

- **Zero dialogs. Ever.** No Qt print dialog, no confirmation
- All printing uses ESC/POS thermal protocol
- Kitchen printer is shared → threading lock for concurrency
- **3 payment methods only**: كاش / فيزا / اونلاين
- **Visa NOT available for delivery**
- **Online delivery = driver collects nothing** (food + delivery fee all prepaid)
- **Cash delivery = driver collects everything** (food + delivery fee)
