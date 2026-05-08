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
  - User switch button: triggers PIN dialog without full logout
  - Printer status indicator: small badge showing printer health
- **Why**: Role-based navigation prevents cashiers from accessing management screens. The stacked widget approach means views are created once and swapped instantly — no re-creation lag.
- **Status**: `Not started`

### 2. Login Window (`login_window.py`)

- **What**: Full-screen login with username and PIN
- **Details**:
  - Clean, centered login form
  - Username field (dropdown or text input)
  - PIN field (masked, 4-6 digits)
  - Login button + keyboard shortcut (Enter)
  - Error message display (Arabic)
  - On successful login: hide login, show main window
  - On app start: always show login first
- **Why**: Simple and fast login is essential. At shift start, the cashier needs to get in within 5 seconds. No unnecessary branding or splash screens.
- **Status**: `Not started`

---

## 📝 Notes

- Windows contain **zero business logic** — they delegate everything to services
- Main window receives services via dependency injection at creation
- Login window calls `auth_service.login()` and passes the user session to main window
- The main window should be **full-screen** or **maximized** for restaurant use
