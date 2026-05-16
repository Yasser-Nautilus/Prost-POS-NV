"""
ESC/POS adapter — low-level thermal printer communication.

Wraps ``python-escpos`` to provide a unified interface across USB,
Network, Serial, and Dummy printer connections.  Arabic encoding is
handled automatically (UTF-8 → printer codepage).

Auto-reconnect on connection loss; **never raises** — returns False
on failure so the cashier is never blocked.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from broast_pos.infrastructure.printing.printer_config import PrinterEntry

logger = logging.getLogger(__name__)

# python-escpos is optional — may not be installed in dev environments
try:
    from escpos.printer import Dummy, Network, Serial, Usb
    ESCPOS_AVAILABLE = True
except ImportError:
    ESCPOS_AVAILABLE = False
    logger.warning("python-escpos not installed — printing will use dummy mode")


class EscPosPrinter:
    """Manages a single ESC/POS thermal printer connection.

    Thread-safe: all operations are guarded by a lock.
    """

    def __init__(self, entry: PrinterEntry) -> None:
        self._entry = entry
        self._printer = None
        self._lock = threading.Lock()
        self._connected = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Establish connection to the printer.

        Returns:
            True if connected successfully, False otherwise.
        """
        with self._lock:
            return self._connect_unsafe()

    def _connect_unsafe(self) -> bool:
        """Internal connect — caller must hold the lock."""
        if not ESCPOS_AVAILABLE:
            self._printer = _DummyPrinter()
            self._connected = True
            logger.info("[%s] Using built-in dummy printer (escpos not installed)", self._entry.key)
            return True

        try:
            if self._entry.conn_type == "usb":
                vid = int(self._entry.vendor_id, 16) if self._entry.vendor_id else 0
                pid = int(self._entry.product_id, 16) if self._entry.product_id else 0
                self._printer = Usb(vid, pid)
            elif self._entry.conn_type == "network":
                self._printer = Network(
                    self._entry.host or "127.0.0.1",
                    port=self._entry.port,
                )
            elif self._entry.conn_type == "serial":
                self._printer = Serial(self._entry.device or "/dev/ttyUSB0")
            elif self._entry.conn_type == "dummy":
                self._printer = Dummy()
            else:
                logger.error("[%s] Unknown printer type: %s", self._entry.key, self._entry.conn_type)
                self._printer = Dummy()

            self._connected = True
            logger.info("[%s] Connected (%s)", self._entry.key, self._entry.conn_type)
            return True

        except Exception as exc:
            logger.error("[%s] Connection failed: %s", self._entry.key, exc)
            self._connected = False
            self._printer = None
            return False

    def disconnect(self) -> None:
        """Close the printer connection gracefully."""
        with self._lock:
            if self._printer is not None:
                try:
                    self._printer.close()
                except Exception:
                    pass
            self._printer = None
            self._connected = False

    @property
    def is_connected(self) -> bool:
        """Whether the printer is currently connected."""
        return self._connected

    # ------------------------------------------------------------------
    # Printing operations — NEVER raise
    # ------------------------------------------------------------------

    def print_raw(self, data: bytes) -> bool:
        """Send raw bytes to the printer.

        Returns:
            True on success, False on failure.
        """
        with self._lock:
            return self._ensure_and_exec(lambda p: p._raw(data))

    def print_text(
        self,
        text: str,
        *,
        align: str = "left",
        bold: bool = False,
        double_width: bool = False,
        double_height: bool = False,
    ) -> bool:
        """Print formatted text.

        Args:
            text: The text to print (Arabic supported).
            align: ``"left"`` | ``"center"`` | ``"right"``
            bold: Bold text.
            double_width: Double character width.
            double_height: Double character height.

        Returns:
            True on success.
        """
        def _do(p):
            p.set(
                align=align,
                bold=bold,
                double_width=double_width,
                double_height=double_height,
            )
            p.text(text + "\n")

        with self._lock:
            return self._ensure_and_exec(_do)

    def print_line(self, char: str = "-", width: int = 32) -> bool:
        """Print a separator line."""
        return self.print_text(char * width, align="center")

    def print_double_line(self, width: int = 32) -> bool:
        """Print a double separator line."""
        return self.print_text("=" * width, align="center")

    def feed(self, lines: int = 1) -> bool:
        """Feed paper by N lines."""
        with self._lock:
            return self._ensure_and_exec(lambda p: p.ln(lines))

    def cut(self) -> bool:
        """Cut the paper."""
        with self._lock:
            return self._ensure_and_exec(lambda p: p.cut())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_and_exec(self, action) -> bool:
        """Auto-reconnect if needed, then execute action.

        Must be called with ``self._lock`` held.
        """
        if self._printer is None or not self._connected:
            if not self._connect_unsafe():
                return False
        try:
            action(self._printer)
            return True
        except Exception as exc:
            logger.error("[%s] Print error: %s — attempting reconnect", self._entry.key, exc)
            self._connected = False
            # One retry after reconnect
            if self._connect_unsafe():
                try:
                    action(self._printer)
                    return True
                except Exception as retry_exc:
                    logger.error("[%s] Retry failed: %s", self._entry.key, retry_exc)
            return False


class _DummyPrinter:
    """Minimal stand-in when python-escpos is not installed."""

    def set(self, **kwargs):
        pass

    def text(self, txt: str):
        logger.debug("[DummyPrinter] %s", txt.strip())

    def ln(self, count: int = 1):
        pass

    def cut(self):
        logger.debug("[DummyPrinter] --- CUT ---")

    def close(self):
        pass

    def _raw(self, data: bytes):
        pass
