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
from unittest.mock import MagicMock, patch

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


class TestH14RealMainCompositionWiring:
    """Calls broast_pos.main's actual startup/shutdown functions directly —
    the real code path main() runs, not a re-implementation of its steps.
    Only the printer transport is a dummy; PrinterManager, EscPosPrinter and
    QApplication are all the genuine classes."""

    def test_real_configure_printing_initialises_printers(self):
        from broast_pos.infrastructure.printing.print_triggers import PrintTriggers
        from broast_pos.main import _configure_printing

        with patch(
            "broast_pos.infrastructure.printing.printer_manager.load_printer_config",
            return_value=_dummy_config(),
        ):
            printer_manager = PrinterManager()
            # The real function main() calls — not a re-implementation.
            print_triggers = _configure_printing(printer_manager)

        assert isinstance(print_triggers, PrintTriggers)
        assert printer_manager.is_printer_available("kitchen") is True
        assert printer_manager.is_printer_available("cashier_1") is True
        assert printer_manager.is_printer_available("cashier_2") is True

    def test_real_shutdown_wiring_disconnects_printers_on_quit(self):
        """A real QApplication, with the real signal connection main() makes —
        firing aboutToQuit (not calling shutdown() directly) must disconnect."""
        from PyQt6.QtWidgets import QApplication

        from broast_pos.main import _configure_printing, _wire_printer_shutdown

        app = QApplication.instance() or QApplication([])

        with patch(
            "broast_pos.infrastructure.printing.printer_manager.load_printer_config",
            return_value=_dummy_config(),
        ):
            printer_manager = PrinterManager()
            _configure_printing(printer_manager)
            assert printer_manager.is_printer_available("kitchen") is True

            _wire_printer_shutdown(app, printer_manager)  # the real wiring call
            app.aboutToQuit.emit()  # simulates real app shutdown firing the signal

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
        # H20: dispatch() revalidates the session from the DB on every call.
        bridge._auth = MagicMock()
        bridge._auth.refresh_current_user.return_value = bridge._current_user

        resp = json.loads(bridge.dispatch("get_printer_status", json.dumps({})))

        assert resp["success"] is True
        assert resp["data"] == {"kitchen": True, "cashier_1": True, "cashier_2": True}

    def test_get_printer_status_without_printer_manager(self):
        bridge = bridge_module.POSBridge.__new__(bridge_module.POSBridge)
        bridge._printer = None
        bridge._current_user = _cashier()
        bridge._auth = MagicMock()
        bridge._auth.refresh_current_user.return_value = bridge._current_user

        resp = json.loads(bridge.dispatch("get_printer_status", json.dumps({})))

        assert resp["success"] is True
        assert resp["data"] == {}
