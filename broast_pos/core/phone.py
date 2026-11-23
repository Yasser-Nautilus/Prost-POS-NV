"""Phone number normalisation for Egyptian mobile numbers.

Customers often paste numbers copied from WhatsApp ("+20 101 234 5678",
"0101-234-5678"). Everything is normalised to the local 11 digit form
01XXXXXXXXX written with English digits only.
"""
from __future__ import annotations

import re

_MOBILE = re.compile(r"^01[0125][0-9]{8}$", re.ASCII)
_SEPARATORS = " \t-().\u200e\u200f\u202a\u202b\u202c\u00a0"

INVALID_PHONE_MSG = "رقم الهاتف يجب أن يكون 11 رقم ويبدأ بـ 010 أو 011 أو 012 أو 015"


def normalize_egyptian_mobile(raw: str | None) -> str | None:
    """Return the normalised 01XXXXXXXXX number, or None when it is not valid.

    Accepts spaces, dashes, brackets, a leading + and the country code
    (+20 / 0020 / 20). Non-English digits are rejected on purpose.
    """
    if raw is None:
        return None
    cleaned = "".join(ch for ch in str(raw) if ch not in _SEPARATORS)
    if not cleaned:
        return None
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
        if not cleaned.startswith("20"):
            return None
        cleaned = cleaned[2:]
        if len(cleaned) == 10 and cleaned[0] == "1":
            cleaned = "0" + cleaned
    elif cleaned.startswith("0020"):
        cleaned = cleaned[4:]
        if len(cleaned) == 10 and cleaned[0] == "1":
            cleaned = "0" + cleaned
    elif cleaned.startswith("20") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    return cleaned if _MOBILE.match(cleaned) else None
