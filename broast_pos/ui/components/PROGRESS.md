# UI Components — Progress

> **Last Updated:** 2026-11-20

---

## Status: Legacy

> [!IMPORTANT]
> These are **legacy PyQt6 widget components** from the original desktop UI implementation. They are **retained in the repository** but are **not used by the active runtime**. The active frontend is a React + TypeScript application rendered inside `QWebEngineView`.

The active application path is:

```
main.py → WebShell (QWebEngineView) → React App (frontend/src/)
```

These PyQt6 components are **not imported** by `WebShell`, `main.py`, or any active code path.

---

## Legacy Components

The following PyQt6 widget components exist in `broast_pos/ui/components/`:

- Custom buttons and input fields
- Product selection grids
- Order summary panels
- Payment dialogs
- Navigation bars
- Status indicators

---

## Replacement

All UI functionality previously provided by these components is now implemented in the React frontend:

| Legacy Component | React Replacement |
|---|---|
| PyQt6 product grid | `POSView.tsx` product selection |
| PyQt6 payment dialog | `PaymentDialog.tsx` |
| PyQt6 PIN entry | `PinDialog.tsx` |
| PyQt6 numpad | `Numpad.tsx` |
| PyQt6 customer lookup | `CustomerLookup.tsx` |
| PyQt6 table grid | `TableGrid.tsx` |
| PyQt6 discount dialog | `DiscountDialog.tsx` |

---

## Disposition

These files are retained for reference. They should not be modified and are not part of active development.
