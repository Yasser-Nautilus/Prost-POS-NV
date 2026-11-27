import json
import logging
from datetime import date, datetime
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from broast_pos.core.models.customer import Customer, Zone
from broast_pos.core.models.order import Order
from broast_pos.core.models.user import User, UserRole
from broast_pos.data.repositories.parked_draft_repository import ParkedDraftRepository
from broast_pos.features.delivery_system.delivery_controller import DeliveryController
from broast_pos.features.financial.financial_controller import FinancialController
from broast_pos.features.financial.session_controller import SessionController
from broast_pos.features.order_lifecycle.order_controller import (
    MANAGER_PIN_REQUIRED_MSG,
    REMOVAL_REASON_REQUIRED_MSG,
    OrderController,
)
from broast_pos.features.reports.reports_controller import ReportsController

logger = logging.getLogger(__name__)

# Actions that are allowed before login
_PUBLIC_ACTIONS = frozenset({
    "login",
    "get_all_users",      # used by LoginView user tiles
    "get_current_user",   # used by App.tsx checkAuth on load
    "get_config",         # used by App.tsx for white-label branding on load
})


# Actions that change what other terminals see on the order screens.
_ORDERS_VISIBLE_ACTIONS = frozenset({
    "new_order", "add_item", "remove_item", "change_item_quantity",
    "set_item_note", "set_customer_info", "set_table", "change_table",
    "apply_discount", "park_order", "resume_parked_order",
    "confirm_order", "complete_payment", "complete_payment_split",
    "cancel_order", "save_amendment", "load_order", "load_order_by_table",
})
_DELIVERY_VISIBLE_ACTIONS = frozenset({
    "create_trip", "dispatch_trip", "return_trip", "settle_trip", "settle_driver",
})


class POSBridge(QObject):
    orderChanged = pyqtSignal(str)
    # Item 13 (batch 6): fired on any change to the visible order list (new
    # order, item added, confirmed, cancelled, dispatched) so every cashier
    # terminal refreshes at once instead of waiting for the 30s poll.
    ordersChanged = pyqtSignal(str)
    parkedChanged = pyqtSignal(str)
    tableStateChanged = pyqtSignal(str)
    shiftStatusChanged = pyqtSignal(str)

    def __init__(
        self,
        auth_service,
        product_service,
        customer_service,
        delivery_service,
        financial_service,
        order_service,
        report_service,
        print_triggers,
        printer_manager,
        settlement_service=None,
        audit_service=None,
        session_service=None,         # CashierSessionService (Phase 5)
        business_day_service=None,    # BusinessDayService (Phase 5)
        parent=None
    ):
        super().__init__(parent)
        self._auth = auth_service
        self._product = product_service
        self._customer = customer_service
        self._delivery = delivery_service
        self._financial = financial_service
        self._order_svc = order_service
        self._report = report_service
        self._print = print_triggers
        self._printer = printer_manager
        self._settlement = settlement_service
        self._audit_svc = audit_service
        self._session_svc = session_service
        self._business_day_svc = business_day_service

        self._current_user = None
        self._order_ctrl = None
        self._delivery_ctrl = None
        self._financial_ctrl = None
        self._reports_ctrl = None
        self._session_ctrl = None

    def _setup_controllers(self, user: User):
        self._current_user = user
        self._order_ctrl = OrderController(
            order_service=self._order_svc,
            financial_service=self._financial,
            auth_service=self._auth,
            print_triggers=self._print,
            cashier_slot=user.cashier_slot or 1,
            product_service=self._product,
            customer_service=self._customer,
            draft_repository=ParkedDraftRepository(self._order_svc._db),
            draft_user_id=user.id,
        )
        self._order_ctrl.on_order_changed(self._on_order_changed_cb)
        self._order_ctrl.on_parked_changed(self._on_parked_changed_cb)
        self._order_ctrl.on_table_state_changed(self._on_table_changed_cb)

        self._delivery_ctrl = DeliveryController(
            delivery_service=self._delivery,
            order_service=self._order_svc,
            print_triggers=self._print,
            cashier_slot=user.cashier_slot or 1,
            settlement_service=self._settlement,
        )
        self._financial_ctrl = FinancialController(
            financial_service=self._financial,
            auth_service=self._auth,
            printer_manager=self._printer,
        )
        self._reports_ctrl = ReportsController(
            report_service=self._report,
            financial_service=self._financial,
            printer_manager=self._printer,
        )
        # Phase 5: session controller (only if services are wired)
        if self._session_svc is not None and self._business_day_svc is not None:
            self._session_ctrl = SessionController(
                session_service=self._session_svc,
                business_day_service=self._business_day_svc,
                auth_service=self._auth,
            )

    def _session_still_valid(self) -> bool:
        """H20: ask the auth service whether this session's PIN is unchanged.

        A bridge built without an auth service (partial test doubles) has no
        way to check and keeps its previous behaviour.
        """
        auth = getattr(self, "_auth", None)
        return True if auth is None else bool(auth.validate_session())

    def _clear_session(self) -> None:
        """Drop the logged-in user and every per-user controller."""
        self._current_user = None
        self._order_ctrl = None
        self._delivery_ctrl = None
        self._financial_ctrl = None
        self._reports_ctrl = None
        self._session_ctrl = None

    @staticmethod
    def _report_scope(payload: dict[str, Any]) -> tuple[date | None, int | None]:
        """H16: read the report scope from a payload → (target_date, shift_id).

        ``shift_id`` selects one shift, ``date`` ("YYYY-MM-DD") one calendar
        day; neither means today. Whether both together are allowed is decided
        by ReportsController.validate_scope().

        Raises:
            ValueError: shift_id is not an integer or date is not YYYY-MM-DD.
        """
        shift_id = payload.get("shift_id")
        if shift_id is not None and (isinstance(shift_id, bool) or not isinstance(shift_id, int)):
            raise ValueError("رقم الوردية غير صحيح")
        raw_date = payload.get("date")
        target_date = None
        if raw_date:
            try:
                target_date = date.fromisoformat(str(raw_date))
            except ValueError:
                raise ValueError("التاريخ غير صحيح — الصيغة YYYY-MM-DD")
        return target_date, shift_id

    def _on_order_changed_cb(self):
        order = self._order_ctrl._current_order if self._order_ctrl else None
        self.orderChanged.emit(json.dumps(self._order_to_dict(order) if order else None))

    def _on_parked_changed_cb(self):
        parked = self._order_ctrl.get_parked_orders() if self._order_ctrl else []
        self.parkedChanged.emit(json.dumps([self._order_to_dict(o) for o in parked]))

    def _on_table_changed_cb(self):
        state = self._order_ctrl.get_table_state() if self._order_ctrl else {}
        self.tableStateChanged.emit(json.dumps(state))

    @staticmethod
    def _dedupe_zone_prefix(address: str, zone: str) -> str:
        """Drop a zone name the cashier typed again at the start of the street.

        Staff often write "المنطقة - الشارع" in the street field, and the order
        screen then prints the area twice (once as the zone, once inside the
        address).
        """
        a = (address or "").strip()
        z = (zone or "").strip()
        if not a or not z or not a.startswith(z):
            return a
        rest = a[len(z):].lstrip(" -–—:|،,.")
        return rest or a

    def _trigger_orders_changed(self):
        """Tell every terminal that the order list changed."""
        try:
            self.ordersChanged.emit(json.dumps({"at": datetime.now().isoformat(timespec="seconds")}))
        except Exception:  # pragma: no cover - a signal failure must never break the write
            logger.debug("ordersChanged emit failed", exc_info=True)

    def _trigger_shift_status_changed(self):
        try:
            active = self._financial.get_active_shift() is not None
            self.shiftStatusChanged.emit(json.dumps({"active": active}))
        except Exception:
            self.shiftStatusChanged.emit(json.dumps({"active": False}))

    # ── Serializers ───────────────────────────────────────────────────────────

    def _user_to_dict(self, u: User | None) -> dict[str, Any] | None:
        if not u:
            return None
        return {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "avatar_path": u.avatar_path,
            "role": u.role.value,
            "cashier_slot": u.cashier_slot,
            "phone": u.phone,
            "is_active": u.is_active,
        }

    def _order_to_dict(self, o: Order | None) -> dict[str, Any] | None:
        if not o:
            return None
        return {
            "id": o.id,
            "invoice_no": o.invoice_no,
            "shift_id": o.shift_id,
            "order_type": o.order_type.value,
            "status": o.status.value,
            "table_no": o.table_no,
            "customer_id": o.customer_id,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "customer_address": o.customer_address,
            "customer_zone": o.customer_zone,
            "delivery_fee": o.delivery_fee,
            "driver_id": o.driver_id,
            "driver_name": o.driver_name,
            "subtotal": o.subtotal,
            "discount_amount": o.discount_amount,
            "discount_type": o.discount_type,
            "service_amount": o.service_amount,
            "total": o.total,
            "payment_method": o.payment_method.value if o.payment_method else None,
            "amount_paid": o.amount_paid,
            "change_given": o.change_given,
            "is_paid": o.is_paid,
            "paid_at": o.paid_at,
            "created_by_id": o.created_by_id,
            "created_by_name": o.created_by_name,
            "cashier_slot": o.cashier_slot,
            "cancelled_by_id": o.cancelled_by_id,
            "cancelled_by_name": o.cancelled_by_name,
            "cancel_reason": o.cancel_reason,
            "cancelled_at": o.cancelled_at,
            "created_at": o.created_at,
            "updated_at": o.updated_at,
            "items": [
                {
                    "id": item.id,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "total_price": item.total_price,
                    "notes": item.notes,
                }
                for item in o.items
            ],
        }

    def _category_to_dict(self, c) -> dict[str, Any]:
        return {"id": c.id, "name": c.name, "sort_order": c.sort_order, "is_active": c.is_active}

    def _product_to_dict(self, p) -> dict[str, Any]:
        return {"id": p.id, "name": p.name, "price": p.price,
                "category_id": p.category_id, "is_active": p.is_active, "sort_order": p.sort_order}

    def _customer_to_dict(self, c: Customer) -> dict[str, Any]:
        return {
            "id": c.id, "name": c.name, "phone": c.phone,
            "notes": c.notes, "created_at": c.created_at,
            "addresses": [
                {"id": a.id, "customer_id": a.customer_id, "street_name": a.street_name,
                 "zone_id": a.zone_id, "zone_name": a.zone_name, "delivery_fee": a.delivery_fee}
                for a in c.addresses
            ],
        }

    def _audit_event(self, event_type, entity_type, entity_id, before=None, after=None):
        """Best-effort audit entry for the current user; never breaks the action."""
        if self._audit_svc is None or self._current_user is None:
            return
        try:
            self._audit_svc.log_from_user(
                event_type=event_type, actor=self._current_user,
                entity_type=entity_type, entity_id=entity_id,
                before=before, after=after,
            )
        except Exception:
            logger.exception("audit log failed for %s", event_type)

    def _zone_to_dict(self, z: Zone) -> dict[str, Any]:
        return {"id": z.id, "name": z.name, "delivery_fee": z.delivery_fee, "is_active": z.is_active}

    # ── Main Dispatcher ───────────────────────────────────────────────────────

    @pyqtSlot(str, str, result=str)
    def dispatch(self, action: str, payload_json: str) -> str:
        result = json.loads(self._dispatch(action, payload_json))
        if not result.get("success"):
            error = str(result.get("error", ""))
            technical = ("constraint", "FOREIGN KEY", "UNIQUE", "NOT NULL", "TypeError",
                         "not supported between", "could not convert", "invalid literal",
                         "has no attribute", "no such", "binding", "datatype", "syntax error")
            if any(term.lower() in error.lower() for term in technical):
                logger.error("Internal bridge error for %s: %s", action, error)
                result["error"] = "تعذر تنفيذ العملية. تحقق من البيانات المختارة وحاول مرة أخرى"
                if "message" in result:
                    result["message"] = result["error"]
        return json.dumps(result)

    def _dispatch(self, action: str, payload_json: str) -> str:
        try:
            payload = json.loads(payload_json) if payload_json else {}
            logger.info("Bridge received action: %s", action)

            # H20: revalidate authority from current DB state on every call —
            # a deactivation/demotion/PIN change must take effect immediately,
            # not only after the next full login. Clears the cached session
            # if the user was deactivated since login.
            if self._current_user is not None:
                self._current_user = self._auth.refresh_current_user()

            # ── Auth guard: reject unauthenticated calls ───────────────────────
            if action not in _PUBLIC_ACTIONS and not self._current_user:
                return json.dumps({"success": False, "error": "غير مصرح — يجب تسجيل الدخول أولاً"})

            # ── H20: reject sessions whose PIN changed (or user was deactivated) ──
            # Runs on every protected call, plus get_current_user so the UI's
            # checkAuth sees "logged out" instead of a stale user.
            if (
                self._current_user
                and action != "logout"          # logging out is always allowed
                and (action not in _PUBLIC_ACTIONS or action == "get_current_user")
                and not self._session_still_valid()
            ):
                self._clear_session()
                if action == "get_current_user":
                    return json.dumps({"success": True, "data": None})
                return json.dumps({
                    "success": False,
                    "code": "session_expired",
                    "error": "انتهت الجلسة — تم تغيير رمز PIN، يجب تسجيل الدخول من جديد",
                })

            # ── Auth ──────────────────────────────────────────────────────────
            if action == "login":
                try:
                    user = self._auth.login_by_pin(payload.get("pin", ""))
                    self._setup_controllers(user)
                    self._trigger_shift_status_changed()
                    return json.dumps({"success": True, "data": self._user_to_dict(user)})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "logout":
                self._auth.logout()
                self._clear_session()
                return json.dumps({"success": True})

            elif action == "get_current_user":
                u = self._auth.get_current_user()
                return json.dumps({"success": True, "data": self._user_to_dict(u)})

            elif action == "get_all_users":
                users = self._auth.get_all_users()
                return json.dumps({"success": True, "data": [self._user_to_dict(u) for u in users]})

            elif action == "verify_manager_pin":
                m = self._auth.verify_pin(payload.get("pin", ""))
                if m and m.is_manager_or_above():
                    return json.dumps({"success": True, "data": self._user_to_dict(m)})
                return json.dumps({"success": False, "error": "ليست لديك صلاحيات مدير"})

            elif action == "get_users_management":
                # Admin only: the list exposes every user incl. driver phones.
                if not self._current_user or self._current_user.role.value != "admin":
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير النظام"})
                users = self._auth.get_users_for_management()
                return json.dumps({"success": True, "data": [self._user_to_dict(u) for u in users]})

            elif action == "create_user":
                # Admin only
                if not self._current_user or self._current_user.role.value != "admin":
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير النظام"})
                try:
                    role_str = payload.get("role", "cashier")
                    role = UserRole(role_str)
                    if role == UserRole.ADMIN:
                        return json.dumps({"success": False, "error": "لا يمكن إنشاء مدير نظام آخر"})
                    user = self._auth.create_user(
                        username=payload.get("username", ""),
                        display_name=payload.get("display_name", ""),
                        role=role,
                        pin=payload.get("pin", ""),
                        cashier_slot=payload.get("cashier_slot"),
                        phone=payload.get("phone"),
                        require_driver_phone=True,
                    )
                    return json.dumps({"success": True, "data": self._user_to_dict(user)})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "update_user":
                # Admin only
                if not self._current_user or self._current_user.role.value != "admin":
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير النظام"})
                try:
                    role_val = payload.get("role")
                    role = UserRole(role_val) if role_val else None
                    if role == UserRole.ADMIN:
                        target = self._auth._users.get_by_id(payload.get("user_id"))
                        if target is None or target.role != UserRole.ADMIN:
                            return json.dumps({"success": False, "error": "لا يمكن ترقية مستخدم إلى مدير نظام"})
                    user = self._auth.update_user(
                        user_id=payload.get("user_id"),
                        username=payload.get("username"),
                        display_name=payload.get("display_name"),
                        role=role,
                        pin=payload.get("pin"),
                        cashier_slot=payload.get("cashier_slot", -1),
                        is_active=payload.get("is_active"),
                        phone=payload.get("phone"),
                        # Only an explicit "make/keep this a driver" (slot null) needs a phone.
                        require_driver_phone=(
                            "cashier_slot" in payload and payload["cashier_slot"] is None
                        ),
                    )
                    return json.dumps({"success": True, "data": self._user_to_dict(user)})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "deactivate_user":
                # Admin only
                if not self._current_user or self._current_user.role.value != "admin":
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير النظام"})
                try:
                    user = self._auth.update_user(
                        user_id=payload.get("user_id"),
                        is_active=False,
                    )
                    return json.dumps({"success": True, "data": self._user_to_dict(user)})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "delete_user":
                # Admin only
                if not self._current_user or self._current_user.role.value != "admin":
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير النظام"})
                try:
                    self._auth.delete_user(payload.get("user_id"))
                    return json.dumps({"success": True, "data": {"deleted": True}})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            # ── Products ──────────────────────────────────────────────────────
            elif action == "get_active_categories":
                cats = self._product.get_categories()  # get_categories() returns active only
                return json.dumps({"success": True, "data": [self._category_to_dict(c) for c in cats]})

            elif action == "get_all_categories":
                cats = self._product.get_all_categories()
                return json.dumps({"success": True, "data": [self._category_to_dict(c) for c in cats]})

            elif action == "get_all_products":
                prods = self._product.get_all_products()
                return json.dumps({"success": True, "data": [self._product_to_dict(p) for p in prods]})

            elif action == "get_products_by_category":
                prods = self._product.get_products_by_category(payload.get("category_id"))
                return json.dumps({"success": True, "data": [self._product_to_dict(p) for p in prods]})

            elif action == "search_products":
                prods = self._product.search_products(payload.get("query", ""))
                return json.dumps({"success": True, "data": [self._product_to_dict(p) for p in prods]})

            elif action == "create_product":
                # Manager/Admin only
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    prod = self._product.create_product(
                        name=payload.get("name", ""),
                        price=payload.get("price", 0),
                        category_id=int(payload.get("category_id")),
                        sort_order=int(payload.get("sort_order", 0)),
                    )
                    return json.dumps({"success": True, "data": self._product_to_dict(prod)})
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "update_product":
                # Manager/Admin only
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    prod = self._product.update_product(
                        product_id=payload.get("product_id"),
                        name=payload.get("name"),
                        price=payload["price"] if "price" in payload else None,
                        category_id=payload.get("category_id"),
                        sort_order=payload.get("sort_order"),
                        is_active=payload.get("is_active"),
                    )
                    return json.dumps({"success": True, "data": self._product_to_dict(prod)})
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "deactivate_product":
                # Manager/Admin only
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    prod = self._product.update_product(
                        product_id=payload.get("product_id"),
                        is_active=False,
                    )
                    return json.dumps({"success": True, "data": self._product_to_dict(prod)})
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "remove_product":
                # Manager/Admin only. Permanent; refused for products with order history.
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    pid = int(payload.get("product_id"))
                    old = self._product.get_product(pid)
                    self._product.remove_product(pid)
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e)})
                self._audit_event(
                    "product_removed", "product", pid,
                    before={"name": old.name, "price": old.price} if old else None,
                )
                return json.dumps({"success": True})

            elif action == "reorder_products":
                # Manager/Admin only. Saves a manual product order for one category.
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    self._product.reorder_products(
                        int(payload.get("category_id")),
                        payload.get("product_ids") or [],
                    )
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e)})
                return json.dumps({"success": True})

            elif action == "create_category":
                # Manager/Admin only
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    cat = self._product.create_category(
                        name=payload.get("name", ""),
                        sort_order=int(payload.get("sort_order", 0)),
                    )
                    return json.dumps({"success": True, "data": self._category_to_dict(cat)})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "update_category":
                # Manager/Admin only
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    cat = self._product.update_category(
                        category_id=payload.get("category_id"),
                        name=payload.get("name"),
                        sort_order=payload.get("sort_order"),
                        is_active=payload.get("is_active"),
                    )
                    return json.dumps({"success": True, "data": self._category_to_dict(cat)})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            # ── Customers ─────────────────────────────────────────────────────
            elif action == "find_customer_by_phone":
                cust = self._customer.find_by_phone(payload.get("phone", ""))
                return json.dumps({"success": True, "data": self._customer_to_dict(cust) if cust else None})

            elif action == "create_customer":
                cust = self._customer.create_customer(
                    name=payload.get("name", ""),
                    phone=payload.get("phone", "")
                )
                return json.dumps({"success": True, "data": self._customer_to_dict(cust)})

            elif action == "add_customer_address":
                addr = self._customer.add_address(
                    customer_id=payload.get("customer_id"),
                    street_name=payload.get("street_name", ""),
                    zone_id=payload.get("zone_id")
                )
                return json.dumps({"success": True, "data": {
                    "id": addr.id, "customer_id": addr.customer_id,
                    "street_name": addr.street_name, "zone_id": addr.zone_id,
                    "zone_name": addr.zone_name, "delivery_fee": addr.delivery_fee,
                }})

            elif action == "delete_customer_address":
                if payload.get("customer_id") is None:
                    raise ValueError("يجب تحديد العميل")
                self._customer.delete_address(payload.get("address_id"), payload["customer_id"])
                return json.dumps({"success": True})

            elif action == "get_active_zones":
                zones = self._customer.get_active_zones()
                return json.dumps({"success": True, "data": [self._zone_to_dict(z) for z in zones]})

            elif action == "search_customers":
                if not self._current_user:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                found = self._customer.search_customers(payload.get("query", ""))
                return json.dumps({"success": True, "data": [self._customer_to_dict(c) for c in found]})

            elif action == "update_customer":
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    before = self._customer.get_customer_by_id(payload.get("customer_id"))
                    cust = self._customer.update_customer(
                        customer_id=payload.get("customer_id"),
                        name=payload.get("name"),
                        phone=payload.get("phone"),
                    )
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})
                self._audit_event(
                    "customer_updated", "customer", cust.id,
                    before={"name": before.name, "phone": before.phone} if before else None,
                    after={"name": cust.name, "phone": cust.phone},
                )
                return json.dumps({"success": True, "data": self._customer_to_dict(cust)})

            # ── Delivery zones (manager+) ─────────────────────────────────────
            elif action == "get_all_zones":
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                return json.dumps({"success": True, "data": [self._zone_to_dict(z) for z in self._customer.get_all_zones()]})

            elif action == "create_zone":
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    zone = self._customer.create_zone(
                        name=payload.get("name", ""),
                        delivery_fee=float(payload.get("delivery_fee", 0)),
                    )
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e)})
                self._audit_event("zone_created", "zone", zone.id,
                                  after={"name": zone.name, "delivery_fee": zone.delivery_fee})
                return json.dumps({"success": True, "data": self._zone_to_dict(zone)})

            elif action == "update_zone":
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    old = next((z for z in self._customer.get_all_zones() if z.id == payload.get("zone_id")), None)
                    fee = payload.get("delivery_fee")
                    zone = self._customer.update_zone(
                        zone_id=payload.get("zone_id"),
                        name=payload.get("name"),
                        delivery_fee=float(fee) if fee is not None else None,
                        is_active=payload.get("is_active"),
                    )
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e)})
                self._audit_event(
                    "zone_updated", "zone", zone.id,
                    before={"name": old.name, "delivery_fee": old.delivery_fee, "is_active": old.is_active} if old else None,
                    after={"name": zone.name, "delivery_fee": zone.delivery_fee, "is_active": zone.is_active},
                )
                return json.dumps({"success": True, "data": self._zone_to_dict(zone)})

            elif action == "delete_category":
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    self._product.delete_category(payload.get("category_id"))
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})
                self._audit_event("category_deleted", "category", payload.get("category_id"))
                return json.dumps({"success": True})

            # ── Monthly / yearly reports (manager+) ───────────────────────────
            elif action in ("get_report_monthly", "get_report_yearly"):
                if not self._reports_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                try:
                    year = int(payload.get("year"))
                    if not 2000 <= year <= 2100:
                        raise ValueError("السنة غير صحيحة")
                    if action == "get_report_monthly":
                        month = int(payload.get("month"))
                        if not 1 <= month <= 12:
                            raise ValueError("الشهر غير صحيح")
                        data = {
                            "summary": self._reports_ctrl.get_monthly_summary(year, month),
                            "bestsellers": self._reports_ctrl.get_monthly_bestsellers(year, month, 10),
                            "expenses": self._reports_ctrl.get_monthly_expenses(year, month),
                        }
                    else:
                        data = {
                            "summary": self._reports_ctrl.get_yearly_summary(year),
                            "bestsellers": self._reports_ctrl.get_yearly_bestsellers(year, 10),
                        }
                except (ValueError, TypeError) as e:
                    return json.dumps({"success": False, "error": str(e) or "بيانات غير صحيحة"})
                return json.dumps({"success": True, "data": data})

            # ── Financial / Shift ─────────────────────────────────────────────
            elif action == "get_active_shift":
                if not self._financial_ctrl:
                    return json.dumps({"success": True, "data": None})
                s = self._financial_ctrl.get_active_shift()
                return json.dumps({"success": True, "data": s})

            elif action == "open_shift":
                if not self._financial_ctrl or not self._current_user:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                uid = payload.get("user_id") or self._current_user.id
                s = self._financial_ctrl.open_shift(uid)
                self._trigger_shift_status_changed()
                return json.dumps({"success": True, "data": s})

            elif action == "get_shift_summary":
                if not self._financial_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                shift_id = payload.get("shift_id")
                if shift_id is None:
                    active = self._financial.get_active_shift()
                    if active is None:
                        return json.dumps({"success": True, "data": {"total_sales": 0, "cash_sales": 0, "total_expenses": 0, "pending_delivery": 0, "pending_dinein": 0, "pending_kitchen": 0, "expected_cash": 0}})
                    shift_id = active.id
                try:
                    summary = self._financial_ctrl.get_shift_summary(shift_id)
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})
                return json.dumps({"success": True, "data": summary})

            elif action == "get_expenses":
                if not self._financial_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                shift_id = payload.get("shift_id")
                if shift_id is None:
                    active = self._financial.get_active_shift()
                    shift_id = active.id if active else None
                if shift_id is None:
                    return json.dumps({"success": True, "data": []})
                exps = self._financial_ctrl.get_expenses(shift_id)
                return json.dumps({"success": True, "data": exps})

            elif action == "add_expense":
                if not self._financial_ctrl or not self._current_user:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                shift_id = payload.get("shift_id")
                if shift_id is None:
                    active = self._financial.get_active_shift()
                    if active is None:
                        return json.dumps({"success": False, "error": "لا توجد وردية مفتوحة"})
                    shift_id = active.id
                exp = self._financial_ctrl.add_expense(
                    shift_id=shift_id,
                    amount=payload.get("amount"),
                    description=payload.get("description", ""),
                    category=payload.get("category", "other"),
                    user_id=self._current_user.id
                )
                return json.dumps({"success": True, "data": exp})

            elif action == "close_shift":
                if not self._financial_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                shift_id = payload.get("shift_id")
                if shift_id is None:
                    active = self._financial.get_active_shift()
                    shift_id = active.id if active else None
                if shift_id is None:
                    return json.dumps({"success": False, "error": "لا توجد وردية مفتوحة"})
                # H08: route through business_day_svc when available to enforce
                # FR-DAY-1 (all sessions closed) before marking the shift closed.
                if self._session_ctrl is not None:
                    data = self._session_ctrl.close_business_day(
                        day_id=shift_id,
                        manager_pin=payload.get("manager_pin", ""),
                    )
                    self._trigger_shift_status_changed()
                    return json.dumps({"success": True, "data": data})
                ok = self._financial_ctrl.close_shift(
                    shift_id=shift_id,
                    manager_pin=payload.get("manager_pin", "")
                )
                self._trigger_shift_status_changed()
                return json.dumps({"success": ok})

            elif action == "get_shift_history":
                if not self._financial_ctrl:
                    return json.dumps({"success": True, "data": []})
                history = self._financial_ctrl.get_shift_history()
                return json.dumps({"success": True, "data": history})

            elif action == "get_users_for_transfer":
                if not self._financial_ctrl:
                    return json.dumps({"success": True, "data": []})
                users = self._financial_ctrl.get_users_for_transfer()
                return json.dumps({"success": True, "data": users})

            elif action == "transfer_shift":
                if not self._financial_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                ok = self._financial_ctrl.transfer_shift(
                    from_user_id=payload.get("from_user_id"),
                    to_user_id=payload.get("to_user_id"),
                    manager_pin=payload.get("manager_pin")
                )
                return json.dumps({"success": ok})

            # ── Reports ───────────────────────────────────────────────────────
            elif action == "get_report_daily_sales":
                if not self._reports_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                # Manager/Admin only — matches the hidden "التقارير المالية" tab
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                # H16: payload "shift_id" → that shift's report; payload "date"
                # (YYYY-MM-DD) → that calendar day; neither → today. Not both.
                try:
                    target_date, shift_id = self._report_scope(payload)
                    data = self._reports_ctrl.generate_daily_summary(
                        target_date=target_date, shift_id=shift_id
                    )
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})
                return json.dumps({"success": True, "data": data})

            elif action == "get_report_product_sales":
                if not self._reports_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                # Manager/Admin only — matches the hidden "التقارير المالية" tab
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                # H16: same scope as get_report_daily_sales (shift_id | date | today)
                try:
                    target_date, shift_id = self._report_scope(payload)
                    self._reports_ctrl.validate_scope(target_date, shift_id)
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})
                data = self._reports_ctrl.get_bestsellers(target_date, shift_id)
                data = data[:payload.get("limit", 20)]
                return json.dumps({"success": True, "data": data})

            elif action == "print_shift_summary":
                if not self._reports_ctrl or not self._current_user:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                # Manager/Admin only — the frontend only ever renders this
                # button for isManagerOrAbove; a cashier must not be able to
                # reach the full financial report by calling the bridge directly.
                if not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                # Auto-resolve shift_id if not provided (mirrors other shift actions)
                shift_id = payload.get("shift_id")
                if shift_id is None and self._financial:
                    active = self._financial.get_active_shift()
                    if active:
                        shift_id = active.id
                # Correct method name: print_daily_summary (not print_shift_report)
                printed = self._reports_ctrl.print_daily_summary(
                    shift_id=shift_id,
                    cashier_slot=self._current_user.cashier_slot or 1
                )
                if not printed:
                    return json.dumps({"success": False, "error": "فشل في طباعة تقرير الوردية"})
                return json.dumps({"success": True})

            elif action == "get_printer_status":
                # H14: visible readiness per printer — the UI can show a
                # warning badge instead of only finding out on a failed print.
                if not self._printer:
                    return json.dumps({"success": True, "data": {}})
                return json.dumps({"success": True, "data": self._printer.get_status()})

            # ── Order Workspace ───────────────────────────────────────────────
            elif action in ("new_order", "get_current_order", "add_item", "change_item_quantity",
                            "remove_item", "set_item_note", "set_table", "change_table", "set_customer_info",
                            "park_order", "resume_parked_order", "get_parked_orders",
                            "confirm_order", "complete_payment", "complete_payment_split", "get_table_state",
                            "get_active_orders", "get_active_by_type", "get_order_history", "cancel_order",
                            "apply_discount", "reprint_receipt",
                            "load_order", "load_order_by_table", "save_amendment"):
                if not self._order_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                result = self._dispatch_order(action, payload)
                if action in _ORDERS_VISIBLE_ACTIONS:
                    self._trigger_orders_changed()
                return result

            # ── Delivery ──────────────────────────────────────────────────────
            elif action in ("get_available_drivers", "get_active_trips", "check_in_driver",
                            "check_out_driver", "create_trip", "dispatch_trip",
                            "return_trip", "settle_trip", "get_trip_details",
                            "get_driver_attendance_today", "get_daily_driver_summary",
                            "get_unassigned_deliveries", "get_driver_settlement_preview",
                            "settle_driver", "get_driver_settlements",
                            "get_driver_stats",
                            "print_driver_day_sheet", "print_trip_sheet"):
                if not self._delivery_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                result = self._dispatch_delivery(action, payload)
                if action in _DELIVERY_VISIBLE_ACTIONS:
                    self._trigger_orders_changed()
                return result

            # ── Customer History (extended) ───────────────────────────────────
            elif action == "get_customer_by_id":
                cust = self._customer.get_customer_by_id(payload.get("customer_id"))
                return json.dumps({"success": True, "data": self._customer_to_dict(cust) if cust else None})

            elif action == "get_customer_history":
                try:
                    history = self._customer.get_customer_history(
                        customer_id=payload.get("customer_id"),
                        limit=payload.get("limit", 50),
                        offset=payload.get("offset", 0),
                    )
                    return json.dumps({"success": True, "data": history})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            elif action == "get_customer_statistics":
                try:
                    stats = self._customer.get_customer_statistics(
                        customer_id=payload.get("customer_id"),
                    )
                    return json.dumps({"success": True, "data": stats})
                except ValueError as e:
                    return json.dumps({"success": False, "error": str(e)})

            # ── Order Status History ──────────────────────────────────────────
            elif action == "get_order_status_history":
                order_id = payload.get("order_id")
                history = self._order_svc.get_order_status_history(order_id)
                return json.dumps({
                    "success": True,
                    "data": [
                        {
                            "id": h.id,
                            "order_id": h.order_id,
                            "old_status": h.old_status,
                            "new_status": h.new_status,
                            "changed_by_id": h.changed_by_id,
                            "changed_by_name": h.changed_by_name,
                            "reason": h.reason,
                            "changed_at": h.changed_at,
                        }
                        for h in history
                    ]
                })

            # ── Audit Log ─────────────────────────────────────────────────────
            elif action == "get_audit_logs":
                if not self._current_user or not self._current_user.is_manager_or_above():
                    return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
                if self._audit_svc is None:
                    return json.dumps({"success": True, "data": []})
                logs = self._audit_svc.get_logs_filtered(
                    date_str=payload.get("date"),
                    user_id=payload.get("user_id"),
                    event_type=payload.get("event_type"),
                    order_id=payload.get("order_id"),
                    entity_type=payload.get("entity_type"),
                    limit=payload.get("limit", 100),
                )
                return json.dumps({
                    "success": True,
                    "data": [
                        {
                            "id": lg.id,
                            "event_type": lg.event_type,
                            "user_id": lg.user_id,
                            "user_name": lg.user_name,
                            "order_id": lg.order_id,
                            "entity_type": lg.entity_type,
                            "entity_id": lg.entity_id,
                            "action": lg.action,
                            "reason": lg.reason,
                            "details": lg.details,
                            "before_data": lg.before_data,
                            "after_data": lg.after_data,
                            "timestamp": lg.timestamp,
                        }
                        for lg in logs
                    ]
                })

            # ── Session (v2) ───────────────────────────────────────────────────
            elif action.startswith("session."):
                return self._dispatch_session(action[len("session."):], payload)

            # ── Config ─────────────────────────────────────────────────────────
            elif action == "get_config":
                from broast_pos.config.config import get_restaurant_info
                info = get_restaurant_info()
                return json.dumps({"success": True, "data": {
                    "restaurant_name_ar": info.get("name_ar", "Prost POS"),
                    "restaurant_name_en": info.get("name_en", "Prost POS"),
                    "slogan_ar": info.get("slogan_ar", ""),
                    "receipt_footer": info.get("receipt_footer", ""),
                }})

            return json.dumps({"success": False, "error": f"إجراء غير معروف: {action}"})

        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)})
        except Exception:
            logger.exception("Error in POSBridge dispatch for action %s", action)
            return json.dumps({"success": False, "error": "تعذر تنفيذ العملية. تحقق من البيانات وحاول مرة أخرى"})

    # ── Order sub-router ──────────────────────────────────────────────────────

    def _dispatch_order(self, action: str, payload: dict) -> str:
        ctrl = self._order_ctrl
        if action == "new_order":
            o = ctrl.new_order(payload.get("order_type", "dine_in"))
            return json.dumps({"success": True, "data": self._order_to_dict(o)})
        elif action == "get_current_order":
            return json.dumps({"success": True, "data": self._order_to_dict(ctrl.current_order)})
        elif action == "add_item":
            # H19: product_name/unit_price from the client are accepted but
            # ignored by the controller — price/name always come from the
            # catalogue via product_id.
            try:
                ctrl.add_item(
                    product_id=payload.get("product_id"),
                    quantity=payload.get("quantity", 1),
                    notes=payload.get("notes", "")
                )
            except ValueError as e:
                return json.dumps({"success": False, "error": str(e)})
            return json.dumps({"success": True})
        elif action == "change_item_quantity":
            ctrl.change_quantity(index=payload.get("index"), delta=payload.get("delta"))
            return json.dumps({"success": True})
        elif action == "remove_item":
            ok, msg = ctrl.remove_item(index=payload.get("index"), manager_pin=payload.get("manager_pin"))
            if ok:
                return json.dumps({"success": True, "message": msg})
            return json.dumps({"success": False, "message": msg, "error": msg})
        elif action == "set_item_note":
            ctrl.set_item_note(index=payload.get("index"), note=payload.get("note", ""))
            return json.dumps({"success": True})
        elif action == "set_table":
            ctrl.set_table(payload.get("table_number"))
            return json.dumps({"success": True})
        elif action == "change_table":
            ok, msg = ctrl.change_table(payload.get("table_number"))
            if ok:
                return json.dumps({"success": True, "message": msg})
            return json.dumps({"success": False, "error": msg})
        elif action == "set_customer_info":
            # H19: zone/delivery_fee from the client are accepted but ignored
            # whenever address_id is given — the fee is resolved from the
            # customer's saved address on the backend.
            try:
                ctrl.set_customer_info(
                    customer_id=payload.get("customer_id"),
                    phone=payload.get("phone", ""),
                    name=payload.get("name", ""),
                    address=self._dedupe_zone_prefix(
                        payload.get("address", ""), payload.get("zone", "")
                    ),
                    zone=payload.get("zone", ""),
                    delivery_fee=payload.get("delivery_fee", 0.0),
                    address_id=payload.get("address_id"),
                    # B-02: pass payment_method so delivery cash/online is recorded
                    payment_method=payload.get("payment_method"),
                )
            except ValueError as e:
                return json.dumps({"success": False, "error": str(e)})
            return json.dumps({"success": True})
        elif action == "park_order":
            return json.dumps({"success": ctrl.park_current()})
        elif action == "resume_parked_order":
            return json.dumps({"success": ctrl.resume_parked(payload.get("index"))})
        elif action == "get_parked_orders":
            return json.dumps({"success": True, "data": [self._order_to_dict(o) for o in ctrl.get_parked_orders()]})
        elif action == "confirm_order":
            ok, res = ctrl.confirm_order(
                cashier_id=self._current_user.id or 0,
                cashier_name=self._current_user.display_name or self._current_user.username
            )
            if ok:
                return json.dumps({"success": True, "data": {
                    "invoice_no": res.invoice_no,
                    "needs_immediate_payment": res.needs_immediate_payment,
                    "order_id": res.order_id,
                    "print_failed": not res.print_ok,
                }})
            return json.dumps({"success": False, "error": str(res)})
        elif action == "complete_payment":
            # keep_open=True pays the order but leaves it active (takeaway).
            ok, msg, print_ok = ctrl.complete_payment(
                order_id=payload.get("order_id"),
                payment_method=payload.get("payment_method"),
                amount_paid=payload.get("amount_paid", 0.0),
                finalize=not payload.get("keep_open", False),
            )
            if ok:
                return json.dumps({"success": True, "message": msg,
                                   "data": {"print_failed": not print_ok}})
            return json.dumps({"success": False, "message": msg, "error": msg})
        elif action == "complete_payment_split":
            ok, msg, print_ok = ctrl.complete_payment_split(
                order_id=payload.get("order_id"),
                parts=payload.get("parts") or [],
                cash_received=payload.get("cash_received"),
                finalize=not payload.get("keep_open", False),
            )
            if ok:
                return json.dumps({"success": True, "message": msg,
                                   "data": {"print_failed": not print_ok}})
            return json.dumps({"success": False, "message": msg, "error": msg})
        elif action == "get_order_history":
            return json.dumps({"success": True, "data": [self._order_to_dict(o) for o in ctrl.get_order_history(
                date.fromisoformat(payload["date"]).isoformat() if payload.get("date") else None)]})
        elif action == "get_table_state":
            return json.dumps({"success": True, "data": ctrl.get_table_state()})
        elif action == "load_order":
            order = ctrl.load_order(payload.get("order_id"))
            if order:
                return json.dumps({"success": True, "data": self._order_to_dict(order)})
            return json.dumps({"success": False, "error": "الطلب غير موجود"})
        elif action == "load_order_by_table":
            order = ctrl.load_order_by_table(payload.get("table_number"))
            if order:
                return json.dumps({"success": True, "data": self._order_to_dict(order)})
            return json.dumps({"success": False, "error": "لا يوجد طلب لهذه الطاولة"})
        elif action == "save_amendment":
            ok, msg, print_ok = ctrl.save_amendment(
                payload.get("manager_pin"), payload.get("reason")
            )
            if ok:
                return json.dumps({"success": True, "message": msg,
                                   "data": {"print_failed": not print_ok}})
            # Machine-readable code so the UI can ask for the manager PIN /
            # removal reason and retry instead of just showing an error.
            code = None
            if msg == MANAGER_PIN_REQUIRED_MSG:
                code = "manager_pin_required"
            elif msg == REMOVAL_REASON_REQUIRED_MSG:
                code = "removal_reason_required"
            resp = {"success": False, "error": msg}
            if code:
                resp["code"] = code
            return json.dumps(resp)
        elif action == "get_active_orders":
            return json.dumps({"success": True, "data": [self._order_to_dict(o) for o in ctrl.get_active_orders()]})
        elif action == "get_active_by_type":
            return json.dumps({"success": True, "data": [self._order_to_dict(o) for o in ctrl.get_active_by_type(payload.get("order_type"))]})
        elif action == "cancel_order":
            ok, msg = ctrl.cancel_order(
                order_id=payload.get("order_id"),
                manager_pin=payload.get("manager_pin"),
                reason=payload.get("reason", "")
            )
            if ok:
                return json.dumps({"success": True, "message": msg})
            return json.dumps({"success": False, "message": msg, "error": msg})
        elif action == "apply_discount":
            ok, msg = ctrl.apply_discount(
                value=payload.get("value"),
                discount_type=payload.get("discount_type"),
                manager_pin=payload.get("manager_pin")
            )
            if ok:
                return json.dumps({"success": True, "message": msg})
            return json.dumps({"success": False, "message": msg, "error": msg})
        elif action == "reprint_receipt":
            printed = ctrl.reprint_receipt(payload.get("order_id"))
            if not printed:
                return json.dumps({"success": False, "error": "تعذر تأكيد طباعة النسخة. افحص الطابعة والورق قبل المحاولة مرة أخرى"})
            return json.dumps({"success": True, "data": {"printed": True}})
        return json.dumps({"success": False, "error": f"إجراء طلب غير معروف: {action}"})

    # ── Delivery sub-router ───────────────────────────────────────────────────

    def _dispatch_delivery(self, action: str, payload: dict) -> str:
        ctrl = self._delivery_ctrl
        if action == "get_available_drivers":
            return json.dumps({"success": True, "data": ctrl.get_available_drivers()})
        elif action == "get_active_trips":
            # Controller already returns List[Dict] — pass through directly
            trips = ctrl.get_active_trips()
            return json.dumps({"success": True, "data": trips})
        elif action == "check_in_driver":
            ok, msg = ctrl.check_in_driver(payload.get("driver_id"))
            if not ok:
                return json.dumps({"success": False, "error": msg})
            return json.dumps({"success": True})
        elif action == "check_out_driver":
            ok, msg = ctrl.check_out_driver(payload.get("driver_id"))
            if not ok:
                return json.dumps({"success": False, "error": msg})
            return json.dumps({"success": True})
        elif action == "create_trip":
            ok, res = ctrl.create_trip(driver_id=payload.get("driver_id"), order_ids=payload.get("order_ids", []))
            if ok:
                # Put trip_id inside 'data' so bridge.call() resolves it correctly
                return json.dumps({"success": True, "data": {"trip_id": res.id}})
            return json.dumps({"success": False, "error": res})
        elif action == "dispatch_trip":
            ok, msg = ctrl.dispatch_trip(payload.get("trip_id"))
            if not ok:
                return json.dumps({"success": False, "error": msg})
            # Driver slips: a marked copy of each order's receipt. Printing is
            # best-effort and read-only; the dispatch above is already saved.
            failed = []
            details = ctrl.get_trip_details(payload.get("trip_id")) or {}
            order_ids = [o["order_id"] for o in details.get("orders", [])]
            if self._order_ctrl and order_ids:
                failed = self._order_ctrl.print_trip_slips(order_ids)
            failed_invoices = [o["invoice_no"] for o in details.get("orders", []) if o["order_id"] in failed]
            return json.dumps({"success": True, "message": msg, "data": {"print_failed": failed_invoices}})
        elif action == "return_trip":
            ok, msg = ctrl.return_trip(payload.get("trip_id"))
            return json.dumps({"success": ok, "message" if ok else "error": msg})
        elif action == "settle_trip":
            if not self._current_user:
                return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
            ok, msg = ctrl.settle_trip(
                payload.get("trip_id"),
                settled_by_id=self._current_user.id,
                settled_by_name=self._current_user.display_name or self._current_user.username,
            )
            if ok:
                return json.dumps({"success": True, "message": msg})
            return json.dumps({"success": False, "message": msg, "error": msg})
        elif action == "get_trip_details":
            # ARCH-001: call public controller method, not private _delivery_svc
            details = ctrl.get_trip_details(payload.get("trip_id"))
            if details:
                return json.dumps({"success": True, "data": details})
            return json.dumps({"success": False, "error": "الرحلة غير موجودة"})
        elif action == "get_driver_attendance_today":
            # ARCH-001: call public controller method, not private _delivery_svc
            records = ctrl.get_driver_attendance_today()
            drivers = ctrl.get_available_drivers()
            drivers_by_id = {d["id"]: d for d in drivers}
            # Merge attendance with driver info
            result = []
            for rec in records:
                drv = drivers_by_id.get(rec["driver_id"], {})
                result.append({
                    **rec,
                    "display_name": drv.get("display_name", rec["driver_id"]),
                })
            return json.dumps({"success": True, "data": result})
        elif action == "get_daily_driver_summary":
            # ARCH-001: call public controller method, not private _delivery_svc
            summary = ctrl.get_all_drivers_daily_summary()
            return json.dumps({"success": True, "data": summary})
        elif action == "get_driver_stats":
            if not self._current_user or not self._current_user.is_manager_or_above():
                return json.dumps({"success": False, "error": "يتطلب صلاحيات مدير"})
            try:
                data = ctrl.get_driver_stats(
                    payload.get("period", "day"), payload.get("date"))
            except ValueError as e:
                return json.dumps({"success": False, "error": str(e)})
            return json.dumps({"success": True, "data": data})
        elif action == "reassign_order":
            if not self._current_user:
                return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
            ok, result = ctrl.reassign_order(
                order_id=payload.get("order_id"),
                new_driver_id=payload.get("new_driver_id"),
                new_driver_name=payload.get("new_driver_name", ""),
            )
            if ok:
                return json.dumps({"success": True, "data": result})
            return json.dumps({"success": False, "error": result})
        elif action == "get_unassigned_deliveries":
            orders = ctrl.get_unassigned_deliveries()
            return json.dumps({"success": True, "data": orders})
        elif action == "get_driver_settlement_preview":
            try:
                preview = ctrl.get_driver_settlement_preview(
                    driver_id=payload.get("driver_id"),
                    settlement_date=payload.get("date"),
                    trip_id=payload.get("trip_id"),
                    expected_day_id=payload.get("expected_day_id"),
                )
                if preview:
                    return json.dumps({"success": True, "data": preview})
                return json.dumps({"success": False, "error": "لا توجد بيانات"})
            except ValueError as e:
                return json.dumps({"success": False, "error": str(e)})
        elif action == "settle_driver":
            if not self._current_user:
                return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
            ok, result = ctrl.settle_driver(
                driver_id=payload.get("driver_id"),
                settled_by_id=self._current_user.id,
                settled_by_name=self._current_user.display_name or self._current_user.username,
                settlement_date=payload.get("date"),
                notes=payload.get("notes"),
                trip_id=payload.get("trip_id"),
                expected_day_id=payload.get("expected_day_id"),
            )
            if ok:
                return json.dumps({"success": True, "data": {
                    "id": result.id,
                    "driver_name": result.driver_name,
                    "settlement_date": result.settlement_date,
                    "trip_count": result.trip_count,
                    "order_count": result.order_count,
                    "cash_collected": result.cash_collected,
                    "online_paid": result.online_paid,
                    "total_delivery_fees": result.total_delivery_fees,
                    "total_order_value": result.total_order_value,
                    "settled_at": result.settled_at,
                }})
            return json.dumps({"success": False, "error": result})
        elif action == "print_driver_day_sheet":
            ok, result = ctrl.print_driver_day_sheet(
                driver_id=payload.get("driver_id"),
                settlement_date=payload.get("date"),
                expected_day_id=payload.get("expected_day_id"),
            )
            if ok:
                return json.dumps({"success": True, "data": {"printed": result["printed"]}})
            return json.dumps({"success": False, "error": result})
        elif action == "print_trip_sheet":
            ok, result = ctrl.print_trip_sheet(
                driver_id=payload.get("driver_id"),
                trip_id=payload.get("trip_id"),
                settlement_date=payload.get("date"),
                expected_day_id=payload.get("expected_day_id"),
            )
            if ok:
                return json.dumps({"success": True, "data": result})
            return json.dumps({"success": False, "error": result})
        elif action == "get_driver_settlements":
            records = ctrl.get_driver_settlements(
                driver_id=payload.get("driver_id"),
                date_str=payload.get("date"),
            )
            return json.dumps({"success": True, "data": records})
        return json.dumps({"success": False, "error": f"إجراء توصيل غير معروف: {action}"})

    # ── Session sub-router (v2) ───────────────────────────────────────────────

    def _dispatch_session(self, action: str, payload: dict) -> str:
        """Handle session.* actions — delegates to SessionController."""
        if self._session_ctrl is None:
            return json.dumps({
                "success": False,
                "error": "نظام الجلسات غير مفعل (تأكد من الإعداد الأولي)"
            })

        # H05: Reject unauthenticated requests immediately — actor comes from login
        if self._current_user is None:
            return json.dumps({
                "success": False,
                "error": "يجب تسجيل الدخول أولاً"
            })

        ctrl = self._session_ctrl

        # Resolve actor from authentication — never trust caller-supplied ids
        actor = self._current_user
        actor_is_manager = actor.is_manager_or_above()

        # Resolve day_id from payload, or fall back to active shift
        day_id = payload.get("day_id")
        if day_id is None and self._financial:
            active = self._financial.get_active_shift()
            if active:
                day_id = active.id

        try:
            if action == "last_day":
                # Item 10: after the day is closed the shifts screen must still
                # show that day's sessions instead of an empty page.
                if self._financial is None:
                    return json.dumps({"success": True, "data": None})
                last = self._financial.get_last_shift()
                if last is None:
                    return json.dumps({"success": True, "data": None})
                sessions = ctrl.get_all_sessions(last.id, actor_id=actor.id)
                return json.dumps({"success": True, "data": {
                    "day": {
                        "id": last.id,
                        "business_date": getattr(last, "business_date", None),
                        "opened_at": str(last.opened_at) if last.opened_at else None,
                        "closed_at": str(last.closed_at) if last.closed_at else None,
                        "is_active": bool(last.is_active),
                    },
                    "sessions": sessions,
                }})

            if action == "open":
                # H09: reject session open against a closed/inactive business day
                open_day_id = day_id or payload.get("day_id")
                if open_day_id is not None and self._financial is not None:
                    shift = self._financial._financial.get_by_id(open_day_id)
                    if shift is None or not shift.is_active:
                        return json.dumps({
                            "success": False,
                            "error": "لا يمكن فتح وردية في يوم عمل مغلق",
                        })

                # H05: cashiers may only open their own session; managers can
                # supply a user_id to open on behalf of another cashier.
                if actor_is_manager:
                    target_user_id = payload.get("user_id", actor.id)
                else:
                    target_user_id = actor.id
                data = ctrl.open_session(
                    day_id=day_id or payload["day_id"],
                    user_id=target_user_id,
                    station=payload.get("station", "ALL"),
                    opening_float_egp=float(payload.get("opening_float_egp", 0)),
                    actor_id=actor.id,
                )
                return json.dumps({"success": True, "data": data})

            elif action == "close":
                # H05: cashiers may only close their own session.
                session_id = payload["session_id"]
                if not actor_is_manager and self._session_svc is not None:
                    owned = self._session_svc.get_session_by_id(session_id)
                    if owned is None or owned.user_id != actor.id:
                        return json.dumps({
                            "success": False,
                            "error": "لا يمكن إغلاق درج كاشير آخر",
                        })
                data = ctrl.close_session(
                    session_id=session_id,
                    counted_cash_egp=payload.get("counted_cash_egp"),
                    actor_id=actor.id,
                    variance_reason=payload.get("variance_reason"),
                    manager_pin=payload.get("manager_pin"),
                )
                return json.dumps({"success": True, "data": data})

            elif action == "handover":
                # H05: cashiers may only handover their own session; recipient cannot be a driver
                from_session_id = payload["from_session_id"]
                outgoing_session = None
                if self._session_svc is not None:
                    outgoing_session = self._session_svc.get_session_by_id(from_session_id)
                if not actor_is_manager:
                    if outgoing_session is None or outgoing_session.user_id != actor.id:
                        return json.dumps({
                            "success": False,
                            "error": "لا يمكن تسليم درج كاشير آخر",
                        })
                to_user_id = payload["to_user_id"]
                if self._auth is not None:
                    to_user = self._auth.get_user_by_id(to_user_id)
                    if to_user is not None and to_user.cashier_slot is None:
                        return json.dumps({
                            "success": False,
                            "error": "المستخدم المستلم ليس كاشيراً مسجلاً — لا يمكن نقل الوردية لسائق توصيل",
                        })
                if outgoing_session is None:
                    return json.dumps({
                        "success": False,
                        "error": "وردية التسليم غير موجودة",
                    })
                # H05: the recipient's new session always takes over the SAME
                # physical station as the outgoing one — a handover changes
                # who is responsible for a drawer, never which drawer it is.
                # Never trust a client-supplied station here.
                data = ctrl.do_handover(
                    from_session_id=from_session_id,
                    to_user_id=to_user_id,
                    station=outgoing_session.station.value,
                    counted_cash_egp=payload.get("counted_cash_egp"),
                    cash_drop_egp=float(payload.get("cash_drop_egp", 0)),
                    actor_id=actor.id,
                    variance_reason=payload.get("variance_reason"),
                    manager_pin=payload.get("manager_pin"),
                )
                return json.dumps({"success": True, "data": data})

            elif action == "get_active":
                if day_id is None:
                    return json.dumps({"success": True, "data": []})
                data = ctrl.get_active_sessions(day_id, actor_id=actor.id)
                return json.dumps({"success": True, "data": data})

            elif action == "get_all":
                if day_id is None:
                    return json.dumps({"success": True, "data": []})
                data = ctrl.get_all_sessions(day_id, actor_id=actor.id)
                return json.dumps({"success": True, "data": data})

            elif action == "get_balance":
                # H05: cashiers cannot read another cashier's balance; and
                # cannot see their own open-session expected cash before the
                # blind count is committed (prevents "counting to target").
                session_id = payload["session_id"]
                if not actor_is_manager and self._session_svc is not None:
                    owned = self._session_svc.get_session_by_id(session_id)
                    if owned is None or owned.user_id != actor.id:
                        return json.dumps({
                            "success": False,
                            "error": "لا يمكن قراءة رصيد درج كاشير آخر",
                        })
                    if owned.is_open:
                        return json.dumps({
                            "success": False,
                            "error": "لا يمكن قراءة الرصيد المتوقع قبل إجراء الجرد",
                        })
                data = ctrl.get_session_balance(session_id, actor_id=actor.id)
                return json.dumps({"success": True, "data": data})

            elif action == "x_report":
                if not actor_is_manager:
                    return json.dumps({
                        "success": False,
                        "error": "تقرير X متاح للمدير فقط",
                    })
                if day_id is None:
                    return json.dumps({"success": False, "error": "لا توجد وردية مفتوحة"})
                data = ctrl.generate_x_report(day_id, actor_id=actor.id)
                return json.dumps({"success": True, "data": data})

            elif action == "close_day":
                manager_pin = payload.get("manager_pin")
                if not actor_is_manager and not manager_pin:
                    return json.dumps({
                        "success": False,
                        "error": "إغلاق اليوم متاح للمدير فقط",
                    })
                if day_id is None:
                    return json.dumps({"success": False, "error": "لا توجد وردية مفتوحة"})
                data = ctrl.close_business_day(
                    day_id=day_id,
                    manager_pin=manager_pin,
                    actor_id=actor.id,
                )
                return json.dumps({"success": True, "data": data})

            return json.dumps({"success": False, "error": f"إجراء جلسة غير معروف: {action}"})

        except ValueError as exc:
            return json.dumps({"success": False, "error": str(exc)})
        except Exception as exc:
            logger.exception("Error in session dispatch: %s", action)
            return json.dumps({"success": False, "error": str(exc)})
