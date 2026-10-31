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

from decimal import Decimal, ROUND_HALF_UP


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
        amount = sub * val / Decimal("100")
    else:  # flat
        if val > sub:
            raise ValueError(
                f"الخصم ({value} ج.م) لا يمكن أن يتجاوز إجمالي الطلب ({subtotal} ج.م)"
            )
        amount = val

    return float(amount.quantize(Decimal("0.01"), ROUND_HALF_UP))
