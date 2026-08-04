"""HTTP access to the Toss Open API.

Owns authentication, rate limiting, and retries so the tool layer can treat a
call as "give me the result or raise something I can explain".
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from toss_mcp.auth import TokenProvider
from toss_mcp.config import Settings, get_settings
from toss_mcp.errors import TossApiError, TossConnectionError
from toss_mcp.ratelimit import RateLimiter

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_RETRIES = 3
RATE_LIMIT_CODES = {"rate-limit-exceeded", "edge-rate-limit-exceeded"}


class TossClient:
    def __init__(
        self,
        settings: Settings | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings or get_settings()
        self._sleep = sleep_fn
        self._http = httpx.AsyncClient(timeout=self._settings.http_timeout)
        self._limiter = RateLimiter()
        self._tokens = TokenProvider(self._settings, self._http, self._limiter)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(
        self,
        path: str,
        group: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """GET `path` and return the envelope's `result`.

        Raises TossApiError or TossConnectionError; never returns an error shape.
        """
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self._settings.api_base_url}{path}"

        auth_retried = False
        rate_limit_attempts = 0

        while True:
            await self._limiter.acquire(group)
            token = await self._tokens.get_token()
            response = await self._send(url, query, token)

            if response.status_code == 200:
                return _unwrap(response)

            body = _safe_json(response)
            error = TossApiError.from_response(response.status_code, body)

            if response.status_code == 401 and not auth_retried:
                # The token may have been invalidated server-side (Toss keeps
                # one per client). Re-issue once before giving up.
                logger.info("token rejected, re-issuing once")
                auth_retried = True
                self._tokens.invalidate()
                continue

            if response.status_code == 429 and rate_limit_attempts < MAX_RATE_LIMIT_RETRIES:
                delay = _retry_delay(response, rate_limit_attempts)
                logger.info("rate limited, retrying in %.2fs", delay)
                rate_limit_attempts += 1
                await self._sleep(delay)
                continue

            raise error

    async def _send(self, url: str, params: dict[str, Any], token: str) -> httpx.Response:
        try:
            return await self._http.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise TossConnectionError(str(exc)) from exc


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Retry-After if the server sent one, else exponential backoff + jitter."""
    header = response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return (2**attempt) * (1.0 + random.random())


def _unwrap(response: httpx.Response) -> Any:
    body = _safe_json(response)
    if not isinstance(body, dict) or "result" not in body:
        raise TossApiError(
            "invalid-response",
            "예상과 다른 응답 형식입니다.",
            status=response.status_code,
        )
    return body["result"]


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


_client: TossClient | None = None


def get_client() -> TossClient:
    """Process-wide client, built on first use."""
    global _client
    if _client is None:
        _client = TossClient()
    return _client
