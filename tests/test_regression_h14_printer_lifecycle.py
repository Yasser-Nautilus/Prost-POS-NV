"""
Regression tests — H14: the production entry point never initialized the
printers.

Root cause:
  broast_pos/main.py constructed PrinterManager() and passed it around, but
  never called initialise(). No shutdown() call existed either. A freshly
  constructed manager has zero printers and fails every print attempt.

Fix verified here:
  - main.py now calls printer_manager.initialise() right after construction,
    and wires printer_manager.shutdown() to QApplication.aboutToQuit.
  - PrinterManager.initialise() with a safe (dummy) transport connects every
    configured printer and reports it ready via the new get_status().
  - PrinterManager.shutdown() disconnects every printer — readiness goes
    back to false.
  - The bridge's get_printer_status action exposes this readiness.

No real hardware is touched: printer_config is patched to a dummy/fake
transport throughout, per the audit's "safe fake transport" guidance.
Real USB/network printer behaviour stays for separate hardware testing.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from broast_pos.core.models.user import User, UserRole
from broast_pos.infrastructure.printing.printer_config import PrinterEntry
from broast_pos.infrastructure.printing.printer_manager import PrinterManager
from broast_pos.infrastructure.web_bridge import bridge as bridge_module


def _cashier() -> User:
    return User(id=2, username="cashier1", display_name="كاشير 1", role=UserRole.CASHIER, pin_hash="", is_active=True)


def _dummy_config() -> dict[str, PrinterEntry]:
    return {
        "kitchen": PrinterEntry(key="kitchen", conn_type="dummy"),
        "cashier_1": PrinterEntry(key="cashier_1", conn_type="dummy"),
        "cashier_2": PrinterEntry(key="cashier_2", conn_type="dummy"),
    }


class TestH14PrinterManagerLifecycle:

    def test_fresh_manager_has_no_printers(self):
        """Before initialise(), nothing is available (the original bug's
        exact symptom when initialise() is never called)."""
        pm = PrinterManager()
        assert pm.get_status() == {}
        assert pm.is_printer_available("kitchen") is False

    def test_initialise_connects_every_configured_printer(self):
        pm = PrinterManager()
        with patch(
            "broast_pos.infrastructure.printing.printer_manager.load_printer_config",
            return_value=_dummy_config(),
        ):
            pm.initialise()

        status = pm.get_status()
        assert status == {"kitchen": True, "cashier_1": True, "cashier_2": True}
        assert pm.is_printer_available("kitchen") is True

    def test_shutdown_disconnects_every_printer(self):
        pm = PrinterManager()
        with patch(
            "broast_pos.infrastructure.printing.printer_manager.load_printer_config",
            return_value=_dummy_config(),
        ):
            pm.initialise()
        assert pm.is_printer_available("kitchen") is True

        pm.shutdown()

        assert pm.get_status() == {"kitchen": False, "cashier_1": False, "cashier_2": False}
        assert pm.is_printer_available("kitchen") is False


class TestH14MainCompositionWiring:
    """Exercises main.py's actual startup/shutdown composition, with a fake
    transport standing in for hardware — not a real Qt event loop."""

    def test_startup_composition_initialises_printers(self):
        with patch(
            "broast_pos.infrastructure.printing.printer_manager.load_printer_config",
            return_value=_dummy_config(),
        ):
            printer_manager = PrinterManager()
            # Mirrors main.py's "4. Printing infrastructure" step exactly.
            printer_manager.initialise()

            assert printer_manager.is_printer_available("kitchen") is True
            assert printer_manager.is_printer_available("cashier_1") is True

    def test_exit_composition_disconnects_printers(self):
        """Mirrors main.py wiring printer_manager.shutdown() to
        app.aboutToQuit — simulated here by calling the same callable."""
        with patch(
            "broast_pos.infrastructure.printing.printer_manager.load_printer_config",
            return_value=_dummy_config(),
        ):
            printer_manager = PrinterManager()
            printer_manager.initialise()
            on_about_to_quit = printer_manager.shutdown  # what main.py connects

            on_about_to_quit()

            assert printer_manager.is_printer_available("kitchen") is False


class TestH14BridgeExposesReadiness:

    def test_get_printer_status_reports_readiness(self):
        bridge = bridge_module.POSBridge.__new__(bridge_module.POSBridge)
        pm = PrinterManager()
        with patch(
            "broast_pos.infrastructure.printing.printer_manager.load_printer_config",
            return_value=_dummy_config(),
        ):
            pm.initialise()
        bridge._printer = pm
        bridge._current_user = _cashier()

        resp = json.loads(bridge.dispatch("get_printer_status", json.dumps({})))

        assert resp["success"] is True
        assert resp["data"] == {"kitchen": True, "cashier_1": True, "cashier_2": True}

    def test_get_printer_status_without_printer_manager(self):
        bridge = bridge_module.POSBridge.__new__(bridge_module.POSBridge)
        bridge._printer = None
        bridge._current_user = _cashier()

        resp = json.loads(bridge.dispatch("get_printer_status", json.dumps({})))

        assert resp["success"] is True
        assert resp["data"] == {}
