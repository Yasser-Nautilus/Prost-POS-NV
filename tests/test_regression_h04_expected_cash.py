"""
Regression tests — H04: expected_cash formula.

Root cause:
  ShiftSummary.expected_cash subtracted pending_delivery + pending_dinein +
  pending_kitchen from cash_sales even though those amounts were never in
  cash_sales to begin with (all pending orders have is_paid=0).

  This caused the drawer balance shown to managers to be LOWER than reality
  whenever there were outstanding orders, making reconciliation impossible.

Fix verified:
  expected_cash = cash_sales - total_expenses
  Pending amounts are shown as "unpaid receivables" separately — not deducted.
"""
from __future__ import annotations

import pytest

from broast_pos.core.models.financial import ShiftSummary


class TestH04ExpectedCash:

    def test_expected_cash_does_not_deduct_pending_delivery(self):
        """Unsettled delivery orders are receivables, not drawer deductions."""
        s = ShiftSummary(
            cash_sales=500.0,
            total_expenses=50.0,
            pending_delivery=100.0,   # driver cash in transit
            pending_dinein=0.0,
            pending_kitchen=0.0,
        )
        # Drawer should be 500 - 50 = 450, NOT 500 - 50 - 100 = 350
        assert s.expected_cash == pytest.approx(450.0), (
            f"expected_cash {s.expected_cash} deducts pending_delivery — it must not"
        )

    def test_expected_cash_does_not_deduct_pending_dinein(self):
        """Unpaid dine-in orders are receivables, not drawer deductions."""
        s = ShiftSummary(
            cash_sales=200.0,
            total_expenses=20.0,
            pending_delivery=0.0,
            pending_dinein=80.0,    # customers at tables haven't paid yet
            pending_kitchen=0.0,
        )
        assert s.expected_cash == pytest.approx(180.0), (
            f"expected_cash {s.expected_cash} deducts pending_dinein — it must not"
        )

    def test_expected_cash_does_not_deduct_pending_kitchen(self):
        """Orders being prepared are receivables, not drawer deductions."""
        s = ShiftSummary(
            cash_sales=300.0,
            total_expenses=30.0,
            pending_delivery=0.0,
            pending_dinein=0.0,
            pending_kitchen=60.0,   # food still being prepared
        )
        assert s.expected_cash == pytest.approx(270.0), (
            f"expected_cash {s.expected_cash} deducts pending_kitchen — it must not"
        )

    def test_expected_cash_formula_cash_minus_expenses(self):
        """expected_cash = cash_sales - total_expenses regardless of pending amounts."""
        s = ShiftSummary(
            cash_sales=1000.0,
            total_expenses=150.0,
            pending_delivery=200.0,
            pending_dinein=100.0,
            pending_kitchen=50.0,
        )
        assert s.expected_cash == pytest.approx(850.0), (
            f"expected_cash should be 850 (1000 - 150), got {s.expected_cash}"
        )

    def test_total_pending_still_accessible_separately(self):
        """Pending amounts remain available for display as unpaid receivables."""
        s = ShiftSummary(
            cash_sales=500.0,
            total_expenses=0.0,
            pending_delivery=100.0,
            pending_dinein=50.0,
            pending_kitchen=25.0,
        )
        assert s.total_pending == pytest.approx(175.0), (
            f"total_pending {s.total_pending} should still sum all pending fields"
        )
        assert s.expected_cash == pytest.approx(500.0), (
            f"expected_cash {s.expected_cash} should equal cash_sales when no expenses"
        )


# ===========================================================================
# Database-level tests: Disjoint pending categories (no double counting)
# ===========================================================================

class TestNoPendingOverlapInDatabase:
    """Verifies that pending categories never double count across SQL queries."""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        yield
        DatabaseConnection.reset()

    def _setup_db(self):
        from broast_pos.data.database.connection import DatabaseConnection
        from broast_pos.data.database.migrations import initialise_database

        db = DatabaseConnection.get_instance(":memory:")
        initialise_database(db)
        db.execute(
            "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
            "VALUES (1, 'admin', 'المدير', 'admin', 'h1', 1)"
        )
        db.execute(
            "INSERT INTO shifts (id, opened_by, next_invoice_no, is_active) "
            "VALUES (1, 1, 1, 1)"
        )
        db.commit()
        return db

    def test_unpaid_dinein_order_not_double_counted_in_kitchen(self):
        """Dine-in orders in preparing status belong to pending_dinein ONLY."""
        from broast_pos.data.repositories.financial_repository import (
            FinancialRepository,
        )

        db = self._setup_db()
        repo = FinancialRepository(db=db)

        # Insert unpaid dine_in order in 'preparing' status
        db.execute(
            """INSERT INTO orders
                   (invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (1, 'dine_in', 'preparing', 70.0, 0, 'cash', 1, 1, 'admin', 1)"""
        )
        db.commit()

        summary = repo.get_shift_summary(1)
        assert summary.pending_dinein == 70.0
        assert summary.pending_kitchen == 0.0, "Dine-in order must NOT be in pending_kitchen!"
        assert summary.pending_delivery == 0.0
        assert summary.total_pending == 70.0

    def test_unpaid_delivery_order_on_trip_not_in_kitchen(self):
        """Delivery orders on unsettled trips belong to pending_delivery ONLY."""
        from broast_pos.data.repositories.financial_repository import (
            FinancialRepository,
        )

        db = self._setup_db()
        repo = FinancialRepository(db=db)

        # Insert order + trip + trip_orders
        db.execute(
            """INSERT INTO orders
                   (id, invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (10, 1, 'delivery', 'delivered', 80.0, 0, 'cash', 1, 1, 'admin', 1)"""
        )
        db.execute(
            """INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled)
               VALUES (1, 1, 'سائق', 0)"""
        )
        db.execute(
            "INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (1, 10)"
        )
        db.commit()

        summary = repo.get_shift_summary(1)
        assert summary.pending_delivery == 80.0
        assert summary.pending_kitchen == 0.0, "Delivery order on trip must NOT be in pending_kitchen!"
        assert summary.pending_dinein == 0.0
        assert summary.total_pending == 80.0

    def test_paid_takeaway_order_not_in_pending_kitchen(self):
        """Paid orders still in preparation are NOT unpaid receivables."""
        from broast_pos.data.repositories.financial_repository import (
            FinancialRepository,
        )

        db = self._setup_db()
        repo = FinancialRepository(db=db)

        db.execute(
            """INSERT INTO orders
                   (invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (1, 'takeaway', 'preparing', 70.0, 1, 'cash', 1, 1, 'admin', 1)"""
        )
        db.commit()

        summary = repo.get_shift_summary(1)
        assert summary.pending_kitchen == 0.0, "Paid order must NOT be in pending_kitchen!"
        assert summary.total_pending == 0.0
        assert summary.cash_sales == 70.0

    def test_unpaid_takeaway_order_is_in_pending_kitchen(self):
        """Unpaid takeaway in kitchen is counted in pending_kitchen."""
        from broast_pos.data.repositories.financial_repository import (
            FinancialRepository,
        )

        db = self._setup_db()
        repo = FinancialRepository(db=db)

        db.execute(
            """INSERT INTO orders
                   (invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (1, 'takeaway', 'preparing', 70.0, 0, 'cash', 1, 1, 'admin', 1)"""
        )
        db.commit()

        summary = repo.get_shift_summary(1)
        assert summary.pending_kitchen == 70.0
        assert summary.pending_dinein == 0.0
        assert summary.pending_delivery == 0.0
        assert summary.total_pending == 70.0

    def test_mixed_orders_no_overlap(self):
        """All three categories exist simultaneously with strictly disjoint amounts."""
        from broast_pos.data.repositories.financial_repository import (
            FinancialRepository,
        )

        db = self._setup_db()
        repo = FinancialRepository(db=db)

        # 1. Unpaid dine-in (50 EGP)
        db.execute(
            """INSERT INTO orders
                   (id, invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (1, 1, 'dine_in', 'preparing', 50.0, 0, 'cash', 1, 1, 'admin', 1)"""
        )
        # 2. Unpaid delivery on unsettled trip (80 EGP)
        db.execute(
            """INSERT INTO orders
                   (id, invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (2, 2, 'delivery', 'ready', 80.0, 0, 'cash', 1, 1, 'admin', 1)"""
        )
        db.execute(
            """INSERT INTO delivery_trips (id, driver_id, driver_name, is_settled)
               VALUES (1, 1, 'سائق', 0)"""
        )
        db.execute("INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (1, 2)")

        # 3. Unpaid takeaway in preparing (70 EGP)
        db.execute(
            """INSERT INTO orders
                   (id, invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (3, 3, 'takeaway', 'preparing', 70.0, 0, 'cash', 1, 1, 'admin', 1)"""
        )
        # 4. Paid takeaway in preparing (100 EGP)
        db.execute(
            """INSERT INTO orders
                   (id, invoice_no, order_type, status, total, is_paid, payment_method, shift_id, created_by_id, created_by_name, cashier_slot)
               VALUES (4, 4, 'takeaway', 'preparing', 100.0, 1, 'cash', 1, 1, 'admin', 1)"""
        )
        db.commit()

        summary = repo.get_shift_summary(1)
        assert summary.pending_dinein == 50.0
        assert summary.pending_delivery == 80.0
        assert summary.pending_kitchen == 70.0
        assert summary.total_pending == 200.0, (
            f"Expected total_pending=200 (50+80+70), got {summary.total_pending}"
        )
        assert summary.cash_sales == 100.0


# ===========================================================================
# End-to-end bridge tests: Cash movements, uncollected orders, Visa & ledger
# ===========================================================================

class TestBridgeH04ExpectedCash:
    """End-to-end regression tests via POSBridge for H04 requirements:
    1. Unpaid 70 EGP without cash movement does not change expected_cash.
    2. Visa/online payments do NOT count as cash.
    3. Cash payment records SALE_CASH in ledger and updates expected_cash.
    """

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        from broast_pos.data.database.connection import DatabaseConnection
        DatabaseConnection.reset()
        yield
        DatabaseConnection.reset()

    @pytest.fixture
    def bridge(self):
        import hashlib
        import json
        from unittest.mock import MagicMock

        from broast_pos.core.services.auth_service import AuthService
        from broast_pos.core.services.business_day_service import BusinessDayService
        from broast_pos.core.services.cashier_session_service import (
            CashierSessionService,
        )
        from broast_pos.core.services.customer_service import CustomerService
        from broast_pos.core.services.delivery_service import DeliveryService
        from broast_pos.core.services.financial_service import FinancialService
        from broast_pos.core.services.order_service import OrderService
        from broast_pos.core.services.product_service import ProductService
        from broast_pos.data.database import seed_database
        from broast_pos.data.database.connection import DatabaseConnection
        from broast_pos.data.database.migrations import initialise_database
        from broast_pos.data.repositories.cash_ledger_repository import (
            CashLedgerRepository,
        )
        from broast_pos.data.repositories.cashier_session_repository import (
            CashierSessionRepository,
        )
        from broast_pos.data.repositories.customer_repository import CustomerRepository
        from broast_pos.data.repositories.delivery_repository import DeliveryRepository
        from broast_pos.data.repositories.financial_repository import (
            FinancialRepository,
        )
        from broast_pos.data.repositories.order_repository import OrderRepository
        from broast_pos.data.repositories.product_repository import ProductRepository
        from broast_pos.data.repositories.user_repository import UserRepository
        from broast_pos.infrastructure.web_bridge.bridge import POSBridge

        conn = DatabaseConnection.get_instance(":memory:")
        initialise_database(conn)
        seed_database(conn)

        # Set admin PIN to 1234
        pin_hash = hashlib.sha256(b"1234").hexdigest()
        conn.execute("UPDATE users SET pin_hash=?, role='admin' WHERE id=1", (pin_hash,))
        conn.commit()

        user_repo = UserRepository(db=conn)
        fin_repo = FinancialRepository(db=conn)
        order_repo = OrderRepository(db=conn)
        deliv_repo = DeliveryRepository(db=conn)
        ledger_repo = CashLedgerRepository(db=conn)
        session_repo = CashierSessionRepository(db=conn)
        product_repo = ProductRepository(db=conn)
        cust_repo = CustomerRepository(db=conn)

        auth_svc = AuthService(user_repo=user_repo)
        session_svc = CashierSessionService(
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            auth_service=auth_svc,
        )
        fin_svc = FinancialService(
            financial_repo=fin_repo,
            auth_service=auth_svc,
            cash_ledger_repo=ledger_repo,
            cashier_session_repo=session_repo,
        )
        order_svc = OrderService(
            order_repo=order_repo,
            financial_service=fin_svc,
            auth_service=auth_svc,
            ledger_repo=ledger_repo,
            cashier_session_repo=session_repo,
            session_service=session_svc,
        )
        deliv_svc = DeliveryService(
            delivery_repo=deliv_repo,
            order_repo=order_repo,
            order_service=order_svc,
        )
        product_svc = ProductService(product_repo=product_repo)
        cust_svc = CustomerService(customer_repo=cust_repo)
        bday_svc = BusinessDayService(
            financial_service=fin_svc,
            session_repo=session_repo,
            ledger_repo=ledger_repo,
            auth_service=auth_svc,
            delivery_repo=deliv_repo,
        )

        mock_print = MagicMock()
        mock_print.on_order_created.return_value = True
        mock_print.on_order_completed.return_value = True

        bridge = POSBridge(
            auth_service=auth_svc,
            product_service=product_svc,
            customer_service=cust_svc,
            delivery_service=deliv_svc,
            financial_service=fin_svc,
            order_service=order_svc,
            report_service=MagicMock(),
            print_triggers=mock_print,
            printer_manager=None,
            session_service=session_svc,
            business_day_service=bday_svc,
        )

        # Login admin
        login_res = json.loads(bridge.dispatch("login", json.dumps({"pin": "1234"})))
        assert login_res["success"]

        # Open shift
        shift_res = json.loads(bridge.dispatch("open_shift", json.dumps({"user_id": 1})))
        assert shift_res["success"]
        shift_id = shift_res["data"]["id"]

        # Open cashier session with 0 opening float
        sess_res = json.loads(bridge.dispatch("session.open", json.dumps({
            "day_id": shift_id,
            "user_id": 1,
            "station": "ALL",
            "opening_float_egp": 0.0,
        })))
        assert sess_res["success"]

        bridge._test_db = conn
        bridge._test_shift_id = shift_id
        bridge._test_ledger = ledger_repo
        return bridge

    def test_unpaid_70_egp_order_does_not_change_expected_cash(self, bridge):
        """Unbezahlte 70 EGP ohne Geldbewegung verändern die Kasse nicht."""
        import json

        shift_id = bridge._test_shift_id

        # Initial check: expected_cash = 0
        summary_res = json.loads(bridge.dispatch("get_shift_summary", json.dumps({"shift_id": shift_id})))
        assert summary_res["success"]
        assert summary_res["data"]["expected_cash"] == 0.0
        assert summary_res["data"]["cash_sales"] == 0.0

        # Create 70 EGP takeaway order and confirm it (product 1 = 70.0)
        bridge.dispatch("new_order", json.dumps({"order_type": "takeaway"}))
        bridge.dispatch("add_item", json.dumps({
            "product_id": 1, "product_name": "وجبة", "unit_price": 70.0, "quantity": 1,
        }))
        conf_res = json.loads(bridge.dispatch("confirm_order", json.dumps({})))
        assert conf_res["success"]

        # Re-check summary: expected_cash MUST still be 0.0!
        summary_res = json.loads(bridge.dispatch("get_shift_summary", json.dumps({"shift_id": shift_id})))
        assert summary_res["success"]
        data = summary_res["data"]
        assert data["expected_cash"] == 0.0, (
            f"Unpaid order must NOT change expected_cash! Got: {data['expected_cash']}"
        )
        assert data["cash_sales"] == 0.0
        assert data["pending_kitchen"] == 70.0
        # No entries in cash_ledger
        entries = bridge._test_ledger.get_entries_for_day(shift_id)
        sale_entries = [e for e in entries if e.entry_type.value == "SALE_CASH"]
        assert len(sale_entries) == 0

    def test_visa_payment_does_not_count_as_cash(self, bridge):
        """Visa/Online zählen nicht als Bargeld."""
        import json

        shift_id = bridge._test_shift_id

        bridge.dispatch("new_order", json.dumps({"order_type": "takeaway"}))
        bridge.dispatch("add_item", json.dumps({
            "product_id": 1, "product_name": "وجبة", "unit_price": 70.0, "quantity": 1,
        }))
        conf_res = json.loads(bridge.dispatch("confirm_order", json.dumps({})))
        assert conf_res["success"]
        order_id = conf_res["data"]["order_id"]

        # Pay via Visa
        pay_res = json.loads(bridge.dispatch("complete_payment", json.dumps({
            "order_id": order_id,
            "payment_method": "visa",
            "amount_paid": 70.0,
        })))
        assert pay_res["success"]

        # Check summary: total_sales=70, but cash_sales=0 and expected_cash=0!
        summary_res = json.loads(bridge.dispatch("get_shift_summary", json.dumps({"shift_id": shift_id})))
        assert summary_res["success"]
        data = summary_res["data"]
        assert data["total_sales"] == 70.0
        assert data["cash_sales"] == 0.0, "Visa must NOT count in cash_sales!"
        assert data["expected_cash"] == 0.0, "Visa must NOT increase expected_cash!"
        assert data["pending_kitchen"] == 0.0

        # No SALE_CASH in cash_ledger
        entries = bridge._test_ledger.get_entries_for_day(shift_id)
        sale_entries = [e for e in entries if e.entry_type.value == "SALE_CASH"]
        assert len(sale_entries) == 0

    def test_cash_payment_increases_expected_cash_via_ledger(self, bridge):
        """Barzahlung bucht SALE_CASH im Ledger und erhöht expected_cash."""
        import json

        shift_id = bridge._test_shift_id

        bridge.dispatch("new_order", json.dumps({"order_type": "takeaway"}))
        bridge.dispatch("add_item", json.dumps({
            "product_id": 1, "product_name": "وجبة", "unit_price": 70.0, "quantity": 1,
        }))
        conf_res = json.loads(bridge.dispatch("confirm_order", json.dumps({})))
        assert conf_res["success"]
        order_id = conf_res["data"]["order_id"]

        # Pay cash
        pay_res = json.loads(bridge.dispatch("complete_payment", json.dumps({
            "order_id": order_id,
            "payment_method": "cash",
            "amount_paid": 70.0,
        })))
        assert pay_res["success"]

        # Check summary: cash_sales=70, expected_cash=70
        summary_res = json.loads(bridge.dispatch("get_shift_summary", json.dumps({"shift_id": shift_id})))
        assert summary_res["success"]
        data = summary_res["data"]
        assert data["cash_sales"] == 70.0
        assert data["expected_cash"] == 70.0
        assert data["pending_kitchen"] == 0.0

        # Exactly 1 SALE_CASH in ledger
        entries = bridge._test_ledger.get_entries_for_day(shift_id)
        sale_entries = [e for e in entries if e.entry_type.value == "SALE_CASH"]
        assert len(sale_entries) == 1
        assert sale_entries[0].amount_pt == 7000

    def test_expense_reduces_expected_cash_via_ledger(self, bridge):
        """Ausgaben buchen EXPENSE im Ledger und verringern expected_cash."""
        import json

        shift_id = bridge._test_shift_id

        # 1. Sale of 70 EGP cash
        bridge.dispatch("new_order", json.dumps({"order_type": "takeaway"}))
        bridge.dispatch("add_item", json.dumps({
            "product_id": 1, "product_name": "وجبة", "unit_price": 70.0, "quantity": 1,
        }))
        conf_res = json.loads(bridge.dispatch("confirm_order", json.dumps({})))
        order_id = conf_res["data"]["order_id"]
        bridge.dispatch("complete_payment", json.dumps({
            "order_id": order_id, "payment_method": "cash", "amount_paid": 70.0,
        }))

        # 2. Add expense of 20 EGP
        exp_res = json.loads(bridge.dispatch("add_expense", json.dumps({
            "shift_id": shift_id,
            "amount": 20.0,
            "description": "مناديل",
            "category": "supplies",
        })))
        assert exp_res["success"]

        # 3. Check summary: expected_cash = 70 - 20 = 50 EGP
        summary_res = json.loads(bridge.dispatch("get_shift_summary", json.dumps({"shift_id": shift_id})))
        assert summary_res["success"]
        data = summary_res["data"]
        assert data["expected_cash"] == 50.0
        assert data["cash_sales"] == 70.0
        assert data["total_expenses"] == 20.0


