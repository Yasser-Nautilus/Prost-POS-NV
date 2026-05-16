"""
Silent printing flow — zero-dialog, event-driven print triggers.

Connects service-layer events to :class:`PrinterManager` print jobs.
**No Qt print dialog ever.** If a printer is unavailable, the failure
is logged and the cashier continues working.

Usage:
    At app startup, create a ``PrintTriggers`` instance with references
    to the ``PrinterManager`` and services, then call the appropriate
    method after each service action.

Trigger points:
    create_order   → kitchen ticket
    amend_order    → amendment kitchen ticket (تابع)
    complete_order → customer receipt
    transfer_shift → shift transfer report
    close_shift    → end-of-day sales report
    settle_driver  → driver settlement receipt
    end_of_day     → driver summary
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from broast_pos.infrastructure.printing.printer_manager import PrinterManager

logger = logging.getLogger(__name__)


class PrintTriggers:
    """Event-driven print trigger layer.

    Each method corresponds to a service action and silently fires
    the appropriate print job.  Failures are logged, never raised.
    """

    def __init__(self, printer_manager: PrinterManager) -> None:
        self._pm = printer_manager

    # ------------------------------------------------------------------
    # Order lifecycle triggers
    # ------------------------------------------------------------------

    def on_order_created(
        self,
        order: Dict[str, Any],
    ) -> bool:
        """Triggered after ``order_service.create_order()``.

        Prints a kitchen ticket to the shared kitchen printer.
        """
        logger.info("Print trigger: kitchen ticket for order #%s", order.get("invoice_no"))
        return self._pm.print_kitchen_ticket_job(order)

    def on_order_amended(
        self,
        order: Dict[str, Any],
        changes: List[Dict[str, Any]],
    ) -> bool:
        """Triggered after ``order_service.amend_order()``.

        Prints an amendment kitchen ticket (تابع) showing only the changes.
        """
        if not changes:
            logger.debug("No changes to print for order #%s", order.get("invoice_no"))
            return True

        logger.info("Print trigger: amendment ticket for order #%s", order.get("invoice_no"))
        return self._pm.print_amendment_ticket_job(order, changes)

    def on_order_completed(
        self,
        order: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Triggered after ``order_service.complete_order()``.

        Prints a customer receipt to the cashier's printer.
        """
        logger.info("Print trigger: receipt for order #%s → slot %d", order.get("invoice_no"), cashier_slot)
        return self._pm.print_receipt(order, cashier_slot)

    # ------------------------------------------------------------------
    # Shift lifecycle triggers
    # ------------------------------------------------------------------

    def on_shift_transfer(
        self,
        transfer: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Triggered after ``financial_service.transfer_shift()``.

        Prints the shift transfer report to the cashier's printer.
        """
        logger.info("Print trigger: shift transfer report → slot %d", cashier_slot)
        return self._pm.print_shift_transfer(transfer, cashier_slot)

    def on_shift_close(
        self,
        report: Dict[str, Any],
        cashier_slot: int = 1,
        shift_period: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Triggered on shift close / daily summary print.

        Prints the end-of-day sales report to the cashier's printer.
        Must be called at least once before shift close is allowed.
        """
        logger.info("Print trigger: daily sales report → slot %d", cashier_slot)
        return self._pm.print_shift_summary(report, cashier_slot, shift_period)

    # ------------------------------------------------------------------
    # Driver triggers
    # ------------------------------------------------------------------

    def on_driver_settled(
        self,
        settlement: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Triggered after ``delivery_service.settle_trip()``.

        Prints the driver settlement receipt.
        """
        logger.info(
            "Print trigger: driver settlement (%s) → slot %d",
            settlement.get("driver_name"),
            cashier_slot,
        )
        return self._pm.print_driver_settlement_job(settlement, cashier_slot)

    def on_end_of_day_drivers(
        self,
        summary: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Triggered at end of day to print driver summary.

        Shows all drivers with trip/order/fee totals.
        """
        logger.info("Print trigger: driver summary → slot %d", cashier_slot)
        return self._pm.print_driver_summary_job(summary, cashier_slot)

    # ------------------------------------------------------------------
    # Manual reprint (from Reports View)
    # ------------------------------------------------------------------

    def reprint_receipt(
        self,
        order: Dict[str, Any],
        cashier_slot: int = 1,
    ) -> bool:
        """Manual reprint of a customer receipt from Reports View."""
        logger.info("Print trigger: reprint receipt for order #%s → slot %d", order.get("invoice_no"), cashier_slot)
        return self._pm.print_receipt(order, cashier_slot)
