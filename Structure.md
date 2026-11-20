# Prost POS — Repository Structure

> **Last Updated:** 2026-11-20
> **Generated from:** Actual file tree on branch `dev`

## Overview

The repository contains a Python backend (`broast_pos/`), a React + TypeScript frontend (`frontend/`), test suites (`tests/`), and project documentation at the root level. Legacy PyQt6 UI files are retained under `broast_pos/ui/` but are not used by the active runtime.

---

## Root

```
Prost-POS-NV/
├── broast_pos/                      # Python backend (Clean Architecture)
├── frontend/                        # React + TypeScript frontend
├── tests/                           # Test suites (23 files)
├── docs/                            # Technical documentation
│   └── TECHNICAL_AUDIT_REPORT.md
├── main.py                          # (Convenience entry — actual entry is broast_pos/main.py)
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variable template
├── .gitignore
├── Pos Project Structure + Progress.md   # Project overview and progress
├── README.md                        # Project readme
└── Structure.md                     # This file
```

## Backend — `broast_pos/`

```
broast_pos/
├── __init__.py
├── main.py                              # Application entry point (225 lines)
│                                        #   → DB init → Repos → Services → Bridge → WebShell
│
├── config/
│   ├── __init__.py
│   ├── config.py                        # Environment-driven config via os.getenv (140 lines)
│   └── PROGRESS.md
│
├── core/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── order.py                     # Order, OrderItem, OrderType, OrderStatus, PaymentMethod
│   │   ├── user.py                      # User, UserRole (with pin_salt)
│   │   ├── product.py                   # Product, Category
│   │   ├── customer.py                  # Customer, CustomerAddress, Zone
│   │   ├── delivery.py                  # DeliveryTrip, DriverAttendance, DriverStatus
│   │   ├── financial.py                 # Shift, ShiftTransfer, CashTransaction, ShiftSummary
│   │   ├── audit.py                     # AuditEventType constants class
│   │   ├── cashier_session.py           # Station, CashierSession, LedgerEntryType, CashLedgerEntry
│   │   ├── driver_settlement.py         # DriverSettlement dataclass
│   │   ├── order_status_history.py      # OrderStatusHistory dataclass
│   │   └── PROGRESS.md
│   ├── policies/
│   │   ├── __init__.py
│   │   └── discount.py                  # compute_discount (Decimal precision)
│   └── services/
│       ├── __init__.py
│       ├── order_service.py             # Order state machine, CRUD, ledger (893 lines)
│       ├── auth_service.py              # PBKDF2 auth, throttle, legacy upgrade (514 lines)
│       ├── delivery_service.py          # Driver lifecycle, trips (604 lines)
│       ├── driver_settlement_service.py # Settlement, ledger entries (543 lines)
│       ├── report_service.py            # Daily/shift/monthly/yearly reports (451 lines)
│       ├── cashier_session_service.py   # Session lifecycle, ledger (398 lines)
│       ├── business_day_service.py      # X/Z reports, business-day close (358 lines)
│       ├── financial_service.py         # Shift lifecycle, expenses (320 lines)
│       ├── customer_service.py          # Customer/address/zone management (251 lines)
│       ├── product_service.py           # Product/category CRUD (195 lines)
│       ├── audit_service.py             # Audit logging and queries (168 lines)
│       └── PROGRESS.md
│
├── data/
│   ├── __init__.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── schema.sql                   # 19 tables, triggers, indexes (475 lines)
│   │   ├── connection.py                # Singleton, WAL, FK ON, busy_timeout (244 lines)
│   │   ├── migrations.py               # LATEST_VERSION=6, 5 migrations (364 lines)
│   │   ├── seed.py                      # Default admin seeding (164 lines)
│   │   └── PROGRESS.md
│   └── repositories/
│       ├── __init__.py
│       ├── base_repository.py           # Abstract base with connection access
│       ├── order_repository.py          # Full CRUD, batch items, shift queries (509 lines)
│       ├── product_repository.py        # Product/category persistence
│       ├── customer_repository.py       # Customer/address/zone persistence
│       ├── user_repository.py           # User CRUD
│       ├── delivery_repository.py       # Trip/driver persistence
│       ├── financial_repository.py      # Shift/transaction persistence
│       ├── report_repository.py         # Report queries
│       ├── audit_repository.py          # Audit log persistence
│       ├── cash_ledger_repository.py    # Append-only ledger, balance queries (204 lines)
│       ├── cashier_session_repository.py    # Session CRUD, station queries (164 lines)
│       ├── driver_settlement_repository.py  # Settlement persistence (131 lines)
│       ├── order_status_history_repository.py  # Status history persistence (121 lines)
│       └── PROGRESS.md
│
├── features/                            # Feature-level documentation
│   ├── delivery_system/
│   │   └── PROGRESS.md
│   ├── financial/
│   │   └── PROGRESS.md
│   ├── order_lifecycle/
│   │   └── PROGRESS.md
│   ├── printing_flow/
│   │   └── PROGRESS.md
│   ├── reports/
│   │   └── PROGRESS.md
│   └── user_permissions/
│       └── PROGRESS.md
│
├── infrastructure/
│   ├── __init__.py
│   ├── printing/
│   │   ├── __init__.py
│   │   ├── printer_manager.py           # Central routing, 3 roles, thread-safe (223 lines)
│   │   ├── print_triggers.py            # Event-driven silent printing (159 lines)
│   │   ├── escpos_printer.py            # ESC/POS hardware interface
│   │   ├── receipt_templates.py         # Arabic/English receipt formatting
│   │   ├── printer_config.py            # Printer configuration loader
│   │   └── PROGRESS.md
│   ├── web_bridge/
│   │   ├── __init__.py
│   │   └── bridge.py                    # POSBridge dispatch, 6 controllers (1016 lines)
│   └── sync/
│       ├── __init__.py
│       └── PROGRESS.md                  # All Deferred
│
└── ui/
    ├── __init__.py
    ├── web_shell.py                     # QWebEngineView + QWebChannel (170 lines)
    ├── components/                      # Legacy PyQt6 components (retained, unused)
    │   └── PROGRESS.md
    ├── views/                           # Legacy PyQt6 views (retained, unused)
    │   └── PROGRESS.md
    ├── styles/                          # Legacy PyQt6 theme (retained, unused)
    │   └── PROGRESS.md
    └── windows/                         # Legacy PyQt6 windows (retained, unused)
        └── PROGRESS.md
```

## Frontend — `frontend/`

```
frontend/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── PROGRESS.md
└── src/
    ├── main.tsx                          # React entry point
    ├── App.tsx                           # App shell, role-based nav (224 lines)
    ├── bridge.ts                         # POSBridgeClient, QWebChannel, mock (1330 lines)
    ├── index.css                         # Tailwind imports
    ├── views/
    │   ├── POSView.tsx                   # Order entry and management
    │   ├── DeliveryView.tsx              # Delivery and driver management
    │   ├── TrackingView.tsx              # Order tracking board
    │   ├── ReportsView.tsx              # Report display
    │   ├── ProductsView.tsx             # Product/category management
    │   ├── DriverSettlementView.tsx     # Per-trip settlement (640 lines)
    │   ├── AuditLogView.tsx             # Audit trail viewer (308 lines)
    │   ├── UsersView.tsx                # User management (admin)
    │   ├── LoginView.tsx                # PIN-based login
    │   └── SessionsView.tsx             # Cashier sessions (693 lines) ⚠️ NOT MOUNTED
    └── components/
        ├── CustomerHistoryModal.tsx
        ├── CustomerLookup.tsx
        ├── DiscountDialog.tsx
        ├── Numpad.tsx
        ├── PaymentDialog.tsx
        ├── PinDialog.tsx
        ├── ShiftDialog.tsx              # Legacy shift dialog (still active)
        └── TableGrid.tsx
```

## Tests — `tests/`

```
tests/
├── 23 test files (6,369 total lines)
├── test_b01_order_service.py
├── test_b02_financial_service.py
├── test_b03_delivery_service.py
├── test_b04_customer_service.py
├── test_b05_auth_service.py
├── test_b06_product_service.py
├── test_b07_integration.py
├── test_b08_order_completion.py
├── test_b09_report_service.py
├── test_b10_shift_reports.py
├── test_b11_cashier_session.py
├── test_b12_cash_ledger.py
├── test_b13_business_day.py
├── test_b14_driver_settlement.py
├── test_b15_audit.py
├── test_b16_session_controller.py
├── test_b17_reports_controller.py
├── test_b18_order_lifecycle.py
├── test_b19_permissions.py
├── test_v2_phase1.py
├── test_v2_phase2.py
├── test_v2_phase3.py
├── test_v2_phase4.py
├── test_v2_phase5.py
└── PROGRESS.md
```

## Documentation — `docs/`

```
docs/
└── TECHNICAL_AUDIT_REPORT.md            # Technical debt, bugs, and security findings
```
