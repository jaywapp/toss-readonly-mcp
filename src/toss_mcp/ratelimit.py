"""Client-side token buckets, one per Toss rate-limit group.

Throttling before we send is cheaper than absorbing 429s: the server counts a
rejected request against us anyway, and the retry costs a round trip.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

# Requests per second, from the Toss Open API docs.
GROUP_LIMITS: dict[str, int] = {
    "AUTH": 5,
    "MARKET_DATA": 10,
    "MARKET_DATA_CHART": 5,
    "STOCK": 5,
    "MARKET_INFO": 3,
}

# Used for groups Toss adds after this was written.
DEFAULT_LIMIT = 5


class _Bucket:
    __slots__ = ("capacity", "tokens", "updated_at", "lock")

    def __init__(self, capacity: int, now: float) -> None:
        self.capacity = capacity
        self.tokens = float(capacity)
        self.updated_at = now
        self.lock = asyncio.Lock()


class RateLimiter:
    """Per-group token bucket. Clock and sleep are injectable for testing."""

    def __init__(
        self,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._time = time_fn
        self._sleep = sleep_fn
        self._buckets: dict[str, _Bucket] = {}

    async def acquire(self, group: str) -> None:
        bucket = self._buckets.get(group)
        if bucket is None:
            capacity = GROUP_LIMITS.get(group, DEFAULT_LIMIT)
            bucket = self._buckets[group] = _Bucket(capacity, self._time())

        async with bucket.lock:
            self._refill(bucket)
            if bucket.tokens < 1.0:
                # Refill runs at `capacity` tokens/sec, so this is the wait for
                # the fraction of a token we still need.
                deficit = 1.0 - bucket.tokens
                await self._sleep(deficit / bucket.capacity)
                self._refill(bucket)
            bucket.tokens -= 1.0

    def _refill(self, bucket: _Bucket) -> None:
        now = self._time()
        elapsed = now - bucket.updated_at
        if elapsed > 0:
            bucket.tokens = min(
                float(bucket.capacity),
                bucket.tokens + elapsed * bucket.capacity,
            )
            bucket.updated_at = now
