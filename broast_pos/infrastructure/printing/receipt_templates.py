"""
Receipt templates — all print layouts for 80mm thermal format.

Generates ESC/POS command sequences via :class:`EscPosPrinter`.
ALL branding text (name, slogan, footer) is loaded from ``restaurant.json``
via :func:`broast_pos.config.config.get_restaurant_info`. **No hardcoded
Arabic branding strings in this file.**

Template catalogue:
    1. Customer receipt — Dine-In
    2. Customer receipt — Delivery
    3. Customer receipt — Takeaway
    4. Customer receipt — Pickup
    5. Kitchen ticket
    6. Amendment kitchen ticket (تابع)
    7. End-of-day sales report
    8. Shift transfer report
    9. Driver settlement receipt
   10. Driver summary
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from broast_pos.config.config import get_restaurant_info, SERVICE_CHARGE_PCT
from broast_pos.infrastructure.printing.escpos_printer import EscPosPrinter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LINE_WIDTH = 32           # 80mm thermal = ~32 chars
SEPARATOR = "-" * LINE_WIDTH
DOUBLE_SEP = "=" * LINE_WIDTH
CUT_LINE = "- " * 8 + "✂" + " -" * 8

# Order type display labels
ORDER_TYPE_LABELS: Dict[str, Dict[str, str]] = {
    "dine_in":  {"ar": "صالة",       "en": "Dine IN"},
    "takeaway": {"ar": "تيك اواي",   "en": "Takeaway"},
    "delivery": {"ar": "دليفري",     "en": "Delivery"},
    "pickup":   {"ar": "استلام محل", "en": "Pickup"},
}

PAYMENT_LABELS: Dict[str, str] = {
    "cash":   "كاش",
    "visa":   "فيزا",
    "online": "اونلاين",
}


# ---------------------------------------------------------------------------
# Branding helpers
# ---------------------------------------------------------------------------

def _get_branding() -> Dict[str, str]:
    """Return branding dict from restaurant.json."""
    info = get_restaurant_info()
    return {
        "name_ar": info.get("name_ar", ""),
        "name_en": info.get("name_en", ""),
        "slogan_ar": info.get("slogan_ar", ""),
        "receipt_footer": info.get("receipt_footer", ""),
    }


def _print_header(printer: EscPosPrinter, brand: Dict[str, str]) -> None:
    """Print the restaurant header block."""
    printer.print_double_line(LINE_WIDTH)
    name_line = f"{brand['name_ar']} / {brand['name_en']}"
    printer.print_text(name_line, align="center")
    printer.print_text("-", align="center")


def _print_footer(printer: EscPosPrinter, brand: Dict[str, str]) -> None:
    """Print the branded footer + cut line."""
    printer.print_line("-", LINE_WIDTH)
    if brand["slogan_ar"]:
        printer.print_text(brand["slogan_ar"], align="center")
    if brand["receipt_footer"]:
        printer.print_text(brand["receipt_footer"], align="center")
    printer.print_text(CUT_LINE, align="center")


def _print_items_table(
    printer: EscPosPrinter,
    items: List[Dict[str, Any]],
    *,
    show_prices: bool = True,
) -> None:
    """Print item rows.

    Args:
        items: list of dicts with keys: product_name, quantity, unit_price,
               total_price, notes (optional).
        show_prices: False for kitchen tickets (no financial info).
    """
    if show_prices:
        printer.print_text(" Total  | Price  | Qty  | Item", align="left")
        printer.print_line("-", LINE_WIDTH)
        for item in items:
            qty = int(item.get("quantity", 0))
            price = f"{item.get('unit_price', 0):.2f}"
            total = f"{item.get('total_price', 0):.2f}"
            name = item.get("product_name", "")
            printer.print_text(f" {total:>6} | {price:>6} | {qty:>3}  | {name}")
            notes = item.get("notes", "")
            if notes:
                printer.print_text(f"            ملاحظة: {notes}")
    else:
        printer.print_text("   Qty  |  Item", align="left")
        printer.print_line("-", LINE_WIDTH)
        for item in items:
            qty = int(item.get("quantity", 0))
            name = item.get("product_name", "")
            printer.print_text(f"   {qty:>3}  |  {name}")
            notes = item.get("notes", "")
            if notes:
                printer.print_text(f"           ملاحظة: {notes}")


def _fmt_money(value) -> str:
    """Format a monetary value to 2 decimal places."""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


# ===========================================================================
# 1. Customer Receipt — Dine-In
# ===========================================================================

def print_dinein_receipt(printer: EscPosPrinter, order: Dict[str, Any]) -> bool:
    """Print a dine-in customer receipt.

    Args:
        printer: The cashier's printer.
        order: Dict with order data (from Order dataclass / service).

    Returns:
        True if printed successfully.
    """
    brand = _get_branding()
    _print_header(printer, brand)

    printer.print_text(f"Dine IN                Station: {order.get('cashier_slot', '')}")
    printer.print_text(f"Cashier: {order.get('cashier_name', '')}      Table: {order.get('table_no', '')}")
    printer.print_text(f"Order NO: {order.get('invoice_no', '')}")
    printer.print_line("-", LINE_WIDTH)

    _print_items_table(printer, order.get("items", []), show_prices=True)

    printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        printer.print_text(f"Service:              {_fmt_money(service)}")

    printer.print_double_line(LINE_WIDTH)
    printer.print_text("Total", align="center")
    printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    printer.print_text(f"Payment:           {payment}")
    printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    _print_footer(printer, brand)
    printer.cut()
    return True


# ===========================================================================
# 2. Customer Receipt — Delivery
# ===========================================================================

def print_delivery_receipt(printer: EscPosPrinter, order: Dict[str, Any]) -> bool:
    """Print a delivery customer receipt."""
    brand = _get_branding()
    _print_header(printer, brand)

    printer.print_text(f"Delivery               Station: {order.get('cashier_slot', '')}")
    printer.print_text(f"Cashier: {order.get('cashier_name', '')}     Order: #{order.get('invoice_no', '')}")
    printer.print_line("-", LINE_WIDTH)

    # Customer info
    printer.print_text(f"العميل:   {order.get('customer_name', '')}")
    printer.print_text(f"الهاتف:   {order.get('customer_phone', '')}")
    printer.print_text(f"العنوان:  {order.get('customer_address', '')}")
    printer.print_text(f"المنطقة:  {order.get('customer_zone', '')}")
    printer.print_text(f"المندوب:  {order.get('driver_name', '')}")
    printer.print_line("-", LINE_WIDTH)

    _print_items_table(printer, order.get("items", []), show_prices=True)

    printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        printer.print_text(f"Service:              {_fmt_money(service)}")
    printer.print_text(f"Delivery Fee:         {_fmt_money(order.get('delivery_fee', 0))}")

    printer.print_double_line(LINE_WIDTH)
    printer.print_text("Total", align="center")
    printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    printer.print_text(f"Payment:           {payment}")
    printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    _print_footer(printer, brand)
    printer.cut()
    return True


# ===========================================================================
# 3. Customer Receipt — Takeaway
# ===========================================================================

def print_takeaway_receipt(printer: EscPosPrinter, order: Dict[str, Any]) -> bool:
    """Print a takeaway customer receipt.

    Same as dine-in but: no table, shows TAKEAWAY banner.
    """
    brand = _get_branding()
    _print_header(printer, brand)

    printer.print_text("** TAKEAWAY — انتظار **", align="center", bold=True)
    printer.print_text(f"Takeaway               Station: {order.get('cashier_slot', '')}")
    printer.print_text(f"Cashier: {order.get('cashier_name', '')}     Order: #{order.get('invoice_no', '')}")
    printer.print_line("-", LINE_WIDTH)

    _print_items_table(printer, order.get("items", []), show_prices=True)

    printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        printer.print_text(f"Service:              {_fmt_money(service)}")

    printer.print_double_line(LINE_WIDTH)
    printer.print_text("Total", align="center")
    printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    printer.print_text(f"Payment:           {payment}")
    printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    _print_footer(printer, brand)
    printer.cut()
    return True


# ===========================================================================
# 4. Customer Receipt — Pickup
# ===========================================================================

def print_pickup_receipt(printer: EscPosPrinter, order: Dict[str, Any]) -> bool:
    """Print a pickup customer receipt.

    Shows customer name + phone (ordered by phone, will collect).
    No address/zone/driver. No delivery fee.
    """
    brand = _get_branding()
    _print_header(printer, brand)

    printer.print_text("** PICKUP — استلام من المحل **", align="center", bold=True)
    printer.print_text(f"Pickup                 Station: {order.get('cashier_slot', '')}")
    printer.print_text(f"Cashier: {order.get('cashier_name', '')}     Order: #{order.get('invoice_no', '')}")
    printer.print_line("-", LINE_WIDTH)

    printer.print_text(f"العميل:   {order.get('customer_name', '')}")
    printer.print_text(f"الهاتف:   {order.get('customer_phone', '')}")
    printer.print_line("-", LINE_WIDTH)

    _print_items_table(printer, order.get("items", []), show_prices=True)

    printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        printer.print_text(f"Service:              {_fmt_money(service)}")

    printer.print_double_line(LINE_WIDTH)
    printer.print_text("Total", align="center")
    printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    printer.print_text(f"Payment:           {payment}")
    printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    _print_footer(printer, brand)
    printer.cut()
    return True


# ===========================================================================
# 5. Kitchen Ticket
# ===========================================================================

def print_kitchen_ticket(printer: EscPosPrinter, order: Dict[str, Any]) -> bool:
    """Print a kitchen ticket — NO prices, NO customer info, NO totals.

    Order number is printed LARGE for easy identification.
    """
    order_type_key = order.get("order_type", "dine_in")
    labels = ORDER_TYPE_LABELS.get(order_type_key, {"ar": "", "en": ""})

    printer.print_double_line(LINE_WIDTH)
    printer.print_text(labels["ar"], align="center")
    printer.print_text(f"{labels['en']}    Station: {order.get('cashier_slot', '')}", align="center")

    if order_type_key == "dine_in":
        printer.print_text(f"Table No. {order.get('table_no', '')}", align="center")

    printer.print_line("-", LINE_WIDTH)
    printer.print_text(f"Cashier: {order.get('cashier_name', '')}")
    now = datetime.now()
    printer.print_text(f"Print On: {now.strftime('%Y-%m-%d')}      {now.strftime('%H:%M')}")
    printer.print_double_line(LINE_WIDTH)

    # Order number — LARGE BOLD
    printer.print_text(
        f"Order NO: {order.get('invoice_no', '')}",
        align="center",
        bold=True,
        double_width=True,
        double_height=True,
    )
    printer.print_double_line(LINE_WIDTH)

    _print_items_table(printer, order.get("items", []), show_prices=False)

    printer.print_line("-", LINE_WIDTH)
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(CUT_LINE, align="center")
    printer.cut()
    return True


# ===========================================================================
# 6. Amendment Kitchen Ticket (تابع)
# ===========================================================================

def print_amendment_ticket(
    printer: EscPosPrinter,
    order: Dict[str, Any],
    changes: List[Dict[str, Any]],
) -> bool:
    """Print an amendment kitchen ticket.

    No fixed section headers — changes are printed directly as they are.

    Args:
        order: The parent order (for invoice_no, cashier).
        changes: List of change dicts with keys:
            - product_name, quantity, notes (optional)
            Each item represents an actual change (add or remove).
    """
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(
        f"تابع — Order #{order.get('invoice_no', '')}",
        align="center",
        bold=True,
        double_width=True,
        double_height=True,
    )
    printer.print_double_line(LINE_WIDTH)

    printer.print_text(f"Cashier: {order.get('cashier_name', '')}")
    now = datetime.now()
    printer.print_text(f"Print On: {now.strftime('%Y-%m-%d')}      {now.strftime('%H:%M')}")
    printer.print_line("-", LINE_WIDTH)

    # Print changes directly — no section headers
    for change in changes:
        qty = int(change.get("quantity", 0))
        name = change.get("product_name", "")
        printer.print_text(f"   {qty:>3}  |  {name}")
        notes = change.get("notes", "")
        if notes:
            printer.print_text(f"           ملاحظة: {notes}")

    printer.print_line("-", LINE_WIDTH)
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(CUT_LINE, align="center")
    printer.cut()
    return True


# ===========================================================================
# 7. End-of-Day Sales Report
# ===========================================================================

def print_daily_sales_report(
    printer: EscPosPrinter,
    report: Dict[str, Any],
    shift_period: Optional[Dict[str, str]] = None,
) -> bool:
    """Print the daily sales report (matches receipt photo format).

    Args:
        report: From ReportService.generate_daily_sales().
        shift_period: {"from_time": "08:00", "from_date": "...",
                       "to_time": "23:00", "to_date": "..."}.
    """
    now = datetime.now()
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(f"{now.strftime('%Y-%m-%d')}           {now.strftime('%A')}", align="center")
    printer.print_text("اجمالي مبيعات", align="center")
    printer.print_text("في الفترة", align="center")

    if shift_period:
        printer.print_text(f"من {shift_period.get('from_time', '')} {shift_period.get('from_date', '')}", align="center")
        printer.print_text(f"الى {shift_period.get('to_time', '')}  {shift_period.get('to_date', '')}", align="center")

    printer.print_double_line(LINE_WIDTH)
    printer.print_text("نوع الاوردر | عدد الاوردرات | اجمالي المبلغ")
    printer.print_line("-", LINE_WIDTH)

    for entry in report.get("breakdown", []):
        t = entry.get("type", "")
        count = entry.get("count", 0)
        revenue = _fmt_money(entry.get("revenue", 0))
        printer.print_text(f"{t:<12} |  {count:>4}   | {revenue}")

    printer.print_line("-", LINE_WIDTH)
    grand = report.get("grand_total", {})
    printer.print_text(
        f"الاجمالي     |  {grand.get('count', 0):>4}   | {_fmt_money(grand.get('revenue', 0))}",
        bold=True,
    )
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(CUT_LINE, align="center")
    printer.cut()
    return True


# ===========================================================================
# 8. Shift Transfer Report
# ===========================================================================

def print_shift_transfer_report(
    printer: EscPosPrinter,
    transfer: Dict[str, Any],
) -> bool:
    """Print shift transfer report (mid-day cashier handover)."""
    now = datetime.now()

    printer.print_double_line(LINE_WIDTH)
    printer.print_text("تقرير تسليم وردية — Shift Transfer", align="center")
    printer.print_line("-", LINE_WIDTH)
    printer.print_text(f"التاريخ: {now.strftime('%Y-%m-%d')}     اليوم: {now.strftime('%A')}")
    printer.print_text(f"من: {transfer.get('from_cashier', '')}    الى: {transfer.get('to_cashier', '')}")
    printer.print_text(f"الوقت: {now.strftime('%H:%M')}")
    printer.print_line("-", LINE_WIDTH)

    printer.print_text(f"اجمالي المبيعات:        {_fmt_money(transfer.get('total_sales', 0))}")
    printer.print_text(f"اجمالي المصروفات:      -{_fmt_money(transfer.get('total_expenses', 0))}")
    printer.print_text(f"معلق دليفري:           -{_fmt_money(transfer.get('pending_delivery', 0))}")
    printer.print_text(f"معلق صالة:             -{_fmt_money(transfer.get('pending_dinein', 0))}")
    printer.print_text(f"معلق مطبخ:             -{_fmt_money(transfer.get('pending_kitchen', 0))}")
    printer.print_line("-", LINE_WIDTH)
    printer.print_text(
        f"المتوقع في الدرج:       {_fmt_money(transfer.get('expected_cash', 0))}",
        bold=True,
    )
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(CUT_LINE, align="center")
    printer.cut()
    return True


# ===========================================================================
# 9. Driver Settlement Receipt
# ===========================================================================

def print_driver_settlement(
    printer: EscPosPrinter,
    settlement: Dict[str, Any],
) -> bool:
    """Print a per-trip driver settlement receipt."""
    printer.print_double_line(LINE_WIDTH)
    printer.print_text("تسوية مندوب — Driver Settlement", align="center")
    printer.print_line("-", LINE_WIDTH)
    printer.print_text(f"المندوب: {settlement.get('driver_name', '')}")
    printer.print_text(f"التاريخ: {settlement.get('date', '')}")
    printer.print_text(f"الرحلة:  #{settlement.get('trip_number', '')}")
    printer.print_line("-", LINE_WIDTH)

    # Order rows
    printer.print_text("Invoice | Order Total | Payment  | Collected")
    printer.print_line("-", LINE_WIDTH)
    for order in settlement.get("orders", []):
        inv = order.get("invoice_no", "")
        total = _fmt_money(order.get("total", 0))
        payment = PAYMENT_LABELS.get(order.get("payment_method", ""), "")
        collected = _fmt_money(order.get("collected", 0))
        printer.print_text(f"#{inv:<5}  |  {total:>8}  | {payment:<8} | {collected}")

    printer.print_line("-", LINE_WIDTH)
    printer.print_text(f"اجمالي الكاش:           {_fmt_money(settlement.get('cash_collected', 0))}")
    printer.print_text(f"عمولة التوصيل:          {_fmt_money(settlement.get('delivery_fees', 0))}")
    printer.print_text(
        f"المبلغ المطلوب تسليمه:   {_fmt_money(settlement.get('cash_collected', 0))}",
        bold=True,
    )
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(CUT_LINE, align="center")
    printer.cut()
    return True


# ===========================================================================
# 10. End-of-Day Driver Summary
# ===========================================================================

def print_driver_summary(
    printer: EscPosPrinter,
    summary: Dict[str, Any],
) -> bool:
    """Print the daily driver summary (all drivers who worked)."""
    printer.print_double_line(LINE_WIDTH)
    printer.print_text("ملخص المناديب — Driver Summary", align="center")
    printer.print_text(f"التاريخ: {summary.get('date', '')}")
    printer.print_double_line(LINE_WIDTH)

    printer.print_text("Driver     | Trips | Orders | Fees")
    printer.print_line("-", LINE_WIDTH)

    for driver in summary.get("drivers", []):
        name = driver.get("driver_name", "")
        trips = driver.get("trip_count", 0)
        orders = driver.get("order_count", 0)
        fees = _fmt_money(driver.get("total_fees", 0))
        printer.print_text(f"{name:<11}|  {trips:>3}  |  {orders:>4}  | {fees}")

    printer.print_line("-", LINE_WIDTH)
    printer.print_text(
        f"اجمالي عمولات المناديب:  {_fmt_money(summary.get('total_fees', 0))}",
        bold=True,
    )
    printer.print_double_line(LINE_WIDTH)
    printer.print_text(CUT_LINE, align="center")
    printer.cut()
    return True


# ===========================================================================
# Template dispatcher
# ===========================================================================

RECEIPT_PRINTERS = {
    "dine_in": print_dinein_receipt,
    "takeaway": print_takeaway_receipt,
    "delivery": print_delivery_receipt,
    "pickup": print_pickup_receipt,
}


def print_customer_receipt(printer: EscPosPrinter, order: Dict[str, Any]) -> bool:
    """Auto-select the correct receipt template based on order type."""
    order_type = order.get("order_type", "dine_in")
    template_fn = RECEIPT_PRINTERS.get(order_type)
    if template_fn is None:
        return False
    return template_fn(printer, order)
