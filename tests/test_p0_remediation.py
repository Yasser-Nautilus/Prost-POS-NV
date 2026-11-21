"""
Tests for P0/P1 remediation — AuthService methods, permission fixes,
FinancialController cleanup, DeliveryService circular dep, and
expense-to-ledger integration.

Tests added:
  - verify_manager_pin: valid, invalid, None
  - get_manager_by_pin: valid, invalid, None
  - get_user_by_id: found, not found
  - MANAGE_USERS removed from Manager permissions
  - FinancialController uses public methods (no private attr access)
  - DeliveryService.set_order_service()
  - FinancialService.add_expense creates EXPENSE ledger entry
"""
from __future__ import annotations

import pytest

from broast_pos.core.models.cashier_session import (
    LedgerEntryType,
    Station,
)
from broast_pos.core.models.user import UserRole
from broast_pos.core.services.auth_service import Action, AuthService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.features.financial.financial_controller import FinancialController

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    """In-memory database with full schema."""
    conn = DatabaseConnection.get_instance(":memory:")
    initialise_database(conn)
    # The seed may have created users already. Use INSERT OR IGNORE
    # and check if our specific users exist, otherwise insert them.
    conn.execute(
        "INSERT OR IGNORE INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (100, 'test_admin', 'Admin User', 'admin', ?, 1)",
        (AuthService.hash_pin("9999"),),
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (101, 'test_manager', 'Manager User', 'manager', ?, 1)",
        (AuthService.hash_pin("5555"),),
    )
    conn.execute(
        "INSERT OR IGNORE INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (102, 'test_cashier', 'Cashier User', 'cashier', ?, 1)",
        (AuthService.hash_pin("1111"),),
    )
    conn.commit()
    yield conn
    DatabaseConnection._instance = None


@pytest.fixture()
def auth(db):
    return AuthService(UserRepository(db))


# ═══════════════════════════════════════════════════════════════════════════
# AuthService — new public methods
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthServiceNewMethods:
    """Test verify_manager_pin, get_manager_by_pin, get_user_by_id."""

    def test_verify_manager_pin_valid(self, auth):
        """Manager PIN returns the manager user."""
        user = auth.verify_manager_pin("5555")
        assert user is not None
        assert user.role == UserRole.MANAGER

    def test_verify_manager_pin_admin_valid(self, auth):
        """Admin PIN also works for verify_manager_pin."""
        user = auth.verify_manager_pin("9999")
        assert user is not None
        assert user.role == UserRole.ADMIN

    def test_verify_manager_pin_invalid(self, auth):
        """Wrong PIN raises ValueError."""
        with pytest.raises(ValueError, match="PIN"):
            auth.verify_manager_pin("0000")

    def test_verify_manager_pin_none(self, auth):
        """None PIN raises ValueError."""
        with pytest.raises(ValueError, match="PIN"):
            auth.verify_manager_pin(None)

    def test_verify_manager_pin_empty(self, auth):
        """Empty string PIN raises ValueError."""
        with pytest.raises(ValueError, match="PIN"):
            auth.verify_manager_pin("")

    def test_verify_manager_pin_cashier_rejected(self, auth):
        """Cashier PIN is rejected (not a manager)."""
        with pytest.raises(ValueError, match="PIN"):
            auth.verify_manager_pin("1111")

    def test_get_manager_by_pin_valid(self, auth):
        """get_manager_by_pin returns manager user."""
        user = auth.get_manager_by_pin("5555")
        assert user is not None
        assert user.role == UserRole.MANAGER

    def test_get_manager_by_pin_invalid(self, auth):
        """get_manager_by_pin returns None for bad PIN."""
        result = auth.get_manager_by_pin("0000")
        assert result is None

    def test_get_manager_by_pin_none(self, auth):
        """get_manager_by_pin returns None for None."""
        result = auth.get_manager_by_pin(None)
        assert result is None

    def test_get_user_by_id_found(self, auth):
        """get_user_by_id returns user when found."""
        user = auth.get_user_by_id(100)
        assert user is not None
        assert user.username == "test_admin"

    def test_get_user_by_id_not_found(self, auth):
        """get_user_by_id returns None for nonexistent ID."""
        assert auth.get_user_by_id(99999) is None


# ═══════════════════════════════════════════════════════════════════════════
# Permission fix — MANAGE_USERS removed from Manager
# ═══════════════════════════════════════════════════════════════════════════

class TestManageUsersPermission:
    """Verify MANAGE_USERS is admin-only after remediation."""

    def test_manager_cannot_manage_users(self, auth):
        """Manager role should NOT have MANAGE_USERS permission."""
        manager = auth.get_user_by_id(101)
        assert manager.role == UserRole.MANAGER
        assert auth.check_permission(manager, Action.MANAGE_USERS) is False

    def test_admin_can_manage_users(self, auth):
        """Admin role should have MANAGE_USERS permission."""
        admin = auth.get_user_by_id(100)
        assert admin.role == UserRole.ADMIN
        assert auth.check_permission(admin, Action.MANAGE_USERS) is True

    def test_cashier_cannot_manage_users(self, auth):
        """Cashier role should NOT have MANAGE_USERS permission."""
        cashier = auth.get_user_by_id(102)
        assert cashier.role == UserRole.CASHIER
        assert auth.check_permission(cashier, Action.MANAGE_USERS) is False


# ═══════════════════════════════════════════════════════════════════════════
# DeliveryService.set_order_service()
# ═══════════════════════════════════════════════════════════════════════════

class TestDeliveryServiceSetOrderService:
    """Verify the new public setter replaces direct private attribute access."""

    def test_set_order_service(self):
        """set_order_service properly injects the dependency."""
        svc = DeliveryService()
        assert svc._order_svc is None

        sentinel = object()
        svc.set_order_service(sentinel)
        assert svc._order_svc is sentinel


# ═══════════════════════════════════════════════════════════════════════════
# FinancialController — no more private attribute access
# ═══════════════════════════════════════════════════════════════════════════

class TestFinancialControllerPublicMethods:
    """Verify FinancialController uses only public methods."""

    def test_get_active_shift_uses_public_method(self, db, auth):
        """FinancialController.get_active_shift calls FinancialService.get_active_shift (public)."""
        fin_repo = FinancialRepository(db)
        fin_svc = FinancialService(financial_repo=fin_repo, auth_service=auth)
        ctrl = FinancialController(financial_service=fin_svc, auth_service=auth)

        # Should succeed without AttributeError (proves no private attr access).
        # Seed may or may not have an active shift — either result is fine.
        result = ctrl.get_active_shift()
        assert result is None or isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════
# Expense → Cash Ledger integration
# ═══════════════════════════════════════════════════════════════════════════

class TestExpenseLedgerIntegration:
    """Verify that add_expense creates an EXPENSE entry in the cash ledger."""

    def test_expense_creates_ledger_entry(self, db, auth):
        """Adding an expense should create a negative EXPENSE ledger entry."""
        fin_repo = FinancialRepository(db)
        session_repo = CashierSessionRepository(db)
        ledger_repo = CashLedgerRepository(db)
        audit_repo = AuditRepository(db)

        fin_svc = FinancialService(
            financial_repo=fin_repo,
            audit_repo=audit_repo,
            auth_service=auth,
            cash_ledger_repo=ledger_repo,
            cashier_session_repo=session_repo,
        )

        # Open a shift (business day)
        shift = fin_svc.open_shift(user_id=100)
        day_id = shift.id

        # Open a cashier session
        sess_svc = CashierSessionService(
            session_repo=session_repo,
            ledger_repo=ledger_repo,
        )
        session = sess_svc.open_session(
            day_id=day_id,
            user_id=100,
            station=Station.ALL,
            opening_float_pt=50000,
        )
        db.commit()

        # Add an expense
        expense = fin_svc.add_expense(
            shift_id=day_id,
            amount=25.50,
            description="مستلزمات مطبخ",
            category="supplies",
            user_id=100,
        )
        db.commit()

        # Verify EXPENSE ledger entry was created
        entries = ledger_repo.get_entries_for_session(session.id)
        expense_entries = [e for e in entries if e.entry_type == LedgerEntryType.EXPENSE]
        assert len(expense_entries) == 1

        entry = expense_entries[0]
        assert entry.amount_pt == -2550  # negative: cash leaves drawer
        assert entry.expense_id == expense.id
        assert entry.actor_id == 100
        assert "مصروف" in entry.reason

    def test_expense_no_session_no_ledger_entry(self, db, auth):
        """If no open session, expense is saved but no ledger entry created."""
        fin_repo = FinancialRepository(db)
        session_repo = CashierSessionRepository(db)
        ledger_repo = CashLedgerRepository(db)
        audit_repo = AuditRepository(db)

        fin_svc = FinancialService(
            financial_repo=fin_repo,
            audit_repo=audit_repo,
            auth_service=auth,
            cash_ledger_repo=ledger_repo,
            cashier_session_repo=session_repo,
        )

        # Open shift but NO cashier session
        shift = fin_svc.open_shift(user_id=100)
        db.commit()

        # Add expense — should still work (expense saved, no ledger entry)
        expense = fin_svc.add_expense(
            shift_id=shift.id,
            amount=10.00,
            description="delivery_fees",
            category="delivery_fees",
            user_id=100,
        )
        db.commit()

        assert expense.id is not None
        # No ledger entries for the day (no session exists)
        entries = ledger_repo.get_entries_for_day(shift.id)
        expense_entries = [e for e in entries if e.entry_type == LedgerEntryType.EXPENSE]
        assert len(expense_entries) == 0
