"""
Prost POS — Application entry point.

Startup sequence:
    1. Configure logging
    2. Load config (restaurant.json)
    3. Initialise database + run migrations + seed if empty
    4. Create service instances (order, financial, auth, product)
    5. Create QApplication, apply theme
    6. Show login window → on login → show main window
    7. Wire order confirm flow end-to-end
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

from broast_pos.config import config
from broast_pos.config.config import LOGS_PATH, get_app_name
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.customer_service import CustomerService
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.driver_settlement_service import DriverSettlementService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.product_service import ProductService
from broast_pos.core.services.report_service import ReportService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import (
    ensure_menu_products,
    seed_database,
    validate_no_default_admin,
)
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.customer_repository import CustomerRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.driver_settlement_repository import (
    DriverSettlementRepository,
)
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.order_status_history_repository import (
    OrderStatusHistoryRepository,
)
from broast_pos.data.repositories.product_repository import ProductRepository
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers
from broast_pos.infrastructure.printing.printer_manager import PrinterManager
from broast_pos.infrastructure.web_bridge.bridge import POSBridge
from broast_pos.ui.styles.theme import apply_theme

# NOTE: WebShell is imported lazily inside main() — QWebEngineWidgets
# must be imported AFTER QApplication is created per Qt6 requirements.

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logger with console + rotating file output."""
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    log_dir = Path(LOGS_PATH)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Rotating file handler (5 MB × 3 backups)
    file_handler = RotatingFileHandler(
        str(log_dir / "prost_pos.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def _configure_printing(printer_manager: PrinterManager) -> PrintTriggers:
    """H14: initialise all configured printers and build print-trigger wiring.

    Extracted out of main() so tests can exercise this exact startup step
    (with a safe dummy transport) instead of re-implementing it.
    """
    printer_manager.initialise()
    return PrintTriggers(printer_manager)


def _wire_printer_shutdown(app: QApplication, printer_manager: PrinterManager) -> None:
    """H14: disconnect printers gracefully on app exit.

    Extracted out of main() so tests can verify this exact wiring runs the
    real shutdown() method, not a hand-rolled stand-in.
    """
    app.aboutToQuit.connect(printer_manager.shutdown)


def main() -> int:
    """Application entry point — returns exit code."""
    _setup_logging()
    logger.info("Starting %s …", get_app_name())

    # ------------------------------------------------------------------
    # 0. Configuration & Security Pre-flight
    # ------------------------------------------------------------------
    try:
        config.validate_production_secrets()
    except Exception as exc:
        logger.critical("Security configuration check failed: %s", exc)
        return 1

    # ------------------------------------------------------------------
    # 1. Database
    # ------------------------------------------------------------------
    try:
        db = DatabaseConnection.get_instance()
        initialise_database(db)
        seed_database(db)
        try:
            ensure_menu_products(db)
        except Exception:  # noqa: BLE001 - menu import must never block startup
            logger.exception("Menu import failed; continuing without it")
        validate_no_default_admin(db)
        logger.info("Database ready (WAL mode)")
    except Exception as exc:
        logger.critical("Database init failed: %s", exc)
        return 1

    # ------------------------------------------------------------------
    # 2. Repositories
    # ------------------------------------------------------------------
    user_repo = UserRepository(db)
    product_repo = ProductRepository(db)
    order_repo = OrderRepository(db)
    audit_repo = AuditRepository(db)
    financial_repo = FinancialRepository(db)
    delivery_repo = DeliveryRepository(db)
    customer_repo = CustomerRepository(db)
    status_history_repo = OrderStatusHistoryRepository(db)
    settlement_repo = DriverSettlementRepository(db)
    cashier_session_repo = CashierSessionRepository(db)
    cash_ledger_repo = CashLedgerRepository(db)

    # ------------------------------------------------------------------
    # 3. Services
    # ------------------------------------------------------------------
    auth_service = AuthService(user_repo)
    auth_service.set_audit(audit_repo)
    product_service = ProductService(product_repo)
    customer_service = CustomerService(customer_repo)
    audit_service = AuditService(audit_repo)

    delivery_service = DeliveryService(
        delivery_repo=delivery_repo,
        user_repo=user_repo,
        audit_repo=audit_repo,
        # order_service injected below after order_service is created
    )
    financial_service = FinancialService(
        financial_repo=financial_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        delivery_service=delivery_service,
        cash_ledger_repo=cash_ledger_repo,
        cashier_session_repo=cashier_session_repo,
    )
    cashier_session_service = CashierSessionService(
        session_repo=cashier_session_repo,
        ledger_repo=cash_ledger_repo,
        auth_service=auth_service,
    )
    order_service = OrderService(
        order_repo=order_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        financial_service=financial_service,
        status_history_repo=status_history_repo,
        audit_service=audit_service,
        session_service=cashier_session_service,
        ledger_repo=cash_ledger_repo,
        cashier_session_repo=cashier_session_repo,
        product_repo=product_repo,
    )
    # Inject order_service back into delivery_service for status history recording
    delivery_service.set_order_service(order_service)

    settlement_service = DriverSettlementService(
        settlement_repo=settlement_repo,
        delivery_repo=delivery_repo,
        order_repo=order_repo,
        user_repo=user_repo,
        audit_repo=audit_repo,
        order_svc=order_service,
        ledger_repo=cash_ledger_repo,
        cashier_session_repo=cashier_session_repo,
    )
    # Driver settlement books the driver's delivery fees as an expense
    settlement_service._expense_recorder = financial_service
    report_service = ReportService(
        order_repo=order_repo,
        financial_repo=financial_repo,
        delivery_repo=delivery_repo,
    )
    business_day_service = BusinessDayService(
        financial_service=financial_service,
        session_repo=cashier_session_repo,
        ledger_repo=cash_ledger_repo,
        auth_service=auth_service,
        delivery_repo=delivery_repo,
    )

    # ------------------------------------------------------------------
    # 4. Printing infrastructure
    # ------------------------------------------------------------------
    printer_manager = PrinterManager()
    print_triggers = _configure_printing(printer_manager)

    # ------------------------------------------------------------------
    # 5. Qt Application
    # ------------------------------------------------------------------
    # Qt6 requirement: AA_ShareOpenGLContexts MUST be set before QApplication
    # when QtWebEngineWidgets is used — otherwise ImportError on web_shell import.
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(get_app_name())

    # Apply dark theme + Arabic font + RTL
    apply_theme(app)

    # ------------------------------------------------------------------
    # 6. Web UI Shell and Bridge Initialization
    # ------------------------------------------------------------------
    # Lazy import — QWebEngineWidgets must be imported AFTER QApplication is created
    from broast_pos.ui.web_shell import WebShell

    bridge = POSBridge(
        auth_service=auth_service,
        product_service=product_service,
        customer_service=customer_service,
        delivery_service=delivery_service,
        financial_service=financial_service,
        order_service=order_service,
        report_service=report_service,
        print_triggers=print_triggers,
        printer_manager=printer_manager,
        settlement_service=settlement_service,
        audit_service=audit_service,
        session_service=cashier_session_service,
        business_day_service=business_day_service,
    )

    shell = WebShell(bridge)
    shell.show()

    # Disconnect printers gracefully on app exit
    _wire_printer_shutdown(app, printer_manager)

    # ------------------------------------------------------------------
    # 7. Background Tasks
    # ------------------------------------------------------------------
    # Periodic timer to auto-complete expired paid takeaway orders (every 60s)
    takeaway_timer = QTimer(shell)
    takeaway_timer.timeout.connect(lambda: order_service.auto_complete_expired_takeaways())
    takeaway_timer.start(60_000)

    logger.info("Application ready — showing modernized QWebEngineView Web UI shell")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

