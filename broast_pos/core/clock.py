"""Restaurant wall-clock helper.

SQLite's ``datetime('now', 'localtime')`` follows the OS timezone. A PC whose
OS clock zone is wrong (e.g. UTC) then stamps attendance two hours early in
Cairo. Attendance is stamped from here instead, always in the restaurant's
timezone, with a safe fallback to the OS local time when tz data is missing.
"""
from __future__ import annotations

from datetime import date, datetime

RESTAURANT_TZ = "Africa/Cairo"


def restaurant_now() -> datetime:
    """Current naive wall-clock time in the restaurant's timezone."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(RESTAURANT_TZ)).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def restaurant_now_str() -> str:
    return restaurant_now().strftime("%Y-%m-%d %H:%M:%S")


def restaurant_today() -> date:
    return restaurant_now().date()
