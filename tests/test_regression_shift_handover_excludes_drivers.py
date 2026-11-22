"""
Regression tests — shift handover must not accept delivery drivers.

Root cause: get_users_for_transfer() returned all active users; the frontend
filter (role == "cashier") passed drivers because drivers are cashier-role
users with cashier_slot = NULL.

Fixes:
  1. get_users_for_transfer() now filters to cashier_slot IS NOT NULL.
  2. FinancialService.transfer_shift() rejects a to_user_id whose
     cashier_slot is None (fail-closed backend guard).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from broast_pos.core.models.financial import Shift
from broast_pos.core.models.user import User, UserRole
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.features.financial.financial_controller import FinancialController

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_db():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _make_user(
    *,
    user_id: int,
    role: UserRole = UserRole.CASHIER,
    cashier_slot: int | None,
) -> User:
    return User(
        id=user_id,
        username=f"user{user_id}",
        display_name=f"User {user_id}",
        pin_hash=f"hash{user_id}",
        role=role,
        cashier_slot=cashier_slot,
        is_active=True,
    )


def _active_shift() -> Shift:
    return Shift(
        id=1,
        opened_by=10,
        opened_at="2026-11-22T08:00:00",
        is_active=True,
        summary_printed_at="2026-11-22T09:00:00",
    )


def _financial_svc(*, to_user: User) -> FinancialService:
    """Minimal FinancialService wired for transfer_shift tests."""
    fin_repo = MagicMock()
    fin_repo.get_active_shift.return_value = _active_shift()
    fin_repo.get_shift_summary.return_value = MagicMock(
        total_sales=0.0,
        cash_sales=0.0,
        total_expenses=0.0,
        pending_delivery=0.0,
        pending_dinein=0.0,
        pending_kitchen=0.0,
        expected_cash=0.0,
    )
    fin_repo.save_transfer.return_value = MagicMock()

    auth_svc = MagicMock()
    auth_svc.get_user_by_id.return_value = to_user

    audit_svc = MagicMock()

    svc = FinancialService.__new__(FinancialService)
    svc._financial = fin_repo
    svc._delivery = MagicMock()
    svc._audit = audit_svc
    svc._auth = auth_svc
    svc._verify_manager_pin = MagicMock(return_value=MagicMock(id=99, display_name="Manager"))

    return svc


# ---------------------------------------------------------------------------
# 1. FinancialController.get_users_for_transfer() — list filtering
# ---------------------------------------------------------------------------

class TestGetUsersForTransferList:
    """The transfer list must only include register-operating users."""

    def _fresh_db_with_users(self) -> DatabaseConnection:
        db = DatabaseConnection(":memory:")
        initialise_database(db)
        users = [
            (1, "cashier_slot1", "cashier", 1),   # eligible
            (2, "cashier_slot2", "cashier", 2),   # eligible
            (3, "driver_a",      "cashier", None), # driver — excluded
            (4, "driver_b",      "cashier", None), # driver — excluded
            (5, "mgr",           "manager", None), # manager, no slot — excluded
            (6, "admin",         "admin",   None), # admin, no slot — excluded
        ]
        for uid, uname, role, slot in users:
            db.execute(
                """INSERT INTO users
                       (id, username, display_name, pin_hash, role, cashier_slot, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, 1)""",
                (uid, uname, uname, f"h{uid}", role, slot),
            )
        return db

    def _make_ctrl(self, db: DatabaseConnection) -> FinancialController:
        from broast_pos.core.services.auth_service import AuthService
        from broast_pos.data.repositories.user_repository import UserRepository
        user_repo = UserRepository(db)
        auth_svc = AuthService(user_repo=user_repo)
        ctrl = FinancialController.__new__(FinancialController)
        ctrl._auth_svc = auth_svc
        return ctrl

    def test_drivers_excluded_from_transfer_list(self):
        db = self._fresh_db_with_users()
        ctrl = self._make_ctrl(db)
        result = ctrl.get_users_for_transfer()
        ids = [u["id"] for u in result]
        assert 3 not in ids  # driver_a
        assert 4 not in ids  # driver_b

    def test_manager_no_slot_excluded(self):
        db = self._fresh_db_with_users()
        ctrl = self._make_ctrl(db)
        result = ctrl.get_users_for_transfer()
        ids = [u["id"] for u in result]
        assert 5 not in ids  # manager without slot

    def test_register_cashiers_included(self):
        db = self._fresh_db_with_users()
        ctrl = self._make_ctrl(db)
        result = ctrl.get_users_for_transfer()
        ids = [u["id"] for u in result]
        assert 1 in ids
        assert 2 in ids

    def test_cashier_slot_field_present_in_result(self):
        db = self._fresh_db_with_users()
        ctrl = self._make_ctrl(db)
        result = ctrl.get_users_for_transfer()
        for u in result:
            assert u["cashier_slot"] is not None


# ---------------------------------------------------------------------------
# 2. FinancialService.transfer_shift() — fail-closed backend guard
# ---------------------------------------------------------------------------

class TestTransferShiftDriverGuard:
    """transfer_shift() must reject driver users as handover target."""

    def test_raises_when_target_is_driver(self):
        driver = _make_user(user_id=3, role=UserRole.CASHIER, cashier_slot=None)
        svc = _financial_svc(to_user=driver)
        with pytest.raises(ValueError, match="سائق توصيل"):
            svc.transfer_shift(from_user_id=10, to_user_id=3, manager_pin="1234")

    def test_raises_when_target_user_not_found(self):
        svc = _financial_svc(to_user=None)  # type: ignore[arg-type]
        svc._auth.get_user_by_id.return_value = None
        with pytest.raises(ValueError, match="سائق توصيل"):
            svc.transfer_shift(from_user_id=10, to_user_id=99, manager_pin="1234")

    def test_succeeds_when_target_has_cashier_slot(self):
        register_cashier = _make_user(user_id=2, role=UserRole.CASHIER, cashier_slot=1)
        svc = _financial_svc(to_user=register_cashier)
        # Should not raise
        svc.transfer_shift(from_user_id=10, to_user_id=2, manager_pin="1234")
        svc._financial.save_transfer.assert_called_once()

    def test_no_shift_state_mutated_on_rejection(self):
        driver = _make_user(user_id=3, role=UserRole.CASHIER, cashier_slot=None)
        svc = _financial_svc(to_user=driver)
        with pytest.raises(ValueError):
            svc.transfer_shift(from_user_id=10, to_user_id=3, manager_pin="1234")
        svc._financial.save_transfer.assert_not_called()
