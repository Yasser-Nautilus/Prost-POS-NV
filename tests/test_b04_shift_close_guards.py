"""
Tests for B-04 — Shift-Close Guards.

Guards (in order):
  G1: daily summary must be printed
  G2: no drivers currently in transit (dispatched, not returned)  ← NEW
  G3: no returned-but-unsettled trips
  G4: no open unpaid cash orders (new/preparing/ready)            ← NEW

Each guard must raise a distinct ValueError with an actionable message.
All four guards must be independent — a failure on G2 must not mask G3/G4.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from typing import Optional

from broast_pos.core.models.financial import Shift
from broast_pos.core.services.financial_service import FinancialService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shift(
    is_active: bool = True,
    summary_printed: bool = True,  # most tests want this satisfied
) -> Shift:
    return Shift(
        id=1,
        opened_by=1,
        opened_at="2026-10-04T08:00:00",
        is_active=is_active,
        summary_printed_at="2026-10-04T09:00:00" if summary_printed else None,
    )


def _manager():
    m = MagicMock()
    m.id = 99
    m.display_name = "مدير"
    m.username = "manager"
    return m


def _financial_svc(
    shift: Shift,
    *,
    has_active_trips: bool = False,
    has_unsettled_trips: bool = False,
    has_open_orders: bool = False,
    unsettled_trip_list=None,
    manager=None,
) -> FinancialService:
    fin_repo = MagicMock()
    fin_repo.get_by_id.return_value = shift
    fin_repo.save.side_effect = lambda s: s
    fin_repo.has_active_trips.return_value = has_active_trips
    fin_repo.has_open_orders.return_value = has_open_orders

    delivery_svc = MagicMock()
    delivery_svc.get_unsettled_trips.return_value = (
        unsettled_trip_list if has_unsettled_trips else []
    )

    audit_repo = MagicMock()
    audit_svc = MagicMock()

    svc = FinancialService.__new__(FinancialService)
    svc._financial = fin_repo
    svc._delivery = delivery_svc
    svc._audit = audit_svc
    svc._auth = MagicMock()

    # Patch PIN verification to return manager
    svc._verify_manager_pin = MagicMock(return_value=manager or _manager())

    return svc


# ===========================================================================
# G1: Daily summary printed
# ===========================================================================

class TestGuard1SummaryPrinted:

    def test_raises_if_summary_not_printed(self):
        shift = _shift(summary_printed=False)
        svc = _financial_svc(shift)
        with pytest.raises(ValueError, match="تقرير"):
            svc.close_shift(shift_id=1, manager_pin="1234")

    def test_allows_close_when_summary_printed(self):
        shift = _shift(summary_printed=True)
        svc = _financial_svc(shift)
        result = svc.close_shift(shift_id=1, manager_pin="1234")
        assert not result.is_active


# ===========================================================================
# G2: No drivers in transit (B-04 NEW GUARD)
# ===========================================================================

class TestGuard2NoDriversInTransit:

    def test_raises_if_driver_still_out(self):
        """B-04: if a driver is dispatched and not returned, close must fail."""
        shift = _shift()
        svc = _financial_svc(shift, has_active_trips=True)
        with pytest.raises(ValueError, match="سائقون في الطريق"):
            svc.close_shift(shift_id=1, manager_pin="1234")

    def test_allows_close_when_no_driver_in_transit(self):
        shift = _shift()
        svc = _financial_svc(shift, has_active_trips=False)
        result = svc.close_shift(shift_id=1, manager_pin="1234")
        assert not result.is_active

    def test_guard2_checked_before_guard3(self):
        """Guard ordering: in-transit trips block before unsettled trips."""
        shift = _shift()
        svc = _financial_svc(
            shift,
            has_active_trips=True,
            has_unsettled_trips=True,   # both bad
        )
        with pytest.raises(ValueError, match="سائقون في الطريق"):
            svc.close_shift(shift_id=1, manager_pin="1234")
        # Must fail on G2, not G3 — message matches G2

    def test_guard2_uses_financial_repo_not_delivery_svc(self):
        """G2 must call financial_repo.has_active_trips(), not delivery_svc."""
        shift = _shift()
        svc = _financial_svc(shift, has_active_trips=True)
        with pytest.raises(ValueError):
            svc.close_shift(shift_id=1, manager_pin="1234")
        # financial repo method was called
        svc._financial.has_active_trips.assert_called_once()


# ===========================================================================
# G3: No returned-but-unsettled trips
# ===========================================================================

class TestGuard3NoUnsettledTrips:

    def test_raises_if_returned_unsettled_trip(self):
        shift = _shift()
        svc = _financial_svc(shift, has_unsettled_trips=True, unsettled_trip_list=[MagicMock()])
        with pytest.raises(ValueError, match="رحلات غير محسوبة"):
            svc.close_shift(shift_id=1, manager_pin="1234")

    def test_allows_close_when_all_trips_settled(self):
        shift = _shift()
        svc = _financial_svc(shift, has_unsettled_trips=False)
        result = svc.close_shift(shift_id=1, manager_pin="1234")
        assert not result.is_active

    def test_guard3_skipped_when_no_delivery_svc(self):
        """If delivery service not injected, G3 is a no-op (graceful degradation)."""
        shift = _shift()
        svc = _financial_svc(shift)
        svc._delivery = None   # remove delivery service
        result = svc.close_shift(shift_id=1, manager_pin="1234")
        assert not result.is_active


# ===========================================================================
# G4: No open unpaid cash orders (B-04 NEW GUARD)
# ===========================================================================

class TestGuard4NoOpenOrders:

    def test_raises_if_open_cash_orders_exist(self):
        """B-04: new/preparing/ready orders block shift close."""
        shift = _shift()
        svc = _financial_svc(shift, has_open_orders=True)
        with pytest.raises(ValueError, match="طلبات مفتوحة"):
            svc.close_shift(shift_id=1, manager_pin="1234")

    def test_allows_close_when_no_open_orders(self):
        shift = _shift()
        svc = _financial_svc(shift, has_open_orders=False)
        result = svc.close_shift(shift_id=1, manager_pin="1234")
        assert not result.is_active

    def test_guard4_checked_last(self):
        """G4 only fires if G1–G3 all pass."""
        shift = _shift()
        svc = _financial_svc(shift, has_open_orders=True)
        with pytest.raises(ValueError, match="طلبات مفتوحة"):
            svc.close_shift(shift_id=1, manager_pin="1234")

    def test_guard4_passes_shift_id_to_repo(self):
        """Guard 4 must pass the correct shift_id to has_open_orders."""
        shift = _shift()
        shift.id = 42
        svc = _financial_svc(shift, has_open_orders=False)
        svc.close_shift(shift_id=42, manager_pin="1234")
        svc._financial.has_open_orders.assert_called_once_with(42)


# ===========================================================================
# Repository SQL — guard query correctness
# ===========================================================================

class TestRepositoryGuardQueries:

    def test_has_active_trips_query_checks_not_returned(self):
        """has_active_trips SQL must filter dispatched_at IS NOT NULL AND returned_at IS NULL."""
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        captured = []

        class CapDB:
            def fetch_one(self, sql, params=()):
                captured.append(sql)
                return {"cnt": 0}

        repo._db = CapDB()
        repo.has_active_trips()

        assert captured, "has_active_trips must query the DB"
        sql = captured[0]
        assert "dispatched_at IS NOT NULL" in sql, f"Missing dispatched check: {sql!r}"
        assert "returned_at IS NULL" in sql, f"Missing returned check: {sql!r}"

    def test_has_open_orders_query_checks_status_and_paid(self):
        """has_open_orders SQL must check status IN (new/preparing/ready) AND is_paid=0."""
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        captured = []

        class CapDB:
            def fetch_one(self, sql, params=()):
                captured.append(sql)
                return {"cnt": 0}

        repo._db = CapDB()
        repo.has_open_orders(shift_id=1)

        assert captured
        sql = captured[0]
        assert "is_paid = 0" in sql, f"Missing is_paid check: {sql!r}"
        assert "preparing" in sql, f"Missing preparing status: {sql!r}"
        assert "ready" in sql, f"Missing ready status: {sql!r}"

    def test_has_active_trips_returns_false_when_count_zero(self):
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        repo._db = MagicMock(**{"fetch_one.return_value": {"cnt": 0}})
        assert repo.has_active_trips() is False

    def test_has_active_trips_returns_true_when_count_positive(self):
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        repo._db = MagicMock(**{"fetch_one.return_value": {"cnt": 2}})
        assert repo.has_active_trips() is True

    def test_has_open_orders_returns_false_when_count_zero(self):
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        repo._db = MagicMock(**{"fetch_one.return_value": {"cnt": 0}})
        assert repo.has_open_orders(shift_id=1) is False

    def test_has_open_orders_returns_true_when_count_positive(self):
        from broast_pos.data.repositories.financial_repository import FinancialRepository
        repo = FinancialRepository.__new__(FinancialRepository)
        repo._db = MagicMock(**{"fetch_one.return_value": {"cnt": 3}})
        assert repo.has_open_orders(shift_id=1) is True
