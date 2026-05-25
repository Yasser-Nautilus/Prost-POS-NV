"""
Global theme — dark navy QSS, Arabic fonts, RTL.

Single entry point: ``apply_theme(app)`` at application startup.
All colours are loaded from ``restaurant.json → theme{}``, with sane
defaults so the app can launch even without the JSON file.

Public helpers:
    apply_theme(app)     — one call does everything
    get_color(name)      — lookup a named colour for programmatic use
    get_font_family()    — returns the loaded Arabic font family name
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

from broast_pos.config.config import (
    FONTS_PATH,
    get_fonts,
    get_theme,
)

logger = logging.getLogger(__name__)

# ============================================================================
# Default colour palette (used when restaurant.json is missing / incomplete)
# ============================================================================
_DEFAULTS: Dict[str, str] = {
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
    "status_cancelled": "#dc3545",
}

# Resolved at first call to apply_theme
_palette: Dict[str, str] = {}
_font_family: str = "Noto Naskh Arabic"


# ============================================================================
# Public API
# ============================================================================


def apply_theme(app: QApplication) -> None:
    """Apply the full theme to *app*: colours, fonts, RTL, QSS.

    Call once, after ``QApplication`` construction but before showing
    any window.
    """
    global _palette, _font_family  # noqa: PLW0603

    # 1. Load palette
    _palette = {**_DEFAULTS, **get_theme()}

    # 2. Load and register Arabic font
    _font_family = _load_font()

    # 3. Set application-wide defaults
    font_cfg = get_fonts()
    default_size = font_cfg.get("size_body", 14)
    app.setFont(QFont(_font_family, default_size))
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    # 4. Generate and apply QSS
    qss = _build_qss()
    app.setStyleSheet(qss)

    logger.info(
        "Theme applied — font='%s', colours=%d, RTL=on",
        _font_family,
        len(_palette),
    )


def get_color(name: str) -> str:
    """Return a hex colour by token name (e.g. ``'primary_bg'``).

    Falls back to the default palette if *name* was not loaded from JSON,
    and returns ``#ff00ff`` (magenta) for truly unknown names so they're
    visually obvious during development.
    """
    return _palette.get(name, _DEFAULTS.get(name, "#ff00ff"))


def get_font_family() -> str:
    """Return the loaded Arabic font family name."""
    return _font_family


# ============================================================================
# Internal helpers
# ============================================================================


def _load_font() -> str:
    """Register the bundled Noto Naskh Arabic font.

    Returns the family name reported by Qt, which may differ slightly
    from the filename.  Falls back to the system default if the file
    is missing.
    """
    fonts_dir = Path(FONTS_PATH)
    font_file = fonts_dir / "NotoNaskhArabic-Regular.ttf"

    if not font_file.exists():
        logger.warning("Font file not found at %s — using system default", font_file)
        return "Noto Naskh Arabic"

    font_id = QFontDatabase.addApplicationFont(str(font_file))
    if font_id == -1:
        logger.warning("Failed to load font from %s", font_file)
        return "Noto Naskh Arabic"

    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        logger.info("Loaded font: %s", families[0])
        return families[0]

    return "Noto Naskh Arabic"


def _build_qss() -> str:
    """Generate the complete QSS string from the current palette."""
    c = _palette  # shorthand
    font_cfg = get_fonts()
    f_body = font_cfg.get("size_body", 14)
    f_heading = font_cfg.get("size_heading", 18)
    f_button = font_cfg.get("size_button", 16)
    f_small = font_cfg.get("size_small", 12)

    return f"""
/* ================================================================
   GLOBAL BASE
   ================================================================ */
* {{
    font-family: "{_font_family}";
    color: {c['text_primary']};
}}

QMainWindow, QWidget {{
    background-color: {c['primary_bg']};
}}

/* ================================================================
   LABELS
   ================================================================ */
QLabel {{
    background: transparent;
    color: {c['text_primary']};
    font-size: {f_body}px;
    border: none;
}}

QLabel[class="heading"] {{
    font-size: {f_heading}px;
    font-weight: bold;
}}

QLabel[class="secondary"] {{
    color: {c['text_secondary']};
    font-size: {f_small}px;
}}

QLabel[class="muted"] {{
    color: {c['text_muted']};
    font-size: {f_small}px;
}}

/* ================================================================
   BUTTONS — minimum 60×60px, rounded, hover/press states
   ================================================================ */
QPushButton {{
    background-color: {c['button_neutral']};
    color: {c['text_primary']};
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: {f_button}px;
    min-height: 44px;
    min-width: 60px;
}}

QPushButton:hover {{
    background-color: {_lighten(c['button_neutral'], 15)};
}}

QPushButton:pressed {{
    background-color: {_darken(c['button_neutral'], 10)};
}}

QPushButton:disabled {{
    background-color: {c['border_color']};
    color: {c['text_muted']};
}}

/* Confirm / action button */
QPushButton[class="confirm"],
QPushButton#confirmBtn {{
    background-color: {c['button_confirm']};
}}

QPushButton[class="confirm"]:hover,
QPushButton#confirmBtn:hover {{
    background-color: {_lighten(c['button_confirm'], 12)};
}}

QPushButton[class="confirm"]:pressed,
QPushButton#confirmBtn:pressed {{
    background-color: {_darken(c['button_confirm'], 10)};
}}

/* Danger / cancel button */
QPushButton[class="danger"],
QPushButton#cancelBtn {{
    background-color: {c['button_cancel']};
}}

QPushButton[class="danger"]:hover,
QPushButton#cancelBtn:hover {{
    background-color: {_lighten(c['button_cancel'], 12)};
}}

QPushButton[class="danger"]:pressed,
QPushButton#cancelBtn:pressed {{
    background-color: {_darken(c['button_cancel'], 10)};
}}

/* Accent / info button */
QPushButton[class="accent"] {{
    background-color: {c['accent_blue']};
}}

QPushButton[class="accent"]:hover {{
    background-color: {_lighten(c['accent_blue'], 12)};
}}

/* ================================================================
   INPUT FIELDS — large touch targets, focus glow
   ================================================================ */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {c['input_bg']};
    color: {c['text_primary']};
    border: 2px solid {c['border_color']};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: {f_body}px;
    min-height: 40px;
    selection-background-color: {c['accent_blue']};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {c['accent_blue']};
}}

/* ================================================================
   COMBO BOX
   ================================================================ */
QComboBox {{
    background-color: {c['input_bg']};
    color: {c['text_primary']};
    border: 2px solid {c['border_color']};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: {f_body}px;
    min-height: 40px;
}}

QComboBox:focus {{
    border-color: {c['accent_blue']};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox QAbstractItemView {{
    background-color: {c['secondary_bg']};
    color: {c['text_primary']};
    border: 1px solid {c['border_color']};
    selection-background-color: {c['accent_blue']};
    padding: 4px;
}}

/* ================================================================
   SCROLL BARS — slim dark
   ================================================================ */
QScrollBar:vertical {{
    background: {c['primary_bg']};
    width: 8px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {c['border_color']};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['text_muted']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {c['primary_bg']};
    height: 8px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {c['border_color']};
    border-radius: 4px;
    min-width: 30px;
}}

/* ================================================================
   FRAMES & PANELS — card style
   ================================================================ */
QFrame[class="card"] {{
    background-color: {c['secondary_bg']};
    border: 1px solid {c['border_color']};
    border-radius: 10px;
    padding: 12px;
}}

QFrame[class="panel"] {{
    background-color: {c['secondary_bg']};
    border: none;
    border-radius: 8px;
    padding: 8px;
}}

/* ================================================================
   DIALOG OVERLAY
   ================================================================ */
QDialog {{
    background-color: {c['secondary_bg']};
    border: 1px solid {c['border_color']};
    border-radius: 12px;
}}

/* ================================================================
   TAB BAR
   ================================================================ */
QTabWidget::pane {{
    border: none;
    background: {c['primary_bg']};
}}

QTabBar::tab {{
    background: {c['secondary_bg']};
    color: {c['text_secondary']};
    border: none;
    padding: 10px 20px;
    font-size: {f_body}px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background: {c['primary_bg']};
    color: {c['text_primary']};
    font-weight: bold;
}}

QTabBar::tab:hover:!selected {{
    background: {_lighten(c['secondary_bg'], 8)};
}}

/* ================================================================
   TOOLTIPS
   ================================================================ */
QToolTip {{
    background-color: {c['secondary_bg']};
    color: {c['text_primary']};
    border: 1px solid {c['border_color']};
    padding: 6px 10px;
    font-size: {f_small}px;
    border-radius: 4px;
}}

/* ================================================================
   STATUS BAR
   ================================================================ */
QStatusBar {{
    background-color: {c['secondary_bg']};
    color: {c['text_secondary']};
    font-size: {f_small}px;
}}
"""


# ============================================================================
# Colour math helpers
# ============================================================================


def _lighten(hex_color: str, amount: int = 10) -> str:
    """Lighten a hex colour by *amount* (0-255 per channel)."""
    hex_color = hex_color.lstrip("#")
    r = min(255, int(hex_color[0:2], 16) + amount)
    g = min(255, int(hex_color[2:4], 16) + amount)
    b = min(255, int(hex_color[4:6], 16) + amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color: str, amount: int = 10) -> str:
    """Darken a hex colour by *amount* (0-255 per channel)."""
    hex_color = hex_color.lstrip("#")
    r = max(0, int(hex_color[0:2], 16) - amount)
    g = max(0, int(hex_color[2:4], 16) - amount)
    b = max(0, int(hex_color[4:6], 16) - amount)
    return f"#{r:02x}{g:02x}{b:02x}"
