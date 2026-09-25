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

from PyQt6.QtWidgets import QApplication, QMessageBox

from broast_pos.config.config import get_app_name
from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.customer_service import CustomerService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.product_service import ProductService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.customer_repository import CustomerRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.product_repository import ProductRepository
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.report_service import ReportService
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers
from broast_pos.infrastructure.printing.printer_manager import PrinterManager
from broast_pos.ui.styles.theme import apply_theme
from broast_pos.infrastructure.web_bridge.bridge import POSBridge
from broast_pos.ui.web_shell import WebShell

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logger with a simple console format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )



def main() -> int:
    """Application entry point — returns exit code."""
    _setup_logging()
    logger.info("Starting %s …", get_app_name())

    # ------------------------------------------------------------------
    # 1. Database
    # ------------------------------------------------------------------
    try:
        db = DatabaseConnection.get_instance()
        initialise_database(db)
        seed_database(db)
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

    # ------------------------------------------------------------------
    # 3. Services
    # ------------------------------------------------------------------
    auth_service = AuthService(user_repo)
    product_service = ProductService(product_repo)
    customer_service = CustomerService(customer_repo)
    delivery_service = DeliveryService(
        delivery_repo=delivery_repo,
        user_repo=user_repo,
    )
    financial_service = FinancialService(
        financial_repo=financial_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        delivery_service=delivery_service,
    )
    order_service = OrderService(
        order_repo=order_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        financial_service=financial_service,
    )
    report_service = ReportService(
        order_repo=order_repo,
        financial_repo=financial_repo,
        delivery_repo=delivery_repo,
    )

    # ------------------------------------------------------------------
    # 4. Printing infrastructure
    # ------------------------------------------------------------------
    printer_manager = PrinterManager()
    print_triggers = PrintTriggers(printer_manager)

    # ------------------------------------------------------------------
    # 5. Qt Application
    # ------------------------------------------------------------------
    app = QApplication(sys.argv)
    app.setApplicationName(get_app_name())

    # Apply dark theme + Arabic font + RTL
    apply_theme(app)

    # ------------------------------------------------------------------
    # 6. Web UI Shell and Bridge Initialization
    # ------------------------------------------------------------------
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
    )

    shell = WebShell(bridge)
    shell.show()

    logger.info("Application ready — showing modernized QWebEngineView Web UI shell")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

