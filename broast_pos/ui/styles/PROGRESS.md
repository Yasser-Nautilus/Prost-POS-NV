# 📁 ui/styles — PROGRESS

## 🎯 Goal

Define the **global visual theme** for the entire application — colors, fonts, spacing, and component styles in one centralized place.

---

## ✅ Tasks

### 1. Global Theme (`theme.py`)

- **What**: Centralized QSS (Qt Style Sheet) for the entire application
- **Details**:
  - **Color palette**: Dark navy base theme (high contrast, easy on eyes in restaurant lighting)
    - Background: `#1a1d23` (dark navy)
    - Surface: `#252830` (slightly lighter)
    - Primary: `#3b82f6` (blue accent)
    - Success: `#22c55e` (green for completed/available)
    - Warning: `#f59e0b` (amber for pending)
    - Danger: `#ef4444` (red for cancel/error)
    - Text primary: `#ffffff`
    - Text secondary: `#9ca3af`
  - **Typography**:
    - Arabic font: "Cairo" or "Tajawal" (Google Fonts, bundled)
    - Font sizes: title (18px), body (14px), caption (12px), large (24px for kitchen)
  - **Spacing**: consistent padding/margins (8px, 12px, 16px, 24px)
  - **Component styles**:
    - Buttons: rounded corners, hover/press states, minimum 48px height
    - Category tabs: highlighted active state
    - Order panel: card-style items with subtle borders
    - Input fields: clear focus state, large touch target
    - Dialogs: centered, dimmed background overlay
  - **RTL support**: layout direction for Arabic text
- **Why**: A consistent dark theme is appropriate for restaurant environments. High contrast improves readability. Centralized styling prevents inconsistent UI across views.
- **Status**: `Done`

---

## 📝 Notes

- Theme is applied globally via `QApplication.setStyleSheet()`
- Individual views should NOT override theme colors — use the palette
- All sizes must accommodate touch input (minimum 48x48px tap targets)
- Bundle Arabic font files with the application (don't depend on system fonts)
