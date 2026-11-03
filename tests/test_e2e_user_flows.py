"""
Comprehensive End-to-End User Simulation Tests.

Simulates a real cashier and manager operating the POS through the POSBridge,
mirroring the exact frontend bridge calls made in React/TypeScript:
  1. Authentication & Role Permissions (login, wrong PIN, admin vs cashier)
  2. Shift Opening
  3. Dine-In workflow (table select, item notes, confirm, table move, cash payment, table release)
  4. Takeaway workflow (items, discount voucher, confirm, card payment, cart cleared)
  5. Delivery workflow (customer lookup/create, delivery order, driver check-in, dispatch, delivery, return, settlement preview with trip_id & notes)
  6. Petty cash expense booking
  7. Shift close guards (prevent closing when orders are in flight)
  8. Shift reconciliation & closing (manager review, print summary, close shift)
  9. Audit logs & reports verification
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication

from broast_pos.core.services.audit_service import AuditService
from broast_pos.core.services.auth_service import AuthService
from broast_pos.core.services.business_day_service import BusinessDayService
from broast_pos.core.services.cashier_session_service import CashierSessionService
from broast_pos.core.services.customer_service import CustomerService
from broast_pos.core.services.delivery_service import DeliveryService
from broast_pos.core.services.driver_settlement_service import DriverSettlementService
from broast_pos.core.services.financial_service import FinancialService
from broast_pos.core.services.order_service import OrderService
from broast_pos.core.services.product_service import ProductService
from broast_pos.core.services.report_service import ReportService
from broast_pos.data.database.connection import DatabaseConnection
from broast_pos.data.database.migrations import initialise_database
from broast_pos.data.database.seed import seed_database
from broast_pos.data.repositories.audit_repository import AuditRepository
from broast_pos.data.repositories.cash_ledger_repository import CashLedgerRepository
from broast_pos.data.repositories.cashier_session_repository import (
    CashierSessionRepository,
)
from broast_pos.data.repositories.customer_repository import CustomerRepository
from broast_pos.data.repositories.delivery_repository import DeliveryRepository
from broast_pos.data.repositories.driver_settlement_repository import (
    DriverSettlementRepository,
)
from broast_pos.data.repositories.financial_repository import FinancialRepository
from broast_pos.data.repositories.order_repository import OrderRepository
from broast_pos.data.repositories.order_status_history_repository import (
    OrderStatusHistoryRepository,
)
from broast_pos.data.repositories.product_repository import ProductRepository
from broast_pos.data.repositories.user_repository import UserRepository
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers
from broast_pos.infrastructure.printing.printer_manager import PrinterManager
from broast_pos.infrastructure.web_bridge.bridge import POSBridge


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QCoreApplication instance exists for QObject signal support."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


@pytest.fixture(autouse=True)
def reset_db_singleton():
    DatabaseConnection.reset()
    yield
    DatabaseConnection.reset()


def _build_test_bridge(qapp):
    """Build a complete POSBridge backed by an in-memory SQLite database seeded with default data."""
    db = DatabaseConnection(":memory:")
    DatabaseConnection._instance = db
    initialise_database(db)
    seed_database(db)

    user_repo = UserRepository(db)
    product_repo = ProductRepository(db)
    order_repo = OrderRepository(db)
    audit_repo = AuditRepository(db)
    financial_repo = FinancialRepository(db)
    delivery_repo = DeliveryRepository(db)
    customer_repo = CustomerRepository(db)
    status_history_repo = OrderStatusHistoryRepository(db)
    settlement_repo = DriverSettlementRepository(db)
    cashier_session_repo = CashierSessionRepository(db)
    cash_ledger_repo = CashLedgerRepository(db)

    auth_service = AuthService(user_repo)
    auth_service.set_audit(audit_repo)
    product_service = ProductService(product_repo)
    customer_service = CustomerService(customer_repo)
    audit_service = AuditService(audit_repo)

    delivery_service = DeliveryService(
        delivery_repo=delivery_repo,
        user_repo=user_repo,
        audit_repo=audit_repo,
    )
    financial_service = FinancialService(
        financial_repo=financial_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        delivery_service=delivery_service,
    )
    cashier_session_service = CashierSessionService(
        session_repo=cashier_session_repo,
        ledger_repo=cash_ledger_repo,
        auth_service=auth_service,
    )
    order_service = OrderService(
        order_repo=order_repo,
        audit_repo=audit_repo,
        auth_service=auth_service,
        financial_service=financial_service,
        status_history_repo=status_history_repo,
        audit_service=audit_service,
        session_service=cashier_session_service,
        ledger_repo=cash_ledger_repo,
        cashier_session_repo=cashier_session_repo,
    )
    delivery_service._order_svc = order_service

    settlement_service = DriverSettlementService(
        settlement_repo=settlement_repo,
        delivery_repo=delivery_repo,
        order_repo=order_repo,
        user_repo=user_repo,
        audit_repo=audit_repo,
        order_svc=order_service,
        ledger_repo=cash_ledger_repo,
        cashier_session_repo=cashier_session_repo,
    )
    delivery_service._settlement_svc = settlement_service

    report_service = ReportService(
        order_repo=order_repo,
        financial_repo=financial_repo,
        delivery_repo=delivery_repo,
    )
    business_day_service = BusinessDayService(
        financial_service=financial_service,
        session_repo=cashier_session_repo,
        ledger_repo=cash_ledger_repo,
        auth_service=auth_service,
    )

    printer_manager = PrinterManager()
    printer_manager.print_receipt = MagicMock(return_value=True)
    printer_manager.print_kitchen_order = MagicMock(return_value=True)
    printer_manager.print_daily_summary = MagicMock(return_value=True)
    printer_manager.print_shift_summary = MagicMock(return_value=True)
    print_triggers = PrintTriggers(printer_manager)

    bridge = POSBridge(
        auth_service=auth_service,
        product_service=product_service,
        customer_service=customer_service,
        delivery_service=delivery_service,
        financial_service=financial_service,
        order_service=order_service,
        report_service=report_service,
        print_triggers=print_triggers,
        printer_manager=printer_manager,
        settlement_service=settlement_service,
        audit_service=audit_service,
        session_service=cashier_session_service,
        business_day_service=business_day_service,
    )

    return bridge, db


class POSUserClient:
    """Helper client that calls the bridge dispatch exactly like the frontend React bridge.call()."""

    def __init__(self, bridge: POSBridge):
        self.bridge = bridge

    def call(self, action: str, payload: dict | None = None) -> dict:
        raw = self.bridge.dispatch(action, json.dumps(payload or {}))
        return json.loads(raw)


class TestFullUserSimulation:
    """Simulate a complete day in the life of a restaurant user."""

    def test_complete_restaurant_day_workflow(self, qapp):
        bridge, _db = _build_test_bridge(qapp)
        client = POSUserClient(bridge)

        # ------------------------------------------------------------------
        # Step 1: Authentication & User Setup
        # ------------------------------------------------------------------
        # Trying a protected action without logging in should fail
        res = client.call("get_active_shift")
        assert res["success"] is False
        assert "تسجيل الدخول" in res["error"]

        # Wrong PIN login fails
        res = client.call("login", {"pin": "9999"})
        assert res["success"] is False
        assert "غير صحيح" in res["error"]

        # Admin logs in (default seeded PIN: "1234")
        res = client.call("login", {"pin": "1234"})
        assert res["success"] is True
        assert res["data"]["role"] == "admin"

        # Admin creates a Cashier user (PIN: "2222", slot 1)
        res = client.call("create_user", {
            "username": "cashier_sara",
            "display_name": "سارة الكاشير",
            "role": "cashier",
            "pin": "2222",
            "cashier_slot": 1,
        })
        assert res["success"] is True
        cashier_id = res["data"]["id"]

        # Admin creates a Delivery Driver (PIN: "3333", cashier_slot None)
        res = client.call("create_user", {
            "username": "driver_omar",
            "display_name": "عمر السائق",
            "role": "cashier",  # Role cashier with slot None acts as driver
            "pin": "3333",
            "cashier_slot": None,
        })
        assert res["success"] is True
        driver_id = res["data"]["id"]

        # Admin logs out
        res = client.call("logout")
        assert res["success"] is True

        # ------------------------------------------------------------------
        # Step 2: Cashier Logs In & Opens Shift
        # ------------------------------------------------------------------
        res = client.call("login", {"pin": "2222"})
        assert res["success"] is True
        assert res["data"]["id"] == cashier_id

        # Cashier checks active shift -> None
        res = client.call("get_active_shift")
        assert res["success"] is True
        assert res["data"] is None

        # Cashier opens shift
        res = client.call("open_shift")
        assert res["success"] is True
        shift = res["data"]
        shift_id = shift["id"]
        assert shift["is_active"] is True

        # Verify active shift is now reported
        res = client.call("get_active_shift")
        assert res["success"] is True
        assert res["data"]["id"] == shift_id

        # Cashier opens cashier session on station ALL
        res = client.call("session.open", {
            "day_id": shift_id,
            "user_id": cashier_id,
            "station": "ALL",
            "opening_float_egp": 500.0,
        })
        assert res["success"] is True
        assert res["data"]["id"] is not None

        # ------------------------------------------------------------------
        # Step 3: Dine-In Order Flow (Order -> Kitchen -> Move Table -> Pay)
        # ------------------------------------------------------------------
        # Products check
        res = client.call("get_all_products")
        assert res["success"] is True
        products = res["data"]
        broast_meal = next(p for p in products if "2 قطعة دجاج حار" in p["name"])
        pepsi = next(p for p in products if "بيبسي" in p["name"])

        # Cashier starts a dine-in order
        res = client.call("new_order", {"order_type": "dine_in"})
        assert res["success"] is True

        # Assign table 4
        res = client.call("set_table", {"table_number": 4})
        assert res["success"] is True

        # Add 2x Broast meal (110 * 2 = 220) and 1x Pepsi (15)
        res = client.call("add_item", {
            "product_id": broast_meal["id"],
            "product_name": broast_meal["name"],
            "unit_price": broast_meal["price"],
            "quantity": 2,
        })
        assert res["success"] is True

        res = client.call("add_item", {
            "product_id": pepsi["id"],
            "product_name": pepsi["name"],
            "unit_price": pepsi["price"],
            "quantity": 1,
            "notes": "بارد جداً",
        })
        assert res["success"] is True

        # Check current order state: total = 235.00
        res = client.call("get_current_order")
        assert res["success"] is True
        assert res["data"]["total"] == 235.0
        assert res["data"]["table_no"] == 4

        # Confirm order (sends to kitchen)
        res = client.call("confirm_order")
        assert res["success"] is True
        dine_in_order_id = res["data"]["order_id"]
        # Dine-in should NOT need immediate payment
        assert res["data"]["needs_immediate_payment"] is False

        # Table state shows table 4 is occupied
        res = client.call("get_table_state")
        assert res["success"] is True
        assert res["data"].get("4") is not None

        # Customer requests moving from Table 4 to Table 12
        # Load order by table first (cashier navigates to table)
        res = client.call("load_order_by_table", {"table_number": 4})
        assert res["success"] is True
        assert res["data"]["id"] == dine_in_order_id

        # Change table to 12
        res = client.call("change_table", {"table_number": 12})
        assert res["success"] is True

        # Verify table 4 is freed and table 12 is occupied
        res = client.call("get_table_state")
        assert res["success"] is True
        assert "4" not in res["data"]
        assert "12" in res["data"]

        # Customer asks for the bill and pays 250.00 cash (bill: 235.00, change: 15.00)
        res = client.call("complete_payment", {
            "order_id": dine_in_order_id,
            "payment_method": "cash",
            "amount_paid": 250.0,
            "keep_open": False,
        })
        assert res["success"] is True

        # Cart must be cleared after payment
        res = client.call("get_current_order")
        assert res["success"] is True
        assert res["data"] is None

        # Table 12 is now free
        res = client.call("get_table_state")
        assert res["success"] is True
        assert "12" not in res["data"]

        # ------------------------------------------------------------------
        # Step 4: Takeaway Order Flow (With Voucher Discount & Card Payment)
        # ------------------------------------------------------------------
        fries = next(p for p in products if "تشيكن فرايز حار" in p["name"])
        coleslaw = next(p for p in products if "كول سلو" in p["name"])

        res = client.call("new_order", {"order_type": "takeaway"})
        assert res["success"] is True

        res = client.call("add_item", {
            "product_id": fries["id"],
            "product_name": fries["name"],
            "unit_price": fries["price"],
            "quantity": 1,
        })
        assert res["success"] is True

        res = client.call("add_item", {
            "product_id": coleslaw["id"],
            "product_name": coleslaw["name"],
            "unit_price": coleslaw["price"],
            "quantity": 1,
        })
        assert res["success"] is True

        # Total is 70 + 15 = 85.00
        res = client.call("get_current_order")
        assert res["data"]["total"] == 85.0

        # Apply a 10.00 EGP discount (manager override PIN: "1234")
        res = client.call("apply_discount", {
            "value": 10.0,
            "discount_type": "flat",
            "manager_pin": "1234",
        })
        assert res["success"] is True

        # Verify discount applied: total is now 75.00
        res = client.call("get_current_order")
        assert res["data"]["total"] == 75.0
        assert res["data"]["discount_amount"] == 10.0

        # Confirm order (Takeaway requires immediate payment)
        res = client.call("confirm_order")
        assert res["success"] is True
        takeaway_order_id = res["data"]["order_id"]
        assert res["data"]["needs_immediate_payment"] is True

        # Pay with card (visa)
        res = client.call("complete_payment", {
            "order_id": takeaway_order_id,
            "payment_method": "visa",
            "amount_paid": 75.0,
            "keep_open": False,
        })
        assert res["success"] is True

        # ------------------------------------------------------------------
        # Step 5: Delivery Order Flow & Driver Settlement
        # ------------------------------------------------------------------
        # Customer lookup -> phone doesn't exist
        res = client.call("find_customer_by_phone", {"phone": "01099887766"})
        assert res["success"] is True
        assert res["data"] is None

        # Register customer
        res = client.call("create_customer", {
            "name": "محمود إبراهيم",
            "phone": "01099887766",
            "notes": "العميل يفضل الاتصال قبل الوصول",
        })
        assert res["success"] is True
        cust_id = res["data"]["id"]

        # Get delivery zones
        res = client.call("get_active_zones")
        assert res["success"] is True
        zones = res["data"]
        zone_entag = next(z for z in zones if "شارع الانتاج" in z["name"])

        # Add customer address
        res = client.call("add_customer_address", {
            "customer_id": cust_id,
            "street_name": "عمارة 15 الدور الثالث",
            "zone_id": zone_entag["id"],
        })
        assert res["success"] is True

        # Create delivery order
        res = client.call("new_order", {"order_type": "delivery"})
        assert res["success"] is True

        res = client.call("set_customer_info", {
            "customer_id": cust_id,
            "name": "محمود إبراهيم",
            "phone": "01099887766",
            "address": "عمارة 15 الدور الثالث",
            "zone": zone_entag["name"],
            "delivery_fee": zone_entag["delivery_fee"],  # 15.00
            "payment_method": "cash",
        })
        assert res["success"] is True

        # Add 1x Broast normal (110.00)
        broast_normal = next(p for p in products if "2 قطعة دجاج عادي" in p["name"])
        res = client.call("add_item", {
            "product_id": broast_normal["id"],
            "product_name": broast_normal["name"],
            "unit_price": broast_normal["price"],
            "quantity": 1,
        })
        assert res["success"] is True

        # Check total: 110.00 + 15.00 = 125.00
        res = client.call("get_current_order")
        assert res["data"]["total"] == 125.0
        assert res["data"]["delivery_fee"] == 15.0

        # Confirm delivery order
        res = client.call("confirm_order")
        assert res["success"] is True
        delivery_order_id = res["data"]["order_id"]

        # Order appears in unassigned deliveries
        res = client.call("get_unassigned_deliveries")
        assert res["success"] is True
        assert any(o["id"] == delivery_order_id for o in res["data"])

        # Driver checks in for the day
        res = client.call("check_in_driver", {"driver_id": driver_id})
        assert res["success"] is True

        # Create trip with driver and order
        res = client.call("create_trip", {
            "driver_id": driver_id,
            "order_ids": [delivery_order_id],
        })
        assert res["success"] is True
        trip_id = res["data"]["trip_id"]

        # Dispatch trip
        res = client.call("dispatch_trip", {"trip_id": trip_id})
        assert res["success"] is True

        # Driver returns
        res = client.call("return_trip", {"trip_id": trip_id})
        assert res["success"] is True

        # Driver settlement preview for this trip
        res = client.call("get_driver_settlement_preview", {
            "driver_id": driver_id,
            "trip_id": trip_id,
        })
        assert res["success"] is True
        preview = res["data"]
        assert preview["order_count"] == 1
        assert preview["cash_collected"] == 125.0

        # Settle driver with notes (verifying notes support!)
        settle_note = "تم استلام 125 ج وتسليم بون الشفت بالكامل"
        res = client.call("settle_driver", {
            "driver_id": driver_id,
            "trip_id": trip_id,
            "notes": settle_note,
        })
        assert res["success"] is True
        settlement_data = res["data"]
        assert settlement_data["cash_collected"] == 125.0

        # ------------------------------------------------------------------
        # Step 6: Petty Cash Expense
        # ------------------------------------------------------------------
        res = client.call("add_expense", {
            "amount": 50.0,
            "description": "منظفات ومعقمات للمطبخ",
            "category": "supplies",
        })
        assert res["success"] is True

        res = client.call("get_expenses")
        assert res["success"] is True
        assert any(e["amount"] == 50.0 for e in res["data"])

        # ------------------------------------------------------------------
        # Step 7: Shift Close Guards (Cannot close with open orders)
        # ------------------------------------------------------------------
        # Start a new order on Table 8 and confirm it (open in-progress)
        res = client.call("new_order", {"order_type": "dine_in"})
        res = client.call("set_table", {"table_number": 8})
        res = client.call("add_item", {
            "product_id": pepsi["id"],
            "product_name": pepsi["name"],
            "unit_price": pepsi["price"],
            "quantity": 1,
        })
        res = client.call("confirm_order")
        open_order_id = res["data"]["order_id"]

        # Attempt to close shift before printing summary -> MUST FAIL (Guard 1)
        res = client.call("close_shift", {"manager_pin": "1234"})
        assert res["success"] is False
        assert "طباعة التقرير اليومي" in res["error"]

        # Print shift summary
        res = client.call("print_shift_summary")
        assert res["success"] is True

        # Now attempt to close shift while an order is open -> MUST FAIL (Guard 4: open orders)
        res = client.call("close_shift", {"manager_pin": "1234"})
        assert res["success"] is False
        assert "طلبات مفتوحة" in res["error"]

        # Cancel open order with manager PIN
        res = client.call("cancel_order", {
            "order_id": open_order_id,
            "reason": "الزبون غادر قبل استلام الطلب",
            "manager_pin": "1234",
        })
        assert res["success"] is True

        # ------------------------------------------------------------------
        # Step 8: Blind Cash Count & Manager Reconciliation
        # ------------------------------------------------------------------
        # As Cashier (Sara): sensitive totals are hidden for blind count security
        res = client.call("get_shift_summary")
        assert res["success"] is True
        cashier_summary = res["data"]
        assert "expected_cash" not in cashier_summary
        assert "total_sales" not in cashier_summary
        assert cashier_summary["total_expenses"] == 50.0

        # Print shift summary (simulating cashier pressing Print Daily Summary)
        res = client.call("print_shift_summary")
        assert res["success"] is True

        # Log out cashier, log in manager/admin to view full figures
        client.call("logout")
        client.call("login", {"pin": "1234"})

        # As Manager (Admin): full financial figures are revealed
        # Expected financial calculations:
        # Cash sales:
        #   Dine-In order = 235.00
        #   Delivery order = 125.00
        #   Total cash sales = 360.00
        # Card sales:
        #   Takeaway order = 75.00
        # Total sales = 435.00
        # Expenses: 50.00
        # Expected cash in drawer = cash_sales (360.00) - expenses (50.00) = 310.00
        res = client.call("get_shift_summary")
        assert res["success"] is True
        summary = res["data"]
        assert summary["cash_sales"] == 360.0
        assert summary["total_sales"] == 435.0
        assert summary["total_expenses"] == 50.0
        assert summary["expected_cash"] == 310.0

        # Manager closes shift
        res = client.call("close_shift")
        assert res["success"] is True

        # Active shift is now None
        res = client.call("get_active_shift")
        assert res["success"] is True
        assert res["data"] is None

        # ------------------------------------------------------------------
        # Step 9: Audit Logs & Reports Verification
        # ------------------------------------------------------------------
        # Verify manager can view audit logs
        res = client.call("get_audit_logs", {"limit": 50})
        assert res["success"] is True
        logs = res["data"]
        assert len(logs) > 0

        # Daily sales report
        res = client.call("get_report_daily_sales")
        assert res["success"] is True
        assert res["data"]["gross_revenue"] == 435.0
        assert res["data"]["sales_by_type"]["grand_total"]["count"] == 3
