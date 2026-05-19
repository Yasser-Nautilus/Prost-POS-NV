"""
Payment coordinator — handles payment flow logic.

Encapsulates the rules for which payment methods are valid
per order type and calculates change. Keeps OrderController
focused on orchestration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

from broast_pos.core.models.order import OrderType, PaymentMethod

logger = logging.getLogger(__name__)


@dataclass
class PaymentResult:
    """Result of a payment calculation."""

    method: PaymentMethod
    total: float
    amount_paid: float
    change_given: float
    is_valid: bool
    error: str = ""


class PaymentCoordinator:
    """Validates payment methods and computes change."""

    # Payment methods allowed per order type
    ALLOWED_METHODS = {
        OrderType.DINE_IN: [PaymentMethod.CASH, PaymentMethod.VISA, PaymentMethod.ONLINE],
        OrderType.TAKEAWAY: [PaymentMethod.CASH, PaymentMethod.VISA, PaymentMethod.ONLINE],
        OrderType.DELIVERY: [PaymentMethod.CASH, PaymentMethod.ONLINE],  # No Visa
        OrderType.PICKUP: [PaymentMethod.CASH, PaymentMethod.VISA, PaymentMethod.ONLINE],
    }

    def get_allowed_methods(self, order_type: OrderType) -> List[PaymentMethod]:
        """Return valid payment methods for an order type."""
        return self.ALLOWED_METHODS.get(order_type, list(PaymentMethod))

    def is_method_allowed(
        self, order_type: OrderType, method: PaymentMethod
    ) -> bool:
        """Check if a payment method is valid for the order type."""
        allowed = self.get_allowed_methods(order_type)
        return method in allowed

    def calculate(
        self,
        total: float,
        method: PaymentMethod,
        amount_paid: float,
        order_type: OrderType,
    ) -> PaymentResult:
        """Validate and calculate payment.

        Args:
            total: Order grand total.
            method: Selected payment method.
            amount_paid: Amount received from customer.
            order_type: Order type for method validation.

        Returns:
            PaymentResult with change calculation or error.
        """
        # Validate method
        if not self.is_method_allowed(order_type, method):
            return PaymentResult(
                method=method,
                total=total,
                amount_paid=0,
                change_given=0,
                is_valid=False,
                error="طريقة الدفع غير مسموح بها لهذا النوع من الطلبات",
            )

        # For non-cash, paid = total
        if method in (PaymentMethod.VISA, PaymentMethod.ONLINE):
            return PaymentResult(
                method=method,
                total=total,
                amount_paid=total,
                change_given=0,
                is_valid=True,
            )

        # Cash — validate received amount
        if amount_paid < total:
            return PaymentResult(
                method=method,
                total=total,
                amount_paid=amount_paid,
                change_given=0,
                is_valid=False,
                error="المبلغ المدفوع أقل من الإجمالي",
            )

        change = round(amount_paid - total, 2)
        return PaymentResult(
            method=method,
            total=total,
            amount_paid=amount_paid,
            change_given=change,
            is_valid=True,
        )

    def get_quick_cash_amounts(self, total: float) -> List[float]:
        """Generate quick-cash button values.

        Returns amounts like: exact, round up to nearest 10, 50, 100.
        """
        amounts = [total]
        for step in [10, 20, 50, 100, 200, 500]:
            rounded = ((total // step) + 1) * step
            if rounded > total and rounded not in amounts:
                amounts.append(rounded)
        # Deduplicate and sort, max 6 buttons
        return sorted(set(amounts))[:6]
