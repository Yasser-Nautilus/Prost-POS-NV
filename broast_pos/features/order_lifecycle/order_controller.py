"""
Order lifecycle controller — orchestrates the full order flow.

Connects the UI layer to services + printing infrastructure.
This is the **single entry point** that views call for all order
operations. Views NEVER call services directly.

Flow: UI → OrderController → OrderService + PrintTriggers + FinancialService
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.auth_service import AuthService
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers
from broast_pos.features.order_lifecycle.amendment_tracker import AmendmentTracker

logger = logging.getLogger(__name__)


@dataclass
class ConfirmResult:
    """Result of confirm_order() — typed instead of string-encoded."""

    invoice_no: int
    needs_immediate_payment: bool = False
    order_id: Optional[int] = None


class OrderController:
    """Orchestrates the full order lifecycle.

    Manages in-memory order state, parked orders, validation,
    and coordinates save → print → payment flows.
    """

    def __init__(
        self,
        order_service: OrderService,
        financial_service: FinancialService,
        auth_service: AuthService,
        print_triggers: PrintTriggers,
        cashier_slot: int = 1,
    ) -> None:
        self._order_svc = order_service
        self._financial_svc = financial_service
        self._auth_svc = auth_service
        self._print = print_triggers
        self._cashier_slot = cashier_slot

        # In-memory state
        self._current_order: Optional[Order] = None
        self._parked_orders: List[Order] = []
        self._occupied_tables: Dict[int, str] = {}  # table_no → order_ref
        self._amendment_tracker = AmendmentTracker()

        # Callbacks for UI updates
        self._on_order_changed: Optional[Callable] = None
        self._on_parked_changed: Optional[Callable] = None
        self._on_table_state_changed: Optional[Callable] = None

    # ------------------------------------------------------------------
    # Callback registration (UI binds to these)
    # ------------------------------------------------------------------

    def on_order_changed(self, callback: Callable) -> None:
        """Register callback when current order changes."""
        self._on_order_changed = callback

    def on_parked_changed(self, callback: Callable) -> None:
        """Register callback when parked orders list changes."""
        self._on_parked_changed = callback

    def on_table_state_changed(self, callback: Callable) -> None:
        """Register callback when table occupancy changes."""
        self._on_table_state_changed = callback

    # ------------------------------------------------------------------
    # 1. Create Order (In-Memory)
    # ------------------------------------------------------------------

    def new_order(self, order_type: str = "dine_in") -> Order:
        """Start a new empty order in memory.

        Args:
            order_type: One of 'dine_in', 'takeaway', 'delivery', 'pickup'.

        Returns:
            The new Order object.
        """
        order = Order(
            order_type=OrderType(order_type),
            status=OrderStatus.NEW,
            cashier_slot=self._cashier_slot,
        )
        self._current_order = order
        self._notify_order_changed()
        logger.info("New %s order created in memory", order_type)
        return order

    def add_item(
        self,
        product_id: int,
        product_name: str,
        unit_price: float,
        quantity: int = 1,
        notes: str = "",
    ) -> None:
        """Add an item to the current in-memory order.

        If the product already exists, increment quantity.
        """
        if self._current_order is None:
            return

        # Check if already in order
        for item in self._current_order.items:
            if item.product_id == product_id and item.notes == notes:
                item.quantity += quantity
                self._recalc_totals()
                self._notify_order_changed()
                return

        item = OrderItem(
            product_id=product_id,
            product_name=product_name,
            unit_price=unit_price,
            quantity=quantity,
            notes=notes,
        )
        self._current_order.items.append(item)
        self._recalc_totals()
        self._notify_order_changed()

    def change_quantity(self, index: int, delta: int) -> None:
        """Change item quantity by delta (+/-)."""
        if self._current_order is None:
            return
        if 0 <= index < len(self._current_order.items):
            self._current_order.items[index].quantity += delta
            if self._current_order.items[index].quantity <= 0:
                self._current_order.items.pop(index)
            self._recalc_totals()
            self._notify_order_changed()

    def remove_item(self, index: int, manager_pin: Optional[str] = None) -> Tuple[bool, str]:
        """Remove item from order.

        If order is saved (has ID), requires manager PIN.

        Returns:
            (success, message)
        """
        if self._current_order is None:
            return False, "لا يوجد طلب حالي"

        if 0 <= index < len(self._current_order.items):
            # If order is already saved, require manager PIN
            if self._current_order.id is not None:
                if not manager_pin:
                    return False, "يتطلب صلاحية مدير"
                manager = self._auth_svc.verify_pin(manager_pin)
                if manager is None:
                    return False, "رمز PIN غير صحيح"

            self._current_order.items.pop(index)
            self._recalc_totals()
            self._notify_order_changed()
            return True, "تم الحذف"
        return False, "عنصر غير موجود"

    def set_item_note(self, index: int, note: str) -> None:
        """Set special instructions for an item."""
        if self._current_order and 0 <= index < len(self._current_order.items):
            self._current_order.items[index].notes = note

    def set_table(self, table_number: int) -> None:
        """Set table number for dine-in orders."""
        if self._current_order:
            self._current_order.table_no = table_number

    def set_customer_info(
        self,
        customer_id: Optional[int] = None,
        phone: str = "",
        name: str = "",
        address: str = "",
        zone: str = "",
        delivery_fee: float = 0.0,
    ) -> None:
        """Set customer info for delivery/pickup orders."""
        if self._current_order:
            self._current_order.customer_id = customer_id
            self._current_order.customer_phone = phone
            self._current_order.customer_name = name
            self._current_order.customer_address = address
            self._current_order.customer_zone = zone
            self._current_order.delivery_fee = delivery_fee

    # ------------------------------------------------------------------
    # 2. Parked Orders
    # ------------------------------------------------------------------

    def park_current(self) -> bool:
        """Park the current order and clear the workspace."""
        if self._current_order is None or not self._current_order.items:
            return False

        # Track table for in-memory occupancy
        if (self._current_order.order_type == OrderType.DINE_IN
                and self._current_order.table_no):
            self._occupied_tables[self._current_order.table_no] = "parked"

        self._parked_orders.append(self._current_order)
        self._current_order = None
        self._notify_parked_changed()
        self._notify_order_changed()
        self._notify_table_changed()
        return True

    def resume_parked(self, index: int) -> bool:
        """Resume a parked order, parking the current one first if needed."""
        if index < 0 or index >= len(self._parked_orders):
            return False

        # Park current if it has items
        if self._current_order and self._current_order.items:
            self._parked_orders.append(self._current_order)

        self._current_order = self._parked_orders.pop(index)

        # Remove from occupied tables tracking
        if (self._current_order.order_type == OrderType.DINE_IN
                and self._current_order.table_no
                and self._current_order.table_no in self._occupied_tables):
            del self._occupied_tables[self._current_order.table_no]

        self._notify_parked_changed()
        self._notify_order_changed()
        self._notify_table_changed()
        return True

    def get_parked_orders(self) -> List[Order]:
        """Return list of parked orders (for tab bar display)."""
        return list(self._parked_orders)

    # ------------------------------------------------------------------
    # 3. Validate & Save ("Confirm" button)
    # ------------------------------------------------------------------

    def confirm_order(
        self,
        cashier_id: int,
        cashier_name: str = "",
    ) -> Tuple[bool, Any]:
        """Validate, save, and print kitchen ticket.

        Args:
            cashier_id: ID of the logged-in cashier.
            cashier_name: Display name of the cashier.

        Returns:
            (success, ConfirmResult or error message)
        """
        if self._current_order is None:
            return False, "لا يوجد طلب حالي"

        if not self._current_order.items:
            return False, "يجب إضافة منتج واحد على الأقل"

        # Validate by type
        order = self._current_order
        if order.order_type == OrderType.DINE_IN and not order.table_no:
            return False, "يجب اختيار رقم الطاولة"
        if order.order_type == OrderType.DELIVERY:
            if not order.customer_phone:
                return False, "يجب إدخال رقم الهاتف"
            if not order.customer_address:
                return False, "يجب إدخال العنوان"
        if order.order_type == OrderType.PICKUP:
            if not order.customer_phone:
                return False, "يجب إدخال رقم الهاتف"

        self._recalc_totals()

        # Save via service (service handles invoice assignment internally)
        try:
            saved = self._order_svc.create_order(order, cashier_id, cashier_name)
        except Exception as exc:
            logger.error("Order save failed: %s", exc)
            return False, f"فشل في حفظ الطلب: {exc}"

        # Print kitchen ticket (silent — never blocks)
        order_dict = self._order_to_dict(saved)
        self._print.on_order_created(order_dict)

        # Handle auto-payment for online delivery
        if (saved.order_type == OrderType.DELIVERY
                and saved.payment_method == PaymentMethod.ONLINE):
            try:
                self._order_svc.complete_order(
                    saved.id,
                    PaymentMethod.ONLINE,
                    saved.total,
                )
            except Exception:
                pass  # Log but don't fail the save

        # Mark table as DB-occupied
        if saved.order_type == OrderType.DINE_IN and saved.table_no:
            self._occupied_tables[saved.table_no] = f"#{saved.invoice_no}"
            self._notify_table_changed()

        # Clear current order
        self._current_order = None
        self._notify_order_changed()

        logger.info("Order #%d confirmed and saved", saved.invoice_no)

        return True, ConfirmResult(
            invoice_no=saved.invoice_no,
            needs_immediate_payment=(saved.order_type == OrderType.TAKEAWAY),
            order_id=saved.id,
        )

    # ------------------------------------------------------------------
    # 4. Payment Flow
    # ------------------------------------------------------------------

    def complete_payment(
        self,
        order_id: int,
        payment_method: str,
        amount_paid: float,
    ) -> Tuple[bool, str]:
        """Process payment and print receipt.

        Args:
            order_id: The saved order ID.
            payment_method: 'cash', 'visa', or 'online'.
            amount_paid: Amount received from customer.

        Returns:
            (success, message)
        """
        try:
            method = PaymentMethod(payment_method)
            completed = self._order_svc.complete_order(
                order_id, method, amount_paid
            )
        except Exception as exc:
            return False, f"فشل في الدفع: {exc}"

        # Print customer receipt
        order_dict = self._order_to_dict(completed)
        order_dict["amount_paid"] = amount_paid
        order_dict["change_given"] = max(0, amount_paid - completed.total)
        self._print.on_order_completed(order_dict, self._cashier_slot)

        # Free table if dine-in
        if completed.order_type == OrderType.DINE_IN and completed.table_no:
            self._occupied_tables.pop(completed.table_no, None)
            self._notify_table_changed()

        logger.info("Payment completed for order #%s", completed.invoice_no)
        return True, "تم الدفع بنجاح"

    # ------------------------------------------------------------------
    # 5. Edit Saved Order (Amendment)
    # ------------------------------------------------------------------

    def load_order(self, order_id: int) -> Optional[Order]:
        """Load a saved order for editing/payment.

        Also takes a snapshot for amendment tracking.
        """
        order = self._order_svc.get_order_by_id(order_id)
        if order:
            self._current_order = order
            self._amendment_tracker.snapshot(order.items)
            self._notify_order_changed()
        return order

    def load_order_by_table(self, table_number: int) -> Optional[Order]:
        """Load an active dine-in order by table number.

        Also takes a snapshot for amendment tracking.
        """
        order = self._order_svc.get_order_by_table(table_number)
        if order:
            self._current_order = order
            self._amendment_tracker.snapshot(order.items)
            self._notify_order_changed()
        return order

    def save_amendment(self, manager_pin: Optional[str] = None) -> Tuple[bool, str]:
        """Save amendments to an existing order and print amendment ticket.

        Uses the AmendmentTracker to detect added/removed items.
        Removing items requires manager PIN.

        Returns:
            (success, message)
        """
        if self._current_order is None or self._current_order.id is None:
            return False, "لا يوجد طلب محفوظ للتعديل"

        # Compute diff from snapshot
        changes = self._amendment_tracker.diff(self._current_order.items)
        if not changes:
            return True, "لا توجد تغييرات"

        # Split into added and removed OrderItems
        added_items: List[OrderItem] = []
        removed_items: List[OrderItem] = []
        for change in changes:
            item = OrderItem(
                product_id=0,  # ID resolved by service from name lookup
                product_name=change["product_name"],
                unit_price=0,
                quantity=change["quantity"],
            )
            if change["action"] == "added":
                added_items.append(item)
            elif change["action"] == "removed":
                removed_items.append(item)

        try:
            self._order_svc.amend_order(
                self._current_order.id,
                added_items,
                removed_items,
                manager_pin,
            )
        except PermissionError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"فشل في حفظ التعديل: {exc}"

        # Print amendment ticket
        order_dict = self._order_to_dict(self._current_order)
        self._print.on_order_amended(order_dict, changes)

        # Clear tracker
        self._amendment_tracker.clear()

        logger.info("Amendment saved for order #%s", self._current_order.invoice_no)
        return True, "تم حفظ التعديل"

    # ------------------------------------------------------------------
    # 6. Cancel Order
    # ------------------------------------------------------------------

    def cancel_order(
        self,
        order_id: int,
        manager_pin: str,
        reason: str = "",
    ) -> Tuple[bool, str]:
        """Cancel an order (requires manager PIN).

        Returns:
            (success, message)
        """
        try:
            cancelled = self._order_svc.cancel_order(
                order_id, manager_pin, reason
            )
        except Exception as exc:
            return False, str(exc)

        # Free table if dine-in
        if cancelled.order_type == OrderType.DINE_IN and cancelled.table_no:
            self._occupied_tables.pop(cancelled.table_no, None)
            self._notify_table_changed()

        # Clear current if it was this order
        if self._current_order and self._current_order.id == order_id:
            self._current_order = None
            self._notify_order_changed()

        return True, "تم إلغاء الطلب"

    # ------------------------------------------------------------------
    # 7. Discount
    # ------------------------------------------------------------------

    def apply_discount(
        self,
        value: float,
        discount_type: str,
        manager_pin: str,
    ) -> Tuple[bool, str]:
        """Apply discount to the current order (requires manager PIN).

        Args:
            value: Discount amount (flat EGP) or percentage (0-100).
            discount_type: "flat" or "percent".
            manager_pin: Manager/admin PIN for authorization.
        """
        if self._current_order is None or self._current_order.id is None:
            return False, "لا يوجد طلب محفوظ"

        try:
            saved = self._order_svc.apply_discount(
                self._current_order, value, discount_type, manager_pin
            )
            self._current_order = saved
            self._notify_order_changed()
        except (PermissionError, ValueError) as exc:
            return False, str(exc)

        label = f"{value}%" if discount_type == "percent" else f"{value} ج.م"
        return True, f"تم تطبيق خصم {label}"

    # ------------------------------------------------------------------
    # 8. Table State
    # ------------------------------------------------------------------

    def get_table_state(self) -> Dict[int, str]:
        """Return occupied tables map: {table_no: order_ref}.

        Merges in-memory parked orders with DB-active orders.
        """
        # Start with DB active dine-in orders
        state = dict(self._occupied_tables)

        # Add from DB (active dine-in with tables)
        try:
            active = self._order_svc.get_active_by_type(OrderType.DINE_IN)
            for order in active:
                if order.table_no:
                    state[order.table_no] = f"#{order.invoice_no}"
        except Exception:
            pass

        return state

    def is_table_occupied(self, table_number: int) -> bool:
        """Check if a table is occupied (in-memory or DB)."""
        return table_number in self.get_table_state()

    # ------------------------------------------------------------------
    # Queries (for tracking view)
    # ------------------------------------------------------------------

    def get_active_orders(self) -> List[Order]:
        """Return all active orders."""
        return self._order_svc.get_active_orders()

    def get_active_by_type(self, order_type: str) -> List[Order]:
        """Return active orders filtered by type."""
        return self._order_svc.get_active_by_type(OrderType(order_type))

    @property
    def current_order(self) -> Optional[Order]:
        """The currently active order (may be unsaved)."""
        return self._current_order

    # ------------------------------------------------------------------
    # Reprint
    # ------------------------------------------------------------------

    def reprint_receipt(self, order_id: int) -> bool:
        """Reprint a customer receipt for a completed order."""
        order = self._order_svc.get_order_by_id(order_id)
        if order is None:
            return False
        order_dict = self._order_to_dict(order)
        return self._print.reprint_receipt(order_dict, self._cashier_slot)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recalc_totals(self) -> None:
        """Recalculate current order totals."""
        if self._current_order is None:
            return
        order = self._current_order
        subtotal = sum(i.unit_price * i.quantity for i in order.items)
        order.subtotal = subtotal
        # Service charge and total are computed by the Order model

    def _order_to_dict(self, order: Order) -> Dict[str, Any]:
        """Convert Order to dict for printing templates."""
        return {
            "invoice_no": order.invoice_no,
            "order_type": order.order_type.value if order.order_type else "dine_in",
            "table_no": order.table_no or "",
            "cashier_name": order.created_by_name or "",
            "cashier_slot": order.cashier_slot or self._cashier_slot,
            "customer_name": order.customer_name or "",
            "customer_phone": order.customer_phone or "",
            "customer_address": order.customer_address or "",
            "customer_zone": order.customer_zone or "",
            "driver_name": getattr(order, "driver_name", ""),
            "delivery_fee": order.delivery_fee or 0,
            "service_amount": getattr(order, "service_amount", 0),
            "discount_amount": order.discount_amount or 0,
            "total": order.total or 0,
            "payment_method": order.payment_method.value if order.payment_method else "",
            "amount_paid": order.amount_paid or 0,
            "change_given": order.change_given or 0,
            "items": [
                {
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.unit_price * item.quantity,
                    "notes": item.notes or "",
                }
                for item in order.items
            ],
        }

    def _notify_order_changed(self) -> None:
        if self._on_order_changed:
            self._on_order_changed()

    def _notify_parked_changed(self) -> None:
        if self._on_parked_changed:
            self._on_parked_changed()

    def _notify_table_changed(self) -> None:
        if self._on_table_state_changed:
            self._on_table_state_changed()
