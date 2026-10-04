from __future__ import annotations

import asyncio
from typing import Any

from balatro_mcp.server import create_server, create_tool_handlers


class FakeClient:
    def __init__(self) -> None:
        self.actions: list[tuple[str, dict[str, Any]]] = []
        self.state: dict[str, Any] = {
            "screen": "SHOP",
            "available_actions": ["end_shop"],
            "hand": {"highlighted_indices": [1], "cards": [{"index": 1}, {"index": 2}, {"index": 3}]},
            "run": {"dollars": 7, "hands_left": 3, "discards_left": 2, "ante": 1},
            "blind": {"name": "Small Blind", "chips": 300},
            "jokers": {"cards": [{"index": 1, "name": "Joker"}]},
            "consumeables": {"cards": [{"index": 1, "name": "The Fool"}]},
            "shop": {"jokers": [{"index": 1, "name": "Joker", "cost": 2}]},
        }

    def get_health(self) -> dict[str, Any]:
        return {"service": "balatro-mcp"}

    def get_state(self) -> dict[str, Any]:
        return self.state

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

    assert handlers["health_check"]() == {"service": "balatro-mcp"}
    assert handlers["get_game_state"]()["screen"] == "SHOP"
    assert handlers["get_raw_game_state"]()["screen"] == "SHOP"
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


def test_explicit_tool_handlers_route_to_existing_actions() -> None:
    client = FakeClient()
    handlers = create_tool_handlers(client)

    handlers["choose_blind"](option_id="boss")
    handlers["choose_option"](option_id="big")
    handlers["skip_choice"]()
    handlers["play_hand"](card_indices=[1, 2, 3, 4, 5])
    handlers["discard_selected"]()
    handlers["buy_item"](area="shop_jokers", index=1)
    handlers["reroll_shop"]()
    handlers["sell_joker"](index=1)
    handlers["use_consumable"](index=1, card_indices=[2])

    assert [action for action, _ in client.actions] == [
        "select_blind",
        "select_blind",
        "skip_blind",
        "play_hand",
        "discard",
        "buy",
        "reroll_shop",
        "sell",
        "use",
    ]
    assert client.actions[0][1]["blind"] == "Boss"
    assert client.actions[1][1]["blind"] == "Big"
    assert client.actions[5][1]["area"] == "shop_jokers"
    assert client.actions[8][1]["area"] == "consumeables"
    assert client.actions[8][1]["card_indices"] == [2]


def test_continue_run_uses_current_screen() -> None:
    client = FakeClient()
    handlers = create_tool_handlers(client)

    for screen, expected in [
        ("MENU", "start_run"),
        ("ROUND_EVAL", "cash_out"),
        ("SHOP", "end_shop"),
        ("TAROT_PACK", "skip_booster"),
        ("GAME_OVER", "return_to_menu"),
    ]:
        client.state["screen"] = screen
        handlers["continue_run"]()
        assert client.actions[-1][0] == expected


def test_select_and_deselect_card_preserve_other_highlights() -> None:
    client = FakeClient()
    handlers = create_tool_handlers(client)

    handlers["select_card"](index=2)
    assert client.actions[-1] == (
        "select_cards",
        {
            "area": None,
            "index": None,
            "card_indices": [1, 2],
            "mode": None,
            "seed": None,
            "stake": None,
            "blind": None,
            "client_context": {"source": "mcp", "tool_name": "select_card"},
        },
    )

    client.state["hand"]["highlighted_indices"] = [1, 2]
    handlers["deselect_card"](index=1)
    assert client.actions[-1][0] == "select_cards"
    assert client.actions[-1][1]["card_indices"] == [2]


def test_history_and_summary_are_available() -> None:
    client = FakeClient()
    handlers = create_tool_handlers(client)

    handlers["play_hand"](card_indices=[1, 2, 3, 4, 5])
    history = handlers["get_action_history"](limit=1)
    summary = handlers["get_run_summary"]()

    assert history["history"][0]["action"] == "play_hand"
    assert summary["screen"] == "SHOP"
    assert summary["money"] == 7
    assert summary["jokers"] == 1


def test_handler_surface_includes_reference_style_tools() -> None:
    handlers = create_tool_handlers(FakeClient())

    for name in [
        "list_legal_actions",
        "continue_run",
        "choose_option",
        "choose_blind",
        "skip_choice",
        "select_card",
        "deselect_card",
        "play_hand",
        "discard_selected",
        "end_turn",
        "buy_item",
        "reroll_shop",
        "sell_joker",
        "use_consumable",
        "get_action_history",
        "get_run_summary",
    ]:
        assert name in handlers


def test_fastmcp_server_registers_reference_style_tools() -> None:
    server = create_server(FakeClient())
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    for name in [
        "list_legal_actions",
        "continue_run",
        "choose_option",
        "choose_blind",
        "skip_choice",
        "select_card",
        "deselect_card",
        "play_hand",
        "discard_selected",
        "end_turn",
        "buy_item",
        "reroll_shop",
        "sell_joker",
        "use_consumable",
        "get_action_history",
        "get_run_summary",
    ]:
        assert name in names


def test_steamodded_booster_options_are_not_mistaken_for_blinds() -> None:
    client = FakeClient()
    client.state["screen"] = "SMODS_BOOSTER_OPENED"
    handlers = create_tool_handlers(client)
    for option in ["1", "2", "3"]:
        handlers["choose_option"](option)
        action, params = client.actions[-1]
        assert action == "use"
        assert params["area"] == "pack"
        assert params["index"] == int(option)
    handlers["skip_choice"]()
    assert client.actions[-1][0] == "skip_booster"
    handlers["continue_run"]()
    assert client.actions[-1][0] == "skip_booster"
