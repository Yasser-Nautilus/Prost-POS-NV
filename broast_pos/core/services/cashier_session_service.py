"""
CashierSessionService — business logic for cashier sessions (shifts at a station).

Terminology (from PRD §3):
  - Business Day  = the `shifts` table row (what the code calls BusinessDay / Shift)
  - Cashier Session = a cashier's open period at a station within a Business Day
  - Station       = ALL / COUNTER / DELIVERY

Key rules enforced here (ADR-4: service layer is authoritative):
  FR-SES-1  Open session: user + station + opening_float
  FR-SES-2  Station conflict: ALL conflicts with COUNTER/DELIVERY (and v.v.)
  FR-SES-6  Handover: blind count → variance → outgoing HANDOVER_OUT + incoming HANDOVER_IN
  FR-SES-7  Opening amount for new session = counted − cash_drop
  FR-SES-8  Open orders/tables stay visible; payment attributed to receiver's session

Cash ledger entries created here (ADR-1):
  OPENING_FLOAT  → when a session opens (first session of day or after cash_drop)
  HANDOVER_IN    → when a session receives the counted cash from previous session
  HANDOVER_OUT   → when a session hands its counted cash to the next session
  ADJUSTMENT     → when variance > 0 at close (signed: + or −)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from broast_pos.core.models.cashier_session import (
    CashierSession,
    CashLedgerEntry,
    LedgerEntryType,
    Station,
)
from broast_pos.data.repositories.cashier_session_repository import CashierSessionRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository

logger = logging.getLogger(__name__)

# Variance threshold above which a manager PIN is required (piasters).
# 2000 pt = EGP 20.00  — matches FR-SES-6 default.
DEFAULT_VARIANCE_THRESHOLD_PT: int = 2_000


class CashierSessionService:
    """Business logic for opening, closing, and handing over cashier sessions."""

    def __init__(
        self,
        session_repo: Optional[CashierSessionRepository] = None,
        ledger_repo: Optional[CashLedgerRepository] = None,
        auth_service=None,
    ) -> None:
        self._sessions = session_repo or CashierSessionRepository()
        self._ledger = ledger_repo or CashLedgerRepository()
        self._auth = auth_service  # injected to verify manager PIN for variance

    # ------------------------------------------------------------------
    # FR-SES-1: Open session
    # ------------------------------------------------------------------

    def open_session(
        self,
        day_id: int,
        user_id: int,
        station: Station,
        opening_float_pt: int,
        actor_id: Optional[int] = None,
    ) -> CashierSession:
        """
        Open a new cashier session at a station.

        Rules:
          - opening_float_pt must be ≥ 0
          - station conflict (FR-SES-2) is checked in Python first for a clear
            Arabic message; the DB trigger is the second line of defence.
          - Creates an OPENING_FLOAT ledger entry in the same logical step.

        Returns the created session (with id set).
        Raises ValueError with Arabic message on any rule violation.
        """
        if opening_float_pt < 0:
            raise ValueError("مبلغ الفتح لا يمكن أن يكون سالباً")

        # FR-SES-2: station conflict check
        self._check_station_conflict(day_id, station)

        now = datetime.now(timezone.utc).isoformat()
        session = CashierSession(
            id=None,
            day_id=day_id,
            user_id=user_id,
            station=station,
            is_open=True,
            opened_at=now,
            opening_float_pt=opening_float_pt,
        )

        created = self._sessions.create(session)

        # OPENING_FLOAT ledger entry — cash enters the drawer
        if opening_float_pt > 0:
            self._ledger.append(CashLedgerEntry(
                id=None,
                day_id=day_id,
                session_id=created.id,
                entry_type=LedgerEntryType.OPENING_FLOAT,
                amount_pt=opening_float_pt,
                actor_id=actor_id or user_id,
                reason="فتح الوردية",
            ))

        logger.info(
            "Session %d opened — day=%d user=%d station=%s float=%.2f EGP",
            created.id, day_id, user_id, station.value, opening_float_pt / 100,
        )
        return created

    # ------------------------------------------------------------------
    # FR-SES-6: Close session (blind count → variance)
    # ------------------------------------------------------------------

    def close_session(
        self,
        session_id: int,
        counted_cash_pt: int,
        actor_id: int,
        variance_threshold_pt: int = DEFAULT_VARIANCE_THRESHOLD_PT,
        manager_pin: Optional[str] = None,
        variance_reason: Optional[str] = None,
    ) -> CashierSession:
        """
        Close a cashier session.

        Flow:
          1. Fetch session + compute expected_cash from ledger.
          2. Compute variance = counted − expected.
          3. If |variance| > threshold → require manager PIN + reason.
          4. Create ADJUSTMENT ledger entry if variance != 0.
          5. Mark session closed (snapshot expected_cash_pt, variance_pt).

        Returns the updated session.
        Raises ValueError with Arabic message if session not found, already
        closed, or variance requires manager approval that wasn't provided.
        """
        session = self._sessions.get_by_id(session_id)
        if session is None:
            raise ValueError(f"الوردية رقم {session_id} غير موجودة")
        if not session.is_open:
            raise ValueError("الوردية مغلقة بالفعل")

        expected_pt = self._ledger.get_session_balance_pt(session_id)
        variance_pt = counted_cash_pt - expected_pt

        # FR-SES-6: large variance requires manager approval
        if abs(variance_pt) > variance_threshold_pt:
            if not variance_reason:
                raise ValueError(
                    f"الفرق {variance_pt / 100:+.2f} ج.م يتجاوز الحد المسموح "
                    f"({variance_threshold_pt / 100:.2f} ج.م). يجب إدخال سبب والحصول على موافقة المدير"
                )
            if self._auth is not None:
                self._auth.verify_manager_pin(manager_pin)

        # ADJUSTMENT entry if there is a variance
        manager_id: Optional[int] = None
        if variance_pt != 0:
            if self._auth is not None and manager_pin:
                try:
                    mgr = self._auth.get_manager_by_pin(manager_pin)
                    manager_id = mgr.id if mgr else None
                except Exception:
                    pass

            self._ledger.append(CashLedgerEntry(
                id=None,
                day_id=session.day_id,
                session_id=session_id,
                entry_type=LedgerEntryType.ADJUSTMENT,
                amount_pt=variance_pt,          # signed: + shortage counted more, − counted less
                actor_id=actor_id,
                approved_by=manager_id,
                reason=variance_reason or ("عجز" if variance_pt < 0 else "زيادة"),
            ))

        self._sessions.close_session(
            session_id=session_id,
            counted_cash_pt=counted_cash_pt,
            expected_cash_pt=expected_pt,
            variance_pt=variance_pt,
            variance_approved_by=manager_id,
            variance_reason=variance_reason,
        )

        closed = self._sessions.get_by_id(session_id)
        logger.info(
            "Session %d closed — expected=%.2f counted=%.2f variance=%.2f EGP",
            session_id, expected_pt / 100, counted_cash_pt / 100, variance_pt / 100,
        )
        return closed

    # ------------------------------------------------------------------
    # FR-SES-6 + FR-SES-7: Handover
    # ------------------------------------------------------------------

    def do_handover(
        self,
        from_session_id: int,
        to_user_id: int,
        station: Station,
        cash_drop_pt: int = 0,
        actor_id: Optional[int] = None,
        variance_threshold_pt: int = DEFAULT_VARIANCE_THRESHOLD_PT,
        manager_pin: Optional[str] = None,
        variance_reason: Optional[str] = None,
        to_user_counted_pt: Optional[int] = None,
    ) -> tuple[CashierSession, CashierSession]:
        """
        Full handover: close outgoing session → open incoming session.

        Flow:
          1. Compute expected_cash from ledger for outgoing session.
          2. Close outgoing session (HANDOVER_OUT entry = counted amount).
          3. Opening amount for new session = counted − cash_drop (FR-SES-7).
          4. Open new session at same station (HANDOVER_IN entry).
          5. Link the two sessions via handover_to_session FK.

        Returns (closed_session, new_session).

        Note: open tables and trips carry over automatically because they are
        linked to the shift (day_id), not the session. Payment attribution
        (FR-SES-8) is handled at payment time by the OrderService.
        """
        outgoing = self._sessions.get_by_id(from_session_id)
        if outgoing is None:
            raise ValueError(f"وردية التسليم رقم {from_session_id} غير موجودة")
        if not outgoing.is_open:
            raise ValueError("وردية التسليم مغلقة بالفعل")

        if cash_drop_pt < 0:
            raise ValueError("مبلغ التحويل للخزينة لا يمكن أن يكون سالباً")

        expected_pt = self._ledger.get_session_balance_pt(from_session_id)
        # Outgoing cashier counts the drawer (blind)
        # If not provided explicitly, default to the expected (no variance)
        counted_pt = to_user_counted_pt if to_user_counted_pt is not None else expected_pt
        variance_pt = counted_pt - expected_pt

        if abs(variance_pt) > variance_threshold_pt:
            if not variance_reason:
                raise ValueError(
                    f"الفرق {variance_pt / 100:+.2f} ج.م يتجاوز الحد. يجب إدخال سبب وموافقة المدير"
                )
            if self._auth is not None:
                self._auth.verify_manager_pin(manager_pin)

        manager_id: Optional[int] = None
        if self._auth is not None and manager_pin:
            try:
                mgr = self._auth.get_manager_by_pin(manager_pin)
                manager_id = mgr.id if mgr else None
            except Exception:
                pass

        now = datetime.now(timezone.utc).isoformat()
        actor = actor_id or to_user_id

        # ADJUSTMENT if variance != 0
        if variance_pt != 0:
            self._ledger.append(CashLedgerEntry(
                id=None,
                day_id=outgoing.day_id,
                session_id=from_session_id,
                entry_type=LedgerEntryType.ADJUSTMENT,
                amount_pt=variance_pt,
                actor_id=actor,
                approved_by=manager_id,
                reason=variance_reason or ("عجز في التسليم" if variance_pt < 0 else "زيادة في التسليم"),
            ))

        # HANDOVER_OUT: counted cash leaves the outgoing drawer
        self._ledger.append(CashLedgerEntry(
            id=None,
            day_id=outgoing.day_id,
            session_id=from_session_id,
            entry_type=LedgerEntryType.HANDOVER_OUT,
            amount_pt=-counted_pt,              # negative: cash leaves drawer
            actor_id=actor,
            reason=f"تسليم الوردية لـ user_id={to_user_id}",
        ))

        # Close outgoing session
        self._sessions.close_session(
            session_id=from_session_id,
            counted_cash_pt=counted_pt,
            expected_cash_pt=expected_pt,
            variance_pt=variance_pt,
            variance_approved_by=manager_id,
            variance_reason=variance_reason,
        )

        # FR-SES-7: opening amount = counted − cash_drop
        incoming_float_pt = max(0, counted_pt - cash_drop_pt)

        # Create new session
        new_session = CashierSession(
            id=None,
            day_id=outgoing.day_id,
            user_id=to_user_id,
            station=station,
            is_open=True,
            opened_at=now,
            opening_float_pt=incoming_float_pt,
        )
        created = self._sessions.create(new_session)

        # Link from_session → new_session
        self._sessions.close_session(
            session_id=from_session_id,
            counted_cash_pt=counted_pt,
            expected_cash_pt=expected_pt,
            variance_pt=variance_pt,
            variance_approved_by=manager_id,
            variance_reason=variance_reason,
            handover_to_session=created.id,
        )

        # HANDOVER_IN: counted cash enters the incoming drawer
        self._ledger.append(CashLedgerEntry(
            id=None,
            day_id=outgoing.day_id,
            session_id=created.id,
            entry_type=LedgerEntryType.HANDOVER_IN,
            amount_pt=incoming_float_pt,        # positive: cash enters drawer
            actor_id=actor,
            reason=f"استلام الوردية من session_id={from_session_id}",
        ))

        closed = self._sessions.get_by_id(from_session_id)
        logger.info(
            "Handover complete — from session %d → new session %d (%.2f EGP transferred)",
            from_session_id, created.id, incoming_float_pt / 100,
        )
        return closed, created

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_active_sessions(self, day_id: int) -> list[CashierSession]:
        """All currently open sessions for a business day."""
        return self._sessions.get_open_sessions_for_day(day_id)

    def get_session_expected_cash_pt(self, session_id: int) -> int:
        """Current expected drawer balance (piasters) — ADR-1 formula."""
        return self._ledger.get_session_balance_pt(session_id)

    def get_session_by_id(self, session_id: int) -> Optional[CashierSession]:
        return self._sessions.get_by_id(session_id)

    def has_open_sessions(self, day_id: int) -> bool:
        return self._sessions.has_any_open_session(day_id)

    def get_open_session_for_station(
        self, day_id: int, station: Station
    ) -> Optional[CashierSession]:
        return self._sessions.get_open_session_for_station(day_id, station)

    # ------------------------------------------------------------------
    # Station conflict guard (FR-SES-2)
    # ------------------------------------------------------------------

    def _check_station_conflict(self, day_id: int, new_station: Station) -> None:
        """
        Raise ValueError with Arabic message if the new station conflicts
        with an existing open session on the same day.

        Rules:
          - ALL conflicts with COUNTER and DELIVERY (and vice-versa)
          - COUNTER and DELIVERY do NOT conflict with each other
          - Only one open session per station per day
        """
        open_sessions = self._sessions.get_open_sessions_for_day(day_id)
        for s in open_sessions:
            if s.station == new_station:
                raise ValueError(
                    f"يوجد بالفعل وردية مفتوحة على محطة {new_station.value}. "
                    "أغلق الوردية الحالية أو انتقل إلى محطة أخرى."
                )
            if new_station == Station.ALL or s.station == Station.ALL:
                raise ValueError(
                    "لا يمكن فتح وردية 'كل الطلبات' بينما توجد وردية تخصص مفتوحة، "
                    "ولا يمكن فتح وردية تخصص بينما وردية 'كل الطلبات' مفتوحة. "
                    "أغلق الوردية الحالية أولاً."
                )
