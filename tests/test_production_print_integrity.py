"""Production printing must never pass through dummy or simulation success."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QCoreApplication
from test_e2e_user_flows import _build_test_bridge

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.infrastructure.printing import escpos_printer as ep
from broast_pos.infrastructure.printing import printer_config as pc
from broast_pos.infrastructure.printing import printer_manager as pm


@pytest.fixture(autouse=True)
def reset_cache():
    pc._config_cache = None
    yield
    pc._config_cache = None
    DatabaseConnection.reset()


@pytest.mark.parametrize("contents", [None, "{broken", "[]", '{"cashier_1": null}', '{"cashier_1": {}}', '{"cashier_1": {"type":"dummy"}}', '{"cashier_1": {"type":"typo"}}'])
def test_bad_production_config_never_ready_or_successful(tmp_path, monkeypatch, contents):
    monkeypatch.setenv("APP_ENV", "prod")
    path = tmp_path / "printers.json"
    if contents is not None:
        path.write_text(contents)
    monkeypatch.setattr(pc, "PRINTER_CONFIG_PATH", str(path))
    monkeypatch.setattr(pm, "PRINTER_SIMULATE", False)
    manager = pm.PrinterManager()
    try:
        manager.initialise()
        assert not any(manager.get_status().values())
        assert manager.is_printer_available("cashier_1") is False
        assert manager.print_shift_summary({}) is False
        assert manager.print_receipt({}) is False
        assert manager.print_kitchen_ticket_job({}) is False
    finally:
        manager.shutdown()


@pytest.mark.parametrize("kind", ["usb", "network", "serial"])
def test_missing_driver_is_not_dummy_success_even_in_dev(monkeypatch, kind):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setattr(ep, "ESCPOS_AVAILABLE", False)
    printer = ep.EscPosPrinter(pc.PrinterEntry("cashier_1", kind, vendor_id="0x1234", product_id="0x5678", host="192.0.2.1", device="/dev/test"))
    assert printer.connect() is False
    assert printer.print_text("test") is False
    assert printer.is_connected is False


def test_explicit_development_dummy_remains_available(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setattr(ep, "ESCPOS_AVAILABLE", False)
    printer = ep.EscPosPrinter(pc.PrinterEntry("cashier_1", "dummy"))
    assert printer.connect() is True
    assert printer.print_text("development only") is True
    printer.disconnect()


@pytest.mark.parametrize("simulate", [False, True])
def test_real_bridge_failed_report_never_satisfies_close_prerequisite(tmp_path, monkeypatch, simulate):
    # Seed synthetic development data, then exercise the print boundary in prod.
    monkeypatch.setenv("APP_ENV", "dev")
    app = QCoreApplication.instance() or QCoreApplication(["print-integrity-test"])
    DatabaseConnection.reset()
    bridge, db = _build_test_bridge(app)
    assert json.loads(bridge.dispatch("login", '{"pin":"1234"}'))["success"]
    assert json.loads(bridge.dispatch("open_shift", "{}"))["success"]
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setattr(pc, "PRINTER_CONFIG_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setattr(pm, "PRINTER_SIMULATE", simulate)
    monkeypatch.setattr(pm, "PRINTER_SIMULATE_OUTPUT_DIR", str(tmp_path / "output"))
    manager = pm.PrinterManager()
    manager.initialise()
    bridge._printer = manager
    bridge._reports_ctrl._printer = manager
    result = json.loads(bridge.dispatch("print_shift_summary", "{}"))
    assert result["success"] is False
    assert db.fetch_one("SELECT summary_printed_at FROM shifts")["summary_printed_at"] is None
    assert not (tmp_path / "output").exists()
    close = json.loads(bridge.dispatch("close_shift", "{}"))
    assert close["success"] is False
    assert db.fetch_one("SELECT is_active FROM shifts")["is_active"] == 1
    manager.shutdown()


def test_real_transport_path_preserved_without_touching_hardware(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setattr(ep, "ESCPOS_AVAILABLE", True)
    with patch.object(ep, "Network", create=True) as network:
        printer = ep.EscPosPrinter(pc.PrinterEntry("cashier_1", "network", host="192.0.2.1"))
        assert printer.connect() is True
        assert printer.print_text("transport test") is True
        network.assert_called_once_with("192.0.2.1", port=9100)
        network.return_value.text.assert_called_once_with("transport test\n")
        printer.disconnect()


@pytest.mark.parametrize("kind", ["usb", "network", "serial"])
def test_incomplete_physical_configuration_does_not_guess_device(monkeypatch, kind):
    monkeypatch.setenv("APP_ENV", "prod")
    printer = ep.EscPosPrinter(pc.PrinterEntry("cashier_1", kind))
    assert printer.connect() is False
    assert printer.print_text("test") is False
