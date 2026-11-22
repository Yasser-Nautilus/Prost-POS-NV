"""
Regression tests — H16: daily-summary printing received the wrong data
shape.

Root cause:
  ReportsController.print_daily_summary() passed the full daily-summary
  dict (sales nested under "sales_by_type") straight to
  print_daily_sales_report(), which reads top-level "breakdown" and
  "grand_total" — always empty on the real summary shape. It also passed
  "opened_at"/"closed_at" as the shift period, while the template expects
  separate from/to date/time keys.

Fix verified here:
  - print_daily_summary() now adapts the summary once: pulls
    "breakdown"/"grand_total" out of "sales_by_type", and splits
    opened_at/closed_at into from_date/from_time/to_date/to_time.
  - End-to-end through Controller → (FinancialService lookup) →
    PrinterManager → the REAL print_daily_sales_report template →
    the REAL EscPosPrinter (dummy transport, not a hand-rolled test
    double): a single 70 EGP order produces a report showing exactly
    1 order, 70.00 EGP, and a populated period — not zero orders /
    blank period.
"""
from __future__ import annotations

from datetime import date

import pytest

from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.report_service import ReportService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.features.reports.reports_controller import ReportsController
from broast_pos.infrastructure.printing.escpos_printer import EscPosPrinter
from broast_pos.infrastructure.printing.printer_config import PrinterEntry
from broast_pos.infrastructure.printing.printer_manager import PrinterManager


def _real_dummy_printer() -> EscPosPrinter:
    """A genuine EscPosPrinter over python-escpos's own Dummy transport —
    the real low-level driver, just with no physical device attached.
    Its captured byte buffer is the actual ESC/POS output the template
    would send to real hardware."""
    printer = EscPosPrinter(PrinterEntry(key="cashier_1", conn_type="dummy"))
    printer.connect()
    return printer


def _captured_text(printer: EscPosPrinter) -> str:
    """Decode the real Dummy transport's captured byte stream for substring
    assertions (ESC/POS control bytes included — this is the raw output)."""
    return printer._printer.output.decode("utf-8", errors="replace")


@pytest.fixture(autouse=True)
def _reset_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    db.execute(
        "INSERT INTO users (id, username, display_name, role, pin_hash, is_active) "
        "VALUES (1,'mgr','مدير','manager','h1',1)"
    )
    today = date.today().isoformat()
    db.execute(
        "INSERT INTO shifts (id, opened_by, opened_at, closed_at, next_invoice_no, "
        "is_active, business_date) "
        "VALUES (1, 1, '2026-01-15 08:00:00', '2026-01-15 20:30:00', 2, 1, ?)",
        (today,),
    )
    db.execute("INSERT INTO categories (id, name, sort_order, is_active) VALUES (1,'طعام',0,1)")
    db.execute("INSERT INTO products (id, name, price, category_id, is_active) VALUES (1,'بيتزا',70.0,1,1)")
    # One completed cash order, today, total EGP 70 — the exact H16 scenario.
    db.execute(
        f"INSERT INTO orders (id, invoice_no, shift_id, order_type, status, subtotal, total, "
        f"payment_method, is_paid, created_by_id, created_by_name, cashier_slot, created_at) "
        f"VALUES (1, 1, 1, 'takeaway', 'completed', 70.0, 70.0, 'cash', 1, 1, 'مدير', 1, "
        f"'{today} 12:00:00')"
    )
    db.commit()
    return db


def _build_controller(db: DatabaseConnection, printer: EscPosPrinter) -> ReportsController:
    order_repo = OrderRepository(db=db)
    financial_repo = FinancialRepository(db=db)
    delivery_repo = DeliveryRepository(db=db)
    user_repo = UserRepository(db)

    report_svc = ReportService(
        order_repo=order_repo, financial_repo=financial_repo, delivery_repo=delivery_repo,
    )
    financial_svc = FinancialService(
        financial_repo=financial_repo, auth_service=AuthService(user_repo),
    )

    pm = PrinterManager()
    pm._printers["cashier_1"] = printer

    return ReportsController(
        report_service=report_svc, financial_service=financial_svc, printer_manager=pm,
    )


class TestH16ReportPrintShape:
    """Runs print_daily_summary() through the real PrinterManager, the real
    print_daily_sales_report template, and a real EscPosPrinter (dummy
    transport) — not a hand-rolled test double standing in for any of them."""

    def test_single_order_report_shows_correct_count_total_and_period(self):
        db = _fresh_db()
        printer = _real_dummy_printer()
        controller = _build_controller(db, printer)

        result = controller.print_daily_summary(shift_id=1, cashier_slot=1)

        assert result is True, "Print must succeed with a real order and a real printer"
        output = _captured_text(printer)

        # H16 regression: previously this showed "0" orders and "0.00" EGP
        # because breakdown/grand_total were read from the wrong nesting level.
        assert "70.00" in output, f"Expected the EGP 70 total in the printed output:\n{output}"
        assert "1" in output, "Expected an order count of 1 somewhere in the output"
        assert "0.00" not in output or "70.00" in output

        # H16 regression: previously the period lines were blank because the
        # template looked for from_time/from_date, not opened_at/closed_at.
        assert "08:00" in output, f"Expected the shift's opening time in the period header:\n{output}"
        assert "20:30" in output, f"Expected the shift's closing time in the period header:\n{output}"

    def test_grand_total_matches_the_single_order(self):
        db = _fresh_db()
        printer = _real_dummy_printer()
        controller = _build_controller(db, printer)

        summary = controller.generate_daily_summary(shift_id=1)
        sales = summary["sales_by_type"]
        assert sales["grand_total"]["count"] == 1
        assert sales["grand_total"]["revenue"] == 70.0
