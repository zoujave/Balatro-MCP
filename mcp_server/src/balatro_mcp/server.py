from __future__ import annotations

import os
from typing import Any, Callable

from fastmcp import FastMCP

from .client import BalatroMCPClient

ToolHandler = Callable[..., dict[str, Any]]

PACK_SCREENS = {"TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK", "BUFFOON_PACK"}
BLIND_OPTIONS = {
    "small": "Small",
    "small_blind": "Small",
    "1": "Small",
    "big": "Big",
    "big_blind": "Big",
    "2": "Big",
    "boss": "Boss",
    "boss_blind": "Boss",
    "3": "Boss",
}
MAX_HISTORY = 200


def create_tool_handlers(client: Any) -> dict[str, Callable[..., Any]]:
    action_history: list[dict[str, Any]] = []

    def _screen_name(state: dict[str, Any]) -> str:
        return str(state.get("screen") or "").upper()

    def _is_pack_screen(screen: str) -> bool:
        return screen in PACK_SCREENS or screen.endswith("_PACK")

    def _blind_from_option(option_id: str | None) -> str | None:
        if option_id is None:
            return None
        return BLIND_OPTIONS.get(str(option_id).strip().lower())

    def _normalize_indices(indices: list[int] | None) -> list[int]:
        if indices is None:
            return []
        normalized: list[int] = []
        for value in indices:
            index = int(value)
            if index not in normalized:
                normalized.append(index)
        return normalized

    def _highlighted_indices() -> list[int]:
        state = client.get_state()
        hand = state.get("hand") if isinstance(state.get("hand"), dict) else {}
        return _normalize_indices(hand.get("highlighted_indices"))

    def _record_action(tool_name: str, action: str, params: dict[str, Any], result: dict[str, Any]) -> None:
        action_history.append(
            {
                "tool": tool_name,
                "action": action,
                "params": {key: value for key, value in params.items() if value is not None},
                "result": result,
            }
        )
        del action_history[:-MAX_HISTORY]

    def _execute_action(
        tool_name: str,
        action: str,
        *,
        area: str | None = None,
        index: int | None = None,
        card_indices: list[int] | None = None,
        mode: str | None = None,
        seed: str | None = None,
        stake: int | None = None,
        blind: str | None = None,
    ) -> dict[str, Any]:
        result = client.execute_action(
            action,
            area=area,
            index=index,
            card_indices=card_indices,
            mode=mode,
            seed=seed,
            stake=stake,
            blind=blind,
            client_context={"source": "mcp", "tool_name": tool_name},
        )
        _record_action(
            tool_name,
            action,
            {
                "area": area,
                "index": index,
                "card_indices": card_indices,
                "mode": mode,
                "seed": seed,
                "stake": stake,
                "blind": blind,
            },
            result,
        )
        return result

    def health_check() -> dict[str, Any]:
        return client.get_health()

    def get_game_state() -> dict[str, Any]:
        return client.get_state()

    def get_raw_game_state() -> dict[str, Any]:
        return client.get_state()

    def get_available_actions() -> dict[str, Any]:
        return {"actions": client.get_available_actions()}

    def list_legal_actions() -> dict[str, Any]:
        return get_available_actions()

    def act(
        action: str,
        *,
        area: str | None = None,
        index: int | None = None,
        card_indices: list[int] | None = None,
        mode: str | None = None,
        seed: str | None = None,
        stake: int | None = None,
        blind: str | None = None,
    ) -> dict[str, Any]:
        return _execute_action(
            "act",
            action,
            area=area,
            index=index,
            card_indices=card_indices,
            mode=mode,
            seed=seed,
            stake=stake,
            blind=blind,
        )

    def wait_until_actionable(timeout: float = 30.0, poll_interval: float = 0.25) -> dict[str, Any]:
        return client.wait_until_actionable(timeout=timeout, poll_interval=poll_interval)

    def continue_run(stake: int | None = None, seed: str | None = None) -> dict[str, Any]:
        state = client.get_state()
        screen = _screen_name(state)
        if screen == "MENU":
            return _execute_action("continue_run", "start_run", stake=stake, seed=seed)
        if screen == "ROUND_EVAL":
            return _execute_action("continue_run", "cash_out")
        if screen == "SHOP":
            return _execute_action("continue_run", "end_shop")
        if _is_pack_screen(screen):
            return _execute_action("continue_run", "skip_booster")
        if screen == "GAME_OVER":
            return _execute_action("continue_run", "return_to_menu")
        raise ValueError(f"Cannot continue from current Balatro screen: {screen or 'UNKNOWN'}")

    def choose_blind(option_id: str | None = None, blind: str | None = None) -> dict[str, Any]:
        blind_name = blind or _blind_from_option(option_id)
        return _execute_action("choose_blind", "select_blind", blind=blind_name)

    def choose_option(option_id: str) -> dict[str, Any]:
        state = client.get_state()
        if _is_pack_screen(_screen_name(state)):
            return _execute_action("choose_option", "use", area="pack", index=int(option_id))

        blind_name = _blind_from_option(option_id)
        if blind_name:
            return _execute_action("choose_option", "select_blind", blind=blind_name)

        return _execute_action("choose_option", "use", area="pack", index=int(option_id))

    def skip_choice() -> dict[str, Any]:
        state = client.get_state()
        if _is_pack_screen(_screen_name(state)):
            return _execute_action("skip_choice", "skip_booster")
        return _execute_action("skip_choice", "skip_blind")

    def select_card(index: int) -> dict[str, Any]:
        selected = _highlighted_indices()
        card_index = int(index)
        if card_index not in selected:
            selected.append(card_index)
        return _execute_action("select_card", "select_cards", card_indices=selected)

    def deselect_card(index: int) -> dict[str, Any]:
        card_index = int(index)
        selected = [existing for existing in _highlighted_indices() if existing != card_index]
        return _execute_action("deselect_card", "select_cards", card_indices=selected)

    def play_hand(card_indices: list[int] | None = None) -> dict[str, Any]:
        return _execute_action("play_hand", "play_hand", card_indices=card_indices)

    def discard_selected(card_indices: list[int] | None = None) -> dict[str, Any]:
        return _execute_action("discard_selected", "discard", card_indices=card_indices)

    def end_turn() -> dict[str, Any]:
        state = client.get_state()
        screen = _screen_name(state)
        if screen == "ROUND_EVAL":
            return _execute_action("end_turn", "cash_out")
        if screen == "SHOP":
            return _execute_action("end_turn", "end_shop")
        if _is_pack_screen(screen):
            return _execute_action("end_turn", "skip_booster")
        if screen == "GAME_OVER":
            return _execute_action("end_turn", "return_to_menu")
        raise ValueError(f"Cannot end turn from current Balatro screen: {screen or 'UNKNOWN'}")

    def buy_item(index: int, area: str = "shop_jokers") -> dict[str, Any]:
        return _execute_action("buy_item", "buy", area=area, index=int(index))

    def reroll_shop() -> dict[str, Any]:
        return _execute_action("reroll_shop", "reroll_shop")

    def sell_joker(index: int) -> dict[str, Any]:
        return _execute_action("sell_joker", "sell", area="jokers", index=int(index))

    def use_consumable(index: int, card_indices: list[int] | None = None) -> dict[str, Any]:
        return _execute_action("use_consumable", "use", area="consumeables", index=int(index), card_indices=card_indices)

    def get_action_history(limit: int = 20) -> dict[str, Any]:
        capped = max(1, min(int(limit), MAX_HISTORY))
        return {"history": list(reversed(action_history[-capped:]))}

    def get_run_summary() -> dict[str, Any]:
        state = client.get_state()
        run = state.get("run") if isinstance(state.get("run"), dict) else {}
        hand = state.get("hand") if isinstance(state.get("hand"), dict) else {}
        blind_state = state.get("blind") if isinstance(state.get("blind"), dict) else {}
        jokers = state.get("jokers") if isinstance(state.get("jokers"), dict) else {}
        consumeables = state.get("consumeables") if isinstance(state.get("consumeables"), dict) else {}
        shop = state.get("shop") if isinstance(state.get("shop"), dict) else {}

        joker_cards = jokers.get("cards") if isinstance(jokers.get("cards"), list) else []
        consumable_cards = consumeables.get("cards") if isinstance(consumeables.get("cards"), list) else []
        hand_cards = hand.get("cards") if isinstance(hand.get("cards"), list) else []
        shop_items = sum(len(cards) for cards in shop.values() if isinstance(cards, list))

        return {
            "screen": state.get("screen"),
            "stage": state.get("stage"),
            "actionable": state.get("actionable"),
            "available_actions": state.get("available_actions", []),
            "money": run.get("dollars"),
            "ante": run.get("ante"),
            "hands_left": run.get("hands_left"),
            "discards_left": run.get("discards_left"),
            "chips": run.get("chips"),
            "blind": blind_state.get("name") or blind_state.get("key"),
            "blind_chips": blind_state.get("chips"),
            "hand_cards": len(hand_cards),
            "selected_cards": hand.get("highlighted_indices", []),
            "jokers": len(joker_cards),
            "consumables": len(consumable_cards),
            "shop_items": shop_items,
        }

    return {
        "health_check": health_check,
        "get_game_state": get_game_state,
        "get_raw_game_state": get_raw_game_state,
        "get_available_actions": get_available_actions,
        "list_legal_actions": list_legal_actions,
        "act": act,
        "wait_until_actionable": wait_until_actionable,
        "continue_run": continue_run,
        "choose_option": choose_option,
        "choose_blind": choose_blind,
        "skip_choice": skip_choice,
        "select_card": select_card,
        "deselect_card": deselect_card,
        "play_hand": play_hand,
        "discard_selected": discard_selected,
        "end_turn": end_turn,
        "buy_item": buy_item,
        "reroll_shop": reroll_shop,
        "sell_joker": sell_joker,
        "use_consumable": use_consumable,
        "get_action_history": get_action_history,
        "get_run_summary": get_run_summary,
    }


def create_server(client: BalatroMCPClient | None = None) -> FastMCP:
    balatro = client or BalatroMCPClient()
    handlers = create_tool_handlers(balatro)
    mcp = FastMCP("Balatro MCP")

    @mcp.tool
    def health_check() -> dict[str, Any]:
        """Check whether the Balatro MCP mod is loaded and reachable."""
        return handlers["health_check"]()

    @mcp.tool
    def get_game_state() -> dict[str, Any]:
        """Read the current Balatro state snapshot."""
        return handlers["get_game_state"]()

    @mcp.tool
    def get_raw_game_state() -> dict[str, Any]:
        """Read the raw state snapshot for debugging or schema inspection."""
        return handlers["get_raw_game_state"]()

    @mcp.tool
    def get_available_actions() -> dict[str, Any]:
        """List legal actions for the current Balatro state."""
        return handlers["get_available_actions"]()

    @mcp.tool
    def list_legal_actions() -> dict[str, Any]:
        """List legal actions for the current Balatro state."""
        return handlers["list_legal_actions"]()

    @mcp.tool
    def act(
        action: str,
        area: str | None = None,
        index: int | None = None,
        card_indices: list[int] | None = None,
        mode: str | None = None,
        seed: str | None = None,
        stake: int | None = None,
        blind: str | None = None,
    ) -> dict[str, Any]:
        """Execute a Balatro action exposed by the local mod."""
        return handlers["act"](
            action,
            area=area,
            index=index,
            card_indices=card_indices,
            mode=mode,
            seed=seed,
            stake=stake,
            blind=blind,
        )

    @mcp.tool
    def wait_until_actionable(timeout: float = 30.0, poll_interval: float = 0.25) -> dict[str, Any]:
        """Poll game state until at least one legal action is available."""
        return handlers["wait_until_actionable"](timeout=timeout, poll_interval=poll_interval)

    @mcp.tool
    def continue_run(stake: int | None = None, seed: str | None = None) -> dict[str, Any]:
        """Advance through menu, reward, shop, pack, or game-over screens."""
        return handlers["continue_run"](stake=stake, seed=seed)

    @mcp.tool
    def choose_option(option_id: str) -> dict[str, Any]:
        """Choose a blind or pack option by option id."""
        return handlers["choose_option"](option_id=option_id)

    @mcp.tool
    def choose_blind(option_id: str | None = None, blind: str | None = None) -> dict[str, Any]:
        """Choose a blind by option id such as small, big, boss, or by blind name."""
        return handlers["choose_blind"](option_id=option_id, blind=blind)

    @mcp.tool
    def skip_choice() -> dict[str, Any]:
        """Skip the current blind or booster-pack choice."""
        return handlers["skip_choice"]()

    @mcp.tool
    def select_card(index: int) -> dict[str, Any]:
        """Highlight one hand card by its 1-based hand index."""
        return handlers["select_card"](index=index)

    @mcp.tool
    def deselect_card(index: int) -> dict[str, Any]:
        """Remove one hand card from the current highlighted selection."""
        return handlers["deselect_card"](index=index)

    @mcp.tool
    def play_hand(card_indices: list[int] | None = None) -> dict[str, Any]:
        """Play highlighted cards, or the supplied 1-based hand card indices."""
        return handlers["play_hand"](card_indices=card_indices)

    @mcp.tool
    def discard_selected(card_indices: list[int] | None = None) -> dict[str, Any]:
        """Discard highlighted cards, or the supplied 1-based hand card indices."""
        return handlers["discard_selected"](card_indices=card_indices)

    @mcp.tool
    def end_turn() -> dict[str, Any]:
        """Leave reward, shop, pack, or game-over screens when legal."""
        return handlers["end_turn"]()

    @mcp.tool
    def buy_item(index: int, area: str = "shop_jokers") -> dict[str, Any]:
        """Buy a shop item by area and 1-based index."""
        return handlers["buy_item"](index=index, area=area)

    @mcp.tool
    def reroll_shop() -> dict[str, Any]:
        """Reroll the current shop."""
        return handlers["reroll_shop"]()

    @mcp.tool
    def sell_joker(index: int) -> dict[str, Any]:
        """Sell a joker by its 1-based joker area index."""
        return handlers["sell_joker"](index=index)

    @mcp.tool
    def use_consumable(index: int, card_indices: list[int] | None = None) -> dict[str, Any]:
        """Use a consumable by its 1-based consumable area index."""
        return handlers["use_consumable"](index=index, card_indices=card_indices)

    @mcp.tool
    def get_action_history(limit: int = 20) -> dict[str, Any]:
        """Return recent actions executed through this MCP server process."""
        return handlers["get_action_history"](limit=limit)

    @mcp.tool
    def get_run_summary() -> dict[str, Any]:
        """Return a compact summary of the current run."""
        return handlers["get_run_summary"]()

    return mcp


def main() -> None:
    server = create_server()
    transport = os.getenv("BALATRO_MCP_TRANSPORT", "stdio")
    server.run(transport=transport)


if __name__ == "__main__":
    main()
