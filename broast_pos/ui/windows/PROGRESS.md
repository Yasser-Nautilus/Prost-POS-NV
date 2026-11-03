# 📁 ui/windows — PROGRESS

## 🎯 Goal

Define the **main application windows** — the navigation shell and the login screen. These are containers that hold views, not business logic.

---

## ✅ Tasks

### 1. Main Window / Navigation Shell (`main_window.py`)

- **What**: The primary application window with sidebar navigation
- **Details**:
  - Sidebar with navigation buttons:
    - 🛒 نقطة البيع (POS) — default active
    - 📋 تتبع الطلبات (Order Tracking)
    - 🚚 التوصيل (Delivery)
    - 📊 التقارير (Reports)
    - 📦 المنتجات (Products) — manager only
    - 👥 المستخدمين (Users) — admin only
    - 💰 المالية (Financial) — manager only
  - Content area: `QStackedWidget` that swaps between views
  - Header: show current user name, role, and shift status
  - Role-based navigation: cashiers only see POS + Tracking + Delivery
  - Logout button: full logout → returns to login window (no fast switch — Option A)
  - Printer status indicator: small badge showing printer health
- **Why**: Role-based navigation prevents cashiers from accessing management screens. The stacked widget approach means views are created once and swapped instantly — no re-creation lag.
- **Status**: `Done`

### 2. Login Window (`login_window.py`)

- **What**: Window container for the avatar-tile login flow
- **Details**:
  - Window frame and geometry management (full-screen or maximized)
  - Hosts `login_view.py` which contains the actual avatar tile UI + PIN entry
  - On successful login: hide login window → show main window
  - On logout from main window: show login window again
  - On app start: always show login window first
- **Why**: The window is a container only — all login UI logic (avatar tiles, PIN numpad, validation) lives in `login_view.py`. This separation keeps window management clean.
- **Status**: `Done`

---

## 📝 Notes

- Windows contain **zero business logic** — they delegate everything to services
- Main window receives services via dependency injection at creation
- Login window calls `auth_service.login()` and passes the user session to main window
- The main window should be **full-screen** or **maximized** for restaurant use
