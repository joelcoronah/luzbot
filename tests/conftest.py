from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from luzbot.messages import Messages
from luzbot.monitor import Monitor
from luzbot.storage import Storage

# 2026-11-23 12:00:00 in Caracas (UTC-4)
T0 = 1_795_449_600.0


class FakeClock:
    def __init__(self, now: float = T0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def storage() -> Storage:
    s = Storage(":memory:")
    yield s
    s.close()


@pytest.fixture
def sent() -> list[str]:
    return []


@pytest.fixture
def messages() -> Messages:
    return Messages("en", ZoneInfo("America/Caracas"))


@pytest.fixture
def make_monitor(storage, sent, messages, clock):
    def factory(timeout: float = 180) -> Monitor:
        return Monitor(storage, sent.append, messages, timeout, clock=clock)

    return factory
