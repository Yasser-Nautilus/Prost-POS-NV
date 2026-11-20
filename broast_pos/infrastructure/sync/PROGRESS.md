# Cloud Sync — Progress

> **Last Updated:** 2026-11-20
> **Source of Truth:** `broast_pos/infrastructure/sync/`

---

## Overview

The cloud synchronization module is planned for future development. All tasks are **Deferred** — no implementation exists.

---

## Planned Features

| Feature | Status | Description |
|---|---|---|
| Cloud synchronization | Deferred | Sync local SQLite data to a cloud database |
| Multi-device sync | Deferred | Support multiple POS terminals sharing data |
| Offline queue | Deferred | Queue operations when offline, replay when connected |
| Conflict resolution | Deferred | Handle concurrent edits from multiple devices |

---

## Notes

- The `sync/` directory exists with an `__init__.py` but no implementation files.
- Cloud sync is not referenced by any active service, controller, or bridge action.
- No timeline has been set for implementation.
