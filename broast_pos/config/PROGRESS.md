# Config — Progress

> **Last Updated:** 2026-11-26
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

---

## Updates since 2026-11-20 (PRs #59 to #110)

> Added 2026-11-26.

- `config.py` loads `.env` with the precedence process environment, then `.env`, then code defaults (`load_env_file()`). New helpers: `get_pin_pepper()`, `get_initial_admin_pin()`, `get_environment()`, `validate_production_secrets()`. Placeholder or weak secrets are rejected in production and the initial admin needs a secure PIN [#90].
- `.env.example` documents the variables; `.gitignore` ignores `.env`, `.env.*` (except `.env.example`), `*.secret`, `*.key`, `*.pem` [#90].
- `main.py` imports `config` so `config.LOGS_PATH` resolves for rotating file logging [#59, #60].
- `PROST_PRINTER_SIMULATE=1` turns on simulated printer mode (default 0) [#69].
- `restaurant.json`: theme colors moved to the Prostsh red/black palette (accent and confirm buttons `#e01038`, near-black surfaces) [#79]. `printers.json` was deleted from the repo and added to `.gitignore`: it is now a local per-machine file. A missing file falls back to a dummy config outside production and fails closed in production, where dummy and simulated printing are forbidden.
