"""
Application-wide configuration — constants, paths, and business rules.

This module consolidates Config Tasks 2, 4, and 5 from PROGRESS.md into
a single source of truth.  All values are plain Python constants — no
logic, no imports of application code.

Sections:
    1. General Settings  (Task 2)
    2. Business Rules     (Task 4)
    3. Paths & Files      (Task 5)
    4. Restaurant Config Loader (reads restaurant.json once)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# 1. General Settings (Task 2)
# ============================================================================
APP_VERSION: str = "1.0.0"
ENVIRONMENT: str = "dev"       # "dev" | "prod"
DEBUG: bool = True
LANGUAGE: str = "ar"           # Arabic primary

# ============================================================================
# 2. Business Rules (Task 4)
# ============================================================================
DEFAULT_TAX_RATE: float = 0.0               # No tax currently — configurable
SERVICE_CHARGE_PCT: float = 0.0             # Service charge % on subtotal (0 = off)
MAX_DISCOUNT_PERCENT: int = 100             # Safety cap — discount ≤ subtotal
DISCOUNT_TYPES: tuple[str, ...] = ("flat", "percent")
ORDER_NUMBER_PREFIX: str = ""               # Optional invoice prefix
TABLE_COUNT: int = 10                       # Dine-in table grid count
AUTO_PRINT_KITCHEN: bool = True
AUTO_PRINT_RECEIPT: bool = True
TAKEAWAY_AUTO_COMPLETE_MINUTES: int = 20    # Visual highlight timer
TRACKING_REFRESH_SECONDS: int = 10

# ============================================================================
# 3. Paths & Files (Task 5)
# ============================================================================
# All paths are relative to the project root (where main.py lives).
# Resolved to absolute at import time so they work regardless of cwd.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # broast_pos/

DATABASE_PATH: str = str(_PROJECT_ROOT / "data" / "broast_pos.db")
LOGS_PATH: str = str(_PROJECT_ROOT.parent / "logs")
PRINTER_CONFIG_PATH: str = str(_PROJECT_ROOT / "config" / "printers.json")
RESTAURANT_CONFIG_PATH: str = str(_PROJECT_ROOT / "config" / "restaurant.json")
FONTS_PATH: str = str(_PROJECT_ROOT.parent / "assets" / "fonts")
BRANDING_PATH: str = str(_PROJECT_ROOT.parent / "assets" / "branding")

# ============================================================================
# 4. Restaurant Config Loader
# ============================================================================
_restaurant_cache: dict[str, Any] | None = None


def load_restaurant_config() -> dict[str, Any]:
    """Load and cache ``restaurant.json``.

    Returns the full dict.  Called once at startup; subsequent calls
    return the cached copy.
    """
    global _restaurant_cache  # noqa: PLW0603
    if _restaurant_cache is not None:
        return _restaurant_cache

    config_path = Path(RESTAURANT_CONFIG_PATH)
    if not config_path.exists():
        logger.warning("restaurant.json not found at %s — using empty defaults", config_path)
        _restaurant_cache = {}
        return _restaurant_cache

    with config_path.open(encoding="utf-8") as f:
        _restaurant_cache = json.load(f)

    logger.info("Loaded restaurant config from %s", config_path.name)
    return _restaurant_cache


def get_restaurant_info() -> dict[str, Any]:
    """Return the ``restaurant`` section (name, logo, slogan, etc.)."""
    return load_restaurant_config().get("restaurant", {})


def get_theme() -> dict[str, str]:
    """Return the ``theme`` section (hex color values)."""
    return load_restaurant_config().get("theme", {})


def get_category_colors() -> list[str]:
    """Return the rotating category color palette."""
    return load_restaurant_config().get("category_colors", [])


def get_fonts() -> dict[str, Any]:
    """Return the ``fonts`` section (families and sizes)."""
    return load_restaurant_config().get("fonts", {})


# Derive APP_NAME from restaurant.json (falls back to hardcoded default)
def get_app_name() -> str:
    """Return the Arabic restaurant name for use as app title."""
    info = get_restaurant_info()
    return info.get("name_ar", "Prost POS")


def get_takeaway_auto_complete_minutes() -> int:
    """Return the takeaway auto complete minutes from restaurant.json or fallback to 20."""
    return load_restaurant_config().get("restaurant", {}).get("takeaway_auto_complete_minutes", 20)


def update_takeaway_auto_complete_minutes(minutes: int) -> None:
    """Save the takeaway auto complete minutes setting to restaurant.json and reload cache."""
    global _restaurant_cache
    # Ensure cache is loaded
    load_restaurant_config()
    config_data = _restaurant_cache.copy()
    if "restaurant" not in config_data:
        config_data["restaurant"] = {}
    config_data["restaurant"]["takeaway_auto_complete_minutes"] = minutes

    config_path = Path(RESTAURANT_CONFIG_PATH)
    try:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        _restaurant_cache = config_data
        logger.info("Saved takeaway_auto_complete_minutes=%d to %s", minutes, config_path.name)
    except Exception as e:
        logger.exception("Failed to write restaurant config to %s", config_path)

