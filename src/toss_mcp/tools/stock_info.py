"""Reference data: stock master and trading warnings."""

from __future__ import annotations

from typing import Any

from toss_mcp.client import TossClient
from toss_mcp.formatting import pick
from toss_mcp.symbols import SymbolStore
from toss_mcp.tools import READ_ONLY, parse_symbols, tool_errors

WARNING_LABELS = {
    "LIQUIDATION_TRADING": "정리매매 (상장폐지 절차 진행 중)",
    "OVERHEATED": "단기과열종목 지정",
    "INVESTMENT_WARNING": "투자경고종목 지정",
    "INVESTMENT_RISK": "투자위험종목 지정",
    "VI_STATIC_AND_DYNAMIC": "변동성 완화장치(VI) 정적+동적 발동",
    "VI_STATIC": "변동성 완화장치(VI) 정적 발동",
    "VI_DYNAMIC": "변동성 완화장치(VI) 동적 발동",
    "STOCK_WARRANTS": "신주인수권증서/증권",
}


def register(mcp: Any, client: TossClient, store: SymbolStore) -> None:
    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_stock_info(symbols: str) -> dict[str, Any]:
        """종목의 기본 정보를 조회한다 — 종목명, 상장 시장, 통화, 상장 상태, 발행주식수.

        Args:
            symbols: 종목 심볼. 콤마로 구분, 최대 200개.
        """
        parsed = parse_symbols(symbols)
        result = await client.get(
            "/api/v1/stocks", "STOCK", {"symbols": ",".join(parsed)}
        )
        rows = result if isinstance(result, list) else []
        return {
            "stocks": [
                pick(
                    row,
                    "symbol",
                    "name",
                    "englishName",
                    "market",
                    "securityType",
                    "isCommonShare",
                    "status",
                    "currency",
                    "listDate",
                    "sharesOutstanding",
                )
                for row in rows
            ]
        }

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_stock_warnings(symbol: str) -> dict[str, Any]:
        """종목의 매수 유의사항을 조회한다.

        정리매매, 단기과열, 투자경고/위험 지정, VI 발동, 신주인수권 여부를 확인한다.
        매수를 검토하는 종목이라면 확인할 가치가 있다.

        Args:
            symbol: 종목 심볼.
        """
        result = await client.get(f"/api/v1/stocks/{symbol}/warnings", "STOCK")
        rows = result if isinstance(result, list) else []
        if not rows:
            return {"symbol": symbol, "warnings": [], "message": "현재 활성화된 유의사항이 없습니다."}

        return {
            "symbol": symbol,
            "warnings": [
                {
                    **pick(row, "warningType", "exchange", "startDate", "endDate"),
                    "description": WARNING_LABELS.get(
                        row.get("warningType", ""), row.get("warningType", "")
                    ),
                }
                for row in rows
            ],
        }
