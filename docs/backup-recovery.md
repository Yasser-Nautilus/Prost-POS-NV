# Local backup and recovery

These commands are explicit operator actions. No automatic schedule, storage
location, retention policy or cloud upload is enabled. No live database was
restored during development. The installation's existing database path is not
changed by this update.

## Create a backup

Use the database path actually configured for that installation, not a guessed
path. Choose a new local destination on a trusted disk with sufficient free space:

```sh
python -m broast_pos.operations.recovery backup \
  --source /path/to/installation.db \
  --destination /chosen/backup-2026-11-23.db
```

The SQLite online backup API takes a consistent snapshot including committed WAL
transactions, even while the app is running. Do not copy only the .db file from a
running installation: committed data may still be in -wal. The tool checks SQLite
integrity, foreign keys, required POS tables and supported schema version before
accepting the result. Destination must be new; existing files and symlinks are
refused. On systems that honor POSIX permissions, a new copy is owner-only (0600).
Windows and shared filesystems require their own access-control checks.

Backups contain customer and financial records plus credential hashes. Protect
them like the live database. This tool does not encrypt or upload them. Keep the
installation's PIN pepper/configuration securely and separately: the database
alone is not a complete application recovery package. Never put secrets in a
support ticket or repository. Decide the destination, encryption, retention,
frequency and off-device copy policy explicitly for the installation.

## Restore drill, without replacing production

```sh
python -m broast_pos.operations.recovery restore \
  --source /chosen/backup-2026-11-23.db \
  --destination /disposable/location/restore-candidate.db
```

Restore creates a new file, upgrades only that candidate with this application's
migrations, then rechecks integrity and foreign keys. The source backup stays
unchanged. A corrupt, unrelated, unsupported newer-schema or invalid-FK database
is rejected. Failure removes only the newly created candidate. Existing live or
backup files are never overwritten. Do not use the candidate with another
application version whose schema support differs.

For a real recovery, first stop all POS processes, preserve a fresh snapshot of
whatever live data remains, and review the candidate in an isolated installation
with the matching application/configuration. Verify order counts and representative
invoices, cash-ledger balances, customers, open sessions/trips, parked work and
login access. Do not print real tickets, settle drivers or take payments during a
drill. Only after operator approval should a qualified operator switch the
installation's configured path or replace a stopped database with an independently
preserved rollback copy. This tool intentionally does not perform that switch.
Keep the original backup and pre-switch live snapshot until acceptance.

## Automated checks

`pytest tests/test_backup_recovery.py` uses disposable databases only. It proves
committed WAL inclusion, exclusion of uncommitted writes, restore/reopen with
orders/items/ledger/audit/parked rows intact, repeatable upgrade, source preservation,
existing-target/symlink protection, invalid input rejection and failure cleanup.
This is an operational method and test evidence, not a claim that backups are now
running for a restaurant or that a machine/storage failure has been covered.
