"""
Order service — full order lifecycle management.

create → validate → save → amend → complete → cancel
All business rules enforced here. Never in repositories or UI.

Status transitions are centralized through change_order_status() which
atomically updates the order AND inserts an OrderStatusHistory record.
"""

from __future__ import annotations

import hashlib
import datetime
from typing import TYPE_CHECKING, List, Optional, Tuple

from broast_pos.core.models.audit import AuditEventType
from broast_pos.core.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    PaymentMethod,
)
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.order_status_history_repository import OrderStatusHistoryRepository
from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.policies.discount import compute_discount

if TYPE_CHECKING:
    from broast_pos.core.services.auth_service import AuthService
    from broast_pos.core.services.financial_service import FinancialService
    from broast_pos.core.services.cashier_session_service import CashierSessionService

# Lazy imports to avoid circular deps — loaded only when ledger is wired in.
_LEDGER_IMPORTS_DONE = False

# ---------------------------------------------------------------------------
# Valid status transitions — the only allowed forward progressions.
# ---------------------------------------------------------------------------
# Common transitions valid for ALL order types
_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW:              {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING:        {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY:            {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED:        {OrderStatus.COMPLETED},
    OrderStatus.COMPLETED:        set(),
    OrderStatus.CANCELLED:        set(),
}

# Extra transitions allowed ONLY for delivery orders (B-06).
# A delivery order can go to OUT_FOR_DELIVERY from any pre-dispatch state.
_DELIVERY_EXTRA: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW:      {OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.PREPARING:{OrderStatus.OUT_FOR_DELIVERY},
    OrderStatus.READY:    {OrderStatus.OUT_FOR_DELIVERY},
}


def _allowed_targets(order: Order) -> set[OrderStatus]:
    """Return the set of valid target statuses for this order's current state."""
    base = set(_ALLOWED_TRANSITIONS.get(order.status, set()))
    if order.order_type == OrderType.DELIVERY:
        base |= _DELIVERY_EXTRA.get(order.status, set())
    return base


class OrderService:
    """Business logic for the full order lifecycle."""

    def __init__(
        self,
        order_repo: Optional[OrderRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
        auth_service: Optional["AuthService"] = None,
        financial_service: Optional["FinancialService"] = None,
        payment_coordinator: Optional[object] = None,
        status_history_repo: Optional[OrderStatusHistoryRepository] = None,
        audit_service: Optional[AuditService] = None,
        session_service: Optional["CashierSessionService"] = None,
        ledger_repo=None,           # CashLedgerRepository (Phase 3)
        cashier_session_repo=None,  # CashierSessionRepository (Phase 3)
    ) -> None:
        self._orders = order_repo or OrderRepository()
        self._audit = audit_repo or AuditRepository()
        self._auth = auth_service
        self._financial = financial_service
        self._session_svc = session_service   # FR-SES-3: station routing
        self._status_history = status_history_repo or OrderStatusHistoryRepository()
        # B-03: _audit_svc is ALWAYS an AuditService — never None, never bypassed.
        self._audit_svc: AuditService = audit_service or AuditService(self._audit)
        if payment_coordinator is None:
            from broast_pos.features.order_lifecycle.payment_coordinator import PaymentCoordinator
            payment_coordinator = PaymentCoordinator()
        self._payments = payment_coordinator
        # Phase 3: cash ledger wiring (optional — skipped if not injected)
        self._ledger = ledger_repo      # CashLedgerRepository | None
        self._cashier_sessions = cashier_session_repo  # CashierSessionRepository | None

    # ------------------------------------------------------------------
    # Create order
    # ------------------------------------------------------------------

    def create_order(
        self,
        order: Order,
        cashier_id: int,
        cashier_name: str,
    ) -> Order:
        """Validate → assign invoice → save → record initial status history → return.

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

        # FR-SES-3: station routing (service layer, not UI)
        # Only enforced when CashierSessionService is wired in.
        if self._session_svc is not None:
            self._enforce_station_routing(
                order=order,
                day_id=shift.id,
                cashier_id=cashier_id,
            )

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

        # B-02: Delivery orders MUST have a payment_method — default to CASH.
        # This closes the bug where NULL payment_method caused settle_trip
        # to always report cash_collected = 0.
        if order.order_type == OrderType.DELIVERY:
            if order.payment_method is None:
                order.payment_method = PaymentMethod.CASH
            if order.payment_method == PaymentMethod.ONLINE:
                # Pre-paid online: mark as paid atomically inside this save.
                # No secondary complete_order() call is required or allowed.
                order.is_paid = True
                order.amount_paid = order.total
                order.paid_at = datetime.datetime.now().isoformat()

        # Persist
        saved = self._orders.save(order)

        # Record initial status history
        try:
            self._status_history.record_transition(
                order_id=saved.id,
                old_status=None,
                new_status=OrderStatus.NEW.value,
                changed_by_id=cashier_id,
                changed_by_name=cashier_name,
            )
        except Exception:
            pass  # History failure must not block order creation

        return saved

    # ------------------------------------------------------------------
    # Centralized status transition (THE authoritative status change path)
    # ------------------------------------------------------------------

    def change_order_status(
        self,
        order_id: int,
        new_status: OrderStatus,
        changed_by_id: Optional[int] = None,
        changed_by_name: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Order:
        """Validate, apply, and record a status transition.

        This is the ONLY correct way to change an order's status after creation.
        It guarantees that every transition is:
          1. Validated against the allowed transition map (order-type-aware).
          2. Persisted to the orders table.
          3. Recorded in order_status_history.

        Args:
            order_id: Target order.
            new_status: Desired status.
            changed_by_id: Actor's user ID (optional).
            changed_by_name: Actor's display name (optional).
            reason: Optional explanation (required for CANCELLED).

        Raises:
            ValueError: if order not found or transition is invalid.
        """
        order = self._orders.get_by_id(order_id)
        if order is None:
            raise ValueError(f"الطلب #{order_id} غير موجود")

        old_status = order.status
        # B-06: use order-type-aware transition check
        allowed = _allowed_targets(order)
        if new_status not in allowed:
            raise ValueError(
                f"لا يمكن الانتقال من '{old_status.value}' إلى '{new_status.value}'"
                f" (نوع الطلب: {order.order_type.value})"
            )

        order.status = new_status
        saved = self._orders.save(order)

        # Record history — log on failure, never silently ignore
        try:
            self._status_history.record_transition(
                order_id=order_id,
                old_status=old_status.value,
                new_status=new_status.value,
                changed_by_id=changed_by_id,
                changed_by_name=changed_by_name,
                reason=reason,
            )
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "Failed to record status history for order #%s: %s", order_id, exc
            )

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
            # B-03: Audit each removal through AuditService (correct path)
            for item in removed_items:
                self._audit_svc.log_from_user(
                    event_type=AuditEventType.ITEM_REMOVED,
                    actor=manager,
                    order_id=order_id,
                    entity_type="order",
                    entity_id=order_id,
                    action=f"حذف عنصر: {item.product_name} ×{item.quantity}",
                    details={
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
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
        actor_id: Optional[int] = None,
        actor_name: str = "نظام",
    ) -> Order:
        """Record payment and mark order as completed.

        Args:
            actor_id, actor_name: The cashier (or system) that triggered completion.
                Defaults to "نظام" for backward-compat, but callers should pass real actor.
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

        payment = self._payments.calculate(
            total=order.total,
            method=payment_method,
            amount_paid=amount_received,
            order_type=order.order_type,
        )
        if not payment.is_valid:
            raise ValueError(payment.error)

        order.payment_method = payment.method
        order.amount_paid = payment.amount_paid
        order.change_given = payment.change_given
        order.is_paid = True
        order.paid_at = datetime.datetime.now().isoformat()

        old_status = order.status
        order.status = OrderStatus.COMPLETED
        saved = self._orders.save(order)

        # Phase 3: Create SALE_CASH ledger entry for cash payments (ADR-1).
        # Non-cash (visa/online) do NOT enter the physical drawer (FR-CASH-4).
        # This runs inside the same request; commit is handled by the caller/bridge.
        if self._ledger is not None and payment_method == PaymentMethod.CASH:
            self._create_sale_cash_entry(
                order=saved,
                actor_id=actor_id,
                shift_id=saved.shift_id,
                cashier_id=actor_id,
            )

        # Record status history
        try:
            self._status_history.record_transition(
                order_id=order_id,
                old_status=old_status.value,
                new_status=OrderStatus.COMPLETED.value,
                changed_by_id=actor_id,
                changed_by_name=actor_name,
            )
        except Exception:
            pass

        return saved

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

        old_status = order.status
        order.status = OrderStatus.CANCELLED
        order.cancelled_by_id = manager.id
        order.cancelled_by_name = manager.display_name
        order.cancel_reason = reason
        order.cancelled_at = datetime.datetime.now().isoformat()

        saved = self._orders.save(order)

        # Record status history
        try:
            self._status_history.record_transition(
                order_id=order_id,
                old_status=old_status.value,
                new_status=OrderStatus.CANCELLED.value,
                changed_by_id=manager.id,
                changed_by_name=manager.display_name,
                reason=reason,
            )
        except Exception:
            pass

        # B-03: Audit trail — always via AuditService (never direct repo)
        self._audit_svc.log(
            event_type=AuditEventType.ORDER_CANCELLED,
            user_id=manager.id,
            user_name=manager.display_name or manager.username or "",
            order_id=order_id,
            entity_type="order",
            entity_id=order_id,
            action="إلغاء الطلب",
            reason=reason,
            before={"status": old_status.value, "total": order.total},
            after={"status": OrderStatus.CANCELLED.value},
            details={"reason": reason},
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
            ValueError: if discount_type is invalid, value ≤ 0, flat > subtotal,
                        or percent > 100.
        """
        manager = self._verify_manager_pin(manager_pin)

        before_total = order.total
        before_discount = order.discount_amount

        # B-05: single validated policy — no more silent capping, no negatives
        order.discount_amount = compute_discount(
            subtotal=order.subtotal,
            value=value,
            kind=discount_type,
        )
        order.discount_type = discount_type
        self._compute_total(order)

        saved = self._orders.save(order)

        # B-03: Audit trail — always via AuditService
        self._audit_svc.log(
            event_type=AuditEventType.DISCOUNT_APPLIED,
            user_id=manager.id,
            user_name=manager.display_name or manager.username or "",
            order_id=order.id,
            entity_type="order",
            entity_id=order.id,
            action=f"تطبيق خصم {discount_type}: {value}",
            before={"discount_amount": before_discount, "total": before_total},
            after={"discount_amount": order.discount_amount, "total": order.total},
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

    def get_order_status_history(self, order_id: int) -> list:
        """Return the complete status timeline for an order."""
        return self._status_history.get_for_order(order_id)

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

    # ------------------------------------------------------------------
    # FR-SES-3: Station routing (service-layer enforcement, ADR-4)
    # ------------------------------------------------------------------

    def _enforce_station_routing(
        self,
        order: Order,
        day_id: int,
        cashier_id: int,
    ) -> None:
        """
        Enforce station routing rules (FR-SES-3):
          COUNTER  → dine_in, takeaway, pickup only
          DELIVERY → delivery only
          ALL      → any order type

        If no open session found for this cashier (legacy / no-session mode),
        routing is skipped gracefully to avoid breaking existing operations.
        """
        from broast_pos.core.models.cashier_session import Station

        all_sessions = self._session_svc.get_active_sessions(day_id)
        cashier_session = next(
            (s for s in all_sessions if s.user_id == cashier_id), None
        )

        if cashier_session is None:
            return  # No session: skip (legacy/migration mode)

        station = cashier_session.station
        order_type = order.order_type

        if station == Station.ALL:
            return  # ALL station: any order type allowed

        if station == Station.COUNTER:
            if order_type == OrderType.DELIVERY:
                raise ValueError(
                    "محطة الكاونتر لا يمكنها إنشاء طلبات ديليفري. "
                    "استخدم محطة الديليفري أو تواصل مع المدير."
                )

        if station == Station.DELIVERY:
            if order_type in (OrderType.DINE_IN, OrderType.TAKEAWAY, OrderType.PICKUP):
                raise ValueError(
                    f"محطة الديليفري لا يمكنها إنشاء طلبات {order_type.value}. "
                    "استخدم محطة الكاونتر أو 'كل الطلبات'."
                )

    # ------------------------------------------------------------------
    # Phase 3: Cash ledger helpers
    # ------------------------------------------------------------------

    def _create_sale_cash_entry(
        self,
        order,
        actor_id: Optional[int],
        shift_id: int,
        cashier_id: Optional[int],
    ) -> None:
        """
        Append a SALE_CASH entry to the active cashier session's ledger.

        Strategy:
          1. If CashierSessionRepository is wired in, look up the open session
             for this cashier on this shift (day_id = shift_id).
          2. If no session found (legacy mode), skip silently.
          3. Amount is in PIASTERS = round(total * 100).

        Called only for CASH payments from complete_order().
        """
        from broast_pos.core.models.cashier_session import CashLedgerEntry, LedgerEntryType
        import datetime as _dt

        # Resolve session_id
        session_id: Optional[int] = None
        if self._cashier_sessions is not None and cashier_id is not None:
            open_sessions = self._cashier_sessions.get_open_sessions_for_day(
                day_id=shift_id
            )
            cashier_session = next(
                (s for s in open_sessions if s.user_id == cashier_id), None
            )
            if cashier_session:
                session_id = cashier_session.id

        if session_id is None:
            # No active session → skip (graceful legacy fallback)
            return

        amount_pt = round(order.total * 100)
        self._ledger.append(CashLedgerEntry(
            id=None,
            day_id=shift_id,
            session_id=session_id,
            entry_type=LedgerEntryType.SALE_CASH,
            amount_pt=amount_pt,
            order_id=order.id,
            actor_id=actor_id or cashier_id or 0,
            created_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        ))
