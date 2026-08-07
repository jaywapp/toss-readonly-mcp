"""Quotes: price, orderbook, trades, price limits, candles."""

from __future__ import annotations

import asyncio
from typing import Any

from toss_mcp.client import TossClient
from toss_mcp.formatting import compute_change, pick
from toss_mcp.symbols import SymbolStore
from toss_mcp.tools import (
    READ_ONLY,
    parse_symbols,
    require_exact,
    require_range,
    tool_errors,
)

CANDLE_INTERVALS = {"1m", "1d"}

# Enough daily candles to find the previous session even when today's bar is
# already open.
_CHANGE_CANDLE_COUNT = 3


def register(mcp: Any, client: TossClient, store: SymbolStore) -> None:
    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_price(symbols: str, include_change: bool = False) -> dict[str, Any]:
        """종목의 현재가를 조회한다. 최대 200종목을 한 번에 조회할 수 있다.

        응답에는 종목명이 함께 담긴다. 사용자가 종목명으로 물었다면 반환된 이름이
        의도한 종목과 맞는지 확인한다.

        Args:
            symbols: 종목 심볼. 콤마로 구분 (예: "005930,000660" 또는 "AAPL").
            include_change: True면 전일 종가 대비 등락액·등락률을 함께 계산한다.
                종목마다 일봉을 추가 조회하므로 종목이 많으면 느려진다.
                사용자가 등락/변동을 물었을 때만 켠다.
        """
        parsed = parse_symbols(symbols)
        rows = await client.get(
            "/api/v1/prices", "MARKET_DATA", {"symbols": ",".join(parsed)}
        )
        rows = rows if isinstance(rows, list) else []

        names = await store.names_for([r.get("symbol", "") for r in rows])
        prices = []
        for row in rows:
            entry = pick(row, "symbol", "lastPrice", "currency", "timestamp")
            name = names.get(entry.get("symbol", ""))
            if name:
                entry["name"] = name
            prices.append(entry)

        if include_change:
            await _attach_changes(client, prices)

        return {"prices": prices}

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_orderbook(symbol: str) -> dict[str, Any]:
        """종목의 매수/매도 호가와 잔량을 조회한다.

        Args:
            symbol: 종목 심볼 (KRX는 6자리 숫자, 미국은 티커).
        """
        result = await client.get("/api/v1/orderbook", "MARKET_DATA", {"symbol": symbol})
        return {
            "symbol": symbol,
            "timestamp": (result or {}).get("timestamp"),
            "currency": (result or {}).get("currency"),
            "asks": [pick(e, "price", "volume") for e in (result or {}).get("asks", [])],
            "bids": [pick(e, "price", "volume") for e in (result or {}).get("bids", [])],
        }

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_trades(symbol: str, count: int = 20) -> dict[str, Any]:
        """종목의 당일 최근 체결 내역을 조회한다.

        Args:
            symbol: 종목 심볼.
            count: 조회 건수 (1~50, 기본 20).
        """
        require_range(count, 1, 50, "count")
        result = await client.get(
            "/api/v1/trades", "MARKET_DATA", {"symbol": symbol, "count": count}
        )
        trades = result if isinstance(result, list) else []
        return {
            "symbol": symbol,
            "trades": [pick(t, "timestamp", "price", "volume", "currency") for t in trades],
        }

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_price_limits(symbol: str) -> dict[str, Any]:
        """종목의 당일 상한가·하한가를 조회한다.

        미국 주식처럼 가격제한이 없는 시장은 null이 반환된다.

        Args:
            symbol: 종목 심볼.
        """
        result = await client.get("/api/v1/price-limits", "MARKET_DATA", {"symbol": symbol})
        return {"symbol": symbol, **pick(result, "timestamp", "upperLimitPrice", "lowerLimitPrice", "currency")}

    @mcp.tool(annotations=READ_ONLY)
    @tool_errors
    async def get_candles(
        symbol: str,
        interval: str = "1d",
        count: int = 30,
        before: str | None = None,
        adjusted: bool = True,
    ) -> dict[str, Any]:
        """종목의 캔들(OHLCV) 차트 데이터를 조회한다.

        Args:
            symbol: 종목 심볼.
            interval: 봉 단위. "1m"(1분봉) 또는 "1d"(일봉).
            count: 조회 봉 수 (1~200, 기본 30).
            before: 페이지네이션 상한 (ISO 8601). 이전 응답의 nextBefore를 그대로 전달한다.
            adjusted: 수정주가 적용 여부 (기본 True).
        """
        require_exact(interval, CANDLE_INTERVALS, "interval")
        require_range(count, 1, 200, "count")

        result = await client.get(
            "/api/v1/candles",
            "MARKET_DATA_CHART",
            {
                "symbol": symbol,
                "interval": interval,
                "count": count,
                "before": before,
                "adjusted": adjusted,
            },
        )
        candles = (result or {}).get("candles", [])
        return {
            "symbol": symbol,
            "interval": interval,
            "candles": [
                pick(c, "timestamp", "openPrice", "highPrice", "lowPrice", "closePrice", "volume")
                for c in candles
            ],
            "nextBefore": (result or {}).get("nextBefore"),
        }


async def _attach_changes(client: TossClient, prices: list[dict[str, Any]]) -> None:
    """Add prevClose/change/changeRate to each entry, in place."""
    results = await asyncio.gather(
        *(_previous_close(client, p) for p in prices), return_exceptions=True
    )
    for entry, prev_close in zip(prices, results):
        if isinstance(prev_close, BaseException) or not prev_close:
            continue
        entry.update(compute_change(entry.get("lastPrice"), prev_close))


async def _previous_close(client: TossClient, entry: dict[str, Any]) -> str | None:
    symbol = entry.get("symbol")
    if not symbol:
        return None

    result = await client.get(
        "/api/v1/candles",
        "MARKET_DATA_CHART",
        {"symbol": symbol, "interval": "1d", "count": _CHANGE_CANDLE_COUNT},
    )
    candles = [c for c in (result or {}).get("candles", []) if c.get("timestamp")]
    if not candles:
        return None

    candles.sort(key=lambda c: c["timestamp"], reverse=True)

    # Skip today's bar: while the market is open its close is the current
    # price, and comparing a price to itself always reads as 0%.
    today = _date_of(entry.get("timestamp"))
    for candle in candles:
        if today and _date_of(candle["timestamp"]) == today:
            continue
        return candle.get("closePrice")

    # Every bar is from the current session (or the price had no timestamp);
    # fall back to the one before the newest.
    return candles[1].get("closePrice") if len(candles) > 1 else None


def _date_of(timestamp: Any) -> str:
    """The date portion of an ISO 8601 timestamp, as sent by the API."""
    if not isinstance(timestamp, str) or "T" not in timestamp:
        return ""
    return timestamp.split("T", 1)[0]
