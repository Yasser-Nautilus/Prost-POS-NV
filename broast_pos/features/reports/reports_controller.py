"""
Reports controller — orchestrates report generation, printing, and validation.

Connects the Reports View to ReportService + FinancialService + PrintTriggers.
All methods return plain dicts suitable for both UI display and printing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from broast_pos.core.services.report_service import ReportService
from broast_pos.core.services.financial_service import FinancialService

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
        printer_manager: Optional[Any] = None,
    ) -> None:
        self._report_svc = report_service
        self._financial_svc = financial_service
        self._printer = printer_manager

    # ------------------------------------------------------------------
    # Task 1: Aggregate Orders by Type
    # ------------------------------------------------------------------

    def get_sales_by_type(
        self, target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Group completed orders by type with count and revenue.

        Queries all non-cancelled orders for the given date.
        Groups by order_type: صالة, تيك اواي, دليفري, استلام محل.

        Args:
            target_date: Date to query. Defaults to today.

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
            raw = self._report_svc.generate_daily_sales(target_date)

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
                "breakdown": [],
                "grand_total": {"count": 0, "revenue": 0.0},
            }

    def get_payment_breakdown(
        self, target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Sales split by payment method (كاش / فيزا / اونلاين).

        Args:
            target_date: Date to query. Defaults to today.

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
            raw = self._report_svc.generate_payment_breakdown(target_date)

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
                "payments": [],
                "total": 0.0,
            }

    def get_bestsellers(
        self, target_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Top products by quantity sold for the day.

        Returns:
            [{"product_name": "...", "quantity": 45, "revenue": 1350.0}, ...]
        """
        try:
            return self._report_svc.generate_product_sales(target_date)
        except Exception as exc:
            logger.error("Failed to get bestsellers: %s", exc)
            return []

    def get_cancelled_orders(
        self, target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Cancelled orders with reasons."""
        try:
            return self._report_svc.generate_cancelled_orders(target_date)
        except Exception as exc:
            logger.error("Failed to get cancelled orders: %s", exc)
            return {"date": (target_date or date.today()).isoformat(), "count": 0, "orders": []}

    # ------------------------------------------------------------------
    # Task 2: Daily Summary Generation
    # ------------------------------------------------------------------

    def generate_daily_summary(
        self,
        target_date: Optional[date] = None,
        shift_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Full daily summary with revenue distinction and driver data.

        Combines:
          - Order type breakdown (صالة, تيك اواي, دليفري, استلام محل)
          - Payment method breakdown (كاش, فيزا, اونلاين)
          - Revenue distinction (gross_revenue vs restaurant_revenue)
          - Cancelled orders summary
          - Product bestsellers
          - Driver summary
          - Shift financial summary (if shift_id provided)

        Args:
            target_date: Date to generate summary for. Defaults to today.
            shift_id: Active shift ID (for shift-specific totals).

        Returns:
            {
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
        """
        d = target_date or date.today()

        try:
            sales = self.get_sales_by_type(d)
            payments = self.get_payment_breakdown(d)
            cancelled = self.get_cancelled_orders(d)
            bestsellers = self.get_bestsellers(d)

            # Driver summary
            try:
                drivers = self._report_svc.generate_driver_summary(d)
            except Exception:
                drivers = []

            # Revenue distinction: calculate from individual orders
            gross_revenue = sales["grand_total"]["revenue"]
            total_delivery_fees = sum(
                entry.get("revenue", 0)
                for entry in sales.get("breakdown", [])
                if entry.get("type") == "delivery"
            )
            # Delivery fees are already included in gross_revenue via order.total.
            # We need to calculate actual delivery_fee amounts from orders.
            try:
                d_str = d.isoformat()
                from broast_pos.data.repositories.order_repository import OrderRepository
                orders = self._report_svc._orders.get_completed_for_date(d_str)
                total_delivery_fees = round(
                    sum(o.delivery_fee for o in orders), 2,
                )
            except Exception:
                total_delivery_fees = 0.0

            restaurant_revenue = round(gross_revenue - total_delivery_fees, 2)

            # Shift-specific data
            shift_data = None
            if shift_id is not None:
                try:
                    shift_data = self._report_svc.generate_shift_close(shift_id)
                except Exception as exc:
                    logger.warning("Could not load shift summary: %s", exc)

            return {
                "date": d.isoformat(),
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
            logger.error("Failed to generate daily summary: %s", exc)
            return {
                "date": d.isoformat(),
                "generated_at": datetime.now().isoformat(),
                "sales_by_type": {"breakdown": [], "grand_total": {"count": 0, "revenue": 0.0}},
                "payment_breakdown": {"payments": [], "total": 0.0},
                "gross_revenue": 0.0,
                "restaurant_revenue": 0.0,
                "total_delivery_fees": 0.0,
                "cancelled": {"count": 0, "orders": []},
                "bestsellers": [],
                "driver_summary": [],
                "shift_summary": None,
            }

    # ------------------------------------------------------------------
    # Task 3: Print Integration
    # ------------------------------------------------------------------

    def print_daily_summary(
        self,
        shift_id: int,
        cashier_slot: int = 1,
        target_date: Optional[date] = None,
    ) -> bool:
        """Print the daily summary report — silent, non-blocking.

        Steps:
          1. Generate summary data
          2. Get shift period (opened_at, closed_at)
          3. Send to printer_manager.print_shift_summary()
          4. Mark summary as printed (prerequisite for shift close)

        Args:
            shift_id: Active shift ID.
            cashier_slot: 1 or 2 — determines which receipt printer.
            target_date: Defaults to today.

        Returns:
            True if print succeeded (or printer unavailable), False on error.
        """
        if self._printer is None:
            logger.warning("PrinterManager not configured — skipping print")
            return False

        try:
            summary = self.generate_daily_summary(target_date, shift_id)

            # Build shift period for header
            shift_period = None
            try:
                from broast_pos.data.repositories.financial_repository import FinancialRepository
                shift = self._financial_svc._financial.get_by_id(shift_id)
                if shift:
                    shift_period = {
                        "opened_at": shift.opened_at or "",
                        "closed_at": shift.closed_at or datetime.now().isoformat(),
                    }
            except Exception:
                pass

            printed = self._printer.print_shift_summary(
                summary, cashier_slot=cashier_slot, shift_period=shift_period,
            )

            if printed:
                # Mark as printed — prerequisite for shift close
                try:
                    self._financial_svc.mark_summary_printed(shift_id)
                except Exception as exc:
                    logger.warning("Summary printed but mark failed: %s", exc)

            return printed

        except Exception as exc:
            logger.error("Daily summary print failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Task 4: Consistency Checks
    # ------------------------------------------------------------------

    def validate_report(
        self, target_date: Optional[date] = None,
    ) -> Dict[str, Any]:
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
        warnings: List[str] = []

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

    def get_monthly_summary(self, year: int, month: int) -> Dict[str, Any]:
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
    ) -> List[Dict[str, Any]]:
        """Top products by quantity sold for a month."""
        try:
            return self._report_svc.generate_monthly_bestsellers(year, month, limit)
        except Exception as exc:
            logger.error("Failed to get monthly bestsellers: %s", exc)
            return []

    def get_monthly_expenses(self, year: int, month: int) -> Dict[str, Any]:
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

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
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
    ) -> List[Dict[str, Any]]:
        """Top products for the entire year."""
        try:
            return self._report_svc.generate_yearly_bestsellers(year, limit)
        except Exception as exc:
            logger.error("Failed to get yearly bestsellers: %s", exc)
            return []

