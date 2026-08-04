from pathlib import Path

import pytest

from toss_mcp.config import Settings
from toss_mcp.errors import ConfigError

SECRET = "s_supersecretvalue"


def test_defaults_are_applied():
    settings = Settings(_env_file=None)

    assert settings.api_base_url == "https://openapi.tossinvest.com"
    assert settings.http_timeout == 10.0
    assert settings.symbol_ttl_days == 7
    assert settings.symbol_markets == ["KRX", "NASDAQ", "NYSE", "AMEX"]
    assert settings.log_level == "INFO"
    assert isinstance(settings.cache_dir, Path)


def test_symbol_markets_parses_comma_separated_string_and_strips_whitespace(monkeypatch):
    monkeypatch.setenv("TOSS_SYMBOL_MARKETS", "KRX, NASDAQ ,  NYSE ")

    assert Settings(_env_file=None).symbol_markets == ["KRX", "NASDAQ", "NYSE"]


def test_symbol_markets_ignores_empty_entries(monkeypatch):
    monkeypatch.setenv("TOSS_SYMBOL_MARKETS", "KRX,,NASDAQ,")

    assert Settings(_env_file=None).symbol_markets == ["KRX", "NASDAQ"]


def test_cache_dir_expands_user(monkeypatch):
    monkeypatch.setenv("TOSS_CACHE_DIR", "~/somewhere/toss")

    cache_dir = Settings(_env_file=None).cache_dir

    assert "~" not in str(cache_dir)
    assert cache_dir.is_absolute()


def test_require_credentials_returns_pair(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "c_abc")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", SECRET)

    assert Settings(_env_file=None).require_credentials() == ("c_abc", SECRET)


def test_require_credentials_raises_when_missing(monkeypatch):
    monkeypatch.delenv("TOSS_CLIENT_ID", raising=False)
    monkeypatch.delenv("TOSS_CLIENT_SECRET", raising=False)

    with pytest.raises(ConfigError) as excinfo:
        Settings(_env_file=None).require_credentials()

    assert "TOSS_CLIENT_ID" in str(excinfo.value)


def test_credential_error_never_leaks_the_secret(monkeypatch):
    """A half-configured server must not echo the secret it does have."""
    monkeypatch.delenv("TOSS_CLIENT_ID", raising=False)
    monkeypatch.setenv("TOSS_CLIENT_SECRET", SECRET)

    with pytest.raises(ConfigError) as excinfo:
        Settings(_env_file=None).require_credentials()

    assert SECRET not in str(excinfo.value)
    assert "TOSS_CLIENT_ID" in str(excinfo.value)
    assert "TOSS_CLIENT_SECRET" not in str(excinfo.value)


def test_blank_credentials_are_treated_as_missing(monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_ID", "   ")
    monkeypatch.setenv("TOSS_CLIENT_SECRET", SECRET)

    with pytest.raises(ConfigError):
        Settings(_env_file=None).require_credentials()
