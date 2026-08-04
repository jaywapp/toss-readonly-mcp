"""Settings, read from the environment with a .env fallback.

MCP servers are launched by the client, which often does not pass the user's
shell environment through — hence the .env fallback.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from toss_mcp.errors import ConfigError

DEFAULT_MARKETS = ["KRX", "NASDAQ", "NYSE", "AMEX"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TOSS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    client_id: str | None = None
    client_secret: str | None = None
    api_base_url: str = "https://openapi.tossinvest.com"
    http_timeout: float = 10.0
    cache_dir: Path = Path("~/.cache/toss-mcp")
    symbol_ttl_days: int = 7
    # NoDecode: the raw env value is a comma-separated list, not JSON.
    symbol_markets: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_MARKETS)
    )
    log_level: str = "INFO"

    @field_validator("symbol_markets", mode="before")
    @classmethod
    def _split_markets(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("api_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("cache_dir", mode="after")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    def require_credentials(self) -> tuple[str, str]:
        """Return (client_id, client_secret), or explain exactly what is missing.

        The message names only the *missing* variables — never the value of one
        that happens to be set.
        """
        missing = [
            name
            for name, value in (
                ("TOSS_CLIENT_ID", self.client_id),
                ("TOSS_CLIENT_SECRET", self.client_secret),
            )
            if not (value or "").strip()
        ]
        if missing:
            raise ConfigError(
                f"{', '.join(missing)}가 설정되지 않았습니다. "
                ".env 파일이나 MCP 설정의 env 블록에 추가하세요. "
                "값은 토스증권 WTS > 설정 > Open API에서 발급합니다."
            )
        assert self.client_id and self.client_secret  # narrowed by the check above
        return self.client_id.strip(), self.client_secret.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
