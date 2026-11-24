"""
Customer service — phone-based lookup, address management, and zone config.

Exact phone match (11 digits, starts with "01") — no partial search.
Zone-based fixed delivery fees: fee comes from the zone at address creation
and is stored on the address for historical consistency.
"""

from __future__ import annotations

from typing import Any

from broast_pos.core.models.customer import Customer, CustomerAddress, Zone
from broast_pos.core.phone import INVALID_PHONE_MSG, normalize_egyptian_mobile
from broast_pos.data.repositories.customer_repository import CustomerRepository


class CustomerService:
    """Business logic for customer lookup, address management, and zones."""

    def __init__(
        self, customer_repo: CustomerRepository | None = None,
    ) -> None:
        self._customers = customer_repo or CustomerRepository()

    # ------------------------------------------------------------------
    # Phone-based lookup
    # ------------------------------------------------------------------

    def find_by_phone(self, phone: str) -> Customer | None:
        """Exact 11-digit phone match → customer with all addresses, or None."""
        phone = self._validate_phone(phone)
        return self._customers.find_by_phone(phone)

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

        phone = self._validate_phone(phone)

        # Check for duplicates
        existing = self._customers.find_by_phone(phone)
        if existing is not None:
            raise ValueError("رقم الهاتف مسجل بالفعل")

        customer = Customer(name=name, phone=phone)
        return self._customers.save(customer)

    # ------------------------------------------------------------------
    # Address management
    # ------------------------------------------------------------------

    def search_customers(self, query: str, limit: int = 20) -> list[Customer]:
        """Find customers by part of the name or phone. Empty query returns none."""
        query = (query or "").strip()
        if len(query) < 2:
            return []
        digits = normalize_egyptian_mobile(query)
        if digits is not None:
            query = digits
        return self._customers.search_customers(query, limit)

    def update_customer(
        self, customer_id: int, name: str | None = None, phone: str | None = None
    ) -> Customer:
        """Edit a customer's name and/or phone.

        Raises:
            ValueError: customer not found, empty name, invalid phone, or the
                phone already belongs to another customer.
        """
        customer = self._customers.get_by_id_simple(customer_id)
        if customer is None:
            raise ValueError("العميل غير موجود")
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("اسم العميل مطلوب")
            customer.name = name
        if phone is not None:
            normalized = self._validate_phone(phone)
            other = self._customers.find_by_phone(normalized)
            if other is not None and other.id != customer.id:
                raise ValueError("رقم الهاتف مسجل بالفعل")
            customer.phone = normalized
        self._customers.save_customer(customer)
        return self._customers.find_by_phone(customer.phone) or customer

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

    def get_addresses(self, customer_id: int) -> list[CustomerAddress]:
        """All saved addresses for a customer."""
        return self._customers.get_addresses(customer_id)

    def get_address(self, address_id: int) -> CustomerAddress | None:
        """A single saved address by id — authoritative zone/fee source."""
        return self._customers.get_address_by_id(address_id)

    def delete_address(self, address_id: int, customer_id: int | None = None) -> None:
        """Soft-delete an address.

        Raises:
            ValueError: if address not found.
        """
        self._customers.delete_address(address_id, customer_id)

    # ------------------------------------------------------------------
    # Customer lookup by ID
    # ------------------------------------------------------------------

    def get_customer_by_id(self, customer_id: int) -> Customer | None:
        """Fetch a customer by primary key (includes addresses)."""
        return self._customers.get_by_id(customer_id)

    # ------------------------------------------------------------------
    # Customer history and statistics (Phase 3)
    # ------------------------------------------------------------------

    def get_customer_history(
        self,
        customer_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Order history for a customer (newest first).

        Args:
            customer_id: The customer's primary key.
            limit: Maximum number of records to return.
            offset: Pagination offset.

        Returns:
            List of order dicts: invoice_no, status, total, created_at, …
        Raises:
            ValueError: if customer not found.
        """
        customer = self._customers.get_by_id(customer_id)
        if customer is None:
            raise ValueError("العميل غير موجود")
        return self._customers.get_customer_order_history(
            customer_id, limit=limit, offset=offset
        )

    def get_customer_statistics(self, customer_id: int) -> dict[str, Any]:
        """Aggregate stats for a customer.

        Returns dict with: total_orders, completed_orders, cancelled_orders,
        total_spent, avg_order_value, largest_order, first/last_order_at.
        Raises:
            ValueError: if customer not found.
        """
        customer = self._customers.get_by_id(customer_id)
        if customer is None:
            raise ValueError("العميل غير موجود")
        return self._customers.get_customer_statistics(customer_id)

    # ------------------------------------------------------------------
    # Zone management (manager only)
    # ------------------------------------------------------------------

    def get_all_zones(self) -> list[Zone]:
        """All zones (active and inactive) for management."""
        return self._customers.get_zones()

    def get_active_zones(self) -> list[Zone]:
        """All active zones for dropdown selection."""
        return self._customers.get_all_active_zones()

    def _ensure_zone_name_free(self, name: str, exclude_id: int | None = None) -> None:
        """Reject a zone name already used by another zone (case/space-insensitive)."""
        wanted = " ".join(name.split()).casefold()
        for z in self._customers.get_zones():
            if z.id != exclude_id and " ".join(z.name.split()).casefold() == wanted:
                raise ValueError("اسم المنطقة مستخدم بالفعل")

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

        self._ensure_zone_name_free(name)
        zone = Zone(name=name, delivery_fee=delivery_fee, is_active=True)
        return self._customers.save_zone(zone)

    def update_zone(
        self,
        zone_id: int,
        name: str | None = None,
        delivery_fee: float | None = None,
        is_active: bool | None = None,
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
            self._ensure_zone_name_free(name, exclude_id=zone_id)
            zone.name = name

        if delivery_fee is not None:
            if delivery_fee < 0:
                raise ValueError(
                    "رسوم التوصيل يجب أن تكون أكبر من أو تساوي صفر"
                )
            zone.delivery_fee = delivery_fee

        if is_active is not None:
            zone.is_active = is_active

        return self._customers.save_zone(zone)

    def deactivate_zone(self, zone_id: int) -> None:
        """Soft-delete a zone.

        Raises:
            ValueError: if zone not found.
        """
        zone = self._customers.get_zone_by_id(zone_id)
        if zone is None:
            raise ValueError("المنطقة غير موجودة")
        self._customers.deactivate_zone(zone_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_phone(phone: str) -> str:
        """Normalise and validate an Egyptian mobile number.

        Accepts pasted WhatsApp formats (+20, spaces, dashes) and returns the
        01XXXXXXXXX form with English digits.

        Raises:
            ValueError: if the number is not a valid Egyptian mobile.
        """
        normalized = normalize_egyptian_mobile(phone)
        if normalized is None:
            raise ValueError(INVALID_PHONE_MSG)
        return normalized
