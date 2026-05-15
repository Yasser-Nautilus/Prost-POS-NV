"""
Customer service — phone-based lookup, address management, and zone config.

Exact phone match (11 digits, starts with "01") — no partial search.
Zone-based fixed delivery fees: fee comes from the zone at address creation
and is stored on the address for historical consistency.
"""

from __future__ import annotations

import re
from typing import List, Optional

from broast_pos.core.models.customer import Customer, CustomerAddress, Zone
from broast_pos.data.repositories.customer_repository import CustomerRepository


_PHONE_PATTERN = re.compile(r"^01\d{9}$")


class CustomerService:
    """Business logic for customer lookup, address management, and zones."""

    def __init__(
        self, customer_repo: Optional[CustomerRepository] = None,
    ) -> None:
        self._customers = customer_repo or CustomerRepository()

    # ------------------------------------------------------------------
    # Phone-based lookup
    # ------------------------------------------------------------------

    def find_by_phone(self, phone: str) -> Optional[Customer]:
        """Exact 11-digit phone match → customer with all addresses, or None."""
        phone = phone.strip()
        self._validate_phone(phone)
        return self._customers.get_by_phone(phone)

    # ------------------------------------------------------------------
    # New customer flow
    # ------------------------------------------------------------------

    def create_customer(self, name: str, phone: str) -> Customer:
        """Create a new customer record.

        Raises:
            ValueError: if name is empty or phone is invalid/duplicate.
        """
        name = name.strip()
        if not name:
            raise ValueError("اسم العميل مطلوب")

        phone = phone.strip()
        self._validate_phone(phone)

        # Check for duplicates
        existing = self._customers.get_by_phone(phone)
        if existing is not None:
            raise ValueError("رقم الهاتف مسجل بالفعل")

        customer = Customer(name=name, phone=phone)
        return self._customers.save(customer)

    # ------------------------------------------------------------------
    # Address management
    # ------------------------------------------------------------------

    def add_address(
        self,
        customer_id: int,
        street_name: str,
        zone_id: int,
    ) -> CustomerAddress:
        """Add a new address to an existing customer.

        The delivery fee is copied from the zone at creation time and
        stored on the address — ensuring historical consistency.

        Raises:
            ValueError: if customer or zone not found, or street is empty.
        """
        customer = self._customers.get_by_id(customer_id)
        if customer is None:
            raise ValueError("العميل غير موجود")

        street_name = street_name.strip()
        if not street_name:
            raise ValueError("اسم الشارع مطلوب")

        zone = self._customers.get_zone_by_id(zone_id)
        if zone is None:
            raise ValueError("المنطقة غير موجودة")

        address = CustomerAddress(
            customer_id=customer_id,
            street_name=street_name,
            zone_id=zone_id,
            zone_name=zone.name,
            delivery_fee=zone.delivery_fee,
        )
        return self._customers.save_address(address)

    def get_addresses(self, customer_id: int) -> List[CustomerAddress]:
        """All saved addresses for a customer."""
        return self._customers.get_addresses(customer_id)

    def delete_address(self, address_id: int) -> None:
        """Soft-delete an address.

        Raises:
            ValueError: if address not found.
        """
        self._customers.delete_address(address_id)

    # ------------------------------------------------------------------
    # Zone management (manager only)
    # ------------------------------------------------------------------

    def get_all_zones(self) -> List[Zone]:
        """All active zones for dropdown selection."""
        return self._customers.get_zones()

    def create_zone(self, name: str, delivery_fee: float) -> Zone:
        """Create a new delivery zone.

        Raises:
            ValueError: if name is empty or fee is negative.
        """
        name = name.strip()
        if not name:
            raise ValueError("اسم المنطقة مطلوب")
        if delivery_fee < 0:
            raise ValueError("رسوم التوصيل يجب أن تكون أكبر من أو تساوي صفر")

        zone = Zone(name=name, delivery_fee=delivery_fee, is_active=True)
        return self._customers.save_zone(zone)

    def update_zone(
        self,
        zone_id: int,
        name: Optional[str] = None,
        delivery_fee: Optional[float] = None,
    ) -> Zone:
        """Update an existing zone.

        Note: changing the fee does NOT affect existing addresses —
        they retain the fee stored at creation time.

        Raises:
            ValueError: if zone not found.
        """
        zone = self._customers.get_zone_by_id(zone_id)
        if zone is None:
            raise ValueError("المنطقة غير موجودة")

        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("اسم المنطقة مطلوب")
            zone.name = name

        if delivery_fee is not None:
            if delivery_fee < 0:
                raise ValueError(
                    "رسوم التوصيل يجب أن تكون أكبر من أو تساوي صفر"
                )
            zone.delivery_fee = delivery_fee

        return self._customers.save_zone(zone)

    def deactivate_zone(self, zone_id: int) -> None:
        """Soft-delete a zone.

        Raises:
            ValueError: if zone not found.
        """
        zone = self._customers.get_zone_by_id(zone_id)
        if zone is None:
            raise ValueError("المنطقة غير موجودة")
        self._customers.delete_zone(zone_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_phone(phone: str) -> None:
        """Enforce 11-digit phone starting with '01'.

        Raises:
            ValueError: if format is invalid.
        """
        if not _PHONE_PATTERN.match(phone):
            raise ValueError("رقم الهاتف يجب أن يكون 11 رقم ويبدأ بـ 01")
