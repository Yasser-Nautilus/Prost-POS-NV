# 📁 ui/components — PROGRESS

## 🎯 Goal

Build **reusable UI building blocks** — widgets that multiple views share. Every component must be touch-friendly with large, clearly labeled elements.

---

## ✅ Tasks

### 1. Product Grid (`product_grid.py`)

- **What**: Grid of large product buttons organized by category
- **Details**:
  - Receives product list from POS view (cached, no DB calls)
  - Large buttons: product name + price, minimum 80x60px
  - Responsive grid: adjusts columns based on window width
  - Click signal emits `product_id` → product goes **directly to order** (no popup)
  - Fast rendering: no heavy widget recreation on category switch
- **Why**: This is the most-tapped component. At 300+ orders/day × ~5 items = 1,500+ taps daily. Must be instant.
- **Important**: No modifier popup — tap product = add to order immediately.
- **Status**: `Done`

### 2. Order Panel (`order_panel.py`)

- **What**: Live order summary sidebar showing selected items
- **Details**:
  - Scrollable list of current order items
  - Each item row: name, quantity (**int**), line total
  - Large +/- buttons for quantity adjustment (NOT QSpinBox)
  - Remove item button (X)
  - **Notes field per item**: small text input for special instructions (e.g., "3 pieces cold")
  - Footer section: subtotal, service (if any), discount (if any), delivery fee (if delivery), grand total
  - Real-time update on every change
  - Signals: `item_added`, `item_removed`, `quantity_changed`, `note_changed`
- **Why**: The cashier needs instant visual feedback. Tap a product → appears immediately.
- **Status**: `Done`

### 3. Payment Dialog (`payment_dialog.py`)

- **What**: Modal dialog for completing payment
- **Details**:
  - Show order total prominently (large font)
  - **3 payment methods**: كاش / فيزا / اونلاين
  - **Visa disabled for delivery orders** (grayed out / hidden)
  - For كاش (cash): amount received input + auto-calculate change
  - For فيزا / اونلاين: Paid = Total, Change = 0 (no cash exchange)
  - Quick cash buttons: exact amount, round up (50, 100, 200, 500)
  - Confirm button → calls `order_service.complete_order()`
  - Cancel button → return to order (don't discard)
- **Status**: `Done`

### ~~4. Modifier Dialog~~ — **REMOVED**

- ~~Product customization popup~~
- **Why removed**: No modifier system. Each product variation (hot/cold, size) is a separate product in the menu. Tap product → goes directly to order. No popup needed.

### 4. PIN Dialog (`pin_dialog.py`)

- **What**: Manager override PIN input dialog
- **Details**:
  - Simple modal with masked PIN input (**any length** — not fixed to 4 digits)
  - On-screen numpad (for touch environments) with large buttons
  - "Confirm" calls `auth_service.verify_pin()` → returns user if MANAGER or ADMIN
  - Used for: cancel order, apply discount, remove items from saved order
  - Show clear error message if PIN is invalid or user lacks permission
  - On success: records WHO authorized it (for audit trail)
  - Auto-close on successful verification
- **Status**: `Done`

### 5. Customer Panel (`customer_panel.py`)

- **What**: Delivery/Pickup customer information widget (matches existing UI style)
- **Details**:
  - **Layout** (RTL, two rows):
    - **Row 1**: تليفون (Phone input, 11 digits) → ✓ checkmark (green if found) → العميل (Customer name)
    - **Row 2**: العنوان (Address) → street name field → المنطقة (Zone dropdown) → توصيل (Delivery fee, auto-filled, read-only)
    - **Row 3**: عناوين (Addresses) → colored address cards as clickable buttons
  - **Phone flow**:
    - Cashier types full 11-digit phone → clicks check button (or presses Enter)
    - System does exact match on `customers.phone`
    - **If found** (green checkmark ✓):
      - Auto-fill customer name
      - If 1 address → auto-select, fill street + zone + fee
      - If multiple → show colored address cards, cashier clicks one
      - "+ عنوان جديد" button to add new address
    - **If not found** (new customer):
      - Open dialog: name + street_name + zone dropdown
      - On save → creates customer + first address
  - **Address cards**: colored buttons showing "zone name - fee ج.م" (like screenshots)
    - Click card → fills street, zone, and delivery fee fields
  - **Zone dropdown**: pre-configured zones, auto-fills delivery fee (read-only)
  - **For Pickup**: phone + name only (no address/zone/fee needed)
    - If phone found → auto-fill name, ignore addresses
    - If phone NOT found → create a minimal customer record (name + phone only, no address required)
    - Customer record is created so future orders can find them by phone
  - Signals: `customer_selected(customer)`, `address_selected(address)`
- **Status**: `Not started`

### 6. Table Grid (`table_grid.py`)

- **What**: Visual table selector for dine-in orders
- **Details**:
  - Grid showing table numbers
  - Color-coded:
    - Green = available → click starts new order for this table
    - Red = occupied → click **loads existing order** for this table (edit or pay)
  - Shows order number on occupied tables (small text under table number)
  - **Shared across cashiers**: if Cashier 1 occupies Table 5, Cashier 2 sees it red too
  - Shows cashier name on occupied tables (so Cashier 2 knows it's not their order)
  - Signals:
    - `table_selected_new(table_number)` → start new order
    - `table_selected_existing(order_id)` → load saved order for edit/payment
- **Why**: The cashier clicks on the table to either create a new order or return to an existing dine-in order for payment or amendments.
- **Status**: `Done`

---

## 📝 Notes

- All components must have **minimum button size 60x60px**
- **Input**: mouse + keyboard (not touch screen)
- Components emit **signals**, they don't call services directly
- **ModifierDialog is REMOVED** — no modifier system exists
- Product tap → direct add to order (fastest possible flow)
- Use large +/- buttons instead of QSpinBox
- PIN Dialog supports **any-length PINs** (unique per user)
- Table grid is **shared** — both cashiers see the same occupied tables
- Each order shows **cashier name** for accountability
- **6 components** total (was 7, modifier dialog removed)
- **Theme**: all colors loaded from `restaurant.json` → applied via Qt StyleSheet
- **Font**: Noto Naskh Arabic (bundled in `assets/fonts/`)
- **Category colors**: each category gets a different color from `restaurant.json → category_colors[]`
- **RTL**: all layouts use `setLayoutDirection(Qt.RightToLeft)`
