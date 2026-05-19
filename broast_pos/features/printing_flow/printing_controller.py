"""
Printing flow controller — routes print events to the correct templates.

This controller bridges the feature layer with the infrastructure/printing
subsystem. It subscribes to order and delivery events and ensures every
document prints silently, automatically, and to the correct printer.

All 5 print types:
  1. Kitchen ticket → shared kitchen printer
  2. Customer receipt (4 variants) → cashier-specific printer
  3. Daily summary → cashier-specific printer
  4. Driver settlement → cashier-specific printer
  5. Failure handling → log + UI badge (never block)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from broast_pos.infrastructure.printing.printer_manager import PrinterManager
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers

logger = logging.getLogger(__name__)


class PrintingFlowController:
    """Coordinates all print events in the POS system.

    This is a thin wrapper that provides:
    - A unified API for the feature layer to trigger prints
    - Health monitoring of printer connections
    - Failure tracking for UI badge indicators
    """

    def __init__(
        self,
        printer_manager: PrinterManager,
        print_triggers: PrintTriggers,
    ) -> None:
        self._manager = printer_manager
        self._triggers = print_triggers
        self._failure_count: int = 0
        self._last_error: str = ""
        self._on_print_failure: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_print_failure(self, callback: Callable[[str], None]) -> None:
        """Register callback for print failure notifications (UI badge)."""
        self._on_print_failure = callback

    # ------------------------------------------------------------------
    # 1. Kitchen Ticket
    # ------------------------------------------------------------------

    def print_kitchen_ticket(self, order_dict: Dict[str, Any]) -> bool:
        """Print kitchen ticket for a new or amended order.

        Routes to shared kitchen printer. Silent — never blocks.
        """
        try:
            self._triggers.on_order_created(order_dict)
            logger.info("Kitchen ticket printed for order #%s", order_dict.get("invoice_no"))
            return True
        except Exception as exc:
            self._record_failure(f"Kitchen ticket: {exc}")
            return False

    def print_amendment_ticket(
        self,
        order_dict: Dict[str, Any],
        changes: List[Dict[str, Any]],
    ) -> bool:
        """Print amendment (تابع) kitchen ticket.

        Only actual changes are printed — no fixed headers.
        """
        try:
            self._triggers.on_order_amended(order_dict, changes)
            logger.info("Amendment ticket printed for order #%s", order_dict.get("invoice_no"))
            return True
        except Exception as exc:
            self._record_failure(f"Amendment ticket: {exc}")
            return False

    # ------------------------------------------------------------------
    # 2. Customer Receipt (4 variants)
    # ------------------------------------------------------------------

    def print_customer_receipt(
        self,
        order_dict: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print customer receipt on cashier-specific printer.

        The template auto-selects the variant based on order_type:
        - Dine-in, Takeaway, Pickup, Delivery (cash/online)
        """
        try:
            self._triggers.on_order_completed(order_dict, cashier_slot)
            logger.info(
                "Customer receipt printed for order #%s on slot %d",
                order_dict.get("invoice_no"),
                cashier_slot,
            )
            return True
        except Exception as exc:
            self._record_failure(f"Customer receipt: {exc}")
            return False

    # ------------------------------------------------------------------
    # 3. Daily Summary Receipt
    # ------------------------------------------------------------------

    def print_daily_summary(
        self,
        summary_data: Dict[str, Any],
        cashier_slot: int = 1,
        shift_period: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Print end-of-shift summary receipt.

        Triggered manually by manager from Reports view.
        """
        try:
            self._triggers.on_shift_close(summary_data, cashier_slot, shift_period)
            logger.info("Daily summary printed on slot %d", cashier_slot)
            return True
        except Exception as exc:
            self._record_failure(f"Daily summary: {exc}")
            return False

    # ------------------------------------------------------------------
    # 4. Driver Settlement Receipt
    # ------------------------------------------------------------------

    def print_settlement_receipt(
        self,
        settlement_data: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Print per-trip settlement receipt for driver accountability.

        Shows cash/online breakdown per order and amount to hand over.
        """
        try:
            self._triggers.on_driver_settled(settlement_data, cashier_slot)
            logger.info("Settlement receipt printed on slot %d", cashier_slot)
            return True
        except Exception as exc:
            self._record_failure(f"Settlement receipt: {exc}")
            return False

    # ------------------------------------------------------------------
    # 5. Failure Handling
    # ------------------------------------------------------------------

    def check_printer_health(self) -> Dict[str, bool]:
        """Test all printer connections on startup.

        Returns:
            Dict mapping printer names to their online status.
        """
        status = {}
        for name in ["kitchen", "cashier_1", "cashier_2"]:
            try:
                online = self._manager.is_printer_available(name)
                status[name] = online
                if not online:
                    logger.warning("Printer '%s' is offline", name)
            except Exception:
                status[name] = False
        return status

    @property
    def failure_count(self) -> int:
        """Number of print failures since last reset."""
        return self._failure_count

    @property
    def last_error(self) -> str:
        """Last print error message."""
        return self._last_error

    def reset_failures(self) -> None:
        """Reset failure counter (after user acknowledges)."""
        self._failure_count = 0
        self._last_error = ""

    def _record_failure(self, message: str) -> None:
        """Record a print failure and notify UI."""
        self._failure_count += 1
        self._last_error = message
        logger.error("Print failure #%d: %s", self._failure_count, message)
        if self._on_print_failure:
            self._on_print_failure(message)

    # ------------------------------------------------------------------
    # Reprint
    # ------------------------------------------------------------------

    def reprint_receipt(
        self,
        order_dict: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Reprint a customer receipt (e.g. customer lost their copy)."""
        return self.print_customer_receipt(order_dict, cashier_slot)
