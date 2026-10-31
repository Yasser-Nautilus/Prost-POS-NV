"""
Cashier Session and Cash Ledger models.

v2 data model additions (Phase 1):

  Station         — ALL / COUNTER / DELIVERY
  CashierSession  — one cashier's open shift at a station within a business day
  LedgerEntryType — all cash-movement event types (append-only)
  CashLedgerEntry — single entry in the cash_ledger table

Business rule: expected_cash(session) = SUM(cash_ledger.amount_pt WHERE session_id = ?)
There is NO other formula for the expected drawer balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Station(str, Enum):
    """Physical cashier station type."""
    ALL = "ALL"           # Morning / single cashier (can handle all order types)
    COUNTER = "COUNTER"   # Night counter: dine-in, takeaway, pickup
    DELIVERY = "DELIVERY" # Night delivery: delivery orders, driver settlement


class LedgerEntryType(str, Enum):
    """Every possible cash movement type in the drawer (append-only)."""
    OPENING_FLOAT    = "OPENING_FLOAT"     # (+) session opens with initial cash
    HANDOVER_IN      = "HANDOVER_IN"       # (+) receives counted cash from previous session
    HANDOVER_OUT     = "HANDOVER_OUT"      # (−) hands counted cash to next session
    SALE_CASH        = "SALE_CASH"         # (+) cash payment collected for an order
    DRIVER_REMITTANCE = "DRIVER_REMITTANCE" # (+) driver hands over collected cash
    DRIVER_FEE_PAYOUT = "DRIVER_FEE_PAYOUT" # (−) delivery fee paid to driver (end of day)
    EXPENSE          = "EXPENSE"           # (−) expense paid from drawer
    CASH_DROP        = "CASH_DROP"         # (−) withdrawal to safe (manager)
    REVERSAL         = "REVERSAL"          # (−) reversal of a previous entry (PIN+reason)
    ADJUSTMENT       = "ADJUSTMENT"        # (±) discrepancy at count (recorded under cashier)


@dataclass
class CashierSession:
    """
    One cashier's open shift at a station within a business day.

    Financial rule: opening_float_pt and all subsequent cash flows are
    recorded in cash_ledger — do NOT compute the balance from this object.
    Use CashLedgerRepository.get_session_balance_pt(session_id) instead.
    """
    id: Optional[int]
    day_id: int                     # FK → shifts.id (the operating day)
    user_id: int                    # FK → users.id
    station: Station                # ALL / COUNTER / DELIVERY
    is_open: bool = True

    opened_at: Optional[str] = None
    closed_at: Optional[str] = None

    # Set at opening; stored for reference (ledger OPENING_FLOAT is authoritative)
    opening_float_pt: int = 0       # piasters (integer)

    # Set at closing (blind count → system compares to ledger balance)
    counted_cash_pt: Optional[int] = None    # what the cashier physically counted
    expected_cash_pt: Optional[int] = None  # SUM(ledger) snapshot at close
    variance_pt: Optional[int] = None       # counted − expected

    variance_approved_by: Optional[int] = None   # FK → users.id (manager)
    variance_reason: Optional[str] = None
    handover_to_session: Optional[int] = None    # FK → cashier_sessions.id

    # Read-only metadata (populated from join in repo)
    user_name: Optional[str] = None
    user_display_name: Optional[str] = None

    @property
    def is_closed(self) -> bool:
        return not self.is_open

    @property
    def station_label(self) -> str:
        """Arabic label for the station."""
        return {
            Station.ALL: "كل الطلبات",
            Station.COUNTER: "الكاونتر",
            Station.DELIVERY: "الديليفري",
        }.get(self.station, self.station.value)


@dataclass
class CashLedgerEntry:
    """
    Single append-only entry in the cash_ledger table.

    amount_pt is signed:
      Positive (+) = cash enters the drawer
      Negative (−) = cash leaves the drawer

    The DB enforces:
      - No UPDATE or DELETE (triggers RAISE ABORT)
      - Unique SALE_CASH per order_id
      - Unique DRIVER_REMITTANCE per trip_id
    """
    id: Optional[int]
    day_id: int
    session_id: int
    entry_type: LedgerEntryType
    amount_pt: int                    # signed piasters

    order_id: Optional[int] = None
    trip_id: Optional[int] = None
    expense_id: Optional[int] = None
    reverses_entry_id: Optional[int] = None

    actor_id: int = 0                 # FK → users.id (who triggered the entry)
    approved_by: Optional[int] = None # FK → users.id (manager, if required)
    reason: Optional[str] = None
    created_at: Optional[str] = None

    @property
    def amount_egp(self) -> float:
        """Convert piasters to EGP for display."""
        return self.amount_pt / 100.0

    @property
    def is_inflow(self) -> bool:
        return self.amount_pt > 0

    @property
    def is_outflow(self) -> bool:
        return self.amount_pt < 0
