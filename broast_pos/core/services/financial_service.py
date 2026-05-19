"""
Financial service — shift lifecycle, expenses, invoice counter, and guard.

Only one shift active at a time. Invoice counter resets to #1 on open_shift.
Expenses are immutable. Shift close requires manager PIN + all drivers settled.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from broast_pos.core.models.financial import (
    CashTransaction,
    Shift,
    ShiftSummary,
    ShiftTransfer,
)
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.audit_repository import AuditRepository

if TYPE_CHECKING:
    from broast_pos.core.services.auth_service import AuthService
    from broast_pos.core.services.delivery_service import DeliveryService


class FinancialService:
    """Business logic for shift management, expenses, and invoicing."""

    def __init__(
        self,
        financial_repo: Optional[FinancialRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        auth_service: Optional["AuthService"] = None,
        delivery_service: Optional["DeliveryService"] = None,
    ) -> None:
        self._financial = financial_repo or FinancialRepository()
        self._audit = audit_repo or AuditRepository()
        self._auth = auth_service
        self._delivery = delivery_service

    # ------------------------------------------------------------------
    # Shift guard (called by OrderService before every order)
    # ------------------------------------------------------------------

    def ensure_shift_active(self) -> Shift:
        """Verify that a shift is currently open.

        Returns the active Shift.
        Raises:
            ValueError: if no shift is open — blocks order creation.
        """
        shift = self._financial.get_active_shift()
        if shift is None:
            raise ValueError("يجب فتح وردية أولاً")
        return shift

    # ------------------------------------------------------------------
    # Open shift
    # ------------------------------------------------------------------

    def open_shift(self, user_id: int) -> Shift:
        """Open a new shift — resets invoice counter to #1.

        Any role can open a shift.

        Raises:
            ValueError: if another shift is already active.
        """
        existing = self._financial.get_active_shift()
        if existing is not None:
            raise ValueError("يوجد وردية مفتوحة بالفعل")

        saved = self._financial.open_shift(user_id)

        self._audit.log(
            event_type="shift_opened",
            user_id=user_id,
            user_name="",
            details={"shift_id": saved.id},
        )

        return saved

    # ------------------------------------------------------------------
    # Shift transfer (mid-day handover)
    # ------------------------------------------------------------------

    def transfer_shift(
        self,
        from_user_id: int,
        to_user_id: int,
        manager_pin: str,
    ) -> ShiftTransfer:
        """Transfer the active shift from one user to another.

        Records a snapshot of the current financial state.
        Invoice numbering continues — does NOT reset.
        Requires manager PIN.

        Raises:
            ValueError: if no active shift.
            PermissionError: if PIN is invalid.
        """
        shift = self.ensure_shift_active()

        # Verify manager authorization
        self._verify_manager_pin(manager_pin)

        # Capture current state
        summary = self._financial.get_shift_summary(shift.id)
        snapshot = json.dumps({
            "total_sales": summary.total_sales,
            "total_expenses": summary.total_expenses,
            "pending_delivery": summary.pending_delivery,
            "pending_dinein": summary.pending_dinein,
            "pending_kitchen": summary.pending_kitchen,
            "expected_cash": summary.expected_cash,
        })

        transfer = ShiftTransfer(
            shift_id=shift.id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            timestamp=datetime.now().isoformat(),
            summary_snapshot=snapshot,
        )

        saved = self._financial.save_transfer(
            shift.id, from_user_id, to_user_id,
            json.loads(snapshot),
        )

        self._audit.log(
            event_type="shift_transferred",
            user_id=from_user_id,
            user_name="",
            details={
                "shift_id": shift.id,
                "from_user_id": from_user_id,
                "to_user_id": to_user_id,
            },
        )

        return saved

    # ------------------------------------------------------------------
    # Close shift
    # ------------------------------------------------------------------

    def close_shift(self, shift_id: int, manager_pin: str) -> Shift:
        """Close the shift — manager only, with prerequisites.

        Prerequisites:
          1. All driver trips must be settled
          2. Daily summary must have been printed at least once

        Raises:
            ValueError: if prerequisites not met.
            PermissionError: if PIN is invalid.
        """
        shift = self._financial.get_by_id(shift_id)
        if shift is None or not shift.is_active:
            raise ValueError("الوردية غير موجودة أو مغلقة")

        manager = self._verify_manager_pin(manager_pin)

        # Check prerequisites
        if not shift.can_close():
            raise ValueError(
                "يجب طباعة التقرير اليومي قبل إغلاق الوردية"
            )

        # Check all driver settlements
        if self._delivery:
            active_drivers = self._delivery.get_active_drivers()
            for driver in active_drivers:
                unsettled = self._delivery.get_unsettled_trips(driver.id)
                if unsettled:
                    raise ValueError(
                        f"يوجد رحلات غير محسوبة للسائق {driver.display_name}"
                    )

        # Close it
        shift.is_active = False
        shift.closed_at = datetime.now().isoformat()
        shift.closed_by = manager.id
        saved = self._financial.save(shift)

        self._audit.log(
            event_type="shift_closed",
            user_id=manager.id,
            user_name=manager.display_name,
            details={"shift_id": shift_id},
        )

        return saved

    # ------------------------------------------------------------------
    # Invoice counter
    # ------------------------------------------------------------------

    def get_next_invoice_number(self) -> int:
        """Atomically fetch and increment the invoice counter.

        Returns the next sequential invoice number for the current shift.
        Raises:
            ValueError: if no active shift.
        """
        shift = self.ensure_shift_active()
        return self._financial.get_next_invoice_no(shift.id)

    # ------------------------------------------------------------------
    # Expense entry
    # ------------------------------------------------------------------

    def add_expense(
        self,
        shift_id: int,
        amount: float,
        description: str,
        category: str,
        user_id: int,
    ) -> CashTransaction:
        """Record a cash-out expense. Immutable — cannot be edited or deleted.

        Raises:
            ValueError: if amount is invalid or category is unknown.
        """
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")

        valid_categories = {"delivery_fees", "supplies", "other"}
        if category not in valid_categories:
            raise ValueError(
                f"فئة المصروف غير صحيحة — يجب أن تكون: {', '.join(valid_categories)}"
            )

        transaction = CashTransaction(
            shift_id=shift_id,
            type="expense",
            amount=amount,
            description=description.strip(),
            category=category,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
        )

        saved = self._financial.save_expense(transaction)

        self._audit.log(
            event_type="expense_added",
            user_id=user_id,
            user_name="",
            details={
                "amount": amount,
                "category": category,
                "description": description,
            },
        )

        return saved

    def get_expenses(self, shift_id: int) -> List[CashTransaction]:
        """All expenses for a shift."""
        return self._financial.get_expenses(shift_id)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_shift_summary(self, shift_id: int) -> ShiftSummary:
        """Compute live shift summary (not stored — always fresh)."""
        return self._financial.get_shift_summary(shift_id)

    def mark_summary_printed(self, shift_id: int) -> None:
        """Record that the daily summary was printed (prerequisite for close)."""
        shift = self._financial.get_by_id(shift_id)
        if shift is None:
            raise ValueError("الوردية غير موجودة")
        shift.summary_printed_at = datetime.now().isoformat()
        self._financial.save(shift)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _verify_manager_pin(self, pin: str):
        """Verify manager/admin PIN. Returns the User.

        Raises:
            PermissionError: if PIN is invalid or user lacks role.
        """
        if self._auth is None:
            raise PermissionError("Auth service not configured")
        manager = self._auth.verify_pin(pin)
        if manager is None:
            raise PermissionError("PIN غير صحيح أو ليس لديك صلاحية")
        return manager
