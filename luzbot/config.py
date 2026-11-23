"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .messages import SUPPORTED_LANGUAGES

MIN_TOKEN_LENGTH = 24
MIN_TIMEOUT_SECONDS = 60


class ConfigError(ValueError):
    """Raised when the configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    telegram_token: str
    telegram_chat_id: str
    heartbeat_token: str
    listen_host: str = "127.0.0.1"
    listen_port: int = 8787
    timeout_seconds: int = 180
    check_interval_seconds: int = 15
    db_path: str = "luzbot.db"
    timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("UTC"))
    language: str = "es"
    telegram_api_base: str = "https://api.telegram.org"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        env = os.environ if env is None else env

        def required(name: str) -> str:
            value = env.get(name, "").strip()
            if not value:
                raise ConfigError(f"{name} is required")
            return value

        def integer(name: str, default: int, minimum: int = 1) -> int:
            raw = env.get(name, "").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
            if value < minimum:
                raise ConfigError(f"{name} must be >= {minimum}")
            return value

        heartbeat_token = required("HEARTBEAT_TOKEN")
        if len(heartbeat_token) < MIN_TOKEN_LENGTH:
            raise ConfigError(
                f"HEARTBEAT_TOKEN must be at least {MIN_TOKEN_LENGTH} characters. Generate one "
                "with: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )

        tz_name = env.get("TIMEZONE", "UTC").strip() or "UTC"
        try:
            timezone = ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ConfigError(f"unknown TIMEZONE {tz_name!r}") from None

        language = env.get("LANGUAGE", "es").strip().lower() or "es"
        if language not in SUPPORTED_LANGUAGES:
            raise ConfigError(
                f"LANGUAGE must be one of {', '.join(SUPPORTED_LANGUAGES)}, got {language!r}"
            )

        return cls(
            telegram_token=required("TELEGRAM_TOKEN"),
            telegram_chat_id=required("TELEGRAM_CHAT_ID"),
            heartbeat_token=heartbeat_token,
            listen_host=env.get("LISTEN_HOST", "127.0.0.1").strip() or "127.0.0.1",
            listen_port=integer("LISTEN_PORT", 8787),
            timeout_seconds=integer("TIMEOUT_SECONDS", 180, minimum=MIN_TIMEOUT_SECONDS),
            check_interval_seconds=integer("CHECK_INTERVAL_SECONDS", 15),
            db_path=env.get("DB_PATH", "luzbot.db").strip() or "luzbot.db",
            timezone=timezone,
            language=language,
            telegram_api_base=env.get("TELEGRAM_API_BASE", "").strip()
            or "https://api.telegram.org",
        )
