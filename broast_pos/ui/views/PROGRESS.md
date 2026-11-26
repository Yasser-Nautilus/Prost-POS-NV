# UI Views — Progress

> **Last Updated:** 2026-11-26

---

## Status: Legacy

> [!IMPORTANT]
> These are **legacy PyQt6 view classes** from the original desktop UI implementation. They are **retained in the repository** but are **not used by the active runtime**. The active frontend uses **React views** in `frontend/src/views/`.

---

## Replacement

| Legacy PyQt6 View | React Replacement | Status |
|---|---|---|
| PyQt6 POS view | `POSView.tsx` | Implemented |
| PyQt6 Delivery view | `DeliveryView.tsx` | Implemented |
| PyQt6 Order tracking | `TrackingView.tsx` | Implemented |
| PyQt6 Reports view | `ReportsView.tsx` | Implemented |
| PyQt6 Products view | `ProductsView.tsx` | Implemented |
| PyQt6 Users view | `UsersView.tsx` | Implemented |
| PyQt6 Login view | `LoginView.tsx` | Implemented |
| *(no equivalent)* | `DriverSettlementView.tsx` | Implemented |
| *(no equivalent)* | `AuditLogView.tsx` | Implemented |
| *(no equivalent)* | `SessionsView.tsx` | Implemented — mounted in `App.tsx` with a navigation tab since PRs #59/#60 |

---

## Disposition

These files are retained for reference. They should not be modified and are not part of active development.

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26 after reviewing the code against the merged PRs.

- `pos_view.py` (the 993-line PyQt6 POS view) was deleted together with its broken discount path [#62]. Seven legacy views remain, kept for reference only.
- `reports_view.py`: the daily print now prints the day shown in the tab instead of the active shift's totals next to another day's sales (H16); the `shift_id` fallback was removed from the `print_daily_summary` call (combined H01-H20 audit merge).
