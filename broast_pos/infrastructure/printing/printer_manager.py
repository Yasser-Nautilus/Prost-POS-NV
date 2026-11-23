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

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from broast_pos.config.config import (
    PRINTER_SIMULATE,
    PRINTER_SIMULATE_OUTPUT_DIR,
    is_production,
)
from broast_pos.infrastructure.printing.escpos_printer import EscPosPrinter
from broast_pos.infrastructure.printing.printer_config import (
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
        self._printers: dict[str, EscPosPrinter] = {}
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

    def get_status(self) -> dict[str, bool]:
        """H14: readiness of every configured printer, keyed by role.

        Exposes what initialise() connected (or failed to connect) so a
        caller — the bridge, a UI badge, a health check — can see printer
        readiness instead of only discovering it on the first failed print.
        """
        return {key: printer.is_connected for key, printer in self._printers.items()}

    # ------------------------------------------------------------------
    # Simulate mode
    # ------------------------------------------------------------------

    def _simulate_print(self, job: str, data: dict[str, Any]) -> bool:
        """Write a simulated print record to printouts/ and return True.

        Called instead of the real hardware path when PROST_PRINTER_SIMULATE=1.
        The file is JSON with a local-time timestamp in the filename so it
        is easy to find after a test run.
        """
        if is_production():
            logger.error("Simulated printing is forbidden in production")
            return False
        try:
            out_dir = Path(PRINTER_SIMULATE_OUTPUT_DIR)
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = out_dir / f"{ts}_{job}.json"
            payload = {"job": job, "printed_at": datetime.now().isoformat(), "data": data}
            filename.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("[SIMULATE] %s → %s", job, filename.name)
            return True
        except Exception as exc:
            logger.error("[SIMULATE] Failed to write simulated output for %s: %s", job, exc)
            return False

    # ------------------------------------------------------------------
    # Print jobs — NEVER raise
    # ------------------------------------------------------------------

    def print_kitchen_ticket_job(self, order: dict[str, Any]) -> bool:
        """Print kitchen ticket → always routes to kitchen printer.

        Thread-safe: kitchen lock prevents interleaved output from
        simultaneous cashier orders.
        """
        if PRINTER_SIMULATE:
            return self._simulate_print("kitchen_ticket", order)

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
        order: dict[str, Any],
        changes: list[dict[str, Any]],
    ) -> bool:
        """Print amendment kitchen ticket (تابع) → kitchen printer."""
        if PRINTER_SIMULATE:
            return self._simulate_print("amendment_ticket", {"order": order, "changes": changes})

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
        order: dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print customer receipt → routes to correct cashier printer.

        Args:
            order: Order data dict.
            cashier_slot: 1 or 2.
        """
        if PRINTER_SIMULATE:
            return self._simulate_print(f"receipt_slot{cashier_slot}", order)

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
        report: dict[str, Any],
        cashier_slot: int = 1,
        shift_period: dict[str, str] | None = None,
    ) -> bool:
        """Print end-of-day sales report → cashier printer."""
        if PRINTER_SIMULATE:
            return self._simulate_print(
                "shift_summary", {"report": report, "shift_period": shift_period}
            )

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
        transfer: dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print shift transfer report → cashier printer."""
        if PRINTER_SIMULATE:
            return self._simulate_print("shift_transfer", transfer)

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
        settlement: dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print driver settlement receipt → cashier printer."""
        if PRINTER_SIMULATE:
            return self._simulate_print("driver_settlement", settlement)

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
        summary: dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print end-of-day driver summary → cashier printer."""
        if PRINTER_SIMULATE:
            return self._simulate_print("driver_summary", summary)

        key = _SLOT_MAP.get(cashier_slot, CASHIER_1)
        printer = self._printers.get(key)
        if printer is None:
            return False

        try:
            return print_driver_summary(printer, summary)
        except Exception as exc:
            logger.error("Driver summary print failed: %s", exc)
            return False
