"""MCP tool definitions, one module per Toss API domain."""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from mcp.types import ToolAnnotations

from toss_mcp.errors import ConfigError, TossApiError, TossConnectionError

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Every tool here only reads. Telling the client that lets it skip approval
# prompts a mutating tool would deserve.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)


class ToolInputError(Exception):
    """The caller passed an argument the API would reject anyway."""


def tool_errors(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Turn exceptions into an `error` field.

    An MCP tool that raises gives the model a stack trace; one that returns
    `{"error": "..."}` gives it something to act on.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except ToolInputError as exc:
            return {"error": str(exc)}
        except ConfigError as exc:
            return {"error": str(exc)}
        except (TossApiError, TossConnectionError) as exc:
            return {"error": exc.user_message()}
        except Exception as exc:  # noqa: BLE001 - the tool boundary is the last line of defence
            logger.exception("unexpected failure in %s", func.__name__)
            return {"error": f"예기치 못한 오류가 발생했습니다: {type(exc).__name__}: {exc}"}

    return wrapper


def require_choice(value: str, allowed: set[str], field: str) -> str:
    """Normalise to upper case and reject anything the API would refuse."""
    normalised = (value or "").strip().upper()
    if normalised not in allowed:
        raise ToolInputError(
            f"{field}는 {', '.join(sorted(allowed))} 중 하나여야 합니다. 받은 값: {value!r}"
        )
    return normalised


def require_exact(value: str, allowed: set[str], field: str) -> str:
    """Same, but for case-sensitive enums such as the candle interval."""
    normalised = (value or "").strip()
    if normalised not in allowed:
        raise ToolInputError(
            f"{field}는 {', '.join(sorted(allowed))} 중 하나여야 합니다. 받은 값: {value!r}"
        )
    return normalised


def require_range(value: int, low: int, high: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise ToolInputError(f"{field}는 {low}~{high} 사이여야 합니다. 받은 값: {value!r}")
    return value


def parse_symbols(symbols: str, limit: int = 200) -> list[str]:
    """Split a comma-separated symbol list and validate its size."""
    parsed = [s.strip() for s in (symbols or "").split(",") if s.strip()]
    if not parsed:
        raise ToolInputError("symbols에 최소 한 개의 종목 심볼이 필요합니다.")
    if len(parsed) > limit:
        raise ToolInputError(f"symbols는 최대 {limit}개까지 조회할 수 있습니다. 받은 개수: {len(parsed)}")
    return parsed
