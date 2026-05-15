"""
Base repository — abstract CRUD contract for all repositories.

Repositories use the singleton DatabaseConnection. Services call
repositories; they never execute SQL directly.

Design:
- Generic[T] so each repo works with a specific model type.
- save() handles both insert (id is None) and update (id exists).
- delete() is always soft-delete (set is_active = 0), never hard-delete.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

from broast_pos.data.database.connection import DatabaseConnection

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Abstract base class defining the repository contract.

    Subclasses must implement the three core methods and supply
    their own SQL + row-to-model mapping logic.
    """

    def __init__(self, db: Optional[DatabaseConnection] = None) -> None:
        self._db = db or DatabaseConnection.get_instance()

    # ------------------------------------------------------------------
    # Abstract contract
    # ------------------------------------------------------------------

    @abstractmethod
    def get_by_id(self, entity_id: int) -> Optional[T]:
        """Fetch a single entity by primary key, or None."""

    @abstractmethod
    def save(self, entity: T) -> T:
        """Insert (id is None) or update (id exists). Returns the entity with id set."""

    @abstractmethod
    def delete(self, entity_id: int) -> None:
        """Soft-delete: set is_active = 0. Never hard-delete."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _last_insert_id(self) -> int:
        """Return the rowid of the last INSERT on this connection."""
        row = self._db.fetch_one("SELECT last_insert_rowid() AS id")
        return row["id"] if row else 0
