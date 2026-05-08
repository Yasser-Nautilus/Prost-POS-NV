# 🍗 Prost POS — نظام نقطة البيع

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/PyQt6-Desktop_UI-41CD52?style=for-the-badge&logo=qt&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL_Mode-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![ESC/POS](https://img.shields.io/badge/ESC%2FPOS-Thermal_Print-FF6B35?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-In_Development-red?style=for-the-badge)

**A full-featured, Arabic-first Point of Sale system built for restaurant operations**

*نظام كاشير متكامل مصمم للمطاعم — عربي أولاً، سريع، موثوق*

</div>

---

## 📖 About / عن المشروع

**Prost POS** is a desktop POS application built specifically for **Prostsh Restaurant (بروستش)**. It handles the full restaurant operation lifecycle — from order creation to driver settlement — with a focus on speed, reliability, and Arabic language support.

The system is designed as **white-label ready**: changing a single `restaurant.json` file transforms it into a completely different restaurant's system (new name, logo, colors, fonts — no code changes needed).

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🛒 **4 Order Types** | Dine-In (صالة) · Takeaway (تيك اواي) · Delivery (دليفري) · Pickup (استلام محل) |
| 💳 **3 Payment Methods** | Cash (كاش) · Visa (فيزا) · Online (اونلاين) |
| 🖨️ **Silent Auto-Printing** | Kitchen tickets + customer receipts — zero dialogs, ever |
| 🚚 **Delivery Management** | Driver check-in/out, trip dispatch, per-trip settlement |
| 📊 **Financial Reports** | Daily, monthly, yearly summaries with thermal print format |
| 🔐 **Role-Based Access** | Cashier / Manager / Admin with PIN-based manager overrides |
| 💰 **Shift Management** | Open/close/transfer shifts with full cash reconciliation |
| 🏷️ **White-Label Ready** | One config file swap = completely new restaurant identity |
| 🌐 **RTL Arabic UI** | Full right-to-left layout with Arabic fonts |
| 📡 **Google Sheets Ready** | Architecture prepared for future cloud sync |

---

## 🏗️ Architecture

```
broast_pos/
├── config/              # White-label config (restaurant.json, printers.json)
├── core/
│   ├── models/          # Pure Python dataclasses (Order, User, Product, ...)
│   └── services/        # All business logic (OrderService, DeliveryService, ...)
├── data/
│   ├── database/        # SQLite connection, schema, migrations, seed
│   └── repositories/    # Data access layer (enables future Google Sheets sync)
├── infrastructure/
│   ├── printing/        # ESC/POS thermal printing (10 receipt templates)
│   └── sync/            # Future Google Sheets integration (stub)
└── ui/                  # PyQt6 — presentation only, zero business logic
    ├── windows/         # Main window (role-based nav) + Login
    ├── views/           # 8 screens (POS, Tracking, Delivery, Reports, ...)
    └── components/      # 6 reusable widgets (ProductGrid, OrderPanel, ...)
```

**Clean Architecture principles**: UI → Services → Repositories → SQLite. No layer bypasses another.

---

## 🍽️ Order Flows

### Dine-In (صالة)
```
Select Table → Add Items → Confirm → Kitchen Prints → [Eat] → Pay → Receipt → Table Free
```

### Takeaway (تيك اواي)
```
Add Items → Confirm → Kitchen Prints → Payment Dialog Immediately → Receipt
```

### Delivery — Cash (دليفري + كاش)
```
Phone Lookup → Select Address → Add Items → Confirm → Kitchen Prints
→ Assign Driver → Dispatch → [Deliver + Collect Cash] → Return → Settle
```

### Delivery — Online (دليفري + اونلاين)
```
Phone Lookup → Select Address → Add Items → Confirm (auto-marked PAID)
→ Assign Driver → Dispatch → [Deliver, collect nothing] → Return → Settle
```

---

## 🖨️ Thermal Printing

10 print layouts, all 80mm ESC/POS format, fully silent:

- **Kitchen Ticket** — No prices, no customer info. Order # in large bold font
- **Customer Receipts** — 4 variants (Dine-In / Delivery / Takeaway / Pickup)
- **Amendment Ticket** — تابع (follow-up) showing only changes to an order
- **Daily Sales Report** — Matches exact receipt photo format
- **Shift Transfer Report** — Mid-day cashier handover snapshot
- **Driver Settlement Receipt** — Per-trip cash accountability
- **Driver Summary** — End-of-day fees per driver

> **Zero dialogs. Ever.** All printing is automatic and silent.

---

## 🔐 Permissions

| Action | Cashier | Manager | Admin |
|--------|:-------:|:-------:|:-----:|
| Create orders | ✅ | ✅ | ✅ |
| Apply discount | ⚠️ override | ✅ | ✅ |
| Cancel order | ⚠️ override | ✅ | ✅ |
| Remove item from saved order | ⚠️ override | ✅ | ✅ |
| Manage products/zones | ❌ | ✅ | ✅ |
| Open/close shift | open only | ✅ | ✅ |
| View reports | ❌ | ✅ | ✅ |
| Manage users | ❌ | ❌ | ✅ |

> ⚠️ = Manager PIN override required (cashier requests, manager enters PIN on their device)

---

## 💡 Design Decisions

- **No modifier system** — Each product variation (hot/cold, size) is a separate menu item. Keeps the POS flow instant: tap product = added to order, no popup.
- **Quantity is always integer** — No 0.5 chickens.
- **PIN is globally unique** — Enables manager identification by PIN alone (override pattern).
- **Expenses are immutable** — Once entered, cannot be edited or deleted.
- **Invoice numbers reset daily** — Resets to #1 on every new shift open.
- **Offline-first** — SQLite local storage. Google Sheets sync is a future phase.

---

## 🚀 Roadmap

| Phase | Scope | Status |
|:-----:|-------|:------:|
| 1 | Database + Models + Schema | 🔴 Planned |
| 2 | Repositories + Base CRUD | 🔴 Planned |
| 3 | Auth Service + Login UI | 🔴 Planned |
| 4 | Product Service + POS View | 🔴 Planned |
| 5 | Order Service + Kitchen Printing | 🔴 Planned |
| 6 | Payment Flow + Receipt Printing | 🔴 Planned |
| 7 | Tracking View + Status Engine | 🔴 Planned |
| 8 | Delivery Service + Delivery View | 🔴 Planned |
| 9 | Financial Service + Shift Lifecycle | 🔴 Planned |
| 10 | Reports + Daily Summary | 🔴 Planned |
| 11 | Permissions + Audit + PIN Override | 🔴 Planned |
| 12 | Polish: Theme, White-Label, Config | 🔴 Planned |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| UI Framework | PyQt6 |
| Database | SQLite (WAL mode) |
| Thermal Printing | python-escpos (USB/Network) |
| Future Sync | Google Sheets API (gspread) |

---

## 📂 Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | 🟢 Production — stable releases only |
| `development` | 🔵 Active development — all new features go here |

**Workflow**: feature branches → `development` → tested → merged to `main`

---

## 📋 Documentation

| File | Description |
|------|-------------|
| [`Structure.md`](./Structure.md) | Full annotated project file tree |
| [`Pos Project Structure + Progress.md`](<./Pos%20Project%20Structure%20+%20Progress.md>) | 88-task progress tracker across all modules |
| `broast_pos/**/PROGRESS.md` | Per-module detailed task descriptions |

---

<div align="center">

Made with ❤️ for **بروستش** — *بروستش في القرمشة مبيهزرش*

</div>
