"""Stock rankings and market indicators (indices, government bond yields)."""

from __future__ import annotations

from typing import Any

from toss_mcp.client import TossClient
from toss_mcp.formatting import pick
from toss_mcp.symbols import SymbolStore
from toss_mcp.tools import (
    READ_ONLY,
    ToolInputError,
    parse_symbols,
    require_choice,
    require_range,
    tool_errors,
)

RANKING_TYPES = {
    "MARKET_TRADING_AMOUNT",
    "MARKET_TRADING_VOLUME",
    "TOP_GAINERS",
    "TOP_LOSERS",
    "TOSS_SECURITIES_TRADING_AMOUNT",
    "TOSS_SECURITIES_TRADING_VOLUME",
}
# realtime is rejected for these two by the API.
_NO_REALTIME = {"TOP_GAINERS", "TOP_LOSERS"}

DURATIONS = {"realtime", "1d", "1w", "1mo", "3mo", "6mo", "1y"}
COUNTRIES = {"KR", "US"}

# The API supports exactly these eight; anything else is 400 unsupported-symbol.
INDICATOR_SYMBOLS = {
    "KOSPI": "코스피 지수",
    "KOSDAQ": "코스닥 지수",
    "KR_BOND_2Y": "한국 국채 2년 금리(%)",
    "KR_BOND_3Y": "한국 국채 3년 금리(%)",
    "KR_BOND_5Y": "한국 국채 5년 금리(%)",
    "KR_BOND_10Y": "한국 국채 10년 금리(%)",
    "KR_BOND_20Y": "한국 국채 20년 금리(%)",
    "KR_BOND_30Y": "한국 국채 30년 금리(%)",
}


def register(mcp: Any, client: TossClient, store: SymbolStore) -> None:
    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_rankings(
        type: str,
        market_country: str = "KR",
        duration: str = "1d",
        count: int = 20,
        exclude_investment_caution: bool = False,
    ) -> dict[str, Any]:
        """주식 랭킹을 조회한다 — 급상승·급하락·거래대금/거래량 상위.

        "오늘 많이 오른 종목", "거래량 터진 종목" 같은 질문에 쓴다.

        Args:
            type: 랭킹 기준.
                TOP_GAINERS(급상승), TOP_LOSERS(급하락),
                MARKET_TRADING_AMOUNT(시장 거래대금 상위),
                MARKET_TRADING_VOLUME(시장 거래량 상위),
                TOSS_SECURITIES_TRADING_AMOUNT, TOSS_SECURITIES_TRADING_VOLUME.
            market_country: "KR"(국내) 또는 "US"(미국).
            duration: 산정 기간. realtime, 1d, 1w, 1mo, 3mo, 6mo, 1y.
                TOP_GAINERS/TOP_LOSERS는 realtime을 지원하지 않는다.
            count: 조회 수 (1~100, 기본 20). 크게 잡을수록 응답이 길어진다.
            exclude_investment_caution: 투자 유의 종목 제외 여부.
        """
        ranking_type = require_choice(type, RANKING_TYPES, "type")
        country = require_choice(market_country, COUNTRIES, "market_country")
        period = (duration or "").strip()
        if period not in DURATIONS:
            raise ToolInputError(
                f"duration은 {', '.join(sorted(DURATIONS))} 중 하나여야 합니다. 받은 값: {duration!r}"
            )
        if ranking_type in _NO_REALTIME and period == "realtime":
            raise ToolInputError(
                f"{ranking_type}는 duration=realtime을 지원하지 않습니다. 1d 등 다른 기간을 사용하세요."
            )
        require_range(count, 1, 100, "count")

        result = await client.get(
            "/api/v1/rankings",
            "RANKING",
            {
                "type": ranking_type,
                "marketCountry": country,
                "duration": period,
                "count": count,
                "excludeInvestmentCaution": exclude_investment_caution,
            },
        )
        items = (result or {}).get("rankings", [])
        names = await store.names_for([i.get("symbol", "") for i in items])

        rankings = []
        for item in items:
            symbol = item.get("symbol", "")
            price = item.get("price") or {}
            entry = {
                "rank": item.get("rank"),
                "symbol": symbol,
                "lastPrice": price.get("lastPrice"),
                "changeRate": price.get("changeRate"),
                "currency": item.get("currency"),
                "tradingAmount": item.get("tradingAmount"),
                "tradingVolume": item.get("tradingVolume"),
            }
            if names.get(symbol):
                entry["name"] = names[symbol]
            rankings.append(entry)

        return {
            "type": ranking_type,
            "marketCountry": country,
            "duration": period,
            "rankedAt": (result or {}).get("rankedAt"),
            "rankings": rankings,
        }

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_market_indicators(symbols: str = "KOSPI,KOSDAQ") -> dict[str, Any]:
        """국내 지수와 국채 금리의 현재가를 조회한다.

        "코스피 지금 얼마야", "국고채 10년 금리" 같은 질문에 쓴다.
        개별 종목 시세는 이 도구가 아니라 get_price를 사용한다.

        Args:
            symbols: 콤마로 구분. 지원 심볼은 다음 8종뿐이다 —
                KOSPI, KOSDAQ, KR_BOND_2Y, KR_BOND_3Y, KR_BOND_5Y,
                KR_BOND_10Y, KR_BOND_20Y, KR_BOND_30Y.
        """
        parsed = [s.upper() for s in parse_symbols(symbols)]
        unknown = [s for s in parsed if s not in INDICATOR_SYMBOLS]
        if unknown:
            raise ToolInputError(
                f"지원하지 않는 지표 심볼입니다: {', '.join(unknown)}. "
                f"사용 가능한 심볼: {', '.join(INDICATOR_SYMBOLS)}. "
                "개별 종목 시세는 get_price를 사용하세요."
            )

        result = await client.get(
            "/api/v1/market-indicators/prices",
            "MARKET_INDICATOR",
            {"symbols": ",".join(parsed)},
        )
        rows = result if isinstance(result, list) else []
        return {
            "indicators": [
                {
                    **pick(row, "symbol", "lastPrice", "timestamp"),
                    "description": INDICATOR_SYMBOLS.get(row.get("symbol", ""), ""),
                }
                for row in rows
            ]
        }
