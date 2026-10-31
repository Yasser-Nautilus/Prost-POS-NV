"""
BusinessDayService — v2 business day lifecycle management.

Wraps FinancialService.close_shift() with v2-specific pre-checks and
end-of-day ledger operations.

New responsibilities vs. the old FinancialService.close_shift():
  FR-DAY-1  Verify all cashier sessions are closed before day close.
  FR-DAY-2  Batch DRIVER_FEE_PAYOUT entries at day close (Q3 = end-of-day).
  FR-DAY-3  Generate Z-Report (final ledger snapshot) at close.
  FR-DAY-4  Set shifts.business_date = DATE(opened_at, 'localtime') on open.

X-Report:  Live ledger snapshot without closing (can be run any time).
Z-Report:  Final snapshot triggered at close; includes all sessions + variances.

Architecture note (ADR-1): all cash numbers come from
CashLedgerRepository.get_session_balance_pt() — never from orders table directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict

from broast_pos.core.models.cashier_session import (
    CashierSession, CashLedgerEntry, LedgerEntryType, Station,
)
from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report models
# ---------------------------------------------------------------------------

@dataclass
class SessionSnapshot:
    """Ledger snapshot for a single cashier session — used in X and Z reports."""
    session_id: int
    user_id: int
    station: str                 # Station.value string
    is_open: bool
    opened_at: str
    closed_at: Optional[str]

    opening_float_pt: int        # from cashier_sessions.opening_float_pt
    expected_cash_pt: int        # SUM(cash_ledger.amount_pt) — ADR-1
    counted_cash_pt: Optional[int]  # blind count (None if session still open)
    variance_pt: Optional[int]      # counted - expected (None if open)

    breakdown: Dict[str, int]    # {entry_type: SUM(amount_pt)}

    @property
    def expected_cash_egp(self) -> float:
        return self.expected_cash_pt / 100

    @property
    def variance_egp(self) -> Optional[float]:
        return self.variance_pt / 100 if self.variance_pt is not None else None


@dataclass
class XReport:
    """
    Mid-day snapshot — live ledger balances without closing anything.
    Can be printed any number of times (each print gets current state).
    """
    day_id: int
    generated_at: str
    sessions: List[SessionSnapshot]

    @property
    def total_expected_cash_pt(self) -> int:
        return sum(s.expected_cash_pt for s in self.sessions)

    @property
    def total_cash_sales_pt(self) -> int:
        return sum(s.breakdown.get("SALE_CASH", 0) for s in self.sessions)

    @property
    def total_driver_remittance_pt(self) -> int:
        return sum(s.breakdown.get("DRIVER_REMITTANCE", 0) for s in self.sessions)

    @property
    def total_expenses_pt(self) -> int:
        """Total outflows (EXPENSE entries) — negative amounts, return abs value."""
        return abs(sum(s.breakdown.get("EXPENSE", 0) for s in self.sessions))


@dataclass
class ZReport(XReport):
    """
    End-of-day report — generated at business day close.
    Extends XReport with close-specific fields.
    """
    day_closed_at: str
    total_variance_pt: int       # sum of all session variances

    @property
    def total_variance_egp(self) -> float:
        return self.total_variance_pt / 100


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class BusinessDayService:
    """
    v2 Business Day lifecycle — open, close, X-report, Z-report.

    This service adds the v2 session-layer checks ON TOP of the existing
    FinancialService.close_shift().  The FinancialService guards
    (no drivers in transit, no open orders, etc.) still run first.
    """

    def __init__(
        self,
        financial_service=None,      # FinancialService
        session_repo: Optional[CashierSessionRepository] = None,
        ledger_repo: Optional[CashLedgerRepository] = None,
        auth_service=None,
    ) -> None:
        self._financial = financial_service
        self._sessions = session_repo or CashierSessionRepository()
        self._ledger = ledger_repo or CashLedgerRepository()
        self._auth = auth_service

    # ------------------------------------------------------------------
    # FR-DAY-3: X-Report (live snapshot, no close)
    # ------------------------------------------------------------------

    def generate_x_report(self, day_id: int) -> XReport:
        """
        Generate a live X-Report for the business day.

        Fetches ALL sessions (open and closed) for this day_id,
        computes expected_cash from the ledger, and returns a snapshot.
        """
        sessions = self._sessions.get_sessions_for_day(day_id)
        snapshots = [self._build_session_snapshot(s) for s in sessions]

        return XReport(
            day_id=day_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            sessions=snapshots,
        )

    # ------------------------------------------------------------------
    # FR-DAY-1 + FR-DAY-2 + FR-DAY-3: Close business day
    # ------------------------------------------------------------------

    def close_business_day(
        self,
        day_id: int,
        manager_pin: Optional[str] = None,
    ) -> ZReport:
        """
        Close the business day with v2 pre-checks, DRIVER_FEE_PAYOUT batch,
        and Z-Report generation.

        v2 pre-checks (run BEFORE FinancialService.close_shift):
          1. FR-DAY-1: All cashier sessions must be closed.
          2. (Financial service guards run inside close_shift)

        v2 close operations (run AFTER session check, BEFORE shift close):
          3. FR-DAY-2: Batch DRIVER_FEE_PAYOUT entries for each settled trip.

        Returns the Z-Report.
        Raises ValueError with Arabic message if any pre-check fails.
        """
        # FR-DAY-1: All sessions must be closed
        self._guard_all_sessions_closed(day_id)

        # FR-DAY-2: Batch DRIVER_FEE_PAYOUT before closing shift
        self._batch_driver_fee_payouts(day_id)

        # Close the shift via FinancialService (handles its own pre-checks)
        if self._financial is not None:
            closed_shift = self._financial.close_shift(
                shift_id=day_id,
                manager_pin=manager_pin,
            )
            closed_at = closed_shift.closed_at or datetime.now(timezone.utc).isoformat()
        else:
            closed_at = datetime.now(timezone.utc).isoformat()

        # FR-DAY-3: Build Z-Report from final ledger state
        sessions = self._sessions.get_sessions_for_day(day_id)
        snapshots = [self._build_session_snapshot(s) for s in sessions]

        total_variance = sum(
            (s.variance_pt or 0) for s in snapshots
        )

        z_report = ZReport(
            day_id=day_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            sessions=snapshots,
            day_closed_at=closed_at,
            total_variance_pt=total_variance,
        )

        logger.info(
            "Business day %d closed — sessions=%d total_expected=%.2f EGP variance=%.2f EGP",
            day_id, len(snapshots),
            z_report.total_expected_cash_pt / 100,
            z_report.total_variance_egp,
        )
        return z_report

    # ------------------------------------------------------------------
    # Pre-check helpers
    # ------------------------------------------------------------------

    def _guard_all_sessions_closed(self, day_id: int) -> None:
        """
        FR-DAY-1: Raise if any cashier session is still open.
        The session IDs are listed in the error message so the manager knows
        which cashier to close first.
        """
        open_sessions = self._sessions.get_open_sessions_for_day(day_id)
        if open_sessions:
            names = ", ".join(
                f"{s.station.value}#{s.id}" for s in open_sessions
            )
            raise ValueError(
                f"لا يمكن إغلاق اليوم بينما توجد وردية مفتوحة: {names}. "
                "أغلق جميع الورديات أولاً."
            )

    # ------------------------------------------------------------------
    # FR-DAY-2: DRIVER_FEE_PAYOUT batch at day close
    # ------------------------------------------------------------------

    def _batch_driver_fee_payouts(self, day_id: int) -> int:
        """
        Create DRIVER_FEE_PAYOUT ledger entries for all settled trips on this day.

        Strategy (Q3 confirmed = end-of-day batch):
          - Query all settled delivery_trips for this day_id's orders.
          - For each trip, the fee owed to the driver = total_delivery_fees.
          - Insert a DRIVER_FEE_PAYOUT entry (negative: cash leaves drawer)
            into the DELIVERY or ALL session for this day.
          - Skip if session not found (legacy mode).
          - Idempotency: no unique index for DRIVER_FEE_PAYOUT (unlike SALE_CASH),
            so we track which trips have already been paid via a simple query.

        Returns the number of entries created.
        """
        # Find DELIVERY or ALL session for this day
        all_sessions = self._sessions.get_open_sessions_for_day(day_id)
        if not all_sessions:
            # All closed — use the last closed DELIVERY or ALL session
            all_sessions_all = self._sessions.get_sessions_for_day(day_id)
            delivery_session = next(
                (s for s in reversed(all_sessions_all)
                 if s.station in (Station.DELIVERY, Station.ALL)), None
            )
        else:
            delivery_session = next(
                (s for s in all_sessions if s.station == Station.DELIVERY), None
            ) or next(
                (s for s in all_sessions if s.station == Station.ALL), None
            )

        if delivery_session is None:
            logger.warning(
                "DRIVER_FEE_PAYOUT batch skipped — no DELIVERY/ALL session for day %d", day_id
            )
            return 0

        # Load settled trip fees for this day via direct SQL query
        # (avoids importing DeliveryRepository to keep dependency light)
        db = self._sessions._db
        rows = db.fetch_all(
            """SELECT dt.id AS trip_id, dt.total_delivery_fees
               FROM delivery_trips dt
               JOIN delivery_trip_orders dto ON dto.trip_id = dt.id
               JOIN orders o ON o.id = dto.order_id
               WHERE dt.is_settled = 1
                 AND o.shift_id = ?
               GROUP BY dt.id
               HAVING dt.total_delivery_fees > 0""",
            (day_id,),
        )

        count = 0
        now = datetime.now(timezone.utc).isoformat()

        # Resolve a real actor_id for the ledger FK (actor_id cannot be 0 or NULL).
        # Use whoever opened the shift (shifts.opened_by).
        shift_row = db.fetch_one("SELECT opened_by FROM shifts WHERE id = ?", (day_id,))
        system_actor_id: int = (
            shift_row["opened_by"] if shift_row
            else delivery_session.user_id
        )

        for row in rows:
            trip_id = row["trip_id"]
            fee_egp = row["total_delivery_fees"]
            fee_pt = round(fee_egp * 100)

            # Idempotency: skip if already payed out this trip
            existing = db.fetch_one(
                "SELECT 1 FROM cash_ledger WHERE trip_id = ? AND entry_type = 'DRIVER_FEE_PAYOUT'",
                (trip_id,),
            )
            if existing:
                continue

            self._ledger.append(CashLedgerEntry(
                id=None,
                day_id=day_id,
                session_id=delivery_session.id,
                entry_type=LedgerEntryType.DRIVER_FEE_PAYOUT,
                amount_pt=-fee_pt,          # negative: cash leaves the drawer to driver
                trip_id=trip_id,
                actor_id=system_actor_id,  # shift opener (FK-safe)
                reason="دفع أجرة السائق عند إغلاق اليوم",
                created_at=now,
            ))
            count += 1

        if count:
            logger.info("DRIVER_FEE_PAYOUT batch: %d entries for day %d", count, day_id)
        return count

    # ------------------------------------------------------------------
    # Session snapshot builder (shared by X and Z report)
    # ------------------------------------------------------------------

    def _build_session_snapshot(self, session: CashierSession) -> SessionSnapshot:
        """Build a SessionSnapshot from a session + its ledger entries."""
        expected_pt = self._ledger.get_session_balance_pt(session.id)
        breakdown = self._ledger.get_session_balance_by_type(session.id)

        return SessionSnapshot(
            session_id=session.id,
            user_id=session.user_id,
            station=session.station.value,
            is_open=session.is_open,
            opened_at=session.opened_at or "",
            closed_at=session.closed_at,
            opening_float_pt=session.opening_float_pt,
            expected_cash_pt=expected_pt,
            counted_cash_pt=session.counted_cash_pt,
            variance_pt=session.variance_pt,
            breakdown=breakdown,
        )
