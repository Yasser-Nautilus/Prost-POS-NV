# Point 10: confirmed dine-in table occupancy

The existing contract is one open dine-in order per table. The table picker
opens that order to append items; payment closes it, cancellation frees it, and
moving it requires a free target table. The existing repository treats every
status except completed/cancelled as active, irrespective of shift or payment
flag. This fix uses exactly that boundary, without adding split billing or
claiming that an unsaved/parked draft is already a confirmed order.

Schema v8 adds SQLite INSERT and UPDATE triggers. They reject entry into a table
already held by an active dine-in order, including simultaneous confirmations,
repository/direct SQL writes, table moves, type conversion and reopening a closed
order. The repository translates the constraint to a cashier-facing message to
open the existing order. Failed confirmation rolls back invoice allocation and
keeps the current draft available. A failed recovered draft also keeps its
recovery row.

A unique index would fail on databases containing old duplicates. Instead, the
triggers prevent new occupancy conflicts without rewriting those rows. Ordinary
updates at an already-held table remain allowed, so old duplicate orders can
still be amended, paid, cancelled or moved away. A table lookup with multiple
open orders now reports the conflict and directs the cashier to the order list,
rather than silently selecting the newest one. No old order is deleted, merged,
renumbered or automatically closed.

Tests cover the public bridge, invoice rollback and retry, parked draft conflict,
payment/cancellation/move release, appending without a second invoice, raw SQL
and repository bypasses, status/type changes, paid-but-active semantics, legacy
duplicates and idempotent migration. Concurrent tests use both the real shared
service connection and two independent SQLite connections racing to create or
move an order. The rendered UI test opens the visibly occupied table and saves
an addition into the same invoice. This does not change table allocation for
unconfirmed drafts or introduce a new historical-cleanup policy.
