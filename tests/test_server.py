from conftest import tool_names

from toss_mcp.config import Settings
from toss_mcp.server import build_server

EXPECTED_TOOLS = {
    "search_symbol",
    "refresh_symbols",
    "get_price",
    "get_orderbook",
    "get_trades",
    "get_price_limits",
    "get_candles",
    "get_stock_info",
    "get_stock_warnings",
    "get_exchange_rate",
    "get_market_calendar",
    "get_rankings",
    "get_market_indicators",
}


async def test_registers_exactly_the_expected_tools(server):
    assert await tool_names(server) == EXPECTED_TOOLS


def test_thirteen_tools():
    assert len(EXPECTED_TOOLS) == 13


async def test_every_tool_is_marked_read_only(server):
    for tool in await server.list_tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name


async def test_every_tool_has_a_description(server):
    for tool in await server.list_tools():
        assert tool.description, tool.name


async def test_builds_without_credentials(stub_client, store, monkeypatch):
    """A server that refuses to start just vanishes from the client's list."""
    monkeypatch.delenv("TOSS_CLIENT_ID", raising=False)
    monkeypatch.delenv("TOSS_CLIENT_SECRET", raising=False)

    built = build_server(Settings(_env_file=None), stub_client, store)

    assert await tool_names(built) == EXPECTED_TOOLS
