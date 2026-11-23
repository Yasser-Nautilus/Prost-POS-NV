"""Owner-scoped durable drafts, never confirmed sales or invoice reservations."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict
from enum import Enum

from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)


class ParkedDraftRepository:
    def __init__(self, db):
        self._db = db

    @contextmanager
    def transaction(self):
        with self._db.transaction():
            yield

    @staticmethod
    def encode(order: Order) -> str:
        return json.dumps(asdict(order), ensure_ascii=False,
                          default=lambda value: value.value if isinstance(value, Enum) else value)

    @staticmethod
    def decode(payload: str) -> Order:
        data = json.loads(payload)
        data["order_type"] = OrderType(data["order_type"])
        data["status"] = OrderStatus(data["status"])
        data["payment_method"] = PaymentMethod(data["payment_method"]) if data["payment_method"] else None
        data["items"] = [OrderItem(**item) for item in data["items"]]
        return Order(**data)

    def list_for_user(self, user_id: int) -> list[tuple[int, Order]]:
        return [(row["id"], self.decode(row["payload"])) for row in self._db.fetch_all(
            "SELECT id,payload FROM parked_order_drafts WHERE user_id=? ORDER BY id", (user_id,))]

    def baseline(self, user_id: int, draft_id: int) -> str | None:
        row = self._db.fetch_one("SELECT baseline FROM parked_order_drafts WHERE user_id=? AND id=?", (user_id, draft_id))
        if row is None:
            raise ValueError("الطلب المعلق غير موجود لهذا الكاشير")
        return row["baseline"]

    def save(self, user_id: int, order: Order, draft_id: int | None = None, baseline: str | None = None) -> int:
        payload = self.encode(order)
        if draft_id is None:
            cursor = self._db.execute("INSERT INTO parked_order_drafts(user_id,payload,baseline) VALUES (?,?,?)", (user_id, payload, baseline))
            return cursor.lastrowid
        cursor = self._db.execute(
            "UPDATE parked_order_drafts SET payload=?,updated_at=datetime('now','localtime') WHERE id=? AND user_id=?",
            (payload, draft_id, user_id))
        if cursor.rowcount != 1:
            raise ValueError("الطلب المعلق غير موجود لهذا الكاشير")
        return draft_id

    def delete(self, user_id: int, draft_id: int) -> None:
        cursor = self._db.execute("DELETE FROM parked_order_drafts WHERE id=? AND user_id=?", (draft_id, user_id))
        if cursor.rowcount != 1:
            raise ValueError("الطلب المعلق غير موجود لهذا الكاشير")
