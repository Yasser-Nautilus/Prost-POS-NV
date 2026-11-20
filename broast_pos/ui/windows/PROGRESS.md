# UI Windows — Progress

> **Last Updated:** 2026-11-20

---

## Status: Legacy

> [!IMPORTANT]
> These are **legacy PyQt6 window classes** from the original desktop UI implementation. They are **retained in the repository** but are **not used by the active runtime**. The active window is `WebShell` (`broast_pos/ui/web_shell.py`), which hosts a `QWebEngineView` rendering the React frontend.

---

## Replacement

| Legacy | Active |
|---|---|
| PyQt6 `MainWindow` | `WebShell` (QWebEngineView + QWebChannel) |
| PyQt6 dialog windows | React components (PinDialog, PaymentDialog, DiscountDialog, ShiftDialog, etc.) |

---

## Active Window: WebShell (`web_shell.py` — 170 lines)

`WebShell` is the only window class used by the active runtime:
- Hosts a `QWebEngineView` that loads the React frontend.
- Connects `POSBridge` via `QWebChannel` for Python-React communication.
- Uses `POSWebPage` (custom `QWebEnginePage`) to route JavaScript console messages to Python logging.

---

## Disposition

Legacy window files are retained for reference. They should not be modified and are not part of active development.
