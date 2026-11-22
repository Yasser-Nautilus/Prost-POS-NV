"""
Reports controller — orchestrates report generation, printing, and validation.

Connects the Reports View to ReportService + FinancialService + PrintTriggers.
All methods return plain dicts suitable for both UI display and printing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.report_service import ReportService

logger = logging.getLogger(__name__)


class ReportsController:
    """Orchestrates report generation for the Reports View.

    This is the single entry point the UI calls. Views NEVER call
    ReportService or FinancialService directly.
    """

    def __init__(
        self,
        report_service: ReportService,
        financial_service: FinancialService,
        printer_manager: Any | None = None,
    ) -> None:
        self._report_svc = report_service
        self._financial_svc = financial_service
        self._printer = printer_manager

    # ------------------------------------------------------------------
    # H16: report scope — one shift OR one calendar day, never both
    # ------------------------------------------------------------------

    def validate_scope(
        self, target_date: date | None = None, shift_id: int | None = None,
    ) -> None:
        """Reject an ambiguous or unknown report scope.

        A report covers either one shift (``shift_id``) or one calendar day
        (``target_date``, default today). Passing both would mix shift totals
        with another period's sales, so it is refused.

        Raises:
            ValueError: both given, or the shift does not exist.
        """
        if shift_id is None:
            return
        if target_date is not None:
            raise ValueError("حدد وردية أو تاريخاً — وليس الاثنين معاً")
        if self._report_svc._orders.get_shift_business_date(shift_id) is None:
            raise ValueError("الوردية غير موجودة")

    # ------------------------------------------------------------------
    # Task 1: Aggregate Orders by Type
    # ------------------------------------------------------------------

    def get_sales_by_type(
        self, target_date: date | None = None, shift_id: int | None = None,
    ) -> dict[str, Any]:
        """Group completed orders by type with count and revenue.

        Queries all non-cancelled orders of the scope: one shift (``shift_id``)
        or one calendar day (``target_date``, default today).
        Groups by order_type: صالة, تيك اواي, دليفري, استلام محل.

        Args:
            target_date: Day to query. Defaults to today. Not with shift_id.
            shift_id: Query this shift instead of a calendar day.

        Returns:
            {
                "date": "2024-01-15",
                "breakdown": [
                    {"type": "dine_in", "label": "صالة", "count": 15, "revenue": 2500.0},
                    {"type": "takeaway", "label": "تيك اواي", "count": 8, "revenue": 1890.0},
                    ...
                ],
                "grand_total": {"count": 38, "revenue": 10240.0}
            }
        """
        try:
            raw = (
                self._report_svc.generate_daily_sales_for_shift(shift_id)
                if shift_id is not None
                else self._report_svc.generate_daily_sales(target_date)
            )

            # Add Arabic labels for display
            type_labels = {
                "dine_in": "صالة",
                "takeaway": "تيك اواي",
                "delivery": "دليفري",
                "pickup": "استلام محل",
            }

            for entry in raw.get("breakdown", []):
                entry["label"] = type_labels.get(entry["type"], entry["type"])

            return raw

        except Exception as exc:
            logger.error("Failed to aggregate orders by type: %s", exc)
            return {
                "date": (target_date or date.today()).isoformat(),
                "shift_id": shift_id,
                "breakdown": [],
                "grand_total": {"count": 0, "revenue": 0.0},
            }

    def get_payment_breakdown(
        self, target_date: date | None = None, shift_id: int | None = None,
    ) -> dict[str, Any]:
        """Sales split by payment method (كاش / فيزا / اونلاين).

        Args:
            target_date: Day to query. Defaults to today. Not with shift_id.
            shift_id: Query this shift instead of a calendar day.

        Returns:
            {
                "date": "...",
                "payments": [
                    {"method": "cash", "label": "كاش", "count": 50, "revenue": 8000.0},
                    ...
                ],
                "total": 12500.0
            }
        """
        try:
            raw = (
                self._report_svc.generate_payment_breakdown_for_shift(shift_id)
                if shift_id is not None
                else self._report_svc.generate_payment_breakdown(target_date)
            )

            method_labels = {
                "cash": "كاش",
                "visa": "فيزا",
                "online": "اونلاين",
            }

            for entry in raw.get("payments", []):
                entry["label"] = method_labels.get(entry["method"], entry["method"])

            return raw

        except Exception as exc:
            logger.error("Failed to get payment breakdown: %s", exc)
            return {
                "date": (target_date or date.today()).isoformat(),
                "shift_id": shift_id,
                "payments": [],
                "total": 0.0,
            }

    def get_bestsellers(
        self, target_date: date | None = None, shift_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Top products by quantity sold for one shift or one calendar day.

        Returns:
            [{"product_name": "...", "quantity": 45, "revenue": 1350.0}, ...]
        """
        try:
            if shift_id is not None:
                return self._report_svc.generate_product_sales_for_shift(shift_id)
            return self._report_svc.generate_product_sales(target_date)
        except Exception as exc:
            logger.error("Failed to get bestsellers: %s", exc)
            return []

    def get_cancelled_orders(
        self, target_date: date | None = None, shift_id: int | None = None,
    ) -> dict[str, Any]:
        """Cancelled orders with reasons, for one shift or one calendar day."""
        try:
            if shift_id is not None:
                return self._report_svc.generate_cancellations_for_shift(shift_id)
            return self._report_svc.generate_cancelled_orders(target_date)
        except Exception as exc:
            logger.error("Failed to get cancelled orders: %s", exc)
            return {
                "date": (target_date or date.today()).isoformat(),
                "shift_id": shift_id,
                "count": 0,
                "orders": [],
            }

    # ------------------------------------------------------------------
    # Task 2: Daily Summary Generation
    # ------------------------------------------------------------------

    def generate_daily_summary(
        self,
        target_date: date | None = None,
        shift_id: int | None = None,
    ) -> dict[str, Any]:
        """Full summary of ONE scope: a shift, or a calendar day (H16).

        - ``shift_id`` given  → shift report. Every section (sales by type,
          payments, cancellations, bestsellers, drivers, delivery fees) and the
          cash totals come from that shift. ``date`` is the shift's business
          date (the day it was opened), so a shift spanning midnight is one
          report.
        - otherwise           → day report for ``target_date`` (default today).
          Everything is filtered by calendar date; ``shift_summary`` is None.

        Combining both is refused: shift cash totals next to another period's
        sales were exactly the mix this method used to produce.

        Combines:
          - Order type breakdown (صالة, تيك اواي, دليفري, استلام محل)
          - Payment method breakdown (كاش, فيزا, اونلاين)
          - Revenue distinction (gross_revenue vs restaurant_revenue)
          - Cancelled orders summary
          - Product bestsellers
          - Driver summary
          - Shift financial summary (shift reports only)

        Args:
            target_date: Calendar day for a day report. Defaults to today.
            shift_id: Shift to report on (shift report). Not with target_date.

        Returns:
            {
                "scope": "shift" | "day",
                "shift_id": 7 | None,
                "date": "2024-01-15",
                "generated_at": "2024-01-15T23:30:00",
                "sales_by_type": {...},
                "payment_breakdown": {...},
                "gross_revenue": 12500.0,
                "restaurant_revenue": 11800.0,
                "total_delivery_fees": 700.0,
                "cancelled": {...},
                "bestsellers": [...],
                "driver_summary": [...],
                "shift_summary": {...} | None,
            }

        Raises:
            ValueError: shift and date both given, unknown shift, or the
                report could not be generated.
        """
        self.validate_scope(target_date, shift_id)
        is_shift = shift_id is not None
        d = target_date or date.today()

        try:
            sales = self.get_sales_by_type(d, shift_id) if is_shift else self.get_sales_by_type(d)
            payments = (
                self.get_payment_breakdown(d, shift_id) if is_shift else self.get_payment_breakdown(d)
            )
            cancelled = (
                self.get_cancelled_orders(d, shift_id) if is_shift else self.get_cancelled_orders(d)
            )
            bestsellers = self.get_bestsellers(d, shift_id) if is_shift else self.get_bestsellers(d)

            # Driver summary
            try:
                drivers = (
                    self._report_svc.generate_driver_summary_for_shift(shift_id)
                    if is_shift
                    else self._report_svc.generate_driver_summary(d)
                )
            except Exception:
                drivers = []

            # Revenue distinction: calculate from individual orders
            gross_revenue = sales["grand_total"]["revenue"]
            # Delivery fees are already included in gross_revenue via order.total.
            # We need to calculate actual delivery_fee amounts from orders.
            try:
                orders = (
                    self._report_svc._orders.get_completed_for_shift(shift_id)
                    if is_shift
                    else self._report_svc._orders.get_completed_for_date(d.isoformat())
                )
                total_delivery_fees = round(
                    sum(o.delivery_fee for o in orders), 2,
                )
            except Exception:
                total_delivery_fees = 0.0

            restaurant_revenue = round(gross_revenue - total_delivery_fees, 2)

            # Shift-specific data (shift reports only)
            shift_data = None
            if is_shift:
                try:
                    shift_data = self._report_svc.generate_shift_close(shift_id)
                except Exception as exc:
                    logger.warning("Could not load shift summary: %s", exc)

            report_date = (
                self._report_svc._orders.get_shift_business_date(shift_id) or ""
                if is_shift
                else d.isoformat()
            )

            return {
                "scope": "shift" if is_shift else "day",
                "shift_id": shift_id,
                "date": report_date,
                "generated_at": datetime.now().isoformat(),
                "sales_by_type": sales,
                "payment_breakdown": payments,
                "gross_revenue": gross_revenue,
                "restaurant_revenue": restaurant_revenue,
                "total_delivery_fees": total_delivery_fees,
                "cancelled": cancelled,
                "bestsellers": bestsellers,
                "driver_summary": drivers,
                "shift_summary": shift_data,
            }

        except Exception as exc:
            logger.exception("Failed to generate daily summary: %s", exc)
            raise ValueError(f"خطأ في إنشاء التقرير اليومي: {exc}")

    # ------------------------------------------------------------------
    # Task 3: Print Integration
    # ------------------------------------------------------------------

    def print_daily_summary(
        self,
        shift_id: int | None = None,
        cashier_slot: int = 1,
        target_date: date | None = None,
    ) -> bool:
        """Print a summary report — silent, non-blocking.

        H16: prints ONE scope, the same one ``generate_daily_summary`` shows.
          * ``shift_id`` → shift report (header with the shift's period). The
            shift is marked "summary printed", which shift close requires.
          * ``target_date`` (or neither) → calendar-day report. This prints no
            shift period and never marks a shift as printed.
        Passing both is refused (returns False).

        Steps:
          1. Generate summary data
          2. Get shift period (opened_at, closed_at) — shift reports only
          3. Send to printer_manager.print_shift_summary()
          4. Mark summary as printed — shift reports only

        Args:
            shift_id: Shift to print.
            cashier_slot: 1 or 2 — determines which receipt printer.
            target_date: Calendar day to print. Defaults to today.

        Returns:
            True if print succeeded (or printer unavailable), False on error.
        """
        if self._printer is None:
            logger.warning("PrinterManager not configured — skipping print")
            return False

        try:
            summary = self.generate_daily_summary(target_date, shift_id)

            # H16: the template expects top-level "breakdown"/"grand_total",
            # but generate_daily_summary nests the sales breakdown under
            # "sales_by_type" — adapt once, here, instead of in the template.
            sales = summary.get("sales_by_type") or {}
            report_payload = {
                "breakdown": sales.get("breakdown", []),
                "grand_total": sales.get("grand_total", {"count": 0, "revenue": 0.0}),
            }

            # Build shift period for header (shift reports only) — the template
            # expects separate from/to date and time keys, not opened_at/closed_at.
            shift_period = None
            if shift_id is not None:
                try:
                    shift = self._financial_svc._financial.get_by_id(shift_id)
                    if shift:
                        opened = shift.opened_at or ""
                        closed = shift.closed_at or datetime.now().isoformat()
                        from_date, from_time = self._split_date_time(opened)
                        to_date, to_time = self._split_date_time(closed)
                        shift_period = {
                            "from_date": from_date,
                            "from_time": from_time,
                            "to_date": to_date,
                            "to_time": to_time,
                        }
                except Exception:
                    # Checkup-Fix: shift period is optional for the summary, but log failures.
                    logger.warning("Loading shift period for report failed", exc_info=True)

            printed = self._printer.print_shift_summary(
                report_payload, cashier_slot=cashier_slot, shift_period=shift_period,
            )

            if printed and shift_id is not None:
                # Mark as printed — prerequisite for shift close
                try:
                    self._financial_svc.mark_summary_printed(shift_id)
                except Exception as exc:
                    logger.warning("Summary printed but mark failed: %s", exc)

            return printed

        except Exception as exc:
            logger.error("Daily summary print failed: %s", exc)
            return False

    @staticmethod
    def _split_date_time(timestamp: str) -> tuple[str, str]:
        """H16: split a stored "YYYY-MM-DD HH:MM:SS" timestamp into
        separate date/time strings for the print template's header."""
        try:
            dt = timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(timestamp)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
        except (ValueError, TypeError):
            ts = str(timestamp)
            return (ts[:10] if len(ts) >= 10 else ""), ""

    # ------------------------------------------------------------------
    # Task 4: Consistency Checks
    # ------------------------------------------------------------------

    def validate_report(
        self, target_date: date | None = None,
    ) -> dict[str, Any]:
        """Cross-validate report totals for data integrity.

        Checks:
          1. Sum of individual order totals == reported grand total
          2. Cancelled orders are excluded from revenue
          3. Revenue = gross - delivery fees

        Returns:
            {
                "is_valid": True/False,
                "calculated_total": 12500.0,
                "reported_total": 12500.0,
                "discrepancy": 0.0,
                "warnings": [],
            }
        """
        d = target_date or date.today()
        d_str = d.isoformat()
        warnings: list[str] = []

        try:
            # Get individual order totals
            orders = self._report_svc._orders.get_completed_for_date(d_str)
            calculated_total = round(sum(o.total for o in orders), 2)

            # Get aggregate from report
            sales = self._report_svc.generate_daily_sales(d)
            reported_total = sales["grand_total"]["revenue"]

            discrepancy = round(abs(calculated_total - reported_total), 2)

            if discrepancy > 0.01:
                warnings.append(
                    f"فرق بين المجموع المحسوب ({calculated_total}) "
                    f"والمجموع المبلغ عنه ({reported_total}): {discrepancy}"
                )

            # Check no cancelled orders leaked into revenue
            cancelled = self._report_svc._orders.get_cancelled_for_date(d_str)
            cancelled_ids = {o.id for o in cancelled}
            leaked = [o for o in orders if o.id in cancelled_ids]
            if leaked:
                warnings.append(
                    f"طلبات ملغاة ({len(leaked)}) ظهرت في الإيرادات"
                )

            # Revenue consistency: gross - delivery = restaurant
            total_fees = round(sum(o.delivery_fee for o in orders), 2)
            restaurant_rev = round(calculated_total - total_fees, 2)
            individual_restaurant = round(
                sum(o.restaurant_revenue for o in orders), 2,
            )
            if abs(restaurant_rev - individual_restaurant) > 0.01:
                warnings.append(
                    f"فرق في إيرادات المطعم: مجموع ({restaurant_rev}) "
                    f"≠ مفرد ({individual_restaurant})"
                )

            return {
                "is_valid": len(warnings) == 0,
                "calculated_total": calculated_total,
                "reported_total": reported_total,
                "discrepancy": discrepancy,
                "warnings": warnings,
            }

        except Exception as exc:
            logger.error("Report validation failed: %s", exc)
            return {
                "is_valid": False,
                "calculated_total": 0.0,
                "reported_total": 0.0,
                "discrepancy": 0.0,
                "warnings": [f"فشل التحقق: {exc}"],
            }

    # ------------------------------------------------------------------
    # Monthly reports wrappers
    # ------------------------------------------------------------------

    def get_monthly_summary(self, year: int, month: int) -> dict[str, Any]:
        """Total sales + expenses + daily breakdown for a month."""
        try:
            return self._report_svc.generate_monthly_summary(year, month)
        except Exception as exc:
            logger.error("Failed to get monthly summary: %s", exc)
            return {
                "year": year,
                "month": month,
                "total_sales": 0.0,
                "total_expenses": 0.0,
                "daily": [],
            }

    def get_monthly_bestsellers(
        self, year: int, month: int, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Top products by quantity sold for a month."""
        try:
            return self._report_svc.generate_monthly_bestsellers(year, month, limit)
        except Exception as exc:
            logger.error("Failed to get monthly bestsellers: %s", exc)
            return []

    def get_monthly_expenses(self, year: int, month: int) -> dict[str, Any]:
        """Expense breakdown by category for a month."""
        try:
            return self._report_svc.generate_monthly_expenses(year, month)
        except Exception as exc:
            logger.error("Failed to get monthly expenses: %s", exc)
            return {
                "year": year,
                "month": month,
                "categories": {},
                "total": 0.0,
            }

    # ------------------------------------------------------------------
    # Yearly reports wrappers
    # ------------------------------------------------------------------

    def get_yearly_summary(self, year: int) -> dict[str, Any]:
        """12-month sales + expenses overview."""
        try:
            return self._report_svc.generate_yearly_summary(year)
        except Exception as exc:
            logger.error("Failed to get yearly summary: %s", exc)
            return {
                "year": year,
                "total_sales": 0.0,
                "total_expenses": 0.0,
                "months": [],
            }

    def get_yearly_bestsellers(
        self, year: int, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Top products for the entire year."""
        try:
            return self._report_svc.generate_yearly_bestsellers(year, limit)
        except Exception as exc:
            logger.error("Failed to get yearly bestsellers: %s", exc)
            return []

    def get_active_shift_id(self) -> int | None:
        """Get current active shift ID."""
        try:
            shift = self._financial_svc._financial.get_active_shift()
            return shift.id if shift else None
        except Exception as exc:
            logger.error("Failed to get active shift ID: %s", exc)
            return None

