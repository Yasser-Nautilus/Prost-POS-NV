"""
Report service — data generation for daily, shift, monthly, and yearly reports.

All methods return plain dicts/dataclasses — NO print formatting here.
Print formatting is handled by receipt_templates.py in infrastructure.
Data is permanent — nothing deleted on shift close.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository


class ReportService:
    """Generate structured report data for display and printing."""

    def __init__(
        self,
        order_repo: Optional[OrderRepository] = None,
        financial_repo: Optional[FinancialRepository] = None,
        delivery_repo: Optional[DeliveryRepository] = None,
    ) -> None:
        self._orders = order_repo or OrderRepository()
        self._financial = financial_repo or FinancialRepository()
        self._delivery = delivery_repo or DeliveryRepository()

    # ------------------------------------------------------------------
    # Daily reports
    # ------------------------------------------------------------------

    def generate_daily_sales(self, target_date: Optional[date] = None) -> Dict:
        """Order type breakdown — count + revenue per type.

        Matches the receipt photo format:
          صالة: count × total
          تيك اواي: count × total
          دليفري: count × total
          استلام محل: count × total
          Grand total: count × total

        Returns:
            {
                "date": "2024-01-15",
                "breakdown": [
                    {"type": "صالة", "count": 15, "revenue": 2500.0},
                    ...
                ],
                "grand_total": {"count": 85, "revenue": 12500.0}
            }
        """
        d = (target_date or date.today()).isoformat()
        orders = self._orders.get_completed_for_date(d)

        type_map: Dict[str, Dict[str, Any]] = {}
        for order in orders:
            t = order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type)
            if t not in type_map:
                type_map[t] = {"type": t, "count": 0, "revenue": 0.0}
            type_map[t]["count"] += 1
            type_map[t]["revenue"] += order.total

        breakdown = list(type_map.values())
        grand_count = sum(b["count"] for b in breakdown)
        grand_revenue = sum(b["revenue"] for b in breakdown)

        return {
            "date": d,
            "breakdown": breakdown,
            "grand_total": {
                "count": grand_count,
                "revenue": round(grand_revenue, 2),
            },
        }

    def generate_payment_breakdown(
        self, target_date: Optional[date] = None,
    ) -> Dict:
        """Sales split by payment method (كاش / فيزا / اونلاين).

        Returns:
            {
                "date": "...",
                "payments": [
                    {"method": "cash", "count": 50, "revenue": 8000.0},
                    {"method": "visa", "count": 20, "revenue": 3000.0},
                    {"method": "online", "count": 15, "revenue": 1500.0},
                ],
                "total": 12500.0,
            }
        """
        d = (target_date or date.today()).isoformat()
        orders = self._orders.get_completed_for_date(d)

        method_map: Dict[str, Dict[str, Any]] = {}
        for order in orders:
            m = order.payment_method.value if hasattr(order.payment_method, "value") else str(order.payment_method)
            if m not in method_map:
                method_map[m] = {"method": m, "count": 0, "revenue": 0.0}
            method_map[m]["count"] += 1
            method_map[m]["revenue"] += order.total

        payments = list(method_map.values())

        return {
            "date": d,
            "payments": payments,
            "total": round(sum(p["revenue"] for p in payments), 2),
        }

    def generate_cancelled_orders(
        self, target_date: Optional[date] = None,
    ) -> Dict:
        """Cancelled orders count + reasons.

        Returns:
            {
                "date": "...",
                "count": 3,
                "orders": [
                    {"order_id": 45, "reason": "...", "cancelled_by": "..."},
                    ...
                ],
            }
        """
        d = (target_date or date.today()).isoformat()
        orders = self._orders.get_cancelled_for_date(d)

        items = []
        for o in orders:
            items.append({
                "order_id": o.id,
                "invoice_no": o.invoice_no,
                "total": o.total,
                "reason": o.cancel_reason or "",
                "cancelled_by": o.cancelled_by_name or "",
            })

        return {
            "date": d,
            "count": len(items),
            "orders": items,
        }

    def generate_product_sales(
        self, target_date: Optional[date] = None,
    ) -> List[Dict]:
        """Qty sold per product, sorted by popularity (highest first).

        Returns:
            [
                {"product_name": "...", "quantity": 45, "revenue": 1350.0},
                ...
            ]
        """
        d = (target_date or date.today()).isoformat()
        return self._orders.get_product_sales_for_date(d)

    def generate_driver_summary(
        self, target_date: Optional[date] = None,
    ) -> List[Dict]:
        """Per-driver trip/order/fee totals for the day.

        Returns:
            [
                {"driver_id": 5, "driver_name": "...", "trip_count": 8,
                 "order_count": 15, "total_fees": 120.0},
                ...
            ]
        """
        d = (target_date or date.today()).isoformat()
        return self._delivery.get_daily_summary(d)

    # ------------------------------------------------------------------
    # Shift reports
    # ------------------------------------------------------------------

    def generate_shift_transfer(self, shift_id: int) -> Dict:
        """Snapshot at transfer: sales, expenses, pending, expected cash."""
        summary = self._financial.get_shift_summary(shift_id)
        return {
            "shift_id": shift_id,
            "total_sales": summary.total_sales,
            "total_expenses": summary.total_expenses,
            "pending_delivery": summary.pending_delivery,
            "pending_dinein": summary.pending_dinein,
            "pending_kitchen": summary.pending_kitchen,
            "expected_cash": summary.expected_cash,
        }

    def generate_shift_close(self, shift_id: int) -> Dict:
        """Final summary for end of day — same data as transfer but final."""
        return self.generate_shift_transfer(shift_id)

    # ------------------------------------------------------------------
    # Monthly reports
    # ------------------------------------------------------------------

    def generate_monthly_summary(self, year: int, month: int) -> Dict:
        """Total sales + expenses + daily breakdown for a month.

        Returns:
            {
                "year": 2024, "month": 1,
                "total_sales": 250000.0,
                "total_expenses": 15000.0,
                "daily": [{"date": "2024-01-01", "sales": 8000, "expenses": 500}, ...]
            }
        """
        days_data = []
        total_sales = 0.0
        total_expenses = 0.0

        # Iterate all days in the month
        import calendar
        _, num_days = calendar.monthrange(year, month)

        for day in range(1, num_days + 1):
            d = date(year, month, day).isoformat()
            daily_sales = self._orders.get_daily_revenue(d)
            daily_expenses = self._financial.get_daily_expenses_total(d)

            days_data.append({
                "date": d,
                "sales": round(daily_sales, 2),
                "expenses": round(daily_expenses, 2),
            })
            total_sales += daily_sales
            total_expenses += daily_expenses

        return {
            "year": year,
            "month": month,
            "total_sales": round(total_sales, 2),
            "total_expenses": round(total_expenses, 2),
            "daily": days_data,
        }

    def generate_monthly_bestsellers(
        self, year: int, month: int, limit: int = 20,
    ) -> List[Dict]:
        """Top products by quantity sold for a month.

        Returns:
            [{"product_name": "...", "quantity": 320, "revenue": 9600.0}, ...]
        """
        start = date(year, month, 1).isoformat()
        import calendar
        _, num_days = calendar.monthrange(year, month)
        end = date(year, month, num_days).isoformat()

        return self._orders.get_product_sales_for_range(start, end, limit)

    def generate_monthly_expenses(self, year: int, month: int) -> Dict:
        """Expense breakdown by category for a month.

        Returns:
            {
                "year": 2024, "month": 1,
                "categories": {
                    "delivery_fees": 5000.0,
                    "supplies": 3000.0,
                    "other": 2000.0,
                },
                "total": 10000.0,
            }
        """
        start = date(year, month, 1).isoformat()
        import calendar
        _, num_days = calendar.monthrange(year, month)
        end = date(year, month, num_days).isoformat()

        breakdown = self._financial.get_expenses_by_category(start, end)
        return {
            "year": year,
            "month": month,
            "categories": breakdown,
            "total": round(sum(breakdown.values()), 2),
        }

    # ------------------------------------------------------------------
    # Yearly reports
    # ------------------------------------------------------------------

    def generate_yearly_summary(self, year: int) -> Dict:
        """12-month sales + expenses overview.

        Returns:
            {
                "year": 2024,
                "total_sales": 3000000.0,
                "total_expenses": 180000.0,
                "months": [{"month": 1, "sales": 250000, "expenses": 15000}, ...]
            }
        """
        months_data = []
        total_sales = 0.0
        total_expenses = 0.0

        for m in range(1, 13):
            monthly = self.generate_monthly_summary(year, m)
            months_data.append({
                "month": m,
                "sales": monthly["total_sales"],
                "expenses": monthly["total_expenses"],
            })
            total_sales += monthly["total_sales"]
            total_expenses += monthly["total_expenses"]

        return {
            "year": year,
            "total_sales": round(total_sales, 2),
            "total_expenses": round(total_expenses, 2),
            "months": months_data,
        }

    def generate_yearly_bestsellers(
        self, year: int, limit: int = 20,
    ) -> List[Dict]:
        """Top products for the entire year."""
        start = date(year, 1, 1).isoformat()
        end = date(year, 12, 31).isoformat()
        return self._orders.get_product_sales_for_range(start, end, limit)
