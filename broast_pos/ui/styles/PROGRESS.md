# UI Styles — Progress

> **Last Updated:** 2026-11-26

---

## Status: Legacy

> [!IMPORTANT]
> These are **legacy PyQt6 theme/stylesheet files** from the original desktop UI implementation. They are **retained in the repository** but are **not used by the active runtime**. The active frontend uses **Tailwind CSS** for styling.

---

## Replacement

All styling is now handled by:
- **Tailwind CSS** — Utility-first CSS framework configured in `frontend/tailwind.config.js`.
- **Component-level styles** — Inline Tailwind classes in React TSX components.
- **`frontend/src/index.css`** — Tailwind imports and any global overrides.

---

## Disposition

These files are retained for reference. They should not be modified and are not part of active development.

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26 after reviewing the code against the merged PRs.

No code changes in this directory this period. `theme.py` is still imported only by the legacy PyQt6 views and dialogs; the active React frontend uses Tailwind.
