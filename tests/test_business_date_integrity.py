"""Stored shift timestamps are local wall time, not UTC awaiting conversion."""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from test_h16_report_scope import env as scope_env
from test_h16_report_scope import reset_db_singleton  # noqa: F401

from broast_pos.data.database.migrations import _migrate_v4_to_v5, initialise_database
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.infrastructure.printing.receipt_templates import (
    print_daily_sales_report,
)


@pytest.fixture
def env():
    return scope_env.__wrapped__()


@pytest.fixture
def cairo_timezone():
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Africa/Cairo"
    time.tzset()
    yield
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def test_new_shift_has_local_business_date(env, cairo_timezone):
    ctrl, _, _ = env
    db = ctrl._report_svc._orders._db
    shift = FinancialRepository(db).open_shift(1)
    row = db.fetch_one("SELECT opened_at,business_date FROM shifts WHERE id=?", (shift.id,))
    assert row["business_date"] == row["opened_at"][:10]
    assert row["business_date"] == datetime.now().date().isoformat()


@pytest.mark.parametrize("opened", ["2026-03-10 23:30:00", "2026-08-10 23:30:00", "2026-03-11T00:30:00"])
def test_legacy_v4_backfill_does_not_convert_local_time_twice(env, cairo_timezone, opened):
    ctrl, _, _ = env
    db = ctrl._report_svc._orders._db
    db.execute("UPDATE shifts SET business_date=NULL,opened_at=? WHERE id=1", (opened,))
    db.commit()
    _migrate_v4_to_v5(db)
    assert db.fetch_one("SELECT business_date FROM shifts WHERE id=1")["business_date"] == opened[:10]


def test_v12_fills_only_null_dates_and_preserves_existing_choices(env, cairo_timezone):
    ctrl, _, _ = env
    db = ctrl._report_svc._orders._db
    db.execute("UPDATE shifts SET business_date=NULL,opened_at='2026-03-10 23:30:00' WHERE id=1")
    db.execute("UPDATE shifts SET business_date='2026-03-12',opened_at='2026-03-11 23:30:00' WHERE id=2")
    db.execute("UPDATE schema_version SET version=11")
    db.commit()
    initialise_database(db)
    initialise_database(db)
    rows = db.fetch_all("SELECT id,business_date FROM shifts ORDER BY id")
    assert [(r["id"], r["business_date"]) for r in rows] == [(1, "2026-03-10"), (2, "2026-03-12")]
    assert ctrl._report_svc._orders.get_shift_business_date(2) == "2026-03-12"


class Paper:
    """Capture exactly the text/style calls from the production receipt template."""
    def __init__(self):
        self.lines = []
    def print_text(self, text, **style):
        self.lines.append({"text": text, **style})
        return True
    def print_double_line(self, width):
        return self.print_text("=" * width)
    def print_line(self, symbol, width):
        return self.print_text(symbol * width)
    def cut(self):
        return True


class PrintClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 23, 3, 27)


def test_historical_day_print_carries_requested_period_and_separate_print_time(env):
    ctrl, printer, fin = env
    assert ctrl.print_daily_summary(target_date=date(2026, 3, 11))
    payload = printer.print_shift_summary.call_args.args[0]
    period = printer.print_shift_summary.call_args.kwargs["shift_period"]
    assert payload["date"] == "2026-03-11"
    assert payload["scope"] == "calendar_day"
    paper = Paper()
    with patch("broast_pos.infrastructure.printing.receipt_templates.datetime", PrintClock):
        assert print_daily_sales_report(paper, payload, period)
    lines = [line["text"] for line in paper.lines]
    assert "Report date: 2026-03-11" in lines
    assert "Printed: 2026-11-23 03:27" in lines
    assert any("00:00 2026-03-11" in line for line in lines)
    assert any("23:59:59" in line for line in lines)
    fin.mark_summary_printed.assert_not_called()
    directory = os.environ.get("POS_UI_EVIDENCE_DIR")
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        (Path(directory) / "14-historical-print.json").write_text(json.dumps(paper.lines, ensure_ascii=False))


def test_shift_print_retains_cross_midnight_real_period(env):
    ctrl, printer, financial = env
    financial._financial = FinancialRepository(ctrl._report_svc._orders._db)
    assert ctrl.print_daily_summary(shift_id=1)
    payload = printer.print_shift_summary.call_args.args[0]
    period = printer.print_shift_summary.call_args.kwargs["shift_period"]
    assert payload["scope"] == "shift" and payload["shift_id"] == 1
    assert period["from_date"] == "2026-03-10" and period["to_date"] == "2026-03-11"
    paper = Paper()
    with patch("broast_pos.infrastructure.printing.receipt_templates.datetime", PrintClock):
        assert print_daily_sales_report(paper, payload, period)
    assert "Shift: 1" in [line["text"] for line in paper.lines]
