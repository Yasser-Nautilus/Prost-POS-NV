"""
Driver settlement service — atomic, transaction-safe end-of-day settlement.

This service is responsible for:
  - Calculating the financial summary for a driver on a given date.
  - Validating that all selected trips are eligible for settlement.
  - Atomically creating the settlement record and marking trips settled.
  - Logging the audit event.

Rule: NEVER trust the frontend to provide financial totals.
All numbers are calculated server-side from actual order records.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional, TYPE_CHECKING

from broast_pos.core.models.audit import AuditEventType
from broast_pos.core.models.driver_settlement import DriverSettlement
from broast_pos.core.models.order import OrderStatus, PaymentMethod
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.driver_settlement_repository import DriverSettlementRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.user_repository import UserRepository

if TYPE_CHECKING:
    from broast_pos.core.services.order_service import OrderService

logger = logging.getLogger(__name__)


class DriverSettlementService:
    """End-of-day driver settlement — atomic and financially authoritative."""

    def __init__(
        self,
        settlement_repo: Optional[DriverSettlementRepository] = None,
        delivery_repo: Optional[DeliveryRepository] = None,
        order_repo: Optional[OrderRepository] = None,
        user_repo: Optional[UserRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        order_svc: Optional["OrderService"] = None,
        ledger_repo=None,           # CashLedgerRepository (Phase 3)
        cashier_session_repo=None,  # CashierSessionRepository (Phase 3)
    ) -> None:
        self._settlements = settlement_repo or DriverSettlementRepository()
        self._delivery = delivery_repo or DeliveryRepository()
        self._orders = order_repo or OrderRepository()
        self._users = user_repo or UserRepository()
        self._audit = audit_repo or AuditRepository()
        # B-07: injected so settle_driver can complete orders after settlement
        self._order_svc = order_svc
        # Phase 3: cash ledger wiring (optional)
        self._ledger = ledger_repo
        self._cashier_sessions = cashier_session_repo

    # ------------------------------------------------------------------
    # Preview — read-only calculation, no DB writes
    # ------------------------------------------------------------------

    def get_driver_settlement_preview(
        self,
        driver_id: int,
        settlement_date: Optional[str] = None,
    ) -> Dict:
        """Calculate what a settlement would look like, without committing.

        Returns a summary dict the frontend can display for manager review.
        If settlement_date is None, uses today.

        Returns:
            Dict with driver info, trip/order counts, and financial breakdown.
        Raises:
            ValueError: if driver not found or no eligible trips exist.
        """
        target_date = settlement_date or date.today().isoformat()

        driver = self._users.get_by_id(driver_id)
        if driver is None:
            raise ValueError(f"السائق #{driver_id} غير موجود")

        trips = self._delivery.get_driver_trips_for_date(driver_id, target_date)
        eligible_trips = [
            t for t in trips
            if t.returned_at is not None and not t.is_settled
        ]

        if not eligible_trips:
            raise ValueError(
                f"لا توجد رحلات مؤهلة للتسوية ليوم {target_date}"
            )

        return self._calculate_summary(
            driver_id=driver_id,
            driver_name=driver.display_name or driver.username,
            settlement_date=target_date,
            eligible_trips=eligible_trips,
        )

    # ------------------------------------------------------------------
    # Settle — atomic: validate → calculate → commit
    # ------------------------------------------------------------------

    def settle_driver(
        self,
        driver_id: int,
        settled_by_id: int,
        settled_by_name: str,
        settlement_date: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> DriverSettlement:
        """Atomically settle all eligible trips for a driver on a date.

        Steps (all in one transaction):
          1. Validate driver exists.
          2. Load all returned, unsettled trips for the date.
          3. Validate there is at least one eligible trip.
          4. Calculate financial totals from actual order records.
          5. BEGIN TRANSACTION
          6. Create driver_settlements record.
          7. Mark all eligible trips as settled.
          8. Log audit event.
          9. COMMIT (or ROLLBACK on error).

        Args:
            driver_id: The driver being settled.
            settled_by_id: Manager/cashier performing the settlement.
            settled_by_name: Manager/cashier display name (for the record).
            settlement_date: YYYY-MM-DD; defaults to today.
            notes: Optional notes from the manager.

        Returns:
            The saved DriverSettlement record.

        Raises:
            ValueError: if driver not found, no eligible trips, or
                        trips not eligible (not returned, already settled).
        """
        target_date = settlement_date or date.today().isoformat()

        # ── Step 1: Validate driver ───────────────────────────────────────
        driver = self._users.get_by_id(driver_id)
        if driver is None:
            raise ValueError(f"السائق #{driver_id} غير موجود")

        driver_name = driver.display_name or driver.username

        # ── Step 2: Load eligible trips ───────────────────────────────────
        trips = self._delivery.get_driver_trips_for_date(driver_id, target_date)
        eligible_trips = [
            t for t in trips
            if t.returned_at is not None and not t.is_settled
        ]

        # ── Step 3: Must have at least one eligible trip ──────────────────
        if not eligible_trips:
            raise ValueError(
                f"لا توجد رحلات مؤهلة للتسوية — السائق {driver_name} ليوم {target_date}"
            )

        # ── Step 4: Calculate financials server-side ──────────────────────
        summary = self._calculate_summary(
            driver_id=driver_id,
            driver_name=driver_name,
            settlement_date=target_date,
            eligible_trips=eligible_trips,
        )

        # Build settlement object
        settlement = DriverSettlement(
            driver_id=driver_id,
            driver_name=driver_name,
            settlement_date=target_date,
            trip_count=summary["trip_count"],
            order_count=summary["order_count"],
            total_order_value=summary["total_order_value"],
            cash_collected=summary["cash_collected"],
            online_paid=summary["online_paid"],
            total_delivery_fees=summary["total_delivery_fees"],
            settled_by_id=settled_by_id,
            settled_by_name=settled_by_name,
            notes=notes,
        )

        # ── Steps 5-9: Atomic transaction (B-06/B-07: use db.transaction()) ──
        db = self._delivery._db
        try:
            with db.transaction():
                # 6. Create settlement record
                self._settlements.create_settlement(settlement)

                # 7. Mark all eligible trips as settled + complete their orders
                for trip in eligible_trips:
                    trip_cash = 0.0
                    trip_fees = 0.0
                    for oid in trip.order_ids:
                        order = self._orders.get_by_id(oid)
                        if order:
                            if order.payment_method == PaymentMethod.CASH:
                                trip_cash += order.total
                            trip_fees += order.delivery_fee or 0.0

                    db.execute(
                        """UPDATE delivery_trips
                           SET is_settled = 1, settled_at = datetime('now'),
                               cash_collected = ?, total_delivery_fees = ?
                           WHERE id = ?""",
                        (trip_cash, trip_fees, trip.id),
                    )

                    # Phase 3: DRIVER_REMITTANCE ledger entry (ADR-1)
                    # day_id = shift_id from the trip's first order (the business day)
                    if self._ledger is not None and trip_cash > 0:
                        _trip_day_id: Optional[int] = None
                        for _oid in trip.order_ids:
                            _o = self._orders.get_by_id(_oid)
                            if _o and _o.shift_id:
                                _trip_day_id = _o.shift_id
                                break
                        if _trip_day_id is not None:
                            self._create_driver_remittance_entry(
                                trip_id=trip.id,
                                day_id=_trip_day_id,
                                trip_cash=trip_cash,
                                actor_id=settled_by_id,
                            )

                    # B-07: complete orders still in DELIVERED status
                    if self._order_svc is not None:
                        for oid in trip.order_ids:
                            order = self._orders.get_by_id(oid)
                            if order and order.status == OrderStatus.DELIVERED:
                                try:
                                    self._order_svc.change_order_status(
                                        order_id=oid,
                                        new_status=OrderStatus.COMPLETED,
                                        changed_by_id=settled_by_id,
                                        changed_by_name=settled_by_name,
                                    )
                                except Exception as exc:
                                    logger.warning(
                                        "Could not complete order #%d during settlement: %s",
                                        oid, exc,
                                    )

                # 8. Audit event (inside transaction — all-or-nothing)
                db.execute(
                    """INSERT INTO audit_log
                           (event_type, user_id, user_name, details,
                            entity_type, entity_id, after_data)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        AuditEventType.DRIVER_SETTLEMENT_COMPLETED,
                        settled_by_id,
                        settled_by_name,
                        f'{{"driver_id": {driver_id}, "driver_name": "{driver_name}", '
                        f'"date": "{target_date}", '
                        f'"trip_count": {summary["trip_count"]}, '
                        f'"order_count": {summary["order_count"]}, '
                        f'"cash_collected": {summary["cash_collected"]}, '
                        f'"online_paid": {summary["online_paid"]}, '
                        f'"delivery_fees": {summary["total_delivery_fees"]}}}',
                        "driver",
                        driver_id,
                        f'{{"settlement_id": {settlement.id}}}',
                    ),
                )
                # db.transaction() commits on clean exit — no explicit commit needed

        except Exception as exc:
            logger.exception("Driver settlement failed for driver %d — rolled back", driver_id)
            raise ValueError(f"فشل في تسجيل التسوية: {exc}") from exc

        return settlement

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_settlements_for_driver(self, driver_id: int) -> List[DriverSettlement]:
        """All settlement records for a driver (newest first)."""
        return self._settlements.get_by_driver(driver_id)

    def get_settlements_for_date(self, date_str: str) -> List[DriverSettlement]:
        """All settlement records for a specific date."""
        return self._settlements.get_for_date(date_str)

    def get_settlement_by_driver_date(
        self, driver_id: int, date_str: str
    ) -> Optional[DriverSettlement]:
        """Find a specific settlement record."""
        return self._settlements.get_by_driver_date(driver_id, date_str)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _calculate_summary(
        self,
        driver_id: int,
        driver_name: str,
        settlement_date: str,
        eligible_trips,
    ) -> Dict:
        """Calculate financial summary from actual order data.

        This is the authoritative financial calculation — NEVER trust
        snapshots from delivery_trips.cash_collected for a new settlement
        (those are set after settlement, not before).
        """
        total_order_value = 0.0
        cash_collected = 0.0
        online_paid = 0.0
        total_delivery_fees = 0.0
        order_count = 0

        per_trip_details = []

        for trip in eligible_trips:
            trip_orders = []
            trip_cash = 0.0
            trip_online = 0.0
            trip_fees = 0.0

            for oid in trip.order_ids:
                order = self._orders.get_by_id(oid)
                if not order:
                    continue

                order_total = order.total or 0.0
                delivery_fee = order.delivery_fee or 0.0
                is_cash = order.payment_method == PaymentMethod.CASH
                is_online = order.payment_method == PaymentMethod.ONLINE

                total_order_value += order_total
                total_delivery_fees += delivery_fee
                order_count += 1

                if is_cash:
                    trip_cash += order_total
                    cash_collected += order_total
                elif is_online:
                    trip_online += order_total
                    online_paid += order_total

                trip_fees += delivery_fee

                trip_orders.append({
                    "order_id": oid,
                    "invoice_no": order.invoice_no,
                    "customer_name": order.customer_name or "—",
                    "customer_address": order.customer_address or "—",
                    "customer_zone": order.customer_zone or "",
                    "total": order_total,
                    "delivery_fee": delivery_fee,
                    "payment_method": order.payment_method.value if order.payment_method else "cash",
                    "status": order.status.value,
                })

            per_trip_details.append({
                "trip_id": trip.id,
                "dispatched_at": str(trip.dispatched_at) if trip.dispatched_at else None,
                "returned_at": str(trip.returned_at) if trip.returned_at else None,
                "order_count": len(trip_orders),
                "cash": trip_cash,
                "online": trip_online,
                "fees": trip_fees,
                "orders": trip_orders,
            })

        return {
            "driver_id": driver_id,
            "driver_name": driver_name,
            "settlement_date": settlement_date,
            "trip_count": len(eligible_trips),
            "order_count": order_count,
            "total_order_value": round(total_order_value, 2),
            "cash_collected": round(cash_collected, 2),
            "online_paid": round(online_paid, 2),
            "total_delivery_fees": round(total_delivery_fees, 2),
            "trips": per_trip_details,
        }

    # ------------------------------------------------------------------
    # Phase 3: Ledger helper
    # ------------------------------------------------------------------

    def _create_driver_remittance_entry(
        self,
        trip_id: int,
        day_id: int,
        trip_cash: float,
        actor_id: int,
    ) -> None:
        """
        Append a DRIVER_REMITTANCE entry to the active DELIVERY or ALL session.

        Strategy:
          - Look up the active session on day_id for DELIVERY or ALL station.
          - If none found, skip silently (legacy / no-session mode).
          - Amount = round(trip_cash * 100) piasters (positive: cash into drawer).
          - Idempotency guaranteed by DB's uq_ledger_remit unique index on trip_id.
        """
        from broast_pos.core.models.cashier_session import (
            CashLedgerEntry, LedgerEntryType, Station,
        )
        import datetime as _dt

        if self._cashier_sessions is None:
            return

        open_sessions = self._cashier_sessions.get_open_sessions_for_day(day_id)
        # Prefer DELIVERY session, fall back to ALL
        session = next(
            (s for s in open_sessions if s.station == Station.DELIVERY), None
        ) or next(
            (s for s in open_sessions if s.station == Station.ALL), None
        )

        if session is None:
            return

        amount_pt = round(trip_cash * 100)
        try:
            self._ledger.append(CashLedgerEntry(
                id=None,
                day_id=day_id,
                session_id=session.id,
                entry_type=LedgerEntryType.DRIVER_REMITTANCE,
                amount_pt=amount_pt,
                trip_id=trip_id,
                actor_id=actor_id,
                created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            ))
        except Exception as exc:
            # uq_ledger_remit: already recorded (idempotency). Log and continue.
            logger.warning("DRIVER_REMITTANCE for trip %d already exists: %s", trip_id, exc)
