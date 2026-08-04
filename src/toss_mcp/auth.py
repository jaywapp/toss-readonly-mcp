"""OAuth 2.0 client-credentials token handling.

Toss keeps exactly one valid access token per client and invalidates the
previous one on re-issue. Two concurrent refreshes would therefore leave one
caller holding a dead token, so refreshes are serialised behind a lock.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

import httpx

from toss_mcp.config import Settings
from toss_mcp.errors import TossApiError, TossConnectionError
from toss_mcp.ratelimit import RateLimiter

logger = logging.getLogger(__name__)

# Refresh this many seconds before the token actually expires, so a request
# never sets off with a token that dies mid-flight.
REFRESH_MARGIN_SECONDS = 60


class TokenProvider:
    def __init__(
        self,
        settings: Settings,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._http = http
        self._limiter = limiter
        self._time = time_fn
        self._token: str | None = None
        self._expires_at: float = 0.0
        # Built lazily: the provider may be constructed outside a running loop.
        self._lock: asyncio.Lock | None = None

    def invalidate(self) -> None:
        """Drop the cached token so the next call fetches a fresh one."""
        self._token = None
        self._expires_at = 0.0

    async def get_token(self) -> str:
        if self._is_fresh():
            return self._token  # type: ignore[return-value]

        lock = self._get_lock()
        async with lock:
            # Another caller may have refreshed while we waited.
            if self._is_fresh():
                return self._token  # type: ignore[return-value]
            return await self._issue()

    def _is_fresh(self) -> bool:
        return self._token is not None and self._time() < self._expires_at

    def _get_lock(self) -> asyncio.Lock:
        # No await here, so this runs atomically with respect to other tasks.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _issue(self) -> str:
        client_id, client_secret = self._settings.require_credentials()
        await self._limiter.acquire("AUTH")

        url = f"{self._settings.api_base_url}/oauth2/token"
        try:
            response = await self._http.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._settings.http_timeout,
            )
        except httpx.HTTPError as exc:
            raise TossConnectionError(str(exc)) from exc

        if response.status_code != 200:
            raise TossApiError.from_response(response.status_code, _safe_json(response))

        body = _safe_json(response)
        token = body.get("access_token") if isinstance(body, dict) else None
        if not token:
            raise TossApiError(
                "invalid-token",
                "토큰 응답에 access_token이 없습니다.",
                status=response.status_code,
            )

        expires_in = _coerce_int(body.get("expires_in"), default=3600)
        self._token = str(token)
        self._expires_at = self._time() + max(0, expires_in - REFRESH_MARGIN_SECONDS)
        logger.info("issued Toss access token, expires_in=%ss", expires_in)
        return self._token


def _safe_json(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return None


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
