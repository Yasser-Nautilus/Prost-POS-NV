# Prost POS

A hybrid desktop point-of-sale system for a restaurant, combining a **Python backend** with a **React + TypeScript frontend** rendered inside a PySide6 QWebEngineView.

## Technology Stack

| Layer | Technology |
|---|---|
| Desktop Shell | PySide6 / QWebEngineView |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Communication | QWebChannel → POSBridge dispatch |
| Backend | Python 3.12+, Clean Architecture |
| Database | SQLite (WAL mode) |
| Printing | python-escpos (ESC/POS thermal printers) |
| Authentication | PBKDF2-HMAC-SHA256 (salted + peppered) |

## Architecture

Prost POS is a **hybrid desktop application**:

- The **backend** is a Python application using Clean Architecture (models → services → repositories → SQLite).
- The **frontend** is a React single-page application built with Vite and Tailwind CSS.
- The two communicate via **QWebChannel**: the React app calls `bridge.ts` functions, which invoke `POSBridge.dispatch()` on the Python side, routing to the appropriate controller and service.
- The whole application runs inside a **PySide6 QWebEngineView** window (`WebShell`).

```
React (TypeScript) ←→ QWebChannel ←→ POSBridge (Python) ←→ Services ←→ SQLite
```

## Features

- **Order Management:** Dine-in, takeaway, and delivery orders with a 7-state lifecycle.
- **Product & Category Management:** Full CRUD with search.
- **Customer Management:** Phone-based lookup, delivery addresses, zone configuration.
- **Delivery System:** Driver attendance, trip management, per-trip and daily settlement.
- **Cash Ledger:** Append-only, integer-piaster accounting with idempotency and database-level protection.
- **Cashier Sessions:** Station-based sessions with opening float, cash counting, variance, and handover.
- **Business Day Accounting:** X-Report, Z-Report, and business-day close operations.
- **Authentication:** PIN-based login with PBKDF2 hashing, brute-force throttling, legacy hash auto-upgrade.
- **Role-Based Access:** Cashier, Manager, and Admin roles with granular permissions.
- **Audit Logging:** Centralized audit trail with before/after snapshots.
- **Reporting:** Daily, shift-based, monthly, and yearly sales reports.
- **Printing:** ESC/POS thermal receipt and kitchen printing with event-driven triggers.
- **Discount Policy:** Centralized discount computation with Decimal precision.

## Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- PySide6 with WebEngine support

## Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Prost-POS-NV
   git checkout dev
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env to set BROAST_PIN_PEPPER and other settings
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install and build the frontend:**
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

5. **Run the application:**
   ```bash
   python -m broast_pos.main
   ```

The database is created and migrated automatically on first run.

## Environment Variables

See [`.env.example`](.env.example) for all available settings:

| Variable | Purpose |
|---|---|
| `BROAST_PIN_PEPPER` | Secret pepper for PIN hashing |
| `APP_ENV` | Environment name (development/production) |
| `DEBUG` | Enable debug mode |
| `LANGUAGE` | Application language |
| `DB_PATH` | SQLite database file path |

> [!CAUTION]
> Never commit `.env` or any file containing `BROAST_PIN_PEPPER` to version control.

## Branch

The active development branch is **`dev`**.

## Project Status

See [`Pos Project Structure + Progress.md`](Pos%20Project%20Structure%20+%20Progress.md) for a detailed breakdown.

The core POS functionality — orders, products, customers, delivery, settlement, authentication, reporting, audit, and printing — is implemented end-to-end. See the progress document for remaining engineering work, known issues, and deferred features.

## Documentation

- [`Pos Project Structure + Progress.md`](Pos%20Project%20Structure%20+%20Progress.md) — Architecture, module status, and overall progress
- [`Structure.md`](Structure.md) — Full file tree
- [`docs/TECHNICAL_AUDIT_REPORT.md`](docs/TECHNICAL_AUDIT_REPORT.md) — Technical debt and bug findings
- Per-module `PROGRESS.md` files throughout the codebase

## License

Proprietary — not for redistribution.
