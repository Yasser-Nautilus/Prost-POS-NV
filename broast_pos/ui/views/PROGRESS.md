# 📁 ui/views — PROGRESS

## 🎯 Goal

Implement all **main screens** (business flows). Each view is a `QWidget` that occupies the content area of the main window. Views call services — never the database directly.

---

## ✅ Tasks

### 0. Login View (`login_view.py`) — App Entry Point

- **What**: The first screen the user sees on app launch
- **Details**:
  - Shows all active users as **avatar tiles** (large circular avatar + username below)
  - Clicking a tile opens PIN entry (on-screen numpad, masked input)
  - On valid PIN → session created → navigate to POS View
  - On invalid PIN → shake animation + error message
  - **Logout** from any screen → returns here
  - **No username typing** — user taps their avatar, then enters PIN
  - If only 1 active user → show their tile alone (still require PIN)
- **Why**: Fast login for restaurant staff. Avatar-based tiles are easier than typing usernames with greasy hands.
- **Status**: `Done`

### 1. POS View (`pos_view.py`) — 🔥 MOST IMPORTANT

- **What**: The primary cashier screen for creating orders
- **Details**:
  - **Layout** (3-column):
    - Left column: Category tabs (vertical buttons)
    - Center: Product grid (large, touch-friendly buttons with name + price)
    - Right: Order summary panel (live list of selected items)
  - **Parked orders bar** (top of view):
    - Tab/button bar showing all in-memory orders
    - Each tab shows: order type icon + table number or "takeaway"
    - Click tab to switch to that order
    - "+" button to start a new order
    - Parked orders are in-memory only (not saved to DB)
  - **Order type selector**: 4 buttons (صالة / تيك اواي / دليفري / استلام محل)
    - **صالة (Dine-In)**: shows table grid selector
    - **دليفري (Delivery)**: shows customer panel (phone + address + zone)
    - **تيك اواي (Takeaway)**: no extra fields — customer is present
    - **استلام محل (Pickup)**: shows phone + name only
  - **Table grid interaction** (dine-in):
    - Green = available → click to start new order for this table
    - Red = occupied → click to **load existing order** for this table (edit or pay)
  - **Product selection**: tap category → products load → tap product → **add directly** (no popup)
  - **Quantity controls**: large +/- buttons (not QSpinBox)
  - **Notes per item**: small text field for special instructions
  - **Live totals**: subtotal, service (%), delivery fee (if delivery), discount (if applied), grand total
  - **Action buttons**:
    - تأكيد (Confirm) → validate → save → print kitchen ticket:
      - **Takeaway**: Payment Dialog appears immediately after save
      - **Delivery (online)**: mark as paid at save time
      - **Others**: save without payment (pay later)
    - دفع (Pay) → opens PaymentDialog (for saved orders loaded from table/tracking)
    - خصم (Discount) → requires manager PIN → unlocks discount field
    - إلغاء (Cancel) → requires manager PIN → cancels with reason
  - **Speed optimizations**:
    - Products cached in memory at view creation
    - No database calls during item selection
    - Instant response to every tap
- **Status**: `Done`

### 2. Tracking View (`tracking_view.py`)

- **What**: View and manage active orders by status
- **Details**:
  - Tab filters: الكل (All) / صالة / تيك اواي / دليفري / استلام محل
  - Order cards showing: invoice #, type, status, total, **time elapsed since creation**
  - Timer: live counter showing how long since the order was sent to kitchen
  - Click order → show details panel with items
  - **Visual auto-complete**:
    - Takeaway orders → after 20 minutes (configurable), card changes color (e.g., green highlight)
    - This is visual only — does NOT change the order's actual status
    - Indicates "this order should be ready by now"
    - Cashier can manually dismiss the highlight
  - Delivery orders → completed when driver confirms delivery
  - Search by invoice number
  - Auto-refresh every 10 seconds
- **Status**: `Done`

### 3. Delivery View (`delivery_view.py`)

- **What**: Driver lifecycle, trip dispatch, settlement, and end-of-day summary
- **Details**:
  - **Layout** (3-panel):
    - Left: Driver list with check-in/out controls
    - Center: Unassigned delivery orders + active trips
    - Right: Settlement panel (when a trip is selected)
  - **Driver panel** (left):
    - List of all drivers with current status: ✅ available / 🚗 out / ⬜ checked out
    - "Check In" button → activate driver (cashier action)
    - "Check Out" button → deactivate driver
    - Adding new drivers → redirects to Users view (manager only)
  - **Orders & trips panel** (center):
    - **Unassigned orders tab**: delivery orders not yet assigned to any driver (from both cashiers)
    - **Active trips tab**: trips currently in progress (dispatched, not yet returned)
    - **Unsettled trips tab**: trips returned but not yet settled (cashier can settle anytime)
    - Assign flow: select order(s) from list → select driver → "Create Trip" button
    - Manual selection only — no automatic grouping
    - "Mark Dispatched" button on created trips (when driver leaves)
    - "Mark Returned" button on dispatched trips (when driver comes back)
  - **Settlement panel** (right):
    - Select an unsettled trip → shows:
      - Orders on this trip: invoice #, total, payment method, collected amount
      - Cash orders: collected = order_total
      - Online orders: collected = 0 (مدفوع اونلاين)
      - Summary: cash collected, delivery fees earned, amount to hand over
    - "Confirm Settlement" button → marks trip as settled
    - "Print Receipt" button → prints settlement receipt
    - **No shortage tracking** — system records as fully delivered
  - **End-of-day section** (bottom or separate tab):
    - Shows ALL drivers with daily totals:
      - Driver name, trip count, order count, total fees earned
    - Grand total: sum of all delivery fee expenses
    - "Print Summary" button → prints multi-driver summary
- **Status**: `Done`

### 4. Reports View (`reports_view.py`) — Manager Only

- **What**: Comprehensive reporting dashboard with daily, monthly, and yearly views
- **Details**:
  - **Daily report** (on-screen + printable):
    - Order type breakdown (count + revenue) — matches receipt photo format
    - Payment method breakdown: كاش / فيزا / اونلاين
    - Cancelled orders count + reasons
    - Driver summary (trips, orders, fees)
    - Product sales ranking (qty sold per product)
    - Date picker to view past days
  - **Monthly dashboard**:
    - Total sales for the month
    - Daily sales chart (bar or line)
    - Best-selling items ranking (top 10-20)
    - Monthly expenses total + breakdown by category
  - **Yearly overview**:
    - Monthly sales summary (12 months)
    - Total revenue, total expenses
    - Best-selling items for the year
  - **Actions**:
    - Print any report (daily summary, driver summary) — thermal printer, silent
    - View on-screen (tables + simple charts)
    - Data is always stored — even if not exported yet (future: Google Sheets)
- **Status**: `Done`

### 5. Products View (`products_view.py`) — Manager Only

- **What**: Product, category, and zone management
- **Details**:
  - **Category management**: add, edit, reorder, activate/deactivate
  - **Product management**: add, edit, set price, assign to category, set sort order
  - Each variation is a separate product (no modifiers)
  - **Zone management** (tab or section):
    - Add new zone: name + delivery fee (e.g., "مدينة فاقوس" = 20)
    - Edit zone: update name or delivery fee
    - Activate/deactivate zones
    - List of all zones with fees — table format
  - **Auto-complete timeout setting**: configurable minutes for takeaway auto-highlight (default 20)
  - Table/grid view with inline editing
- **Status**: `Not started`

### 6. Users View (`users_view.py`) — Admin Only

- **What**: User management screen
- **Details**:
  - Add/edit users: username, display name, role (CASHIER/MANAGER/ADMIN), PIN
  - Upload or select avatar image (shown on login tiles)
  - Assign cashier slot (1 or 2) for receipt printer routing
  - Activate/deactivate users
  - Reset PIN
  - **PIN must be unique** — system validates on save
  - Adding drivers to system also happens here (create user with driver flag)
- **Status**: `Not started`

### 7. Financial View (`financial_view.py`) — Manager for close/transfer

- **What**: Shift lifecycle, expense entry, and end-of-day reconciliation
- **Details**:
  - **Open shift section**:
    - "Open Shift" button → any role can open
    - System blocks if a shift is already active
    - No opening cash amount — just click and go
    - Shows confirmation: "Shift opened. Invoice numbers start from #1."
  - **Active shift dashboard**:
    - Running totals: sales, expenses, pending orders
    - Live counters auto-updating
  - **Expense entry section**:
    - Amount input + description + category dropdown (delivery_fees, supplies, other)
    - "Add Expense" button → immutable after creation (cannot edit/delete)
    - List of today's expenses below
  - **Shift transfer** (mid-day handover):
    - Manager only (requires PIN)
    - **Step 1**: Manager adds any final expenses (e.g., supplies bought during shift)
    - **Step 2**: Shows current state: sales, expenses, pending breakdown, expected cash
    - **Step 3**: Select "transfer to" user from dropdown
    - **Step 4**: Auto-prints shift transfer report (تقرير تسليم وردية)
    - Records snapshot → shift continues with new cashier
    - Invoice numbers continue (no reset)
  - **Close shift** (end of day):
    - Manager only (requires PIN) + confirmation dialog
    - **System checks prerequisites**:
      - ⚠️ All driver trips must be settled
      - ⚠️ Daily summary must be printed at least once
    - Shows final summary:
      ```
      Sales:              10,000
      Expenses:           -2,000
      Pending delivery:     -500
      Pending dine-in:    -1,000
      Pending kitchen:      -800
      ─────────────────────────
      Expected cash:       5,700
      ```
    - Confirm → shift closed → next open resets invoices to #1
  - **Shift history**: past shifts with summaries (read-only)
- **Status**: `Done`

### ~~8. Reports View~~ — **MERGED into Task #4 above**

- This task was a duplicate of Task #4 (both described `reports_view.py`). All details have been consolidated into Task #4.

### ~~9. Expenses View~~ — **DEFERRED to v2**

- ~~Dedicated expense management page~~
- **Why deferred**: For v1, expense entry lives inside the Financial View (section 7). A dedicated page will be added in a future version.
- **v1 expense entry**: available in Financial View → "Expense entry section" (amount + description + category, immutable)

---

## 📝 Notes

- **POS View is highest priority** — everything else can wait
- All views call services, never repositories or database directly
- **Parked orders** = in-memory buffer, shown as tabs in POS view
- **Table click** = load existing order (dine-in pay/edit flow)
- **Takeaway** = Confirm triggers save + immediate Payment Dialog
- **Auto-complete** in tracking = visual only (color change), not a real status change
- **No kitchen display screen** — kitchen uses printed tickets only

### UI Theme Specs

- **Color scheme**: dark navy (`#0d1b2a` base) — all colors from `restaurant.json`
- **Font**: Noto Naskh Arabic (bundled in `assets/fonts/`)
- **Font sizes**: heading=18, body=14, button=16, small=12
- **Resolution**: 1920x1080 (target)
- **Window mode**: normal windowed (not fullscreen)
- **Minimum button size**: 60x60px
- **Input device**: mouse + keyboard (not touch screen)
- **RTL layout**: all text and layout is right-to-left
- **Category colors**: rotating palette from `restaurant.json → category_colors[]`
- **Accent colors**: UX-logical (green=confirm, red=cancel/danger, yellow=pending, blue=info)
- **White-label**: all branding from single `restaurant.json` file — no code changes for new restaurant
