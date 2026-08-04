import pytest
from conftest import call

from toss_mcp.errors import TossApiError

PRICES = "/api/v1/prices"
CANDLES = "/api/v1/candles"


def price_row(symbol, last, timestamp="2026-08-04T14:00:00+09:00"):
    return {"symbol": symbol, "lastPrice": last, "currency": "KRW", "timestamp": timestamp}


def candle(date, close):
    return {
        "timestamp": f"{date}T09:00:00+09:00",
        "openPrice": close,
        "highPrice": close,
        "lowPrice": close,
        "closePrice": close,
        "volume": "100",
    }


async def test_price_carries_the_stock_name(server, stub_client):
    stub_client.set(PRICES, [price_row("005930", "72000")])

    result = await call(server, "get_price", symbols="005930")

    assert result["prices"][0]["name"] == "삼성전자"
    assert result["prices"][0]["lastPrice"] == "72000"


async def test_unknown_symbol_still_returns_a_price(server, stub_client):
    """A symbol missing from the local master is not an error."""
    stub_client.set(PRICES, [price_row("999999", "1000")])

    result = await call(server, "get_price", symbols="999999")

    assert "name" not in result["prices"][0]
    assert result["prices"][0]["lastPrice"] == "1000"


async def test_price_does_not_touch_the_chart_api_by_default(server, stub_client):
    stub_client.set(PRICES, [price_row("005930", "72000")])

    await call(server, "get_price", symbols="005930")

    assert CANDLES not in stub_client.paths()


async def test_include_change_computes_the_rate(server, stub_client):
    stub_client.set(PRICES, [price_row("005930", "72000")])
    stub_client.set(
        CANDLES,
        {"candles": [candle("2026-08-04", "72000"), candle("2026-08-03", "71000")]},
    )

    result = await call(server, "get_price", symbols="005930", include_change=True)

    entry = result["prices"][0]
    assert entry["prevClose"] == "71000"
    assert entry["change"] == "1000"
    assert entry["changeRate"] == "1.41"


async def test_include_change_skips_todays_bar(server, stub_client):
    """Today's close equals the live price, so using it would always read 0%."""
    stub_client.set(PRICES, [price_row("005930", "72000", "2026-08-04T14:00:00+09:00")])
    stub_client.set(
        CANDLES,
        {"candles": [candle("2026-08-04", "72000"), candle("2026-08-03", "70000")]},
    )

    result = await call(server, "get_price", symbols="005930", include_change=True)

    assert result["prices"][0]["prevClose"] == "70000"


async def test_include_change_survives_a_chart_failure(server, stub_client):
    stub_client.set(PRICES, [price_row("005930", "72000")])
    stub_client.set(CANDLES, TossApiError("internal-error", "boom"))

    result = await call(server, "get_price", symbols="005930", include_change=True)

    assert result["prices"][0]["lastPrice"] == "72000"
    assert "changeRate" not in result["prices"][0]


async def test_price_rejects_more_than_200_symbols(server, stub_client):
    symbols = ",".join(f"{i:06d}" for i in range(201))

    result = await call(server, "get_price", symbols=symbols)

    assert "200" in result["error"]
    assert stub_client.calls == []


async def test_price_rejects_an_empty_symbol_list(server):
    result = await call(server, "get_price", symbols="  ,  ")

    assert "error" in result


async def test_orderbook_returns_only_price_and_volume(server, stub_client):
    stub_client.set(
        "/api/v1/orderbook",
        {
            "timestamp": "2026-08-04T14:00:00+09:00",
            "currency": "KRW",
            "asks": [{"price": "72100", "volume": "10", "noise": "drop me"}],
            "bids": [{"price": "72000", "volume": "20"}],
        },
    )

    result = await call(server, "get_orderbook", symbol="005930")

    assert result["asks"] == [{"price": "72100", "volume": "10"}]
    assert result["bids"] == [{"price": "72000", "volume": "20"}]


async def test_trades_default_count(server, stub_client):
    stub_client.set("/api/v1/trades", [])

    await call(server, "get_trades", symbol="005930")

    assert stub_client.params_for("/api/v1/trades")["count"] == 20


@pytest.mark.parametrize("count", [0, 51, -1])
async def test_trades_rejects_out_of_range_counts(server, stub_client, count):
    result = await call(server, "get_trades", symbol="005930", count=count)

    assert "1~50" in result["error"]
    assert stub_client.calls == []


async def test_candles_rejects_an_unsupported_interval(server, stub_client):
    result = await call(server, "get_candles", symbol="005930", interval="5m")

    assert "1d" in result["error"] and "1m" in result["error"]
    assert stub_client.calls == []


async def test_candles_rejects_more_than_200_bars(server, stub_client):
    result = await call(server, "get_candles", symbol="005930", count=201)

    assert "1~200" in result["error"]
    assert stub_client.calls == []


async def test_candles_passes_through_pagination(server, stub_client):
    stub_client.set(CANDLES, {"candles": [candle("2026-08-03", "71000")], "nextBefore": "2026-08-03T00:00:00+09:00"})

    result = await call(server, "get_candles", symbol="005930", interval="1d", count=1)

    assert result["nextBefore"] == "2026-08-03T00:00:00+09:00"
    assert stub_client.params_for(CANDLES)["interval"] == "1d"


async def test_api_error_becomes_an_error_field(server, stub_client):
    stub_client.set(PRICES, TossApiError("stock-not-found", "없음"))

    result = await call(server, "get_price", symbols="000000")

    assert "search_symbol" in result["error"]
