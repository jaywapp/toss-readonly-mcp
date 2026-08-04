"""MCP server entry point."""

from __future__ import annotations

import logging
import sys

from mcp.server.mcpserver import MCPServer

from toss_mcp import __version__
from toss_mcp.client import TossClient, get_client
from toss_mcp.config import Settings, get_settings
from toss_mcp.symbols import SymbolStore, get_store
from toss_mcp.tools import market_data, market_info, rankings, stock_info
from toss_mcp.tools import symbols as symbol_tools

logger = logging.getLogger(__name__)

INSTRUCTIONS = """토스증권 Open API로 국내·미국 주식 시세와 종목 정보를 조회한다.

사용자가 종목명으로 물으면 먼저 search_symbol로 심볼을 찾은 뒤 시세 도구를 호출한다.
조회 전용이라 주문이나 계좌 조회는 할 수 없다."""


def build_server(
    settings: Settings | None = None,
    client: TossClient | None = None,
    store: SymbolStore | None = None,
) -> MCPServer:
    settings = settings or get_settings()
    client = client or get_client()
    store = store or get_store()

    mcp = MCPServer("toss", instructions=INSTRUCTIONS, version=__version__)

    symbol_tools.register(mcp, store)
    market_data.register(mcp, client, store)
    stock_info.register(mcp, client, store)
    market_info.register(mcp, client, store)
    rankings.register(mcp, client, store)

    return mcp


def main() -> None:
    settings = get_settings()

    # stdout carries the MCP protocol; anything logged there corrupts it.
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not (settings.client_id and settings.client_secret):
        # Start anyway: a server that exits here disappears from the client
        # with no explanation. The tools return an actionable message instead.
        logger.warning(
            "TOSS_CLIENT_ID/TOSS_CLIENT_SECRET가 설정되지 않았습니다. "
            "조회 도구는 설정 안내를 반환합니다."
        )

    build_server(settings).run()


if __name__ == "__main__":
    main()
