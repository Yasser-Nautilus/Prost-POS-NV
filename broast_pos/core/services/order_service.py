"""
Order service — full order lifecycle management.

create → validate → save → amend → complete → cancel
All business rules enforced here. Never in repositories or UI.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, List, Optional, Tuple

from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.audit_repository import AuditRepository

if TYPE_CHECKING:
    from broast_pos.core.services.auth_service import AuthService
    from broast_pos.core.services.financial_service import FinancialService


class OrderService:
    """Business logic for the full order lifecycle."""

    def __init__(
        self,
        order_repo: Optional[OrderRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        auth_service: Optional["AuthService"] = None,
        financial_service: Optional["FinancialService"] = None,
    ) -> None:
        self._orders = order_repo or OrderRepository()
        self._audit = audit_repo or AuditRepository()
        self._auth = auth_service
        self._financial = financial_service

    # ------------------------------------------------------------------
    # Create order
    # ------------------------------------------------------------------

    def create_order(
        self,
        order: Order,
        cashier_id: int,
        cashier_name: str,
    ) -> Order:
        """Validate → assign invoice → save → return saved order.

        Caller must check shift is active before calling.
        Returns:
            Saved order with id and invoice_no set.
        Raises:
            ValueError: if validation fails or no active shift.
        """
        # Guard: shift must be active
        if self._financial is None:
            raise ValueError("Financial service not configured")
        shift = self._financial.ensure_shift_active()

        # Validate business rules
        self._validate_order(order)

        # Assign shift + invoice + cashier info
        order.shift_id = shift.id
        order.invoice_no = self._financial.get_next_invoice_number()
        order.created_by_id = cashier_id
        order.created_by_name = cashier_name
        order.status = OrderStatus.NEW

        # Compute totals
        order.subtotal = sum(item.total_price for item in order.items)
        self._compute_total(order)

        # Delivery (online) = auto-paid at creation
        if (order.order_type == OrderType.DELIVERY
                and order.payment_method == PaymentMethod.ONLINE):
            order.is_paid = True

        # Persist
        saved = self._orders.save(order)
        return saved

    # ------------------------------------------------------------------
    # Amend order (edit saved order)
    # ------------------------------------------------------------------

    def amend_order(
        self,
        order_id: int,
        added_items: List[OrderItem],
        removed_items: List[OrderItem],
        manager_pin: Optional[str] = None,
    ) -> Order:
        """Edit a saved order — add or remove items.

        Adding items: free.
        Removing items: requires manager PIN.

        Returns:
            Updated order.
        Raises:
            ValueError: if order not found or not editable.
            PermissionError: if removing items without valid manager PIN.
        """
        order = self._orders.get_by_id(order_id)
        if order is None:
            raise ValueError("الطلب غير موجود")

        if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            raise ValueError("لا يمكن تعديل طلب مكتمل أو ملغي")

        # Removing items requires manager override
        if removed_items:
            if not manager_pin:
                raise PermissionError("يجب إدخال PIN المدير لحذف عنصر")
            manager = self._verify_manager_pin(manager_pin)
            # Audit each removal
            for item in removed_items:
                self._audit.log(
                    event_type="item_removed",
                    user_id=manager.id,
                    user_name=manager.display_name,
                    order_id=order_id,
                    details={
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                    },
                )

        # Apply changes
        # Remove items from order
        remove_ids = {i.product_id for i in removed_items}
        order.items = [i for i in order.items if i.product_id not in remove_ids]

        # Add new items (prices locked at this moment)
        order.items.extend(added_items)

        # Recalculate totals
        order.subtotal = sum(item.total_price for item in order.items)
        self._compute_total(order)

        # Persist
        return self._orders.save(order)

    # ------------------------------------------------------------------
    # Complete order (payment)
    # ------------------------------------------------------------------

    def complete_order(
        self,
        order_id: int,
        payment_method: PaymentMethod,
        amount_received: float = 0.0,
    ) -> Order:
        """Record payment and mark order as completed.

        Raises:
            ValueError: if order not found, already completed, or invalid payment.
        """
        order = self._orders.get_by_id(order_id)
        if order is None:
            raise ValueError("الطلب غير موجود")

        if order.status == OrderStatus.COMPLETED:
            raise ValueError("الطلب مكتمل بالفعل")

        if order.status == OrderStatus.CANCELLED:
            raise ValueError("لا يمكن دفع طلب ملغي")

        # Visa NOT allowed for delivery
        if (order.order_type == OrderType.DELIVERY
                and payment_method == PaymentMethod.VISA):
            raise ValueError("الفيزا غير متاحة لطلبات التوصيل")

        order.payment_method = payment_method
        order.is_paid = True

        if payment_method == PaymentMethod.CASH:
            order.amount_paid = amount_received
            order.change_given = max(0.0, amount_received - order.total)
        else:
            # Visa / Online: paid = total, change = 0
            order.amount_paid = order.total
            order.change_given = 0.0

        order.status = OrderStatus.COMPLETED
        return self._orders.save(order)

    # ------------------------------------------------------------------
    # Cancel order
    # ------------------------------------------------------------------

    def cancel_order(
        self,
        order_id: int,
        manager_pin: Optional[str] = None,
        reason: str = "",
    ) -> Order:
        """Cancel an order — requires manager PIN + reason.

        Raises:
            ValueError: if order not found or not cancellable.
            PermissionError: if PIN is invalid.
        """
        order = self._orders.get_by_id(order_id)
        if order is None:
            raise ValueError("الطلب غير موجود")

        if order.status == OrderStatus.COMPLETED:
            raise ValueError("لا يمكن إلغاء طلب مكتمل")

        if order.status == OrderStatus.CANCELLED:
            raise ValueError("الطلب ملغي بالفعل")

        # Block cancellation of delivery in transit
        if order.status == OrderStatus.OUT_FOR_DELIVERY:
            raise ValueError("الطلب خارج للتوصيل - لا يمكن إلغاؤه")

        manager = self._verify_manager_pin(manager_pin)

        order.status = OrderStatus.CANCELLED
        order.cancelled_by_id = manager.id
        order.cancelled_by_name = manager.display_name
        order.cancel_reason = reason

        saved = self._orders.save(order)

        # Audit trail
        self._audit.log(
            event_type="order_cancelled",
            user_id=manager.id,
            user_name=manager.display_name,
            order_id=order_id,
            details={"reason": reason, "total": order.total},
        )

        return saved

    # ------------------------------------------------------------------
    # Apply discount
    # ------------------------------------------------------------------

    def apply_discount(
        self,
        order: Order,
        value: float,
        discount_type: str,
        manager_pin: Optional[str] = None,
    ) -> Order:
        """Apply discount to order — requires manager PIN.

        Args:
            value: discount amount (flat EGP) or percentage (0-100).
            discount_type: "flat" or "percent".

        Raises:
            PermissionError: if PIN is invalid.
            ValueError: if discount_type is invalid.
        """
        manager = self._verify_manager_pin(manager_pin)

        if discount_type == "flat":
            order.discount_amount = min(value, order.subtotal)
        elif discount_type == "percent":
            capped = min(value, 100.0)
            order.discount_amount = order.subtotal * (capped / 100.0)
        else:
            raise ValueError("نوع الخصم غير صحيح — يجب أن يكون 'flat' أو 'percent'")

        order.discount_type = discount_type
        self._compute_total(order)

        saved = self._orders.save(order)

        # Audit trail
        self._audit.log(
            event_type="discount_applied",
            user_id=manager.id,
            user_name=manager.display_name,
            order_id=order.id,
            details={
                "discount_type": discount_type,
                "value": value,
                "discount_amount": order.discount_amount,
            },
        )

        return saved

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_order_by_id(self, order_id: int) -> Optional[Order]:
        """Fetch a single order."""
        return self._orders.get_by_id(order_id)

    def get_order_by_table(self, table_number: int) -> Optional[Order]:
        """Load the active dine-in order for a table."""
        return self._orders.get_by_table(table_number)

    def get_active_orders(self) -> List[Order]:
        """All non-completed, non-cancelled orders."""
        return self._orders.get_active_orders()

    def get_active_by_type(self, order_type: OrderType) -> List[Order]:
        """Active orders filtered by type."""
        return self._orders.get_active_by_type(order_type)

    def get_unassigned_deliveries(self) -> List[Order]:
        """Delivery orders not yet assigned to a driver."""
        return self._orders.get_unassigned_deliveries()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_order(self, order: Order) -> None:
        """Enforce business rules before saving."""
        if not order.items:
            raise ValueError("يجب إضافة عنصر واحد على الأقل")

        if order.order_type == OrderType.DINE_IN and not order.table_no:
            raise ValueError("يجب اختيار رقم الطاولة")

        if order.order_type == OrderType.DELIVERY:
            if not order.customer_phone:
                raise ValueError("يجب إدخال رقم الهاتف للتوصيل")
            if not order.customer_address:
                raise ValueError("يجب إدخال العنوان للتوصيل")

        if order.order_type == OrderType.PICKUP:
            if not order.customer_phone:
                raise ValueError("يجب إدخال رقم الهاتف للاستلام")

    def _compute_total(self, order: Order) -> None:
        """total = subtotal + service - discount + delivery_fee"""
        order.total = (
            order.subtotal
            + order.service_amount
            - order.discount_amount
            + order.delivery_fee
        )

    def _verify_manager_pin(self, pin: Optional[str]):
        """Hash PIN and verify against a manager/admin user.

        Returns the manager User object.
        Raises PermissionError if invalid.
        """
        if self._auth is None:
            raise PermissionError("Auth service not configured")
        if not pin:
            current_user = self._auth.get_current_user()
            if current_user and current_user.is_manager_or_above():
                return current_user
            raise PermissionError("يجب إدخال رمز PIN للمدير")
        manager = self._auth.verify_pin(pin)
        if manager is None:
            raise PermissionError("PIN غير صحيح أو ليس لديك صلاحية")
        return manager
