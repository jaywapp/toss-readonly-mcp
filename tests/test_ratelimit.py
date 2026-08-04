import pytest

from toss_mcp.ratelimit import GROUP_LIMITS, RateLimiter


class FakeClock:
    """Virtual time, so the tests never actually wait."""

    def __init__(self):
        self.now = 0.0
        self.slept = []

    def time(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(clock):
    return RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)


async def test_burst_up_to_the_limit_does_not_wait(limiter, clock):
    for _ in range(GROUP_LIMITS["MARKET_DATA"]):
        await limiter.acquire("MARKET_DATA")

    assert clock.slept == []


async def test_exceeding_the_limit_waits(limiter, clock):
    for _ in range(GROUP_LIMITS["MARKET_DATA"]):
        await limiter.acquire("MARKET_DATA")

    await limiter.acquire("MARKET_DATA")

    assert clock.slept, "the 11th call in the same second should have waited"
    assert clock.slept[0] == pytest.approx(1 / GROUP_LIMITS["MARKET_DATA"], rel=1e-3)


async def test_groups_have_independent_buckets(limiter, clock):
    for _ in range(GROUP_LIMITS["MARKET_DATA"]):
        await limiter.acquire("MARKET_DATA")

    await limiter.acquire("STOCK")

    assert clock.slept == [], "draining MARKET_DATA must not throttle STOCK"


async def test_bucket_refills_over_time(limiter, clock):
    for _ in range(GROUP_LIMITS["MARKET_INFO"]):
        await limiter.acquire("MARKET_INFO")

    clock.now += 1.0
    await limiter.acquire("MARKET_INFO")

    assert clock.slept == []


async def test_bucket_does_not_refill_beyond_capacity(limiter, clock):
    await limiter.acquire("MARKET_INFO")
    clock.now += 3600.0

    for _ in range(GROUP_LIMITS["MARKET_INFO"]):
        await limiter.acquire("MARKET_INFO")
    await limiter.acquire("MARKET_INFO")

    assert clock.slept, "an hour idle must not grant more than one full bucket"


async def test_unknown_group_gets_a_conservative_default(limiter, clock):
    for _ in range(5):
        await limiter.acquire("SOMETHING_NEW")

    assert clock.slept == []

    await limiter.acquire("SOMETHING_NEW")
    assert clock.slept


def test_known_groups_match_the_published_limits():
    assert GROUP_LIMITS == {
        "AUTH": 5,
        "MARKET_DATA": 10,
        "MARKET_DATA_CHART": 5,
        "STOCK": 5,
        "MARKET_INFO": 3,
        "RANKING": 5,
        "MARKET_INDICATOR": 5,
    }
