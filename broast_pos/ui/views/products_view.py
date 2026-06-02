"""
Products view — manager-only screen to manage categories, products, delivery zones,
and order-related configurations (takeaway auto-complete threshold).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from broast_pos.config import config
from broast_pos.core.models.customer import Zone
from broast_pos.core.models.product import Category, Product
from broast_pos.core.services.customer_service import CustomerService
from broast_pos.core.services.product_service import ProductService
from broast_pos.ui.styles.theme import get_color, get_font_family

logger = logging.getLogger(__name__)


class ProductsView(QWidget):
    """The central widget for product, category, zone, and settings management."""

    def __init__(
        self,
        product_service: ProductService,
        customer_service: CustomerService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._products = product_service
        self._customers = customer_service

        self._setup_ui()
        self.refresh_all()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header Title
        self._header = QLabel("إدارة المنتجات والإعدادات 🍔")
        self._header.setStyleSheet(f"""
            font-size: 20px;
            font-weight: bold;
            color: {get_color('text_primary')};
            margin-bottom: 4px;
        """)
        layout.addWidget(self._header)

        # Tab Widget
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
                min-width: 120px;
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

        # Add Tabs
        self._tabs.addTab(self._build_products_tab(), "المنتجات 🍗")
        self._tabs.addTab(self._build_categories_tab(), "الفئات 📁")
        self._tabs.addTab(self._build_zones_tab(), "مناطق التوصيل 🛵")
        self._tabs.addTab(self._build_settings_tab(), "إعدادات الطلبات ⏱️")

        layout.addWidget(self._tabs)

    # ------------------------------------------------------------------
    # Tab 1: Products
    # ------------------------------------------------------------------
    def _build_products_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        # Search box
        self._prod_search = QLineEdit()
        self._prod_search.setPlaceholderText("بحث عن منتج...")
        self._prod_search.textChanged.connect(self._filter_products)
        self._prod_search.setFixedWidth(200)
        filter_bar.addWidget(self._prod_search)

        # Category filter
        filter_bar.addWidget(QLabel("الفئة:"))
        self._prod_cat_filter = QComboBox()
        self._prod_cat_filter.currentIndexChanged.connect(self._filter_products)
        self._prod_cat_filter.setFixedWidth(150)
        filter_bar.addWidget(self._prod_cat_filter)

        filter_bar.addStretch()

        # Add Product button
        self._add_prod_btn = QPushButton("➕  إضافة منتج")
        self._add_prod_btn.setProperty("class", "confirm")
        self._add_prod_btn.clicked.connect(self._on_add_product)
        filter_bar.addWidget(self._add_prod_btn)

        layout.addLayout(filter_bar)

        # Table
        self._products_table = self._create_table(
            ["الرقم", "الاسم", "السعر", "الفئة", "الترتيب", "الحالة", "العمليات"]
        )
        layout.addWidget(self._products_table)

        return widget

    # ------------------------------------------------------------------
    # Tab 2: Categories
    # ------------------------------------------------------------------
    def _build_categories_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        header_bar = QHBoxLayout()
        header_bar.addStretch()

        self._add_cat_btn = QPushButton("➕  إضافة فئة")
        self._add_cat_btn.setProperty("class", "confirm")
        self._add_cat_btn.clicked.connect(self._on_add_category)
        header_bar.addWidget(self._add_cat_btn)

        layout.addLayout(header_bar)

        self._categories_table = self._create_table(
            ["الرقم", "الاسم", "الترتيب", "الحالة", "العمليات"]
        )
        layout.addWidget(self._categories_table)

        return widget

    # ------------------------------------------------------------------
    # Tab 3: Zones
    # ------------------------------------------------------------------
    def _build_zones_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        header_bar = QHBoxLayout()
        header_bar.addStretch()

        self._add_zone_btn = QPushButton("➕  إضافة منطقة")
        self._add_zone_btn.setProperty("class", "confirm")
        self._add_zone_btn.clicked.connect(self._on_add_zone)
        header_bar.addWidget(self._add_zone_btn)

        layout.addLayout(header_bar)

        self._zones_table = self._create_table(
            ["الرقم", "المنطقة", "رسوم التوصيل", "الحالة", "العمليات"]
        )
        layout.addWidget(self._zones_table)

        return widget

    # ------------------------------------------------------------------
    # Tab 4: Settings
    # ------------------------------------------------------------------
    def _build_settings_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("SettingsCard")
        card.setStyleSheet(f"""
            QFrame#SettingsCard {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 12px;
                padding: 24px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(20)

        title = QLabel("⚙️  إعدادات تشغيل صالة الكاشير")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        card_layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Autocomplete timeout spinbox
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setRange(1, 120)
        self._timeout_spin.setSuffix(" دقيقة")
        self._timeout_spin.setFixedWidth(120)
        self._timeout_spin.setValue(config.get_takeaway_auto_complete_minutes())

        form.addRow("زمن تمييز طلبات التيك أواي تلقائياً:", self._timeout_spin)
        card_layout.addLayout(form)

        # Save button
        self._save_settings_btn = QPushButton("💾  حفظ الإعدادات")
        self._save_settings_btn.setProperty("class", "confirm")
        self._save_settings_btn.setFixedWidth(160)
        self._save_settings_btn.clicked.connect(self._on_save_settings)
        card_layout.addWidget(self._save_settings_btn)

        layout.addWidget(card)
        layout.addStretch()

        return widget

    # ------------------------------------------------------------------
    # Loading / Populating Data
    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        """Reload all categories, products, zones, and settings."""
        self._refresh_category_filters()
        self._refresh_products()
        self._refresh_categories()
        self._refresh_zones()

        # Update settings view
        self._timeout_spin.setValue(config.get_takeaway_auto_complete_minutes())

    def _refresh_category_filters(self) -> None:
        """Update category dropdown filter in products tab."""
        self._prod_cat_filter.blockSignals(True)
        self._prod_cat_filter.clear()
        self._prod_cat_filter.addItem("كل الفئات", None)
        for cat in self._products.get_categories():
            self._prod_cat_filter.addItem(cat.name, cat.id)
        self._prod_cat_filter.blockSignals(False)

    def _refresh_products(self) -> None:
        """Repopulate products table."""
        self._all_products = self._products.get_all_products()
        self._filter_products()

    def _filter_products(self) -> None:
        """Filter products by search text and category dropdown."""
        search_txt = self._prod_search.text().strip().lower()
        selected_cat_id = self._prod_cat_filter.currentData()

        # Fetch category map for display
        categories = {c.id: c.name for c in self._products.get_all_categories()}

        filtered = []
        for p in self._all_products:
            if selected_cat_id is not None and p.category_id != selected_cat_id:
                continue
            if search_txt and search_txt not in p.name.lower():
                continue
            filtered.append(p)

        self._products_table.setRowCount(0)
        for p in filtered:
            row = self._products_table.rowCount()
            self._products_table.insertRow(row)

            # ID
            self._products_table.setItem(row, 0, QTableWidgetItem(str(p.id)))
            # Name
            self._products_table.setItem(row, 1, QTableWidgetItem(p.name))
            # Price
            self._products_table.setItem(row, 2, QTableWidgetItem(f"{p.price:.2f}"))
            # Category
            cat_name = categories.get(p.category_id, "—")
            self._products_table.setItem(row, 3, QTableWidgetItem(cat_name))
            # Sort Order
            self._products_table.setItem(row, 4, QTableWidgetItem(str(p.sort_order)))

            # Status (Toggle Button)
            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            status_btn = QPushButton("نشط" if p.is_active else "غير نشط")
            status_btn.setProperty("class", "status-active" if p.is_active else "status-inactive")
            status_btn.setFixedSize(85, 28)
            status_btn.clicked.connect(lambda checked, pid=p.id, act=p.is_active: self._toggle_product_status(pid, act))
            status_layout.addWidget(status_btn)
            self._products_table.setCellWidget(row, 5, status_widget)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            edit_btn = QPushButton("تعديل")
            edit_btn.setProperty("class", "edit-action")
            edit_btn.setFixedSize(72, 28)
            edit_btn.clicked.connect(lambda checked, prod=p: self._on_edit_product(prod))
            actions_layout.addWidget(edit_btn)

            self._products_table.setCellWidget(row, 6, actions_widget)

    def _refresh_categories(self) -> None:
        """Repopulate categories table."""
        categories = self._products.get_all_categories()
        self._categories_table.setRowCount(0)

        for c in categories:
            row = self._categories_table.rowCount()
            self._categories_table.insertRow(row)

            # ID
            self._categories_table.setItem(row, 0, QTableWidgetItem(str(c.id)))
            # Name
            self._categories_table.setItem(row, 1, QTableWidgetItem(c.name))
            # Sort Order
            self._categories_table.setItem(row, 2, QTableWidgetItem(str(c.sort_order)))

            # Status (Toggle Button)
            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            status_btn = QPushButton("نشط" if c.is_active else "غير نشط")
            status_btn.setProperty("class", "status-active" if c.is_active else "status-inactive")
            status_btn.setFixedSize(85, 28)
            status_btn.clicked.connect(lambda checked, cid=c.id, act=c.is_active: self._toggle_category_status(cid, act))
            status_layout.addWidget(status_btn)
            self._categories_table.setCellWidget(row, 3, status_widget)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            edit_btn = QPushButton("تعديل")
            edit_btn.setProperty("class", "edit-action")
            edit_btn.setFixedSize(72, 28)
            edit_btn.clicked.connect(lambda checked, cat=c: self._on_edit_category(cat))
            actions_layout.addWidget(edit_btn)

            self._categories_table.setCellWidget(row, 4, actions_widget)

    def _refresh_zones(self) -> None:
        """Repopulate delivery zones table."""
        zones = self._customers.get_all_zones()
        self._zones_table.setRowCount(0)

        for z in zones:
            row = self._zones_table.rowCount()
            self._zones_table.insertRow(row)

            # ID
            self._zones_table.setItem(row, 0, QTableWidgetItem(str(z.id)))
            # Name
            self._zones_table.setItem(row, 1, QTableWidgetItem(z.name))
            # Delivery Fee
            self._zones_table.setItem(row, 2, QTableWidgetItem(f"{z.delivery_fee:.2f}"))

            # Status (Toggle Button)
            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            status_btn = QPushButton("نشط" if z.is_active else "غير نشط")
            status_btn.setProperty("class", "status-active" if z.is_active else "status-inactive")
            status_btn.setFixedSize(85, 28)
            status_btn.clicked.connect(lambda checked, zid=z.id, act=z.is_active: self._toggle_zone_status(zid, act))
            status_layout.addWidget(status_btn)
            self._zones_table.setCellWidget(row, 3, status_widget)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            edit_btn = QPushButton("تعديل")
            edit_btn.setProperty("class", "edit-action")
            edit_btn.setFixedSize(72, 28)
            edit_btn.clicked.connect(lambda checked, zone=z: self._on_edit_zone(zone))
            actions_layout.addWidget(edit_btn)

            self._zones_table.setCellWidget(row, 4, actions_widget)

    # ------------------------------------------------------------------
    # Actions & Operations
    # ------------------------------------------------------------------
    def _toggle_product_status(self, product_id: int, current_status: bool) -> None:
        try:
            self._products.update_product(product_id, is_active=not current_status)
            self._refresh_products()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تغيير حالة المنتج: {str(e)}")

    def _toggle_category_status(self, category_id: int, current_status: bool) -> None:
        try:
            self._products.update_category(category_id, is_active=not current_status)
            self.refresh_all()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تغيير حالة الفئة: {str(e)}")

    def _toggle_zone_status(self, zone_id: int, current_status: bool) -> None:
        try:
            self._customers.update_zone(zone_id, is_active=not current_status)
            self._refresh_zones()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تغيير حالة المنطقة: {str(e)}")

    def _on_add_product(self) -> None:
        categories = self._products.get_categories()
        if not categories:
            QMessageBox.warning(self, "تحذير", "يجب إضافة فئة واحدة على الأقل قبل إضافة المنتجات.")
            return

        dialog = ProductFormDialog(categories, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, cat_id, price, sort_order = dialog.get_data()
                self._products.create_product(
                    name=name, price=price, category_id=cat_id, sort_order=sort_order
                )
                self._refresh_products()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل إضافة المنتج: {str(e)}")

    def _on_edit_product(self, product: Product) -> None:
        categories = self._products.get_all_categories()
        dialog = ProductFormDialog(categories, product, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, cat_id, price, sort_order = dialog.get_data()
                self._products.update_product(
                    product_id=product.id,
                    name=name,
                    price=price,
                    category_id=cat_id,
                    sort_order=sort_order,
                )
                self._refresh_products()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل تعديل المنتج: {str(e)}")

    def _on_add_category(self) -> None:
        dialog = CategoryFormDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, sort_order = dialog.get_data()
                self._products.create_category(name=name, sort_order=sort_order)
                self.refresh_all()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل إضافة الفئة: {str(e)}")

    def _on_edit_category(self, category: Category) -> None:
        dialog = CategoryFormDialog(category, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, sort_order = dialog.get_data()
                self._products.update_category(
                    category_id=category.id, name=name, sort_order=sort_order
                )
                self.refresh_all()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل تعديل الفئة: {str(e)}")

    def _on_add_zone(self) -> None:
        dialog = ZoneFormDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, fee = dialog.get_data()
                self._customers.create_zone(name=name, delivery_fee=fee)
                self._refresh_zones()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل إضافة المنطقة: {str(e)}")

    def _on_edit_zone(self, zone: Zone) -> None:
        dialog = ZoneFormDialog(zone, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                name, fee = dialog.get_data()
                self._customers.update_zone(zone_id=zone.id, name=name, delivery_fee=fee)
                self._refresh_zones()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل تعديل المنطقة: {str(e)}")

    def _on_save_settings(self) -> None:
        try:
            val = self._timeout_spin.value()
            config.update_takeaway_auto_complete_minutes(val)
            QMessageBox.information(self, "نجاح", "تم حفظ إعدادات صالة الكاشير بنجاح.")
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل حفظ الإعدادات: {str(e)}")

    # ------------------------------------------------------------------
    # UI Helpers
    # ------------------------------------------------------------------
    def _create_table(self, headers: List[str]) -> QTableWidget:
        """Utility method to configure standardized styled data tables."""
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(40)

        # Columns sizing
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        
        last_col = len(headers) - 1
        status_col = len(headers) - 2
        
        header.setSectionResizeMode(status_col, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(last_col, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(status_col, 110)
        table.setColumnWidth(last_col, 100)

        table.setStyleSheet(f"""
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
        return table


# ============================================================================
# Form Dialogs
# ============================================================================


class ProductFormDialog(QDialog):
    """Form dialog to add or edit a product."""

    def __init__(
        self,
        categories: List[Category],
        product: Optional[Product] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("تعديل منتج" if product else "إضافة منتج جديد")
        self.setFixedWidth(400)
        self._product = product

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name Input
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("مثال: وجبة بروست ٤ قطع")
        if product:
            self._name_edit.setText(product.name)
        form.addRow("اسم المنتج:", self._name_edit)

        # Category ComboBox
        self._cat_combo = QComboBox()
        for cat in categories:
            self._cat_combo.addItem(cat.name, cat.id)
        if product:
            index = self._cat_combo.findData(product.category_id)
            if index != -1:
                self._cat_combo.setCurrentIndex(index)
        form.addRow("الفئة:", self._cat_combo)

        # Price DoubleSpinBox
        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0.0, 9999.0)
        self._price_spin.setDecimals(2)
        self._price_spin.setSuffix(" ج.م")
        self._price_spin.setFixedWidth(150)
        if product:
            self._price_spin.setValue(product.price)
        form.addRow("السعر:", self._price_spin)

        # Sort Order SpinBox
        self._sort_spin = QSpinBox()
        self._sort_spin.setRange(0, 999)
        self._sort_spin.setFixedWidth(150)
        if product:
            self._sort_spin.setValue(product.sort_order)
        form.addRow("الترتيب في الشبكة:", self._sort_spin)

        layout.addLayout(form)

        # Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Custom Arabic labels
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

    def get_data(self) -> tuple[str, int, float, int]:
        return (
            self._name_edit.text().strip(),
            self._cat_combo.currentData(),
            self._price_spin.value(),
            self._sort_spin.value(),
        )

    def accept(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "تحذير", "يرجى إدخال اسم المنتج.")
            return
        super().accept()


class CategoryFormDialog(QDialog):
    """Form dialog to add or edit a product category."""

    def __init__(
        self,
        category: Optional[Category] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("تعديل فئة" if category else "إضافة فئة جديدة")
        self.setFixedWidth(360)
        self._category = category

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name Input
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("مثال: وجبات بروست")
        if category:
            self._name_edit.setText(category.name)
        form.addRow("اسم الفئة:", self._name_edit)

        # Sort Order SpinBox
        self._sort_spin = QSpinBox()
        self._sort_spin.setRange(0, 999)
        self._sort_spin.setFixedWidth(120)
        if category:
            self._sort_spin.setValue(category.sort_order)
        form.addRow("ترتيب التبويب:", self._sort_spin)

        layout.addLayout(form)

        # Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
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

    def get_data(self) -> tuple[str, int]:
        return (
            self._name_edit.text().strip(),
            self._sort_spin.value(),
        )

    def accept(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "تحذير", "يرجى إدخال اسم الفئة.")
            return
        super().accept()


class ZoneFormDialog(QDialog):
    """Form dialog to add or edit a delivery zone."""

    def __init__(
        self,
        zone: Optional[Zone] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("تعديل منطقة توصيل" if zone else "إضافة منطقة توصيل")
        self.setFixedWidth(360)
        self._zone = zone

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Name Input
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("مثال: حي الدقي")
        if zone:
            self._name_edit.setText(zone.name)
        form.addRow("اسم المنطقة:", self._name_edit)

        # Delivery Fee DoubleSpinBox
        self._fee_spin = QDoubleSpinBox()
        self._fee_spin.setRange(0.0, 999.0)
        self._fee_spin.setDecimals(2)
        self._fee_spin.setSuffix(" ج.م")
        self._fee_spin.setFixedWidth(120)
        if zone:
            self._fee_spin.setValue(zone.delivery_fee)
        form.addRow("رسوم التوصيل:", self._fee_spin)

        layout.addLayout(form)

        # Dialog Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
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

    def get_data(self) -> tuple[str, float]:
        return (
            self._name_edit.text().strip(),
            self._fee_spin.value(),
        )

    def accept(self) -> None:
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "تحذير", "يرجى إدخال اسم المنطقة.")
            return
        super().accept()
