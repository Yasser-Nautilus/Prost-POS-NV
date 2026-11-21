"""
Regression test — delivery_repository DATE filter double-conversion bug.

delivery_trips.created_at and driver_attendance.check_in_at are both stored as
local-time strings via datetime('now', 'localtime').  Filtering with
DATE(col, 'localtime') would double-shift the already-local value, causing
trips created at e.g. 23:00 local to appear as the NEXT calendar day and
silently drop them from settlement queries.

The fix: use DATE(col) — no modifier — for columns that already hold local time.
This test pins the timestamps at 23:00 local to exercise the exact failure case.
"""
from __future__ import annotations

import pytest

from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.delivery_repository import DeliveryRepository

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_db_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _fresh_db() -> DatabaseConnection:
    db = DatabaseConnection(":memory:")
    initialise_database(db)
    return db


def _seed_driver(db: DatabaseConnection, driver_id: int = 1) -> None:
    """Insert a minimal user row so FK constraints are satisfied."""
    db.execute(
        """INSERT INTO users (id, username, display_name, pin_hash, role,
                              cashier_slot, is_active)
           VALUES (?, 'driver1', 'سائق 1', 'x', 'manager', 1, 1)""",
        (driver_id,),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

LATE_EVENING = "2026-11-21 23:00:00"   # local time, near midnight
QUERY_DATE   = "2026-11-21"            # what date.today() would return


class TestDriverDailyTripsLateEvening:
    """get_driver_daily_trips must find trips created at 23:xx local."""

    def test_trip_at_2300_local_is_found_for_same_date(self):
        db = _fresh_db()
        _seed_driver(db)

        db.execute(
            """INSERT INTO delivery_trips
                   (driver_id, driver_name, created_at, returned_at)
               VALUES (1, 'سائق 1', ?, ?)""",
            (LATE_EVENING, LATE_EVENING),
        )

        repo = DeliveryRepository(db)
        trips = repo.get_driver_daily_trips(1, QUERY_DATE)

        assert len(trips) == 1, (
            f"Expected 1 trip for {QUERY_DATE!r} but got {len(trips)}. "
            "DATE(created_at, 'localtime') double-shifts already-local timestamps."
        )

    def test_trip_on_different_date_is_not_returned(self):
        db = _fresh_db()
        _seed_driver(db)

        db.execute(
            """INSERT INTO delivery_trips
                   (driver_id, driver_name, created_at, returned_at)
               VALUES (1, 'سائق 1', ?, ?)""",
            ("2026-11-20 23:00:00", "2026-11-20 23:30:00"),
        )

        repo = DeliveryRepository(db)
        trips = repo.get_driver_daily_trips(1, QUERY_DATE)
        assert trips == [], "Trip from a different date must not bleed into today's query."


class TestAllDriversDailySummaryLateEvening:
    """get_all_drivers_daily_summary must include trips created at 23:xx local."""

    def test_summary_includes_late_evening_trip(self):
        db = _fresh_db()
        _seed_driver(db)

        db.execute(
            """INSERT INTO delivery_trips
                   (driver_id, driver_name, created_at, total_delivery_fees)
               VALUES (1, 'سائق 1', ?, 25.0)""",
            (LATE_EVENING,),
        )

        repo = DeliveryRepository(db)
        summary = repo.get_all_drivers_daily_summary(QUERY_DATE)

        assert len(summary) == 1, (
            f"Expected 1 driver in summary for {QUERY_DATE!r} but got {len(summary)}."
        )
        assert summary[0]["trip_count"] == 1
        assert summary[0]["fees_earned"] == 25.0


class TestAttendanceQueryLateEvening:
    """get_attendance_for_date must find check-ins at 23:xx local."""

    def test_checkin_at_2300_found_for_same_date(self):
        db = _fresh_db()
        _seed_driver(db)

        db.execute(
            "INSERT INTO driver_attendance (driver_id, check_in_at) VALUES (1, ?)",
            (LATE_EVENING,),
        )

        repo = DeliveryRepository(db)
        records = repo.get_attendance_for_date(QUERY_DATE)

        assert len(records) == 1, (
            f"Expected 1 attendance record for {QUERY_DATE!r} but got {len(records)}. "
            "date(check_in_at, 'localtime') double-shifts already-local timestamps."
        )
