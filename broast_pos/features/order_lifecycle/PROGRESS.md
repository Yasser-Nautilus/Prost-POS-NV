# 📦 feature/order_lifecycle — PROGRESS

## 🎯 Goal

Handle the **full order flow** end-to-end: creation → save → print → status updates → edit → payment → completion/cancellation. This is the most critical feature — everything else depends on it.

---

## ✅ Tasks

### 1. Create Order (In-Memory)

- **What**: Start an empty order that lives only in memory until explicitly saved
- **Details**:
  - Cashier selects order type → empty order object created in memory
  - Adding items: tap product → **add directly to order** (no popup)
  - Notes per item: cashier can type special instructions (e.g., "3 pieces cold")
  - Quantity adjustment: +/- buttons on each item
  - Live totals: subtotal, service (%), delivery fee (if delivery), discount (if applied), grand total
  - Order is **NOT** in the database at this point
  - **No draft system** — unsaved orders exist in memory only
- **Touches**: `core/models/order.py`, `ui/views/pos_view.py`, `ui/components/order_panel.py`
- **Status**: `Not started`

### 2. Parked Orders (Multi-Order Buffer)

- **What**: Cashier can work on multiple orders simultaneously
- **Details**:
  - Cashier is building Order A (dine-in, Table 3)
  - A takeaway customer walks in → cashier "parks" Order A
  - Cashier creates Order B (takeaway), processes it, pays
  - Cashier returns to Order A and continues
  - **Implementation**: tab/button bar showing parked orders at top of POS view
  - Each parked order shows: order type icon + table number (or "takeaway")
  - Parked orders live in **memory only** — not saved to database
  - If app crashes, parked orders are lost (acceptable for v1)
  - No limit on number of parked orders (practically 2-4 max)
  - **⚠️ Table concurrency**: if a cashier parks a dine-in order for Table 3 (in-memory, not in DB), the table grid still shows Table 3 as GREEN (available) because the parked order isn't persisted. Another cashier could start a new order for Table 3. **Mitigation**: parked dine-in orders should mark their table as OCCUPIED in the in-memory table state shared across the app. This is a UI-level concern, not a DB concern.
- **Why**: In a busy restaurant, the cashier needs to juggle multiple orders without losing progress.
- **Touches**: `ui/views/pos_view.py`
- **Status**: `Not started`

### 3. Validate & Save Order ("Confirm" Button)

- **What**: Enforce business rules and persist the order
- **Details**:
  - Validation rules:
    - Must have at least one item
    - Dine-in requires table number
    - Delivery requires phone + address
    - Pickup requires phone
    - Takeaway requires nothing extra
    - Visa NOT allowed for delivery orders
  - Generate sequential invoice number (integer, resets daily on shift close)
  - Persist via `OrderService.create_order()` → `OrderRepository.save()`
  - On save:
    - **Always**: print kitchen ticket (silent, auto)
    - **Takeaway**: immediately show Payment Dialog after save (Save + Pay in one flow)
    - **Delivery (online)**: mark as paid immediately (prepaid)
    - **Dine-in / Pickup / Delivery (cash)**: save without payment — payment happens later
  - On save failure: show error message, keep order in memory for retry
- **Why**: Invoice numbers reset daily on shift close. Next day starts from #1.
- **Touches**: `core/services/order_service.py`, `data/repositories/order_repository.py`
- **Status**: `Not started`

### 4. Payment Flow (Separate from Save)

- **What**: Record payment and print customer receipt
- **Details**:
  - **Takeaway**: Payment Dialog appears immediately after save (one flow)
  - **Dine-in**: Cashier clicks on occupied table → loads existing order → clicks "Pay" → Payment Dialog
  - **Pickup**: Customer arrives → cashier finds order (by phone/number) → clicks "Pay" → Payment Dialog
  - **Delivery (cash)**: Payment recorded during driver settlement
  - **Delivery (online)**: Marked as paid at creation — no separate payment step
  - Payment Dialog:
    - 3 methods: كاش / فيزا / اونلاين
    - Cash: enter amount received → auto-calculate change
    - Visa/Online: Paid = Total, Change = 0
    - Confirm → `order_service.complete_order()` → auto-print receipt
  - After payment: order status = COMPLETED
- **Touches**: `core/services/order_service.py`, `ui/components/payment_dialog.py`
- **Status**: `Not started`

### 5. Edit Saved Order (Amendment)

- **What**: Modify a saved order — add or remove items
- **Details**:
  - **Adding items**: allowed freely (no PIN required)
  - **Removing items**: requires **manager PIN** (prevents revenue leakage)
  - How to access: 
    - Dine-in: click on table → order loads → edit
    - Other types: find order in tracking view → click "Edit"
  - On save amendment:
    - Update order in database with new items/totals
    - Print **amendment kitchen ticket** — shows ONLY changes:
      ```
      ================================
       تابع — Order #3
      ================================
       إضافة:
          1  |  تشيكن فرايز حار
        
      حذف:
          1  |  قطعة دجاج عادي 2
      ================================
      ```
    - "تابع" (follow-up) — not "تعديل" (modification)
    - Kitchen knows this is an update to an existing order
    - Shows additions under "إضافة" and removals under "حذف"
    - **No prices** on amendment ticket (same as regular kitchen ticket)
  - Price lock: item prices are locked at time of original order creation
  - Product price changes in admin don't affect existing orders
- **Touches**: `core/services/order_service.py`, `infrastructure/printing/receipt_templates.py`
- **Status**: `Not started`

### 6. Status Transitions

- **What**: Move orders through their lifecycle
- **Details**:
  - **Simplified flow** (no PREPARING/READY intermediate states):
    - Non-delivery: `ACTIVE` → `COMPLETED` (after payment)
    - Delivery: `ACTIVE` → `OUT_FOR_DELIVERY` → `DELIVERED` → `COMPLETED` (after settlement)
  - `CANCELLED` is reachable from any non-completed state **except OUT_FOR_DELIVERY**
  - **Delivery in transit**: cancellation is **blocked** when order status is OUT_FOR_DELIVERY. Cashier sees warning: "الطلب خارج للتوصيل - لا يمكن إلغاؤه". Must wait for driver return (DELIVERED), then cancel.
  - Invalid transitions rejected by service layer
- **Touches**: `core/services/order_service.py`
- **Status**: `Not started`

### 7. Cancel Order (Manager Only)

- **What**: Cancel an active order with full audit trail
- **Details**:
  - PIN dialog → enter manager/admin PIN
  - If valid:
    - Record: cancelled_by_id, cancelled_by_name, cancel_reason, cancelled_at
    - Set status to CANCELLED
  - Cannot cancel completed orders
  - Audit log entry created
- **Touches**: `core/services/order_service.py`, `ui/components/pin_dialog.py`
- **Status**: `Not started`

### 8. Invoice Number Management

- **What**: Sequential integer that resets daily
- **Details**:
  - Starts at #1 each day after "Close Shift"
  - Assigned at **save time** (not pay time)
  - Race-safe with two concurrent cashiers: use atomic `UPDATE shifts SET next_invoice_no = next_invoice_no + 1 WHERE id = ? RETURNING next_invoice_no` (not SELECT then UPDATE)
  - Format: plain integer (1, 2, 3... not padded)
- **Touches**: `data/repositories/order_repository.py`, `core/services/financial_service.py`
- **Status**: `Not started`

---

## 📊 Complete Order Flow Per Type

### Dine-In (صالة)
```
1. Select "صالة" → Select Table
2. Add items → Notes if needed
3. Click "Confirm" → Kitchen ticket prints → Order saved (ACTIVE, unpaid)
4. Table shows as occupied (red) in table grid
5. [Customer eats...]
6. [Optional: customer adds more items → amendment ticket prints]
7. Cashier clicks on table → order loads → clicks "Pay"
8. Payment Dialog → select method → confirm
9. Receipt prints → Order = COMPLETED → Table = available (green)
```

### Takeaway (تيك اواي)
```
1. Select "تيك اواي"
2. Add items → Notes if needed
3. Click "Confirm" → Kitchen ticket prints → Order saved
4. Payment Dialog appears IMMEDIATELY
5. Select method → confirm → Receipt prints → Order = COMPLETED
6. Tracking screen shows order with timer
7. After 20 min → visually highlighted as "should be ready"
```

### Delivery — Cash (دليفري + كاش)
```
1. Select "دليفري" → Enter customer phone → auto-fill → select address
2. Add items → Notes if needed
3. Click "Confirm" → Kitchen ticket prints → Order saved (ACTIVE, unpaid)
4. [Kitchen prepares...]
5. Assign driver → Driver dispatched → OUT_FOR_DELIVERY
6. Driver delivers + collects cash from customer
7. Driver returns → settlement → cash handed over
8. Order = COMPLETED
```

### Delivery — Online (دليفري + اونلاين)
```
1. Select "دليفري" → Enter customer phone → auto-fill → select address
2. Add items → Notes if needed
3. Click "Confirm" → Kitchen ticket prints → Order saved (ACTIVE, marked PAID)
4. [Kitchen prepares...]
5. Assign driver → Driver dispatched → OUT_FOR_DELIVERY
6. Driver delivers (collects NOTHING — everything prepaid)
7. Driver returns → settlement → hands over nothing
8. Order = COMPLETED
```

### Pickup (استلام محل)
```
1. Select "استلام محل" → Enter customer phone + name
2. Add items → Notes if needed
3. Click "Confirm" → Kitchen ticket prints → Order saved (ACTIVE, unpaid)
4. [Kitchen prepares... Customer arrives later...]
5. Cashier finds order (by phone or number) → clicks "Pay"
6. Payment Dialog → select method → confirm → Receipt prints
7. Order = COMPLETED
```

---

## 📝 Notes

- **No draft system** — unsaved orders are in-memory only
- Parked orders = in-memory buffer (lost on app crash, acceptable for v1)
- Invoice numbers reset to #1 daily on "Close Shift"
- Prices locked at order creation time — admin price changes don't affect existing orders
- Adding items to saved order = free. Removing items = manager PIN required.
- Amendment kitchen ticket header: "تابع" not "تعديل"
- Takeaway auto-complete is **visual only** (color change in tracking) — not a real status change
