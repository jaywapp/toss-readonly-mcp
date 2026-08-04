"""Shaping API payloads for LLM consumption.

Tool results land in the model's context, which is the one thing here that
costs money — so responses carry the fields a question actually needs and
nothing else.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

_SENTINEL = object()


def pick(data: Any, *keys: str) -> dict[str, Any]:
    """Keep only `keys` that are present, preserving explicit nulls."""
    if not isinstance(data, dict):
        return {}
    result = {}
    for key in keys:
        value = data.get(key, _SENTINEL)
        if value is not _SENTINEL:
            result[key] = value
    return result


def compute_change(last_price: Any, prev_close: Any) -> dict[str, str]:
    """Change and change rate versus the previous close.

    Returns {} when either side is unusable — a missing previous close is
    normal for a newly listed stock, not an error worth surfacing.
    """
    last = _to_decimal(last_price)
    prev = _to_decimal(prev_close)
    if last is None or prev is None or prev == 0:
        return {}

    change = last - prev
    rate = (change / prev) * 100

    return {
        "prevClose": _plain(prev),
        "change": _plain(change),
        "changeRate": f"{rate:.2f}",
    }


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def _plain(value: Decimal) -> str:
    """Render without scientific notation or a trailing exponent."""
    return format(value, "f")
