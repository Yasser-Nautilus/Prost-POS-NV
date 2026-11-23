"""Boundary checks for unit counts and physical cash, never truthiness defaults."""
from __future__ import annotations

import math


def unit_count(value: object, *, positive: bool = True) -> int:
    if type(value) is not int or (positive and value <= 0):
        raise ValueError("الكمية يجب أن تكون عدداً صحيحاً موجباً")
    return value


def cash_amount(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("المبلغ يجب أن يكون رقماً صالحاً غير سالب")
    return value


def cash_piasters(value: object) -> int:
    if isinstance(value, (int, float)) and value < 0:
        raise ValueError("المبلغ لا يمكن أن يكون سالباً")
    if type(value) is not int:
        raise ValueError("المبلغ المعدود يجب أن يكون عدداً صحيحاً غير سالب من القروش")
    return value
