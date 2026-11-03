import pytest

from broast_pos.core.models.order import OrderType, PaymentMethod
from broast_pos.features.order_lifecycle.payment_coordinator import PaymentCoordinator


@pytest.fixture
def coordinator():
    return PaymentCoordinator()


def test_cash_exact_and_overpayment(coordinator):
    exact = coordinator.calculate(100, PaymentMethod.CASH, 100, OrderType.TAKEAWAY)
    over = coordinator.calculate(100, PaymentMethod.CASH, 125, OrderType.TAKEAWAY)

    assert exact.is_valid and exact.amount_paid == 100 and exact.change_given == 0
    assert over.is_valid and over.amount_paid == 125 and over.change_given == 25


def test_cash_underpayment_is_rejected(coordinator):
    result = coordinator.calculate(100, PaymentMethod.CASH, 99, OrderType.TAKEAWAY)

    assert not result.is_valid
    assert "أقل" in result.error


def test_visa_delivery_is_rejected(coordinator):
    result = coordinator.calculate(100, PaymentMethod.VISA, 100, OrderType.DELIVERY)

    assert not result.is_valid