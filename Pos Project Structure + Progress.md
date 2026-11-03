# 📦 Prost POS — Complete Project Structure + Progress

> **Last Updated**: 2026-06-02
> **Tech**: Python 3 · PyQt6 · SQLite (WAL) · ESC/POS · White-Label
> **Restaurant**: بروستش / Prostsh (configurable via restaurant.json)
> **Overall Status**: 🟢 **~95% implemented** — 85/89 tasks Done, 4 deferred (sync module)
> **Codebase**: 79 Python files · ~19,645 lines of code · Working application

> **⚠️ Note**: Multi-device mode (secondary PC over network) is **DEFERRED to v2**. V1 is single-PC only.

---

# 📊 Progress Summary Dashboard

| Module | Files Planned | Files Done | Tasks | Status |
|--------|:---:|:---:|:---:|:---:|
| config/ | 4 | 4 | 5/5 | 🟢 Done |
| core/models/ | 6 | 6 | 7/7 | 🟢 Done |
| core/services/ | 7 | 7 | 7/7 | 🟢 Done |
| data/database/ | 4 | 4 | 5/5 | 🟢 Done |
| data/repositories/ | 8 | 8 | 8/8 | 🟢 Done |
| infrastructure/printing/ | 4 | 5 | 5/5 | 🟢 Done |
| infrastructure/sync/ | 2 | 0 | 0/4 | 🔴 Deferred to v2 |
| ui/styles/ | 1 | 1 | 1/1 | 🟢 Done |
| ui/windows/ | 2 | 2 | 2/2 | 🟢 Done |
| ui/views/ | 8 | 8 | 8/8 | 🟢 Done |
| ui/components/ | 4 | 4 | 4/4 | 🟢 Done |
| ui/dialogs/ | 4 | 4 | 4/4 | 🟢 Done |
| features/ (controllers) | 6 | 8 | 8/8 | 🟢 Done |
| **feature/order_lifecycle** | cross-cutting | — | 8/8 | 🟢 Done |
| **feature/delivery_system** | cross-cutting | — | 8/8 | 🟢 Done |
| **feature/printing_flow** | cross-cutting | — | 5/5 | 🟢 Done |
| **feature/reports** | cross-cutting | — | 4/4 | 🟢 Done |
| **feature/user_permissions** | cross-cutting | — | 5/5 | 🟢 Done |
| **TOTAL** | ~51 files | 79 files | **85/89** | 🟢 **95%** |

---

# 🏗️ Project Structure (Annotated)

```
broast_pos/
├── main.py                          # Entry point (536 lines): load config → init DB → seed → create services → start QApplication → show login
├── config/
│   ├── restaurant.json              # ✅ White-label identity (name, logo, colors, fonts)
│   ├── config.py                    # ✅ APP_NAME, VERSION, ENVIRONMENT, DEBUG, business rules
│   └── printers.json                # ✅ Printer role → device mapping
├── core/
│   ├── models/                      # ✅ Pure dataclasses — NO DB, NO UI
│   │   ├── order.py                 # ✅ Order, OrderItem, OrderStatus, OrderType, PaymentMethod (195 lines)
│   │   ├── user.py                  # ✅ User, UserRole (CASHIER/MANAGER/ADMIN)
│   │   ├── product.py               # ✅ Product, Category (NO modifiers)
│   │   ├── customer.py              # ✅ Customer, CustomerAddress, Zone
│   │   ├── delivery.py              # ✅ DeliveryTrip, DriverAttendance, DriverStatus
│   │   └── financial.py             # ✅ Shift, ShiftTransfer, CashTransaction, ShiftSummary
│   └── services/                    # ✅ Business logic — calls repos, never DB directly
│       ├── order_service.py         # ✅ Create, amend(تابع), complete, cancel (363 lines)
│       ├── auth_service.py          # ✅ Login, session, verify_pin (manager override) (246 lines)
│       ├── delivery_service.py      # ✅ Check-in/out, trips, settlement, daily summary (302 lines)
│       ├── product_service.py       # ✅ CRUD, search (<100ms) (197 lines)
│       ├── customer_service.py      # ✅ Phone lookup, addresses, zones (202 lines)
│       ├── financial_service.py     # ✅ Shift lifecycle, expenses, invoice counter (304 lines)
│       └── report_service.py        # ✅ Daily/monthly/yearly reports (327 lines)
├── data/
│   ├── database/
│   │   ├── connection.py            # ✅ SQLite singleton, WAL mode, foreign keys (190 lines)
│   │   ├── schema.sql               # ✅ 14 tables (NO modifier tables)
│   │   ├── migrations.py            # ✅ Version-tracked schema updates (149 lines)
│   │   └── seed.py                  # ✅ Default admin + sample data (164 lines)
│   └── repositories/                # ✅ Abstract DB access — enables future sync
│       ├── base_repository.py       # ✅ Generic ABC
│       ├── order_repository.py      # ✅ (383 lines)
│       ├── user_repository.py       # ✅ (170 lines)
│       ├── product_repository.py    # ✅ (168 lines)
│       ├── customer_repository.py   # ✅ (184 lines)
│       ├── delivery_repository.py   # ✅ (338 lines)
│       ├── financial_repository.py  # ✅ (369 lines)
│       └── audit_repository.py      # ✅ (168 lines)
├── features/                        # ✅ Cross-cutting controllers
│   ├── order_lifecycle/
│   │   ├── order_controller.py      # ✅ Full order lifecycle (636 lines)
│   │   ├── amendment_tracker.py     # ✅ Snapshot + diff for edits (126 lines)
│   │   ├── payment_coordinator.py   # ✅ Payment method validation (124 lines)
│   │   └── invoice_manager.py       # ✅ Race-safe invoice numbers (73 lines)
│   ├── delivery_system/
│   │   └── delivery_controller.py   # ✅ Driver lifecycle + settlement (347 lines)
│   ├── printing_flow/
│   │   └── printing_controller.py   # ✅ Silent print orchestration (212 lines)
│   ├── reports/
│   │   └── reports_controller.py    # ✅ Report generation + validation (486 lines)
│   ├── financial/
│   │   └── financial_controller.py  # ✅ Shift lifecycle UI orchestration (219 lines)
│   └── user_permissions/
│       └── permissions_controller.py # ✅ Role-based access + audit logging (437 lines)
├── infrastructure/
│   ├── printing/
│   │   ├── printer_manager.py       # ✅ Routes to KITCHEN / CASHIER_1 / CASHIER_2 (224 lines)
│   │   ├── escpos_printer.py        # ✅ USB/Network/Serial thermal adapter (219 lines)
│   │   ├── receipt_templates.py     # ✅ 10 print layouts (572 lines)
│   │   ├── printer_config.py        # ✅ JSON config loader
│   │   └── print_triggers.py        # ✅ Auto-trigger hooks (159 lines)
│   └── sync/                        # 🔴 DEFERRED to v2
│       └── __init__.py              # Placeholder only
└── ui/                              # ✅ PyQt6 — ZERO business logic
    ├── styles/
    │   └── theme.py                 # ✅ Dark navy QSS, Arabic fonts, RTL (521 lines)
    ├── windows/
    │   ├── main_window.py           # ✅ Sidebar navigation shell (role-based) (552 lines)
    │   └── login_window.py          # ✅ Window container for login (wraps login_view)
    ├── views/
    │   ├── login_view.py            # ✅ User avatar tiles → PIN → session (593 lines)
    │   ├── pos_view.py              # ✅ 🔥 Main cashier screen (3-column) (944 lines)
    │   ├── tracking_view.py         # ✅ Active orders, timers, auto-complete visual (688 lines)
    │   ├── delivery_view.py         # ✅ 3-panel: drivers | trips | settlement (792 lines)
    │   ├── reports_view.py          # ✅ Reports dashboard + print (999 lines)
    │   ├── products_view.py         # ✅ Products/categories/zones (Manager) (827 lines)
    │   ├── users_view.py            # ✅ User management (Admin) (360 lines)
    │   └── financial_view.py        # ✅ Shift/expenses/reconciliation (Manager) (667 lines)
    ├── components/                   # ✅ Reusable widgets
    │   ├── product_grid.py          # ✅ Tap = add to order (NO popup) (226 lines)
    │   ├── order_panel.py           # ✅ Live items, +/-, notes, totals (481 lines)
    │   ├── customer_panel.py        # ✅ Phone → auto-fill → address cards (413 lines)
    │   └── table_grid.py            # ✅ Green=free / Red=occupied (204 lines)
    └── dialogs/                      # ✅ Modal dialogs
        ├── payment_dialog.py        # ✅ كاش / فيزا / اونلاين (476 lines)
        ├── pin_dialog.py            # ✅ Manager override numpad (331 lines)
        ├── shift_dialog.py          # ✅ Shift transfer/close flows (539 lines)
        └── expense_dialog.py        # ✅ Expense entry form (245 lines)
```

---

# 📁 MODULE-LEVEL STATUS

---

## 📁 config/ — 🟢 DONE (5/5)

| # | Task | Status |
|---|------|:---:|
| 1 | Restaurant Branding (`restaurant.json`) | 🟢 Done |
| 2 | General Settings (`config.py`) | 🟢 Done |
| 3 | Printer Config (`printers.json`) | 🟢 Done |
| 4 | Business Rules | 🟢 Done |
| 5 | Paths & Files | 🟢 Done |

---

## 📁 core/models/ — 🟢 DONE (7/7)

| # | Task | Status |
|---|------|:---:|
| 1 | Order Model (Order, OrderItem, OrderStatus, OrderType, PaymentMethod) | 🟢 Done |
| 2 | OrderItem Model (inside order.py) | 🟢 Done |
| 3 | User Model (User, UserRole) | 🟢 Done |
| 4 | Product Model (Product, Category) | 🟢 Done |
| 5 | Customer Model (Customer, CustomerAddress, Zone) | 🟢 Done |
| 6 | Delivery Model (DeliveryTrip, DriverAttendance, DriverStatus) | 🟢 Done |
| 7 | Financial Model (Shift, ShiftTransfer, CashTransaction, ShiftSummary) | 🟢 Done |

---

## 📁 core/services/ — 🟢 DONE (7/7)

| # | Service | Status |
|---|---------|:---:|
| 1 | OrderService | 🟢 Done |
| 2 | AuthService | 🟢 Done |
| 3 | DeliveryService | 🟢 Done |
| 4 | ProductService | 🟢 Done |
| 5 | CustomerService | 🟢 Done |
| 6 | FinancialService | 🟢 Done |
| 7 | ReportService | 🟢 Done |

---

## 📁 data/database/ — 🟢 DONE (5/5)

| # | Task | Status |
|---|------|:---:|
| 1 | Connection (WAL, singleton, Row factory) | 🟢 Done |
| 2 | Schema (14 tables, no modifier tables) | 🟢 Done |
| 3 | Indexes (11 performance indexes) | 🟢 Done |
| 4 | Migrations (version-tracked, auto-run) | 🟢 Done |
| 5 | Seed Data (admin, categories, products, zones) | 🟢 Done |

---

## 📁 data/repositories/ — 🟢 DONE (8/8)

| # | Repository | Status |
|---|-----------|:---:|
| 1 | BaseRepository (ABC, Generic CRUD) | 🟢 Done |
| 2 | OrderRepository | 🟢 Done |
| 3 | UserRepository | 🟢 Done |
| 4 | ProductRepository | 🟢 Done |
| 5 | CustomerRepository | 🟢 Done |
| 6 | DeliveryRepository | 🟢 Done |
| 7 | FinancialRepository | 🟢 Done |
| 8 | AuditRepository | 🟢 Done |

---

## 📁 infrastructure/printing/ — 🟢 DONE (5/5)

| # | Task | Status |
|---|------|:---:|
| 1 | PrinterManager (route to KITCHEN / CASHIER_1 / CASHIER_2) | 🟢 Done |
| 2 | ESC/POS Adapter (USB/Network/Serial/Dummy) | 🟢 Done |
| 3 | Receipt Templates (10 layouts) | 🟢 Done |
| 4 | Silent Printing (auto-trigger, zero dialogs) | 🟢 Done |
| 5 | Printer Config (JSON loader) | 🟢 Done |

---

## 📁 infrastructure/sync/ — 🔴 DEFERRED (0/4)

| # | Task | Status |
|---|------|:---:|
| 1 | Sync Interface (abstract contract) | 🔴 Deferred |
| 2 | Event Hooks (design only) | 🔴 Deferred |
| 3 | Sheets Adapter (stub) | 🔴 Deferred |
| 4 | Background Worker (future) | 🔴 Deferred |

> **Note**: Sync is intentionally deferred. Local system must be stable first.

---

## 📁 ui/styles/ — 🟢 DONE (1/1)

| # | Task | Status |
|---|------|:---:|
| 1 | Global Theme (dark navy, Arabic fonts, RTL, 521 lines QSS) | 🟢 Done |

---

## 📁 ui/windows/ — 🟢 DONE (2/2)

| # | Task | Status |
|---|------|:---:|
| 1 | Main Window (sidebar nav, role-based, collapsible) | 🟢 Done |
| 2 | Login Window (container for login_view) | 🟢 Done |

---

## 📁 ui/views/ — 🟢 DONE (8/8)

| # | View | Lines | Status |
|---|------|:---:|:---:|
| 0 | Login View (avatar tiles + PIN) | 593 | 🟢 Done |
| 1 | **POS View** 🔥 (3-column cashier screen) | 944 | 🟢 Done |
| 2 | Tracking View (timers, auto-highlight) | 688 | 🟢 Done |
| 3 | Delivery View (3-panel driver management) | 792 | 🟢 Done |
| 4 | Reports View (daily/monthly/yearly + print) | 999 | 🟢 Done |
| 5 | Products View (CRUD + zones, manager only) | 827 | 🟢 Done |
| 6 | Users View (admin only) | 360 | 🟢 Done |
| 7 | Financial View (shift lifecycle + expenses) | 667 | 🟢 Done |

---

## 📁 ui/components/ — 🟢 DONE (4/4)

| # | Component | Lines | Status |
|---|-----------|:---:|:---:|
| 1 | Product Grid (tap = add directly) | 226 | 🟢 Done |
| 2 | Order Panel (live items, +/-, notes, totals) | 481 | 🟢 Done |
| 3 | Customer Panel (phone → auto-fill → address cards) | 413 | 🟢 Done |
| 4 | Table Grid (green=free, red=occupied) | 204 | 🟢 Done |

---

## 📁 ui/dialogs/ — 🟢 DONE (4/4)

| # | Dialog | Lines | Status |
|---|--------|:---:|:---:|
| 1 | Payment Dialog (كاش/فيزا/اونلاين, quick buttons) | 476 | 🟢 Done |
| 2 | PIN Dialog (manager override, on-screen numpad) | 331 | 🟢 Done |
| 3 | Shift Dialog (transfer + close flows) | 539 | 🟢 Done |
| 4 | Expense Dialog (amount + category + description) | 245 | 🟢 Done |

---

# 🧩 FEATURE-LEVEL STATUS

---

## 📦 feature/order_lifecycle — 🟢 DONE (8/8)

| # | Task | Status |
|---|------|:---:|
| 1 | Create Order (in-memory → validate → save) | 🟢 Done |
| 2 | Parked Orders (multi-order tabs, in-memory) | 🟢 Done |
| 3 | Validate & Save (shift guard, kitchen print, takeaway auto-pay) | 🟢 Done |
| 4 | Payment Flow (separate from save, 3 methods) | 🟢 Done |
| 5 | Edit Saved Order (تابع, manager PIN for removals) | 🟢 Done |
| 6 | Status Transitions (simplified: ACTIVE → COMPLETED / delivery chain) | 🟢 Done |
| 7 | Cancel Order (manager PIN + reason + audit) | 🟢 Done |
| 8 | Invoice Numbers (race-safe, resets per shift) | 🟢 Done |

**Controllers**: `order_controller.py` (636), `amendment_tracker.py` (126), `payment_coordinator.py` (124), `invoice_manager.py` (73)

---

## 🚚 feature/delivery_system — 🟢 DONE (8/8)

| # | Task | Status |
|---|------|:---:|
| 1 | Driver Management (check-in/out, status tracking) | 🟢 Done |
| 2 | Assign Driver to Trip (manual order selection) | 🟢 Done |
| 3 | Mark Out for Delivery (dispatch timestamp) | 🟢 Done |
| 4 | Mark Returned (driver back, orders → DELIVERED) | 🟢 Done |
| 5 | Per-Trip Settlement 🔥 (cash vs online breakdown) | 🟢 Done |
| 6 | Settlement Receipt (per-trip print) | 🟢 Done |
| 7 | End-of-Day Summary 🔥 (all drivers aggregate) | 🟢 Done |
| 8 | Expense Entry (manual v1) | 🟢 Done |

**Controller**: `delivery_controller.py` (347 lines)

---

## 🖨️ feature/printing_flow — 🟢 DONE (5/5)

| # | Task | Status |
|---|------|:---:|
| 1 | Kitchen Ticket (auto on save, NO prices) | 🟢 Done |
| 2 | Customer Receipt (4 variants by order type) | 🟢 Done |
| 3 | Daily Summary (matches receipt format) | 🟢 Done |
| 4 | Driver Settlement Receipt | 🟢 Done |
| 5 | Failure Handling (log, badge, never block) | 🟢 Done |

**Controller**: `printing_controller.py` (212 lines)

---

## 📊 feature/reports — 🟢 DONE (4/4)

| # | Task | Status |
|---|------|:---:|
| 1 | Aggregate by Type (صالة/تيك اواي/دليفري/استلام محل) | 🟢 Done |
| 2 | Daily Summary (shift-based structured data) | 🟢 Done |
| 3 | Print Integration (thermal, silent) | 🟢 Done |
| 4 | Consistency Checks (cross-validate sums) | 🟢 Done |

**Controller**: `reports_controller.py` (486 lines)

---

## 🔐 feature/user_permissions — 🟢 DONE (5/5)

| # | Task | Status |
|---|------|:---:|
| 1 | Role Model (CASHIER/MANAGER/ADMIN hierarchy) | 🟢 Done |
| 2 | PIN Storage (SHA-256 hash, UNIQUE) | 🟢 Done |
| 3 | Manager Override (PIN → verify → audit trail) | 🟢 Done |
| 4 | Audit Logging (cancel, discount, shift events) | 🟢 Done |
| 5 | Navigation Access (sidebar by role) | 🟢 Done |

**Controller**: `permissions_controller.py` (437 lines)

---

# 🧭 EXECUTION ROADMAP

| Phase | Scope | Status |
|:---:|-------|:---:|
| **1** | Database + Models + Connection | 🟢 Done |
| **2** | Repositories + Base CRUD | 🟢 Done |
| **3** | Auth Service + Login UI | 🟢 Done |
| **4** | Product Service + POS View (core) | 🟢 Done |
| **5** | Order Service + Kitchen Printing | 🟢 Done |
| **6** | Payment Flow + Receipt Printing | 🟢 Done |
| **7** | Tracking View + Status Transitions | 🟢 Done |
| **8** | Customer/Delivery Service + Delivery View | 🟢 Done |
| **9** | Financial Service + Shift Lifecycle | 🟢 Done |
| **10** | Reports + Daily Summary | 🟢 Done |
| **11** | Permissions + Audit + PIN Override | 🟢 Done |
| **12** | Polish: Theme, White-Label, Config | 🟢 Done |

---

# 🔧 Recent Fixes & Refinements (Latest Commits)

| Commit | Description |
|--------|-------------|
| `50cecfd` | Collapsible sidebar + order type buttons moved to top parked-orders bar |
| `faff188` | All internal components made flexible (responsive sizing) |
| `db1f891` | PIN and Payment dialogs made flexible |
| `590eb02` | Main window sidebar and header made flexible |
| `029628e` | POS view 3-column layout with stretch factors |
| `04015fb` | Inject delivery_service into FinancialService for driver settlement check |
| `3a1417b` | `_recalc_totals()` delegates to `Order.recalculate()` |
| `6b1b4b6` | Fix order_controller references to non-existent attributes |
| `955750e` | Eliminate dashed border in empty order state |

---

# 📌 What's Left (v1 Polish)

| Item | Priority | Notes |
|------|:---:|-------|
| Real hardware printer testing | 🔴 High | Test with actual ESC/POS thermal printers |
| End-to-end order flow testing | 🔴 High | Full workflow: login → create → pay → print |
| Edge case handling | 🟡 Medium | Network errors, concurrent access, corrupt data |
| Sync module stubs | 🟡 Low | Interface + no-op adapter for future Google Sheets |
| Performance profiling | 🟡 Low | Verify <100ms product search at scale |

---

# 📌 Critical Business Rules Reference

### Order Type Requirements
| Type | Arabic | Requires |
|------|--------|----------|
| Dine-In | صالة | Table number |
| Delivery | دليفري | Phone + Address + Zone |
| Takeaway | تيك اواي | Nothing extra |
| Pickup | استلام محل | Phone |

### Payment Availability
| Method | Dine-In | Takeaway | Pickup | Delivery |
|--------|:---:|:---:|:---:|:---:|
| كاش | ✅ | ✅ | ✅ | ✅ driver collects ALL |
| فيزا | ✅ | ✅ | ✅ | ❌ NOT available |
| اونلاين | ✅ | ✅ | ✅ | ✅ driver collects NOTHING |

### Financial Formulas
```
subtotal         = Σ(qty × unit_price) for all items
service          = subtotal × (SERVICE_CHARGE_PCT / 100)
discount_amount  = value (if flat) OR subtotal × (value / 100) (if percent)
total            = subtotal + service - discount_amount + delivery_fee
change           = max(0, paid - total)
restaurant_revenue = total - delivery_fee   ← restaurant's actual income
expected_cash    = total_sales - total_expenses - pending_delivery - pending_dinein - pending_kitchen
```

---

# ❌ Removed from Original Design

| Item | Reason |
|------|--------|
| Modifier Dialog | No modifier system — each variation is separate product |
| modifiers table | Eliminated from schema |
| product_modifiers table | Eliminated from schema |
| order_item_modifiers table | Eliminated from schema |
| Dedicated Expenses View | Deferred to v2 — lives inside Financial View |
| Fast user switch | Full logout/login every time (Option A) |
| Draft system | Unsaved orders = memory only |
| Touch screen optimization | Input is mouse + keyboard |

---

✅ **IMPLEMENTATION ~95% COMPLETE — READY FOR TESTING & POLISH**
