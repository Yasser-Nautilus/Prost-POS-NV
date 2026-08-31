import json
import logging
from typing import Any, Dict, List, Optional
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal

from broast_pos.core.models.order import Order, OrderItem, OrderType, OrderStatus, PaymentMethod
from broast_pos.core.models.user import User, UserRole
from broast_pos.core.models.customer import Customer, CustomerAddress, Zone
from broast_pos.core.models.financial import Shift, ShiftSummary, CashTransaction
from broast_pos.core.models.delivery import DeliveryTrip, DriverStatus
from broast_pos.features.order_lifecycle.order_controller import OrderController
from broast_pos.features.delivery_system.delivery_controller import DeliveryController
from broast_pos.features.financial.financial_controller import FinancialController
from broast_pos.features.reports.reports_controller import ReportsController

logger = logging.getLogger(__name__)


class POSBridge(QObject):
    orderChanged = pyqtSignal(str)
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

        self._current_user = None
        self._order_ctrl = None
        self._delivery_ctrl = None
        self._financial_ctrl = None
        self._reports_ctrl = None

    def _setup_controllers(self, user: User):
        self._current_user = user
        self._order_ctrl = OrderController(
            order_service=self._order_svc,
            financial_service=self._financial,
            auth_service=self._auth,
            print_triggers=self._print,
            cashier_slot=user.cashier_slot or 1,
        )
        self._order_ctrl.on_order_changed(self._on_order_changed_cb)
        self._order_ctrl.on_parked_changed(self._on_parked_changed_cb)
        self._order_ctrl.on_table_state_changed(self._on_table_changed_cb)

        self._delivery_ctrl = DeliveryController(
            delivery_service=self._delivery,
            order_service=self._order_svc,
            print_triggers=self._print,
            cashier_slot=user.cashier_slot or 1,
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

    def _on_order_changed_cb(self):
        order = self._order_ctrl._current_order if self._order_ctrl else None
        self.orderChanged.emit(json.dumps(self._order_to_dict(order) if order else None))

    def _on_parked_changed_cb(self):
        parked = self._order_ctrl.get_parked_orders() if self._order_ctrl else []
        self.parkedChanged.emit(json.dumps([self._order_to_dict(o) for o in parked]))

    def _on_table_changed_cb(self):
        state = self._order_ctrl.get_table_state() if self._order_ctrl else {}
        self.tableStateChanged.emit(json.dumps(state))

    def _trigger_shift_status_changed(self):
        try:
            active = self._financial.get_active_shift() is not None
            self.shiftStatusChanged.emit(json.dumps({"active": active}))
        except Exception:
            self.shiftStatusChanged.emit(json.dumps({"active": False}))

    # ── Serializers ───────────────────────────────────────────────────────────

    def _user_to_dict(self, u: Optional[User]) -> Optional[Dict[str, Any]]:
        if not u:
            return None
        return {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "avatar_path": u.avatar_path,
            "role": u.role.value,
            "cashier_slot": u.cashier_slot,
            "is_active": u.is_active,
        }

    def _order_to_dict(self, o: Optional[Order]) -> Optional[Dict[str, Any]]:
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

    def _category_to_dict(self, c) -> Dict[str, Any]:
        return {"id": c.id, "name": c.name, "sort_order": c.sort_order, "is_active": c.is_active}

    def _product_to_dict(self, p) -> Dict[str, Any]:
        return {"id": p.id, "name": p.name, "price": p.price,
                "category_id": p.category_id, "is_active": p.is_active, "sort_order": p.sort_order}

    def _customer_to_dict(self, c: Customer) -> Dict[str, Any]:
        return {
            "id": c.id, "name": c.name, "phone": c.phone,
            "notes": c.notes, "created_at": c.created_at,
            "addresses": [
                {"id": a.id, "customer_id": a.customer_id, "street_name": a.street_name,
                 "zone_id": a.zone_id, "zone_name": a.zone_name, "delivery_fee": a.delivery_fee}
                for a in c.addresses
            ],
        }

    def _zone_to_dict(self, z: Zone) -> Dict[str, Any]:
        return {"id": z.id, "name": z.name, "delivery_fee": z.delivery_fee, "is_active": z.is_active}

    # ── Main Dispatcher ───────────────────────────────────────────────────────

    @pyqtSlot(str, str, result=str)
    def dispatch(self, action: str, payload_json: str) -> str:
        try:
            payload = json.loads(payload_json) if payload_json else {}
            logger.info("Bridge received action: %s", action)

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
                self._current_user = None
                self._order_ctrl = None
                self._delivery_ctrl = None
                self._financial_ctrl = None
                self._reports_ctrl = None
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

            # ── Products ──────────────────────────────────────────────────────
            elif action == "get_active_categories":
                cats = self._product.get_active_categories()
                return json.dumps({"success": True, "data": [self._category_to_dict(c) for c in cats]})

            elif action == "get_products_by_category":
                prods = self._product.get_products_by_category(payload.get("category_id"))
                return json.dumps({"success": True, "data": [self._product_to_dict(p) for p in prods]})

            elif action == "search_products":
                prods = self._product.search_products(payload.get("query", ""))
                return json.dumps({"success": True, "data": [self._product_to_dict(p) for p in prods]})

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

            elif action == "get_active_zones":
                zones = self._customer.get_active_zones()
                return json.dumps({"success": True, "data": [self._zone_to_dict(z) for z in zones]})

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
                        return json.dumps({"success": True, "data": {"total_sales": 0, "total_expenses": 0, "pending_delivery": 0, "pending_dinein": 0, "pending_kitchen": 0, "expected_cash": 0}})
                    shift_id = active.id
                summary = self._financial_ctrl.get_shift_summary(shift_id)
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
                    user_id=payload.get("user_id") or self._current_user.id
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
                data = self._report.get_daily_sales_summary(payload.get("date_str", ""))
                return json.dumps({"success": True, "data": data})

            elif action == "get_report_product_sales":
                data = self._report.get_product_sales_summary(
                    start_date=payload.get("start_date", ""),
                    end_date=payload.get("end_date", "")
                )
                return json.dumps({"success": True, "data": data})

            elif action == "print_shift_summary":
                if self._reports_ctrl and self._current_user:
                    self._reports_ctrl.print_shift_report(
                        shift_id=payload.get("shift_id"),
                        cashier_slot=self._current_user.cashier_slot or 1
                    )
                return json.dumps({"success": True})

            # ── Order Workspace ───────────────────────────────────────────────
            elif action in ("new_order", "get_current_order", "add_item", "change_item_quantity",
                            "remove_item", "set_item_note", "set_table", "set_customer_info",
                            "park_order", "resume_parked_order", "get_parked_orders",
                            "confirm_order", "complete_payment", "get_table_state",
                            "get_active_orders", "get_active_by_type", "cancel_order",
                            "apply_discount", "reprint_receipt"):
                if not self._order_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                return self._dispatch_order(action, payload)

            # ── Delivery ──────────────────────────────────────────────────────
            elif action in ("get_available_drivers", "get_active_trips", "check_in_driver",
                            "check_out_driver", "create_trip", "dispatch_trip",
                            "return_trip", "settle_trip"):
                if not self._delivery_ctrl:
                    return json.dumps({"success": False, "error": "يجب تسجيل الدخول أولاً"})
                return self._dispatch_delivery(action, payload)

            return json.dumps({"success": False, "error": f"إجراء غير معروف: {action}"})

        except Exception as e:
            logger.exception("Error in POSBridge dispatch for action %s", action)
            return json.dumps({"success": False, "error": str(e)})

    # ── Order sub-router ──────────────────────────────────────────────────────

    def _dispatch_order(self, action: str, payload: dict) -> str:
        ctrl = self._order_ctrl
        if action == "new_order":
            o = ctrl.new_order(payload.get("order_type", "dine_in"))
            return json.dumps({"success": True, "data": self._order_to_dict(o)})
        elif action == "get_current_order":
            return json.dumps({"success": True, "data": self._order_to_dict(ctrl.current_order)})
        elif action == "add_item":
            ctrl.add_item(
                product_id=payload.get("product_id"),
                product_name=payload.get("product_name"),
                unit_price=payload.get("unit_price"),
                quantity=payload.get("quantity", 1),
                notes=payload.get("notes", "")
            )
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
        elif action == "set_customer_info":
            ctrl.set_customer_info(
                customer_id=payload.get("customer_id"),
                phone=payload.get("phone", ""),
                name=payload.get("name", ""),
                address=payload.get("address", ""),
                zone=payload.get("zone", ""),
                delivery_fee=payload.get("delivery_fee", 0.0)
            )
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
                    "order_id": res.order_id
                }})
            return json.dumps({"success": False, "error": str(res)})
        elif action == "complete_payment":
            ok, msg = ctrl.complete_payment(
                order_id=payload.get("order_id"),
                payment_method=payload.get("payment_method"),
                amount_paid=payload.get("amount_paid", 0.0)
            )
            if ok:
                return json.dumps({"success": True, "message": msg})
            return json.dumps({"success": False, "message": msg, "error": msg})
        elif action == "get_table_state":
            return json.dumps({"success": True, "data": ctrl.get_table_state()})
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
            return json.dumps({"success": ctrl.reprint_receipt(payload.get("order_id"))})
        return json.dumps({"success": False, "error": f"إجراء طلب غير معروف: {action}"})

    # ── Delivery sub-router ───────────────────────────────────────────────────

    def _dispatch_delivery(self, action: str, payload: dict) -> str:
        ctrl = self._delivery_ctrl
        if action == "get_available_drivers":
            return json.dumps({"success": True, "data": ctrl.get_available_drivers()})
        elif action == "get_active_trips":
            trips = ctrl.get_active_trips()
            return json.dumps({"success": True, "data": [{
                "id": t.id, "driver_id": t.driver_id, "driver_name": t.driver_name,
                "created_at": t.created_at, "dispatched_at": t.dispatched_at,
                "returned_at": t.returned_at, "settled_at": t.settled_at,
                "order_ids": t.order_ids, "cash_collected": t.cash_collected,
                "total_delivery_fees": t.total_delivery_fees, "is_settled": t.is_settled,
            } for t in trips]})
        elif action == "check_in_driver":
            ctrl.check_in_driver(payload.get("driver_id"))
            return json.dumps({"success": True})
        elif action == "check_out_driver":
            ctrl.check_out_driver(payload.get("driver_id"))
            return json.dumps({"success": True})
        elif action == "create_trip":
            ok, res = ctrl.create_trip(driver_id=payload.get("driver_id"), order_ids=payload.get("order_ids", []))
            if ok:
                return json.dumps({"success": True, "trip_id": res.id})
            return json.dumps({"success": False, "error": res})
        elif action == "dispatch_trip":
            ok, msg = ctrl.dispatch_trip(payload.get("trip_id"))
            return json.dumps({"success": ok, "message" if ok else "error": msg})
        elif action == "return_trip":
            ok, msg = ctrl.return_trip(payload.get("trip_id"))
            return json.dumps({"success": ok, "message" if ok else "error": msg})
        elif action == "settle_trip":
            ok, msg = ctrl.settle_trip(payload.get("trip_id"))
            if ok:
                return json.dumps({"success": True, "message": msg})
            return json.dumps({"success": False, "message": msg, "error": msg})
        return json.dumps({"success": False, "error": f"إجراء توصيل غير معروف: {action}"})
