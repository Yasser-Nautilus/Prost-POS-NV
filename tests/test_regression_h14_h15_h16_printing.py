"""
Regression tests — H14/H15/H16: printing infrastructure.

H14: PrinterManager.initialise() was never called in main.py, so _printers
     stayed empty and every print job returned False silently.

H15: print_daily_summary() caught all exceptions and returned bare False.
     The bridge then emitted a generic Arabic error.  The specific root cause
     was invisible to operators.  Fix: let exceptions propagate so the bridge
     captures str(e) in its outer except clause.

H16: print_daily_summary() passed the full generate_daily_summary() dict to
     print_shift_summary(), but print_daily_sales_report() reads
     report["breakdown"] and report["grand_total"] — keys that only exist one
     level deeper under report["sales_by_type"].
     Also the shift_period dict used keys "opened_at"/"closed_at" but the
     template expects "from_time"/"from_date"/"to_time"/"to_date".

All tests use fake printers — no real hardware required.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from broast_pos.infrastructure.printing.printer_manager import PrinterManager


# ---------------------------------------------------------------------------
# Fake printer helpers
# ---------------------------------------------------------------------------

class _FakeEscPosPrinter:
    """Records calls instead of printing to a physical device."""

    def __init__(self):
        self.is_connected = True
        self.calls: list[tuple[str, Any]] = []

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def print_text(self, text: str, **kw) -> None:
        self.calls.append(("text", text))

    def print_line(self, char: str, width: int) -> None:
        self.calls.append(("line", char * width))

    def print_double_line(self, width: int) -> None:
        self.calls.append(("double_line", "=" * width))

    def cut(self) -> None:
        self.calls.append(("cut", None))

    def printed_text(self) -> str:
        return "\n".join(str(v) for _, v in self.calls if v is not None)


def _make_manager_with_fake_printers() -> tuple[PrinterManager, _FakeEscPosPrinter]:
    """Return a PrinterManager whose kitchen/cashier printers are fakes."""
    mgr = PrinterManager()
    fake = _FakeEscPosPrinter()
    mgr._printers = {
        "kitchen": fake,
        "cashier_1": fake,
        "cashier_2": fake,
    }
    return mgr, fake


# ---------------------------------------------------------------------------
# H14 — initialise() must populate _printers
# ---------------------------------------------------------------------------

class TestH14PrinterInit:

    def test_uninitialised_manager_has_no_printers(self):
        """Before initialise(), _printers is empty → all jobs return False."""
        mgr = PrinterManager()
        assert mgr._printers == {}, "_printers should be empty before initialise()"

    def test_print_job_returns_false_without_init(self):
        """Kitchen print job on an uninitialised manager must return False."""
        mgr = PrinterManager()
        result = mgr.print_kitchen_ticket_job({"id": 1, "items": []})
        assert result is False, "print_kitchen_ticket_job must return False when printers not initialised"

    def test_initialise_populates_printers(self):
        """After initialise() is called (mocked config), _printers is populated."""
        mgr = PrinterManager()
        fake_config = {
            "kitchen": {"connection": "usb", "vendor_id": "0x0001", "product_id": "0x0002"},
            "cashier_1": {"connection": "usb", "vendor_id": "0x0003", "product_id": "0x0004"},
        }
        with patch("broast_pos.infrastructure.printing.printer_manager.load_printer_config", return_value=fake_config), \
             patch("broast_pos.infrastructure.printing.printer_manager.EscPosPrinter") as MockPrinter:
            fake_p = MagicMock()
            fake_p.connect.return_value = True
            MockPrinter.return_value = fake_p
            mgr.initialise()
        assert len(mgr._printers) == 2, f"Expected 2 printers after initialise, got {len(mgr._printers)}"


# ---------------------------------------------------------------------------
# H15 — failures must propagate, not be silently swallowed
# ---------------------------------------------------------------------------

class TestH15FailurePropagation:

    def test_print_daily_summary_raises_when_printer_none(self):
        """print_daily_summary must raise (not return False) when printer is None."""
        from broast_pos.features.reports.reports_controller import ReportsController

        ctrl = ReportsController(
            report_service=MagicMock(),
            financial_service=MagicMock(),
            printer_manager=None,
        )
        with pytest.raises(Exception):
            ctrl.print_daily_summary(shift_id=1)

    def test_print_daily_summary_raises_on_template_error(self):
        """print_daily_summary must propagate an exception from the print template."""
        from broast_pos.features.reports.reports_controller import ReportsController

        mock_report_svc = MagicMock()
        mock_report_svc.generate_daily_sales.return_value = {
            "breakdown": [], "grand_total": {"count": 0, "revenue": 0.0}
        }
        mock_report_svc.generate_payment_breakdown.return_value = {"payments": [], "total": 0.0}
        mock_report_svc.generate_cancelled_orders.return_value = {"count": 0, "orders": []}
        mock_report_svc.generate_product_sales.return_value = []
        mock_report_svc.generate_driver_summary.return_value = []
        mock_report_svc._orders.get_completed_for_date.return_value = []

        mock_fin_svc = MagicMock()
        mock_fin_svc._financial.get_by_id.return_value = None

        mock_printer = MagicMock()
        mock_printer.print_shift_summary.side_effect = RuntimeError("injected printer failure")

        ctrl = ReportsController(
            report_service=mock_report_svc,
            financial_service=mock_fin_svc,
            printer_manager=mock_printer,
        )

        with pytest.raises(RuntimeError, match="injected printer failure"):
            ctrl.print_daily_summary(shift_id=1)


# ---------------------------------------------------------------------------
# H16 — data shape: template must receive sales_by_type subdict
# ---------------------------------------------------------------------------

class TestH16DataShape:

    def _make_summary(self) -> dict:
        return {
            "date": "2024-01-15",
            "generated_at": datetime.now().isoformat(),
            "sales_by_type": {
                "breakdown": [
                    {"type": "dine_in", "label": "صالة", "count": 10, "revenue": 1500.0},
                ],
                "grand_total": {"count": 10, "revenue": 1500.0},
            },
            "payment_breakdown": {"payments": [], "total": 0.0},
            "gross_revenue": 1500.0,
            "restaurant_revenue": 1500.0,
            "total_delivery_fees": 0.0,
            "cancelled": {"count": 0, "orders": []},
            "bestsellers": [],
            "driver_summary": [],
            "shift_summary": None,
        }

    def test_print_shift_summary_receives_breakdown_key(self):
        """printer_manager.print_shift_summary must be called with a dict
        that has a top-level 'breakdown' key (the sales_by_type subdict),
        not the full generate_daily_summary() output."""
        from broast_pos.features.reports.reports_controller import ReportsController

        summary = self._make_summary()

        mock_report_svc = MagicMock()
        mock_fin_svc = MagicMock()
        mock_fin_svc._financial.get_by_id.return_value = None

        captured: list[dict] = []

        def fake_print_shift_summary(report, cashier_slot=1, shift_period=None):
            captured.append(report)
            return True

        mock_printer = MagicMock()
        mock_printer.print_shift_summary.side_effect = fake_print_shift_summary

        ctrl = ReportsController(
            report_service=mock_report_svc,
            financial_service=mock_fin_svc,
            printer_manager=mock_printer,
        )

        with patch.object(ctrl, "generate_daily_summary", return_value=summary):
            ctrl.print_daily_summary(shift_id=1)

        assert captured, "print_shift_summary was not called"
        passed_report = captured[0]
        assert "breakdown" in passed_report, (
            f"print_shift_summary received wrong shape — no 'breakdown' key. "
            f"Got keys: {list(passed_report.keys())}"
        )
        assert "grand_total" in passed_report, (
            f"print_shift_summary received wrong shape — no 'grand_total' key. "
            f"Got keys: {list(passed_report.keys())}"
        )

    def test_shift_period_has_correct_keys_for_template(self):
        """The shift_period dict passed to print_shift_summary must use
        the keys from_time/from_date/to_time/to_date, not opened_at/closed_at."""
        from broast_pos.features.reports.reports_controller import ReportsController

        summary = self._make_summary()

        mock_report_svc = MagicMock()

        fake_shift = MagicMock()
        fake_shift.opened_at = "2024-01-15T08:00:00"
        fake_shift.closed_at = "2024-01-15T23:00:00"
        mock_fin_svc = MagicMock()
        mock_fin_svc._financial.get_by_id.return_value = fake_shift

        captured_period: list[dict] = []

        def fake_print_shift_summary(report, cashier_slot=1, shift_period=None):
            captured_period.append(shift_period or {})
            return True

        mock_printer = MagicMock()
        mock_printer.print_shift_summary.side_effect = fake_print_shift_summary

        ctrl = ReportsController(
            report_service=mock_report_svc,
            financial_service=mock_fin_svc,
            printer_manager=mock_printer,
        )

        with patch.object(ctrl, "generate_daily_summary", return_value=summary):
            ctrl.print_daily_summary(shift_id=1)

        assert captured_period, "print_shift_summary was not called"
        period = captured_period[0]
        assert "from_time" in period, (
            f"shift_period missing 'from_time' key — got {list(period.keys())}"
        )
        assert "from_date" in period, (
            f"shift_period missing 'from_date' key — got {list(period.keys())}"
        )
        assert "to_time" in period, (
            f"shift_period missing 'to_time' key — got {list(period.keys())}"
        )
        assert "to_date" in period, (
            f"shift_period missing 'to_date' key — got {list(period.keys())}"
        )
