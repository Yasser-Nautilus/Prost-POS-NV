"""
Regression tests — simulated printer mode (PROST_PRINTER_SIMULATE=1).

Simulate ON:  every print job returns True and writes a JSON file to
              PRINTER_SIMULATE_OUTPUT_DIR (patched to a tmp dir).
Simulate OFF: no file written; a missing printer still returns False.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from broast_pos.infrastructure.printing import printer_manager as pm_module
from broast_pos.infrastructure.printing.printer_manager import PrinterManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manager() -> PrinterManager:
    m = PrinterManager()
    # No real printers — _printers stays empty
    return m


def _patch_simulate(tmp_path: Path, enabled: bool):
    """Patch PRINTER_SIMULATE and output dir for one test."""
    return (
        patch.object(pm_module, "PRINTER_SIMULATE", enabled),
        patch.object(pm_module, "PRINTER_SIMULATE_OUTPUT_DIR", str(tmp_path)),
    )


# ---------------------------------------------------------------------------
# Simulate ON — shift summary
# ---------------------------------------------------------------------------

class TestSimulateModeOn:

    def test_shift_summary_returns_true(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            result = pm.print_shift_summary({"total_sales": 100.0}, cashier_slot=1)
        assert result is True

    def test_shift_summary_writes_file(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            pm.print_shift_summary({"total_sales": 99.5}, cashier_slot=1)
        files = list(tmp_path.glob("*_shift_summary.json"))
        assert len(files) == 1

    def test_shift_summary_file_contains_data(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            pm.print_shift_summary({"total_sales": 42.0}, cashier_slot=1)
        f = next(tmp_path.glob("*_shift_summary.json"))
        payload = json.loads(f.read_text(encoding="utf-8"))
        assert payload["job"] == "shift_summary"
        assert payload["data"]["report"]["total_sales"] == 42.0

    def test_kitchen_ticket_returns_true(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            result = pm.print_kitchen_ticket_job({"invoice_no": "001"})
        assert result is True

    def test_kitchen_ticket_writes_file(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            pm.print_kitchen_ticket_job({"invoice_no": "002"})
        assert len(list(tmp_path.glob("*_kitchen_ticket.json"))) == 1

    def test_receipt_returns_true(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            result = pm.print_receipt({"order_id": 1}, cashier_slot=1)
        assert result is True

    def test_shift_transfer_returns_true(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            result = pm.print_shift_transfer({"from_cashier": "A"}, cashier_slot=1)
        assert result is True

    def test_driver_settlement_returns_true(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            result = pm.print_driver_settlement_job({"driver_id": 5}, cashier_slot=1)
        assert result is True

    def test_driver_summary_returns_true(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, True)
        with p1, p2:
            result = pm.print_driver_summary_job({"trips": 3}, cashier_slot=1)
        assert result is True


# ---------------------------------------------------------------------------
# Simulate OFF — no hardware → still fails as before
# ---------------------------------------------------------------------------

class TestSimulateModeOff:

    def test_shift_summary_returns_false_without_printer(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, False)
        with p1, p2:
            result = pm.print_shift_summary({"total_sales": 50.0}, cashier_slot=1)
        assert result is False

    def test_no_file_written_when_simulate_off(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, False)
        with p1, p2:
            pm.print_shift_summary({"total_sales": 50.0}, cashier_slot=1)
        assert list(tmp_path.iterdir()) == []

    def test_kitchen_ticket_returns_false_without_printer(self, tmp_path):
        pm = _manager()
        p1, p2 = _patch_simulate(tmp_path, False)
        with p1, p2:
            result = pm.print_kitchen_ticket_job({"invoice_no": "X"})
        assert result is False
