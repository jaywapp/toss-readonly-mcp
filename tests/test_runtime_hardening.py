import sqlite3

import httpx
import pytest

from toss_mcp.auth import _coerce_int
from toss_mcp.client import _retry_delay
from toss_mcp.config import Settings
from toss_mcp.symbols import SymbolRecord, SymbolStore


@pytest.fixture
def store(tmp_path):
    return SymbolStore(Settings(_env_file=None, cache_dir=tmp_path), fetcher=lambda _: [])


async def test_blank_search_does_not_fetch_or_create_cache(store):
    assert await store.search('  \t ') == []
    assert not store._db_path.exists()


async def test_empty_name_batch_does_not_create_cache(store):
    assert await store.names_for([]) == {}
    assert not store._db_path.exists()


@pytest.mark.parametrize('fail', [False, True])
def test_connection_closes_on_success_and_failure(store, fail):
    connection = None
    try:
        with store._connect() as connection:
            if fail:
                raise RuntimeError('operation failed')
    except RuntimeError:
        assert fail
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')


def test_failed_replacement_preserves_previous_cache(store):
    original = SymbolRecord('AAPL', 'Apple', None, 'NASDAQ')
    store._write([original])
    with pytest.raises(sqlite3.IntegrityError):
        store._write([SymbolRecord('BAD', None, None, 'NASDAQ')])
    assert store._load_all(None) == [original]


def test_name_lookup_uses_expression_index(store):
    store._write([SymbolRecord('AAPL', 'Apple', None, 'NASDAQ')])
    with store._connect() as connection:
        plan = connection.execute(
            'EXPLAIN QUERY PLAN SELECT symbol, name FROM symbols WHERE UPPER(symbol) IN (?)',
            ('AAPL',),
        ).fetchall()
    assert any('idx_symbols_upper_symbol' in row[3] for row in plan)


async def test_name_lookup_keeps_requested_case_and_skips_unknown(store):
    store._write([SymbolRecord('AAPL', 'Apple', None, 'NASDAQ')])
    assert await store.names_for(['aapl', 'missing']) == {'aapl': 'Apple'}


@pytest.mark.parametrize('header', ['NaN', 'inf', '-inf', '-1', 'invalid', '1e999'])
def test_invalid_retry_after_uses_finite_backoff(header, caplog):
    delay = _retry_delay(httpx.Response(429, headers={'Retry-After': header}), 0)
    assert 1 <= delay < 2
    assert 'invalid Retry-After' in caplog.text


@pytest.mark.parametrize('header,expected', [('0', 0), ('0.5', .5), ('3', 3)])
def test_valid_retry_after_is_preserved(header, expected):
    assert _retry_delay(httpx.Response(429, headers={'Retry-After': header}), 0) == expected


@pytest.mark.parametrize('value', [None, 'bad', float('inf'), float('-inf'), float('nan')])
def test_invalid_expiry_uses_existing_default(value):
    assert _coerce_int(value, 3600) == 3600
