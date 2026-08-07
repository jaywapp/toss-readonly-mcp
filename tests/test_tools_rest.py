import pytest
from conftest import call

STOCKS = "/api/v1/stocks"
WARNINGS = "/api/v1/stocks/005930/warnings"
RATE = "/api/v1/exchange-rate"
RANKINGS = "/api/v1/rankings"
INDICATORS = "/api/v1/market-indicators/prices"


# -- symbol search ----------------------------------------------------------


async def test_search_symbol_returns_candidates(server):
    result = await call(server, "search_symbol", query="삼성")

    assert result["results"][0]["symbol"] == "005930"
    assert result["results"][0]["name"] == "삼성전자"


async def test_search_symbol_explains_a_miss(server):
    result = await call(server, "search_symbol", query="없는회사이름")

    assert result["results"] == []
    assert "refresh_symbols" in result["message"]


async def test_refresh_symbols_reports_the_count(server):
    result = await call(server, "refresh_symbols")

    assert result["count"] == 3


# -- stock info -------------------------------------------------------------


async def test_stock_info_trims_to_useful_fields(server, stub_client):
    stub_client.set(
        STOCKS,
        [{"symbol": "005930", "name": "삼성전자", "market": "KOSPI", "isinCode": "KR7005930003", "currency": "KRW",
          "status": "ACTIVE", "sharesOutstanding": "5919637922", "englishName": "SamsungElec",
          "securityType": "STOCK", "isCommonShare": True, "leverageFactor": None}],
    )

    result = await call(server, "get_stock_info", symbols="005930")

    stock = result["stocks"][0]
    assert stock["name"] == "삼성전자"
    assert "isinCode" not in stock, "not useful to an LLM answering price questions"
    assert "leverageFactor" not in stock


async def test_stock_info_rejects_over_200_symbols(server, stub_client):
    result = await call(server, "get_stock_info", symbols=",".join(f"{i:06d}" for i in range(201)))

    assert "200" in result["error"]
    assert stub_client.calls == []


async def test_warnings_are_labelled(server, stub_client):
    stub_client.set(
        WARNINGS,
        [{"warningType": "INVESTMENT_WARNING", "exchange": "KRX", "startDate": "2026-08-01", "endDate": None}],
    )

    result = await call(server, "get_stock_warnings", symbol="005930")

    assert result["warnings"][0]["description"] == "투자경고종목 지정"


async def test_unknown_warning_type_does_not_break(server, stub_client):
    stub_client.set(WARNINGS, [{"warningType": "SOMETHING_NEW", "startDate": "2026-08-01"}])

    result = await call(server, "get_stock_warnings", symbol="005930")

    assert result["warnings"][0]["description"] == "SOMETHING_NEW"


async def test_no_warnings_says_so(server, stub_client):
    stub_client.set(WARNINGS, [])

    result = await call(server, "get_stock_warnings", symbol="005930")

    assert result["warnings"] == []
    assert "없습니다" in result["message"]


# -- market info ------------------------------------------------------------


async def test_exchange_rate_defaults_to_usd_krw(server, stub_client):
    stub_client.set(RATE, {"baseCurrency": "USD", "quoteCurrency": "KRW", "rate": "1380.5"})

    result = await call(server, "get_exchange_rate")

    assert result["rate"] == "1380.5"
    params = stub_client.params_for(RATE)
    assert params["baseCurrency"] == "USD"
    assert params["quoteCurrency"] == "KRW"


async def test_exchange_rate_rejects_an_unsupported_currency(server, stub_client):
    result = await call(server, "get_exchange_rate", base="EUR")

    assert "error" in result
    assert stub_client.calls == []


async def test_exchange_rate_rejects_identical_currencies(server, stub_client):
    result = await call(server, "get_exchange_rate", base="KRW", quote="KRW")

    assert "error" in result
    assert stub_client.calls == []


@pytest.mark.parametrize("country,expected", [("kr", "KR"), ("KR", "KR"), ("us", "US")])
async def test_market_calendar_normalises_country(server, stub_client, country, expected):
    stub_client.set(f"/api/v1/market-calendar/{expected}", {"days": []})

    result = await call(server, "get_market_calendar", country=country)

    assert result["country"] == expected


async def test_market_calendar_rejects_other_countries(server, stub_client):
    result = await call(server, "get_market_calendar", country="JP")

    assert "error" in result
    assert stub_client.calls == []


# -- rankings ---------------------------------------------------------------


def ranking_payload():
    return {
        "rankedAt": "2026-08-04T14:00:00+09:00",
        "rankings": [
            {
                "rank": 1,
                "symbol": "005930",
                "currency": "KRW",
                "price": {"lastPrice": "72000", "basePrice": "71000", "changeRate": "1.41"},
                "tradingVolume": "1000",
                "tradingAmount": "72000000",
            }
        ],
    }


async def test_rankings_attach_names(server, stub_client):
    stub_client.set(RANKINGS, ranking_payload())

    result = await call(server, "get_rankings", type="TOP_GAINERS")

    entry = result["rankings"][0]
    assert entry["name"] == "삼성전자"
    assert entry["changeRate"] == "1.41"


async def test_rankings_default_count_is_20_not_100(server, stub_client):
    """The API defaults to 100, which would flood the model's context."""
    stub_client.set(RANKINGS, ranking_payload())

    await call(server, "get_rankings", type="TOP_GAINERS")

    assert stub_client.params_for(RANKINGS)["count"] == 20


async def test_rankings_reject_realtime_for_gainers(server, stub_client):
    result = await call(server, "get_rankings", type="TOP_GAINERS", duration="realtime")

    assert "realtime" in result["error"]
    assert stub_client.calls == []


async def test_rankings_allow_realtime_for_trading_amount(server, stub_client):
    stub_client.set(RANKINGS, ranking_payload())

    await call(server, "get_rankings", type="MARKET_TRADING_AMOUNT", duration="realtime")

    assert stub_client.params_for(RANKINGS)["duration"] == "realtime"


@pytest.mark.parametrize("bad", ["TOP_MOVERS", "", "top_gainers_x"])
async def test_rankings_reject_unknown_types(server, stub_client, bad):
    result = await call(server, "get_rankings", type=bad)

    assert "error" in result
    assert stub_client.calls == []


async def test_rankings_reject_unknown_duration(server, stub_client):
    result = await call(server, "get_rankings", type="TOP_GAINERS", duration="2w")

    assert "error" in result
    assert stub_client.calls == []


async def test_rankings_reject_count_over_100(server, stub_client):
    result = await call(server, "get_rankings", type="TOP_GAINERS", count=101)

    assert "1~100" in result["error"]
    assert stub_client.calls == []


async def test_rankings_lowercase_type_is_accepted(server, stub_client):
    stub_client.set(RANKINGS, ranking_payload())

    await call(server, "get_rankings", type="top_gainers")

    assert stub_client.params_for(RANKINGS)["type"] == "TOP_GAINERS"


# -- market indicators ------------------------------------------------------


async def test_indicators_describe_each_symbol(server, stub_client):
    stub_client.set(
        INDICATORS,
        [{"symbol": "KOSPI", "lastPrice": "2810.55", "timestamp": "2026-08-04T14:00:00+09:00"}],
    )

    result = await call(server, "get_market_indicators", symbols="KOSPI")

    assert result["indicators"][0]["description"] == "코스피 지수"
    assert result["indicators"][0]["lastPrice"] == "2810.55"


async def test_indicators_reject_a_stock_symbol(server, stub_client):
    """005930 belongs to get_price, not here — say so instead of a bare 400."""
    result = await call(server, "get_market_indicators", symbols="005930")

    assert "get_price" in result["error"]
    assert stub_client.calls == []


async def test_indicators_accept_bonds_and_normalise_case(server, stub_client):
    stub_client.set(INDICATORS, [])

    await call(server, "get_market_indicators", symbols="kr_bond_10y")

    assert stub_client.params_for(INDICATORS)["symbols"] == "KR_BOND_10Y"
