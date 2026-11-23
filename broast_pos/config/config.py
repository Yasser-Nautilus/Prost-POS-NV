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
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# 0. Canonical Environment / Dotenv Loader
# ============================================================================
# All paths are relative to the project root (where main.py lives).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # broast_pos/


def load_env_file(
    env_path: Path | str | None = None,
    override: bool = False,
) -> dict[str, str]:
    """Load environment variables from a .env file into os.environ.

    Precedence order:
      1. Process environment variables (os.environ) take precedence (when override=False).
      2. Key-value pairs defined in the .env file.
      3. Application defaults defined in code.

    Args:
        env_path: Optional explicit path to .env file. If omitted, checks
                  BROAST_ENV_FILE env var, then defaults to `<project_root>/.env`.
        override: If True, overwrite variables already present in os.environ.
                  Default is False (standard dotenv convention).

    Returns:
        Dict of key-value pairs loaded from the file.
    """
    if env_path is None:
        explicit = os.getenv("BROAST_ENV_FILE", os.getenv("ENV_FILE"))
        if explicit:
            target_path = Path(explicit)
        else:
            target_path = _PROJECT_ROOT.parent / ".env"
            if not target_path.is_file():
                # Also check inside broast_pos/ as fallback
                fallback_path = _PROJECT_ROOT / ".env"
                if fallback_path.is_file():
                    target_path = fallback_path
    else:
        target_path = Path(env_path)

    if not target_path.is_file():
        return {}

    loaded: dict[str, str] = {}
    try:
        with target_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and (
                    (val[0] == '"' and val[-1] == '"')
                    or (val[0] == "'" and val[-1] == "'")
                ):
                    val = val[1:-1]
                loaded[key] = val
                if override or key not in os.environ:
                    os.environ[key] = val
    except Exception as exc:
        logger.warning("Could not read .env file at %s: %s", target_path, exc)

    return loaded


# Load canonical .env file once on module import
load_env_file()


# ============================================================================
# 1. General Settings (Task 2)
# ============================================================================
DEV_FALLBACK_PEPPER: str = "broast-dev-fallback-pepper-2026-unsecret"

DISALLOWED_PEPPER_PLACEHOLDERS: set[str] = {
    "broast-pos-default-pepper-change-me",
    "change-me-to-a-secure-random-secret-pepper-string",
    "broast-dev-fallback-pepper-2026-unsecret",
    "test-pepper",
    "pepper",
    "secret",
    "password",
    "placeholder",
    "default",
}


def get_environment() -> str:
    """Return the active environment ('dev', 'prod', or 'test')."""
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "dev")).lower()


def is_production() -> bool:
    """Return True if running in production mode."""
    return get_environment() == "prod"


def is_debug() -> bool:
    """Return True if debug mode is active."""
    default_debug = "true" if not is_production() else "false"
    return os.getenv("DEBUG", default_debug).lower() in ("true", "1", "yes")


def get_pin_pepper() -> str:
    """Return the PIN pepper configured in the environment, or the dev fallback."""
    pepper = os.getenv("BROAST_PIN_PEPPER")
    if pepper is not None and pepper.strip():
        return pepper.strip()
    return DEV_FALLBACK_PEPPER


def is_placeholder_pepper(pepper: str) -> bool:
    """Return True if *pepper* is empty, matches a known placeholder, or is insecure."""
    if not pepper or not pepper.strip():
        return True
    cleaned = pepper.strip().lower()
    if cleaned in DISALLOWED_PEPPER_PLACEHOLDERS:
        return True
    disallowed_substrings = (
        "change-me",
        "changeme",
        "placeholder",
        "example",
        "replace-me",
        "replaceme",
        "dummy",
    )
    if any(sub in cleaned for sub in disallowed_substrings):
        return True
    return len(pepper.strip()) < 16


def validate_production_secrets(
    env: str | None = None,
    pepper: str | None = None,
) -> None:
    """Validate that secrets are set and not placeholders in production.

    Raises:
        RuntimeError: If running in production and BROAST_PIN_PEPPER is missing,
                      is a placeholder, contains insecure markers, or is too short.
    """
    current_env = (env or get_environment()).lower()
    if current_env != "prod":
        return

    check_pepper = pepper if pepper is not None else os.getenv("BROAST_PIN_PEPPER", "")
    if not check_pepper or not check_pepper.strip():
        raise RuntimeError(
            "BROAST_PIN_PEPPER must be set in production (APP_ENV=prod). "
            "Refusing to run without a secret pepper."
        )

    if is_placeholder_pepper(check_pepper):
        raise RuntimeError(
            f"Insecure or placeholder BROAST_PIN_PEPPER rejected in production: {check_pepper!r}. "
            "A strong, unique secret key of at least 16 characters must be set."
        )


def get_initial_admin_pin() -> str | None:
    """Return the configured initial admin PIN from environment if set."""
    pin = os.getenv("BROAST_INITIAL_ADMIN_PIN", os.getenv("INITIAL_ADMIN_PIN"))
    if pin is not None:
        pin = pin.strip()
    return pin if pin else None


APP_VERSION: str = "1.0.0"
ENVIRONMENT: str = get_environment()
DEBUG: bool = is_debug()
LANGUAGE: str = os.getenv("LANGUAGE", "ar")           # Arabic primary
# Set PROST_PRINTER_SIMULATE=1 to run without hardware: prints succeed and
# output is written to PRINTER_SIMULATE_OUTPUT_DIR as timestamped JSON files.
PRINTER_SIMULATE: bool = os.getenv("PROST_PRINTER_SIMULATE", "0").strip() in ("1", "true", "yes")

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

DATABASE_PATH: str = str(_PROJECT_ROOT / "data" / "broast_pos.db")
LOGS_PATH: str = str(_PROJECT_ROOT.parent / "logs")
PRINTER_CONFIG_PATH: str = str(_PROJECT_ROOT / "config" / "printers.json")
PRINTER_SIMULATE_OUTPUT_DIR: str = str(_PROJECT_ROOT.parent / "printouts")
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
    global _restaurant_cache
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
    except Exception:
        logger.exception("Failed to write restaurant config to %s", config_path)

