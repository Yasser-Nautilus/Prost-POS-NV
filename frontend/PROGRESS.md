# Frontend — Progress

> **Last Updated:** 2026-11-26
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

## Views (10 total, all mounted since #59/#60)

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
| `SessionsView` | `SessionsView.tsx` | 693 | **Implemented, mounted (#59, #60)** | Cashier session management |

> [!NOTE]
> `SessionsView.tsx` (693 lines) is fully implemented and has corresponding bridge API endpoints (v2 session API in `bridge.ts`), and it is now imported and mounted in `App.tsx` (PRs #59, #60).

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
| Views | 10 (all mounted) | none |
| Components | 8 | All implemented |
| Bridge client | 1 (1,330 lines) | Implemented with mock |
| Build config | 3 files | Implemented |

| Known Issue | Details |
|---|---|
| SessionsView not mounted | Fixed in #59/#60: now mounted in App.tsx |
| ShiftDialog still active | Legacy component coexists with new session system |
| `window.confirm()` | Used for logout — may not work in QWebEngineView |

## Update 2026-11-27 (Batch 5: menu and products)

- `ProductsView`: products can be dragged to a new position inside a category (saved with `reorder_products`). Each card shows Edit, Hide/Show and Remove side by side. Hide keeps the product listed (dimmed, marked "مخفي") with a Show button; Remove deletes it after a confirm.
- The product list now loads `get_all_products` so hidden products stay visible on this screen; the cashier screen still gets active products only.
- `bridge.ts` mock: added `remove_product`, `reorder_products`, `get_all_products`, and `update_product` only changes fields that are sent.
---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26. Details come from the merged PR descriptions (PR numbers in brackets).

### Shell and navigation
- `SessionsView` is now mounted in `App.tsx` with a navigation tab, role-based visibility and data refresh [#59, #60]. The earlier "Implemented, not integrated" warning no longer applies.
- `window.confirm()` is replaced by the React `ConfirmDialog` in the POS views [#60].
- Top bar is bigger (icons 24px, bar 80px, touch targets at least 48px); navbar tabs slide their name in on hover; account and shift controls stay visible at supported desktop widths [#99, #105, #95].
- Dark/light theme toggle (`ThemeToggle.tsx`, `theme.ts`): sun/moon button in the header and on the login screen, dark by default, choice saved on the device [#108].
- All modals (22 overlays) close when the dark area outside is clicked, using mousedown on the overlay itself [#109].
- `bridge.ts` only falls back to the in-memory mock backend when `VITE_ALLOW_MOCK_BRIDGE=true` is set at build time [#85].
- Favicon is the Nautix hex N [#110].

### Branding and styling
- Rebrand to Prostsh: brand accent changed from gold to red (`brand-gold` renamed `brand-red`), near-black surfaces, new login art and logo [#79]. Light login art and self-hosted Cairo font (`frontend/src/fonts/`) added [#110].
- Login: logo sits in the circle at the top of the PIN card; duplicate white PIN dots removed (keyboard typing still works) [#99, #108, #110].

### Views and components
- `POSView`: cashier shortcuts (`/` or `F2` jumps to search, `Enter` adds the first match, `Esc` clears, `F8` opens discount) [#99]; per-item comment and mixed payment/bill split in `PaymentDialog` [#100]; discount re-validated after removing items [#98].
- `CustomerLookup` / `CustomerHistoryModal`: lookup by a full phone number shows addresses and the last 3 orders; edit name and phone [#95, #100].
- `phone.ts`: shared Egyptian mobile helper (`+20`, spaces and dashes normalise to `01XXXXXXXXX`), phone fields stop at 11 digits [#95, #110].
- `ZonesPanel`: delivery zones management for manager and above, audit-logged, unique names [#95, #97].
- `DriverStats`, `PeriodReports`: driver statistics and monthly/yearly reports (manager and above) [#95, #100].
- `SettlementHistory`, `DriverSettlementView`: settlement history, daily settlement completed state, invoice number first in trip previews, optional notes field removed from single-trip settlement [#95, #96, #104, #105].
- `ShiftDialog`: Escape closes it, expenses and pending shown for cashiers; `SessionsView` day-close Z-report no longer disappears after closing [#94, #97].
- `UsersView`: delete (only users without history; users with records must be deactivated) and reactivate buttons, no second system admin in the role dropdown, the driver form hides the PIN (an internal 8-digit one is generated) and cashier slot, and the PIN field notes that new PINs need at least four English digits [#94, #108, #110].
- `ProductsView`: price validation (0 to 50,000 EGP), duplicate names blocked, category delete [#93, #95, #108].
- `TrackingView`: copy buttons for receipts, date picker in the archive, "sent to printer" notice clears after 5 seconds [#106, #109].
- `ToastHost`, `ConfirmDialog`, `ManagerApprovalDialog`: new shared components [#60, #94, #108].

## Update 2026-11-27 (Batch 6: shifts, keyboard, live orders)

- `TrackingView`: subscribes to `ordersChanged` and refreshes at once (the 30s poll stays as a safety net).
- `ConfirmDialog`: one decision per open — Enter confirms, Escape cancels, key repeat and the focused button's own Enter are ignored so an action never runs twice.
- `ShiftDialog`: shift-change label reworded; when no shift is open the dialog now tells a closed day apart from a missing one (closed day → "a manager must open a new day", instead of offering a drawer that cannot open).
- `SessionsView`: after the day is closed the screen keeps showing that day's sessions with a banner instead of going blank.
- `CustomerLookup`: the register and address forms take the cursor on open, so Enter saves without the mouse.
- `POSView`: an item note saves when the field loses focus and is cleared when the order changes, so it cannot leak into the next order.
- `DeliveryView`: a zone repeated inside the street line is shown once.
- `bridge.ts`: `ordersChanged` listener (plus a mock-mode emit) and `sessionLastDay()`.

---
