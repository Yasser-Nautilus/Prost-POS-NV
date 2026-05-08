# 📁 infrastructure/printing — PROGRESS

## 🎯 Goal

Provide **reliable, silent thermal printing (ESC/POS)** for kitchen tickets, customer receipts, driver settlement reports, and daily summaries. Correctly route to 2 cashier printers + 1 shared kitchen printer. **Never block the cashier with a dialog.**

---

## ✅ Tasks

### 1. Printer Manager (`printer_manager.py`)

- **What**: Central routing layer — decides which physical printer handles each print job
- **Details**:
  - Initialize at app startup, detect and connect to all configured printers
  - Routing map:
    - `KITCHEN` → shared kitchen printer (both cashiers send here)
    - `CASHIER_1` → receipt printer for cashier 1
    - `CASHIER_2` → receipt printer for cashier 2
  - Public API:
    - `print_kitchen_ticket(order)` → always routes to kitchen printer
    - `print_receipt(order, cashier_slot)` → routes to correct cashier printer
    - `print_shift_summary(summary_data, cashier_slot)` → end-of-shift receipt
    - `print_driver_settlement(driver_data, orders, cashier_slot)` → per-trip settlement
  - Failure handling: log error + return `False` — **never raise, never block**
  - Status indicator: expose `is_printer_available(key)` for UI warning badge
- **Why**: The system is useless without printing. The kitchen never sees a screen — they rely entirely on printed tickets. If the printer fails, the cashier must still be able to create orders (log the failure, retry later).
- **Status**: `Not started`

### 2. ESC/POS Adapter (`escpos_printer.py`)

- **What**: Low-level thermal printer communication using `python-escpos`
- **Details**:
  - Support connection types:
    - USB: `escpos.printer.Usb(vendor_id, product_id)`
    - Network/TCP: `escpos.printer.Network(ip, port=9100)`
    - Serial: `escpos.printer.Serial(device)` (fallback)
    - Dummy: `escpos.printer.Dummy()` (for development/testing)
  - Low-level commands: `text()`, `set()` (align, bold, size), `ln()`, `cut()`
  - Arabic text encoding support (CP864 or UTF-8 depending on printer model)
  - Auto-reconnect on connection loss
- **Why**: Different printers connect differently. USB is common for cashier printers, Network/TCP is common for kitchen printers located across the restaurant.
- **Status**: `Not started`

### 3. Receipt Templates (`receipt_templates.py`)

- **What**: All print layouts defined in one place — 80mm thermal format
- **Details**:

  #### 3a. Customer Receipt — Dine-In
  ```
  ================================
          بروستش / Prostsir
                -
  Dine IN                Station: {station}
  Cashier: {cashier}      Table: {table}
  Order NO: {order_number}
  --------------------------------
   Total  | Price  | Qty  | Item
  --------------------------------
   {total} | {price} | {qty} | {item_name}
            ملاحظة: {note}         ← if note exists
   ... (repeat per item)
  --------------------------------
  Service:              {service}
  ================================
             Total
            {total}
  ================================
  Payment:           {payment_method}
  Paid:              {paid}
  Change:            {change}
  --------------------------------
       بروستش في القرمشة سبيهزرقن
  - - - - - - - - ✂ - - - - - - -
  ```

  #### 3b. Customer Receipt — Delivery
  ```
  ================================
          بروستش / Prostsir
                -
  Delivery               Station: {station}
  Cashier: {cashier}     Order: #{order_number}
  --------------------------------
  العميل:   {customer_name}
  الهاتف:   {customer_phone}
  العنوان:  {customer_address}
  المنطقة:  {customer_zone}
  المندوب:  {driver_name}
  --------------------------------
   Total  | Price  | Qty  | Item
  --------------------------------
   {total} | {price} | {qty} | {item_name}
            ملاحظة: {note}
   ... (repeat per item)
  --------------------------------
  Service:              {service}
  Delivery Fee:         {delivery_fee}
  ================================
             Total
            {total}
  ================================
  Payment:           {payment_method}
  Paid:              {paid}
  Change:            {change}
  --------------------------------
       بروستش في القرمشة سبيهزرقن
  - - - - - - - - ✂ - - - - - - -
  ```

  #### 3c. Customer Receipt — Takeaway
  - Same structure as Dine-In but:
    - Header: `Takeaway` instead of `Dine IN`
    - **No Table** field
    - Banner: `** TAKEAWAY — انتظار **` (customer is standing and waiting)
    - **No phone/address** — customer is physically present
    - No delivery fee

  #### 3d. Customer Receipt — Pickup
  - Same structure as Takeaway but:
    - Header: `Pickup` instead of `Takeaway`
    - Shows: العميل + الهاتف (customer ordered by phone, will come to collect)
    - **No address/zone/driver** — customer picks up themselves
    - Banner: `** PICKUP — استلام من المحل **`
    - No delivery fee

  #### 3e. Kitchen Ticket
  ```
  ================================
             {order_type_ar}
      {order_type_en}    Station: {station}
                Table No. {table}   ← dine-in only
  --------------------------------
  Cashier: {cashier}
  Print On: {date}      {time}
  ================================
       Order NO: {order_number}     ← LARGE BOLD FONT
  ================================
    Qty  |  Item
  --------------------------------
    {qty}  |  {item_name}
             ملاحظة: {note}         ← if note exists (e.g., "3 pieces cold")
    {qty}  |  {item_name}
  --------------------------------
  ================================
  - - - - - - - - ✂ - - - - - - -
  ```
  - **NO prices** — kitchen doesn't need financial info
  - **NO customer details** — kitchen doesn't need name/phone/zone
  - **NO totals, no payment, no service**
  - **Order number is BIG** (most important identifier for kitchen)
  - Notes per item shown clearly below the item name
  - For delivery: no extra info (kitchen just prepares food)

  #### 3f. Amendment Kitchen Ticket (when order is edited after save)
  ```
  ================================
   تابع — Order #{order_number}
  ================================
  Cashier: {cashier}
  Print On: {date}      {time}
  --------------------------------
   إضافة:
    {qty}  |  {item_name}
            ملاحظة: {note}          ← if note exists
    {qty}  |  {item_name}

  حذف:
    {qty}  |  {item_name}
  --------------------------------
  ================================
  - - - - - - - - ✂ - - - - - - -
  ```
  - Header: "تابع" (follow-up), NOT "تعديل" (modification)
  - Shows ONLY the changes — not the full original order
  - "إضافة" section: items added to the order
  - "حذف" section: items removed from the order (required manager PIN)
  - **NO prices** — same as regular kitchen ticket
  - Kitchen sees: "this is a follow-up for Order #3, add these items, remove those"
  - If only additions: "حذف" section is omitted
  - If only removals: "إضافة" section is omitted

  #### 3f. End-of-Day Sales Report (matches receipt photo)
  ```
  ================================
         {date}           {day}
  اجمالي مبيعات
  في الفترة
  من {from_time} {from_date}
  الى {to_time}  {to_date}
  ================================
  نوع الاوردر | عدد الاوردرات | اجمالي المبلغ
  --------------------------------
  صالة       |  {n}   | {amount}
  تيك اواي   |  {n}   | {amount}
  دليفري     |  {n}   | {amount}
  استلام محل  |  {n}   | {amount}
  --------------------------------
  الاجمالي   |  {n}   | {amount}
  ================================
  - - - - - - - - ✂ - - - - - - -
  ```
  - Date and day are **auto-generated** by system (no handwriting)
  - Period = shift open time → shift close time
  - Order types: صالة, تيك اواي, دليفري, استلام محل
  - Must print at least once before shift close is allowed

  #### 3g. Shift Transfer Report (mid-day cashier handover)
  ```
  ================================
  تقرير تسليم وردية — Shift Transfer
  --------------------------------
  التاريخ: {date}     اليوم: {day}
  من: {from_cashier}    الى: {to_cashier}
  الوقت: {time}
  --------------------------------
  اجمالي المبيعات:        {sales}
  اجمالي المصروفات:      -{expenses}
  معلق دليفري:           -{pending_delivery}
  معلق صالة:             -{pending_dinein}
  معلق مطبخ:             -{pending_kitchen}
  --------------------------------
  المتوقع في الدرج:       {expected_cash}
  ================================
  - - - - - - - - ✂ - - - - - - -
  ```
  - Printed when manager transfers shift to another cashier
  - Shows what the next cashier should expect in the cash drawer
  - "Pending" = money not yet collected (delivery out, dine-in unpaid, kitchen in progress)

  #### 3h. Driver Settlement Receipt
  ```
  ================================
  تسوية مندوب — Driver Settlement
  --------------------------------
  المندوب: {driver_name}
  التاريخ: {date}
  الرحلة:  #{trip_number}
  --------------------------------
  Invoice | Order Total | Payment  | Collected
  --------------------------------
  #{inv}  |  {total}    | كاش      | {total}
  #{inv}  |  {total}    | اونلاين   | 0.00
  --------------------------------
  Cash Collected:         {cash_collected}
  Delivery Fees Earned:   {fees}
  Amount to Hand Over:    {cash_collected}
  ================================
  - - - - - - - - ✂ - - - - - - -
  ```

  #### 3j. End-of-Day Driver Summary
  ```
  ================================
  ملخص المناديب — Driver Summary
  التاريخ: {date}
  ================================
  Driver     | Trips | Orders | Fees
  --------------------------------
  {name}     |  {n}  |  {n}   | {fees}
  {name}     |  {n}  |  {n}   | {fees}
  --------------------------------
  Total Driver Expenses:  {total_fees}
  ================================
  - - - - - - - - ✂ - - - - - - -
  ```
  - Shows ALL drivers who worked that day
  - Per driver: trip count, order count, total delivery fees earned
  - Grand total = sum of all delivery fees = total driver expenses
  - Used by manager to know how much to pay each driver

- **Columns direction**: RTL — Item on far right, Total on far left
- **Quantity format**: Integer only (1, 2, 9 — NOT 1.00)
- **No modifiers system** — each product variation is a separate product in the menu
- **Notes per item**: shown as `ملاحظة: {text}` below the item line if present

- **Status**: `Not started`

### 4. Silent Printing Flow

- **What**: Zero-dialog printing triggered automatically at the right moments
- **Details**:
  - On `order_service.create_order()` → auto-print kitchen ticket
  - On `order_service.amend_order()` → auto-print amendment kitchen ticket (تابع)
  - On `order_service.complete_order()` → auto-print customer receipt
  - On shift transfer → auto-print shift transfer report (تقرير تسليم وردية)
  - On shift close → auto-print end-of-day sales report (اجمالي مبيعات)
  - On driver settlement → auto-print driver settlement receipt
  - On end-of-day → auto-print driver summary (ملخص المناديب)
  - On report request (from Reports View) → print to current cashier's printer
  - **No Qt print dialog ever** — all printing goes directly to ESC/POS
  - If printer unavailable: log warning, show small badge icon in UI, continue
- **Why**: The old system opened a Qt print dialog for every single print — this is completely unusable in a busy shift. Silent printing is a hard requirement.
- **Status**: `Not started`

### 5. Printer Configuration (`printer_config.py`)

- **What**: Store printer mapping configuration
- **Details**:
  - JSON config file or database table:
    ```json
    {
      "kitchen":   {"type": "network", "address": "192.168.1.100", "port": 9100},
      "cashier_1": {"type": "usb", "address": "0x04b8,0x0202"},
      "cashier_2": {"type": "usb", "address": "0x04b8,0x0203"}
    }
    ```
  - Load at app startup
  - Future: setup screen in admin panel to configure without editing files
- **Why**: Printer addresses change when hardware is swapped. The config must be editable without touching code.
- **Status**: `Not started`

---

## 📊 Variable Reference (All Templates)

| Variable | Type | Used In | Notes |
|---|---|---|---|
| `{station}` | string | all | e.g. `01`, `02` |
| `{cashier}` | string | all | cashier username |
| `{table}` | int | dine-in only | table number |
| `{order_number}` | int | **all order types** | auto-increment sequential |
| `{customer_name}` | string | delivery + pickup | Arabic or Latin |
| `{customer_phone}` | string | delivery + pickup | required for these types |
| `{customer_address}` | string | delivery only | required for delivery |
| `{customer_zone}` | string | delivery only | area/zone name |
| `{driver_name}` | string | delivery only | assigned driver |
| `{delivery_fee}` | decimal | delivery only | per-order, zone-based |
| `{item_name}` | string | all | full product name (includes variation like حار/عادي) |
| `{qty}` | **int** | all | whole numbers only (1, 2, 9) |
| `{price}` | decimal | cashier receipts | unit price, 2 decimal places |
| `{item_total}` | decimal | cashier receipts | qty × price |
| `{note}` | string | all (if exists) | per-item note (e.g., "3 pieces cold") |
| `{service}` | decimal | cashier receipts | configurable %, default 0.00 |
| `{total}` | decimal | cashier receipts | subtotal + service + delivery_fee |
| `{payment_method}` | string | cashier receipts | **كاش / فيزا / اونلاين** |
| `{paid}` | decimal | cashier receipts | amount received from customer |
| `{change}` | decimal | cashier receipts | max(0, paid - total) |

## 🧮 Calculation Logic

```
subtotal     = sum(qty × price) for all items
service      = subtotal × (service_pct / 100)
total        = subtotal + service + delivery_fee
change       = max(0, paid - total)
```

All monetary values formatted to 2 decimal places. Change never negative.

---

## 📝 Notes

- **Printing is CRITICAL PATH** — the system is useless without it
- Must **never block** the cashier workflow
- Kitchen printer is shared → must be concurrency-safe (threading lock)
- Arabic text rendering depends on printer model — test with actual hardware
- **No modifiers** — product name includes variation (e.g., "تشيكن فرايز حار" is one product)
- **Notes per item** — for special instructions like "3 pieces cold"
- Quantity is always **integer** (not decimal)
- **3 payment methods only**: كاش / فيزا / اونلاين
- **Visa NOT available for delivery**
- **Online delivery**: driver collects nothing (everything prepaid including delivery fee)
- **White-label receipts**: all branding from `restaurant.json`:
  - `{logo}` → `restaurant.logo_path`
  - `{restaurant_name}` → `restaurant.name_ar`
  - `{slogan}` → `restaurant.slogan_ar`
  - Receipt footer → `restaurant.receipt_footer`
- **Cash delivery**: driver collects full amount (food + delivery fee)
- Install dependency: `pip install python-escpos`

## 📌 Order Type Definitions (for template selection)

| Type | Arabic | Receipt Shows | Requires |
|------|--------|---------------|----------|
| Dine-In | صالة | Table number | Table # |
| Delivery | دليفري | Customer info + driver + delivery fee | Phone, Address, Zone |
| Takeaway | تيك اواي | "انتظار" banner — customer is standing and waiting | Nothing extra |
| Pickup | استلام محل | Customer name + phone — ordered by phone, will collect | Phone |

## 📌 Payment Availability per Order Type

| Method | Dine-In | Takeaway | Pickup | Delivery |
|--------|---------|----------|--------|----------|
| كاش | ✅ counter | ✅ counter | ✅ counter | ✅ driver collects ALL |
| فيزا | ✅ counter | ✅ counter | ✅ counter | ❌ NOT available |
| اونلاين | ✅ prepaid | ✅ prepaid | ✅ prepaid | ✅ driver collects NOTHING |
