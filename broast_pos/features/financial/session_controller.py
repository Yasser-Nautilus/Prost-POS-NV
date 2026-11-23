"""
SessionController — API surface for cashier sessions (v2).

Follows the same controller pattern as FinancialController:
  - Thin orchestration layer between bridge dispatch and service layer
  - Returns dicts (JSON-serializable) or raises ValueError with Arabic messages
  - All business logic stays in the service; controller only serializes/deserializes

Exposed bridge actions:
  session.open           → open_session()
  session.close          → close_session()
  session.handover       → do_handover()
  session.get_active     → get_active_sessions()
  session.get_balance    → get_session_balance()
  session.x_report       → generate_x_report()
  session.close_day      → close_business_day()
"""

from __future__ import annotations

import logging
from typing import Any

from broast_pos.core.models.cashier_session import CashierSession, Station
from broast_pos.core.policies.input_values import cash_amount
from broast_pos.core.services.business_day_service import (
    BusinessDayService,
    SessionSnapshot,
    XReport,
)
from broast_pos.core.services.cashier_session_service import CashierSessionService

logger = logging.getLogger(__name__)


class SessionController:
    """Orchestrates cashier session lifecycle for the frontend."""

    def __init__(
        self,
        session_service: CashierSessionService,
        business_day_service: BusinessDayService,
        auth_service=None,
    ) -> None:
        self._svc = session_service
        self._day = business_day_service
        self._auth = auth_service

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    def open_session(
        self,
        day_id: int,
        user_id: int,
        station: str,
        opening_float_egp: float,
        actor_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Open a new cashier session.

        Args:
            station: 'ALL' | 'COUNTER' | 'DELIVERY'
            opening_float_egp: amount in EGP (converted to piasters internally)
        Raises ValueError with Arabic message on conflict or invalid input.
        """
        try:
            st = Station(station)
        except ValueError:
            raise ValueError(
                f"محطة غير صحيحة: {station!r}. القيم المسموح بها: ALL, COUNTER, DELIVERY"
            )

        float_pt = round(cash_amount(opening_float_egp) * 100)
        # H05: Only manager can open on behalf of another user
        if self._auth is not None and actor_id is not None:
            actor = self._auth.get_user_by_id(actor_id)
            if actor is not None and not actor.is_manager_or_above() and user_id != actor_id:
                raise ValueError("لا يمكن فتح وردية لكاشير آخر")
        session = self._svc.open_session(
            day_id=day_id,
            user_id=user_id,
            station=st,
            opening_float_pt=float_pt,
            actor_id=actor_id or user_id,
        )
        return self._session_to_dict(session)

    def close_session(
        self,
        session_id: int,
        counted_cash_egp: float,
        actor_id: int,
        variance_reason: str | None = None,
        manager_pin: str | None = None,
    ) -> dict[str, Any]:
        """
        Close a cashier session with a blind cash count.

        Large variances (> EGP 20) require variance_reason + manager PIN.
        """
        # H05: Cashiers may only close their own session
        if self._auth is not None and actor_id is not None:
            actor = self._auth.get_user_by_id(actor_id)
            if actor is not None and not actor.is_manager_or_above():
                session = self._svc.get_session_by_id(session_id)
                if session is not None and session.user_id != actor_id:
                    raise ValueError("لا يمكن إغلاق درج كاشير آخر")

        counted_pt = round(cash_amount(counted_cash_egp) * 100)
        session = self._svc.close_session(
            session_id=session_id,
            counted_cash_pt=counted_pt,
            actor_id=actor_id,
            manager_pin=manager_pin,
            variance_reason=variance_reason,
        )
        return self._session_to_dict(session)

    def do_handover(
        self,
        from_session_id: int,
        to_user_id: int,
        station: str,
        counted_cash_egp: float,
        cash_drop_egp: float = 0.0,
        actor_id: int | None = None,
        variance_reason: str | None = None,
        manager_pin: str | None = None,
    ) -> dict[str, Any]:
        """
        Handover: close outgoing session → open incoming session.

        Returns {'closed': {...}, 'new': {...}}.
        """
        # H05: Cashiers may only handover their own session; recipient cannot be a driver
        if self._auth is not None and actor_id is not None:
            actor = self._auth.get_user_by_id(actor_id)
            if actor is not None and not actor.is_manager_or_above():
                outgoing = self._svc.get_session_by_id(from_session_id)
                if outgoing is not None and outgoing.user_id != actor_id:
                    raise ValueError("لا يمكن تسليم درج كاشير آخر")
            to_user = self._auth.get_user_by_id(to_user_id)
            if to_user is not None and to_user.cashier_slot is None:
                raise ValueError("المستخدم المستلم ليس كاشيراً مسجلاً — لا يمكن نقل الوردية لسائق توصيل")

        try:
            st = Station(station)
        except ValueError:
            raise ValueError(f"محطة غير صحيحة: {station!r}")

        if cash_drop_egp < 0:
            raise ValueError("مبلغ التحويل للخزينة لا يمكن أن يكون سالباً")
        if counted_cash_egp < 0:
            raise ValueError("المبلغ المعدود لا يمكن أن يكون سالباً")
        if cash_drop_egp > counted_cash_egp:
            raise ValueError("مبلغ التحويل للخزينة لا يمكن أن يتجاوز المبلغ المعدود")

        counted_pt = round(cash_amount(counted_cash_egp) * 100)
        drop_pt = round(cash_amount(cash_drop_egp) * 100)

        closed, new_s = self._svc.do_handover(
            from_session_id=from_session_id,
            to_user_id=to_user_id,
            station=st,
            to_user_counted_pt=counted_pt,
            cash_drop_pt=drop_pt,
            actor_id=actor_id,
            variance_reason=variance_reason,
            manager_pin=manager_pin,
        )
        return {
            "closed": self._session_to_dict(closed),
            "new": self._session_to_dict(new_s),
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_sessions(
        self, day_id: int, actor_id: int | None = None
    ) -> list[dict[str, Any]]:
        """All open sessions for a business day (filtered for cashier)."""
        sessions = self._svc.get_active_sessions(day_id)
        if self._auth is not None:
            actor = self._auth.get_user_by_id(actor_id) if actor_id else self._auth.get_current_user()
            if actor is not None and not actor.is_manager_or_above():
                sessions = [s for s in sessions if s.user_id == actor.id]
        return [self._session_to_dict(s) for s in sessions]

    def get_all_sessions(
        self, day_id: int, actor_id: int | None = None
    ) -> list[dict[str, Any]]:
        """All sessions (open + closed) for a business day (filtered for cashier)."""
        sessions = self._svc.get_all_sessions_for_day(day_id)
        if self._auth is not None:
            actor = self._auth.get_user_by_id(actor_id) if actor_id else self._auth.get_current_user()
            if actor is not None and not actor.is_manager_or_above():
                sessions = [s for s in sessions if s.user_id == actor.id]
        return [self._session_to_dict(s) for s in sessions]

    def get_session_balance(
        self, session_id: int, actor_id: int | None = None
    ) -> dict[str, Any]:
        """Current expected cash balance for a session (from ledger)."""
        # H05: Cashiers cannot read another cashier's balance or open session expected cash
        if self._auth is not None:
            actor = self._auth.get_user_by_id(actor_id) if actor_id else self._auth.get_current_user()
            if actor is not None and not actor.is_manager_or_above():
                session = self._svc.get_session_by_id(session_id)
                if session is None or session.user_id != actor.id:
                    raise ValueError("لا يمكن قراءة رصيد درج كاشير آخر")
                if session.is_open:
                    raise ValueError("لا يمكن قراءة الرصيد المتوقع قبل إجراء الجرد")

        balance_pt = self._svc.get_session_expected_cash_pt(session_id)
        session = self._svc.get_session_by_id(session_id)
        return {
            "session_id": session_id,
            "balance_pt": balance_pt,
            "balance_egp": round(balance_pt / 100, 2),
            "is_open": session.is_open if session else None,
        }

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def generate_x_report(
        self, day_id: int, actor_id: int | None = None
    ) -> dict[str, Any]:
        """
        X-Report: live snapshot of all sessions for the business day.
        Can be called any number of times without closing anything.
        Manager only.
        """
        if self._auth is not None:
            actor = self._auth.get_user_by_id(actor_id) if actor_id else self._auth.get_current_user()
            if actor is not None and not actor.is_manager_or_above():
                raise ValueError("تقرير X متاح للمدير فقط")

        report = self._day.generate_x_report(day_id)
        return self._x_report_to_dict(report)

    def close_business_day(
        self,
        day_id: int,
        manager_pin: str | None = None,
        actor_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Close the business day and generate Z-Report.
        Manager only (or with valid manager PIN).
        """
        if self._auth is not None:
            actor = self._auth.get_user_by_id(actor_id) if actor_id else self._auth.get_current_user()
            if actor is not None and not actor.is_manager_or_above() and not manager_pin:
                raise ValueError("إغلاق اليوم متاح للمدير فقط")

        z = self._day.close_business_day(day_id=day_id, manager_pin=manager_pin)
        result = self._x_report_to_dict(z)
        result.update({
            "type": "Z",
            "day_closed_at": z.day_closed_at,
            "total_variance_pt": z.total_variance_pt,
            "total_variance_egp": round(z.total_variance_pt / 100, 2),
        })
        return result

    # ------------------------------------------------------------------
    # Serializers
    # ------------------------------------------------------------------

    def _session_to_dict(self, s: CashierSession) -> dict[str, Any]:
        return {
            "id": s.id,
            "day_id": s.day_id,
            "user_id": s.user_id,
            "station": s.station.value,
            "is_open": s.is_open,
            "opened_at": s.opened_at,
            "closed_at": s.closed_at,
            "opening_float_pt": s.opening_float_pt,
            "opening_float_egp": round(s.opening_float_pt / 100, 2),
            "counted_cash_pt": s.counted_cash_pt,
            "counted_cash_egp": (
                round(s.counted_cash_pt / 100, 2) if s.counted_cash_pt is not None else None
            ),
            "expected_cash_pt": s.expected_cash_pt,
            "expected_cash_egp": (
                round(s.expected_cash_pt / 100, 2) if s.expected_cash_pt is not None else None
            ),
            "variance_pt": s.variance_pt,
            "variance_egp": (
                round(s.variance_pt / 100, 2) if s.variance_pt is not None else None
            ),
        }

    def _snapshot_to_dict(self, snap: SessionSnapshot) -> dict[str, Any]:
        return {
            "session_id": snap.session_id,
            "user_id": snap.user_id,
            "station": snap.station,
            "is_open": snap.is_open,
            "opened_at": snap.opened_at,
            "closed_at": snap.closed_at,
            "opening_float_pt": snap.opening_float_pt,
            "opening_float_egp": round(snap.opening_float_pt / 100, 2),
            "expected_cash_pt": snap.expected_cash_pt,
            "expected_cash_egp": snap.expected_cash_egp,
            "counted_cash_pt": snap.counted_cash_pt,
            "counted_cash_egp": (
                round(snap.counted_cash_pt / 100, 2)
                if snap.counted_cash_pt is not None else None
            ),
            "variance_pt": snap.variance_pt,
            "variance_egp": snap.variance_egp,
            "breakdown": {k: {"pt": v, "egp": round(v / 100, 2)} for k, v in snap.breakdown.items()},
        }

    def _x_report_to_dict(self, report: XReport) -> dict[str, Any]:
        return {
            "type": "X",
            "day_id": report.day_id,
            "generated_at": report.generated_at,
            "sessions": [self._snapshot_to_dict(s) for s in report.sessions],
            "totals": {
                "expected_cash_pt": report.total_expected_cash_pt,
                "expected_cash_egp": round(report.total_expected_cash_pt / 100, 2),
                "cash_sales_pt": report.total_cash_sales_pt,
                "cash_sales_egp": round(report.total_cash_sales_pt / 100, 2),
                "driver_remittance_pt": report.total_driver_remittance_pt,
                "driver_remittance_egp": round(report.total_driver_remittance_pt / 100, 2),
                "expenses_pt": report.total_expenses_pt,
                "expenses_egp": round(report.total_expenses_pt / 100, 2),
            },
        }
