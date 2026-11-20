"""
Bridge integration tests — verify dispatch actions return correct responses.

Covers: get_config, session dispatch, reassign_order, delivery controller
reassign_order method, and error paths.
"""

from __future__ import annotations

import json

import pytest

from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.customer_service import CustomerService
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.product_service import ProductService
from broast_pos.data.database import seed_database
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.customer_repository import CustomerRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.product_repository import ProductRepository
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.features.delivery_system.delivery_controller import DeliveryController
from broast_pos.infrastructure.web_bridge.bridge import POSBridge


@pytest.fixture
def db():
    """In-memory DB with schema + seed data."""
    conn = DatabaseConnection.get_instance(":memory:")
    initialise_database(conn)
    seed_database(conn)
    yield conn
    DatabaseConnection._instance = None


@pytest.fixture
def bridge(db):
    """Fully-wired POSBridge for integration testing."""
    user_repo = UserRepository(db=db)
    fin_repo = FinancialRepository(db=db)
    order_repo = OrderRepository(db=db)
    delivery_repo = DeliveryRepository(db=db)
    ledger_repo = CashLedgerRepository(db=db)
    session_repo = CashierSessionRepository(db=db)
    product_repo = ProductRepository(db=db)
    customer_repo = CustomerRepository(db=db)

    auth_svc = AuthService(user_repo=user_repo)
    fin_svc = FinancialService(
        financial_repo=fin_repo,
        auth_service=auth_svc,
        cash_ledger_repo=ledger_repo,
        cashier_session_repo=session_repo,
    )
    order_svc = OrderService(order_repo=order_repo, financial_service=fin_svc)
    delivery_svc = DeliveryService(
        delivery_repo=delivery_repo,
        order_repo=order_repo,
        order_service=order_svc,
    )
    product_svc = ProductService(product_repo=product_repo)
    customer_svc = CustomerService(customer_repo=customer_repo)
    session_svc = CashierSessionService(
        session_repo=session_repo,
        ledger_repo=ledger_repo,
        auth_service=auth_svc,
    )
    business_day_svc = BusinessDayService(
        financial_service=fin_svc,
        session_repo=session_repo,
        ledger_repo=ledger_repo,
        auth_service=auth_svc,
        delivery_repo=delivery_repo,
    )

    return POSBridge(
        auth_service=auth_svc,
        product_service=product_svc,
        customer_service=customer_svc,
        financial_service=fin_svc,
        order_service=order_svc,
        delivery_service=delivery_svc,
        report_service=None,
        printer_manager=None,
        print_triggers=None,
        settlement_service=None,
        audit_service=None,
        session_service=session_svc,
        business_day_service=business_day_svc,
    )


def _login_admin(bridge: POSBridge) -> dict:
    """Login as the seed admin (PIN 1234)."""
    raw = bridge.dispatch("login", json.dumps({"pin": "1234"}))
    resp = json.loads(raw)
    assert resp["success"] is True, f"Admin login failed: {resp}"
    return resp


# ── get_config ────────────────────────────────────────────────────────────────


class TestGetConfigAction:
    """Test the get_config bridge action."""

    def test_get_config_returns_success(self, bridge):
        raw = bridge.dispatch("get_config", "{}")
        resp = json.loads(raw)
        assert resp["success"] is True
        data = resp["data"]
        assert "restaurant_name_ar" in data
        assert "restaurant_name_en" in data

    def test_get_config_works_without_login(self, bridge):
        """get_config is a public action — no login required."""
        raw = bridge.dispatch("get_config", "{}")
        resp = json.loads(raw)
        assert resp["success"] is True


# ── Session dispatch ──────────────────────────────────────────────────────────


class TestSessionDispatch:
    """Test session.* bridge actions."""

    def test_session_actions_require_login(self, bridge):
        """Session actions behind auth guard should reject unauthenticated."""
        raw = bridge.dispatch("session.get_active", "{}")
        resp = json.loads(raw)
        assert resp["success"] is False
        assert "تسجيل الدخول" in resp.get("error", "")

    def test_session_get_active_returns_list(self, bridge):
        _login_admin(bridge)
        raw = bridge.dispatch("session.get_active", "{}")
        resp = json.loads(raw)
        assert resp["success"] is True
        assert isinstance(resp["data"], list)

    def test_session_get_all_returns_list(self, bridge):
        _login_admin(bridge)
        raw = bridge.dispatch("session.get_all", "{}")
        resp = json.loads(raw)
        assert resp["success"] is True
        assert isinstance(resp["data"], list)

    def test_session_x_report_returns_data(self, bridge):
        _login_admin(bridge)
        raw = bridge.dispatch("session.x_report", "{}")
        resp = json.loads(raw)
        assert isinstance(resp, dict)
        assert "success" in resp

    def test_session_unknown_action_error(self, bridge):
        _login_admin(bridge)
        raw = bridge.dispatch("session.nonexistent", "{}")
        resp = json.loads(raw)
        assert resp["success"] is False
        assert "غير معروف" in resp.get("error", "")


# ── reassign_order ────────────────────────────────────────────────────────────


class TestReassignOrderAction:
    """Test the reassign_order delivery bridge action."""

    def test_reassign_order_requires_login(self, bridge):
        raw = bridge.dispatch("reassign_order", json.dumps({
            "order_id": 999, "new_driver_id": 1, "new_driver_name": "Test"
        }))
        resp = json.loads(raw)
        assert resp["success"] is False
        assert "تسجيل الدخول" in resp.get("error", "")

    def test_reassign_nonexistent_order_fails(self, bridge):
        _login_admin(bridge)
        raw = bridge.dispatch("reassign_order", json.dumps({
            "order_id": 99999, "new_driver_id": 1, "new_driver_name": "Test"
        }))
        resp = json.loads(raw)
        assert resp["success"] is False


# ── DeliveryController.reassign_order ─────────────────────────────────────────


class TestDeliveryControllerReassign:
    """Test the DeliveryController.reassign_order method directly."""

    def test_reassign_order_nonexistent(self, db):
        """reassign_order for a non-existent order returns failure."""
        delivery_repo = DeliveryRepository(db=db)
        order_repo = OrderRepository(db=db)
        order_svc = OrderService(
            order_repo=order_repo,
            financial_service=FinancialService(
                financial_repo=FinancialRepository(db=db),
                auth_service=AuthService(user_repo=UserRepository(db=db)),
            ),
        )
        delivery_svc = DeliveryService(
            delivery_repo=delivery_repo,
            order_repo=order_repo,
            order_service=order_svc,
        )
        ctrl = DeliveryController(
            delivery_service=delivery_svc,
            order_service=order_svc,
            print_triggers=None,
        )
        ok, msg = ctrl.reassign_order(
            order_id=99999,
            new_driver_id=1,
            new_driver_name="Test",
        )
        assert ok is False
        assert isinstance(msg, str)


# ── Unknown action ────────────────────────────────────────────────────────────


class TestUnknownAction:
    """Test that unknown top-level actions return error."""

    def test_unknown_action_returns_error(self, bridge):
        _login_admin(bridge)
        raw = bridge.dispatch("totally_unknown_action_xyz", "{}")
        resp = json.loads(raw)
        assert resp["success"] is False
