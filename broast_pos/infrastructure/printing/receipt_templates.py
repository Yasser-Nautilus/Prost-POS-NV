"""
Receipt templates — all print layouts for 80mm thermal format.

Generates ESC/POS command sequences via :class:`EscPosPrinter`.
ALL branding text (name, slogan, footer) is loaded from ``restaurant.json``
via :func:`broast_pos.config.config.get_restaurant_info`. **No hardcoded
Arabic branding strings in this file.**

H15: every low-level EscPosPrinter call returns a bool. Each template
aggregates those results with AND and returns the aggregate, instead of
unconditionally returning True — a failed text/cut/etc. step now makes the
whole job report failure, matching what actually reached the paper.

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
from typing import Any

from broast_pos.config.config import get_restaurant_info
from broast_pos.infrastructure.printing.escpos_printer import EscPosPrinter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LINE_WIDTH = 32           # 80mm thermal = ~32 chars
SEPARATOR = "-" * LINE_WIDTH
DOUBLE_SEP = "=" * LINE_WIDTH
CUT_LINE = "- " * 8 + "✂" + " -" * 8

# Order type display labels
ORDER_TYPE_LABELS: dict[str, dict[str, str]] = {
    "dine_in":  {"ar": "صالة",       "en": "Dine IN"},
    "takeaway": {"ar": "تيك اواي",   "en": "Takeaway"},
    "delivery": {"ar": "دليفري",     "en": "Delivery"},
    "pickup":   {"ar": "استلام محل", "en": "Pickup"},
}

PAYMENT_LABELS: dict[str, str] = {
    "cash":   "كاش",
    "visa":   "فيزا",
    "online": "اونلاين",
}


# ---------------------------------------------------------------------------
# Branding helpers
# ---------------------------------------------------------------------------

def _get_branding() -> dict[str, str]:
    """Return branding dict from restaurant.json."""
    info = get_restaurant_info()
    return {
        "name_ar": info.get("name_ar", ""),
        "name_en": info.get("name_en", ""),
        "slogan_ar": info.get("slogan_ar", ""),
        "receipt_footer": info.get("receipt_footer", ""),
    }


def _print_header(printer: EscPosPrinter, brand: dict[str, str]) -> bool:
    """Print the restaurant header block. Returns True iff every line printed."""
    ok = printer.print_double_line(LINE_WIDTH)
    name_line = f"{brand['name_ar']} / {brand['name_en']}"
    ok &= printer.print_text(name_line, align="center")
    ok &= printer.print_text("-", align="center")
    return ok


def _print_copy_label(printer: EscPosPrinter, order: dict[str, Any]) -> bool:
    """Copies are explicit, including unpaid or cancelled historical orders."""
    if not order.get("is_copy"):
        return True
    ok = printer.print_text("نسخة / COPY", align="center", bold=True, double_height=True)
    if order.get("created_at"):
        ok &= printer.print_text(str(order["created_at"]), align="center")
    if order.get("status") == "cancelled":
        ok &= printer.print_text("طلب ملغي / CANCELLED", align="center", bold=True)
    if not order.get("is_paid"):
        ok &= printer.print_text("غير مدفوع / UNPAID", align="center", bold=True)
    return ok


def _print_footer(printer: EscPosPrinter, brand: dict[str, str]) -> bool:
    """Print the branded footer + cut line. Returns True iff every line printed."""
    ok = printer.print_line("-", LINE_WIDTH)
    if brand["slogan_ar"]:
        ok &= printer.print_text(brand["slogan_ar"], align="center")
    if brand["receipt_footer"]:
        ok &= printer.print_text(brand["receipt_footer"], align="center")
    ok &= printer.print_text(CUT_LINE, align="center")
    return ok


def _print_items_table(
    printer: EscPosPrinter,
    items: list[dict[str, Any]],
    *,
    show_prices: bool = True,
) -> bool:
    """Print item rows. Returns True iff every row printed.

    Args:
        items: list of dicts with keys: product_name, quantity, unit_price,
               total_price, notes (optional).
        show_prices: False for kitchen tickets (no financial info).
    """
    ok = True
    if show_prices:
        ok &= printer.print_text(" Total  | Price  | Qty  | Item", align="left")
        ok &= printer.print_line("-", LINE_WIDTH)
        for item in items:
            qty = int(item.get("quantity", 0))
            price = f"{item.get('unit_price', 0):.2f}"
            total = f"{item.get('total_price', 0):.2f}"
            name = item.get("product_name", "")
            ok &= printer.print_text(f" {total:>6} | {price:>6} | {qty:>3}  | {name}")
            notes = item.get("notes", "")
            if notes:
                ok &= printer.print_text(f"            ملاحظة: {notes}")
    else:
        ok &= printer.print_text("   Qty  |  Item", align="left")
        ok &= printer.print_line("-", LINE_WIDTH)
        for item in items:
            qty = int(item.get("quantity", 0))
            name = item.get("product_name", "")
            ok &= printer.print_text(f"   {qty:>3}  |  {name}")
            notes = item.get("notes", "")
            if notes:
                ok &= printer.print_text(f"           ملاحظة: {notes}")
    return ok


def _fmt_money(value) -> str:
    """Format a monetary value to 2 decimal places."""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


# ===========================================================================
# 1. Customer Receipt — Dine-In
# ===========================================================================

def print_dinein_receipt(printer: EscPosPrinter, order: dict[str, Any]) -> bool:
    """Print a dine-in customer receipt.

    Args:
        printer: The cashier's printer.
        order: Dict with order data (from Order dataclass / service).

    Returns:
        True only if every step of the job actually printed.
    """
    brand = _get_branding()
    ok = _print_header(printer, brand)
    ok &= _print_copy_label(printer, order)

    ok &= printer.print_text(f"Dine IN                Station: {order.get('cashier_slot', '')}")
    ok &= printer.print_text(f"Cashier: {order.get('cashier_name', '')}      Table: {order.get('table_no', '')}")
    ok &= printer.print_text(f"Order NO: {order.get('invoice_no', '')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    ok &= _print_items_table(printer, order.get("items", []), show_prices=True)

    ok &= printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        ok &= printer.print_text(f"Service:              {_fmt_money(service)}")

    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("Total", align="center")
    ok &= printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    ok &= printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    ok &= printer.print_text(f"Payment:           {payment}")
    ok &= printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    ok &= printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    ok &= _print_footer(printer, brand)
    ok &= printer.cut()
    return ok


# ===========================================================================
# 2. Customer Receipt — Delivery
# ===========================================================================

def print_delivery_receipt(printer: EscPosPrinter, order: dict[str, Any]) -> bool:
    """Print a delivery customer receipt."""
    brand = _get_branding()
    ok = _print_header(printer, brand)
    ok &= _print_copy_label(printer, order)

    ok &= printer.print_text(f"Delivery               Station: {order.get('cashier_slot', '')}")
    ok &= printer.print_text(f"Cashier: {order.get('cashier_name', '')}     Order: #{order.get('invoice_no', '')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    # Customer info
    ok &= printer.print_text(f"العميل:   {order.get('customer_name', '')}")
    ok &= printer.print_text(f"الهاتف:   {order.get('customer_phone', '')}")
    ok &= printer.print_text(f"العنوان:  {order.get('customer_address', '')}")
    ok &= printer.print_text(f"المنطقة:  {order.get('customer_zone', '')}")
    ok &= printer.print_text(f"المندوب:  {order.get('driver_name', '')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    ok &= _print_items_table(printer, order.get("items", []), show_prices=True)

    ok &= printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        ok &= printer.print_text(f"Service:              {_fmt_money(service)}")
    ok &= printer.print_text(f"Delivery Fee:         {_fmt_money(order.get('delivery_fee', 0))}")

    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("Total", align="center")
    ok &= printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    ok &= printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    ok &= printer.print_text(f"Payment:           {payment}")
    ok &= printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    ok &= printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    ok &= _print_footer(printer, brand)
    ok &= printer.cut()
    return ok


# ===========================================================================
# 3. Customer Receipt — Takeaway
# ===========================================================================

def print_takeaway_receipt(printer: EscPosPrinter, order: dict[str, Any]) -> bool:
    """Print a takeaway customer receipt.

    Same as dine-in but: no table, shows TAKEAWAY banner.
    """
    brand = _get_branding()
    ok = _print_header(printer, brand)
    ok &= _print_copy_label(printer, order)

    ok &= printer.print_text("** TAKEAWAY — انتظار **", align="center", bold=True)
    ok &= printer.print_text(f"Takeaway               Station: {order.get('cashier_slot', '')}")
    ok &= printer.print_text(f"Cashier: {order.get('cashier_name', '')}     Order: #{order.get('invoice_no', '')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    ok &= _print_items_table(printer, order.get("items", []), show_prices=True)

    ok &= printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        ok &= printer.print_text(f"Service:              {_fmt_money(service)}")

    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("Total", align="center")
    ok &= printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    ok &= printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    ok &= printer.print_text(f"Payment:           {payment}")
    ok &= printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    ok &= printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    ok &= _print_footer(printer, brand)
    ok &= printer.cut()
    return ok


# ===========================================================================
# 4. Customer Receipt — Pickup
# ===========================================================================

def print_pickup_receipt(printer: EscPosPrinter, order: dict[str, Any]) -> bool:
    """Print a pickup customer receipt.

    Shows customer name + phone (ordered by phone, will collect).
    No address/zone/driver. No delivery fee.
    """
    brand = _get_branding()
    ok = _print_header(printer, brand)
    ok &= _print_copy_label(printer, order)

    ok &= printer.print_text("** PICKUP — استلام من المحل **", align="center", bold=True)
    ok &= printer.print_text(f"Pickup                 Station: {order.get('cashier_slot', '')}")
    ok &= printer.print_text(f"Cashier: {order.get('cashier_name', '')}     Order: #{order.get('invoice_no', '')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    ok &= printer.print_text(f"العميل:   {order.get('customer_name', '')}")
    ok &= printer.print_text(f"الهاتف:   {order.get('customer_phone', '')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    ok &= _print_items_table(printer, order.get("items", []), show_prices=True)

    ok &= printer.print_line("-", LINE_WIDTH)
    service = order.get("service_amount", 0)
    if service:
        ok &= printer.print_text(f"Service:              {_fmt_money(service)}")

    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("Total", align="center")
    ok &= printer.print_text(_fmt_money(order.get("total", 0)), align="center", bold=True, double_height=True)
    ok &= printer.print_double_line(LINE_WIDTH)

    payment = PAYMENT_LABELS.get(order.get("payment_method", ""), order.get("payment_method", ""))
    ok &= printer.print_text(f"Payment:           {payment}")
    ok &= printer.print_text(f"Paid:              {_fmt_money(order.get('amount_paid', 0))}")
    ok &= printer.print_text(f"Change:            {_fmt_money(order.get('change_given', 0))}")

    ok &= _print_footer(printer, brand)
    ok &= printer.cut()
    return ok


# ===========================================================================
# 5. Kitchen Ticket
# ===========================================================================

def print_kitchen_ticket(printer: EscPosPrinter, order: dict[str, Any]) -> bool:
    """Print a kitchen ticket — NO prices, NO customer info, NO totals.

    Order number is printed LARGE for easy identification.
    """
    order_type_key = order.get("order_type", "dine_in")
    labels = ORDER_TYPE_LABELS.get(order_type_key, {"ar": "", "en": ""})

    ok = printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(labels["ar"], align="center")
    ok &= printer.print_text(f"{labels['en']}    Station: {order.get('cashier_slot', '')}", align="center")

    if order_type_key == "dine_in":
        ok &= printer.print_text(f"Table No. {order.get('table_no', '')}", align="center")

    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(f"Cashier: {order.get('cashier_name', '')}")
    now = datetime.now()
    ok &= printer.print_text(f"Print On: {now.strftime('%Y-%m-%d')}      {now.strftime('%H:%M')}")
    ok &= printer.print_double_line(LINE_WIDTH)

    # Order number — LARGE BOLD
    ok &= printer.print_text(
        f"Order NO: {order.get('invoice_no', '')}",
        align="center",
        bold=True,
        double_width=True,
        double_height=True,
    )
    ok &= printer.print_double_line(LINE_WIDTH)

    ok &= _print_items_table(printer, order.get("items", []), show_prices=False)

    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(CUT_LINE, align="center")
    ok &= printer.cut()
    return ok


# ===========================================================================
# 6. Amendment Kitchen Ticket (تابع)
# ===========================================================================

def print_amendment_ticket(
    printer: EscPosPrinter,
    order: dict[str, Any],
    changes: list[dict[str, Any]],
) -> bool:
    """Print an amendment kitchen ticket.

    No fixed section headers — changes are printed directly as they are.

    Args:
        order: The parent order (for invoice_no, cashier).
        changes: List of change dicts with keys:
            - product_name, quantity, notes (optional)
            Each item represents an actual change (add or remove).
    """
    ok = printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(
        f"تابع — Order #{order.get('invoice_no', '')}",
        align="center",
        bold=True,
        double_width=True,
        double_height=True,
    )
    ok &= printer.print_double_line(LINE_WIDTH)

    ok &= printer.print_text(f"Cashier: {order.get('cashier_name', '')}")
    now = datetime.now()
    ok &= printer.print_text(f"Print On: {now.strftime('%Y-%m-%d')}      {now.strftime('%H:%M')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    # Print changes directly — no section headers
    for change in changes:
        qty = int(change.get("quantity", 0))
        name = change.get("product_name", "")
        ok &= printer.print_text(f"   {qty:>3}  |  {name}")
        notes = change.get("notes", "")
        if notes:
            ok &= printer.print_text(f"           ملاحظة: {notes}")

    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(CUT_LINE, align="center")
    ok &= printer.cut()
    return ok


# ===========================================================================
# 7. End-of-Day Sales Report
# ===========================================================================

def print_daily_sales_report(
    printer: EscPosPrinter,
    report: dict[str, Any],
    shift_period: dict[str, str] | None = None,
) -> bool:
    """Print the daily sales report (matches receipt photo format).

    Args:
        report: From ReportService.generate_daily_sales().
        shift_period: {"from_time": "08:00", "from_date": "...",
                       "to_time": "23:00", "to_date": "..."}.
    """
    now = datetime.now()
    ok = printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("اجمالي مبيعات", align="center")
    if report.get("date"):
        ok &= printer.print_text(f"Report date: {report['date']}", align="center")
    if report.get("shift_id") is not None:
        ok &= printer.print_text(f"Shift: {report['shift_id']}", align="center")
    ok &= printer.print_text("في الفترة", align="center")
    if shift_period:
        ok &= printer.print_text(f"من {shift_period.get('from_time', '')} {shift_period.get('from_date', '')}", align="center")
        ok &= printer.print_text(f"الى {shift_period.get('to_time', '')} {shift_period.get('to_date', '')}", align="center")
    elif report.get("date"):
        ok &= printer.print_text(f"Calendar day: {report['date']}", align="center")
    else:
        ok &= printer.print_text("Report period unavailable", align="center")
    ok &= printer.print_text(f"Printed: {now.strftime('%Y-%m-%d %H:%M')}", align="center")

    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("نوع الاوردر | عدد الاوردرات | اجمالي المبلغ")
    ok &= printer.print_line("-", LINE_WIDTH)

    for entry in report.get("breakdown", []):
        t = entry.get("type", "")
        count = entry.get("count", 0)
        revenue = _fmt_money(entry.get("revenue", 0))
        ok &= printer.print_text(f"{t:<12} |  {count:>4}   | {revenue}")

    ok &= printer.print_line("-", LINE_WIDTH)
    grand = report.get("grand_total", {})
    ok &= printer.print_text(
        f"الاجمالي     |  {grand.get('count', 0):>4}   | {_fmt_money(grand.get('revenue', 0))}",
        bold=True,
    )
    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(CUT_LINE, align="center")
    ok &= printer.cut()
    return ok


# ===========================================================================
# 8. Shift Transfer Report
# ===========================================================================

def print_shift_transfer_report(
    printer: EscPosPrinter,
    transfer: dict[str, Any],
) -> bool:
    """Print shift transfer report (mid-day cashier handover)."""
    now = datetime.now()

    ok = printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("تقرير تسليم وردية — Shift Transfer", align="center")
    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(f"التاريخ: {now.strftime('%Y-%m-%d')}     اليوم: {now.strftime('%A')}")
    ok &= printer.print_text(f"من: {transfer.get('from_cashier', '')}    الى: {transfer.get('to_cashier', '')}")
    ok &= printer.print_text(f"الوقت: {now.strftime('%H:%M')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    ok &= printer.print_text(f"اجمالي المبيعات:        {_fmt_money(transfer.get('total_sales', 0))}")
    ok &= printer.print_text(f"اجمالي المصروفات:      -{_fmt_money(transfer.get('total_expenses', 0))}")
    ok &= printer.print_text(f"معلق دليفري:           -{_fmt_money(transfer.get('pending_delivery', 0))}")
    ok &= printer.print_text(f"معلق صالة:             -{_fmt_money(transfer.get('pending_dinein', 0))}")
    ok &= printer.print_text(f"معلق مطبخ:             -{_fmt_money(transfer.get('pending_kitchen', 0))}")
    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(
        f"المتوقع في الدرج:       {_fmt_money(transfer.get('expected_cash', 0))}",
        bold=True,
    )
    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(CUT_LINE, align="center")
    ok &= printer.cut()
    return ok


# ===========================================================================
# 9. Driver Settlement Receipt
# ===========================================================================

def print_driver_settlement(
    printer: EscPosPrinter,
    settlement: dict[str, Any],
) -> bool:
    """Print a per-trip driver settlement receipt."""
    ok = printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("تسوية مندوب — Driver Settlement", align="center")
    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(f"المندوب: {settlement.get('driver_name', '')}")
    ok &= printer.print_text(f"التاريخ: {settlement.get('date', '')}")
    ok &= printer.print_text(f"الرحلة:  #{settlement.get('trip_number', '')}")
    ok &= printer.print_line("-", LINE_WIDTH)

    # Order rows
    ok &= printer.print_text("Invoice | Order Total | Payment  | Collected")
    ok &= printer.print_line("-", LINE_WIDTH)
    for order in settlement.get("orders", []):
        inv = order.get("invoice_no", "")
        total = _fmt_money(order.get("total", 0))
        payment = PAYMENT_LABELS.get(order.get("payment_method", ""), "")
        collected = _fmt_money(order.get("collected", 0))
        ok &= printer.print_text(f"#{inv:<5}  |  {total:>8}  | {payment:<8} | {collected}")

    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(f"اجمالي الكاش:           {_fmt_money(settlement.get('cash_collected', 0))}")
    ok &= printer.print_text(f"عمولة التوصيل:          {_fmt_money(settlement.get('delivery_fees', 0))}")
    ok &= printer.print_text(
        f"المبلغ المطلوب تسليمه:   {_fmt_money(settlement.get('cash_collected', 0))}",
        bold=True,
    )
    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(CUT_LINE, align="center")
    ok &= printer.cut()
    return ok


# ===========================================================================
# 10. End-of-Day Driver Summary
# ===========================================================================

def print_driver_summary(
    printer: EscPosPrinter,
    summary: dict[str, Any],
) -> bool:
    """Print the daily driver summary (all drivers who worked)."""
    ok = printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("ملخص المناديب — Driver Summary", align="center")
    ok &= printer.print_text(f"التاريخ: {summary.get('date', '')}")
    ok &= printer.print_double_line(LINE_WIDTH)

    ok &= printer.print_text("Driver     | Trips | Orders | Fees")
    ok &= printer.print_line("-", LINE_WIDTH)

    for driver in summary.get("drivers", []):
        name = driver.get("driver_name", "")
        trips = driver.get("trip_count", 0)
        orders = driver.get("order_count", 0)
        fees = _fmt_money(driver.get("total_fees", 0))
        ok &= printer.print_text(f"{name:<11}|  {trips:>3}  |  {orders:>4}  | {fees}")

    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(
        f"اجمالي عمولات المناديب:  {_fmt_money(summary.get('total_fees', 0))}",
        bold=True,
    )
    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(CUT_LINE, align="center")
    ok &= printer.cut()
    return ok


# ===========================================================================
# 11. Driver end-of-day settlement sheet (orders counted by delivery fee)
# ===========================================================================

def print_driver_day_sheet(
    printer: EscPosPrinter,
    sheet: dict[str, Any],
) -> bool:
    """Print the driver's end-of-day settlement: order count per delivery fee."""
    ok = printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text("تسوية آخر اليوم — Driver Day Settlement", align="center")
    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(f"السائق: {sheet.get('driver_name', '')}")
    if sheet.get("driver_phone"):
        ok &= printer.print_text(f"التليفون: {sheet.get('driver_phone')}")
    ok &= printer.print_text(f"التاريخ: {sheet.get('settlement_date', '')}")
    ok &= printer.print_text(
        f"الرحلات: {sheet.get('trip_count', 0)}   الأوردرات: {sheet.get('order_count', 0)}"
    )
    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text("رسم التوصيل | عدد الأوردرات | الإجمالي")
    for row in sheet.get("fee_breakdown", []):
        ok &= printer.print_text(
            f"{_fmt_money(row.get('fee', 0)):>10} | {row.get('order_count', 0):>10} | "
            f"{_fmt_money(row.get('subtotal', 0))}"
        )
    ok &= printer.print_line("-", LINE_WIDTH)
    ok &= printer.print_text(
        f"إجمالي رسوم التوصيل:  {_fmt_money(sheet.get('total_delivery_fees', 0))}",
        bold=True,
    )
    ok &= printer.print_text("توقيع السائق: ______________")
    ok &= printer.print_double_line(LINE_WIDTH)
    ok &= printer.print_text(CUT_LINE, align="center")
    ok &= printer.cut()
    return ok


# ===========================================================================
# Template dispatcher
# ===========================================================================

RECEIPT_PRINTERS = {
    "dine_in": print_dinein_receipt,
    "takeaway": print_takeaway_receipt,
    "delivery": print_delivery_receipt,
    "pickup": print_pickup_receipt,
}


def print_customer_receipt(printer: EscPosPrinter, order: dict[str, Any]) -> bool:
    """Auto-select the correct receipt template based on order type."""
    order_type = order.get("order_type", "dine_in")
    template_fn = RECEIPT_PRINTERS.get(order_type)
    if template_fn is None:
        return False
    return template_fn(printer, order)
