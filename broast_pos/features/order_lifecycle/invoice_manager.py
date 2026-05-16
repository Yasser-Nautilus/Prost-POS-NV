"""
Invoice number management — race-safe sequential numbering.

Wraps FinancialService.get_next_invoice_number() with additional
formatting and reset logic. Invoice numbers:
  - Start at #1 each shift
  - Are assigned at **save** time (not pay time)
  - Are race-safe via atomic DB UPDATE ... RETURNING
"""

from __future__ import annotations

import logging

from broast_pos.core.services.financial_service import FinancialService

logger = logging.getLogger(__name__)


class InvoiceManager:
    """Thread-safe invoice number dispenser.

    Delegates to FinancialService which uses atomic SQL.
    This class provides display formatting and caching.
    """

    def __init__(self, financial_service: FinancialService) -> None:
        self._financial_svc = financial_service
        self._last_issued: int = 0

    def next_number(self) -> int:
        """Get the next sequential invoice number.

        Uses atomic DB operation to prevent duplicates
        with concurrent cashiers.

        Returns:
            Integer invoice number.

        Raises:
            RuntimeError: If no active shift exists.
        """
        number = self._financial_svc.get_next_invoice_number()
        self._last_issued = number
        logger.debug("Issued invoice #%d", number)
        return number

    @property
    def last_issued(self) -> int:
        """Last issued invoice number in this session."""
        return self._last_issued

    @staticmethod
    def format_display(invoice_no: int, pad: int = 3) -> str:
        """Format invoice number for display.

        Args:
            invoice_no: The integer invoice number.
            pad: Zero-padding width (default 3 → #001).

        Returns:
            Formatted string like '#001'.
        """
        return f"#{str(invoice_no).zfill(pad)}"

    @staticmethod
    def format_receipt(invoice_no: int) -> str:
        """Format invoice number for receipt printing.

        Returns:
            Plain integer string (no padding, no #).
        """
        return str(invoice_no)
