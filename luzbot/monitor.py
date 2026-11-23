"""The heartbeat state machine.

    UNKNOWN --first heartbeat--> ONLINE --no heartbeat for `timeout`--> OFFLINE
                                   ^                                      |
                                   +------------ heartbeat ---------------+

State lives in SQLite, so restarting the service does not lose an ongoing
outage or send duplicate alerts.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import Enum

from .messages import Messages
from .storage import Storage

THIRTY_DAYS = 30 * 86_400


class Status(str, Enum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"


class Monitor:
    def __init__(
        self,
        storage: Storage,
        notify: Callable[[str], None],
        messages: Messages,
        timeout_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._storage = storage
        self._notify = notify
        self._msg = messages
        self._timeout = timeout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        # Grace period: after a restart, wait a full timeout before declaring
        # an outage, so downtime of the server itself is not blamed on home.
        self._started_at = clock()

    # -- state helpers ---------------------------------------------------

    @property
    def status(self) -> Status:
        return Status(self._storage.get("status", Status.UNKNOWN.value))

    @property
    def last_heartbeat(self) -> float | None:
        value = self._storage.get("last_heartbeat")
        return float(value) if value is not None else None

    def _set_status(self, status: Status) -> None:
        self._storage.set("status", status.value)

    # -- events ----------------------------------------------------------

    def heartbeat(self, charging: bool | None = None) -> None:
        """Record a heartbeat from home. `charging` is optional device info."""
        with self._lock:
            now = self._clock()
            status = self.status
            self._storage.set("last_heartbeat", repr(now))

            if status is Status.OFFLINE:
                outage = self._storage.close_outage(now)
                self._set_status(Status.ONLINE)
                started = outage.started_at if outage else now
                self._notify(
                    self._msg(
                        "restored",
                        now=self._msg.time(now),
                        start=self._msg.time(started),
                        duration=self._msg.duration(now - started),
                    )
                )
            elif status is Status.UNKNOWN:
                self._set_status(Status.ONLINE)
                self._notify(self._msg("monitor_started", time=self._msg.time(now)))

            self._track_charging(charging)

    def _track_charging(self, charging: bool | None) -> None:
        if charging is None:
            return
        warned = self._storage.get("unplugged_warned") == "1"
        if charging is False and not warned:
            self._storage.set("unplugged_warned", "1")
            self._notify(self._msg("unplugged"))
        elif charging is True and warned:
            self._storage.set("unplugged_warned", "0")
            self._notify(self._msg("replugged"))

    def check(self) -> None:
        """Declare an outage if heartbeats stopped. Call this periodically."""
        with self._lock:
            if self.status is not Status.ONLINE:
                return
            now = self._clock()
            last = self.last_heartbeat
            reference = max(last or 0.0, self._started_at)
            if now - reference <= self._timeout:
                return
            started = last if last is not None else reference
            self._storage.open_outage(started)
            self._set_status(Status.OFFLINE)
            self._notify(self._msg("outage", last=self._msg.time(started)))

    # -- reports for Telegram commands ----------------------------------

    def status_report(self) -> str:
        now = self._clock()
        status = self.status
        if status is Status.ONLINE and self.last_heartbeat is not None:
            last = self.last_heartbeat
            text = self._msg(
                "status_online", ago=self._msg.duration(now - last), last=self._msg.time(last)
            )
        elif status is Status.OFFLINE:
            outage = self._storage.current_outage()
            started = outage.started_at if outage else now
            text = self._msg(
                "status_offline",
                start=self._msg.time(started),
                ago=self._msg.duration(now - started),
            )
        else:
            return self._msg("status_unknown")
        return f"{text}\n\n{self._stats(now)}"

    def _stats(self, now: float) -> str:
        since = now - THIRTY_DAYS
        outages = self._storage.outages_since(since)
        total = sum(
            max(0.0, (o.ended_at if o.ended_at is not None else now) - max(o.started_at, since))
            for o in outages
        )
        return self._msg("stats_30d", count=len(outages), total=self._msg.duration(total))

    def history_report(self, limit: int = 10) -> str:
        now = self._clock()
        outages = self._storage.recent_outages(limit)
        if not outages:
            return self._msg("history_empty")
        lines = [self._msg("history_header")]
        for outage in outages:
            end = (
                self._msg.time(outage.ended_at)
                if outage.ended_at is not None
                else self._msg("ongoing")
            )
            lines.append(
                self._msg(
                    "history_item",
                    start=self._msg.time(outage.started_at),
                    end=end,
                    duration=self._msg.duration(outage.duration(now)),
                )
            )
        return "\n".join(lines)
