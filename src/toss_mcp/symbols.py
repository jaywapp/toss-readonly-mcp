"""Local symbol master: name -> symbol lookup.

The Toss API has no symbol search endpoint — /api/v1/stocks needs the symbol
before it will tell you the name — so listings are pulled from
FinanceDataReader and cached in SQLite.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from toss_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Korean preferred shares: 삼성전자우, 현대차2우B, ...
_PREFERRED_SUFFIX = re.compile(r"\d*우[A-Z]?$")

# FDR column names differ by market and change between versions, so take the
# first column that exists rather than hard-coding one.
_SYMBOL_COLUMNS = ("Symbol", "Code", "code", "symbol")
_NAME_COLUMNS = ("Name", "name", "Description")
_MARKET_COLUMNS = ("Market", "market")


@dataclass(frozen=True)
class SymbolRecord:
    symbol: str
    name: str
    english_name: str | None
    market: str


def fetch_market(market: str) -> list[SymbolRecord]:
    """Pull one market's listing via FinanceDataReader.

    Imported lazily: FDR pulls in pandas, which would slow every server start
    even when nobody searches by name.
    """
    import FinanceDataReader as fdr

    frame = fdr.StockListing(market)
    columns = set(frame.columns)
    symbol_col = _first_present(_SYMBOL_COLUMNS, columns)
    name_col = _first_present(_NAME_COLUMNS, columns)
    market_col = _first_present(_MARKET_COLUMNS, columns)

    if symbol_col is None or name_col is None:
        raise RuntimeError(
            f"{market} 목록에서 심볼/종목명 컬럼을 찾지 못했습니다: {sorted(columns)}"
        )

    is_domestic = market.upper() in {"KRX", "KOSPI", "KOSDAQ", "KONEX"}
    records = []
    for row in frame.to_dict("records"):
        symbol = _clean(row.get(symbol_col))
        name = _clean(row.get(name_col))
        if not symbol or not name:
            continue
        # US listings from FDR carry the English name in `Name`; KRX has no
        # English column at all.
        english = None if is_domestic else name
        row_market = _clean(row.get(market_col)) if market_col else ""
        records.append(SymbolRecord(symbol, name, english, row_market or market.upper()))
    return records


class SymbolStore:
    def __init__(
        self,
        settings: Settings | None = None,
        fetcher: Callable[[str], list[SymbolRecord]] = fetch_market,
    ) -> None:
        self._settings = settings or get_settings()
        self._fetch = fetcher
        self._db_path = self._settings.cache_dir / "symbols.db"
        self._lock: asyncio.Lock | None = None

    # -- public API ---------------------------------------------------------

    async def search(
        self,
        query: str,
        market: str | None = None,
        limit: int = 10,
    ) -> list[SymbolRecord]:
        await self._ensure_loaded()
        needle = query.strip()
        if not needle:
            return []

        rows = self._load_all(market)
        return _rank(rows, needle)[:limit]

    async def refresh(self) -> dict:
        """Re-fetch every configured market, replacing the cache."""
        await self._reload()
        return {
            "markets": list(self._settings.symbol_markets),
            "count": self._count(),
            "updated_at": self._updated_at() or "",
        }

    async def name_for(self, symbol: str) -> str | None:
        return (await self.names_for([symbol])).get(symbol)

    async def names_for(self, symbols: list[str]) -> dict[str, str]:
        """Map symbols to names, silently skipping ones we do not know."""
        if not symbols:
            return {}
        await self._ensure_loaded()

        wanted = {s.upper(): s for s in symbols}
        found: dict[str, str] = {}
        with self._connect() as conn:
            placeholders = ",".join("?" * len(wanted))
            cursor = conn.execute(
                f"SELECT symbol, name FROM symbols WHERE UPPER(symbol) IN ({placeholders})",
                list(wanted),
            )
            for symbol, name in cursor:
                original = wanted.get(symbol.upper(), symbol)
                found[original] = name
        return found

    # -- cache management ---------------------------------------------------

    async def _ensure_loaded(self) -> None:
        if self._is_fresh():
            return
        async with self._get_lock():
            if self._is_fresh():  # another task may have loaded it
                return
            await self._reload()

    async def _reload(self) -> None:
        records: list[SymbolRecord] = []
        failures: list[str] = []
        for market in self._settings.symbol_markets:
            try:
                # FDR is synchronous and network-bound; keep the loop free.
                fetched = await asyncio.to_thread(self._fetch, market)
            except Exception as exc:  # noqa: BLE001 - one bad market must not sink the rest
                logger.warning("failed to load %s listing: %s", market, exc)
                failures.append(market)
                continue
            records.extend(fetched)

        if not records:
            raise RuntimeError(
                "종목 목록을 가져오지 못했습니다: " + ", ".join(failures or ["대상 시장 없음"])
            )

        self._write(records)
        logger.info("loaded %d symbols from %s", len(records), self._settings.symbol_markets)

    def _is_fresh(self) -> bool:
        if not self._db_path.exists() or self._count() == 0:
            return False
        return self._age_days() < self._settings.symbol_ttl_days

    def _age_days(self) -> float:
        updated = self._updated_at_epoch()
        if updated is None:
            return float("inf")
        return (time.time() - updated) / 86400

    # -- storage ------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        self._settings.cache_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS symbols (
                   symbol TEXT PRIMARY KEY,
                   name TEXT NOT NULL,
                   english_name TEXT,
                   market TEXT NOT NULL,
                   updated_at REAL NOT NULL
               )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
        return conn

    def _write(self, records: list[SymbolRecord]) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("DELETE FROM symbols")
            conn.executemany(
                "INSERT OR REPLACE INTO symbols VALUES (?, ?, ?, ?, ?)",
                [(r.symbol, r.name, r.english_name, r.market, now) for r in records],
            )

    def _load_all(self, market: str | None) -> list[SymbolRecord]:
        with self._connect() as conn:
            if market:
                cursor = conn.execute(
                    "SELECT symbol, name, english_name, market FROM symbols WHERE UPPER(market) = ?",
                    (market.upper(),),
                )
            else:
                cursor = conn.execute("SELECT symbol, name, english_name, market FROM symbols")
            return [SymbolRecord(*row) for row in cursor]

    def _count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]

    def _updated_at_epoch(self) -> float | None:
        with self._connect() as conn:
            value = conn.execute("SELECT MAX(updated_at) FROM symbols").fetchone()[0]
        return value

    def _updated_at(self) -> str | None:
        epoch = self._updated_at_epoch()
        if epoch is None:
            return None
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock


# -- ranking ----------------------------------------------------------------


def _rank(rows: list[SymbolRecord], needle: str) -> list[SymbolRecord]:
    """Exact symbol, exact name, prefix, then substring.

    Stop at the first tier that produces anything: someone who typed an exact
    name does not want every company containing that word.
    """
    lowered = needle.lower()

    tiers: list[list[SymbolRecord]] = [[] for _ in range(4)]
    for row in rows:
        names = [row.name.lower()]
        if row.english_name:
            names.append(row.english_name.lower())

        if row.symbol.lower() == lowered:
            tiers[0].append(row)
        elif lowered in names:
            tiers[1].append(row)
        elif any(n.startswith(lowered) for n in names):
            tiers[2].append(row)
        elif any(lowered in n for n in names):
            tiers[3].append(row)

    for tier in tiers:
        if tier:
            return sorted(tier, key=_sort_key)
    return []


def _sort_key(record: SymbolRecord) -> tuple[int, int, str]:
    return (0 if _is_common_share(record) else 1, len(record.name), record.name)


def _is_common_share(record: SymbolRecord) -> bool:
    if record.market.upper() in {"KOSPI", "KOSDAQ", "KONEX", "KRX"}:
        return not _PREFERRED_SUFFIX.search(record.name)
    return True


# -- helpers ----------------------------------------------------------------


def _first_present(candidates: tuple[str, ...], available: set[str]) -> str | None:
    return next((c for c in candidates if c in available), None)


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


_store: SymbolStore | None = None


def get_store() -> SymbolStore:
    global _store
    if _store is None:
        _store = SymbolStore()
    return _store
