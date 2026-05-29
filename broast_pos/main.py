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
from typing import Any, Optional

from PyQt6.QtWidgets import QApplication, QMessageBox

from broast_pos.config.config import get_app_name
from broast_pos.core.models.order import Order, OrderType
from broast_pos.core.models.user import User
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
from broast_pos.core.services.report_service import ReportService

from broast_pos.features.order_lifecycle.order_controller import (
    ConfirmResult,
    OrderController,
)
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers
from broast_pos.infrastructure.printing.printer_manager import PrinterManager
from broast_pos.ui.dialogs.payment_dialog import PaymentDialog
from broast_pos.ui.dialogs.shift_dialog import ShiftDialog
from broast_pos.ui.dialogs.expense_dialog import ExpenseDialog
from broast_pos.ui.dialogs.pin_dialog import PinDialog
from broast_pos.ui.styles.theme import apply_theme
from broast_pos.ui.views.pos_view import PosView
from broast_pos.ui.views.tracking_view import TrackingView
from broast_pos.ui.views.delivery_view import DeliveryView
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.features.delivery_system.delivery_controller import DeliveryController
from broast_pos.ui.windows.login_window import LoginWindow
from broast_pos.ui.windows.main_window import MainWindow, NavPage
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialog

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logger with a simple console format."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


class AppController:
    """Manages window lifecycle and order confirm flow.

    Owns both windows, services, and the order controller.
    Handles the full confirm → save → print → payment pipeline.
    """

    def __init__(
        self,
        auth_service: AuthService,
        product_service: ProductService,
        order_service: OrderService,
        financial_service: FinancialService,
        delivery_service: DeliveryService,
        customer_service: CustomerService,
        report_service: ReportService,
        print_triggers: PrintTriggers,
        printer_manager: PrinterManager,
    ) -> None:
        self._auth = auth_service
        self._product_svc = product_service
        self._order_svc = order_service
        self._financial_svc = financial_service
        self._delivery_svc = delivery_service
        self._customer_svc = customer_service
        self._report_svc = report_service
        self._print_triggers = print_triggers
        self._printer_mgr = printer_manager

        self._login_window = LoginWindow(auth_service)
        self._main_window: Optional[MainWindow] = None
        self._pos_view: Optional[PosView] = None
        self._order_ctrl: Optional[OrderController] = None
        self._current_user: Optional[User] = None

        # Wire login → show main
        self._login_window.login_complete.connect(self._on_login)

    # ------------------------------------------------------------------
    # Window transitions
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Show the login window — entry point."""
        self._login_window.show()

    def _on_login(self, user: User) -> None:
        """Login succeeded → hide login, create main window, wire confirm flow."""
        logger.info(
            "→ Logged in: %s (%s)", user.display_name, user.role.value
        )
        self._current_user = user
        self._login_window.hide()

        # Create a fresh main window for this session
        self._main_window = MainWindow(user)
        self._main_window.logout_requested.connect(self._on_logout)

        # Create order controller for this session
        self._order_ctrl = OrderController(
            order_service=self._order_svc,
            financial_service=self._financial_svc,
            auth_service=self._auth,
            print_triggers=self._print_triggers,
            cashier_slot=user.cashier_slot or 1,
        )

        # Inject the POS view (replaces the placeholder)
        self._pos_view = PosView(
            product_service=self._product_svc,
            customer_service=self._customer_svc,
            user_id=user.id or 0,
            user_name=user.display_name or user.username,
            cashier_slot=user.cashier_slot or 1,
        )
        self._main_window.set_view(NavPage.POS, self._pos_view)

        # Inject the Tracking view
        self._tracking_view = TrackingView(
            order_service=self._order_svc,
        )
        self._main_window.set_view(NavPage.TRACKING, self._tracking_view)

        # Inject the Delivery view
        self._delivery_ctrl = DeliveryController(
            delivery_service=self._delivery_svc,
            order_service=self._order_svc,
            print_triggers=self._print_triggers,
            cashier_slot=user.cashier_slot or 1,
        )
        self._delivery_view = DeliveryView(
            delivery_controller=self._delivery_ctrl,
        )
        self._main_window.set_view(NavPage.DELIVERY, self._delivery_view)

        # Inject the Reports view
        from broast_pos.features.reports.reports_controller import ReportsController
        from broast_pos.ui.views.reports_view import ReportsView
        self._reports_ctrl = ReportsController(
            report_service=self._report_svc,
            financial_service=self._financial_svc,
            printer_manager=self._printer_mgr,
        )
        self._reports_view = ReportsView(
            reports_controller=self._reports_ctrl,
            cashier_slot=user.cashier_slot or 1,
        )
        self._main_window.set_view(NavPage.REPORTS, self._reports_view)

        # Inject the Financial view
        from broast_pos.features.financial.financial_controller import FinancialController
        from broast_pos.ui.views.financial_view import FinancialView
        self._financial_ctrl = FinancialController(
            financial_service=self._financial_svc,
            auth_service=self._auth,
            printer_manager=self._printer_mgr,
        )
        self._financial_view = FinancialView(
            financial_controller=self._financial_ctrl,
            current_user_id=user.id or 0,
        )
        self._main_window.set_view(NavPage.FINANCIAL, self._financial_view)
        self._financial_view.shift_status_changed.connect(self._update_shift_badge)

        # Inject the Products view
        from broast_pos.ui.views.products_view import ProductsView
        self._products_view = ProductsView(
            product_service=self._product_svc,
            customer_service=self._customer_svc,
        )
        self._main_window.set_view(NavPage.PRODUCTS, self._products_view)

        # Inject the Users view
        from broast_pos.ui.views.users_view import UsersView
        self._users_view = UsersView(
            auth_service=self._auth,
        )
        self._main_window.set_view(NavPage.USERS, self._users_view)

        # Wire confirm flow: PosView → AppController → OrderController
        self._pos_view.order_confirmed.connect(self._on_order_confirmed)

        # Wire shift click in header
        self._main_window.shift_clicked.connect(self._show_shift_dialog)

        # Update initial shift badge
        self._update_shift_badge()

        self._main_window.show()

        # If no active shift, auto-prompt ShiftDialog
        try:
            self._financial_svc.ensure_shift_active()
        except ValueError:
            self._show_shift_dialog(auto_prompt=True)

    def _on_logout(self) -> None:
        """Logout requested → destroy main window, show login."""
        logger.info("← Logout — returning to login screen")
        self._auth.logout()

        self._pos_view = None
        self._tracking_view = None
        self._delivery_view = None
        self._delivery_ctrl = None
        self._reports_view = None
        self._reports_ctrl = None
        self._financial_view = None
        self._financial_ctrl = None
        self._products_view = None
        self._users_view = None
        self._order_ctrl = None
        self._current_user = None

        if self._main_window is not None:
            self._main_window.close()
            self._main_window.deleteLater()
            self._main_window = None

        self._login_window.reset()
        self._login_window.show()

    # ------------------------------------------------------------------
    # Order confirm flow
    # ------------------------------------------------------------------

    def _on_order_confirmed(self, order: Order) -> None:
        """Handle the confirmed order from PosView.

        Flow:
            1. Feed the order to OrderController.confirm_order()
            2. OrderController saves to DB + prints kitchen ticket
            3. If takeaway → show PaymentDialog immediately
            4. On payment → OrderController.complete_payment() → receipt
        """
        if self._order_ctrl is None or self._current_user is None:
            return

        user = self._current_user

        # Transfer order to controller for save
        self._order_ctrl._current_order = order
        success, result = self._order_ctrl.confirm_order(
            cashier_id=user.id or 0,
            cashier_name=user.display_name or user.username,
        )

        if not success:
            logger.warning("Order confirm failed: %s", result)
            self._show_error(str(result))
            return

        result: ConfirmResult = result
        logger.info(
            "Order saved → invoice #%d (needs_payment=%s)",
            result.invoice_no,
            result.needs_immediate_payment,
        )

        # Takeaway → immediate payment dialog
        if result.needs_immediate_payment and result.order_id:
            self._show_payment_dialog(
                order_id=result.order_id,
                total=order.total,
                order_type=order.order_type,
            )

    def _show_payment_dialog(
        self,
        order_id: int,
        total: float,
        order_type: OrderType,
    ) -> None:
        """Show payment dialog and handle the result."""
        dialog = PaymentDialog(
            total=total,
            order_type=order_type,
            parent=self._main_window,
        )

        def on_payment(method: str, amount: float) -> None:
            if self._order_ctrl is None:
                return
            ok, msg = self._order_ctrl.complete_payment(
                order_id=order_id,
                payment_method=method,
                amount_paid=amount,
            )
            if ok:
                logger.info("Payment completed: %s", msg)
            else:
                logger.warning("Payment failed: %s", msg)
                self._show_error(msg)

        dialog.payment_confirmed.connect(on_payment)
        dialog.exec()

    def _update_shift_badge(self) -> None:
        """Fetch current active shift and update header badge."""
        if not self._main_window:
            return
        try:
            active_shift = self._financial_svc.ensure_shift_active()
            self._main_window.update_shift_status(active=True, shift_id=active_shift.id)
        except ValueError:
            self._main_window.update_shift_status(active=False)

    def _show_shift_dialog(self, auto_prompt: bool = False) -> None:
        """Open the shift management dialog."""
        if not self._main_window or not self._current_user:
            return

        user = self._current_user

        def on_add_expense() -> None:
            dialog = ExpenseDialog(self._main_window)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                amount, category, description = dialog.get_data()
                try:
                    active_shift = self._financial_svc.ensure_shift_active()
                    self._financial_svc.add_expense(
                        shift_id=active_shift.id,
                        amount=amount,
                        description=description,
                        category=category,
                        user_id=user.id or 0,
                    )
                    logger.info("Expense of %s added successfully", amount)
                except Exception as exc:
                    self._show_error(str(exc))

        def on_close_shift() -> None:
            try:
                active_shift = self._financial_svc.ensure_shift_active()
            except ValueError:
                self._show_error("لا توجد وردية مفتوحة لإغلاقها")
                return

            pin_val = None
            def on_pin_verified(raw_pin: str) -> None:
                nonlocal pin_val
                pin_val = raw_pin

            pin_dialog = PinDialog(
                title="أدخل PIN المدير لإغلاق الوردية",
                verify_fn=self._auth.verify_pin,
                parent=self._main_window,
            )
            pin_dialog.pin_verified.connect(on_pin_verified)
            if pin_dialog.exec() == QDialog.DialogCode.Accepted and pin_val is not None:
                try:
                    self._financial_svc.close_shift(active_shift.id, pin_val)
                    self._update_shift_badge()
                    self._show_info("تم إغلاق الوردية بنجاح")
                except Exception as exc:
                    self._show_error(str(exc))

        def on_print_summary(shift_id: int) -> None:
            try:
                summary = self._financial_svc.get_shift_summary(shift_id)
                report = {
                    "shift_id": shift_id,
                    "total_sales": summary.total_sales,
                    "total_expenses": summary.total_expenses,
                    "pending_delivery": summary.pending_delivery,
                    "pending_dinein": summary.pending_dinein,
                    "pending_kitchen": summary.pending_kitchen,
                    "expected_cash": summary.expected_cash,
                    "order_breakdown": summary.order_breakdown,
                }
                slot = user.cashier_slot or 1
                self._printer_mgr.print_shift_summary(report, cashier_slot=slot)
            except Exception as exc:
                self._show_error(f"فشلت عملية الطباعة: {exc}")

        dialog = ShiftDialog(
            financial_service=self._financial_svc,
            user_id=user.id or 0,
            user_name=user.display_name or user.username,
            on_add_expense=on_add_expense,
            on_close_shift=on_close_shift,
            on_print_summary=on_print_summary,
            parent=self._main_window,
        )

        def on_state_changed(is_open: bool) -> None:
            self._update_shift_badge()

        dialog.shift_state_changed.connect(on_state_changed)
        dialog.exec()

    def _show_info(self, message: str) -> None:
        """Show a non-blocking info message."""
        if self._main_window:
            QMessageBox.information(
                self._main_window,
                "نجاح",
                message,
            )

    def _show_error(self, message: str) -> None:
        """Show a non-blocking error message."""
        if self._main_window:
            QMessageBox.warning(
                self._main_window,
                "خطأ",
                message,
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
    financial_service = FinancialService(
        financial_repo=financial_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
    )
    order_service = OrderService(
        order_repo=order_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        financial_service=financial_service,
    )
    delivery_service = DeliveryService(
        delivery_repo=delivery_repo,
        user_repo=user_repo,
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
    # 6. Window lifecycle controller (owns the full confirm flow)
    # ------------------------------------------------------------------
    controller = AppController(
        auth_service=auth_service,
        product_service=product_service,
        order_service=order_service,
        financial_service=financial_service,
        delivery_service=delivery_service,
        customer_service=customer_service,
        report_service=report_service,
        print_triggers=print_triggers,
        printer_manager=printer_manager,
    )
    controller.start()

    logger.info("Application ready — showing login window")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
