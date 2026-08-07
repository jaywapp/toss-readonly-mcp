"""Live API checks. Skipped unless credentials are configured.

Run with: uv run pytest -m smoke -v
"""

from __future__ import annotations

import pytest
from conftest import call

from toss_mcp.client import TossClient
from toss_mcp.config import Settings
from toss_mcp.server import build_server
from toss_mcp.symbols import SymbolStore

pytestmark = pytest.mark.smoke


@pytest.fixture(scope="module")
def live_settings():
    settings = Settings()
    if not (settings.client_id and settings.client_secret):
        pytest.skip("TOSS_CLIENT_ID/TOSS_CLIENT_SECRET not configured")
    return settings


@pytest.fixture
async def live_server(live_settings):
    client = TossClient(live_settings)
    server = build_server(live_settings, client, SymbolStore(live_settings))
    try:
        yield server
    finally:
        await client.aclose()


async def test_price_of_samsung(live_server):
    result = await call(live_server, "get_price", symbols="005930")

    assert "error" not in result, result
    assert result["prices"][0]["symbol"] == "005930"
    assert result["prices"][0]["lastPrice"]


async def test_price_with_change(live_server):
    result = await call(live_server, "get_price", symbols="005930", include_change=True)

    assert "error" not in result, result
    assert "changeRate" in result["prices"][0], result


async def test_stock_info(live_server):
    result = await call(live_server, "get_stock_info", symbols="005930,AAPL")

    assert "error" not in result, result
    assert {s["symbol"] for s in result["stocks"]} == {"005930", "AAPL"}


async def test_candles(live_server):
    result = await call(live_server, "get_candles", symbol="005930", interval="1d", count=5)

    assert "error" not in result, result
    assert len(result["candles"]) >= 1


async def test_orderbook(live_server):
    result = await call(live_server, "get_orderbook", symbol="005930")

    assert "error" not in result, result


async def test_trades(live_server):
    result = await call(live_server, "get_trades", symbol="005930", count=3)

    assert "error" not in result, result


async def test_price_limits(live_server):
    result = await call(live_server, "get_price_limits", symbol="005930")

    assert "error" not in result, result


async def test_stock_warnings(live_server):
    result = await call(live_server, "get_stock_warnings", symbol="005930")

    assert "error" not in result, result


async def test_exchange_rate(live_server):
    result = await call(live_server, "get_exchange_rate")

    assert "error" not in result, result
    assert result["rate"]


async def test_market_calendar_kr(live_server):
    result = await call(live_server, "get_market_calendar", country="KR")

    assert "error" not in result, result


async def test_market_calendar_us(live_server):
    result = await call(live_server, "get_market_calendar", country="US")

    assert "error" not in result, result


async def test_rankings(live_server):
    result = await call(live_server, "get_rankings", type="TOP_GAINERS", duration="1d", count=5)

    assert "error" not in result, result


async def test_market_indicators(live_server):
    result = await call(live_server, "get_market_indicators", symbols="KOSPI,KOSDAQ")

    assert "error" not in result, result
    assert len(result["indicators"]) == 2


async def test_search_symbol_against_the_real_listing(live_server):
    result = await call(live_server, "search_symbol", query="삼성전자")

    assert result["results"][0]["symbol"] == "005930", result
