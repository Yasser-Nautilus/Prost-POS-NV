"""
Discount computation policy — single source of truth.

Both OrderService (saved orders) and OrderController (in-memory orders)
use this function. This eliminates the duplicate, divergent implementations
that existed before B-05.

Design decisions (per plan):
- Flat discount > subtotal  → ValueError  (not silently capped)
- Percent > 100             → ValueError
- Negative values           → ValueError  (closes F-05 manipulation vector)
- Zero value                → ValueError  (almost certainly a UI mistake)
- Rounding: ROUND_HALF_UP to 2 decimal places (piastres)
"""

from decimal import ROUND_HALF_UP, Decimal


def compute_discount(subtotal: float, value: float, kind: str) -> float:
    """Compute the discount *amount* (in EGP) to subtract from subtotal.

    Args:
        subtotal: Order subtotal before discount (must be > 0).
        value:    The raw discount value entered by the manager.
        kind:     ``"flat"`` (EGP) or ``"percent"`` (0–100).

    Returns:
        The discount *amount* to apply, rounded to 2 decimal places.

    Raises:
        ValueError: If any input is invalid (wrong type, out of range, exceeds subtotal).
    """
    # --- type guard ---------------------------------------------------------
    if kind not in ("flat", "percent"):
        raise ValueError(
            f"نوع الخصم غير صحيح '{kind}' — يجب أن يكون 'flat' أو 'percent'"
        )

    if value is None:
        raise ValueError("قيمة الخصم مطلوبة")

    try:
        val = Decimal(str(value))
        sub = Decimal(str(subtotal))
    except Exception:
        raise ValueError("قيمة الخصم يجب أن تكون رقمًا")

    # --- sign guard (closes F-05) ------------------------------------------
    if val <= 0:
        raise ValueError("يجب أن تكون قيمة الخصم أكبر من صفر")

    # --- range guards -------------------------------------------------------
    if kind == "percent":
        if val > 100:
            raise ValueError("نسبة الخصم لا يمكن أن تتجاوز 100%")
        amount = sub * val / Decimal(100)
    else:  # flat
        if val > sub:
            raise ValueError(
                f"الخصم ({value} ج.م) لا يمكن أن يتجاوز إجمالي الطلب ({subtotal} ج.م)"
            )
        amount = val

    return float(amount.quantize(Decimal("0.01"), ROUND_HALF_UP))


def rescale_discount(
    discount_amount: float,
    kind: str | None,
    old_subtotal: float,
    new_subtotal: float,
) -> float:
    """Keep an existing discount valid after the order subtotal changed.

    Removing items must never leave a discount larger than the new subtotal
    (that made the order total negative).

    * ``percent`` discounts keep their original percentage of the subtotal.
    * ``flat`` (and unknown) discounts keep their amount, capped at the new
      subtotal.
    * An empty order has no discount.
    """
    disc = Decimal(str(discount_amount or 0))
    new_sub = Decimal(str(new_subtotal or 0))
    if disc <= 0 or new_sub <= 0:
        return 0.0
    if kind == "percent":
        old_sub = Decimal(str(old_subtotal or 0))
        if old_sub > 0:
            amount = new_sub * disc / old_sub
            amount = min(amount, new_sub)
            return float(amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
    return float(min(disc, new_sub).quantize(Decimal("0.01"), ROUND_HALF_UP))
