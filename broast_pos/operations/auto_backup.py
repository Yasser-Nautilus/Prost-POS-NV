"""Automatic database backup taken when the business day is closed.

A consistent snapshot (SQLite backup API, includes committed WAL data) is
written next to the database file under ``backups/`` and old snapshots are
pruned. A backup failure never blocks closing the day: it is logged and
reported to the caller, not raised.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from broast_pos.operations.recovery import backup

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
BACKUP_PREFIX = "prost-dayclose-"
KEEP_LAST = 30


def run_day_close_backup(
    db_path: str | Path, *, keep: int = KEEP_LAST, now: datetime | None = None,
) -> Path | None:
    """Snapshot the live database after a day close. Returns the new file, or
    ``None`` when there is nothing to back up or the backup failed."""
    try:
        source = Path(db_path)
        if str(db_path) in ("", ":memory:") or not source.is_file():
            return None
        folder = source.parent / BACKUP_DIR_NAME
        folder.mkdir(parents=True, exist_ok=True)
        stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        target = folder / f"{BACKUP_PREFIX}{stamp}.db"
        counter = 1
        while target.exists():
            counter += 1
            target = folder / f"{BACKUP_PREFIX}{stamp}-{counter}.db"
        result = backup(source, target)
        _prune(folder, keep)
        logger.info("Day-close backup written: %s", result)
        return result
    except Exception:
        logger.exception("Day-close backup failed (day close is not affected)")
        return None


def _prune(folder: Path, keep: int) -> None:
    files = sorted(folder.glob(f"{BACKUP_PREFIX}*.db"), key=lambda p: p.stat().st_mtime)
    for old in files[: max(0, len(files) - keep)]:
        old.unlink(missing_ok=True)
