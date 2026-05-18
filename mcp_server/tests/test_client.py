from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from balatro_agent_mcp.client import BalatroAgentApiError, BalatroAgentClient


class FakeBalatroHandler(BaseHTTPRequestHandler):
    states: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    last_action: dict[str, Any] | None = None

    def log_message(self, *_: object) -> None:
        return

    def _write(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write(200, {"ok": True, "data": {"service": "balatro-mcp"}})
            return
        if self.path == "/state":
            state = self.states.pop(0) if self.states else {"screen": "MENU", "actionable": False}
            self._write(200, {"ok": True, "data": state})
            return
        if self.path == "/actions/available":
            self._write(200, {"ok": True, "data": {"actions": self.actions}})
            return
        if self.path == "/broken":
            self._write(409, {"ok": False, "error": {"code": "invalid_action", "message": "Nope"}})
            return
        self._write(404, {"ok": False, "error": {"code": "not_found", "message": "Missing"}})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.last_action = json.loads(body.decode("utf-8"))
        self._write(200, {"ok": True, "data": {"message": "queued", "state": {"screen": "SELECTING_HAND"}}})


@pytest.fixture()
def fake_server() -> str:
    FakeBalatroHandler.states = []
    FakeBalatroHandler.actions = [{"name": "start_run"}]
    FakeBalatroHandler.last_action = None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeBalatroHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def test_client_unwraps_successful_payloads(fake_server: str) -> None:
    client = BalatroAgentClient(base_url=fake_server, max_retries=0)

    assert client.get_health()["service"] == "balatro-mcp"
    assert client.get_available_actions() == [{"name": "start_run"}]


def test_client_posts_actions(fake_server: str) -> None:
    client = BalatroAgentClient(base_url=fake_server, max_retries=0)

    result = client.execute_action("play_hand", card_indices=[1, 2, 3])

    assert result["message"] == "queued"
    assert FakeBalatroHandler.last_action == {
        "action": "play_hand",
        "card_indices": [1, 2, 3],
        "index": None,
        "area": None,
        "mode": None,
        "seed": None,
        "stake": None,
        "blind": None,
        "client_context": None,
    }


def test_client_raises_api_error(fake_server: str) -> None:
    client = BalatroAgentClient(base_url=fake_server, max_retries=0)

    with pytest.raises(BalatroAgentApiError) as exc_info:
        client._request("GET", "/broken")

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_action"
    assert "Nope" in str(exc_info.value)


def test_wait_until_actionable_polls_until_state_is_ready(fake_server: str) -> None:
    FakeBalatroHandler.states = [
        {"screen": "MENU", "actionable": False},
        {"screen": "SELECTING_HAND", "actionable": True, "available_actions": ["play_hand"]},
    ]
    client = BalatroAgentClient(base_url=fake_server, max_retries=0)

    state = client.wait_until_actionable(timeout=2, poll_interval=0.01)

    assert state["screen"] == "SELECTING_HAND"
    assert state["available_actions"] == ["play_hand"]
