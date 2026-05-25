"""
Reports view — comprehensive on-screen dashboard and printable financial reports.

Features:
    • Daily summary: order types, payment methods, cancelled orders, driver totals, bestsellers.
    • Monthly dashboard: sales, expenses, profits, custom daily bar chart, expenses split.
    • Yearly overview: monthly comparison, year-level bestsellers, custom monthly bar chart.
    • Silent print integration for thermal printers.
    • Clean modern bento-grid layout with custom painted rounded-top bar charts and gauges.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QDate, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from broast_pos.features.reports.reports_controller import ReportsController
from broast_pos.ui.styles.theme import get_color, get_font_family

logger = logging.getLogger(__name__)


# ============================================================================
# Custom Graphical Widgets
# ============================================================================


class RoundedBarChartWidget(QWidget):
    """Custom graphical widget that draws vertical bars with rounded tops.

    Fits the modern 'bento-grid' visual design requested by the user.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.data: List[Dict[str, Any]] = []  # list of {"label": str, "value": float}
        self.hovered_idx = -1
        self.max_val = 0.0

        # Style colors
        self.accent_color = QColor("#007bff")  # default blue
        self.accent_hover = QColor("#3395ff")
        self.grid_color = QColor("#2d3748")
        self.text_color = QColor("#a0aec0")
        self.bg_color = QColor("#1b2838")

    def set_data(self, data: List[Dict[str, Any]], accent_color_hex: str = "#007bff") -> None:
        """Update chart dataset and trigger repaint."""
        self.data = data
        self.accent_color = QColor(accent_color_hex)
        self.accent_hover = self.accent_color.lighter(115)
        self.max_val = max((item["value"] for item in data), default=0.0)
        self.hovered_idx = -1
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        # Draw container card background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.bg_color))
        painter.drawRoundedRect(rect, 12, 12)

        if not self.data:
            painter.setPen(QPen(self.text_color))
            painter.setFont(QFont(get_font_family(), 14))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "لا توجد بيانات لعرضها")
            return

        # Margins inside container
        left_margin = 60
        right_margin = 20
        top_margin = 35
        bottom_margin = 35

        w = rect.width() - left_margin - right_margin
        h = rect.height() - top_margin - bottom_margin

        # Draw Y Axis Grid lines and labels (5 steps)
        painter.setFont(QFont(get_font_family(), 9))
        grid_steps = 4
        for i in range(grid_steps + 1):
            val = (self.max_val / grid_steps) * i if self.max_val > 0 else 0
            y = rect.height() - bottom_margin - (h / grid_steps) * i

            # Dash line
            painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(left_margin), int(y), int(rect.width() - right_margin), int(y))

            # Value label
            painter.setPen(QPen(self.text_color))
            label_text = f"{val:,.0f}" if val >= 1000 else f"{val:.0f}"
            painter.drawText(
                QRectF(5, y - 8, left_margin - 12, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label_text,
            )

        # Draw bars
        bar_count = len(self.data)
        if bar_count <= 0:
            return

        bar_width = (w / bar_count) * 0.6
        bar_gap = (w / bar_count) * 0.4

        for idx, item in enumerate(self.data):
            val = item["value"]
            lbl = item["label"]

            # Calculate height
            bar_h = (val / self.max_val) * h if self.max_val > 0 else 0
            x = left_margin + idx * (w / bar_count) + bar_gap / 2
            y = rect.height() - bottom_margin - bar_h

            if bar_h > 0:
                bar_rect = QRectF(x, y, bar_width, bar_h)
                path = QPainterPath()
                # Rounded top corners path
                radius = min(8.0, bar_width / 2.0)
                path.moveTo(x, y + bar_h)
                path.lineTo(x, y + radius)
                path.quadTo(x, y, x + radius, y)
                path.lineTo(x + bar_width - radius, y)
                path.quadTo(x + bar_width, y, x + bar_width, y + radius)
                path.lineTo(x + bar_width, y + bar_h)
                path.closeSubpath()

                # Hover style
                if idx == self.hovered_idx:
                    painter.setBrush(QBrush(self.accent_hover))
                else:
                    painter.setBrush(QBrush(self.accent_color))

                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPath(path)

            # Draw labels (skip overlapping labels if data is dense)
            show_label = True
            if bar_count > 15:
                step = 5 if bar_count > 25 else 2
                show_label = (idx % step == 0) or (idx == bar_count - 1)

            if show_label:
                painter.setPen(QPen(self.text_color))
                painter.drawText(
                    QRectF(x - bar_gap / 2, rect.height() - bottom_margin + 5, bar_width + bar_gap, 20),
                    Qt.AlignmentFlag.AlignCenter,
                    str(lbl),
                )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        rect = self.rect()
        left_margin = 60
        right_margin = 20
        top_margin = 35
        bottom_margin = 35

        w = rect.width() - left_margin - right_margin
        h = rect.height() - top_margin - bottom_margin

        if not self.data or w <= 0 or h <= 0:
            return

        pos = event.position()
        x_chart = pos.x() - left_margin

        bar_count = len(self.data)
        idx = int(x_chart / (w / bar_count))

        if 0 <= idx < bar_count:
            val = self.data[idx]["value"]
            bar_h = (val / self.max_val) * h if self.max_val > 0 else 0
            y_bar = rect.height() - bottom_margin - bar_h

            if y_bar <= pos.y() <= rect.height() - bottom_margin:
                if idx != self.hovered_idx:
                    self.hovered_idx = idx
                    self.update()
                    # Show value tooltip
                    tip = f"{self.data[idx]['label']}: {val:,.2f} ج.م"
                    QToolTip.showText(
                        self.mapToGlobal(QPointF(pos.x(), y_bar).toPoint()),
                        tip,
                        self,
                    )
                return

        if self.hovered_idx != -1:
            self.hovered_idx = -1
            self.update()
            QToolTip.hideText()

    def leaveEvent(self, event: Any) -> None:
        if self.hovered_idx != -1:
            self.hovered_idx = -1
            self.update()
            QToolTip.hideText()


class CircularProgressWidget(QWidget):
    """Circular ring/donut progress indicator.

    Typically displays targeted percentage status (e.g. Sales Margin or Order Shares).
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.percentage = 0.0
        self.label = ""
        self.color = QColor("#28a745")
        self.bg_color = QColor("#1b2838")
        self.track_color = QColor("#2d3748")
        self.text_color = QColor("#ffffff")

    def set_value(self, percentage: float, label: str, color_hex: str = "#28a745") -> None:
        self.percentage = min(100.0, max(0.0, percentage))
        self.label = label
        self.color = QColor(color_hex)
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.bg_color))
        painter.drawRoundedRect(rect, 12, 12)

        size = min(rect.width(), rect.height()) - 50
        if size <= 10:
            return

        x = (rect.width() - size) / 2
        y = (rect.height() - size) / 2 - 10

        # Draw outer track
        pen_w = 12
        painter.setPen(QPen(self.track_color, pen_w, Qt.PenStyle.SolidLine, Qt.PenLineCapStyle.RoundCap))
        painter.drawArc(QRectF(x, y, size, size), 0, 360 * 16)

        # Draw filled arc starting from top (90 deg)
        start_angle = 90 * 16
        span_angle = int(-self.percentage * 3.6 * 16)
        painter.setPen(QPen(self.color, pen_w, Qt.PenStyle.SolidLine, Qt.PenLineCapStyle.RoundCap))
        painter.drawArc(QRectF(x, y, size, size), start_angle, span_angle)

        # Percentage label in center
        painter.setPen(QPen(self.text_color))
        painter.setFont(QFont(get_font_family(), 18, QFont.Weight.Bold))
        painter.drawText(
            QRectF(x, y, size, size),
            Qt.AlignmentFlag.AlignCenter,
            f"{self.percentage:.1f}%",
        )

        # Label text at bottom
        painter.setFont(QFont(get_font_family(), 11))
        painter.setPen(QPen(QColor("#a0aec0")))
        painter.drawText(
            QRectF(10, rect.height() - 35, rect.width() - 20, 24),
            Qt.AlignmentFlag.AlignCenter,
            self.label,
        )


class MetricCard(QFrame):
    """A premium dashboard summary card showing an icon, title, and total value."""

    def __init__(
        self,
        title: str,
        value: str,
        icon: str,
        color_hex: str = "#007bff",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {get_color('secondary_bg')};
                border: 1px solid {get_color('border_color')};
                border-radius: 12px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Circular icon background
        self.icon_lbl = QLabel(icon)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setFixedSize(50, 50)
        self.icon_lbl.setStyleSheet(f"""
            background-color: {color_hex}20;
            color: {color_hex};
            border-radius: 25px;
            font-size: 22px;
            border: none;
        """)
        layout.addWidget(self.icon_lbl)

        # Description text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"""
            color: {get_color('text_secondary')};
            font-size: 13px;
            background: transparent;
            border: none;
        """)
        text_layout.addWidget(self.title_lbl)

        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet(f"""
            color: {get_color('text_primary')};
            font-size: 20px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        text_layout.addWidget(self.value_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()

    def set_value(self, val: str) -> None:
        self.value_lbl.setText(val)


# ============================================================================
# Helpers
# ============================================================================


def make_bento_box(title: str, widget_or_layout: Any) -> QFrame:
    """Helper to wrap a view element in a card-style bento frame."""
    frame = QFrame()
    frame.setStyleSheet(f"""
        QFrame {{
            background-color: {get_color('secondary_bg')};
            border: 1px solid {get_color('border_color')};
            border-radius: 12px;
        }}
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(f"""
        font-size: 15px;
        font-weight: bold;
        color: {get_color('text_primary')};
        background: transparent;
        border: none;
    """)
    layout.addWidget(title_lbl)

    if isinstance(widget_or_layout, QLayout):
        layout.addLayout(widget_or_layout, 1)
    else:
        widget_or_layout.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(widget_or_layout, 1)

    return frame


def create_styled_table(headers: List[str]) -> QTableWidget:
    """Helper to initialize and style a flat headerless QTableWidget."""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(40)
    table.setMinimumHeight(240)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    table.setStyleSheet(f"""
        QTableWidget {{
            background-color: {get_color('primary_bg')};
            border: 1px solid {get_color('border_color')};
            border-radius: 8px;
            gridline-color: transparent;
            font-size: 13px;
        }}
        QHeaderView::section {{
            background-color: {get_color('secondary_bg')};
            color: {get_color('text_secondary')};
            padding: 8px;
            border: none;
            border-bottom: 2px solid {get_color('border_color')};
            font-weight: bold;
            font-size: 13px;
        }}
        QTableWidget::item {{
            padding: 10px;
            border-bottom: 1px solid {get_color('border_color')};
            color: {get_color('text_primary')};
            background-color: transparent;
        }}
    """)
    return table


# ============================================================================
# Main ReportsView
# ============================================================================


class ReportsView(QWidget):
    """The central widget for financial reporting.

    Uses tabs to navigate Daily, Monthly, and Yearly statistics.
    """

    def __init__(
        self,
        reports_controller: ReportsController,
        cashier_slot: int = 1,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ctrl = reports_controller
        self._cashier_slot = cashier_slot

        self._setup_ui()
        self._refresh_daily()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Tab widget container
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
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Add tabs
        self._tabs.addTab(self._build_daily_tab(), "التقرير اليومي 📅")
        self._tabs.addTab(self._build_monthly_tab(), "التقرير الشهري 📊")
        self._tabs.addTab(self._build_yearly_tab(), "التقرير السنوي 📈")

        layout.addWidget(self._tabs)

    # ------------------------------------------------------------------
    # Tab 1: Daily
    # ------------------------------------------------------------------

    def _build_daily_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        # 1. Date filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        lbl = QLabel("تاريخ التقرير:")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        filter_bar.addWidget(lbl)

        self._daily_date = QDateEdit()
        self._daily_date.setDate(QDate.currentDate())
        self._daily_date.setCalendarPopup(True)
        self._daily_date.setFixedWidth(160)
        self._daily_date.setStyleSheet(f"""
            QDateEdit {{
                background-color: {get_color('input_bg')};
                border: 2px solid {get_color('border_color')};
                border-radius: 6px;
                padding: 6px;
                color: {get_color('text_primary')};
                font-size: 14px;
            }}
            QDateEdit:focus {{
                border-color: {get_color('accent_blue')};
            }}
        """)
        self._daily_date.dateChanged.connect(self._refresh_daily)
        filter_bar.addWidget(self._daily_date)

        filter_bar.addStretch()

        self._daily_print_btn = QPushButton("🖨️  طباعة الملخص اليومي")
        self._daily_print_btn.setProperty("class", "confirm")
        self._daily_print_btn.clicked.connect(self._on_print_daily)
        filter_bar.addWidget(self._daily_print_btn)

        layout.addLayout(filter_bar)

        # Scroll area for dashboards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        grid = QVBoxLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        # 2. Metric summaries row
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self._daily_rev_card = MetricCard("إجمالي الإيرادات", "0.00 ج.م", "💰", get_color("accent_green"))
        self._daily_orders_card = MetricCard("عدد الفواتير", "0 فاتورة", "📝", get_color("accent_blue"))
        self._daily_cancelled_card = MetricCard("الطلبات الملغية", "0 طلب", "❌", get_color("accent_red"))
        self._daily_rest_rev_card = MetricCard("إيراد المطعم (بدون توصيل)", "0.00 ج.م", "🍽️", get_color("accent_orange"))

        metrics_layout.addWidget(self._daily_rev_card)
        metrics_layout.addWidget(self._daily_orders_card)
        metrics_layout.addWidget(self._daily_cancelled_card)
        metrics_layout.addWidget(self._daily_rest_rev_card)

        grid.addLayout(metrics_layout)

        # 3. Tables grid
        split_layout = QHBoxLayout()
        split_layout.setSpacing(12)

        # Left Column: Order Types and Payments
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        self._daily_types_table = create_styled_table(["نوع الطلب", "عدد الفواتير", "إجمالي المبيعات"])
        left_col.addWidget(make_bento_box("📦  مبيعات أنواع الطلبات", self._daily_types_table))

        self._daily_payments_table = create_styled_table(["طريقة الدفع", "عدد الفواتير", "إجمالي التحصيل"])
        left_col.addWidget(make_bento_box("💳  تحليل طرق الدفع", self._daily_payments_table))

        split_layout.addLayout(left_col, 1)

        # Right Column: Bestsellers & Drivers & Cancelled detail
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        self._daily_bestsellers_table = create_styled_table(["اسم الصنف", "الكمية المباعة", "القيمة"])
        right_col.addWidget(make_bento_box("🏆  الأصناف الأكثر مبيعاً اليوم", self._daily_bestsellers_table))

        self._daily_drivers_table = create_styled_table(["السائق", "الرحلات", "الطلبات", "حساب التوصيل"])
        right_col.addWidget(make_bento_box("🛵  ملخص حركة السائقين", self._daily_drivers_table))

        self._daily_cancelled_table = create_styled_table(["رقم الفاتورة", "المجموع", "الملغي بواسطة", "السبب"])
        right_col.addWidget(make_bento_box("❌  الفواتير الملغية وأسبابها", self._daily_cancelled_table))

        split_layout.addLayout(right_col, 1)

        grid.addLayout(split_layout)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        return widget

    def _refresh_daily(self) -> None:
        """Query Daily report statistics and populate tables."""
        qdate = self._daily_date.date()
        target = date(qdate.year(), qdate.month(), qdate.day())

        # Generate summary
        summary = self._ctrl.generate_daily_summary(target)

        # Set metrics
        self._daily_rev_card.set_value(f"{summary['gross_revenue']:,.2f} ج.م")
        orders_count = summary["sales_by_type"].get("grand_total", {}).get("count", 0)
        self._daily_orders_card.set_value(f"{orders_count} فاتورة")
        self._daily_cancelled_card.set_value(f"{summary['cancelled'].get('count', 0)} طلب")
        self._daily_rest_rev_card.set_value(f"{summary['restaurant_revenue']:,.2f} ج.م")

        # 1. Order Types Table
        types_table = self._daily_types_table
        types_table.setRowCount(0)
        breakdown = summary["sales_by_type"].get("breakdown", [])
        for entry in breakdown:
            row = types_table.rowCount()
            types_table.insertRow(row)
            types_table.setItem(row, 0, QTableWidgetItem(entry.get("label", entry.get("type"))))
            types_table.setItem(row, 1, QTableWidgetItem(str(entry.get("count", 0))))
            types_table.setItem(row, 2, QTableWidgetItem(f"{entry.get('revenue', 0.0):,.2f} ج.م"))

        # 2. Payments Table
        pay_table = self._daily_payments_table
        pay_table.setRowCount(0)
        payments = summary["payment_breakdown"].get("payments", [])
        for entry in payments:
            row = pay_table.rowCount()
            pay_table.insertRow(row)
            pay_table.setItem(row, 0, QTableWidgetItem(entry.get("label", entry.get("method"))))
            pay_table.setItem(row, 1, QTableWidgetItem(str(entry.get("count", 0))))
            pay_table.setItem(row, 2, QTableWidgetItem(f"{entry.get('revenue', 0.0):,.2f} ج.م"))

        # 3. Bestsellers Table
        bs_table = self._daily_bestsellers_table
        bs_table.setRowCount(0)
        bestsellers = summary.get("bestsellers", [])[:10]  # top 10 for screen
        for entry in bestsellers:
            row = bs_table.rowCount()
            bs_table.insertRow(row)
            bs_table.setItem(row, 0, QTableWidgetItem(entry.get("product_name", "")))
            bs_table.setItem(row, 1, QTableWidgetItem(str(entry.get("quantity", 0))))
            bs_table.setItem(row, 2, QTableWidgetItem(f"{entry.get('revenue', 0.0):,.2f} ج.م"))

        # 4. Drivers Table
        drv_table = self._daily_drivers_table
        drv_table.setRowCount(0)
        drivers = summary.get("driver_summary", [])
        for entry in drivers:
            row = drv_table.rowCount()
            drv_table.insertRow(row)
            drv_table.setItem(row, 0, QTableWidgetItem(entry.get("driver_name", "")))
            drv_table.setItem(row, 1, QTableWidgetItem(str(entry.get("trip_count", 0))))
            drv_table.setItem(row, 2, QTableWidgetItem(str(entry.get("order_count", 0))))
            drv_table.setItem(row, 3, QTableWidgetItem(f"{entry.get('total_fees', 0.0):,.2f} ج.م"))

        # 5. Cancelled Table
        cnc_table = self._daily_cancelled_table
        cnc_table.setRowCount(0)
        cancelled = summary["cancelled"].get("orders", [])
        for entry in cancelled:
            row = cnc_table.rowCount()
            cnc_table.insertRow(row)
            cnc_table.setItem(row, 0, QTableWidgetItem(f"#{entry.get('invoice_no', '')}"))
            cnc_table.setItem(row, 1, QTableWidgetItem(f"{entry.get('total', 0.0):,.2f} ج.م"))
            cnc_table.setItem(row, 2, QTableWidgetItem(entry.get("cancelled_by", "")))
            cnc_table.setItem(row, 3, QTableWidgetItem(entry.get("reason", "")))

    def _on_print_daily(self) -> None:
        """Trigger print for the daily summary."""
        shift_id = self._ctrl.get_active_shift_id()
        if shift_id is None:
            # Fallback to 1 if no active shift exists in database for this moment
            shift_id = 1

        qdate = self._daily_date.date()
        target = date(qdate.year(), qdate.month(), qdate.day())

        # Execute printing via controller
        success = self._ctrl.print_daily_summary(
            shift_id=shift_id,
            cashier_slot=self._cashier_slot,
            target_date=target,
        )
        if success:
            logger.info("Daily summary sent to printer successfully.")
        else:
            logger.warning("Failed to print daily summary.")

    # ------------------------------------------------------------------
    # Tab 2: Monthly
    # ------------------------------------------------------------------

    def _build_monthly_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        # 1. Filters Row
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        filter_bar.addWidget(QLabel("السنة:"))
        self._monthly_year = QComboBox()
        current_year = date.today().year
        for y in range(current_year - 5, current_year + 5):
            self._monthly_year.addItem(str(y), y)
        self._monthly_year.setCurrentText(str(current_year))
        self._monthly_year.currentIndexChanged.connect(self._refresh_monthly)
        filter_bar.addWidget(self._monthly_year)

        filter_bar.addWidget(QLabel("الشهر:"))
        self._monthly_month = QComboBox()
        arabic_months = [
            "يناير (1)", "فبراير (2)", "مارس (3)", "أبريل (4)", "مايو (5)", "يونيو (6)",
            "يوليو (7)", "أغسطس (8)", "سبتمبر (9)", "أكتوبر (10)", "نوفمبر (11)", "ديسمبر (12)"
        ]
        for idx, m_name in enumerate(arabic_months, 1):
            self._monthly_month.addItem(m_name, idx)
        self._monthly_month.setCurrentIndex(date.today().month - 1)
        self._monthly_month.currentIndexChanged.connect(self._refresh_monthly)
        filter_bar.addWidget(self._monthly_month)

        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        grid = QVBoxLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        # 2. Metric summaries
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self._month_sales_card = MetricCard("إجمالي المبيعات", "0.00 ج.م", "💰", get_color("accent_green"))
        self._month_expenses_card = MetricCard("إجمالي المصروفات", "0.00 ج.م", "📉", get_color("accent_red"))
        self._month_profit_card = MetricCard("صافي الأرباح", "0.00 ج.م", "📈", get_color("accent_blue"))

        metrics_layout.addWidget(self._month_sales_card)
        metrics_layout.addWidget(self._month_expenses_card)
        metrics_layout.addWidget(self._month_profit_card)

        grid.addLayout(metrics_layout)

        # 3. Main Dashboard grid layout
        dashboard_layout = QHBoxLayout()
        dashboard_layout.setSpacing(12)

        # Left: Graphical Daily Sales Chart
        self._month_chart = RoundedBarChartWidget()
        self._month_chart.setMinimumHeight(350)
        dashboard_layout.addWidget(make_bento_box("📊  مخطط المبيعات اليومية للشهر", self._month_chart), 2)

        # Right: Expenses Breakdown & Bestsellers list
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)

        self._month_expenses_table = create_styled_table(["الفئة", "المجموع"])
        right_panel.addWidget(make_bento_box("💸  فئات المصروفات للشهر", self._month_expenses_table), 1)

        self._month_bestsellers_table = create_styled_table(["اسم الصنف", "الكمية المباعة", "القيمة"])
        right_panel.addWidget(make_bento_box("🏆  الأصناف الأكثر مبيعاً للشهر", self._month_bestsellers_table), 1)

        dashboard_layout.addLayout(right_panel, 1)

        grid.addLayout(dashboard_layout)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        return widget

    def _refresh_monthly(self) -> None:
        """Load monthly stats and render bar charts."""
        year = self._monthly_year.currentData()
        month = self._monthly_month.currentData()
        if not year or not month:
            return

        # Fetch monthly data
        summary = self._ctrl.get_monthly_summary(year, month)
        expenses = self._ctrl.get_monthly_expenses(year, month)
        bestsellers = self._ctrl.get_monthly_bestsellers(year, month, limit=10)

        sales_val = summary.get("total_sales", 0.0)
        exp_val = expenses.get("total", 0.0)
        profit_val = sales_val - exp_val

        # Fill Metric cards
        self._month_sales_card.set_value(f"{sales_val:,.2f} ج.م")
        self._month_expenses_card.set_value(f"{exp_val:,.2f} ج.م")
        self._month_profit_card.set_value(f"{profit_val:,.2f} ج.م")
        if profit_val < 0:
            self._month_profit_card.icon_lbl.setStyleSheet(f"""
                background-color: {get_color('accent_red')}20;
                color: {get_color('accent_red')};
                border-radius: 25px; font-size: 22px; border: none;
            """)
        else:
            self._month_profit_card.icon_lbl.setStyleSheet(f"""
                background-color: {get_color('accent_blue')}20;
                color: {get_color('accent_blue')};
                border-radius: 25px; font-size: 22px; border: none;
            """)

        # 1. Draw daily sales bar chart
        chart_data = []
        for entry in summary.get("daily", []):
            try:
                dt = date.fromisoformat(entry["date"])
                day_lbl = str(dt.day)
            except Exception:
                day_lbl = entry["date"]
            chart_data.append({"label": day_lbl, "value": entry.get("sales", 0.0)})

        self._month_chart.set_data(chart_data, accent_color_hex=get_color("accent_blue"))

        # 2. Expenses breakdown table
        exp_table = self._month_expenses_table
        exp_table.setRowCount(0)
        categories = expenses.get("categories", {})
        cat_labels = {
            "delivery_fees": "أجور توصيل السائقين 🛵",
            "supplies": "خامات ومستلزمات مطعم 🥩",
            "other": "مصاريف ونثريات أخرى 🧾",
        }
        for cat, total in categories.items():
            row = exp_table.rowCount()
            exp_table.insertRow(row)
            exp_table.setItem(row, 0, QTableWidgetItem(cat_labels.get(cat, cat)))
            exp_table.setItem(row, 1, QTableWidgetItem(f"{total:,.2f} ج.م"))

        # 3. Bestsellers table
        bs_table = self._month_bestsellers_table
        bs_table.setRowCount(0)
        for entry in bestsellers:
            row = bs_table.rowCount()
            bs_table.insertRow(row)
            bs_table.setItem(row, 0, QTableWidgetItem(entry.get("product_name", "")))
            bs_table.setItem(row, 1, QTableWidgetItem(str(entry.get("quantity", 0))))
            bs_table.setItem(row, 2, QTableWidgetItem(f"{entry.get('revenue', 0.0):,.2f} ج.م"))

    # ------------------------------------------------------------------
    # Tab 3: Yearly
    # ------------------------------------------------------------------

    def _build_yearly_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        # Filters Row
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("اختر السنة المالية:"))
        self._yearly_year = QComboBox()
        current_year = date.today().year
        for y in range(current_year - 5, current_year + 5):
            self._yearly_year.addItem(str(y), y)
        self._yearly_year.setCurrentText(str(current_year))
        self._yearly_year.currentIndexChanged.connect(self._refresh_yearly)
        filter_bar.addWidget(self._yearly_year)
        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        grid = QVBoxLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        # Metrics cards
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)

        self._year_sales_card = MetricCard("إجمالي مبيعات السنة", "0.00 ج.م", "💰", get_color("accent_green"))
        self._year_expenses_card = MetricCard("إجمالي مصروفات السنة", "0.00 ج.م", "📉", get_color("accent_red"))
        self._year_profit_card = MetricCard("صافي الأرباح السنوية", "0.00 ج.م", "📈", get_color("accent_blue"))

        metrics_layout.addWidget(self._year_sales_card)
        metrics_layout.addWidget(self._year_expenses_card)
        metrics_layout.addWidget(self._year_profit_card)

        grid.addLayout(metrics_layout)

        # Yearly visual grid layout
        dashboard_layout = QHBoxLayout()
        dashboard_layout.setSpacing(12)

        # Left: Custom monthly bar chart
        self._year_chart = RoundedBarChartWidget()
        self._year_chart.setMinimumHeight(350)
        dashboard_layout.addWidget(make_bento_box("📊  مخطط المبيعات الشهرية للسنة", self._year_chart), 2)

        # Right: Bestsellers table
        self._year_bestsellers_table = create_styled_table(["اسم الصنف", "الكمية المباعة", "القيمة"])
        dashboard_layout.addWidget(make_bento_box("🏆  أعلى الأصناف مبيعاً للسنة", self._year_bestsellers_table), 1)

        grid.addLayout(dashboard_layout)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        return widget

    def _refresh_yearly(self) -> None:
        """Load yearly stats and render the 12-month bar chart."""
        year = self._yearly_year.currentData()
        if not year:
            return

        summary = self._ctrl.get_yearly_summary(year)
        bestsellers = self._ctrl.get_yearly_bestsellers(year, limit=10)

        sales_val = summary.get("total_sales", 0.0)
        exp_val = summary.get("total_expenses", 0.0)
        profit_val = sales_val - exp_val

        # Fill Metric cards
        self._year_sales_card.set_value(f"{sales_val:,.2f} ج.م")
        self._year_expenses_card.set_value(f"{exp_val:,.2f} ج.م")
        self._year_profit_card.set_value(f"{profit_val:,.2f} ج.م")
        if profit_val < 0:
            self._year_profit_card.icon_lbl.setStyleSheet(f"""
                background-color: {get_color('accent_red')}20;
                color: {get_color('accent_red')};
                border-radius: 25px; font-size: 22px; border: none;
            """)
        else:
            self._year_profit_card.icon_lbl.setStyleSheet(f"""
                background-color: {get_color('accent_blue')}20;
                color: {get_color('accent_blue')};
                border-radius: 25px; font-size: 22px; border: none;
            """)

        # 1. Fill monthly sales bar chart
        chart_data = []
        month_names = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
        for entry in summary.get("months", []):
            m_idx = entry.get("month", 1) - 1
            m_name = month_names[m_idx] if 0 <= m_idx < 12 else str(m_idx + 1)
            chart_data.append({"label": m_name, "value": entry.get("sales", 0.0)})

        self._year_chart.set_data(chart_data, accent_color_hex=get_color("accent_green"))

        # 2. Fill bestsellers table
        bs_table = self._year_bestsellers_table
        bs_table.setRowCount(0)
        for entry in bestsellers:
            row = bs_table.rowCount()
            bs_table.insertRow(row)
            bs_table.setItem(row, 0, QTableWidgetItem(entry.get("product_name", "")))
            bs_table.setItem(row, 1, QTableWidgetItem(str(entry.get("quantity", 0))))
            bs_table.setItem(row, 2, QTableWidgetItem(f"{entry.get('revenue', 0.0):,.2f} ج.م"))

    # ------------------------------------------------------------------
    # Tab Change Handler
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int) -> None:
        """Trigger loading of reports dynamically when a tab becomes active."""
        if index == 0:
            self._refresh_daily()
        elif index == 1:
            self._refresh_monthly()
        elif index == 2:
            self._refresh_yearly()
