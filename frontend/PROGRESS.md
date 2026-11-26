# Frontend — Progress

> **Last Updated:** 2026-11-20
> **Source of Truth:** `frontend/src/App.tsx`, `frontend/src/bridge.ts`, and all view/component files

---

## Overview

The frontend is a **React 18 + TypeScript** single-page application built with **Vite** and styled with **Tailwind CSS**. It is rendered inside a PySide6 `QWebEngineView` and communicates with the Python backend via `QWebChannel` through the `POSBridgeClient` in `bridge.ts`.

---

## Build Stack

| Tool | Purpose |
|---|---|
| React 18 | UI framework |
| TypeScript | Type-safe JavaScript |
| Vite | Build tool and dev server |
| Tailwind CSS | Utility-first CSS |

---

## Application Shell (`App.tsx` — 224 lines)

**Status:** Implemented

### Authentication
- Unauthenticated users see `LoginView`.
- Authenticated users see the main navigation and active view.
- Logout uses `window.confirm()` (line 56) — may not display in QWebEngineView.

### Navigation (Role-Based)

| Tab | Visible To | View Component |
|---|---|---|
| POS | All | `POSView` |
| Delivery | All | `DeliveryView` |
| Tracking | All | `TrackingView` |
| Settlement | Manager+ | `DriverSettlementView` |
| Reports | Manager+ | `ReportsView` |
| Products | Manager+ | `ProductsView` |
| Audit | Manager+ | `AuditLogView` |
| Users | Admin | `UsersView` |

### Active Dialogs
- `ShiftDialog` — Legacy shift management, still mounted and active.

---

## Views (10 total — 9 mounted)

| View | File | Lines | Status | Description |
|---|---|---|---|---|
| `POSView` | `POSView.tsx` | — | Implemented | Order entry, product selection, cart, payment |
| `DeliveryView` | `DeliveryView.tsx` | — | Implemented | Driver management, trip tracking |
| `TrackingView` | `TrackingView.tsx` | — | Implemented | Order status tracking board |
| `ReportsView` | `ReportsView.tsx` | — | Implemented | Report generation and display |
| `ProductsView` | `ProductsView.tsx` | — | Implemented | Product/category CRUD |
| `DriverSettlementView` | `DriverSettlementView.tsx` | 640 | Implemented | Per-trip driver settlement |
| `AuditLogView` | `AuditLogView.tsx` | 308 | Implemented | Audit trail viewer with filters |
| `UsersView` | `UsersView.tsx` | — | Implemented | User management (admin only) |
| `LoginView` | `LoginView.tsx` | — | Implemented | PIN-based login |
| `SessionsView` | `SessionsView.tsx` | 693 | **Implemented — Not Integrated** | Cashier session management |

> [!WARNING]
> `SessionsView.tsx` (693 lines) is fully implemented and has corresponding bridge API endpoints (v2 session API in `bridge.ts`), but it is **not imported or mounted** in `App.tsx`. It is unreachable at runtime.

---

## Components (8)

| Component | File | Description |
|---|---|---|
| `CustomerHistoryModal` | `CustomerHistoryModal.tsx` | Customer order history popup |
| `CustomerLookup` | `CustomerLookup.tsx` | Phone-based customer search |
| `DiscountDialog` | `DiscountDialog.tsx` | Discount percentage/amount entry |
| `Numpad` | `Numpad.tsx` | Numeric input pad |
| `PaymentDialog` | `PaymentDialog.tsx` | Payment method selection and amount |
| `PinDialog` | `PinDialog.tsx` | PIN entry for auth and verification |
| `ShiftDialog` | `ShiftDialog.tsx` | Legacy shift open/close (still active) |
| `TableGrid` | `TableGrid.tsx` | Dine-in table layout selection |

---

## Bridge Communication (`bridge.ts` — 1,330 lines)

**Status:** Implemented

### POSBridgeClient

The `POSBridgeClient` class provides the TypeScript interface to the Python backend:

- **QWebChannel initialization:** Connects to `POSBridge` via `QWebChannel` on page load.
- **Action dispatch:** `dispatch(action, payload)` sends requests to `POSBridge.dispatch()` on the Python side.
- **Response handling:** Receives JSON responses and resolves/rejects promises.
- **Mock dispatcher:** When running outside QWebEngineView (e.g., in a browser for development), a mock dispatcher simulates backend responses.

### API Coverage

The bridge exposes actions for all implemented features:
- Order CRUD and lifecycle.
- Product and category management.
- Customer management.
- Delivery and driver operations.
- Driver settlement.
- Authentication and user management.
- Financial/shift operations.
- Report generation.
- Audit log queries.
- **v2 session API** — Cashier session endpoints (open, close, handover, X/Z reports, business-day close).

---

## Build Configuration

### `vite.config.ts`
- Configures React plugin.
- Build output for embedding in QWebEngineView.

### `tailwind.config.js`
- Content paths for TSX files.
- Custom theme extensions.

### `tsconfig.json`
- Strict TypeScript configuration.
- Path aliases.

---

## Summary

| Category | Count | Status |
|---|---|---|
| Views | 10 (9 mounted) | 1 not integrated (SessionsView) |
| Components | 8 | All implemented |
| Bridge client | 1 (1,330 lines) | Implemented with mock |
| Build config | 3 files | Implemented |

| Known Issue | Details |
|---|---|
| SessionsView not mounted | 693-line view exists but is not in App.tsx |
| ShiftDialog still active | Legacy component coexists with new session system |
| `window.confirm()` | Used for logout — may not work in QWebEngineView |

## Update 2026-11-27 (Batch 5: menu and products)

- `ProductsView`: products can be dragged to a new position inside a category (saved with `reorder_products`). Each card shows Edit, Hide/Show and Remove side by side. Hide keeps the product listed (dimmed, marked "مخفي") with a Show button; Remove deletes it after a confirm.
- The product list now loads `get_all_products` so hidden products stay visible on this screen; the cashier screen still gets active products only.
- `bridge.ts` mock: added `remove_product`, `reorder_products`, `get_all_products`, and `update_product` only changes fields that are sent.
