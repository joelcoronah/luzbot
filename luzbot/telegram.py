"""Minimal Telegram Bot API client, a retrying notifier and a command listener."""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, timeout: float = 20, api_base: str = API_BASE) -> None:
        self._token = token
        self._timeout = timeout
        self._api_base = api_base.rstrip("/")

    def call(self, method: str, params: Mapping[str, Any], timeout: float | None = None) -> Any:
        data = urlencode({k: v for k, v in params.items() if v is not None}).encode()
        # The URL contains the bot token: never log it or put it in exceptions.
        request = Request(f"{self._api_base}/bot{self._token}/{method}", data=data)
        try:
            with urlopen(request, timeout=timeout or self._timeout) as response:
                payload = json.load(response)
        except HTTPError as exc:
            try:
                description = json.load(exc).get("description", "")
            except Exception:
                description = ""
            raise TelegramError(f"{method}: HTTP {exc.code} {description}".strip()) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise TelegramError(f"{method}: network error: {reason}") from None
        if not payload.get("ok"):
            raise TelegramError(f"{method}: {payload.get('description', 'unknown error')}")
        return payload["result"]

    def send_message(self, chat_id: str, text: str) -> None:
        self.call("sendMessage", {"chat_id": chat_id, "text": text})

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        return self.call(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'},
            timeout=timeout + 10,
        )


class Notifier:
    """Queues messages and delivers them in the background, retrying forever.

    An alert must not be lost because Telegram or the network hiccuped, and
    the monitor must never block on the network.
    """

    def __init__(
        self,
        client: TelegramClient,
        chat_id: str,
        initial_backoff: float = 2,
        max_backoff: float = 300,
    ) -> None:
        self._client = client
        self._chat_id = chat_id
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, name="notifier", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def __call__(self, text: str) -> None:
        log.info("notify: %s", text.replace("\n", " | "))
        self._queue.put(text)

    def stop(self, timeout: float = 5) -> None:
        self._stopping.set()
        self._queue.put(None)
        if self._thread.is_alive():
            self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            text = self._queue.get()
            if text is None:
                return
            backoff = self._initial_backoff
            while True:
                try:
                    self._client.send_message(self._chat_id, text)
                    break
                except TelegramError as exc:
                    log.warning("could not send message, retrying in %ss: %s", backoff, exc)
                    if self._stopping.wait(backoff):
                        return
                    backoff = min(backoff * 2, self._max_backoff)


class CommandListener:
    """Long-polls Telegram and answers commands from the configured chat only."""

    def __init__(
        self,
        client: TelegramClient,
        chat_id: str,
        handlers: Mapping[str, Callable[[], str]],
        reply: Callable[[str], None],
        poll_timeout: int = 50,
    ) -> None:
        self._client = client
        self._chat_id = str(chat_id)
        self._handlers = dict(handlers)
        self._reply = reply
        self._poll_timeout = poll_timeout
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        offset = self._skip_backlog()
        while not self._stop.is_set():
            try:
                updates = self._client.get_updates(offset, self._poll_timeout)
            except TelegramError as exc:
                log.warning("getUpdates failed: %s", exc)
                self._stop.wait(5)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                self.handle_update(update)

    def _skip_backlog(self) -> int | None:
        """Ignore commands sent while the bot was down."""
        try:
            updates = self._client.get_updates(-1, 0)
        except TelegramError as exc:
            log.warning("could not skip update backlog: %s", exc)
            return None
        return updates[-1]["update_id"] + 1 if updates else None

    def handle_update(self, update: Mapping[str, Any]) -> None:
        message = update.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        if chat_id != self._chat_id:
            log.info("ignoring message from unknown chat %s", chat_id or "?")
            return
        words = (message.get("text") or "").split()
        if not words:
            return
        command = words[0].split("@", 1)[0].lower()
        handler = self._handlers.get(command)
        if handler is not None:
            self._reply(handler())
