"""
H01 · Barzahlung — Regressionstest über die echte Bridge.

Prüft den **kompletten** Pfad:
  Frontend-JSON → POSBridge.dispatch → OrderController → OrderService
  → PaymentCoordinator → CashLedgerRepository

Fertig-Kriterien:
  1. Angemeldeter Kassierer bezahlt bar → seine Actor-ID landet im Ledger.
  2. Genau EIN SALE_CASH-Eintrag entsteht.
  3. 100 + 70 = 170 stimmt (Summe zweier Produkte).
  4. Ohne aktive Session bleibt die Bestellung unbezahlt (kein SALE_CASH).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

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
from broast_pos.infrastructure.web_bridge.bridge import POSBridge

# ---------------------------------------------------------------------------
# Singleton isolation
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """In-memory DB with schema + seed data + H01 test product."""
    conn = DatabaseConnection.get_instance(":memory:")
    initialise_database(conn)
    seed_database(conn)
    # Insert a test product at exactly 100 EGP so we can test 100 + 70 = 170.
    conn.execute(
        "INSERT INTO products (name, price, category_id, is_active, sort_order) "
        "VALUES (?, ?, 1, 1, 99)",
        ("Testprodukt H01", 100.0),
    )
    conn.commit()
    yield conn
    DatabaseConnection._instance = None


@pytest.fixture
def repos(db):
    """All repositories wired to the same in-memory DB."""
    return {
        "user":     UserRepository(db=db),
        "fin":      FinancialRepository(db=db),
        "order":    OrderRepository(db=db),
        "delivery": DeliveryRepository(db=db),
        "ledger":   CashLedgerRepository(db=db),
        "session":  CashierSessionRepository(db=db),
        "product":  ProductRepository(db=db),
        "customer": CustomerRepository(db=db),
    }


@pytest.fixture
def bridge(db, repos):
    """Fully-wired POSBridge for integration testing (like production)."""
    auth_svc = AuthService(user_repo=repos["user"])
    session_svc = CashierSessionService(
        session_repo=repos["session"],
        ledger_repo=repos["ledger"],
        auth_service=auth_svc,
    )
    fin_svc = FinancialService(
        financial_repo=repos["fin"],
        auth_service=auth_svc,
        cash_ledger_repo=repos["ledger"],
        cashier_session_repo=repos["session"],
    )
    order_svc = OrderService(
        order_repo=repos["order"],
        financial_service=fin_svc,
        auth_service=auth_svc,
        ledger_repo=repos["ledger"],
        cashier_session_repo=repos["session"],
        session_service=session_svc,
    )
    delivery_svc = DeliveryService(
        delivery_repo=repos["delivery"],
        order_repo=repos["order"],
        order_service=order_svc,
    )
    product_svc = ProductService(product_repo=repos["product"])
    customer_svc = CustomerService(customer_repo=repos["customer"])
    business_day_svc = BusinessDayService(
        financial_service=fin_svc,
        session_repo=repos["session"],
        ledger_repo=repos["ledger"],
        auth_service=auth_svc,
        delivery_repo=repos["delivery"],
    )

    mock_print = MagicMock()
    mock_print.on_order_created.return_value = True
    mock_print.on_order_completed.return_value = True

    return POSBridge(
        auth_service=auth_svc,
        product_service=product_svc,
        customer_service=customer_svc,
        financial_service=fin_svc,
        order_service=order_svc,
        delivery_service=delivery_svc,
        report_service=None,
        printer_manager=None,
        print_triggers=mock_print,
        settlement_service=None,
        audit_service=None,
        session_service=session_svc,
        business_day_service=business_day_svc,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dispatch(bridge: POSBridge, action: str, payload: dict | None = None) -> dict:
    """Dispatch an action via the bridge and return parsed JSON."""
    raw = bridge.dispatch(action, json.dumps(payload or {}))
    return json.loads(raw)


def _login_admin(bridge: POSBridge) -> dict:
    """Login as the seed admin (PIN 1234) and return the user dict."""
    resp = _dispatch(bridge, "login", {"pin": "1234"})
    assert resp["success"], f"Admin login failed: {resp}"
    return resp["data"]


def _open_shift(bridge: POSBridge, user_id: int) -> dict:
    resp = _dispatch(bridge, "open_shift", {"user_id": user_id})
    assert resp["success"], f"open_shift failed: {resp}"
    return resp["data"]


def _open_session(bridge: POSBridge, day_id: int, user_id: int) -> dict:
    """Open a cashier session at the ALL station via the session bridge."""
    resp = _dispatch(bridge, "session.open", {
        "day_id": day_id,
        "user_id": user_id,
        "station": "ALL",
        "opening_float_egp": 0,
    })
    assert resp["success"], f"session.open failed: {resp}"
    return resp["data"]


def _create_takeaway_order(bridge: POSBridge) -> int:
    """Create and confirm a takeaway order with two items (100 + 70 = 170).

    Uses:
      - product_id=1 (تشيكن فرايز حار, 70 EGP)  — from seed
      - product_id=11 (Testprodukt H01, 100 EGP)  — inserted in fixture

    Returns the order_id.
    """
    # new takeaway order
    resp = _dispatch(bridge, "new_order", {"order_type": "takeaway"})
    assert resp["success"]

    # Item 1: 70 EGP (seed product_id=1)
    _dispatch(bridge, "add_item", {
        "product_id": 1, "product_name": "تشيكن فرايز حار",
        "unit_price": 70.0, "quantity": 1,
    })
    # Item 2: 100 EGP (test product_id=11)
    _dispatch(bridge, "add_item", {
        "product_id": 11, "product_name": "Testprodukt H01",
        "unit_price": 100.0, "quantity": 1,
    })

    # confirm
    resp = _dispatch(bridge, "confirm_order", {})
    assert resp["success"], f"confirm_order failed: {resp}"
    order_id = resp["data"]["order_id"]
    assert order_id is not None
    return order_id


# ===========================================================================
# Test class — H01 Barzahlung Regression
# ===========================================================================

class TestH01CashPaymentBridge:
    """Full-bridge regression for cash payment (H01)."""

    def test_cash_payment_creates_sale_cash_with_actor_id(
        self, bridge, repos,
    ):
        """
        Happy path: Kassierer meldet sich an, bezahlt bar.
        → Genau ein SALE_CASH im Ledger, Actor-ID == Kassierer.
        → Betrag 170 EGP == 17000 pt.
        """
        user = _login_admin(bridge)
        user_id = user["id"]

        # Open shift (business day)
        shift = _open_shift(bridge, user_id)
        day_id = shift["id"]

        # Open cashier session
        _open_session(bridge, day_id, user_id)

        # Create order (100 + 70 = 170)
        order_id = _create_takeaway_order(bridge)

        # Pay cash via bridge
        pay_resp = _dispatch(bridge, "complete_payment", {
            "order_id": order_id,
            "payment_method": "cash",
            "amount_paid": 200.0,  # 200 given, change = 30
        })
        assert pay_resp["success"], f"complete_payment failed: {pay_resp}"

        # ── Assertions ────────────────────────────────────────────────

        # 1) Exactly one SALE_CASH entry in the ledger for this order
        ledger = repos["ledger"]
        from broast_pos.core.models.cashier_session import LedgerEntryType
        entry = ledger.get_entry_by_order(order_id, LedgerEntryType.SALE_CASH)
        assert entry is not None, "SALE_CASH entry missing in ledger!"

        # 2) Amount is 170 EGP = 17000 pt
        assert entry.amount_pt == 17_000, (
            f"Expected 17000 pt (170 EGP), got {entry.amount_pt}"
        )

        # 3) Actor-ID is the logged-in cashier
        assert entry.actor_id == user_id, (
            f"Actor-ID mismatch: expected {user_id}, got {entry.actor_id}"
        )

        # 4) No duplicate entries — only one SALE_CASH for this order
        all_entries = ledger.get_entries_for_day(day_id)
        sale_cash_entries = [
            e for e in all_entries
            if e.entry_type == LedgerEntryType.SALE_CASH
            and e.order_id == order_id
        ]
        assert len(sale_cash_entries) == 1, (
            f"Expected exactly 1 SALE_CASH, found {len(sale_cash_entries)}"
        )

    def test_no_session_means_no_sale_cash(self, bridge, repos):
        """
        Ohne offene Cashier-Session schlägt die Barzahlung fehl und die
        Bestellung bleibt unbezahlt (is_paid=False, kein SALE_CASH im Ledger).
        """
        user = _login_admin(bridge)
        user_id = user["id"]

        # Open shift — but do NOT open a cashier session
        _open_shift(bridge, user_id)

        # Create order
        order_id = _create_takeaway_order(bridge)

        # Pay cash
        pay_resp = _dispatch(bridge, "complete_payment", {
            "order_id": order_id,
            "payment_method": "cash",
            "amount_paid": 170.0,
        })
        # Payment fails because no session is open for this cashier
        assert pay_resp["success"] is False
        assert "لا توجد جلسة مفتوحة" in pay_resp.get("error", "")

        # ── Assertion: Order remains unpaid ───────────────────────────
        order = repos["order"].get_by_id(order_id)
        assert order is not None
        assert order.is_paid is False
        assert order.status.value != "completed"

        # ── Assertion: No SALE_CASH in ledger ─────────────────────────
        ledger = repos["ledger"]
        from broast_pos.core.models.cashier_session import LedgerEntryType
        entry = ledger.get_entry_by_order(order_id, LedgerEntryType.SALE_CASH)
        assert entry is None, "Without a cashier session there should be no SALE_CASH entry"

    def test_total_matches_100_plus_70(self, bridge):
        """
        Verify that the order total is exactly 100 + 70 = 170 EGP.
        """
        user = _login_admin(bridge)
        _open_shift(bridge, user["id"])

        order_id = _create_takeaway_order(bridge)

        # Load the order from DB and check total
        resp = _dispatch(bridge, "load_order", {"order_id": order_id})
        assert resp["success"]
        assert resp["data"]["total"] == pytest.approx(170.0), (
            f"Total should be 170.0 EGP, got {resp['data']['total']}"
        )

    def test_visa_payment_creates_no_sale_cash(self, bridge, repos):
        """
        Visa-Zahlung → kein SALE_CASH (Geld kommt nicht in die Kasse).
        """
        user = _login_admin(bridge)
        user_id = user["id"]

        shift = _open_shift(bridge, user_id)
        day_id = shift["id"]
        _open_session(bridge, day_id, user_id)

        order_id = _create_takeaway_order(bridge)

        pay_resp = _dispatch(bridge, "complete_payment", {
            "order_id": order_id,
            "payment_method": "visa",
            "amount_paid": 170.0,
        })
        assert pay_resp["success"]

        # No SALE_CASH for visa
        from broast_pos.core.models.cashier_session import LedgerEntryType
        entry = repos["ledger"].get_entry_by_order(
            order_id, LedgerEntryType.SALE_CASH,
        )
        assert entry is None, "Visa should NOT create a SALE_CASH entry"

    def test_session_balance_reflects_cash_sale(self, bridge, repos):
        """
        After a cash sale the session balance includes the SALE_CASH amount.
        """
        user = _login_admin(bridge)
        user_id = user["id"]

        shift = _open_shift(bridge, user_id)
        day_id = shift["id"]
        session = _open_session(bridge, day_id, user_id)
        session_id = session["id"]

        order_id = _create_takeaway_order(bridge)
        _dispatch(bridge, "complete_payment", {
            "order_id": order_id,
            "payment_method": "cash",
            "amount_paid": 170.0,
        })

        # Session balance should be 170 EGP = 17000 pt
        # (opening float was 0, only one SALE_CASH of 17000 pt)
        balance = repos["ledger"].get_session_balance_pt(session_id)
        assert balance == 17_000, (
            f"Session balance should be 17000 pt after 170 EGP cash sale, "
            f"got {balance}"
        )
