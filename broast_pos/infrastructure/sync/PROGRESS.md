# 📁 infrastructure/sync — PROGRESS

## 🎯 Goal

Prepare the system for **future Google Sheets sync** without affecting current offline-first behavior. Define the contract now, implement later.

---

## ✅ Tasks

### 1. Sync Interface / Contract (`sync_interface.py`)

- **What**: Abstract base class defining what sync operations look like
- **Details**:
  - Abstract methods:
    - `sync_order(order)` → push order data to external system
    - `sync_expense(transaction)` → push expense/cash transaction
    - `sync_report(summary)` → push shift/daily report
    - `is_connected()` → check if external system is reachable
  - No implementation — just the contract
- **Why**: By defining the interface now, services can optionally call sync hooks without knowing if Google Sheets is actually connected. When the time comes, implementing the concrete class is the only change needed.
- **Status**: `Not started`

### 2. Event Hooks in Services (Design Only)

- **What**: Plan where sync triggers will be placed in service code
- **Details**:
  - After `order_service.create_order()` → trigger `sync_order()`
  - After `order_service.cancel_order()` → trigger `sync_order()` (update status)
  - After `delivery_service.settle_trip()` → trigger `sync_expense()`
  - After `financial_service.close_shift()` → trigger `sync_report()`
  - All hooks must be **non-blocking** — fire and forget
  - If sync fails, queue for retry (future implementation)
- **Why**: The sync must never slow down or block the cashier. It runs in the background after the local operation completes.
- **Status**: `Not started`

### 3. Google Sheets Adapter — Stub (`sheets_sync.py`)

- **What**: Placeholder file that implements the sync interface with no-op methods
- **Details**:
  - Implements `SyncInterface` with empty method bodies
  - Logs "sync not configured" when called
  - Will be replaced with real Google Sheets API code later
  - Will use `gspread` library + service account credentials
- **Why**: Having the stub in place means the service layer can already call sync methods without errors. When Google Sheets is ready, we just fill in the implementation.
- **Status**: `Not started`

### 4. Background Sync Worker (Future)

- **What**: Queue-based async sync system
- **Details**:
  - Local queue (SQLite table or file-based) for pending sync items
  - Background thread/process that drains the queue
  - Retry logic with exponential backoff
  - Offline-safe: queue accumulates while offline, drains when connected
  - Status dashboard showing sync health
- **Why**: Network failures should never affect local operations. The queue guarantees eventual consistency.
- **Status**: `Not started` (FUTURE — do not implement now)

---

## 📝 Notes

- **DO NOT implement real sync now** — only define contracts and stubs
- The design must allow **plug-in later** without touching services or repositories
- Google Sheets sync will eventually replace the manual Excel tracking the manager does today
- Priority: get the local system working perfectly first, then add sync
