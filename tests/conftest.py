"""Shared fixtures: a server wired to a stubbed client and symbol store."""

from __future__ import annotations

from typing import Any

import pytest

from toss_mcp.config import Settings
from toss_mcp.server import build_server
from toss_mcp.symbols import SymbolRecord, SymbolStore

FIXTURE_SYMBOLS = [
    SymbolRecord("005930", "삼성전자", None, "KOSPI"),
    SymbolRecord("000660", "SK하이닉스", None, "KOSPI"),
    SymbolRecord("AAPL", "Apple Inc", "Apple Inc", "NASDAQ"),
]


class StubClient:
    """Records calls and replays canned responses keyed by path."""

    def __init__(self) -> None:
        self.responses: dict[str, Any] = {}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def set(self, path: str, value: Any) -> None:
        self.responses[path] = value

    async def get(self, path: str, group: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((path, group, dict(params or {})))
        if path not in self.responses:
            raise AssertionError(f"unexpected call to {path}")
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        if callable(value):
            return value(params or {})
        return value

    def paths(self) -> list[str]:
        return [c[0] for c in self.calls]

    def params_for(self, path: str) -> dict[str, Any]:
        for call_path, _, params in self.calls:
            if call_path == path:
                return params
        raise AssertionError(f"{path} was never called")


@pytest.fixture
def stub_client():
    return StubClient()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("TOSS_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("TOSS_SYMBOL_MARKETS", "KRX")
    settings = Settings(_env_file=None)
    return SymbolStore(settings, fetcher=lambda market: list(FIXTURE_SYMBOLS))


@pytest.fixture
def server(stub_client, store, monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "c_abc")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", "s_xyz")
    return build_server(Settings(_env_file=None), stub_client, store)


async def call(server, name: str, **kwargs) -> Any:
    """Invoke a tool through the server and return its structured payload."""
    result = await server.call_tool(name, kwargs)
    return result.structured_content


async def tool_names(server) -> set[str]:
    return {tool.name for tool in await server.list_tools()}
