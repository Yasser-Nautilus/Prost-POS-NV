"""
Regression tests — H19: the backend accepted client-selected catalogue
prices.

Root cause:
  OrderController.add_item() built an OrderItem from the caller-supplied
  product_name/unit_price directly, with no lookup against the product
  catalogue. A client could set any product_id with a price of its choosing.
  set_customer_info() had the same problem for delivery_fee — the client's
  number was stored verbatim with no zone lookup.

Fix verified here:
  - add_item() always resolves name/price from the product catalogue by
    product_id; a manipulated client price/name is silently discarded.
  - add_item() rejects an inactive or unknown product_id.
  - set_customer_info() resolves zone/delivery_fee from the customer's
    saved address (address_id) on the backend; a manipulated client fee
    for a known address is discarded in favour of the real fee.
  - Omitting address_id (e.g. a payment-method-only re-send) preserves
    the order's already-resolved zone/fee rather than trusting the client.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from broast_pos.core.services.order_service import OrderService
from broast_pos.features.order_lifecycle.order_controller import OrderController
from broast_pos.infrastructure.printing.print_triggers import PrintTriggers


def _build_ctrl(product=None, address=None):
    order_repo = MagicMock(**{"save.side_effect": lambda o: o})
    svc = OrderService(order_repo=order_repo)

    products = MagicMock()
    products.get_product.return_value = product

    customers = MagicMock()
    customers.get_address.return_value = address

    ctrl = OrderController(
        order_service=svc,
        financial_service=MagicMock(),
        auth_service=MagicMock(),
        print_triggers=MagicMock(spec=PrintTriggers),
        product_service=products,
        customer_service=customers,
    )
    return ctrl


class TestH19ProductPriceFromCatalogue:

    def test_manipulated_client_price_is_discarded(self):
        """A client sending unit_price=0 for an active EGP 70 product must
        still be charged the real catalogue price."""
        real_product = SimpleNamespace(id=5, name="برجر", price=70.0, is_active=True)
        ctrl = _build_ctrl(product=real_product)
        ctrl.new_order("takeaway")

        ctrl.add_item(product_id=5, product_name="برجر مجاني", unit_price=0.0, quantity=1)

        item = ctrl._current_order.items[0]
        assert item.unit_price == 70.0, "H19 regression: client-supplied price was used"
        assert item.product_name == "برجر"

    def test_manipulated_client_name_is_discarded(self):
        real_product = SimpleNamespace(id=5, name="برجر", price=70.0, is_active=True)
        ctrl = _build_ctrl(product=real_product)
        ctrl.new_order("takeaway")

        ctrl.add_item(product_id=5, product_name="اسم مزور", unit_price=70.0, quantity=1)

        assert ctrl._current_order.items[0].product_name == "برجر"

    def test_unknown_product_id_rejected(self):
        ctrl = _build_ctrl(product=None)
        ctrl.new_order("takeaway")

        with pytest.raises(ValueError):
            ctrl.add_item(product_id=999, product_name="x", unit_price=1.0)

        assert ctrl._current_order.items == []

    def test_inactive_product_rejected(self):
        inactive_product = SimpleNamespace(id=5, name="برجر", price=70.0, is_active=False)
        ctrl = _build_ctrl(product=inactive_product)
        ctrl.new_order("takeaway")

        with pytest.raises(ValueError):
            ctrl.add_item(product_id=5, product_name="برجر", unit_price=70.0)

        assert ctrl._current_order.items == []

    def test_no_product_service_wired_raises_instead_of_trusting_client(self):
        order_repo = MagicMock(**{"save.side_effect": lambda o: o})
        svc = OrderService(order_repo=order_repo)
        ctrl = OrderController(
            order_service=svc,
            financial_service=MagicMock(),
            auth_service=MagicMock(),
            print_triggers=MagicMock(spec=PrintTriggers),
        )
        ctrl.new_order("takeaway")

        with pytest.raises(ValueError):
            ctrl.add_item(product_id=5, product_name="برجر", unit_price=70.0)


class TestH19DeliveryFeeFromZone:

    def test_manipulated_client_delivery_fee_is_discarded(self):
        """A client sending delivery_fee=1.0 for a 25 EGP zone address must
        still be charged the real zone fee."""
        real_address = MagicMock(customer_id=1, zone_name="الغابة", delivery_fee=25.0)
        ctrl = _build_ctrl(address=real_address)
        ctrl.new_order("delivery")

        ctrl.set_customer_info(
            customer_id=1, name="عميل", phone="010", address="شارع 1",
            zone="منطقة مزورة", delivery_fee=1.0, address_id=42,
        )

        assert ctrl._current_order.delivery_fee == 25.0, (
            "H19 regression: client-supplied delivery fee was used"
        )
        assert ctrl._current_order.customer_zone == "الغابة"

    def test_unknown_or_mismatched_address_rejected(self):
        ctrl = _build_ctrl(address=None)
        ctrl.new_order("delivery")

        with pytest.raises(ValueError):
            ctrl.set_customer_info(
                customer_id=1, name="عميل", phone="010",
                delivery_fee=1.0, address_id=999,
            )

    def test_address_belonging_to_different_customer_rejected(self):
        someone_elses_address = MagicMock(customer_id=2, zone_name="الغابة", delivery_fee=25.0)
        ctrl = _build_ctrl(address=someone_elses_address)
        ctrl.new_order("delivery")

        with pytest.raises(ValueError):
            ctrl.set_customer_info(
                customer_id=1, name="عميل", phone="010",
                delivery_fee=1.0, address_id=42,
            )

    def test_payment_method_resend_keeps_resolved_fee(self):
        """Re-sending without address_id (payment-mode toggle) must not
        let a client reset the already-resolved fee to its own number."""
        real_address = MagicMock(customer_id=1, zone_name="الغابة", delivery_fee=25.0)
        ctrl = _build_ctrl(address=real_address)
        ctrl.new_order("delivery")
        ctrl.set_customer_info(
            customer_id=1, name="عميل", phone="010", address="شارع 1",
            address_id=42, payment_method="cash",
        )
        assert ctrl._current_order.delivery_fee == 25.0

        # Re-send with a manipulated fee and no address_id (as the payment
        # toggle buttons do) — must keep the already-resolved real fee.
        ctrl.set_customer_info(
            customer_id=1, name="عميل", phone="010", address="شارع 1",
            delivery_fee=0.01, payment_method="online",
        )
        assert ctrl._current_order.delivery_fee == 25.0
        assert ctrl._current_order.payment_method.value == "online"

    def test_pickup_order_defaults_to_zero_fee(self):
        ctrl = _build_ctrl()
        ctrl.new_order("pickup")

        ctrl.set_customer_info(
            customer_id=1, name="عميل", phone="010", address="استلام محل",
            delivery_fee=99.0,  # manipulated, no address_id
        )

        assert ctrl._current_order.delivery_fee == 0.0
