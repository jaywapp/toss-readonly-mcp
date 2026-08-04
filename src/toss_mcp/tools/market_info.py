"""Exchange rate and market operating hours."""

from __future__ import annotations

from typing import Any

from toss_mcp.client import TossClient
from toss_mcp.symbols import SymbolStore
from toss_mcp.tools import READ_ONLY, require_choice, tool_errors

CURRENCIES = {"KRW", "USD"}
COUNTRIES = {"KR", "US"}


def register(mcp: Any, client: TossClient, store: SymbolStore) -> None:
    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_exchange_rate(
        base: str = "USD",
        quote: str = "KRW",
        date_time: str | None = None,
    ) -> dict[str, Any]:
        """KRW-USD 환율을 조회한다.

        1분마다 갱신되는 참고용 표시 환율이다. 실제 거래 환율과는 다를 수 있다.

        Args:
            base: 기준 통화 (KRW 또는 USD, 기본 USD).
            quote: 표시 통화 (KRW 또는 USD, 기본 KRW). 1 base = ? quote.
            date_time: 특정 시점의 환율 (ISO 8601). 생략하면 현재 유효 환율.
        """
        base = require_choice(base, CURRENCIES, "base")
        quote = require_choice(quote, CURRENCIES, "quote")
        if base == quote:
            return {"error": "base와 quote는 서로 달라야 합니다."}

        result = await client.get(
            "/api/v1/exchange-rate",
            "MARKET_INFO",
            {"baseCurrency": base, "quoteCurrency": quote, "dateTime": date_time},
        )
        return result

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_market_calendar(country: str, date: str | None = None) -> dict[str, Any]:
        """국내 또는 미국 시장의 장 운영 시간을 조회한다.

        지금 장이 열려 있는지 확인할 때 쓴다. 전일·당일·익일 3영업일 정보를 반환하며,
        모든 시각은 KST(+09:00) 기준이다. 휴장일은 세션이 비어 있다.

        Args:
            country: "KR"(국내) 또는 "US"(미국).
            date: 조회 기준일 (YYYY-MM-DD). 생략하면 오늘.
        """
        country = require_choice(country, COUNTRIES, "country")
        result = await client.get(
            f"/api/v1/market-calendar/{country}", "MARKET_INFO", {"date": date}
        )
        return {"country": country, **(result if isinstance(result, dict) else {"result": result})}
