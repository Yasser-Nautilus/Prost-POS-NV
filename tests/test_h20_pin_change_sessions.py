"""
H20 — After a PIN change, the user's old sessions are rejected on their next call.

Scenario: two stations (two bridges, one shared database).
  * Station 1 is logged in as admin A.
  * On station 2, a different admin (B) changes A's PIN.
  * A's session on station 1 must not keep working — not for reads, not for
    admin-only actions — and must not come back by itself.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication

from broast_pos.core.models.user import UserRole
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.customer_service import CustomerService
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.product_service import ProductService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.customer_repository import CustomerRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.order_status_history_repository import (
    OrderStatusHistoryRepository,
)
from broast_pos.data.repositories.product_repository import ProductRepository
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers
from broast_pos.infrastructure.printing.printer_manager import PrinterManager
from broast_pos.infrastructure.web_bridge.bridge import POSBridge

SEED_ADMIN_PIN = "1234"   # admin B (seeded)
ADMIN_A_PIN = "5678"      # admin A (created in the fixture)
NEW_PIN = "9999"


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture(autouse=True)
def reset_db_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


class Station:
    """One POS station: its own bridge and its own AuthService (own session)."""

    def __init__(self, bridge: POSBridge):
        self.bridge = bridge

    def call(self, action: str, payload: dict | None = None) -> dict:
        return json.loads(self.bridge.dispatch(action, json.dumps(payload or {})))


@pytest.fixture
def stations(qapp):
    """Return (station_1, station_2, db). Both stations share one database."""
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    seed_database(db)

    product_repo = ProductRepository(db)
    audit_repo = AuditRepository(db)
    session_repo = CashierSessionRepository(db)
    ledger_repo = CashLedgerRepository(db)
    audit_svc = AuditService(audit_repo)

    def new_auth() -> AuthService:
        auth = AuthService(UserRepository(db))
        auth.set_audit(audit_repo)
        return auth

    auth_1, auth_2 = new_auth(), new_auth()

    delivery_svc = DeliveryService(
        delivery_repo=DeliveryRepository(db),
        user_repo=UserRepository(db),
        audit_repo=audit_repo,
    )
    fin = FinancialService(
        financial_repo=FinancialRepository(db), audit_repo=audit_repo,
        auth_service=auth_2, delivery_service=delivery_svc,
    )
    session_svc = CashierSessionService(
        session_repo=session_repo, ledger_repo=ledger_repo, auth_service=auth_2
    )
    order_svc = OrderService(
        order_repo=OrderRepository(db), audit_repo=audit_repo, auth_service=auth_2,
        financial_service=fin,
        status_history_repo=OrderStatusHistoryRepository(db),
        audit_service=audit_svc, session_service=session_svc,
        ledger_repo=ledger_repo, cashier_session_repo=session_repo,
        product_repo=product_repo,
    )
    delivery_svc._order_svc = order_svc

    printer = PrinterManager()
    for name in ("print_receipt", "print_kitchen_ticket_job",
                 "print_amendment_ticket_job", "print_shift_summary"):
        setattr(printer, name, MagicMock(return_value=True))

    def new_bridge(auth: AuthService) -> Station:
        return Station(POSBridge(
            auth_service=auth,
            product_service=ProductService(product_repo),
            customer_service=CustomerService(CustomerRepository(db)),
            delivery_service=delivery_svc,
            financial_service=fin,
            order_service=order_svc,
            report_service=None,
            print_triggers=PrintTriggers(printer),
            printer_manager=printer,
            settlement_service=None,
            audit_service=audit_svc,
            session_service=session_svc,
            business_day_service=BusinessDayService(
                financial_service=fin, session_repo=session_repo,
                ledger_repo=ledger_repo, auth_service=auth,
            ),
        ))

    station_1, station_2 = new_bridge(auth_1), new_bridge(auth_2)
    return station_1, station_2, db


def _login(station: Station, pin: str) -> dict:
    res = station.call("login", {"pin": pin})
    assert res["success"], res
    return res["data"]


@pytest.fixture
def two_admins(stations):
    """Admin B (seeded) on station 2, admin A (second admin) on station 1."""
    station_1, station_2, db = stations
    _login(station_2, SEED_ADMIN_PIN)
    # The UI/bridge no longer creates a second admin, so seed one directly.
    created = station_2.bridge._auth.create_user(
        "admin_a", "Admin A", UserRole.ADMIN, ADMIN_A_PIN,
    )
    admin_a = _login(station_1, ADMIN_A_PIN)
    assert admin_a["id"] == created.id
    return station_1, station_2, db, admin_a["id"]


def _change_pin(station: Station, user_id: int, new_pin: str) -> dict:
    return station.call("update_user", {"user_id": user_id, "pin": new_pin})


def _user_count(db: DatabaseConnection) -> int:
    return db.fetch_one("SELECT COUNT(*) AS n FROM users")["n"]


# ---------------------------------------------------------------------------
# The H20 scenario
# ---------------------------------------------------------------------------

class TestOtherAdminChangesPin:

    def test_session_works_before_the_pin_change(self, two_admins):
        station_1, _s2, _db, _a = two_admins
        assert station_1.call("get_users_management")["success"] is True

    def test_old_session_is_rejected_on_next_call(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins

        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]

        res = station_1.call("get_users_management")
        assert res["success"] is False
        assert res["code"] == "session_expired"

    def test_old_session_cannot_run_admin_actions(self, two_admins):
        station_1, station_2, db, admin_a_id = two_admins
        users_before = _user_count(db)

        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]

        res = station_1.call("create_user", {
            "username": "intruder", "display_name": "Intruder",
            "role": "admin", "pin": "4321",
        })
        assert res["success"] is False
        assert _user_count(db) == users_before

    def test_old_session_stays_rejected_and_is_logged_out(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]

        for _ in range(3):
            assert station_1.call("get_users_management")["success"] is False
        # The UI's startup check now sees "not logged in", not the stale admin.
        res = station_1.call("get_current_user")
        assert res["success"] is True
        assert res["data"] is None

    def test_stale_session_may_still_use_public_actions(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]
        assert station_1.call("get_all_users")["success"] is True

    def test_user_can_log_in_again_with_the_new_pin_only(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]
        assert station_1.call("get_users_management")["success"] is False

        assert station_1.call("login", {"pin": ADMIN_A_PIN})["success"] is False
        again = station_1.call("login", {"pin": NEW_PIN})
        assert again["success"] is True
        assert again["data"]["id"] == admin_a_id
        assert station_1.call("get_users_management")["success"] is True

    def test_admin_who_changed_the_pin_keeps_working(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]
        assert station_2.call("get_users_management")["success"] is True

    def test_other_users_sessions_are_not_affected(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        # A third person is logged in on station 1's twin; changing A's PIN
        # must not touch anybody else.
        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]
        assert station_2.call("get_users_management")["success"] is True
        assert station_2.call("get_current_user")["data"]["username"] == "admin"


# ---------------------------------------------------------------------------
# Related ways a session must end or survive
# ---------------------------------------------------------------------------

class TestRelatedCases:

    def test_setting_the_same_pin_again_still_ends_old_sessions(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        assert _change_pin(station_2, admin_a_id, ADMIN_A_PIN)["success"]
        assert station_1.call("get_users_management")["success"] is False

    def test_changing_own_pin_keeps_this_session_but_ends_the_other_one(self, stations):
        station_1, station_2, _db = stations
        _login(station_1, SEED_ADMIN_PIN)
        admin = _login(station_2, SEED_ADMIN_PIN)   # same user, second station

        assert _change_pin(station_1, admin["id"], NEW_PIN)["success"]

        assert station_1.call("get_users_management")["success"] is True
        assert station_2.call("get_users_management")["success"] is False

    def test_deactivated_user_session_is_rejected(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        res = station_2.call("update_user", {"user_id": admin_a_id, "is_active": False})
        assert res["success"], res
        assert station_1.call("get_users_management")["success"] is False

    def test_unrelated_changes_do_not_end_the_session(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        res = station_2.call("update_user", {
            "user_id": admin_a_id, "display_name": "Admin A (neu)",
        })
        assert res["success"], res
        assert station_1.call("get_users_management")["success"] is True

    def test_explicit_logout_still_works_after_a_pin_change(self, two_admins):
        station_1, station_2, _db, admin_a_id = two_admins
        assert _change_pin(station_2, admin_a_id, NEW_PIN)["success"]
        assert station_1.call("logout")["success"] is True
        assert station_1.call("get_users_management")["success"] is False


# ---------------------------------------------------------------------------
# AuthService level
# ---------------------------------------------------------------------------

class TestAuthServiceValidateSession:

    def test_no_session_is_invalid(self, stations):
        _s1, _s2, db = stations
        assert AuthService(UserRepository(db)).validate_session() is False

    def test_session_is_valid_until_the_pin_changes(self, stations):
        _s1, _s2, db = stations
        auth = AuthService(UserRepository(db))
        user = auth.login_by_pin(SEED_ADMIN_PIN)
        assert auth.validate_session() is True
        assert auth.validate_session() is True  # checking does not consume it

        other = AuthService(UserRepository(db))
        other.login_by_pin(SEED_ADMIN_PIN)
        other.update_user(user.id, pin=NEW_PIN)

        assert auth.validate_session() is False
        assert auth.get_current_user() is None
        assert auth.is_logged_in() is False
