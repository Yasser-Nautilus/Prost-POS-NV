"""
User models — User and UserRole.

PIN-based authentication with SHA-256 hashing. PIN uniqueness enables
the manager override pattern: manager types their PIN on any cashier
device, system identifies them by PIN alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class UserRole(Enum):
    """
    Three roles with a clear permission hierarchy.

    CASHIER  — order creation, driver check-in/out, settlement
    MANAGER  — owner: discounts, cancellations, products, drivers, shifts, reports
    ADMIN    — developer: full access including user management
    """
    CASHIER = "cashier"
    MANAGER = "manager"
    ADMIN = "admin"

    def has_manager_access(self) -> bool:
        """Manager or Admin can perform privileged operations."""
        return self in (UserRole.MANAGER, UserRole.ADMIN)


@dataclass
class User:
    """
    A system user (cashier, manager, or admin).

    - `pin_hash` is SHA-256 and UNIQUE — users are identified by PIN alone.
    - `cashier_slot` (1 or 2) determines which receipt printer to use.
      NULL for drivers who don't print receipts.
    - `avatar_path` is shown on the login screen tiles.
    """
    id: Optional[int] = None
    username: str = ""
    display_name: str = ""
    avatar_path: Optional[str] = None
    pin_hash: str = ""
    role: UserRole = UserRole.CASHIER
    cashier_slot: Optional[int] = None  # 1 or 2, NULL for drivers
    is_active: bool = True
    created_at: Optional[str] = None

    def is_manager_or_above(self) -> bool:
        """Check if user has manager-level privileges."""
        return self.role.has_manager_access()

    def can_authorise_discount(self) -> bool:
        """Only managers and admins can authorise discounts."""
        return self.role.has_manager_access()

    def can_cancel_order(self) -> bool:
        """Only managers and admins can cancel orders."""
        return self.role.has_manager_access()
