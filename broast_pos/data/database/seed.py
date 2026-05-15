"""
Seed data — sample records for fresh installations and testing.

Idempotent: only inserts data when the target table is completely empty.
This means re-running ``seed_database()`` on an already-populated database
is a safe no-op.

Data seeded:
    • 1 admin user  (PIN "1234" → SHA-256 hash)
    • 3 categories  (بروست, مشروبات, إضافات)
    • Sample products per category (each variation is a separate product)
    • 3 delivery zones with fixed fees
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from broast_pos.data.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_pin(pin: str) -> str:
    """Return the SHA-256 hex digest of a PIN string."""
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def _is_empty(db: "DatabaseConnection", table: str) -> bool:
    """Return True if *table* has zero rows."""
    row = db.fetch_one(f"SELECT COUNT(*) AS c FROM {table}")  # noqa: S608
    return row["c"] == 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def seed_database(db: "DatabaseConnection") -> None:
    """Insert sample data into empty tables.

    Call this after ``initialise_database()`` at app startup.
    """
    _seed_users(db)
    _seed_categories_and_products(db)
    _seed_zones(db)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _seed_users(db: "DatabaseConnection") -> None:
    if not _is_empty(db, "users"):
        logger.debug("users table already populated — skipping seed")
        return

    db.execute(
        """
        INSERT INTO users (username, display_name, pin_hash, role, cashier_slot, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("admin", "مدير النظام", _hash_pin("1234"), "admin", 1, 1),
    )
    db.commit()
    logger.info("Seeded default admin user (PIN: 1234)")


# ---------------------------------------------------------------------------
# Categories & Products
# ---------------------------------------------------------------------------
_SEED_CATEGORIES: list[tuple[str, int]] = [
    # (name, sort_order)
    ("بروست", 1),
    ("مشروبات", 2),
    ("إضافات", 3),
]

_SEED_PRODUCTS: dict[str, list[tuple[str, float, int]]] = {
    # category_name → [(product_name, price, sort_order), ...]
    "بروست": [
        ("تشيكن فرايز حار", 70.0, 1),
        ("تشيكن فرايز عادي", 70.0, 2),
        ("2 قطعة دجاج حار", 110.0, 3),
        ("2 قطعة دجاج عادي", 110.0, 4),
    ],
    "مشروبات": [
        ("بيبسي", 15.0, 1),
        ("ميرندا", 15.0, 2),
        ("مياه", 10.0, 3),
    ],
    "إضافات": [
        ("أرز", 20.0, 1),
        ("بطاطس كبير", 30.0, 2),
        ("كول سلو", 15.0, 3),
    ],
}


def _seed_categories_and_products(db: "DatabaseConnection") -> None:
    if not _is_empty(db, "categories"):
        logger.debug("categories table already populated — skipping seed")
        return

    # Insert categories and collect their IDs
    category_ids: dict[str, int] = {}
    for name, sort_order in _SEED_CATEGORIES:
        cursor = db.execute(
            "INSERT INTO categories (name, sort_order, is_active) VALUES (?, ?, 1)",
            (name, sort_order),
        )
        category_ids[name] = cursor.lastrowid

    # Insert products linked to their category
    for cat_name, products in _SEED_PRODUCTS.items():
        cat_id = category_ids.get(cat_name)
        if cat_id is None:
            continue
        for product_name, price, sort_order in products:
            db.execute(
                """
                INSERT INTO products (name, price, category_id, is_active, sort_order)
                VALUES (?, ?, ?, 1, ?)
                """,
                (product_name, price, cat_id, sort_order),
            )

    db.commit()
    total_products = sum(len(p) for p in _SEED_PRODUCTS.values())
    logger.info(
        "Seeded %d categories and %d products",
        len(_SEED_CATEGORIES),
        total_products,
    )


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
_SEED_ZONES: list[tuple[str, float]] = [
    # (name, delivery_fee)
    ("مدينة فاقوس", 20.0),
    ("شارع الانتاج", 15.0),
    ("الغابة", 80.0),
]


def _seed_zones(db: "DatabaseConnection") -> None:
    if not _is_empty(db, "zones"):
        logger.debug("zones table already populated — skipping seed")
        return

    for name, fee in _SEED_ZONES:
        db.execute(
            "INSERT INTO zones (name, delivery_fee, is_active) VALUES (?, ?, 1)",
            (name, fee),
        )

    db.commit()
    logger.info("Seeded %d delivery zones", len(_SEED_ZONES))
