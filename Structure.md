# 🏗️ Prost POS — Project Structure

> **Tech Stack**: Python 3 · PyQt6 · SQLite (WAL) · ESC/POS Thermal Printing
> **Target**: 1920×1080 · RTL Arabic-first · Dark Navy Theme · White-Label Ready
> **Status**: 🔴 Architecture & planning complete — zero implementation code yet

```
broast_pos/
│
├── main.py                          # Entry point only — no logic here
│
├── config/                          # ⚙️ Configuration — no business logic
│   ├── restaurant.json              # 🏷️ WHITE-LABEL: one file = new restaurant identity
│   ├── config.py                    # APP_NAME, VERSION, ENVIRONMENT, DEBUG, LANGUAGE
│   ├── printers.json                # Printer role → device mapping (USB/Network)
│   └── business_rules.py           # TAX, MAX_DISCOUNT, AUTO_PRINT, timers
│
├── core/                            # 🧠 Pure business logic — NO UI, NO database
│   ├── models/                      # Data classes — what things ARE
│   │   ├── order.py                 # Order, OrderItem, OrderStatus, OrderType, PaymentMethod
│   │   ├── user.py                  # User, UserRole (CASHIER / MANAGER / ADMIN)
│   │   ├── product.py               # Product, Category — NO Modifier model
│   │   ├── customer.py              # Customer, CustomerAddress, Zone
│   │   ├── delivery.py              # DeliveryTrip, DriverAttendance, DriverStatus
│   │   └── financial.py             # Shift, ShiftTransfer, CashTransaction, ShiftSummary
│   │
│   └── services/                    # Business rules — what things DO
│       ├── order_service.py         # Create, amend, complete, cancel (with PIN)
│       ├── auth_service.py          # Login, session, manager override
│       ├── delivery_service.py      # Check-in/out, trip dispatch, settlement
│       ├── product_service.py       # Product/category CRUD, search
│       ├── customer_service.py      # Phone lookup, address management, zone CRUD
│       ├── financial_service.py     # Shift open/close/transfer, expenses (immutable)
│       └── report_service.py        # Daily/monthly/yearly reports
│
├── data/                            # 💾 Everything about storage
│   ├── database/
│   │   ├── connection.py            # SQLite singleton (WAL mode)
│   │   ├── schema.sql               # 14 tables (NO modifier tables)
│   │   ├── migrations.py            # Version-tracked ALTER TABLE runner
│   │   └── seed.py                  # Default admin + sample products
│   │
│   └── repositories/                # 🔑 KEY LAYER — services → repos → SQLite
│       ├── base_repository.py       # Abstract base: get_by_id, save, delete
│       ├── order_repository.py      # Orders + items queries
│       ├── user_repository.py       # Auth queries, PIN lookup
│       ├── product_repository.py    # Products/categories queries
│       ├── customer_repository.py   # Phone lookup, addresses, zones
│       ├── delivery_repository.py   # Trips, attendance, settlement
│       └── financial_repository.py  # Shifts, expenses, pending calculations
│
├── infrastructure/                  # 🔌 External systems
│   ├── printing/
│   │   ├── printer_manager.py       # Routes: KITCHEN / CASHIER_1 / CASHIER_2
│   │   ├── escpos_printer.py        # USB/Network thermal (python-escpos)
│   │   ├── receipt_templates.py     # 10 print layouts in one file
│   │   └── printer_config.py        # JSON printer → device mapping
│   │
│   └── sync/                        # 🔮 Future Google Sheets integration
│       ├── sync_interface.py        # Abstract contract (stub)
│       └── sheets_sync.py           # No-op placeholder
│
└── ui/                              # 🖥️ PyQt6 — presentation only
    ├── app.py                       # QApplication setup
    ├── styles/
    │   └── theme.py                 # Global QSS dark navy theme
    │
    ├── windows/
    │   ├── main_window.py           # Navigation shell (role-based sidebar)
    │   └── login_window.py          # Avatar tiles + PIN entry
    │
    ├── views/                       # Each screen = one QWidget
    │   ├── login_view.py            # Avatar tiles → PIN → session
    │   ├── pos_view.py              # 🔥 3-column order creation (MOST IMPORTANT)
    │   ├── tracking_view.py         # Active orders, live timers
    │   ├── delivery_view.py         # 3-panel driver/trip/settlement
    │   ├── reports_view.py          # Daily/monthly/yearly reports
    │   ├── products_view.py         # Product/category/zone management
    │   ├── users_view.py            # User management + drivers
    │   └── financial_view.py        # Shift lifecycle, expenses
    │
    └── components/                  # 6 reusable widgets
        ├── product_grid.py          # Tap = add directly (NO popup)
        ├── order_panel.py           # Live items, +/-, per-item notes
        ├── payment_dialog.py        # كاش / فيزا / اونلاين
        ├── pin_dialog.py            # Manager override numpad
        ├── table_grid.py            # Green=free / Red=occupied
        └── customer_panel.py        # Phone lookup → address cards
```

---

## ❌ REMOVED from Original Design

| Item | Reason |
|------|--------|
| `modifier_dialog.py` | No modifier system — each variation is a separate product |
| `modifiers` table | Removed from schema |
| `product_modifiers` table | Removed from schema |
| `order_item_modifiers` table | Removed from schema |
| Expenses View (dedicated) | Deferred to v2 — lives inside Financial View |

## 📌 Key Design Decisions

| Decision | Detail |
|----------|--------|
| No modifiers | Variations = separate products |
| 3 payments only | كاش / فيزا / اونلاين — Visa NOT for delivery |
| Quantity = int | No fractional quantities |
| PIN = unique | Identifies WHO by PIN alone |
| Invoice resets daily | Resets to #1 on open_shift() |
| Expenses immutable | Cannot edit/delete after creation |
| No draft system | Unsaved orders = memory only |
| Zero print dialogs | All ESC/POS, all silent |
| White-label | Single restaurant.json swap |
| Offline-first | SQLite local, Google Sheets = future |