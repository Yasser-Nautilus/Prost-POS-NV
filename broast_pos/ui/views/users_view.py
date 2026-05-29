"""
Users view — manager-only screen to manage system users/cashiers, roles, and PIN codes.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from broast_pos.core.models.user import User
from broast_pos.core.services.auth_service import AuthService
from broast_pos.ui.styles.theme import get_color, get_font_family

logger = logging.getLogger(__name__)


class UsersView(QWidget):
    """The central widget for user/cashier account management."""

    def __init__(
        self,
        auth_service: AuthService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._auth = auth_service

        self._setup_ui()
        self.refresh_users()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header Title
        self._header = QLabel("إدارة المستخدمين والصلاحيات 👥")
        self._header.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {get_color('text_primary')};
            margin-bottom: 4px;
        """)
        layout.addWidget(self._header)

        # Top Bar
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        self._add_user_btn = QPushButton("➕  إضافة مستخدم جديد")
        self._add_user_btn.setProperty("class", "confirm")
        self._add_user_btn.clicked.connect(self._on_add_user)
        top_bar.addWidget(self._add_user_btn)

        layout.addLayout(top_bar)

        # Users Table
        self._users_table = QTableWidget()
        self._users_table.setColumnCount(6)
        self._users_table.setHorizontalHeaderLabels(
            ["الرقم", "الاسم", "الدور / الصلاحية", "رمز الدخول (PIN)", "الحالة", "العمليات"]
        )
        self._users_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._users_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._users_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._users_table.verticalHeader().setVisible(False)
        self._users_table.verticalHeader().setDefaultSectionSize(40)

        # Column sizing
        header = self._users_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self._users_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 8px;
                gridline-color: {get_color('border_color')};
                font-size: 13px;
            }}
            QHeaderView::section {{
                background-color: {get_color('primary_bg')};
                color: {get_color('text_secondary')};
                padding: 8px;
                border: none;
                border-bottom: 2px solid {get_color('border_color')};
                font-weight: bold;
                font-size: 13px;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {get_color('border_color')};
                color: {get_color('text_primary')};
            }}
        """)
        layout.addWidget(self._users_table)

    def refresh_users(self) -> None:
        """Repopulate user list table from repository/service."""
        try:
            users = self._auth.get_all_users()
        except Exception as e:
            logger.exception("Failed to load users")
            QMessageBox.critical(self, "خطأ", f"فشل تحميل بيانات المستخدمين: {str(e)}")
            return

        self._users_table.setRowCount(0)
        for u in users:
            row = self._users_table.rowCount()
            self._users_table.insertRow(row)

            # ID
            self._users_table.setItem(row, 0, QTableWidgetItem(str(u.id)))
            # Name
            self._users_table.setItem(row, 1, QTableWidgetItem(u.name))
            # Role translation
            role_display = "مدير" if u.role == "manager" else "كاشير"
            self._users_table.setItem(row, 2, QTableWidgetItem(role_display))
            # PIN Code (masked or clear, let's keep it visible for management screen)
            self._users_table.setItem(row, 3, QTableWidgetItem(u.pin))

            # Status Toggle Button
            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            status_btn = QPushButton("نشط" if u.is_active else "غير نشط")
            status_btn.setProperty("class", "compact")
            status_btn.setFixedSize(70, 28)
            if u.is_active:
                status_btn.setStyleSheet(f"""
                    background-color: {get_color('accent_green')}30;
                    color: {get_color('accent_green')};
                    border: 1px solid {get_color('accent_green')};
                    border-radius: 4px;
                    font-size: 12px;
                """)
            else:
                status_btn.setStyleSheet(f"""
                    background-color: {get_color('text_muted')}30;
                    color: {get_color('text_muted')};
                    border: 1px solid {get_color('text_muted')};
                    border-radius: 4px;
                    font-size: 12px;
                """)
            status_btn.clicked.connect(lambda checked, uid=u.id, act=u.is_active: self._toggle_user_status(uid, act))
            status_layout.addWidget(status_btn)
            self._users_table.setCellWidget(row, 4, status_widget)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            edit_btn = QPushButton("تعديل")
            edit_btn.setProperty("class", "compact")
            edit_btn.setFixedSize(50, 28)
            edit_btn.setStyleSheet(f"""
                background-color: {get_color('accent_blue')}30;
                color: {get_color('accent_blue')};
                border: 1px solid {get_color('accent_blue')};
                border-radius: 4px;
                font-size: 12px;
            """)
            edit_btn.clicked.connect(lambda checked, user=u: self._on_edit_user(user))
            actions_layout.addWidget(edit_btn)

            self._users_table.setCellWidget(row, 5, actions_widget)

    def _toggle_user_status(self, user_id: int, current_status: bool) -> None:
        try:
            self._auth.update_user(user_id, is_active=not current_status)
            self.refresh_users()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تغيير حالة المستخدم: {str(e)}")

    def _on_add_user(self) -> None:
        dialog = UserFormDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, role, pin = dialog.get_data()
                # Verify PIN uniqueness
                existing_users = self._auth.get_all_users()
                if any(u.pin == pin for u in existing_users):
                    QMessageBox.warning(self, "تحذير", "رمز الدخول (PIN) هذا مستخدم بالفعل من قبل موظف آخر.")
                    return

                self._auth.create_user(name=name, role=role, pin=pin)
                self.refresh_users()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل إضافة المستخدم: {str(e)}")

    def _on_edit_user(self, user: User) -> None:
        dialog = UserFormDialog(user, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, role, pin = dialog.get_data()
                # Verify PIN uniqueness
                existing_users = self._auth.get_all_users()
                if any(u.pin == pin and u.id != user.id for u in existing_users):
                    QMessageBox.warning(self, "تحذير", "رمز الدخول (PIN) هذا مستخدم بالفعل من قبل موظف آخر.")
                    return

                self._auth.update_user(user_id=user.id, name=name, role=role, pin=pin)
                self.refresh_users()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل تعديل المستخدم: {str(e)}")


# ============================================================================
# User Form Dialog
# ============================================================================


class UserFormDialog(QDialog):
    """Form dialog to add or edit a system user."""

    def __init__(
        self,
        user: Optional[User] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("تعديل مستخدم" if user else "إضافة مستخدم جديد")
        self.setFixedWidth(360)
        self._user = user

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name Input
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("اسم الموظف الثنائي أو الثلاثي")
        if user:
            self._name_edit.setText(user.name)
        form.addRow("اسم الموظف:", self._name_edit)

        # Role ComboBox
        self._role_combo = QComboBox()
        self._role_combo.addItem("كاشير", "cashier")
        self._role_combo.addItem("مدير", "manager")
        if user:
            index = self._role_combo.findData(user.role)
            if index != -1:
                self._role_combo.setCurrentIndex(index)
        form.addRow("الدور / الصلاحية:", self._role_combo)

        # PIN Code Input (4 digits only)
        self._pin_edit = QLineEdit()
        self._pin_edit.setPlaceholderText("٤ أرقام فقط")
        self._pin_edit.setMaxLength(4)
        # Regex validator for 4 digits
        rx = QRegularExpression(r"^\d{0,4}$")
        self._pin_edit.setValidator(QRegularExpressionValidator(rx))
        if user:
            self._pin_edit.setText(user.pin)
        form.addRow("رمز الدخول (PIN):", self._pin_edit)

        layout.addLayout(form)

        # Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.ButtonRole.AcceptRole | QDialogButtonBox.ButtonRole.RejectRole
        )
        accept_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if accept_btn:
            accept_btn.setText("حفظ")
            accept_btn.setProperty("class", "confirm")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setText("إلغاء")
            cancel_btn.setProperty("class", "danger")

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> tuple[str, str, str]:
        return (
            self._name_edit.text().strip(),
            self._role_combo.currentData(),
            self._pin_edit.text().strip(),
        )

    def accept(self) -> None:
        name = self._name_edit.text().strip()
        pin = self._pin_edit.text().strip()

        if not name:
            QMessageBox.warning(self, "تحذير", "يرجى إدخال اسم الموظف.")
            return
        if len(pin) != 4 or not pin.isdigit():
            QMessageBox.warning(self, "تحذير", "رمز الدخول (PIN) يجب أن يكون ٤ أرقام تماماً.")
            return
        super().accept()
