# Point 9: durable parking

Parking keeps cashier work separate from confirmed sales. Existing login-scoped
controllers define the visibility boundary: recovery is by authenticated user ID,
not cashier slot, client payload, or a shared list. A different login does not
inherit another user's draft. This is not a new shared handover workflow.

Schema v7 adds `parked_order_drafts`. Startup upgrades existing databases without
changing historical sales. The payload is a lossless server-side Order snapshot,
not the receipt/UI projection. Product IDs, backend-resolved prices, notes,
customer fields, payment choice, authorized discounts and table survive recovery.
No invoice, sale row, cash movement or kitchen print is created by parking.

Resuming hides the draft from the parked list for that session but retains its
recovery row. Subsequent edits update that row. Re-parking updates the same row.
After logout or process restart, unfinished recovered work appears in the parked
list again. Confirming consumes the row in the same transaction that saves the
sale. Failure preserves both the row and the retryable in-memory draft. A second
controller cannot confirm an already consumed row.

A parked saved order remains an amendment, never a new sale. Its original saved
snapshot is compared with the live order before recovery and amendment save.
Intervening payment, cancellation or edits cause an explicit conflict instead of
overwriting live state. The recovery row is retained, and the message directs the
cashier to review the current order from the order list. Item removals still need
the existing manager PIN. This change does not add a discard/conflict-resolution
screen or change table allocation policy.

Regression coverage: real POSBridge logout/login, SQLite file reopen, per-user
isolation (including matching slots and forged payload IDs), lossless fields,
park/swap/re-park, failed writes and confirm rollback, duplicate-controller
confirmation, amendment differences, removal authorization, stale paid state, and
idempotent v6 upgrade. The rendered Qt/React/QWebChannel test parks through the
visible UI, logs out/in, restores from the modal, and confirms/pays once for both
admin and cashier flows.
