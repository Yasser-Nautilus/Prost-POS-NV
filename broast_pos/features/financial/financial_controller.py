"""
Financial controller — coordinates shift lifecycle, expenses, and history.

Acts as the interface between the Financial View and core services.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class FinancialController:
    """Orchestrates financial operations for the Financial View."""

    def __init__(
        self,
        financial_service: FinancialService,
        auth_service: AuthService,
        printer_manager: Optional[Any] = None,
    ) -> None:
        self._financial_svc = financial_service
        self._auth_svc = auth_service
        self._printer = printer_manager

    def get_active_shift(self) -> Optional[Dict[str, Any]]:
        """Return details of the current active shift, if any."""
        try:
            shift = self._financial_svc._financial.get_active_shift()
            if shift is None:
                return None
            return {
                "id": shift.id,
                "opened_by": shift.opened_by,
                "opened_at": shift.opened_at,
                "next_invoice_no": shift.next_invoice_no,
                "is_active": shift.is_active,
                "summary_printed_at": shift.summary_printed_at,
            }
        except Exception as e:
            logger.error("Error fetching active shift: %s", e)
            return None

    def open_shift(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Open a new shift."""
        try:
            shift = self._financial_svc.open_shift(user_id)
            return {
                "id": shift.id,
                "opened_by": shift.opened_by,
                "opened_at": shift.opened_at,
                "next_invoice_no": shift.next_invoice_no,
                "is_active": shift.is_active,
            }
        except Exception as e:
            logger.error("Error opening shift: %s", e)
            raise ValueError(str(e))

    def get_shift_summary(self, shift_id: int) -> Dict[str, Any]:
        """Get live financial summary of a shift."""
        try:
            summary = self._financial_svc.get_shift_summary(shift_id)
            return {
                "total_sales": summary.total_sales,
                "total_expenses": summary.total_expenses,
                "pending_delivery": summary.pending_delivery,
                "pending_dinein": summary.pending_dinein,
                "pending_kitchen": summary.pending_kitchen,
                "expected_cash": summary.expected_cash,
            }
        except Exception as e:
            logger.error("Error getting shift summary: %s", e)
            return {
                "total_sales": 0.0,
                "total_expenses": 0.0,
                "pending_delivery": 0.0,
                "pending_dinein": 0.0,
                "pending_kitchen": 0.0,
                "expected_cash": 0.0,
            }

    def get_expenses(self, shift_id: int) -> List[Dict[str, Any]]:
        """Get list of expenses in a shift."""
        try:
            expenses = self._financial_svc.get_expenses(shift_id)
            return [
                {
                    "id": exp.id,
                    "amount": exp.amount,
                    "description": exp.description,
                    "category": exp.category,
                    "timestamp": exp.timestamp,
                    "user_id": exp.user_id,
                }
                for exp in expenses
            ]
        except Exception as e:
            logger.error("Error fetching expenses: %s", e)
            return []

    def add_expense(
        self,
        shift_id: int,
        amount: float,
        description: str,
        category: str,
        user_id: int,
    ) -> Dict[str, Any]:
        """Record an expense."""
        try:
            exp = self._financial_svc.add_expense(
                shift_id=shift_id,
                amount=amount,
                description=description,
                category=category,
                user_id=user_id,
            )
            return {
                "id": exp.id,
                "amount": exp.amount,
                "description": exp.description,
                "category": exp.category,
                "timestamp": exp.timestamp,
            }
        except Exception as e:
            logger.error("Error adding expense: %s", e)
            raise ValueError(str(e))

    def get_users_for_transfer(self) -> List[Dict[str, Any]]:
        """Get list of cashiers and managers for shift transfer dropdown."""
        try:
            users = self._auth_svc.get_all_users()
            return [
                {"id": u.id, "display_name": u.display_name, "role": u.role.value}
                for u in users
            ]
        except Exception as e:
            logger.error("Error listing users for transfer: %s", e)
            return []

    def transfer_shift(
        self,
        from_user_id: int,
        to_user_id: int,
        manager_pin: Optional[str] = None,
    ) -> bool:
        """Perform a mid-day cashier transfer."""
        try:
            transfer_obj = self._financial_svc.transfer_shift(
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                manager_pin=manager_pin,
            )
            # Try to print shift transfer report
            if self._printer:
                try:
                    import json
                    snapshot = json.loads(transfer_obj.summary_snapshot)

                    # Get cashier display names
                    from_user = self._auth_svc._users.get_by_id(from_user_id)
                    to_user = self._auth_svc._users.get_by_id(to_user_id)
                    from_name = from_user.display_name if from_user else f"#{from_user_id}"
                    to_name = to_user.display_name if to_user else f"#{to_user_id}"

                    transfer_data = {
                        "from_cashier": from_name,
                        "to_cashier": to_name,
                        "total_sales": snapshot.get("total_sales", 0.0),
                        "total_expenses": snapshot.get("total_expenses", 0.0),
                        "pending_delivery": snapshot.get("pending_delivery", 0.0),
                        "pending_dinein": snapshot.get("pending_dinein", 0.0),
                        "pending_kitchen": snapshot.get("pending_kitchen", 0.0),
                        "expected_cash": snapshot.get("expected_cash", 0.0),
                    }

                    current_user = self._auth_svc.get_current_user()
                    cashier_slot = current_user.cashier_slot if (current_user and current_user.cashier_slot) else 1

                    self._printer.print_shift_transfer(transfer_data, cashier_slot=cashier_slot)
                except Exception as pe:
                    logger.warning("Failed to print shift transfer report: %s", pe)
            return True
        except Exception as e:
            logger.error("Error transferring shift: %s", e)
            raise ValueError(str(e))

    def close_shift(self, shift_id: int, manager_pin: Optional[str] = None) -> bool:
        """Close the active shift."""
        try:
            self._financial_svc.close_shift(shift_id, manager_pin)
            return True
        except Exception as e:
            logger.error("Error closing shift: %s", e)
            raise ValueError(str(e))

    def get_shift_history(self) -> List[Dict[str, Any]]:
        """Get past shifts."""
        try:
            shifts = self._financial_svc.get_shift_history()
            return [
                {
                    "id": s.id,
                    "opened_by": s.opened_by,
                    "closed_by": s.closed_by,
                    "opened_at": s.opened_at,
                    "closed_at": s.closed_at,
                    "is_active": s.is_active,
                }
                for s in shifts
            ]
        except Exception as e:
            logger.error("Error fetching shift history: %s", e)
            return []
