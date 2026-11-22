"""
Regression tests — H15: receipt templates reported success even when
low-level printing failed.

Root cause:
  EscPosPrinter's low-level methods (print_text, print_line,
  print_double_line, cut) each return a bool, but every template function
  in receipt_templates.py called them and then unconditionally returned
  True — a text/line/cut failure anywhere in the job was invisible to the
  caller. The old PrintingFlowController and PrinterManager already
  propagate whatever the template returns (or catch a raised exception),
  so the fix had to land in the templates themselves.

Fix verified here:
  - Every template now aggregates each low-level call's result with AND
    and returns that aggregate — a single failed step anywhere in the job
    makes the whole job report failure, never "printed".
  - A failure does not short-circuit the job: every remaining line is
    still attempted (matches the hardware's actual behaviour — a failed
    line doesn't stop the paper feed), and the captured output below
    proves exactly what was (and wasn't) produced.
  - An exception raised during a print call is caught by EscPosPrinter
    itself (never raises) and already converts to False; PrinterManager
    and the old PrintingFlowController both already turn that into a
    failed job rather than "printed" — confirmed here too, so nothing
    upstream quietly re-labels a failure as success.
"""
from __future__ import annotations

from broast_pos.features.printing_flow.printing_controller import (
    PrintingFlowController,
)
from broast_pos.infrastructure.printing import receipt_templates as tpl
from broast_pos.infrastructure.printing.printer_manager import PrinterManager


class _FakePrinter:
    """Records every call it receives (the actual test output) and lets a
    test fail specific calls by index, or raise on a specific call."""

    def __init__(self, fail_at: set[int] | None = None, raise_at: int | None = None):
        self.calls: list[str] = []
        self._fail_at = fail_at or set()
        self._raise_at = raise_at
        self._n = 0

    def _step(self, label: str) -> bool:
        self.calls.append(label)
        self._n += 1
        if self._raise_at is not None and self._n == self._raise_at:
            raise RuntimeError(f"simulated hardware fault on call #{self._n}")
        return self._n not in self._fail_at

    def print_text(self, text, *, align="left", bold=False, double_width=False, double_height=False):
        return self._step(f"TEXT:{text}")

    def print_line(self, char="-", width=32):
        return self._step("LINE")

    def print_double_line(self, width=32):
        return self._step("DOUBLE_LINE")

    def cut(self):
        return self._step("CUT")


def _order() -> dict:
    return {
        "order_type": "dine_in",
        "cashier_slot": 1,
        "cashier_name": "كاشير",
        "table_no": 3,
        "invoice_no": 42,
        "items": [{"product_name": "برجر", "quantity": 2, "unit_price": 50.0, "total_price": 100.0}],
        "total": 100.0,
        "payment_method": "cash",
        "amount_paid": 100.0,
        "change_given": 0.0,
    }


class TestH15TemplateAggregatesRealOutcome:

    def test_all_steps_succeed_reports_true(self):
        printer = _FakePrinter()
        result = tpl.print_dinein_receipt(printer, _order())
        assert result is True
        assert any("برجر" in c for c in printer.calls), "Expected item line in captured output"
        assert "CUT" in printer.calls

    def test_single_failed_text_line_fails_whole_job(self):
        """H15 regression: previously this returned True regardless."""
        printer = _FakePrinter(fail_at={1})  # fail the very first call (header line)
        result = tpl.print_dinein_receipt(printer, _order())
        assert result is False, (
            "H15 regression: a failed print step must make the job report "
            "failure, not 'printed'"
        )
        # The job still attempted every remaining step (no short-circuit) —
        # proof via the captured output that the cut was still attempted.
        assert "CUT" in printer.calls

    def test_cut_failure_alone_fails_the_job(self):
        """Even if every text line printed, a failed cut is still a failure."""
        printer = _FakePrinter()
        # Fail only the very last call — find its index after a dry run.
        dry = _FakePrinter()
        tpl.print_dinein_receipt(dry, _order())
        last_call_index = len(dry.calls)

        printer = _FakePrinter(fail_at={last_call_index})
        result = tpl.print_dinein_receipt(printer, _order())
        assert result is False

    def test_kitchen_ticket_text_failure_is_not_reported_as_printed(self):
        printer = _FakePrinter(fail_at={3})
        result = tpl.print_kitchen_ticket(printer, _order())
        assert result is False


class TestH15ExceptionNeverBecomesSuccess:

    def test_printer_manager_turns_exception_into_failure(self):
        """An exception mid-job must surface as a failed print_receipt call,
        not a silent success — PrinterManager already guarantees this; this
        test locks that guarantee in place alongside the template fix."""
        pm = PrinterManager()
        failing_printer = _FakePrinter(raise_at=5)
        pm._printers["cashier_1"] = failing_printer  # bypass hardware connect

        result = pm.print_receipt(_order(), cashier_slot=1)
        assert result is False

    def test_old_printing_flow_controller_reports_failure_on_exception(self):
        """The pre-existing PrintingFlowController wraps everything in
        try/except and already returns False — confirmed here per MO's ask
        to also check the old controller."""
        pm = PrinterManager()
        failing_printer = _FakePrinter(raise_at=5)
        pm._printers["cashier_1"] = failing_printer

        class _Triggers:
            def on_order_completed(self, order_dict, cashier_slot):
                ok = pm.print_receipt(order_dict, cashier_slot=cashier_slot)
                if not ok:
                    raise RuntimeError("print failed")

        controller = PrintingFlowController(printer_manager=pm, print_triggers=_Triggers())
        result = controller.print_customer_receipt(_order(), cashier_slot=1)

        assert result is False
        assert controller.failure_count == 1
