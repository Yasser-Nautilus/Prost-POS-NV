"""
H16 — A report shows EITHER a shift OR a calendar day, never a mix.

Decision: the shift is the unit of the cash drawer, and shifts can span
midnight, so a report asked for a shift is filtered by shift_id in every
section. A report asked for a calendar day is filtered by date in every
section and carries no shift totals. Asking for both is an error.

Fixture data (all timestamps are local time):

  shift 1  opened 2026-03-10 22:00, spans midnight
    o1  03-10 23:30  takeaway  100  cash   paid       item "A" x2
    o2  03-11 00:30  delivery  150  visa   paid fee20 item "B" x1
    o3  03-11 00:45  cancelled  40                     item "A" x1
  shift 2  opened 2026-03-11 18:00
    o4  03-11 19:00  takeaway   60  cash   paid       item "A" x1
    o5  03-11 20:00  delivery   90  cash   paid fee10 item "C" x1

  trip 1 (fees 20): orders o1 + o2  → shift 1
  trip 2 (fees 10): order  o5       → shift 2
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from broast_pos.core.services.report_service import ReportService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.features.reports.reports_controller import ReportsController
from broast_pos.infrastructure.web_bridge.bridge import POSBridge

DAY_1 = date(2026, 3, 10)
DAY_2 = date(2026, 3, 11)


@pytest.fixture(autouse=True)
def reset_db_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _order(db, *, order_id, invoice_no, shift_id, order_type, status, total,
           created_at, payment_method=None, is_paid=0, delivery_fee=0.0,
           items=(), cancel_reason=None):
    db.execute(
        """INSERT INTO orders
               (id, invoice_no, shift_id, order_type, status, delivery_fee,
                subtotal, total, payment_method, is_paid,
                created_by_id, created_by_name, cashier_slot, created_at,
                cancelled_by_id, cancelled_by_name, cancel_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'admin', 1, ?, ?, ?, ?)""",
        (order_id, invoice_no, shift_id, order_type, status, delivery_fee,
         total - delivery_fee, total, payment_method, is_paid, created_at,
         1 if cancel_reason else None, "admin" if cancel_reason else None,
         cancel_reason),
    )
    for name, qty, price in items:
        db.execute(
            """INSERT INTO order_items
                   (order_id, product_id, product_name, quantity, unit_price, total_price)
               VALUES (?, 1, ?, ?, ?, ?)""",
            (order_id, name, qty, price / qty, price),
        )


@pytest.fixture
def env():
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    seed_database(db)

    db.execute("INSERT INTO shifts (id, opened_by, opened_at, closed_at, is_active) "
               "VALUES (1, 1, '2026-03-10 22:00:00', '2026-03-11 06:00:00', 0)")
    db.execute("INSERT INTO shifts (id, opened_by, opened_at, is_active) "
               "VALUES (2, 1, '2026-03-11 18:00:00', 1)")

    _order(db, order_id=1, invoice_no=1, shift_id=1, order_type="takeaway",
           status="completed", total=100, created_at="2026-03-10 23:30:00",
           payment_method="cash", is_paid=1, items=[("A", 2, 100)])
    _order(db, order_id=2, invoice_no=2, shift_id=1, order_type="delivery",
           status="completed", total=150, created_at="2026-03-11 00:30:00",
           payment_method="visa", is_paid=1, delivery_fee=20,
           items=[("B", 1, 130)])
    _order(db, order_id=3, invoice_no=3, shift_id=1, order_type="takeaway",
           status="cancelled", total=40, created_at="2026-03-11 00:45:00",
           items=[("A", 1, 40)], cancel_reason="خطأ")
    _order(db, order_id=4, invoice_no=1, shift_id=2, order_type="takeaway",
           status="completed", total=60, created_at="2026-03-11 19:00:00",
           payment_method="cash", is_paid=1, items=[("A", 1, 60)])
    _order(db, order_id=5, invoice_no=2, shift_id=2, order_type="delivery",
           status="completed", total=90, created_at="2026-03-11 20:00:00",
           payment_method="cash", is_paid=1, delivery_fee=10,
           items=[("C", 1, 80)])

    db.execute("INSERT INTO delivery_trips (id, driver_id, driver_name, created_at, total_delivery_fees) "
               "VALUES (1, 1, 'سائق', '2026-03-11 00:35:00', 20)")
    db.execute("INSERT INTO delivery_trips (id, driver_id, driver_name, created_at, total_delivery_fees) "
               "VALUES (2, 1, 'سائق', '2026-03-11 20:05:00', 10)")
    db.execute("INSERT INTO delivery_trip_orders (trip_id, order_id) VALUES (1, 1), (1, 2), (2, 5)")
    db.commit()

    service = ReportService(
        order_repo=OrderRepository(db),
        financial_repo=FinancialRepository(db),
        delivery_repo=DeliveryRepository(db),
    )
    printer = MagicMock()
    printer.print_shift_summary.return_value = True
    financial_svc = MagicMock()
    ctrl = ReportsController(service, financial_svc, printer)
    return ctrl, printer, financial_svc


def _by_type(report: dict) -> dict[str, dict]:
    return {b["type"]: b for b in report["sales_by_type"]["breakdown"]}


def _qty(report: dict) -> dict[str, int]:
    return {b["product_name"]: b["quantity"] for b in report["bestsellers"]}


# ---------------------------------------------------------------------------
# Shift report: every section follows the shift
# ---------------------------------------------------------------------------

class TestShiftReport:

    def test_shift_spanning_midnight_is_one_report(self, env):
        ctrl, *_ = env
        r = ctrl.generate_daily_summary(shift_id=1)
        assert r["scope"] == "shift"
        assert r["shift_id"] == 1
        assert r["date"] == "2026-03-10"          # business date = day it was opened
        assert r["sales_by_type"]["grand_total"] == {"count": 2, "revenue": 250.0}
        assert r["gross_revenue"] == 250.0

    def test_every_section_uses_the_shift(self, env):
        ctrl, *_ = env
        r = ctrl.generate_daily_summary(shift_id=1)

        assert {m["method"]: m["revenue"] for m in r["payment_breakdown"]["payments"]} == {
            "cash": 100.0, "visa": 150.0,
        }
        assert r["cancelled"]["count"] == 1
        assert r["cancelled"]["orders"][0]["order_id"] == 3
        assert _qty(r) == {"A": 2, "B": 1}        # the cancelled "A" is not counted
        assert r["total_delivery_fees"] == 20.0
        assert r["restaurant_revenue"] == 230.0

    def test_driver_summary_counts_each_trip_once(self, env):
        ctrl, *_ = env
        r = ctrl.generate_daily_summary(shift_id=1)
        assert r["driver_summary"] == [{
            "driver_id": 1, "driver_name": "سائق",
            "trip_count": 1, "order_count": 2, "fees_earned": 20.0,
        }]

    def test_shift_report_carries_the_shift_cash_totals(self, env):
        ctrl, *_ = env
        r = ctrl.generate_daily_summary(shift_id=1)
        assert r["shift_summary"] is not None
        assert r["shift_summary"]["shift_id"] == 1

    def test_other_shift_of_the_same_day_is_excluded(self, env):
        ctrl, *_ = env
        r = ctrl.generate_daily_summary(shift_id=2)
        assert r["date"] == "2026-03-11"
        assert r["sales_by_type"]["grand_total"] == {"count": 2, "revenue": 150.0}
        assert r["cancelled"]["count"] == 0
        assert _qty(r) == {"A": 1, "C": 1}
        assert r["total_delivery_fees"] == 10.0
        assert r["driver_summary"][0]["fees_earned"] == 10.0

    def test_old_shift_does_not_show_todays_sales(self, env):
        """Reprinting an old shift must show that shift, not 'today'."""
        ctrl, *_ = env
        assert date.today() not in (DAY_1, DAY_2)
        assert ctrl.generate_daily_summary(shift_id=1)["gross_revenue"] == 250.0


# ---------------------------------------------------------------------------
# Day report: every section follows the calendar day
# ---------------------------------------------------------------------------

class TestDayReport:

    def test_day_report_has_no_shift_part(self, env):
        ctrl, *_ = env
        r = ctrl.generate_daily_summary(DAY_1)
        assert r["scope"] == "day"
        assert r["shift_id"] is None
        assert r["shift_summary"] is None
        assert r["date"] == "2026-03-10"

    def test_midnight_orders_belong_to_the_calendar_day_they_were_created(self, env):
        ctrl, *_ = env
        day_1 = ctrl.generate_daily_summary(DAY_1)
        assert day_1["gross_revenue"] == 100.0                      # only o1
        assert _qty(day_1) == {"A": 2}

        day_2 = ctrl.generate_daily_summary(DAY_2)
        assert day_2["gross_revenue"] == 300.0                      # o2 + o4 + o5
        assert day_2["cancelled"]["count"] == 1                     # o3, created 00:45
        assert day_2["total_delivery_fees"] == 30.0                 # both shifts' fees
        assert day_2["restaurant_revenue"] == 270.0

    def test_default_day_is_today(self, env):
        ctrl, *_ = env
        r = ctrl.generate_daily_summary()
        assert r["scope"] == "day"
        assert r["date"] == date.today().isoformat()
        assert r["gross_revenue"] == 0.0


# ---------------------------------------------------------------------------
# Scope rules
# ---------------------------------------------------------------------------

class TestScopeRules:

    def test_shift_and_date_together_are_refused(self, env):
        ctrl, *_ = env
        with pytest.raises(ValueError, match="وليس الاثنين معاً"):
            ctrl.generate_daily_summary(DAY_1, shift_id=1)

    def test_unknown_shift_is_refused(self, env):
        ctrl, *_ = env
        with pytest.raises(ValueError, match="الوردية غير موجودة"):
            ctrl.generate_daily_summary(shift_id=999)

    def test_validate_scope_accepts_a_day_a_shift_or_nothing(self, env):
        ctrl, *_ = env
        ctrl.validate_scope(DAY_1, None)
        ctrl.validate_scope(None, 1)
        ctrl.validate_scope(None, None)


# ---------------------------------------------------------------------------
# Printing prints the same scope it shows
# ---------------------------------------------------------------------------

class TestPrintScope:

    # NOTE: the printer contract on this branch (H16 shape fix) is the
    # template payload {"breakdown", "grand_total"}, not the raw summary —
    # so scope correctness shows up as that payload's totals.

    def test_shift_print_is_shift_scoped_and_marks_the_shift_printed(self, env):
        ctrl, printer, financial_svc = env
        assert ctrl.print_daily_summary(shift_id=1, cashier_slot=2) is True

        payload = printer.print_shift_summary.call_args.args[0]
        assert payload["grand_total"] == {"count": 2, "revenue": 250.0}
        assert {b["type"]: b["revenue"] for b in payload["breakdown"]} == {
            "takeaway": 100.0, "delivery": 150.0,
        }
        assert printer.print_shift_summary.call_args.kwargs["shift_period"] is not None
        financial_svc.mark_summary_printed.assert_called_once_with(1)

    def test_day_print_is_day_scoped_and_does_not_mark_any_shift(self, env):
        ctrl, printer, financial_svc = env
        assert ctrl.print_daily_summary(target_date=DAY_2) is True

        payload = printer.print_shift_summary.call_args.args[0]
        assert payload["grand_total"] == {"count": 3, "revenue": 300.0}
        assert printer.print_shift_summary.call_args.kwargs["shift_period"] == {
            "from_date": "2026-03-11", "from_time": "00:00",
            "to_date": "2026-03-11", "to_time": "23:59:59",
        }
        assert payload["date"] == "2026-03-11"
        financial_svc.mark_summary_printed.assert_not_called()

    def test_print_with_shift_and_date_prints_nothing(self, env):
        ctrl, printer, financial_svc = env
        assert ctrl.print_daily_summary(shift_id=1, target_date=DAY_1) is False
        printer.print_shift_summary.assert_not_called()
        financial_svc.mark_summary_printed.assert_not_called()


# ---------------------------------------------------------------------------
# Bridge: the filter the UI can actually send
# ---------------------------------------------------------------------------

class TestBridgeFilter:

    @staticmethod
    def _call(env, action: str, payload: dict | None = None) -> dict:
        ctrl, *_ = env
        bridge = POSBridge.__new__(POSBridge)
        bridge._reports_ctrl = ctrl
        bridge._current_user = MagicMock()
        # H20: dispatch() revalidates the session from the DB on every call.
        bridge._auth = MagicMock()
        bridge._auth.refresh_current_user.return_value = bridge._current_user
        raw = POSBridge.dispatch(bridge, action, json.dumps(payload or {}))
        return json.loads(raw)

    def test_daily_report_by_shift(self, env):
        res = self._call(env, "get_report_daily_sales", {"shift_id": 1})
        assert res["success"] is True
        assert res["data"]["scope"] == "shift"
        assert res["data"]["gross_revenue"] == 250.0

    def test_daily_report_by_date(self, env):
        res = self._call(env, "get_report_daily_sales", {"date": "2026-03-11"})
        assert res["success"] is True
        assert res["data"]["scope"] == "day"
        assert res["data"]["gross_revenue"] == 300.0

    def test_daily_report_without_filter_is_today(self, env):
        res = self._call(env, "get_report_daily_sales")
        assert res["success"] is True
        assert res["data"]["scope"] == "day"
        assert res["data"]["date"] == date.today().isoformat()

    @pytest.mark.parametrize("payload", [
        {"shift_id": 1, "date": "2026-03-10"},   # both
        {"shift_id": 999},                        # unknown shift
        {"shift_id": "1"},                        # not an integer
        {"shift_id": True},                       # bool is not a shift id
        {"date": "10.03.2026"},                   # wrong format
    ])
    def test_daily_report_rejects_bad_scope(self, env, payload):
        res = self._call(env, "get_report_daily_sales", payload)
        assert res["success"] is False
        assert res["error"]

    def test_product_sales_follow_the_shift(self, env):
        res = self._call(env, "get_report_product_sales", {"shift_id": 2})
        assert res["success"] is True
        assert {p["product_name"]: p["quantity"] for p in res["data"]} == {"A": 1, "C": 1}

    def test_product_sales_follow_the_date(self, env):
        res = self._call(env, "get_report_product_sales", {"date": "2026-03-10"})
        assert res["success"] is True
        assert {p["product_name"]: p["quantity"] for p in res["data"]} == {"A": 2}

    def test_product_sales_respect_the_limit(self, env):
        res = self._call(env, "get_report_product_sales", {"date": "2026-03-11", "limit": 1})
        assert res["success"] is True
        assert len(res["data"]) == 1

    @pytest.mark.parametrize("payload", [
        {"shift_id": 1, "date": "2026-03-10"},
        {"shift_id": 999},
        {"date": "nonsense"},
    ])
    def test_product_sales_reject_bad_scope(self, env, payload):
        res = self._call(env, "get_report_product_sales", payload)
        assert res["success"] is False
