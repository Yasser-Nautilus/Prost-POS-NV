# 📁 config — PROGRESS

## 🎯 Goal

Centralize **all system configuration and constants** — no business logic, just values that control how the system behaves. Should be easily editable without touching code. **White-label ready**: one config file swap = new restaurant identity.

---

## ✅ Tasks

### 1. Restaurant Branding (`restaurant.json`) — **Single File White-Label**

- **What**: One JSON file that fully customizes the system for any restaurant
- **Details**:
  ```json
  {
    "restaurant": {
      "name_ar": "بروستش",
      "name_en": "Prostsh",
      "slogan_ar": "بروستش لي القرمشة مبيهزرش",
      "logo_path": "./assets/branding/logo.png",
      "receipt_footer": "شكراً لزيارتكم — Thank you for visiting",
      "receipt_notice": "",
      "login_sidebar_image": "./assets/branding/sidebar.png",
      "app_background_image": ""
    },
    "theme": {
      "primary_bg": "#0d1b2a",
      "secondary_bg": "#1b2838",
      "accent_green": "#28a745",
      "accent_red": "#dc3545",
      "accent_blue": "#007bff",
      "accent_orange": "#fd7e14",
      "accent_yellow": "#ffc107",
      "text_primary": "#ffffff",
      "text_secondary": "#a0aec0",
      "text_muted": "#6c757d",
      "border_color": "#2d3748",
      "input_bg": "#1a202c",
      "button_confirm": "#28a745",
      "button_cancel": "#dc3545",
      "button_neutral": "#4a5568",
      "table_occupied": "#dc3545",
      "table_free": "#28a745",
      "status_pending": "#ffc107",
      "status_ready": "#28a745",
      "status_cancelled": "#dc3545"
    },
    "category_colors": [
      "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
      "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
      "#16a085", "#c0392b", "#2980b9", "#27ae60"
    ],
    "fonts": {
      "family_arabic": "Noto Naskh Arabic",
      "family_english": "Noto Naskh Arabic",
      "size_heading": 18,
      "size_body": 14,
      "size_button": 16,
      "size_small": 12,
      "size_receipt": 11
    }
  }
  ```
- **Why**: Selling the system to another restaurant requires only editing this one file. No code changes needed. Logo, name, colors, fonts — everything in one place.
- **How to use**:
  - Developer edits `restaurant.json` → entire app changes identity
  - Future: Admin page in the app to edit these values via UI
  - Theme colors are loaded at startup and applied via Qt StyleSheet
  - Receipt templates read `restaurant.name_ar`, `receipt_footer`, etc.
- **Status**: `Done`

### 2. General Settings (`config.py`)

- **What**: Application-wide constants
- **Details**:
  - `APP_NAME` = loaded from `restaurant.json → restaurant.name_ar`
  - `APP_VERSION` = "1.0.0"
  - `ENVIRONMENT` = "dev" | "prod"
  - `DEBUG` = True/False
  - `LANGUAGE` = "ar" (Arabic primary)
- **Status**: `Done`

### 3. Printer Configuration (`printers.json`)

- **What**: Printer role-to-device mapping
- **Details**:
  - Stored as JSON file:
    ```json
    {
      "kitchen": {"type": "network", "host": "192.168.x.x", "port": 9100},
      "cashier_1": {"type": "usb", "vendor_id": "0x0483", "product_id": "0x5743"},
      "cashier_2": {"type": "usb", "vendor_id": "0x0483", "product_id": "0x5743"}
    }
    ```
  - Loaded at app startup by PrinterManager
  - Editable without code changes
- **Status**: `Done`

### 4. Business Rules Configuration

- **What**: Configurable business parameters
- **Details**:
  - `DEFAULT_TAX_RATE` = 0.0 (no tax currently, configurable for future)
  - `SERVICE_CHARGE_PCT` = 0.0 (service charge % applied to subtotal. 0 = no service charge)
  - `MAX_DISCOUNT_PERCENT` = 100 (safety cap — discount cannot exceed subtotal)
  - `DISCOUNT_TYPES` = "flat" | "percent" (discount can be a fixed amount or a percentage of subtotal)
  - `ORDER_NUMBER_PREFIX` = "" (optional prefix for invoice numbers)
  - `TABLE_COUNT` = 10 (number of dine-in tables displayed in table grid, configurable)
  - `AUTO_PRINT_KITCHEN` = True
  - `AUTO_PRINT_RECEIPT` = True
  - `TAKEAWAY_AUTO_COMPLETE_MINUTES` = 20 (visual highlight timer)
  - `TRACKING_REFRESH_SECONDS` = 10
- **Why**: Zones are now in the database (manager-managed), not in config.
- **Status**: `Done`

### 5. Paths & Files

- **What**: File system paths used by the application
- **Details**:
  - `DATABASE_PATH` = "./data/broast_pos.db"
  - `LOGS_PATH` = "./logs/"
  - `PRINTER_CONFIG_PATH` = "./config/printers.json"
  - `RESTAURANT_CONFIG_PATH` = "./config/restaurant.json"
  - `FONTS_PATH` = "./assets/fonts/"
  - `BRANDING_PATH` = "./assets/branding/"
- **Status**: `Done`

---

## 📝 Notes

- **No logic here** — only constants and configuration values
- **White-label**: `restaurant.json` is the ONLY file to change for a new restaurant
- `restaurant.json` is loaded once at startup and cached in memory
- Theme colors from `restaurant.json` → converted to Qt StyleSheet at startup
- `category_colors` is a rotating palette — categories cycle through these colors
- Fonts are bundled in `assets/fonts/` (Noto Naskh Arabic TTF files)
- Sensitive values (printer addresses) stay in `printers.json`, separate from branding
- Future: Admin page to edit `restaurant.json` via UI (deferred to v2)
