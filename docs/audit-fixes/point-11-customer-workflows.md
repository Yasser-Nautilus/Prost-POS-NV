# Point 11: address removal and customer history

`CustomerService.delete_address` called `CustomerRepository.delete`, whose
intentional no-op protects customer history. It now calls a separate address
method. Schema v9 adds an active flag, defaulting existing addresses to active.
Removal atomically deactivates one address. Missing/already inactive addresses
raise an error, rather than reporting success. Customer records, other addresses,
zones, historical orders and their stored street/zone/fee snapshots stay intact.
All address selection lookups exclude inactive rows, including the authoritative
lookup used for delivery prices. A previously copied order snapshot stays valid;
new selection by a removed address ID is rejected.

The authenticated bridge exposes `delete_customer_address` with both customer ID
and address ID. A mismatch cannot remove another customer's address. Like the
existing lookup/create/address workflow, this is available to authenticated
cashiers, not a new manager-only policy. The service's existing address-ID-only
API remains usable internally. Current schema/model has no default-address field
or cashier ownership of customers; no default reassignment or per-cashier access
rule was invented. Old model progress notes mentioning a default field do not
match the implemented schema.

The history modal's phone path now calls the supported exact validated
`find_customer_by_phone` action. ID-based lookup remains unchanged. Rendered
regression tests mount the production component through a test-only build entry
with the real Qt native bridge and SQLite, not a mock backend. They test phone,
ID, unknown phone and invalid phone, display order history after address removal,
and open statistics. This fixture is not part of the production entry point and
does not expose a new application screen. Address deletion has no existing UI
control; the public bridge and service workflows are tested directly rather than
adding an unsolicited address-management screen.
