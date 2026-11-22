"""
Regression tests for BUG-03 — audit_log.action is NULL for shift lifecycle events.

FinancialService.open_shift, transfer_shift and close_shift all call
audit_repo.log() without an `action` kwarg, leaving that column NULL.
The fix populates action with Arabic text consistent with other audit events.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from broast_pos.core.models.financial import Shift
from broast_pos.core.services.financial_service import FinancialService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shift(summary_printed: bool = True) -> Shift:
    return Shift(
        id=1, opened_by=1, opened_at="2026-11-21T08:00:00", is_active=True,
        summary_printed_at="2026-11-21T09:00:00" if summary_printed else None,
    )


def _manager(user_id: int = 2) -> MagicMock:
    m = MagicMock()
    m.id = user_id
    m.display_name = "مدير"
    m.is_manager_or_above.return_value = True
    return m


def _svc(shift: Shift | None = None, auth=None) -> tuple[FinancialService, MagicMock]:
    audit_repo = MagicMock()
    financial_repo = MagicMock()
    financial_repo.get_active_shift.return_value = shift or _shift()
    financial_repo.get_by_id.return_value = shift or _shift()
    financial_repo.has_active_trips.return_value = False
    financial_repo.has_open_orders.return_value = False
    financial_repo.save.side_effect = lambda s: s
    financial_repo.open_shift.return_value = Shift(
        id=10, opened_by=1, opened_at="2026-11-21T08:00:00", is_active=True,
    )

    if auth is None:
        auth = MagicMock()
        auth.get_current_user.return_value = _manager()
        auth.get_user_by_id.return_value = _manager(1)
        auth.verify_pin.return_value = _manager()

    svc = FinancialService(
        financial_repo=financial_repo,
        audit_repo=audit_repo,
        auth_service=auth,
    )
    return svc, audit_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOpenShiftAuditAction:

    def test_action_is_populated(self):
        svc, audit = _svc(shift=None)
        svc._financial.get_active_shift.return_value = None  # no existing shift
        svc.open_shift(user_id=1)
        call_kwargs = audit.log.call_args.kwargs
        assert call_kwargs.get("action") == "فتح الوردية"

    def test_event_type_is_shift_opened(self):
        svc, audit = _svc(shift=None)
        svc._financial.get_active_shift.return_value = None
        svc.open_shift(user_id=1)
        assert audit.log.call_args.kwargs.get("event_type") == "shift_opened"


class TestCloseShiftAuditAction:

    def test_action_is_populated(self):
        svc, audit = _svc()
        svc.close_shift(shift_id=1, manager_pin="1234")
        call_kwargs = audit.log.call_args.kwargs
        assert call_kwargs.get("action") == "إغلاق الوردية"

    def test_event_type_is_shift_closed(self):
        svc, audit = _svc()
        svc.close_shift(shift_id=1, manager_pin="1234")
        assert audit.log.call_args.kwargs.get("event_type") == "shift_closed"
