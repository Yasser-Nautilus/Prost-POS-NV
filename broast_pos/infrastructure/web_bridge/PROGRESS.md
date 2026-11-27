# Web Bridge — Progress

> **Last Updated:** 2026-11-26
> **Source of Truth:** `bridge.py` (1,016 lines)

---

## Overview

The web bridge is the communication layer between the React frontend and the Python backend. It consists of `POSBridge`, which receives dispatched actions from the frontend via `QWebChannel` and routes them to the appropriate controller method.

---

## POSBridge (`bridge.py` — 1,016 lines)

**Status:** Implemented

### Architecture

```
React (bridge.ts)
  → QWebChannel
    → POSBridge.dispatch(action, payload)
      → Route to Controller method
        → Service call
          → Response dict
            → JSON back to React
```

### Dispatch System

- `dispatch(action: str, payload: dict)` — Central entry point for all frontend requests.
- Actions are string identifiers (e.g., `"create_order"`, `"authenticate"`, `"get_products"`).
- The dispatcher routes to one of 6 internal controllers based on action prefix/mapping.
- Returns a JSON-serializable dict with `success`, `data`, and optionally `error`.

### Authentication Guard

- Most actions require `self._current_user` to be set (authenticated).
- Unauthenticated requests to protected actions return an error response.
- Authentication actions (`authenticate`, `logout`) are exempt.

### Serialization

- Domain objects are converted to dicts for JSON transport.
- Date/datetime fields are serialized to ISO 8601 strings.
- Enum values are serialized to their string values.

---

## Controllers (6)

The bridge contains 6 internal controller classes that handle specific action domains:

### 1. OrderController (`order_controller.py` — 760 lines)

**Status:** Implemented

| Action | Description |
|---|---|
| `create_order` | Create a new order |
| `get_order` | Get order by ID |
| `get_orders` | List/filter orders |
| `update_order_status` | Change order status |
| `amend_order` | Modify order items |
| `complete_order` | Finalize and record payment |
| `cancel_order` | Cancel an order |
| `get_order_history` | Get status history for an order |

### 2. DeliveryController (`delivery_controller.py` — 484 lines)

**Status:** Implemented

| Action | Description |
|---|---|
| `clock_in_driver` | Clock in a driver |
| `clock_out_driver` | Clock out a driver |
| `get_available_drivers` | List available drivers |
| `assign_trip` | Assign an order to a driver |
| `mark_picked_up` | Record trip pickup |
| `mark_delivered` | Record trip delivery |
| `preview_settlement` | Preview driver settlement |
| `settle_trip` | Settle a single trip |
| `settle_daily` | Settle all trips for a driver |
| `get_settlement_history` | Get driver settlement history |

### 3. ReportsController (`reports_controller.py` — 473 lines)

**Status:** Implemented

| Action | Description |
|---|---|
| `get_daily_report` | Generate daily report |
| `get_shift_report` | Generate shift-based report |
| `get_monthly_report` | Generate monthly report |
| `get_yearly_report` | Generate yearly report |
| `print_report` | Print a report |

### 4. PermissionsController (`permissions_controller.py` — 437 lines)

**Status:** Implemented

| Action | Description |
|---|---|
| `authenticate` | Login with username and PIN |
| `logout` | Log out current user |
| `get_users` | List all users |
| `create_user` | Create a new user |
| `update_user` | Update user details |
| `change_pin` | Change a user's PIN |
| `deactivate_user` | Deactivate a user |
| `get_audit_log` | Query audit trail |
| `get_navigation_access` | Get role-based navigation permissions |

### 5. SessionController (`session_controller.py` — 275 lines)

**Status:** Implemented

| Action | Description |
|---|---|
| `open_session` | Open a cashier session |
| `close_session` | Close a cashier session |
| `handover_session` | Transfer session to another cashier |
| `get_active_sessions` | List active sessions |
| `generate_x_report` | Generate X-Report |
| `generate_z_report` | Generate Z-Report |
| `close_business_day` | Close the business day |

### 6. FinancialController (`financial_controller.py` — 242 lines)

**Status:** Implemented

| Action | Description |
|---|---|
| `open_shift` | Open a cashier shift |
| `close_shift` | Close a cashier shift |
| `transfer_shift` | Transfer cash between shifts |
| `add_expense` | Record an expense |
| `get_next_invoice` | Get next invoice number |

> [!WARNING]
> `FinancialController` accesses private attributes of injected services at lines 34, 184, 227–228. This should be refactored to use public service APIs.

---

## Bridge-Level Authorization Issues

> [!WARNING]
> `bridge.py` (lines 266, 284, 302) checks `self._current_user.role.value != "admin"` for user management operations, independent of `AuthService` permissions. This creates an inconsistency where Managers have `MANAGE_USERS` permission in AuthService but are blocked by the bridge.

---

## Summary

| Component | Status |
|---|---|
| POSBridge dispatch | Implemented |
| Authentication guard | Implemented |
| Serialization | Implemented |
| OrderController | Implemented (760 lines) |
| DeliveryController | Implemented (484 lines) |
| ReportsController | Implemented (473 lines) |
| PermissionsController | Implemented (437 lines) |
| SessionController | Implemented (275 lines) |
| FinancialController | Implemented (242 lines) |
| **Total bridge code** | **1,016 lines** (bridge.py) + **2,671 lines** (controllers) |

## Update 2026-11-27 (Batch 5: menu and products)

- New manager/admin actions `remove_product` (audited as `product_removed`) and `reorder_products` (`category_id`, `product_ids`). `update_product` with `is_active` is used to hide and show a product.
---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26.

- Session actions enforce ownership; cashiers cannot open or close another user's session; blind-count protection [#74].
- Close shift routes through the guarded day-close operation [#77].
- Report actions need manager role; `get_users_management` is admin-only [#80, #97].
- New or routed actions include `get_printer_status` and `get_driver_stats` [#84, #101]; other bridge changes follow the per-feature notes in the other PROGRESS files.
- CI test scans frontend `call(...)` actions and dispatches each through the real bridge to catch "unknown action" errors [#102].
- `dispatch_trip` returns `print_failed` invoice numbers when slips fail [#107].
