"""
Printer manager — central routing layer.

Decides which physical printer handles each print job.
**Never blocks** the cashier — all failures logged and swallowed.

Routing:
    KITCHEN   → shared kitchen printer (both cashiers send here)
    CASHIER_1 → receipt printer for cashier slot 1
    CASHIER_2 → receipt printer for cashier slot 2
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

from broast_pos.infrastructure.printing.escpos_printer import EscPosPrinter
from broast_pos.infrastructure.printing.printer_config import (
    PrinterEntry,
    load_printer_config,
)
from broast_pos.infrastructure.printing.receipt_templates import (
    print_amendment_ticket,
    print_customer_receipt,
    print_daily_sales_report,
    print_driver_settlement,
    print_driver_summary,
    print_kitchen_ticket,
    print_shift_transfer_report,
)

logger = logging.getLogger(__name__)

# Printer role keys
KITCHEN = "kitchen"
CASHIER_1 = "cashier_1"
CASHIER_2 = "cashier_2"

# Map cashier slot (int) → config key
_SLOT_MAP = {1: CASHIER_1, 2: CASHIER_2}


class PrinterManager:
    """Central print routing — initialised once at app startup.

    Thread-safe: the kitchen printer lock prevents interleaved tickets
    from both cashier devices.
    """

    def __init__(self) -> None:
        self._printers: Dict[str, EscPosPrinter] = {}
        self._kitchen_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialise(self) -> None:
        """Detect and connect to all configured printers.

        Call once at app startup.
        """
        config = load_printer_config()
        for key, entry in config.items():
            printer = EscPosPrinter(entry)
            connected = printer.connect()
            self._printers[key] = printer
            if connected:
                logger.info("Printer [%s] ready", key)
            else:
                logger.warning("Printer [%s] unavailable — will retry on print", key)

    def shutdown(self) -> None:
        """Disconnect all printers gracefully."""
        for key, printer in self._printers.items():
            printer.disconnect()
            logger.info("Printer [%s] disconnected", key)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def is_printer_available(self, key: str) -> bool:
        """Check if a specific printer is connected.

        Used by UI to show warning badge.
        """
        printer = self._printers.get(key)
        return printer is not None and printer.is_connected

    # ------------------------------------------------------------------
    # Print jobs — NEVER raise
    # ------------------------------------------------------------------

    def print_kitchen_ticket_job(self, order: Dict[str, Any]) -> bool:
        """Print kitchen ticket → always routes to kitchen printer.

        Thread-safe: kitchen lock prevents interleaved output from
        simultaneous cashier orders.
        """
        printer = self._printers.get(KITCHEN)
        if printer is None:
            logger.error("Kitchen printer not configured")
            return False

        with self._kitchen_lock:
            try:
                return print_kitchen_ticket(printer, order)
            except Exception as exc:
                logger.error("Kitchen ticket print failed: %s", exc)
                return False

    def print_amendment_ticket_job(
        self,
        order: Dict[str, Any],
        changes: List[Dict[str, Any]],
    ) -> bool:
        """Print amendment kitchen ticket (تابع) → kitchen printer."""
        printer = self._printers.get(KITCHEN)
        if printer is None:
            logger.error("Kitchen printer not configured")
            return False

        with self._kitchen_lock:
            try:
                return print_amendment_ticket(printer, order, changes)
            except Exception as exc:
                logger.error("Amendment ticket print failed: %s", exc)
                return False

    def print_receipt(
        self,
        order: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print customer receipt → routes to correct cashier printer.

        Args:
            order: Order data dict.
            cashier_slot: 1 or 2.
        """
        key = _SLOT_MAP.get(cashier_slot, CASHIER_1)
        printer = self._printers.get(key)
        if printer is None:
            logger.error("Cashier printer [%s] not configured", key)
            return False

        try:
            return print_customer_receipt(printer, order)
        except Exception as exc:
            logger.error("Receipt print failed (slot %d): %s", cashier_slot, exc)
            return False

    def print_shift_summary(
        self,
        report: Dict[str, Any],
        cashier_slot: int = 1,
        shift_period: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Print end-of-day sales report → cashier printer."""
        key = _SLOT_MAP.get(cashier_slot, CASHIER_1)
        printer = self._printers.get(key)
        if printer is None:
            logger.error("Cashier printer [%s] not configured", key)
            return False

        try:
            return print_daily_sales_report(printer, report, shift_period)
        except Exception as exc:
            logger.error("Shift summary print failed: %s", exc)
            return False

    def print_shift_transfer(
        self,
        transfer: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print shift transfer report → cashier printer."""
        key = _SLOT_MAP.get(cashier_slot, CASHIER_1)
        printer = self._printers.get(key)
        if printer is None:
            return False

        try:
            return print_shift_transfer_report(printer, transfer)
        except Exception as exc:
            logger.error("Shift transfer print failed: %s", exc)
            return False

    def print_driver_settlement_job(
        self,
        settlement: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print driver settlement receipt → cashier printer."""
        key = _SLOT_MAP.get(cashier_slot, CASHIER_1)
        printer = self._printers.get(key)
        if printer is None:
            return False

        try:
            return print_driver_settlement(printer, settlement)
        except Exception as exc:
            logger.error("Driver settlement print failed: %s", exc)
            return False

    def print_driver_summary_job(
        self,
        summary: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print end-of-day driver summary → cashier printer."""
        key = _SLOT_MAP.get(cashier_slot, CASHIER_1)
        printer = self._printers.get(key)
        if printer is None:
            return False

        try:
            return print_driver_summary(printer, summary)
        except Exception as exc:
            logger.error("Driver summary print failed: %s", exc)
            return False
