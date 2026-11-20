# Config — Progress

> **Last Updated:** 2026-11-20
> **Source of Truth:** `config.py`, `.env.example`

---

## Overview

Application configuration is **environment-driven** via `os.getenv()`, with defaults for development. Sensitive values (e.g., PIN pepper) are loaded from environment variables and must not be committed to version control.

---

## Configuration Sources

### Environment Variables (`config.py` — 140 lines)

**Status:** Implemented

| Variable | Purpose | Default |
|---|---|---|
| `BROAST_PIN_PEPPER` | Secret pepper for PBKDF2 PIN hashing | *(required in production)* |
| `APP_ENV` | Environment name | `development` |
| `DEBUG` | Enable debug mode | `false` |
| `LANGUAGE` | Application language | `en` |
| `DB_PATH` | SQLite database file path | `broast_pos.db` |

### `.env.example` (20 lines)

**Status:** Implemented

Template file listing all available environment variables with comments. Users copy this to `.env` for local configuration.

> [!CAUTION]
> `BROAST_PIN_PEPPER` must be set to a unique secret value in production. Never commit `.env` to version control.

### Restaurant Configuration (`restaurant.json`)

**Status:** Implemented

Static restaurant metadata: name, address, phone, tax settings, business rules.

### Printer Configuration (`printers.json`)

**Status:** Implemented

Maps printer roles (cashier, kitchen, report) to hardware device identifiers.

### Business Rules

**Status:** Implemented

Configured values for:
- Tax rate and calculation.
- Currency settings.
- Order numbering format.
- Takeaway auto-complete timeout.

---

## Security

| Aspect | Status |
|---|---|
| SEC-001 (Hard-coded DEBUG) | **Resolved** — Now environment-driven via `os.getenv()` |
| PIN pepper externalized | Implemented |
| `.env` in `.gitignore` | Implemented |

---

## Summary

| Component | Status |
|---|---|
| Environment-driven config | Implemented |
| `.env.example` template | Implemented |
| Restaurant config | Implemented |
| Printer config | Implemented |
| Business rules | Implemented |
| Secret externalization | Implemented |
