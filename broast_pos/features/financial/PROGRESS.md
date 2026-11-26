# Financial System — Progress

> **Last Updated:** 2026-11-26
> **Source of Truth:** `financial_service.py`, `cashier_session_service.py`, `business_day_service.py`, `cash_ledger_repository.py`, `cashier_session.py`, `financial.py`

---

## Overview

The financial system has two layers:

1. **Legacy Shift System** — `FinancialService` + `ShiftDialog` (still active in the frontend).
2. **New Cashier Session System** — `CashierSessionService` + `BusinessDayService` + Cash Ledger (backend complete, frontend view exists but is not mounted).

Both systems coexist in the current codebase.

---

## Legacy Shift System

### FinancialService (`financial_service.py` — 320 lines)

**Status:** Implemented (Legacy — Still Active)

**Key responsibilities:**
- Open/close shifts with opening and closing amounts.
- 4 close guards (validates shift state before closing).
- Shift transfers between cashiers.
- Expense recording against active shifts.
- Sequential invoice numbering.

**Frontend integration:**
- `ShiftDialog` component in `App.tsx` — still mounted and active.
- Users can open/close shifts through this dialog.

> [!NOTE]
> The legacy shift system remains active in the frontend via `ShiftDialog`. The newer cashier session system is intended to replace it, but the transition is not yet complete.

---

## Cashier Session System

### CashierSessionService (`cashier_session_service.py` — 398 lines)

**Status:** Implemented

Station-based cashier sessions with full cash ledger integration.

#### Session Lifecycle

```
Open Session → Active Operations → Close Session
                    ↓
              Handover Session → New Session (linked)
```

#### Stations

| Station | Handles |
|---|---|
| `ALL` | All order types |
| `COUNTER` | Dine-in, takeaway, pickup |
| `DELIVERY` | Delivery orders only |

#### Open Session
- Assigns cashier to a station.
- Records opening float amount.
- Creates `FLOAT` ledger entry.
- **Station conflict guard:** Prevents opening a session on a station that already has an active session.

#### Close Session
- Records cash count (`closing_float`).
- Calculates expected cash from ledger entries.
- Determines variance (`closing_float - expected_cash`).
- Manager approval required for significant variance.
- Logs `SESSION_CLOSED` audit event.

#### Session Handover
- Transfers a session from one cashier to another.
- Links sessions via `handover_to_session_id`.
- Logs `SESSION_HANDOVER` audit event.

#### Active Session Queries
- Get active sessions by station or user.
- List all active sessions.

---

## Cash Ledger

### Design

**Status:** Implemented

The cash ledger is the central financial record for all cash movements.

| Property | Detail |
|---|---|
| Storage | Append-only (INSERT only) |
| Currency | Integer piasters (no floating-point) |
| Sign convention | Positive = cash in, Negative = cash out |
| Protection | Database triggers block UPDATE and DELETE |
| Idempotency | Unique indexes prevent duplicate entries |

### Entry Types (10)

| Type | Direction | Source |
|---|---|---|
| `SALE_CASH` | + | Order completed with cash payment |
| `SALE_CARD` | + | Order completed with card payment |
| `SALE_MOBILE` | + | Order completed with mobile payment |
| `REVERSAL` | − | Completed order cancelled |
| `EXPENSE` | − | Cash expense recorded |
| `CASH_IN` | + | Manual cash deposit |
| `CASH_OUT` | − | Manual cash withdrawal |
| `FLOAT` | + | Opening float for session |
| `DRIVER_REMITTANCE` | + | Cash returned by driver |
| `DRIVER_FEE_PAYOUT` | − | Delivery fee paid to driver |

### Integration Points

Ledger entries are created by:
- `OrderService` — on order completion (`SALE_*`) and cancellation of paid orders (`REVERSAL`).
- `CashierSessionService` — on session open (`FLOAT`).
- `DriverSettlementService` — on trip settlement (`DRIVER_REMITTANCE`).
- `BusinessDayService` — on business-day close (`DRIVER_FEE_PAYOUT`).

---

## Business Day Accounting

### BusinessDayService (`business_day_service.py` — 358 lines)

**Status:** Implemented

#### X-Report (Interim)
- Read-only snapshot of current business day activity.
- Built from cash ledger data.
- Includes per-session summaries.
- Does not close or modify anything.

#### Z-Report (Final)
- Final end-of-day report.
- Freezes the business day.
- Includes all session summaries and ledger totals.

#### Close Business Day
1. **Open-session guard:** Verifies all cashier sessions are closed.
2. Generates batch `DRIVER_FEE_PAYOUT` ledger entries for all delivery fees owed.
3. Produces the Z-Report.
4. Records the business-day close event.

---

## Frontend Integration

| Component | Status | Notes |
|---|---|---|
| `ShiftDialog` | Implemented (Legacy) | Mounted in `App.tsx`, uses `FinancialService` |
| `SessionsView.tsx` | **Implemented — Not Integrated** | 693 lines, full session management UI, but NOT imported/mounted in `App.tsx` |

> [!WARNING]
> `SessionsView.tsx` exists and is fully implemented (693 lines) with the bridge API (v2 session endpoints in `bridge.ts`), but it is not imported or mounted in `App.tsx`. The cashier session backend is complete and exposed through the bridge, but the frontend view is unreachable at runtime.

---

## Bridge Integration

### SessionController (`session_controller.py` — 275 lines)

**Status:** Implemented

Handles cashier session bridge actions:
- Open/close/handover sessions.
- Active session queries.
- X-Report and Z-Report generation.
- Business-day close.

### FinancialController (`financial_controller.py` — 242 lines)

**Status:** Implemented

Handles legacy financial bridge actions:
- Shift open/close/transfer.
- Expense recording.
- Invoice numbering.

> [!WARNING]
> `FinancialController` accesses private attributes of injected services at lines 34, 184, 227–228 (e.g., `self._financial_svc._financial` and `self._auth_svc._users`). This breaks encapsulation and should be refactored to use public service APIs.

---

## Summary

| Feature | Status | Notes |
|---|---|---|
| Legacy shifts (open/close/transfer) | Implemented | Still active via ShiftDialog |
| Expense recording | Implemented | |
| Invoice numbering | Implemented | |
| Cashier sessions (open/close/handover) | Implemented | Backend complete |
| Station-based sessions | Implemented | ALL / COUNTER / DELIVERY |
| Station conflict guard | Implemented | |
| Cash ledger (append-only) | Implemented | 10 entry types, integer piasters |
| Ledger UPDATE/DELETE protection | Implemented | Database triggers |
| Ledger idempotency | Implemented | Unique indexes |
| X-Report generation | Implemented | Read-only interim |
| Z-Report generation | Implemented | Final end-of-day |
| Business-day close | Implemented | With open-session guard |
| Driver fee payout entries | Implemented | Batch on business-day close |
| SessionsView frontend | **Implemented — Not Integrated** | Not mounted in App.tsx |
| ShiftDialog frontend | Implemented (Legacy) | Still mounted |
| Session bridge controller | Implemented | |
| Financial bridge controller | Implemented | Has private attribute access issue |

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26.

- `session_controller.py`: public `get_all_sessions()` uses the service (no private repo access); open lets only managers open for another user, cashiers always open their own; close is limited to the caller's own session [#60, #74, #94].
- Handover: `HandoverDialog` flow (select target, cash count, variance, manager PIN, cash drop, incoming session) is atomic and validates `0 <= cash_drop <= counted` [#59, #61, #86].
- `financial_controller.py`: `get_users_for_transfer()` returns cashier-slot users only; same-user transfer is rejected; open sessions show live expected cash; shifts show the cashier name [#68, #95, #97, #110].
- Cashier blind count and close; large variance needs manager PIN and reason [#94].
