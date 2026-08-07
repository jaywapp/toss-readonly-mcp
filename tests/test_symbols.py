import asyncio

import pytest

from toss_mcp.config import Settings
from toss_mcp.symbols import SymbolRecord, SymbolStore

KRX = [
    SymbolRecord("005930", "삼성전자", None, "KOSPI"),
    SymbolRecord("005935", "삼성전자우", None, "KOSPI"),
    SymbolRecord("028260", "삼성물산", None, "KOSPI"),
    SymbolRecord("000660", "SK하이닉스", None, "KOSPI"),
    SymbolRecord("035720", "카카오", None, "KOSPI"),
    SymbolRecord("323410", "카카오뱅크", None, "KOSPI"),
]
NASDAQ = [
    SymbolRecord("AAPL", "Apple Inc", "Apple Inc", "NASDAQ"),
    SymbolRecord("NVDA", "NVIDIA Corp", "NVIDIA Corp", "NASDAQ"),
]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("TOSS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TOSS_SYMBOL_MARKETS", "KRX,NASDAQ")
    return Settings(_env_file=None)


class CountingFetcher:
    def __init__(self):
        self.calls = []

    def __call__(self, market):
        self.calls.append(market)
        return {"KRX": KRX, "NASDAQ": NASDAQ}.get(market, [])


@pytest.fixture
def fetcher():
    return CountingFetcher()


@pytest.fixture
def store(settings, fetcher):
    return SymbolStore(settings, fetcher=fetcher)


async def test_exact_symbol_wins(store):
    results = await store.search("005930")

    assert results[0].symbol == "005930"


async def test_exact_name_beats_prefix(store):
    results = await store.search("삼성전자")

    assert results[0].name == "삼성전자"


async def test_prefix_matches_come_back_for_partial_names(store):
    names = [r.name for r in await store.search("삼성")]

    assert "삼성전자" in names
    assert "삼성물산" in names


async def test_common_share_ranks_above_preferred(store):
    names = [r.name for r in await store.search("삼성")]

    assert names.index("삼성전자") < names.index("삼성전자우")


async def test_shorter_name_ranks_first_within_a_tier(store):
    names = [r.name for r in await store.search("카카")]

    assert names[0] == "카카오"
    assert "카카오뱅크" in names


async def test_an_exact_name_does_not_drag_in_looser_matches(store):
    """Asking for 삼성전자 should not also return 삼성전자우 and 삼성물산."""
    assert [r.name for r in await store.search("삼성전자")] == ["삼성전자"]


async def test_symbol_lookup_is_case_insensitive(store):
    results = await store.search("aapl")

    assert results[0].symbol == "AAPL"


async def test_english_name_is_searchable(store):
    results = await store.search("Apple")

    assert results[0].symbol == "AAPL"


async def test_market_filter(store):
    results = await store.search("a", market="NASDAQ")

    assert results, "expected NASDAQ matches"
    assert all(r.market == "NASDAQ" for r in results)


async def test_limit_is_respected(store):
    assert len(await store.search("삼성", limit=1)) == 1


async def test_no_match_returns_empty(store):
    assert await store.search("존재하지않는종목명") == []


async def test_fetches_once_and_reuses_the_cache(store, fetcher):
    await store.search("삼성전자")
    await store.search("카카오")

    assert fetcher.calls == ["KRX", "NASDAQ"], "second search must hit the cache"


async def test_concurrent_first_searches_fetch_only_once(store, fetcher):
    await asyncio.gather(*(store.search("삼성전자") for _ in range(8)))

    assert fetcher.calls == ["KRX", "NASDAQ"]


async def test_stale_cache_is_refetched(settings, fetcher, monkeypatch):
    store = SymbolStore(settings, fetcher=fetcher)
    await store.search("삼성전자")
    assert len(fetcher.calls) == 2

    # A new store on the same cache dir, with the data aged past the TTL.
    stale = SymbolStore(settings, fetcher=fetcher)
    stale._age_days = lambda: settings.symbol_ttl_days + 1  # noqa: SLF001
    await stale.search("삼성전자")

    assert len(fetcher.calls) == 4


async def test_fresh_cache_survives_a_new_store(settings, fetcher):
    await SymbolStore(settings, fetcher=fetcher).search("삼성전자")
    await SymbolStore(settings, fetcher=fetcher).search("삼성전자")

    assert len(fetcher.calls) == 2, "a fresh cache must not trigger a refetch"


async def test_refresh_reports_what_it_loaded(store):
    summary = await store.refresh()

    assert summary["count"] == len(KRX) + len(NASDAQ)
    assert summary["markets"] == ["KRX", "NASDAQ"]
    assert summary["updated_at"]


async def test_name_for_and_names_for(store):
    assert await store.name_for("005930") == "삼성전자"
    assert await store.name_for("999999") is None

    names = await store.names_for(["005930", "AAPL", "999999"])
    assert names == {"005930": "삼성전자", "AAPL": "Apple Inc"}


async def test_a_failing_market_does_not_sink_the_others(settings):
    def flaky(market):
        if market == "KRX":
            raise RuntimeError("upstream down")
        return NASDAQ

    store = SymbolStore(settings, fetcher=flaky)
    results = await store.search("AAPL")

    assert results[0].symbol == "AAPL"


async def test_all_markets_failing_surfaces_an_error(settings):
    def broken(market):
        raise RuntimeError("upstream down")

    store = SymbolStore(settings, fetcher=broken)

    with pytest.raises(RuntimeError):
        await store.search("삼성전자")
