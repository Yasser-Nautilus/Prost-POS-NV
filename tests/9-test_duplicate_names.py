"""Duplicate usernames and active product names are rejected."""
from __future__ import annotations

import pytest

from broast_pos.core.models.user import UserRole
from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.product_service import ProductService
from broast_pos.data.database import seed_database
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.repositories.product_repository import ProductRepository
from broast_pos.data.repositories.user_repository import UserRepository


@pytest.fixture
def svc():
    conn = DatabaseConnection.get_instance(":memory:")
    initialise_database(conn)
    seed_database(conn)
    yield (
        AuthService(user_repo=UserRepository(db=conn)),
        ProductService(product_repo=ProductRepository(db=conn)),
        conn,
    )
    DatabaseConnection._instance = None


def test_duplicate_username_blocked(svc):
    auth, _, _ = svc
    auth.create_user("sam", "Sam", UserRole.MANAGER, "123456")
    with pytest.raises(ValueError, match="موجود بالفعل"):
        auth.create_user("SAM ", "Other", UserRole.MANAGER, "654321")
    other = auth.create_user("tom", "Tom", UserRole.MANAGER, "111222")
    with pytest.raises(ValueError, match="موجود بالفعل"):
        auth.update_user(other.id, username="sam")
    # keeping your own username on update is fine
    assert auth.update_user(other.id, username="tom", display_name="Tom 2").display_name == "Tom 2"


def test_duplicate_product_name_blocked(svc):
    _, prod, conn = svc
    cat = ProductRepository(db=conn).get_all_categories()[0]
    a = prod.create_product("برجر خاص", 50, cat.id)
    with pytest.raises(ValueError, match="موجود بالفعل"):
        prod.create_product("  برجر خاص ", 60, cat.id)
    b = prod.create_product("بطاطس", 20, cat.id)
    with pytest.raises(ValueError, match="موجود بالفعل"):
        prod.update_product(b.id, name="برجر خاص")
    assert prod.update_product(b.id, name="بطاطس", price=25).price == 25
    # a deleted product's name can be reused, but it cannot then be reactivated as a twin
    prod.delete_product(a.id)
    prod.create_product("برجر خاص", 55, cat.id)
    with pytest.raises(ValueError, match="موجود بالفعل"):
        prod.update_product(a.id, is_active=True)
