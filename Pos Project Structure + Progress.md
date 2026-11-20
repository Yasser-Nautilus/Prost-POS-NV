# Prost POS — Project Structure & Progress

> **Last Updated:** 2026-11-20
> **Branch:** `dev`
> **Schema Version:** 6
> **Documentation generated from:** Source code audit of all implementation files

---

## Project Overview

Prost POS is a hybrid desktop point-of-sale application for a restaurant (Broast/fried chicken), combining a **Python backend** with a **React + TypeScript frontend** rendered inside a **PySide6 QWebEngineView**. The system supports dine-in, takeaway, and delivery order types, with integrated driver management, cashier session accounting, cash ledger reconciliation, printing, and audit logging.

### Technology Stack

| Layer | Technology |
|---|---|
| Desktop Shell | PySide6 / QWebEngineView |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Bridge | QWebChannel → `POSBridge.dispatch()` |
| Backend | Python 3.12+, Clean Architecture |
| Database | SQLite (WAL mode, FK enforcement) |
| Printing | python-escpos (ESC/POS thermal printers) |
| Auth | PBKDF2-HMAC-SHA256 (salted + peppered) with legacy SHA-256 auto-upgrade |

---

## Architecture

### Runtime Initialization Flow

```
main.py
  → DatabaseConnection.get_instance()       # Singleton, WAL, FK ON, busy_timeout=5000
  → initialise_database(schema.sql)          # 19 tables
  → run_migrations()                         # v1 → v6
  → seed_database()                          # Default admin user
  → 12 Repositories instantiated
  → 11 Services instantiated (with dependency injection)
  → PrinterManager instantiated
  → QApplication created
  → WebShell(POSBridge) launched
  → QTimer for takeaway auto-complete (60 s interval)
  → app.exec()
```

### Frontend Request Flow

```
React View → bridge.ts → QWebChannel → POSBridge.dispatch(action, payload)
  → Controller method → Service → Repository → SQLite
  → Response dict → bridge.ts callback → React state update
```

### Key Runtime Classes

| Class | File | Responsibility |
|---|---|---|
| `DatabaseConnection` | `broast_pos/data/database/connection.py` | Singleton SQLite connection, WAL, transactions |
| `POSBridge` | `broast_pos/infrastructure/web_bridge/bridge.py` | Central dispatch, auth guard, 6 sub-routers |
| `WebShell` | `broast_pos/ui/web_shell.py` | QWebEngineView + QWebChannel host |
| `POSWebPage` | `broast_pos/ui/web_shell.py` | Custom QWebEnginePage for JS console logging |

---

## Project Structure

### Backend — `broast_pos/`

```
broast_pos/
├── main.py                          # Application entry point (225 lines)
├── config/
│   └── config.py                    # Environment-driven configuration via os.getenv
├── core/
│   ├── models/                      # Domain dataclasses and enums
│   │   ├── order.py                 # Order, OrderItem, OrderType(4), OrderStatus(7), PaymentMethod(3)
│   │   ├── user.py                  # User, UserRole, pin_salt field
│   │   ├── product.py               # Product, Category
│   │   ├── customer.py              # Customer, CustomerAddress, Zone
│   │   ├── delivery.py              # DeliveryTrip, DriverAttendance, DriverStatus
│   │   ├── financial.py             # Shift, ShiftTransfer, CashTransaction, ShiftSummary
│   │   ├── audit.py                 # AuditEventType constants class
│   │   ├── cashier_session.py       # Station, CashierSession, LedgerEntryType(10), CashLedgerEntry
│   │   ├── driver_settlement.py     # DriverSettlement dataclass
│   │   └── order_status_history.py  # OrderStatusHistory dataclass
│   ├── policies/
│   │   └── discount.py              # compute_discount with Decimal precision
│   └── services/
│       ├── order_service.py          # State machine, create/amend/complete/cancel, ledger entries (893 lines)
│       ├── auth_service.py           # PBKDF2 auth, legacy upgrade, brute-force throttle (514 lines)
│       ├── delivery_service.py       # Driver lifecycle, trip management (604 lines)
│       ├── driver_settlement_service.py  # Settlement preview/execution, ledger entries (543 lines)
│       ├── report_service.py         # Daily/shift/monthly/yearly reports (451 lines)
│       ├── cashier_session_service.py    # Open/close/handover sessions, ledger (398 lines)
│       ├── business_day_service.py   # X/Z reports, business-day close (358 lines)
│       ├── financial_service.py      # Shift lifecycle, expenses, invoice counter (320 lines)
│       ├── customer_service.py       # Phone lookup, address/zone management (251 lines)
│       ├── product_service.py        # Category/product CRUD with search (195 lines)
│       └── audit_service.py          # Centralized audit logging and queries (168 lines)
├── data/
│   ├── database/
│   │   ├── schema.sql               # 19 tables, triggers, indexes (475 lines)
│   │   ├── connection.py            # Singleton, WAL, FK, busy_timeout (244 lines)
│   │   ├── migrations.py            # LATEST_VERSION=6, 5 migrations (364 lines)
│   │   └── seed.py                  # Default admin seeding (164 lines)
│   └── repositories/
│       ├── base_repository.py        # Abstract base with connection access
│       ├── order_repository.py       # Full CRUD, batch item loading, shift queries (509 lines)
│       ├── product_repository.py     # Product/category persistence
│       ├── customer_repository.py    # Customer/address/zone persistence
│       ├── user_repository.py        # User CRUD
│       ├── delivery_repository.py    # Trip/driver persistence
│       ├── financial_repository.py   # Shift/transaction persistence
│       ├── report_repository.py      # Report queries
│       ├── audit_repository.py       # Audit log persistence
│       ├── cash_ledger_repository.py # Append-only ledger, balance queries (204 lines)
│       ├── cashier_session_repository.py  # Session CRUD, station queries (164 lines)
│       ├── driver_settlement_repository.py  # Settlement persistence (131 lines)
│       └── order_status_history_repository.py  # Status history persistence (121 lines)
├── features/                        # Feature-level documentation only
│   ├── delivery_system/
│   ├── financial/
│   ├── order_lifecycle/
│   ├── printing_flow/
│   ├── reports/
│   └── user_permissions/
├── infrastructure/
│   ├── printing/
│   │   ├── printer_manager.py       # Central routing, 3 roles, thread-safe (223 lines)
│   │   ├── print_triggers.py        # Event-driven silent printing, 7 triggers (159 lines)
│   │   ├── escpos_printer.py        # ESC/POS hardware interface
│   │   ├── receipt_templates.py     # Arabic/English receipt formatting
│   │   └── printer_config.py       # Printer configuration loader
│   ├── web_bridge/
│   │   └── bridge.py               # POSBridge dispatch + 6 controllers (1016 lines)
│   └── sync/                       # Cloud sync — all Deferred
└── ui/
    ├── web_shell.py                 # QWebEngineView + QWebChannel (170 lines)
    ├── components/                  # Legacy PyQt6 components (retained, unused)
    ├── views/                       # Legacy PyQt6 views (retained, unused)
    ├── styles/                      # Legacy PyQt6 theme (retained, unused)
    └── windows/                     # Legacy PyQt6 windows (retained, unused)
```

### Frontend — `frontend/`

```
frontend/
├── src/
│   ├── App.tsx                      # Main shell, routing, role-based nav (224 lines)
│   ├── bridge.ts                    # POSBridgeClient, QWebChannel init, mock (1330 lines)
│   ├── main.tsx                     # React entry point
│   ├── views/
│   │   ├── POSView.tsx              # Order entry and management
│   │   ├── DeliveryView.tsx         # Delivery and driver management
│   │   ├── TrackingView.tsx         # Order tracking board
│   │   ├── ReportsView.tsx          # Report generation and display
│   │   ├── ProductsView.tsx         # Product/category management
│   │   ├── DriverSettlementView.tsx # Per-trip driver settlement (640 lines)
│   │   ├── AuditLogView.tsx         # Audit trail viewer (308 lines)
│   │   ├── UsersView.tsx            # User management (admin only)
│   │   ├── LoginView.tsx            # PIN-based login
│   │   └── SessionsView.tsx         # Cashier session management (693 lines) ⚠️ NOT MOUNTED
│   └── components/
│       ├── CustomerHistoryModal.tsx  # Customer order history
│       ├── CustomerLookup.tsx       # Phone-based customer search
│       ├── DiscountDialog.tsx       # Discount application
│       ├── Numpad.tsx               # Numeric input pad
│       ├── PaymentDialog.tsx        # Payment method selection
│       ├── PinDialog.tsx            # PIN entry dialog
│       ├── ShiftDialog.tsx          # Shift open/close (legacy, still active)
│       └── TableGrid.tsx            # Dine-in table layout
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

### Tests — `tests/`

```
tests/
├── 23 test files (6,369 total lines)
├── Coverage: order lifecycle, delivery, financial, auth, reports,
│   cashier sessions, cash ledger, business day, driver settlement,
│   audit, products, customers, permissions, and integration scenarios
└── Status: Tests exist but have NOT been executed — pass/fail unknown
```

### Documentation

```
├── Pos Project Structure + Progress.md   # This file
├── README.md                              # Project overview and setup
├── Structure.md                           # File tree reference
├── docs/
│   └── TECHNICAL_AUDIT_REPORT.md          # Technical debt and bug findings
└── PROGRESS.md files in each module       # Per-module implementation status
```

---

## Module Status Summary

| Module | Files | Status | Notes |
|---|---|---|---|
| **Core Models** | 10 model files + 1 policy | Implemented | All domain types defined |
| **Core Services** | 11 service files | Implemented | Full business logic layer |
| **Database** | schema.sql + connection + migrations + seed | Implemented | 19 tables, schema v6 |
| **Repositories** | 12 repository files | Implemented | Full persistence layer |
| **Web Bridge** | bridge.py (1016 lines) | Implemented | 6 controllers, auth guard |
| **Frontend Shell** | web_shell.py | Implemented | QWebEngineView + QWebChannel |
| **React App** | 10 views, 8 components | Partially Implemented | SessionsView not mounted |
| **Printing** | 5 files | Implemented | Hardware validation pending |
| **Config** | config.py + .env.example | Implemented | Environment-driven |
| **Legacy PyQt UI** | 26 files in ui/ | Legacy | Retained but unused |
| **Cloud Sync** | sync/ | Deferred | No implementation |
| **Tests** | 23 files | Needs Verification | Not executed |

---

## Feature Status

### Fully Implemented Features

| Feature | Backend | Frontend | Bridge | Tests |
|---|---|---|---|---|
| Order creation (dine-in, takeaway, delivery) | ✅ | ✅ | ✅ | ✅ Exist |
| 7-state order lifecycle | ✅ | ✅ | ✅ | ✅ Exist |
| Product/category management | ✅ | ✅ | ✅ | ✅ Exist |
| Customer management (phone lookup, zones) | ✅ | ✅ | ✅ | ✅ Exist |
| PIN-based authentication (PBKDF2) | ✅ | ✅ | ✅ | ✅ Exist |
| Role-based permissions (Cashier/Manager/Admin) | ✅ | ✅ | ✅ | ✅ Exist |
| Delivery driver lifecycle | ✅ | ✅ | ✅ | ✅ Exist |
| Driver settlement (per-trip and daily) | ✅ | ✅ | ✅ | ✅ Exist |
| Audit logging | ✅ | ✅ | ✅ | ✅ Exist |
| Daily/shift/monthly/yearly reports | ✅ | ✅ | ✅ | ✅ Exist |
| Cash ledger (append-only) | ✅ | — | ✅ | ✅ Exist |
| Business day X/Z reports | ✅ | — | ✅ | ✅ Exist |
| Discount policy (Decimal precision) | ✅ | ✅ | ✅ | ✅ Exist |
| Order tracking board | ✅ | ✅ | ✅ | — |
| Takeaway auto-complete (QTimer) | ✅ | — | — | — |
| Receipt printing (kitchen/cashier) | ✅ | — | ✅ | — |

### Partially Implemented / Not Integrated

| Feature | Status | Details |
|---|---|---|
| Cashier session management | **Implemented — Not Integrated** | Full backend + SessionsView.tsx (693 lines) exists but is NOT imported in App.tsx |
| Shift management (legacy) | **Legacy — Still Active** | ShiftDialog still mounted in App.tsx alongside newer cashier-session system |
| User management bridge auth | **Partially Implemented** | AuthService grants Manager MANAGE_USERS, but bridge.py restricts to admin-only |

### Deferred / Not Started

| Feature | Status |
|---|---|
| Cloud synchronization | Deferred |
| Multi-device sync | Deferred |
| Offline queue | Deferred |
| Conflict resolution | Deferred |
| File-based logging (RotatingFileHandler) | Planned |

---

## Known Issues

> [!WARNING]
> These issues were identified during the source code audit. They are documented here for tracking — none have been modified as part of this documentation update.

### Authorization Inconsistency (BUG-003 — Partially Resolved)

- `AuthService` (line 88) now includes `MANAGE_USERS` in Manager permissions.
- However, `bridge.py` (lines 266, 284, 302) still checks `self._current_user.role.value != "admin"` for user management operations.
- **Effect:** Managers cannot manage users despite having the permission in AuthService.

### FinancialController Private Attribute Access

- `financial_controller.py` accesses private attributes of injected services at lines 34, 184, 227–228.
- Accesses `self._financial_svc._financial` and `self._auth_svc._users` directly.

### Circular Dependency

- `main.py` line 144: `delivery_service._order_svc = order_service` — sets a cross-reference after construction.

### Seed Admin Legacy Hash

- `seed.py` creates the default admin with a legacy SHA-256 hash (no salt, `pin_salt=NULL`).
- The hash is auto-upgraded to PBKDF2 on first successful login.

### SessionsView Not Mounted

- `frontend/src/views/SessionsView.tsx` (693 lines) is fully implemented but not imported or mounted in `App.tsx`.
- The cashier session backend is complete and exposed through bridge.ts (v2 session API).

### window.confirm() Usage

- `App.tsx` line 56 uses `window.confirm()` for logout confirmation — may not display in QWebEngineView.

### Console-Only Logging

- `main.py` uses `logging.basicConfig()` — no file-based log rotation configured.

---

## Database Summary

| Metric | Value |
|---|---|
| Schema Version | 6 |
| Total Tables | 19 |
| Migrations Applied | 5 (v1→v2 through v5→v6) |
| Connection Mode | WAL |
| Foreign Keys | Enforced |
| Busy Timeout | 5,000 ms |

### Tables (19)

`categories`, `products`, `customers`, `customer_addresses`, `zones`, `users`, `orders`, `order_items`, `delivery_trips`, `driver_attendance`, `shifts`, `shift_transfers`, `cash_transactions`, `audit_log`, `order_status_history`, `driver_settlements`, `cashier_sessions`, `cash_ledger`, `schema_version`

### Cash Ledger Design

- Append-only with database-level `BEFORE UPDATE` and `BEFORE DELETE` triggers that raise errors.
- Integer piaster storage (no floating-point).
- Signed cash movements (positive = cash in, negative = cash out).
- Unique idempotency indexes prevent duplicate entries.
- References: orders, trips, expenses, actors, approval users.

---

## Test Summary

- **23 test files** in `tests/` directory (6,369 total lines).
- Coverage areas: order lifecycle, delivery, financial, auth, reports, cashier sessions, cash ledger, business day, driver settlement, audit, products, customers, permissions, integration.
- **Status: Not Executed** — pass/fail results are unknown. No runtime verification has been performed.

---

## Overall Project Status

### Calculated from Verified Implementation

| Category | Count | Status |
|---|---|---|
| Core domain models | 10+ files | Complete |
| Business services | 11 | Complete |
| Data repositories | 12 | Complete |
| Database tables | 19 | Complete |
| Frontend views | 10 (9 mounted) | 1 not integrated |
| Frontend components | 8 | Complete |
| Bridge controllers | 6 | Complete |
| Printing infrastructure | 5 files | Complete (hardware unverified) |
| Test files | 23 | Exist but unverified |

### Summary

The core POS functionality — order management, product/customer management, delivery, settlement, authentication, reporting, audit, and printing — is **implemented end-to-end** from React frontend through Python backend to SQLite persistence.

**Remaining engineering work:**

1. Mount `SessionsView.tsx` in `App.tsx` and retire legacy `ShiftDialog`.
2. Resolve the bridge/AuthService authorization inconsistency for Manager user-management access.
3. Refactor `FinancialController` to use public service APIs instead of private attribute access.
4. Resolve circular dependency injection between delivery and order services.
5. Add file-based logging with rotation.
6. Execute and verify the full test suite.
7. Validate printing hardware on target thermal printers.
8. Replace `window.confirm()` with an in-app dialog.
9. Cloud sync (deferred).

**The project should not be assigned a single completion percentage** without first defining and agreeing on a weighted task list. The backend and bridge layers are substantially complete; the frontend has one significant unintegrated view; hardware validation and test execution remain outstanding.
