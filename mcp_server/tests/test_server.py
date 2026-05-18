from __future__ import annotations

from typing import Any

from balatro_agent_mcp.server import create_tool_handlers


class FakeClient:
    def __init__(self) -> None:
        self.actions: list[tuple[str, dict[str, Any]]] = []

    def get_health(self) -> dict[str, Any]:
        return {"service": "balatro-agent"}

    def get_state(self) -> dict[str, Any]:
        return {"screen": "SHOP"}

    def get_available_actions(self) -> list[dict[str, Any]]:
        return [{"name": "end_shop"}]

    def execute_action(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.actions.append((action, kwargs))
        return {"action": action, "state": {"screen": "BLIND_SELECT"}}

    def wait_until_actionable(self, timeout: float = 30.0, poll_interval: float = 0.25) -> dict[str, Any]:
        return {"screen": "SELECTING_HAND", "timeout": timeout, "poll_interval": poll_interval}


def test_tool_handlers_delegate_to_client() -> None:
    client = FakeClient()
    handlers = create_tool_handlers(client)

    assert handlers["health_check"]() == {"service": "balatro-agent"}
    assert handlers["get_game_state"]() == {"screen": "SHOP"}
    assert handlers["get_raw_game_state"]() == {"screen": "SHOP"}
    assert handlers["get_available_actions"]() == {"actions": [{"name": "end_shop"}]}
    assert handlers["wait_until_actionable"](timeout=1, poll_interval=0.1)["screen"] == "SELECTING_HAND"

    result = handlers["act"]("end_shop", area="shop_jokers", index=1)

    assert result["action"] == "end_shop"
    assert client.actions == [
        (
            "end_shop",
            {
                "area": "shop_jokers",
                "index": 1,
                "card_indices": None,
                "mode": None,
                "seed": None,
                "stake": None,
                "blind": None,
                "client_context": {"source": "mcp", "tool_name": "act"},
            },
        )
    ]
