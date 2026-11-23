from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from luzbot.server import HeartbeatServer, parse_bool

TOKEN = "t" * 32


@pytest.fixture
def server():
    received: list[bool | None] = []
    srv = HeartbeatServer(("127.0.0.1", 0), TOKEN, received.append)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    srv.received = received
    srv.url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield srv
    srv.shutdown()
    srv.server_close()


def request(url, method="POST", headers=None, data=None):
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def test_bearer_token_accepted(server):
    status, _ = request(f"{server.url}/heartbeat", headers={"Authorization": f"Bearer {TOKEN}"})
    assert status == 204
    assert server.received == [None]


def test_query_token_and_charging(server):
    status, _ = request(f"{server.url}/heartbeat?token={TOKEN}&charging=false", method="GET")
    assert status == 204
    assert server.received == [False]


def test_x_token_header_with_form_body(server):
    status, _ = request(
        f"{server.url}/heartbeat",
        headers={"X-Token": TOKEN, "Content-Type": "application/x-www-form-urlencoded"},
        data=b"charging=on",
    )
    assert status == 204
    assert server.received == [True]


def test_json_body(server):
    status, _ = request(
        f"{server.url}/heartbeat",
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        data=json.dumps({"charging": True}).encode(),
    )
    assert status == 204
    assert server.received == [True]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"X-Token": "x"}])
def test_bad_token_rejected(server, headers):
    status, _ = request(f"{server.url}/heartbeat", headers=headers)
    assert status == 401
    assert server.received == []


def test_unknown_path_and_healthz(server):
    assert request(f"{server.url}/", method="GET")[0] == 404
    assert request(f"{server.url}/healthz", method="GET") == (200, b"ok\n")


def test_body_too_large(server):
    status, _ = request(
        f"{server.url}/heartbeat",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data=b"x" * 5000,
    )
    assert status == 413
    assert server.received == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("ON", True),
        ("sí", True),
        ("Charging", True),
        ("false", False),
        ("0", False),
        ("Discharging", False),
        ("", None),
        ("maybe", None),
        (None, None),
        (True, True),
    ],
)
def test_parse_bool(value, expected):
    assert parse_bool(value) is expected
