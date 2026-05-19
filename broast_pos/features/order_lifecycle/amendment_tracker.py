"""
Amendment tracker — tracks changes to saved orders.

Compares original items snapshot with current state to generate
the changes list for the amendment kitchen ticket ("تابع").

Only actual changes are printed — no fixed "Added"/"Removed" headers.
Changes are printed in the order they happened.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from broast_pos.core.models.order import OrderItem

logger = logging.getLogger(__name__)


@dataclass
class OrderChange:
    """Represents a single change in an amendment."""

    action: str  # "added" or "removed"
    product_name: str
    quantity: int


class AmendmentTracker:
    """Tracks modifications to a saved order for amendment printing.

    Usage:
        tracker = AmendmentTracker()
        tracker.snapshot(order.items)  # Take snapshot before editing
        # ... user edits items ...
        changes = tracker.diff(order.items)  # Get changes for printing
    """

    # Key type: (product_id, notes) — distinguishes same product with
    # different special instructions (e.g., "chicken fries" vs "chicken fries, no salt").
    _Key = Tuple[int, str]

    def __init__(self) -> None:
        self._original: Optional[Dict[AmendmentTracker._Key, int]] = None
        self._original_names: Dict[AmendmentTracker._Key, str] = {}

    def snapshot(self, items: List[OrderItem]) -> None:
        """Take a snapshot of the current items before editing.

        Args:
            items: Current order items to snapshot.
        """
        self._original = {}
        self._original_names = {}
        for item in items:
            key = (item.product_id, item.notes or "")
            self._original[key] = item.quantity
            self._original_names[key] = item.product_name
        logger.debug("Amendment snapshot taken: %d items", len(items))

    def diff(self, current_items: List[OrderItem]) -> List[Dict[str, object]]:
        """Compare current items against snapshot and return changes.

        Returns list of change dicts for printing:
        [
            {"action": "added", "product_name": "...", "quantity": 2},
            {"action": "removed", "product_name": "...", "quantity": 1},
        ]

        Changes are ordered: additions first, then removals.
        """
        if self._original is None:
            return []

        changes: List[OrderChange] = []
        current_map: Dict[AmendmentTracker._Key, int] = {}
        current_names: Dict[AmendmentTracker._Key, str] = {}

        for item in current_items:
            key = (item.product_id, item.notes or "")
            current_map[key] = item.quantity
            current_names[key] = item.product_name

        # Check for additions and quantity increases
        for key, qty in current_map.items():
            orig_qty = self._original.get(key, 0)
            if qty > orig_qty:
                name = current_names[key]
                changes.append(OrderChange(
                    action="added",
                    product_name=name,
                    quantity=qty - orig_qty,
                ))

        # Check for removals and quantity decreases
        for key, orig_qty in self._original.items():
            curr_qty = current_map.get(key, 0)
            if curr_qty < orig_qty:
                name = self._original_names[key]
                changes.append(OrderChange(
                    action="removed",
                    product_name=name,
                    quantity=orig_qty - curr_qty,
                ))

        # Convert to dicts for printer
        return [
            {
                "action": c.action,
                "product_name": c.product_name,
                "quantity": c.quantity,
            }
            for c in changes
        ]

    def has_changes(self, current_items: List[OrderItem]) -> bool:
        """Check if there are any changes since the snapshot."""
        return len(self.diff(current_items)) > 0

    def clear(self) -> None:
        """Clear the snapshot."""
        self._original = None
        self._original_names = {}
