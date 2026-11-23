"""HTTP endpoint that receives heartbeats.

    POST /heartbeat            Authorization: Bearer <token>   -> 204
    GET  /heartbeat?token=...  (for clients that cannot set headers)
    GET  /healthz              -> 200 "ok" (no auth, meant for localhost)

An optional `charging` field (query string, form body or JSON body) lets a
phone report whether it is plugged in.
"""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 4096

_TRUE = {"1", "true", "yes", "on", "si", "sí", "charging", "connected", "plugged"}
_FALSE = {"0", "false", "no", "off", "discharging", "disconnected", "unplugged", "not charging"}


def parse_bool(value: object) -> bool | None:
    """Lenient boolean parser for values sent by automation apps."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


class HeartbeatServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        token: str,
        on_heartbeat: Callable[[bool | None], None],
    ) -> None:
        self.token = token.encode()
        self.on_heartbeat = on_heartbeat
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    server: HeartbeatServer
    server_version = "luzbot"
    sys_version = ""

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def log_message(self, format: str, *args: object) -> None:
        # The default logger prints the full request line, which may contain
        # the token in the query string. We log our own sanitized line instead.
        pass

    def _dispatch(self) -> None:
        url = urlsplit(self.path)
        if url.path == "/healthz" and self.command == "GET":
            self._respond(200, b"ok\n")
            return
        if url.path != "/heartbeat":
            self._respond(404)
            return

        fields: dict[str, object] = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            fields.update(self._read_body())
        except ValueError as exc:
            self._respond(400 if str(exc) != "too large" else 413)
            return

        if not self._authorized(fields):
            log.warning("rejected heartbeat with bad token from %s", self._client_ip())
            self._respond(401)
            return

        charging = parse_bool(fields.get("charging"))
        self.server.on_heartbeat(charging)
        log.debug("heartbeat from %s (charging=%s)", self._client_ip(), charging)
        self._respond(204)

    def _read_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("too large")
        raw = self.rfile.read(length)
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type == "application/json":
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                raise ValueError("invalid json") from None
            return data if isinstance(data, dict) else {}
        return {k: v[0] for k, v in parse_qs(raw.decode("utf-8", "replace")).items()}

    def _authorized(self, fields: dict[str, object]) -> bool:
        token = ""
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        token = token or self.headers.get("X-Token", "") or str(fields.get("token") or "")
        return bool(token) and hmac.compare_digest(token.encode(), self.server.token)

    def _client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For")
        return forwarded.split(",")[0].strip() if forwarded else self.client_address[0]

    def _respond(self, code: int, body: bytes = b"") -> None:
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        if body:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        if body:
            self.wfile.write(body)
