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
from datetime import datetime

from broast_pos.core.models.cashier_session import (
    CashierSession,
    CashLedgerEntry,
    LedgerEntryType,
    Station,
)
from broast_pos.core.policies.input_values import cash_piasters
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)

logger = logging.getLogger(__name__)

# Variance threshold above which a manager PIN is required (piasters).
# 2000 pt = EGP 20.00  — matches FR-SES-6 default.
DEFAULT_VARIANCE_THRESHOLD_PT: int = 2_000


class CashierSessionService:
    """Business logic for opening, closing, and handing over cashier sessions."""

    def __init__(
        self,
        session_repo: CashierSessionRepository | None = None,
        ledger_repo: CashLedgerRepository | None = None,
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
        actor_id: int | None = None,
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

        # Guard (H08/H09): reject opening session on a closed business day
        shift_row = self._sessions._db.fetch_one(
            "SELECT is_active FROM shifts WHERE id = ?", (day_id,)
        )
        if shift_row and not shift_row["is_active"]:
            raise ValueError("لا يمكن فتح وردية في يوم عمل مغلق")

        # FR-SES-2: station conflict check
        self._check_station_conflict(day_id, station)

        now = datetime.now().isoformat()
        session = CashierSession(
            id=None,
            day_id=day_id,
            user_id=user_id,
            station=station,
            is_open=True,
            opened_at=now,
            opening_float_pt=opening_float_pt,
        )

        db = self._sessions._db
        with db.transaction():
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
        manager_pin: str | None = None,
        variance_reason: str | None = None,
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
        counted_cash_pt = cash_piasters(counted_cash_pt)
        session = self._sessions.get_by_id(session_id)
        if session is None:
            raise ValueError(f"الوردية رقم {session_id} غير موجودة")
        if not session.is_open:
            raise ValueError("الوردية مغلقة بالفعل")

        # H05: Only session owner or manager/admin can close a session
        if self._auth is not None and actor_id is not None:
            actor = self._auth.get_user_by_id(actor_id)
            if actor is not None and not actor.is_manager_or_above() and session.user_id != actor_id:
                raise ValueError("لا يمكن إغلاق درج كاشير آخر")

        expected_pt = self._ledger.get_session_balance_pt(session_id)
        variance_pt = counted_cash_pt - expected_pt

        # FR-SES-6: large variance requires manager approval
        if abs(variance_pt) > variance_threshold_pt:
            if not variance_reason:
                raise ValueError(
                    "يلزم إدخال سبب والحصول على موافقة المدير لإتمام الجرد"
                )
            if self._auth is not None:
                self._auth.verify_manager_pin(manager_pin)

        # ADJUSTMENT entry and session close are atomic — roll back both on failure
        manager_id: int | None = None
        if variance_pt != 0:
            if self._auth is not None and manager_pin:
                try:
                    mgr = self._auth.get_manager_by_pin(manager_pin)
                    manager_id = mgr.id if mgr else None
                except Exception:
                    # Checkup-Fix: manager lookup is optional here, but log failures.
                    logger.debug("Manager-by-PIN lookup failed (variance entry)", exc_info=True)

        db = self._sessions._db
        with db.transaction():
            if variance_pt != 0:
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
        actor_id: int | None = None,
        variance_threshold_pt: int = DEFAULT_VARIANCE_THRESHOLD_PT,
        manager_pin: str | None = None,
        variance_reason: str | None = None,
        to_user_counted_pt: int | None = None,
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
        cash_drop_pt = cash_piasters(cash_drop_pt)
        if to_user_counted_pt is not None:
            to_user_counted_pt = cash_piasters(to_user_counted_pt)
        outgoing = self._sessions.get_by_id(from_session_id)
        if outgoing is None:
            raise ValueError(f"وردية التسليم رقم {from_session_id} غير موجودة")
        if not outgoing.is_open:
            raise ValueError("وردية التسليم مغلقة بالفعل")

        # H05: Only session owner or manager/admin can handover a session
        if self._auth is not None and actor_id is not None:
            actor = self._auth.get_user_by_id(actor_id)
            if actor is not None and not actor.is_manager_or_above() and outgoing.user_id != actor_id:
                raise ValueError("لا يمكن تسليم درج كاشير آخر")
            to_user = self._auth.get_user_by_id(to_user_id)
            if to_user is not None and to_user.cashier_slot is None:
                raise ValueError("المستخدم المستلم ليس كاشيراً مسجلاً — لا يمكن نقل الوردية لسائق توصيل")

        if cash_drop_pt < 0:
            raise ValueError("مبلغ التحويل للخزينة لا يمكن أن يكون سالباً")

        expected_pt = self._ledger.get_session_balance_pt(from_session_id)
        # Outgoing cashier counts the drawer (blind)
        # If not provided explicitly, default to the expected (no variance)
        counted_pt = to_user_counted_pt if to_user_counted_pt is not None else expected_pt
        if counted_pt < 0:
            raise ValueError("المبلغ المعدود لا يمكن أن يكون سالباً")

        if cash_drop_pt > counted_pt:
            raise ValueError("مبلغ التحويل للخزينة لا يمكن أن يتجاوز المبلغ المعدود")

        variance_pt = counted_pt - expected_pt

        if abs(variance_pt) > variance_threshold_pt:
            if not variance_reason:
                raise ValueError(
                    "يلزم إدخال سبب والحصول على موافقة المدير لإتمام الجرد"
                )
            if self._auth is not None:
                self._auth.verify_manager_pin(manager_pin)

        manager_id: int | None = None
        if self._auth is not None and manager_pin:
            try:
                mgr = self._auth.get_manager_by_pin(manager_pin)
                manager_id = mgr.id if mgr else None
            except Exception:
                # Checkup-Fix: manager lookup is optional here, but log failures.
                logger.debug("Manager-by-PIN lookup failed (session close)", exc_info=True)

        now = datetime.now().isoformat()
        actor = actor_id or to_user_id
        incoming_float_pt = counted_pt - cash_drop_pt

        # All writes are atomic: if create() or set_handover_link() fail after
        # close_session(), the outgoing session would be permanently closed with
        # no successor.  Roll back everything on any exception.
        db = self._sessions._db
        with db.transaction():
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

            # CASH_DROP: cash transferred to safe if cash_drop_pt > 0
            if cash_drop_pt > 0:
                self._ledger.append(CashLedgerEntry(
                    id=None,
                    day_id=outgoing.day_id,
                    session_id=from_session_id,
                    entry_type=LedgerEntryType.CASH_DROP,
                    amount_pt=-cash_drop_pt,              # negative: cash leaves drawer to safe
                    actor_id=actor,
                    approved_by=manager_id,
                    reason=f"تحويل للخزينة عند التسليم لـ user_id={to_user_id}",
                ))

            # HANDOVER_OUT: remaining counted cash leaves outgoing drawer for next session
            self._ledger.append(CashLedgerEntry(
                id=None,
                day_id=outgoing.day_id,
                session_id=from_session_id,
                entry_type=LedgerEntryType.HANDOVER_OUT,
                amount_pt=-incoming_float_pt,         # negative: cash transferred to new session
                actor_id=actor,
                reason=f"تسليم الوردية لـ user_id={to_user_id}",
            ))

            # Close outgoing session first — the DB trigger blocks a second open
            # session at the same station, so we must close before creating the new one.
            self._sessions.close_session(
                session_id=from_session_id,
                counted_cash_pt=counted_pt,
                expected_cash_pt=expected_pt,
                variance_pt=variance_pt,
                variance_approved_by=manager_id,
                variance_reason=variance_reason,
            )

            # Create new session (old session is now closed, so the station is free).
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

            # Link outgoing → incoming now that created.id is known.
            # Uses a separate UPDATE without the is_open guard (session is closed).
            self._sessions.set_handover_link(from_session_id, created.id)

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

    def get_all_sessions_for_day(self, day_id: int) -> list[CashierSession]:
        """All sessions (open and closed) for a business day."""
        return self._sessions.get_sessions_for_day(day_id)

    def get_session_expected_cash_pt(self, session_id: int) -> int:
        """Current expected drawer balance (piasters) — ADR-1 formula."""
        return self._ledger.get_session_balance_pt(session_id)

    def get_session_by_id(self, session_id: int) -> CashierSession | None:
        return self._sessions.get_by_id(session_id)

    def has_open_sessions(self, day_id: int) -> bool:
        return self._sessions.has_any_open_session(day_id)

    def get_open_session_for_station(
        self, day_id: int, station: Station
    ) -> CashierSession | None:
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
