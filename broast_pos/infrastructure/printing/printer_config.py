"""
Printer configuration — load and parse ``printers.json``.

Provides typed access to printer connection details for kitchen,
cashier_1, and cashier_2.  Loaded once at app startup and cached.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from broast_pos.config.config import PRINTER_CONFIG_PATH

logger = logging.getLogger(__name__)


@dataclass
class PrinterEntry:
    """A single printer's connection info."""

    key: str                     # "kitchen", "cashier_1", "cashier_2"
    conn_type: str               # "usb", "network", "serial", "dummy"
    # USB
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    # Network
    host: Optional[str] = None
    port: int = 9100
    # Serial
    device: Optional[str] = None


_config_cache: Optional[Dict[str, PrinterEntry]] = None


def load_printer_config() -> Dict[str, PrinterEntry]:
    """Load ``printers.json`` and return a dict keyed by printer role.

    Returns:
        ``{"kitchen": PrinterEntry, "cashier_1": PrinterEntry, ...}``
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = Path(PRINTER_CONFIG_PATH)
    if not config_path.exists():
        logger.warning("printers.json not found at %s — using dummy printers", config_path)
        _config_cache = _build_dummy_config()
        return _config_cache

    try:
        with config_path.open(encoding="utf-8") as f:
            raw: dict = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to parse printers.json: %s — using dummy printers", exc)
        _config_cache = _build_dummy_config()
        return _config_cache

    entries: Dict[str, PrinterEntry] = {}
    for key, cfg in raw.items():
        entries[key] = PrinterEntry(
            key=key,
            conn_type=cfg.get("type", "dummy"),
            vendor_id=cfg.get("vendor_id"),
            product_id=cfg.get("product_id"),
            host=cfg.get("host"),
            port=cfg.get("port", 9100),
            device=cfg.get("device"),
        )

    _config_cache = entries
    logger.info("Loaded printer config: %s", list(entries.keys()))
    return _config_cache


def get_printer_entry(key: str) -> Optional[PrinterEntry]:
    """Get a single printer entry by role key."""
    return load_printer_config().get(key)


def _build_dummy_config() -> Dict[str, PrinterEntry]:
    """Fallback — all printers set to dummy for dev/testing."""
    return {
        "kitchen": PrinterEntry(key="kitchen", conn_type="dummy"),
        "cashier_1": PrinterEntry(key="cashier_1", conn_type="dummy"),
        "cashier_2": PrinterEntry(key="cashier_2", conn_type="dummy"),
    }


def reload_config() -> Dict[str, PrinterEntry]:
    """Force-reload the printer config (e.g. after admin edits)."""
    global _config_cache
    _config_cache = None
    return load_printer_config()
