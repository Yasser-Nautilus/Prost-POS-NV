# UI Windows — Progress

> **Last Updated:** 2026-11-26

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

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26. Legacy PyQt6 window classes are still untouched. Changes apply to the active `WebShell` (`broast_pos/ui/web_shell.py`) and to `main.py`.

- Window title is now "Nautix POS - نظام البيع", and alert/confirm dialog titles read "Nautix POS" [#110].
- `main.py` sets the application display name to "Nautix POS" and the window/taskbar icon to `assets/branding/nautix_app_icon.png` (hex N). Before this, no window icon was set and the OS default showed [#110].
- The restaurant branding inside the UI (Prostsh, receipts, login page) is unchanged by the app rename [#79, #110].
