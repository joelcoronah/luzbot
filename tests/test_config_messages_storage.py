from zoneinfo import ZoneInfo

import pytest

from luzbot.config import Config, ConfigError
from luzbot.messages import Messages
from luzbot.storage import Storage

BASE_ENV = {
    "TELEGRAM_TOKEN": "123:abc",
    "TELEGRAM_CHAT_ID": "42",
    "HEARTBEAT_TOKEN": "x" * 32,
}


def test_config_defaults():
    config = Config.from_env(BASE_ENV)
    assert config.listen_host == "127.0.0.1"
    assert config.listen_port == 8787
    assert config.timeout_seconds == 180
    assert config.language == "es"


def test_config_overrides():
    config = Config.from_env(
        {**BASE_ENV, "TIMEZONE": "America/Caracas", "LANGUAGE": "EN", "TIMEOUT_SECONDS": "300"}
    )
    assert config.timezone == ZoneInfo("America/Caracas")
    assert config.language == "en"
    assert config.timeout_seconds == 300


@pytest.mark.parametrize(
    "override",
    [
        {"TELEGRAM_TOKEN": ""},
        {"HEARTBEAT_TOKEN": "short"},
        {"TIMEZONE": "Mars/Olympus"},
        {"LANGUAGE": "fr"},
        {"TIMEOUT_SECONDS": "10"},
        {"LISTEN_PORT": "abc"},
    ],
)
def test_config_errors(override):
    with pytest.raises(ConfigError):
        Config.from_env({**BASE_ENV, **override})


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (5, "menos de 1 min"),
        (60, "1 min"),
        (3600, "1 h"),
        (4680, "1 h 18 min"),
        (90_000, "1 d 1 h"),
    ],
)
def test_duration_es(seconds, expected):
    assert Messages("es").duration(seconds) == expected


def test_time_uses_timezone():
    messages = Messages("es", ZoneInfo("America/Caracas"))
    assert messages.time(1_795_449_600) == "23/11 12:00"


def test_storage_persists_to_disk(tmp_path):
    path = str(tmp_path / "data" / "luzbot.db")
    s = Storage(path)
    s.set("status", "online")
    s.open_outage(100.0)
    s.close()

    s = Storage(path)
    assert s.get("status") == "online"
    assert s.current_outage().started_at == 100.0
    closed = s.close_outage(400.0)
    assert closed.duration(0) == 300.0
    assert s.current_outage() is None
    assert s.close_outage(500.0) is None
    s.close()
