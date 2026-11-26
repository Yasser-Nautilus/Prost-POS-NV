# Order Lifecycle — Progress

> **Last Updated:** 2026-11-26
> **Source of Truth:** `order_service.py`, `order.py`, `order_controller.py`, `bridge.py`

---

## Overview

The order lifecycle is managed by a **centralized 7-state machine** in `OrderService`, with type-aware transitions, cash ledger integration, discount policy, status history tracking, and audit logging.

---

## Order State Machine

### States (7)

| Status | Description |
|---|---|
| `NEW` | Order created, not yet sent to kitchen |
| `PREPARING` | Sent to kitchen, being prepared |
| `READY` | Prepared, awaiting pickup or delivery dispatch |
| `OUT_FOR_DELIVERY` | Assigned to driver, in transit (delivery only) |
| `DELIVERED` | Driver confirmed delivery (delivery only) |
| `COMPLETED` | Order finalized and paid |
| `CANCELLED` | Order cancelled |

### Type-Aware Transitions

```
Dine-in / Takeaway / Pickup:
  NEW → PREPARING → READY → COMPLETED

Delivery:
  NEW → PREPARING → READY → OUT_FOR_DELIVERY → DELIVERED → COMPLETED

All types:
  Any non-terminal state → CANCELLED
```

- Terminal states: `COMPLETED`, `CANCELLED` — no further transitions allowed.
- The state machine is enforced programmatically in `OrderService.update_order_status()`.
- Invalid transitions raise exceptions.

---

## Order Types (4)

| Type | Description |
|---|---|
| `DINE_IN` | Eat-in with optional table number |
| `TAKEAWAY` | Pickup by customer |
| `DELIVERY` | Delivered to customer address |
| `PICKUP` | Pre-ordered for customer pickup |

---

## Payment Methods (3)

| Method | Description |
|---|---|
| `CASH` | Cash payment |
| `CARD` | Card payment |
| `MOBILE` | Mobile payment |

---

## Key Behaviors

### Order Creation
- **Status:** Implemented
- Validates order type, items, and customer (for delivery).
- Applies discount via `compute_discount` policy (Decimal precision).
- Calculates subtotal, discount, tax, and total.
- Records `created_by` user.
- Logs `ORDER_CREATED` audit event.

### Order Amendment
- **Status:** Implemented
- Modifies items on non-terminal orders.
- Recalculates totals with discount policy.
- Logs `ORDER_AMENDED` audit event with before/after snapshots.

### Order Completion
- **Status:** Implemented
- Records payment method.
- Sets `is_paid = True`.
- **Cash ledger entry:** Creates `SALE_CASH`, `SALE_CARD`, or `SALE_MOBILE` entry in the cash ledger based on payment method.
- Logs `ORDER_COMPLETED` audit event.

### Order Cancellation
- **Status:** Implemented
- Accepts cancellation reason.
- **Reversal ledger entry:** If the order was previously completed and had a ledger entry, creates a `REVERSAL` entry with negative amount.
- Logs `ORDER_CANCELLED` audit event.

### Status Transitions
- **Status:** Implemented
- Each transition is validated against the type-aware state machine.
- Creates an `OrderStatusHistory` record for every transition.
- Logs `ORDER_STATUS_CHANGED` audit event.

### Takeaway Auto-Complete
- **Status:** Implemented
- `auto_complete_expired_takeaways()` is called by a 60-second `QTimer` in `main.py` (lines 215–217).
- Automatically completes takeaway orders that have been in `READY` status beyond a configured timeout.

### Unpaid Completion Policy
- **Status:** Implemented
- Orders can be moved to `COMPLETED` without the `is_paid` flag being set first.
- Payment recording happens as part of the completion call.

---

## Integration Points

| Integration | Status | Details |
|---|---|---|
| Cash Ledger | Implemented | SALE and REVERSAL entries on complete/cancel |
| Order Status History | Implemented | Immutable transition log |
| Audit Logging | Implemented | All lifecycle events logged |
| Discount Policy | Implemented | Decimal-precision `compute_discount` |
| Delivery System | Implemented | Delivery transitions routed through OrderService |
| Print Triggers | Implemented | Kitchen/receipt printing on status changes |
| Frontend (POSView) | Implemented | Full order management UI |
| Frontend (TrackingView) | Implemented | Order tracking board |
| Bridge | Implemented | `OrderController` dispatches all order actions |

---

## Frontend Integration

### POSView
- Order creation with product selection, quantity, notes.
- Customer lookup for delivery orders.
- Discount application via `DiscountDialog`.
- Payment via `PaymentDialog`.
- Table selection for dine-in via `TableGrid`.

### TrackingView
- Real-time order status board.
- Status transition buttons.
- Order detail display.

---

## Summary

| Component | Status |
|---|---|
| 7-state machine | Implemented |
| Type-aware transitions | Implemented |
| Order creation | Implemented |
| Order amendment | Implemented |
| Order completion + ledger | Implemented |
| Order cancellation + reversal | Implemented |
| Status history recording | Implemented |
| Takeaway auto-complete | Implemented |
| Discount policy | Implemented |
| Audit logging | Implemented |
| Print triggers | Implemented |
| Frontend (POSView) | Implemented |
| Frontend (TrackingView) | Implemented |
| Bridge integration | Implemented |

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26.

- `amendment_tracker.py`: lines are identified by `(product_id, notes)`; removals are consumed once across identical lines; quantity deltas fixed [#71, #94].
- `order_controller.py`: `save_amendment()` reloads the persisted order; `print_trip_slips(order_ids)` prints receipts for a trip's orders; every valid print attempt is audited; cashier amendment and cancel need manager PIN and reason [#71, #94, #107].
- `payment_coordinator.py`: paid-order guard, mixed payment and equal split [#72, #100].
- Receipt reprint from tracking, copies marked "COPY" [#106].
