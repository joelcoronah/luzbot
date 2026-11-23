"""Entry point: `python -m luzbot` (configuration comes from the environment)."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading

from . import __version__
from .config import Config, ConfigError
from .messages import Messages
from .monitor import Monitor
from .server import HeartbeatServer
from .storage import Storage
from .telegram import CommandListener, Notifier, TelegramClient

log = logging.getLogger("luzbot")


def _watch(monitor: Monitor, interval: float, stop: threading.Event) -> None:
    while not stop.wait(interval):
        try:
            monitor.check()
        except Exception:
            log.exception("check failed")


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"luzbot: configuration error: {exc}", file=sys.stderr)
        return 2

    storage = Storage(config.db_path)
    messages = Messages(config.language, config.timezone)
    client = TelegramClient(config.telegram_token, api_base=config.telegram_api_base)
    notifier = Notifier(client, config.telegram_chat_id)
    monitor = Monitor(storage, notifier, messages, config.timeout_seconds)

    listener = CommandListener(
        client,
        config.telegram_chat_id,
        handlers={
            "/start": lambda: messages("help"),
            "/help": lambda: messages("help"),
            "/ayuda": lambda: messages("help"),
            "/status": monitor.status_report,
            "/estado": monitor.status_report,
            "/history": monitor.history_report,
            "/historial": monitor.history_report,
            "/arm": monitor.arm,
            "/armar": monitor.arm,
            "/disarm": monitor.disarm,
            "/desarmar": monitor.disarm,
        },
        reply=notifier,
    )

    server = HeartbeatServer(
        (config.listen_host, config.listen_port), config.heartbeat_token, monitor.heartbeat
    )
    stop = threading.Event()

    def shutdown(signum: int, _frame: object) -> None:
        log.info("received signal %s, shutting down", signum)
        stop.set()
        listener.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    notifier.start()
    threading.Thread(
        target=_watch,
        args=(monitor, config.check_interval_seconds, stop),
        name="watcher",
        daemon=True,
    ).start()
    threading.Thread(target=listener.run, name="telegram-listener", daemon=True).start()

    log.info(
        "luzbot %s listening on %s:%s (timeout %ss, status %s)",
        __version__,
        config.listen_host,
        config.listen_port,
        config.timeout_seconds,
        monitor.status.value,
    )
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        notifier.stop()
        storage.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
