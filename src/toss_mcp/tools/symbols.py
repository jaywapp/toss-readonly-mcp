"""Symbol search — the Toss API has no equivalent endpoint."""

from __future__ import annotations

from typing import Any

from toss_mcp.symbols import SymbolStore
from toss_mcp.tools import READ_ONLY, tool_errors


def register(mcp: Any, store: SymbolStore) -> None:
    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def search_symbol(query: str, market: str | None = None, limit: int = 10) -> dict[str, Any]:
        """종목명이나 티커로 종목 심볼을 찾는다.

        시세 조회 도구는 모두 심볼을 요구하므로, 사용자가 종목명으로 물으면 먼저 이 도구를 쓴다.
        예: "삼성전자" -> 005930, "apple" -> AAPL.

        결과가 여러 개면 어느 종목인지 사용자에게 되묻는다.

        Args:
            query: 종목명, 영문명, 또는 심볼. 부분 일치도 동작한다.
            market: 특정 시장으로 제한 (KOSPI, KOSDAQ, NASDAQ, NYSE, AMEX).
            limit: 최대 결과 수 (기본 10).
        """
        limit = max(1, min(int(limit), 50))
        results = await store.search(query, market=market, limit=limit)
        if not results:
            return {
                "results": [],
                "message": (
                    f"'{query}'와(과) 일치하는 종목이 없습니다. "
                    "철자를 확인하거나 refresh_symbols로 종목 목록을 갱신해 보세요."
                ),
            }
        return {
            "results": [
                {"symbol": r.symbol, "name": r.name, "market": r.market} for r in results
            ]
        }

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def refresh_symbols() -> dict[str, Any]:
        """종목 목록 캐시를 즉시 갱신한다.

        신규 상장 종목이 검색되지 않을 때 사용한다. 평소에는 자동으로 갱신되므로 부를 필요가 없다.
        """
        return await store.refresh()
