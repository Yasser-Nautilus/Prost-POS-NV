"""
Customer Panel component — phone search, address cards, and customer setup.

Housed in the POS View column, this component allows:
    • Cashier lookup of customers by 11-digit phone number.
    • Auto-selection/rendering of delivery address cards.
    • Modal dialog for creating new customers and adding new addresses.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from broast_pos.core.models.customer import Customer, CustomerAddress
from broast_pos.core.services.customer_service import CustomerService
from broast_pos.ui.styles.theme import get_color

logger = logging.getLogger(__name__)


class CustomerAddressDialog(QDialog):
    """Dialog to create a new customer and/or add a new address."""

    def __init__(
        self,
        customer_service: CustomerService,
        phone: str,
        existing_customer: Optional[Customer] = None,
        pickup_only: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._customer_svc = customer_service
        self._phone = phone
        self._customer = existing_customer
        self._pickup_only = pickup_only

        self.created_customer: Optional[Customer] = None
        self.created_address: Optional[CustomerAddress] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("إضافة عميل جديد" if not self._customer else "إضافة عنوان جديد")
        self.setMinimumWidth(380)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        hdr = QLabel(self.windowTitle())
        hdr.setProperty("class", "heading")
        hdr.setStyleSheet("font-size: 16px; font-weight: bold; padding-bottom: 4px;")
        layout.addWidget(hdr)

        # Phone field (Read-only)
        layout.addWidget(QLabel("رقم الهاتف"))
        self._phone_input = QLineEdit(self._phone)
        self._phone_input.setReadOnly(True)
        self._phone_input.setStyleSheet(f"background-color: {get_color('primary_bg')}; color: {get_color('text_secondary')};")
        layout.addWidget(self._phone_input)

        # Name field
        layout.addWidget(QLabel("اسم العميل"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("أدخل اسم العميل بالكامل")
        if self._customer:
            self._name_input.setText(self._customer.name)
            self._name_input.setReadOnly(True)
            self._name_input.setStyleSheet(f"background-color: {get_color('primary_bg')}; color: {get_color('text_secondary')};")
        layout.addWidget(self._name_input)

        # Address fields (if not pickup_only)
        self._address_container = QWidget()
        addr_layout = QVBoxLayout(self._address_container)
        addr_layout.setContentsMargins(0, 0, 0, 0)
        addr_layout.setSpacing(12)

        addr_layout.addWidget(QLabel("المنطقة / الحي"))
        self._zone_combo = QComboBox()
        self._zones = self._customer_svc.get_active_zones()
        for zone in self._zones:
            self._zone_combo.addItem(f"{zone.name} ({zone.delivery_fee} ج.م)", zone.id)
        addr_layout.addWidget(self._zone_combo)

        addr_layout.addWidget(QLabel("اسم الشارع والوصف"))
        self._street_input = QLineEdit()
        self._street_input.setPlaceholderText("مثال: شارع البحر بجوار المسجد")
        addr_layout.addWidget(self._street_input)

        layout.addWidget(self._address_container)

        if self._pickup_only:
            self._address_container.hide()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self._save_btn = QPushButton("حفظ")
        self._save_btn.setProperty("class", "confirm")
        self._save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self._save_btn)

        self._cancel_btn = QPushButton("إلغاء")
        self._cancel_btn.setProperty("class", "danger")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

    def _on_save(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "خطأ", "يرجى إدخال اسم العميل.")
            return

        try:
            # 1. Create or load customer
            if not self._customer:
                customer = self._customer_svc.create_customer(name, self._phone)
                self.created_customer = customer
            else:
                customer = self._customer

            # 2. Add address if delivery (not pickup_only)
            if not self._pickup_only:
                street = self._street_input.text().strip()
                if not street:
                    QMessageBox.warning(self, "خطأ", "يرجى إدخال اسم الشارع.")
                    return
                zone_idx = self._zone_combo.currentIndex()
                if zone_idx == -1:
                    QMessageBox.warning(self, "خطأ", "لا توجد مناطق توصيل نشطة.")
                    return
                zone_id = self._zone_combo.currentData()
                address = self._customer_svc.add_address(customer.id, street, zone_id)
                self.created_address = address

            self.accept()
        except ValueError as e:
            QMessageBox.critical(self, "خطأ", str(e))


class CustomerPanel(QFrame):
    """Panel for customer search and selection at the top of the Order Summary."""

    customer_selected = pyqtSignal(object)  # Customer
    address_selected = pyqtSignal(object)   # CustomerAddress
    clear_customer = pyqtSignal()

    def __init__(
        self,
        customer_service: CustomerService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._customer_svc = customer_service
        self._current_customer: Optional[Customer] = None
        self._current_address: Optional[CustomerAddress] = None
        self._pickup_only: bool = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            CustomerPanel {{
                background-color: {get_color('secondary_bg')};
                border-bottom: 1px solid {get_color('border_color')};
                border-radius: 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Phone Search Row
        search_layout = QHBoxLayout()
        search_layout.setSpacing(6)

        self._phone_input = QLineEdit()
        self._phone_input.setPlaceholderText("رقم الهاتف (11 رقم)")
        self._phone_input.setClearButtonEnabled(True)
        # Limit to 11 digits
        validator = QRegularExpressionValidator(QRegularExpression(r"^\d{0,11}$"))
        self._phone_input.setValidator(validator)
        self._phone_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self._phone_input, 1)

        self._search_btn = QPushButton("🔍")
        self._search_btn.setProperty("class", "compact")
        self._search_btn.setFixedSize(36, 36)
        self._search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('accent_blue')};
                border-radius: 6px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: {get_color('accent_blue')}dd; }}
        """)
        self._search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(self._search_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setFixedWidth(24)
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        search_layout.addWidget(self._status_lbl)

        layout.addLayout(search_layout)

        # Info Display Row (Name, Address status)
        self._info_widget = QWidget()
        info_layout = QVBoxLayout(self._info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        self._name_lbl = QLabel("")
        self._name_lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {get_color('text_primary')};")
        info_layout.addWidget(self._name_lbl)

        # Active Address line
        self._active_address_lbl = QLabel("")
        self._active_address_lbl.setStyleSheet(f"font-size: 12px; color: {get_color('text_secondary')};")
        info_layout.addWidget(self._active_address_lbl)

        # Container for address cards
        self._cards_widget = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(0, 4, 0, 4)
        self._cards_layout.setSpacing(6)
        info_layout.addWidget(self._cards_widget)

        # "+ New Address" button
        self._add_addr_btn = QPushButton("+ عنوان جديد")
        self._add_addr_btn.setProperty("class", "compact")
        self._add_addr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_addr_btn.setMinimumHeight(32)
        self._add_addr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color('button_neutral')};
                color: {get_color('text_primary')};
                border: 1px solid {get_color('border_color')};
                border-radius: 6px;
                font-size: 12px;
                padding: 0 10px;
            }}
            QPushButton:hover {{ background-color: {get_color('border_color')}; }}
        """)
        self._add_addr_btn.clicked.connect(self._on_add_address)
        info_layout.addWidget(self._add_addr_btn)

        layout.addWidget(self._info_widget)
        self._info_widget.hide()

    def set_pickup_only(self, pickup_only: bool) -> None:
        """Configure UI layout for delivery vs pickup modes."""
        self._pickup_only = pickup_only
        self._clear_ui_states()
        if pickup_only:
            self._cards_widget.hide()
            self._add_addr_btn.setText("+ عميل جديد")
            self._active_address_lbl.hide()
        else:
            self._cards_widget.show()
            self._add_addr_btn.setText("+ عنوان جديد")
            self._active_address_lbl.show()

    def _clear_ui_states(self) -> None:
        self._current_customer = None
        self._current_address = None
        self._name_lbl.setText("")
        self._active_address_lbl.setText("")
        self._status_lbl.setText("")
        self._info_widget.hide()
        self._clear_address_cards()
        self.clear_customer.emit()

    def _clear_address_cards(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _on_search(self) -> None:
        phone = self._phone_input.text().strip()
        if len(phone) != 11 or not phone.startswith("01"):
            self._status_lbl.setText("✗")
            self._status_lbl.setStyleSheet(f"color: {get_color('accent_red')};")
            self._clear_ui_states()
            return

        try:
            customer = self._customer_svc.find_by_phone(phone)
            if customer:
                self._status_lbl.setText("✓")
                self._status_lbl.setStyleSheet(f"color: {get_color('accent_green')};")
                self._display_customer(customer)
            else:
                self._status_lbl.setText("✗")
                self._status_lbl.setStyleSheet(f"color: {get_color('accent_red')};")
                self._clear_ui_states()
                # Auto-open add dialog
                self._on_add_address()
        except ValueError as e:
            self._status_lbl.setText("✗")
            self._status_lbl.setStyleSheet(f"color: {get_color('accent_red')};")
            self._clear_ui_states()
            QMessageBox.critical(self, "خطأ", str(e))

    def _display_customer(self, customer: Customer) -> None:
        self._current_customer = customer
        self._name_lbl.setText(f"الاسم: {customer.name}")
        self._info_widget.show()
        self.customer_selected.emit(customer)

        if self._pickup_only:
            self._active_address_lbl.setText("طلب استلام - لا يتطلب عنوان")
            return

        # Fetch addresses
        addresses = self._customer_svc.get_addresses(customer.id)
        customer.addresses = addresses
        self._clear_address_cards()

        if not addresses:
            self._active_address_lbl.setText("لا يوجد عناوين مسجلة.")
            # Automatically prompt to add an address
            self._on_add_address()
        elif len(addresses) == 1:
            addr = addresses[0]
            self._select_address(addr)
        else:
            self._active_address_lbl.setText("اختر عنوان التوصيل:")
            for addr in addresses:
                btn = QPushButton(f"{addr.zone_name} - {addr.street_name}")
                btn.setProperty("class", "compact")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setMinimumHeight(32)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {get_color('secondary_bg')};
                        color: {get_color('text_primary')};
                        border: 2px solid {get_color('accent_blue')};
                        border-radius: 6px;
                        font-size: 11px;
                        padding: 0 8px;
                    }}
                    QPushButton:hover {{ background-color: {get_color('accent_blue')}22; }}
                """)
                btn.clicked.connect(lambda _, a=addr: self._select_address(a))
                self._cards_layout.addWidget(btn)

    def _select_address(self, address: CustomerAddress) -> None:
        self._current_address = address
        self._active_address_lbl.setText(f"العنوان: {address.zone_name} - {address.street_name} (رسوم: {address.delivery_fee} ج.م)")
        self.address_selected.emit(address)

    def _on_add_address(self) -> None:
        phone = self._phone_input.text().strip()
        if len(phone) != 11 or not phone.startswith("01"):
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال رقم هاتف صحيح (11 رقم يبدأ بـ 01) أولاً.")
            return

        dialog = CustomerAddressDialog(
            customer_service=self._customer_svc,
            phone=phone,
            existing_customer=self._current_customer,
            pickup_only=self._pickup_only,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.created_customer:
                self._current_customer = dialog.created_customer
                self._phone_input.setText(dialog.created_customer.phone)
                self._on_search()
            elif dialog.created_address:
                self._on_search()
                self._select_address(dialog.created_address)
