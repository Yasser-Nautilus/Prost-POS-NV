"""
Tests for DLV-001 — backend driver-availability enforcement in create_trip.

These tests verify that DeliveryService.create_trip is the authoritative
guard, not the frontend filter. Mocks are used throughout so no DB is needed.
"""
import pytest
from unittest.mock import MagicMock

from broast_pos.core.models.delivery import DriverStatus, DeliveryTrip
from broast_pos.core.models.order import OrderStatus, OrderType
from broast_pos.core.services.delivery_service import DeliveryService


def _make_service(driver_status=DriverStatus.AVAILABLE, trip_for_order=None):
    """Return a DeliveryService wired with mocked repositories."""
    delivery_repo = MagicMock()
    delivery_repo.get_driver_status.return_value = driver_status
    delivery_repo.get_trip_for_order.return_value = trip_for_order
    delivery_repo.create_trip.return_value = DeliveryTrip(
        id=1, driver_id=10, driver_name="Test Driver", order_ids=[101]
    )

    order_repo = MagicMock()
    stub_order = MagicMock()
    stub_order.id = 101
    stub_order.order_type = OrderType.DELIVERY
    stub_order.status = OrderStatus.NEW
    order_repo.get_by_id.return_value = stub_order

    user_repo = MagicMock()
    stub_user = MagicMock()
    stub_user.display_name = "Test Driver"
    user_repo.get_by_id.return_value = stub_user

    return DeliveryService(
        delivery_repo=delivery_repo,
        order_repo=order_repo,
        user_repo=user_repo,
    )


class TestCreateTripDriverGuards:

    def test_succeeds_when_driver_available(self):
        svc = _make_service(driver_status=DriverStatus.AVAILABLE, trip_for_order=None)
        trip = svc.create_trip(driver_id=10, order_ids=[101])
        assert trip.id == 1

    def test_raises_when_driver_out(self):
        svc = _make_service(driver_status=DriverStatus.OUT)
        with pytest.raises(ValueError, match="رحلة توصيل حالياً"):
            svc.create_trip(driver_id=10, order_ids=[101])

    def test_raises_when_driver_checked_out(self):
        svc = _make_service(driver_status=DriverStatus.CHECKED_OUT)
        with pytest.raises(ValueError, match="غير مسجل حضور"):
            svc.create_trip(driver_id=10, order_ids=[101])

    def test_raises_when_order_already_on_trip(self):
        existing_trip = DeliveryTrip(id=99, driver_id=5, order_ids=[101])
        svc = _make_service(
            driver_status=DriverStatus.AVAILABLE,
            trip_for_order=existing_trip,
        )
        with pytest.raises(ValueError, match="مسند بالفعل"):
            svc.create_trip(driver_id=10, order_ids=[101])

    def test_raises_with_empty_order_list(self):
        svc = _make_service(driver_status=DriverStatus.AVAILABLE)
        with pytest.raises(ValueError, match="يجب اختيار"):
            svc.create_trip(driver_id=10, order_ids=[])

    def test_raises_when_order_not_found(self):
        svc = _make_service(driver_status=DriverStatus.AVAILABLE)
        svc._orders.get_by_id.return_value = None
        with pytest.raises(ValueError, match="غير موجود"):
            svc.create_trip(driver_id=10, order_ids=[999])

    def test_driver_guard_fires_before_order_validation(self):
        """Driver OUT guard must short-circuit before order DB lookup."""
        svc = _make_service(driver_status=DriverStatus.OUT)
        svc._orders.get_by_id.return_value = None
        with pytest.raises(ValueError, match="رحلة توصيل حالياً"):
            svc.create_trip(driver_id=10, order_ids=[999])

    def test_rejects_duplicate_order_ids(self):
        svc = _make_service(driver_status=DriverStatus.AVAILABLE)
        with pytest.raises(ValueError, match="تكرار الطلب"):
            svc.create_trip(driver_id=10, order_ids=[101, 101])
