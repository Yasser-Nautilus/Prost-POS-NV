"""
Financial view — manages shift lifecycle, mid-day handovers, end-of-day closures,
records immutable cash expenses, and displays shift history.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QTime, Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QDoubleValidator, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from broast_pos.features.financial.financial_controller import FinancialController
from broast_pos.ui.styles.theme import get_color, get_font_family, _lighten
from broast_pos.ui.dialogs.pin_dialog import PinDialog
from broast_pos.ui.views.reports_view import (
    MetricCard,
    create_styled_table,
    make_bento_box,
)

logger = logging.getLogger(__name__)


class FinancialView(QWidget):
    """The central view for shift management and cash control."""

    # Emitted when a shift status changes (opened or closed)
    shift_status_changed = pyqtSignal()

    def __init__(
        self,
        financial_controller: FinancialController,
        current_user_id: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctrl = financial_controller
        self._user_id = current_user_id
        self._active_shift: Optional[Dict[str, Any]] = None

        self._setup_ui()
        self.refresh_state()

        # Periodic auto-refresh timer (every 15 seconds)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_state)
        self._refresh_timer.start(15000)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header title
        self._header = QLabel("الرقابة المالية والورديات 💵")
        self._header.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {get_color('text_primary')};
            margin-bottom: 4px;
        """)
        layout.addWidget(self._header)

        # State Stack: Page 0 is Open Shift, Page 1 is Tabbed Dashboard
        self._state_stack = QStackedWidget()
        layout.addWidget(self._state_stack, 1)

        # Build stack pages
        self._state_stack.addWidget(self._build_no_active_shift_page())
        self._state_stack.addWidget(self._build_dashboard_tabs_page())

    # ------------------------------------------------------------------
    # State 1: No Active Shift Page
    # ------------------------------------------------------------------

    def _build_no_active_shift_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # Centered frame
        card = QFrame()
        card.setFixedSize(500, 360)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 16px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 40, 30, 40)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)

        # Warning/Info Icon
        icon_lbl = QLabel("🏪")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 64px; border: none; background: transparent;")
        card_layout.addWidget(icon_lbl)

        # Title
        title_lbl = QLabel("لا توجد وردية مفتوحة حالياً")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {get_color('text_primary')};
            border: none;
            background: transparent;
        """)
        card_layout.addWidget(title_lbl)

        # Description
        desc_lbl = QLabel(
            "لبدء تلقي الطلبات وتسجيل المبيعات والمصروفات، يجب فتح وردية جديدة أولاً.\n"
            "ملاحظة: فتح الوردية سيقوم بتصفير ترقيم الفواتير ليبدأ من الرقم #1."
        )
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_secondary')};
            line-height: 1.5;
            border: none;
            background: transparent;
        """)
        card_layout.addWidget(desc_lbl)

        card_layout.addStretch()

        # Action Button
        open_btn = QPushButton("فتح وردية جديدة  🟢")
        open_btn.setFixedHeight(50)
        open_btn.setFixedWidth(280)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_confirm')};
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: {get_color('accent_green')};
            }}
        """)
        open_btn.clicked.connect(self._on_open_shift_clicked)
        card_layout.addWidget(open_btn)

        layout.addWidget(card)
        return page

    # ------------------------------------------------------------------
    # State 2: Tabbed Dashboard Page
    # ------------------------------------------------------------------

    def _build_dashboard_tabs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background-color: {get_color('primary_bg')};
            }}
            QTabBar::tab {{
                background-color: {get_color('secondary_bg')};
                color: {get_color('text_secondary')};
                border: 1px solid {get_color('border_color')};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 10px 24px;
                font-size: 14px;
                font-weight: bold;
                min-width: 130px;
            }}
            QTabBar::tab:selected {{
                background-color: {get_color('primary_bg')};
                color: {get_color('text_primary')};
                border-bottom: 1px solid {get_color('primary_bg')};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: rgba(255, 255, 255, 0.05);
            }}
        """)

        # Tab 1: Current active shift dashboard
        self._tabs.addTab(self._build_active_shift_tab(), "الوردية الحالية 🏪")
        # Tab 2: History of completed shifts
        self._tabs.addTab(self._build_history_tab(), "سجل الورديات 📂")

        layout.addWidget(self._tabs)
        return page

    def _build_active_shift_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        # 1. Metrics summary cards
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self._sales_card = MetricCard("مبيعات الوردية", "0.00 ج.م", "💰", get_color("accent_green"))
        self._expenses_card = MetricCard("المصروفات", "0.00 ج.م", "📉", get_color("accent_red"))
        self._expected_cash_card = MetricCard("الرصيد المتوقع (في الدرج)", "0.00 ج.م", "🏦", get_color("accent_blue"))
        self._pending_card = MetricCard("الطلبات المعلقة", "0 طلب", "🕒", get_color("accent_orange"))

        metrics_layout.addWidget(self._sales_card)
        metrics_layout.addWidget(self._expenses_card)
        metrics_layout.addWidget(self._expected_cash_card)
        metrics_layout.addWidget(self._pending_card)

        layout.addLayout(metrics_layout)

        # 2. Main split view layout
        split_layout = QHBoxLayout()
        split_layout.setSpacing(12)

        # Left side: Expense tracking section (Form + Table)
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Expense creation form
        form_widget = QWidget()
        form_layout = QHBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        self._expense_amount = QLineEdit()
        self._expense_amount.setPlaceholderText("المبلغ (مثال: 50.00)")
        self._expense_amount.setValidator(QDoubleValidator(0.0, 99999.0, 2))
        self._expense_amount.setStyleSheet(self._input_style())
        form_layout.addWidget(self._expense_amount, 1)

        self._expense_category = QComboBox()
        self._expense_category.addItem("أخرى", "other")
        self._expense_category.addItem("مشتريات ومستلزمات", "supplies")
        self._expense_category.addItem("مصاريف توصيل سائقين", "delivery_fees")
        self._expense_category.setStyleSheet(self._input_style())
        form_layout.addWidget(self._expense_category, 1)

        self._expense_desc = QLineEdit()
        self._expense_desc.setPlaceholderText("وصف المصروف...")
        self._expense_desc.setStyleSheet(self._input_style())
        form_layout.addWidget(self._expense_desc, 2)

        add_expense_btn = QPushButton("إضافة  ➕")
        add_expense_btn.setFixedHeight(40)
        add_expense_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_confirm')};
                color: #ffffff;
                font-weight: bold;
                border-radius: 8px;
                padding-left: 16px;
                padding-right: 16px;
            }}
            QPushButton:hover {{
                background-color: {_lighten(get_color('button_confirm'), 10)};
            }}
        """)
        add_expense_btn.clicked.connect(self._on_add_expense_clicked)
        form_layout.addWidget(add_expense_btn)

        expense_bento_layout = QVBoxLayout()
        expense_bento_layout.addLayout(form_layout)

        self._expenses_table = create_styled_table(["الوقت", "الفئة", "البيان/الوصف", "المبلغ"])
        expense_bento_layout.addWidget(self._expenses_table, 1)

        left_col.addWidget(make_bento_box("💸  إدارة وتسجيل المصروفات الصادرة", expense_bento_layout))
        split_layout.addLayout(left_col, 2)

        # Right side: Shift Operations Panel
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        self._shift_info_lbl = QLabel("")
        self._shift_info_lbl.setStyleSheet(f"""
            font-size: 13px;
            color: {get_color('text_secondary')};
            line-height: 1.6;
        """)

        ops_layout = QVBoxLayout()
        ops_layout.addWidget(self._shift_info_lbl)
        ops_layout.addSpacing(16)

        # Transfer button
        transfer_btn = QPushButton("تسليم الوردية (مناوبة)  🔁")
        transfer_btn.setFixedHeight(46)
        transfer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        transfer_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_neutral')};
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: rgba(255,255,255,0.1);
            }}
        """)
        transfer_btn.clicked.connect(self._on_transfer_shift_clicked)
        ops_layout.addWidget(transfer_btn)

        ops_layout.addSpacing(8)

        # Close button
        close_btn = QPushButton("إغلاق الوردية واليومية  🛑")
        close_btn.setFixedHeight(46)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_cancel')};
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: #bd2130;
            }}
        """)
        close_btn.clicked.connect(self._on_close_shift_clicked)
        ops_layout.addWidget(close_btn)

        right_col.addWidget(make_bento_box("⚙️  إجراءات الوردية الحالية", ops_layout))
        split_layout.addLayout(right_col, 1)

        layout.addLayout(split_layout)
        return tab

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        self._history_table = create_styled_table([
            "رقم الوردية", "فتحت بواسطة", "أغلقت بواسطة", "تاريخ الفتح", "تاريخ الإغلاق", "الحالة"
        ])
        layout.addWidget(make_bento_box("📂  الورديات السابقة المغلقة", self._history_table))
        return tab

    # ------------------------------------------------------------------
    # Event Handlers & Core Methods
    # ------------------------------------------------------------------

    def refresh_state(self) -> None:
        """Update display based on active shift state."""
        self._active_shift = self._ctrl.get_active_shift()

        if self._active_shift is None:
            self._state_stack.setCurrentIndex(0)
            self._header.setText("فتح الوردية لبدء العمل 🏪")
        else:
            self._state_stack.setCurrentIndex(1)
            shift_id = self._active_shift["id"]
            self._header.setText(f"الوردية النشطة: #{shift_id} 🏪")

            # Update Metrics
            summary = self._ctrl.get_shift_summary(shift_id)
            self._sales_card.set_value(f"{summary['total_sales']:,.2f} ج.م")
            self._expenses_card.set_value(f"{summary['total_expenses']:,.2f} ج.م")
            self._expected_cash_card.set_value(f"{summary['expected_cash']:,.2f} ج.م")

            pending_total = (
                summary["pending_delivery"]
                + summary["pending_dinein"]
                + summary["pending_kitchen"]
            )
            self._pending_card.set_value(f"{pending_total} طلب")

            # Update shift info details
            opened_at_str = self._active_shift.get("opened_at", "")
            try:
                dt = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))
                formatted_time = dt.strftime("%Y-%m-%d %I:%M %p")
            except Exception:
                formatted_time = opened_at_str

            info_text = (
                f"رقم الوردية: <b>#{shift_id}</b><br/>"
                f"فتحت بواسطة الموظف: <b>#{self._active_shift.get('opened_by')}</b><br/>"
                f"تاريخ الفتح: <b>{formatted_time}</b><br/>"
                f"رقم الفاتورة القادم: <b>#{self._active_shift.get('next_invoice_no', 1)}</b>"
            )
            self._shift_info_lbl.setText(info_text)

            # Update logged expenses table
            expenses = self._ctrl.get_expenses(shift_id)
            self._expenses_table.setRowCount(0)
            for exp in expenses:
                row = self._expenses_table.rowCount()
                self._expenses_table.insertRow(row)

                # Format category text
                cat_map = {
                    "other": "أخرى",
                    "supplies": "مستلزمات ومشتريات",
                    "delivery_fees": "توصيل سائقين",
                }
                cat_text = cat_map.get(exp["category"], exp["category"])

                # Format time
                time_str = exp["timestamp"]
                try:
                    dt_exp = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                    formatted_exp_time = dt_exp.strftime("%I:%M %p")
                except Exception:
                    formatted_exp_time = time_str

                self._expenses_table.setItem(row, 0, QTableWidgetItem(formatted_exp_time))
                self._expenses_table.setItem(row, 1, QTableWidgetItem(cat_text))
                self._expenses_table.setItem(row, 2, QTableWidgetItem(exp["description"]))
                self._expenses_table.setItem(row, 3, QTableWidgetItem(f"{exp['amount']:,.2f} ج.م"))

            # Populate History Table
            history = self._ctrl.get_shift_history()
            self._history_table.setRowCount(0)
            for s in history:
                row = self._history_table.rowCount()
                self._history_table.insertRow(row)

                def parse_date(d_str: Optional[str]) -> str:
                    if not d_str:
                        return "-"
                    try:
                        parsed = datetime.fromisoformat(d_str.replace("Z", "+00:00"))
                        return parsed.strftime("%Y-%m-%d %I:%M %p")
                    except Exception:
                        return d_str

                self._history_table.setItem(row, 0, QTableWidgetItem(f"#{s['id']}"))
                self._history_table.setItem(row, 1, QTableWidgetItem(f"الموظف #{s['opened_by']}"))
                self._history_table.setItem(row, 2, QTableWidgetItem(f"الموظف #{s['closed_by']}" if s['closed_by'] else "-"))
                self._history_table.setItem(row, 3, QTableWidgetItem(parse_date(s['opened_at'])))
                self._history_table.setItem(row, 4, QTableWidgetItem(parse_date(s['closed_at'])))
                self._history_table.setItem(row, 5, QTableWidgetItem("مغلقة 🔴" if not s['is_active'] else "نشطة 🟢"))

    def _on_open_shift_clicked(self) -> None:
        """Handle opening a new shift."""
        try:
            self._ctrl.open_shift(self._user_id)
            QMessageBox.information(
                self,
                "تم بنجاح",
                "تم فتح وردية جديدة بنجاح وتصفير ترقيم الفواتير.",
            )
            self.refresh_state()
            self.shift_status_changed.emit()
        except Exception as e:
            QMessageBox.critical(
                self,
                "خطأ",
                f"فشل في فتح الوردية: {e}",
            )

    def _on_add_expense_clicked(self) -> None:
        """Add a cash expense."""
        if not self._active_shift:
            return

        amount_txt = self._expense_amount.text().strip()
        desc = self._expense_desc.text().strip()
        cat = self._expense_category.currentData()

        if not amount_txt:
            QMessageBox.warning(self, "خطأ في الإدخال", "يرجى تحديد مبلغ المصروف.")
            return
        if not desc:
            QMessageBox.warning(self, "خطأ في الإدخال", "يرجى كتابة وصف/بيان للمصروف.")
            return

        try:
            amount = float(amount_txt)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "خطأ في الإدخال", "المبلغ يجب أن يكون قيمة رقمية أكبر من الصفر.")
            return

        try:
            self._ctrl.add_expense(
                shift_id=self._active_shift["id"],
                amount=amount,
                description=desc,
                category=cat,
                user_id=self._user_id,
            )
            self._expense_amount.clear()
            self._expense_desc.clear()
            self.refresh_state()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تسجيل المصروف: {e}")

    def _on_transfer_shift_clicked(self) -> None:
        """Mid-day cashier transfer."""
        if not self._active_shift:
            return

        # 1. Ask for Manager PIN
        dialog = PinDialog(
            title="تأكيد صلاحية المدير لتسليم الوردية",
            verify_fn=self._ctrl._auth_svc.verify_pin,
            parent=self,
        )

        def proceed_transfer(raw_pin: str) -> None:
            # 2. Show Transfer dialog to select target cashier
            users = self._ctrl.get_users_for_transfer()
            if not users:
                QMessageBox.warning(self, "خطأ", "لم يتم العثور على موظفين متاحين للتحويل.")
                return

            dialog_users = QDialog(self)
            dialog_users.setWindowTitle("اختر الموظف المستلم")
            dialog_users.setFixedSize(320, 200)
            dialog_users.setStyleSheet(f"""
                QDialog {{
                    background-color: {get_color('primary_bg')};
                    border: 1px solid {get_color('border_color')};
                }}
            """)
            du_layout = QVBoxLayout(dialog_users)
            du_layout.setSpacing(12)

            lbl = QLabel("اختر الكاشير المستلم للوردية:")
            lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
            du_layout.addWidget(lbl)

            combo = QComboBox()
            combo.setStyleSheet(self._input_style())
            for u in users:
                if u["id"] != self._user_id:
                    combo.addItem(f"{u['display_name']} ({u['role']})", u["id"])
            du_layout.addWidget(combo)

            confirm_btn = QPushButton("تأكيد التحويل")
            confirm_btn.setFixedHeight(40)
            confirm_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color('button_confirm')};
                    color: #ffffff;
                    font-weight: bold;
                }}
            """)

            def execute() -> None:
                to_user_id = combo.currentData()
                if to_user_id is None:
                    QMessageBox.warning(dialog_users, "خطأ", "يرجى اختيار الموظف المستلم.")
                    return
                try:
                    self._ctrl.transfer_shift(
                        from_user_id=self._user_id,
                        to_user_id=to_user_id,
                        manager_pin=raw_pin,
                    )
                    QMessageBox.information(
                        dialog_users,
                        "تم التحويل",
                        "تمت عملية تسليم الوردية وطباعة التقرير بنجاح.",
                    )
                    dialog_users.accept()
                    self.refresh_state()
                    self.shift_status_changed.emit()
                except Exception as ex:
                    QMessageBox.critical(dialog_users, "خطأ", f"فشل تسليم الوردية: {ex}")

            confirm_btn.clicked.connect(execute)
            du_layout.addWidget(confirm_btn)

            dialog_users.exec()

        dialog.pin_verified.connect(proceed_transfer)
        dialog.exec()

    def _on_close_shift_clicked(self) -> None:
        """End-of-day shift closure."""
        if not self._active_shift:
            return

        # 1. Ask for Manager PIN
        dialog = PinDialog(
            title="تأكيد صلاحية المدير لإغلاق الوردية",
            verify_fn=self._ctrl._auth_svc.verify_pin,
            parent=self,
        )

        def proceed_close(raw_pin: str) -> None:
            # 2. Trigger Close Shift in service via controller
            try:
                self._ctrl.close_shift(
                    shift_id=self._active_shift["id"],
                    manager_pin=raw_pin,
                )
                QMessageBox.information(
                    self,
                    "تم الإغلاق",
                    "تم إغلاق الوردية واليومية بنجاح وطباعة تقرير الإغلاق النهائي.",
                )
                self.refresh_state()
                self.shift_status_changed.emit()
            except Exception as ex:
                QMessageBox.critical(
                    self,
                    "خطأ",
                    f"فشل إغلاق الوردية:\n{ex}",
                )

        dialog.pin_verified.connect(proceed_close)
        dialog.exec()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------

    @staticmethod
    def _input_style() -> str:
        return f"""
            QLineEdit, QComboBox {{
                background-color: {get_color('input_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 6px;
                padding: 8px;
                color: {get_color('text_primary')};
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {get_color('accent_blue')};
            }}
        """
