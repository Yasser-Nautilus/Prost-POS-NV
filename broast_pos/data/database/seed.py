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
import secrets
from typing import TYPE_CHECKING

from broast_pos.config import config

if TYPE_CHECKING:
    from broast_pos.data.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

DISALLOWED_INITIAL_ADMIN_PINS: set[str] = {
    "1234",
    "0000",
    "1111",
    "2222",
    "3333",
    "4444",
    "5555",
    "6666",
    "7777",
    "8888",
    "9999",
    "password",
    "admin",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hash_pin_pbkdf2(pin: str, salt: str, pepper: str) -> str:
    """PBKDF2-HMAC-SHA256 hash using the versioned format."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        (pepper + pin).encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return f"pbkdf2_sha256$100000${dk.hex()}"


def _is_empty(db: DatabaseConnection, table: str) -> bool:
    """Return True if *table* has zero rows."""
    row = db.fetch_one(f"SELECT COUNT(*) AS c FROM {table}")
    return row["c"] == 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def seed_database(db: DatabaseConnection) -> None:
    """Insert sample data into empty tables.

    Call this after ``initialise_database()`` at app startup.
    In production, a secure BROAST_INITIAL_ADMIN_PIN is required to seed users.
    """
    _seed_users(db)
    _seed_categories_and_products(db)
    _seed_zones(db)


_MENU_IMPORT_MARKER = 1  # PRAGMA user_version value once the menu was imported


def ensure_menu_products(db: DatabaseConnection) -> int:
    """Add the printed menu's categories and products once. Returns rows added.

    Runs a single time per database (tracked with ``PRAGMA user_version``), so
    items the owner later deletes or deactivates are not brought back. Existing
    categories/products are matched by exact name and are never modified.
    """
    from broast_pos.data.database.menu_data import MENU

    row = db.fetch_one("PRAGMA user_version")
    current = (row[0] if row is not None else 0) or 0
    if current >= _MENU_IMPORT_MARKER:
        return 0

    added = 0
    with db.transaction():
        for cat_name, cat_order, items in MENU:
            cat = db.fetch_one("SELECT id FROM categories WHERE name = ?", (cat_name,))
            if cat is None:
                cur = db.execute(
                    "INSERT INTO categories (name, sort_order, is_active) VALUES (?, ?, 1)",
                    (cat_name, cat_order),
                )
                cat_id = cur.lastrowid
            else:
                cat_id = cat["id"]
            base = db.fetch_one(
                "SELECT COALESCE(MAX(sort_order), 0) AS m FROM products WHERE category_id = ?",
                (cat_id,),
            )["m"]
            for i, (name, price) in enumerate(items, start=1):
                if db.fetch_one("SELECT 1 FROM products WHERE name = ?", (name,)):
                    continue
                db.execute(
                    "INSERT INTO products (name, price, category_id, is_active, sort_order)"
                    " VALUES (?, ?, ?, 1, ?)",
                    (name, price, cat_id, base + i),
                )
                added += 1
    db.execute(f"PRAGMA user_version = {_MENU_IMPORT_MARKER}")
    db.commit()
    logger.info("Menu import: added %d products", added)
    return added


def validate_no_default_admin(db: DatabaseConnection) -> None:
    """Verify that no active admin or manager has the default/known PIN '1234' in production.

    Raises:
        RuntimeError: If running in production and any active admin/manager has the default PIN,
                      or if no active admin/manager exists.
    """
    if not config.is_production():
        return

    rows = db.fetch_all(
        "SELECT id, username, role, pin_hash, pin_salt FROM users WHERE is_active = 1 AND role IN ('admin', 'manager')"
    )
    if not rows:
        raise RuntimeError(
            "Security violation in production (APP_ENV=prod): No active admin or manager user found in database. "
            "Initial admin setup required."
        )

    legacy_default_hash = hashlib.sha256(b"1234").hexdigest()
    pepper = config.get_pin_pepper()

    for user in rows:
        stored_hash = user["pin_hash"] or ""
        salt = user["pin_salt"]

        # Check 1: Legacy unsalted hash of "1234"
        if stored_hash == legacy_default_hash:
            raise RuntimeError(
                f"Default admin credentials detected in production: user '{user['username']}' "
                "has the published default PIN '1234' (legacy hash). Change this PIN immediately before running in production."
            )

        # Check 2: Salted PBKDF2 or legacy-salted hash matching "1234"
        if salt:
            if stored_hash.startswith("pbkdf2_sha256$"):
                try:
                    _, iter_str, expected = stored_hash.split("$", 2)
                    dk = hashlib.pbkdf2_hmac(
                        "sha256",
                        (pepper + "1234").encode("utf-8"),
                        salt.encode("utf-8"),
                        int(iter_str),
                    )
                    if secrets.compare_digest(dk.hex(), expected):
                        raise RuntimeError(
                            f"Default admin credentials detected in production: user '{user['username']}' "
                            "has the default PIN '1234'. Change this PIN immediately before running in production."
                        )
                except (ValueError, AttributeError):
                    pass
            else:
                expected_salted = hashlib.sha256((pepper + salt + "1234").encode("utf-8")).hexdigest()
                if secrets.compare_digest(stored_hash, expected_salted):
                    raise RuntimeError(
                        f"Default admin credentials detected in production: user '{user['username']}' "
                        "has the default PIN '1234'. Change this PIN immediately before running in production."
                    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _seed_users(db: DatabaseConnection) -> None:
    if not _is_empty(db, "users"):
        logger.debug("users table already populated — skipping seed")
        return

    is_prod = config.is_production()
    initial_pin = config.get_initial_admin_pin()

    if is_prod:
        if not initial_pin:
            raise RuntimeError(
                "Initial admin setup required in production (APP_ENV=prod): "
                "BROAST_INITIAL_ADMIN_PIN must be set to a secure PIN. "
                "Refusing to seed or run without secure initial admin configuration."
            )
        if len(initial_pin) < 4 or initial_pin in DISALLOWED_INITIAL_ADMIN_PINS:
            raise RuntimeError(
                f"Insecure BROAST_INITIAL_ADMIN_PIN rejected in production: {initial_pin!r}. "
                "Initial admin PIN must be at least 4 digits and cannot be a trivial default like '1234'."
            )
        pin_to_use = initial_pin
    else:
        pin_to_use = initial_pin if initial_pin else "1234"

    salt = secrets.token_hex(16)
    pepper = config.get_pin_pepper()
    pin_hash = _hash_pin_pbkdf2(pin_to_use, salt, pepper)

    db.execute(
        """
        INSERT INTO users (username, display_name, pin_hash, pin_salt, role, cashier_slot, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("admin", "مدير النظام", pin_hash, salt, "admin", 1, 1),
    )
    db.commit()
    logger.info("Seeded initial admin user (username: admin, secure PBKDF2 hash)")


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


def _seed_categories_and_products(db: DatabaseConnection) -> None:
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


def _seed_zones(db: DatabaseConnection) -> None:
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
