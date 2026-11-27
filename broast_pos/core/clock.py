"""Restaurant wall-clock helper.

SQLite's ``datetime('now', 'localtime')`` follows the OS timezone. A PC whose
OS clock zone is wrong (e.g. UTC) then stamps attendance two hours early in
Cairo. Attendance is stamped from here instead, always in the restaurant's
timezone, with a safe fallback to the OS local time when tz data is missing.
"""
from __future__ import annotations

import ctypes
import logging
import os
import time
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


_configured = False


def configure_process_timezone() -> None:
    """Pin the whole process to the restaurant's timezone.

    ``restaurant_now*`` already answers in Cairo time, but the rest of the app
    (Python's ``datetime.now()`` and SQLite's ``datetime('now','localtime')``
    column defaults) follows the OS timezone. On a machine set to UTC that put
    every stored timestamp two hours behind: a shift opened at 06:35 was saved
    as 04:16 and a brand-new order showed "02:06" elapsed on the tracking
    screen. Pinning TZ once, at database import, makes all three agree.

    Idempotent and never raises: if the platform refuses, the OS timezone stays
    in force and only a warning is logged.
    """
    global _configured
    if _configured:
        return
    _configured = True
    try:
        if os.environ.get("TZ") != RESTAURANT_TZ:
            os.environ["TZ"] = RESTAURANT_TZ
        tzset = getattr(time, "tzset", None)
        if tzset is not None:  # POSIX
            tzset()
        else:  # Windows CRT keeps its own copy of TZ
            try:
                ctypes.CDLL("msvcrt")._tzset()
            except Exception:  # pragma: no cover - non-CRT platform
                pass
    except Exception:  # pragma: no cover - defensive
        logging.getLogger(__name__).warning(
            "Could not pin the process timezone to %s", RESTAURANT_TZ, exc_info=True
        )
