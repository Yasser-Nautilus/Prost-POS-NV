"""
Reports controller — orchestrates report generation, printing, and validation.

Connects the Reports View to ReportService + FinancialService + PrintTriggers.
All methods return plain dicts suitable for both UI display and printing.
"""

from __future__ import annotations

import logging
from datetime import date
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
    ) -> None:
        self._report_svc = report_service
        self._financial_svc = financial_service

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
