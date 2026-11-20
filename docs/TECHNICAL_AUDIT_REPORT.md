# Technical Audit Report — Prost POS

> **Last Updated:** 2026-11-20
> **Schema Version at Time of Audit:** 6
> **Branch:** `dev`
> **Audit Method:** Source code inspection only — no runtime execution or test runs

---

## Executive Summary

This report documents technical debt, bugs, and security findings identified through a comprehensive source code audit of the Prost POS repository. All findings are based on static code analysis; no runtime testing was performed.

---

## Bug Findings

### BUG-001 — Corrupted Historical Orders

**Status:** Identified (from previous audit)

- The previous audit identified 35 orders with potentially corrupted data (incorrect totals or missing items) created before the order amendment and discount policy were stabilized.
- **No data-repair migration has been applied.** Any future repair must use migration version **7 or higher** (v6 is already used for `pin_salt`).
- Impact is limited to historical reporting accuracy for those specific orders.

### BUG-003 — Manager Cannot Manage Users (Authorization Inconsistency)

**Status:** Partially Resolved

**Previous finding:** Managers could not access user management functionality.

**Current state:**
- ✅ `AuthService` (line 88) now includes `MANAGE_USERS` in Manager permissions.
- ❌ `bridge.py` (lines 266, 284, 302) still checks `self._current_user.role.value != "admin"` for user management operations (create, update, deactivate).
- ❌ `App.tsx` renders the Users tab only for Admin role.

**Effect:** The AuthService-level fix is in place, but the bridge-level and frontend-level restrictions still prevent Managers from managing users. The inconsistency is between the permission definition and the enforcement points.

**Resolution options:**
1. Remove `MANAGE_USERS` from Manager permissions in `AuthService` (align definition with enforcement).
2. Update bridge.py and App.tsx to allow Manager access (align enforcement with definition).

### BUG-005 — Takeaway Auto-Complete Not Wired

**Status:** Resolved ✅

- `main.py` (lines 215–217) now creates a `QTimer` that calls `order_service.auto_complete_expired_takeaways()` every 60 seconds.
- The timer is started before `app.exec()`.

---

## Security Findings

### SEC-001 — Hard-Coded DEBUG Flag

**Status:** Resolved ✅

- `config.py` now uses `os.getenv()` for all configuration including `DEBUG` and `APP_ENV`.
- `.env.example` provides a template without secrets.

### SEC-002 — PIN Pepper Externalization

**Status:** Implemented ✅

- `BROAST_PIN_PEPPER` is loaded from the environment via `os.getenv()`.
- `.env.example` documents the variable without exposing a value.
- `.env` is in `.gitignore`.

### SEC-003 — Seed Admin Legacy Hash

**Status:** Known — By Design

- The default admin user is seeded with a legacy SHA-256 hash (no salt, `pin_salt=NULL`).
- On first successful login, `AuthService` auto-upgrades the hash to PBKDF2-HMAC-SHA256 with a random salt and the application pepper.
- **Recommendation:** Change the default admin PIN immediately after first deployment.

### SEC-004 — Brute-Force Throttling

**Status:** Implemented ✅

- `AuthService` tracks failed login attempts per user.
- Configurable lockout after repeated failures.

---

## Code Quality Findings

### CQ-001 — FinancialController Private Attribute Access

**Status:** Open

- `financial_controller.py` accesses private attributes of injected services:
  - Line 34: Accesses `self._financial_svc._financial`
  - Line 184: Accesses `self._financial_svc._financial`
  - Lines 227–228: Accesses `self._auth_svc._users`
- **Impact:** Breaks encapsulation, couples controller to service internals.
- **Recommendation:** Expose the needed data through public service methods.

### CQ-002 — Circular Dependency (Delivery ↔ Order)

**Status:** Open

- `main.py` line 144: `delivery_service._order_svc = order_service`
- `DeliveryService` needs `OrderService` for status transitions, and both are instantiated in `main.py`.
- The dependency is resolved by post-construction injection of a private attribute.
- **Impact:** Works correctly but violates clean dependency injection patterns.
- **Recommendation:** Consider a mediator pattern or event-based decoupling.

### CQ-003 — `window.confirm()` in QWebEngineView

**Status:** Open

- `App.tsx` line 56 uses `window.confirm()` for logout confirmation.
- `window.confirm()` may not display a dialog in QWebEngineView (depends on `QWebEnginePage` configuration).
- **Recommendation:** Replace with an in-app confirmation dialog component.

### CQ-004 — Console-Only Logging

**Status:** Open

- `main.py` uses `logging.basicConfig()` — console output only.
- No `RotatingFileHandler` or file-based log persistence.
- **Impact:** Log history is lost when the application restarts.
- **Recommendation:** Add a `RotatingFileHandler` for production deployments.

### CQ-005 — SessionsView Not Integrated

**Status:** Open

- `frontend/src/views/SessionsView.tsx` (693 lines) is fully implemented.
- `frontend/src/bridge.ts` includes v2 session API endpoints.
- `SessionController` (275 lines) handles all session bridge actions.
- **But** `SessionsView` is not imported or mounted in `App.tsx`.
- **Impact:** The cashier session frontend is unreachable at runtime despite being fully implemented.
- **Recommendation:** Import and mount `SessionsView` in `App.tsx`, add a navigation tab for Manager+ roles, and retire the legacy `ShiftDialog`.

### CQ-006 — Dual Financial Systems

**Status:** Open

- The legacy shift system (`FinancialService` + `ShiftDialog`) and the new cashier session system (`CashierSessionService` + `SessionsView`) coexist.
- Both systems are partially active: `ShiftDialog` is mounted; `SessionsView` is not.
- **Recommendation:** Complete the transition to cashier sessions and retire the legacy shift system, or clearly document both as intentionally parallel systems.

---

## Schema Status

| Item | Value |
|---|---|
| Current schema version | 6 |
| Total tables | 19 |
| Applied migrations | 5 (v1→v2 through v5→v6) |
| Next available migration version | **7** |

> [!CAUTION]
> Migration version 6 is already used (`add_pin_salt`). Any future schema changes — including data-repair migrations for BUG-001 — must use version 7 or higher.

---

## Summary of Findings

| ID | Category | Finding | Status |
|---|---|---|---|
| BUG-001 | Bug | Corrupted historical orders | Identified — no repair applied |
| BUG-003 | Bug | Manager user-management auth inconsistency | Partially Resolved |
| BUG-005 | Bug | Takeaway auto-complete not wired | **Resolved** ✅ |
| SEC-001 | Security | Hard-coded DEBUG | **Resolved** ✅ |
| SEC-002 | Security | PIN pepper externalization | **Implemented** ✅ |
| SEC-003 | Security | Seed admin legacy hash | Known — By Design |
| SEC-004 | Security | Brute-force throttling | **Implemented** ✅ |
| CQ-001 | Quality | FinancialController private attr access | Open |
| CQ-002 | Quality | Circular dependency (delivery ↔ order) | Open |
| CQ-003 | Quality | `window.confirm()` in QWebEngineView | Open |
| CQ-004 | Quality | Console-only logging | Open |
| CQ-005 | Quality | SessionsView not integrated | Open |
| CQ-006 | Quality | Dual financial systems | Open |

---

## Resolved Since Previous Audit

1. **BUG-005:** Takeaway auto-complete is now wired via QTimer in `main.py`.
2. **SEC-001:** DEBUG flag is now environment-driven via `os.getenv()`.
3. **SEC-002:** PIN pepper is loaded from environment variables.
4. **SEC-004:** Brute-force throttling is implemented in AuthService.
5. **BUG-003 (partial):** Manager `MANAGE_USERS` permission added to AuthService, but bridge/frontend enforcement still restricts to Admin.
