from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable

from fastmcp import FastMCP

from .client import BalatroMCPClient
from .runtime import AssistantRuntime, compact_state
from . import analysis

ToolHandler = Callable[..., dict[str, Any]]

PACK_SCREENS = {"SMODS_BOOSTER_OPENED", "TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK", "BUFFOON_PACK"}
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


def create_tool_handlers(client: Any, runtime: AssistantRuntime | None = None) -> dict[str, Callable[..., Any]]:
    action_history: list[dict[str, Any]] = []
    assistant = runtime or AssistantRuntime()

    def _read_state() -> dict[str, Any]:
        return assistant.observe(client.get_state())

    def _analysis_result(tool: str, params: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        result["scoring_data"] = assistant.catalog.scoring_data()
        assistant.write("analysis", tool=tool, params=params, result=result, strategy=assistant.config["strategy"])
        return result

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
        state = _read_state()
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
        expected_revision: str | None = None,
        card_uids: list[str] | None = None,
        control_mode: str | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        before = assistant.last_state or {}
        params = {"area": area, "index": index, "card_indices": card_indices, "mode": mode,
                  "seed": seed, "stake": stake, "blind": blind, "card_uids": card_uids,
                  "expected_revision": expected_revision, "control_mode": control_mode}
        planned_revision = expected_revision or (before.get("revision") if action != "set_control_mode" else None)
        try:
            before = _read_state()
            configured_mode = assistant.config["control_mode"]
            game_mode = before.get("control", {}).get("mode", "auto")
            active_mode = "assist" if game_mode == "assist" or configured_mode == "assist" else "auto"
            if action != "set_control_mode" and active_mode == "assist":
                raise ValueError("Assist mode: the human controls the game. Switch explicitly to auto before acting.")
            if planned_revision and planned_revision != before.get("revision"):
                raise ValueError("Stale game state: reread state before executing this action")
            extra: dict[str, Any] = {}
            context = {"source": "mcp", "tool_name": tool_name}
            if before.get("revision"):
                extra["expected_revision"] = before["revision"]
                context["request_id"] = uuid.uuid4().hex
            if card_uids is not None: extra["card_uids"] = card_uids
            if control_mode is not None: extra["control_mode"] = control_mode
            result = client.execute_action(action, area=area, index=index, card_indices=card_indices,
                                           mode=mode, seed=seed, stake=stake, blind=blind,
                                           client_context=context, **extra)
        except Exception as exc:
            assistant.record_action(tool_name, action, params, before, error=exc, elapsed_ms=(time.monotonic() - started) * 1000)
            raise
        assistant.record_action(tool_name, action, params, before, result=result, elapsed_ms=(time.monotonic() - started) * 1000)
        if isinstance(result.get("state"), dict): assistant.observe(result["state"])
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

    def get_game_state(compact: bool = False, include_descriptions: bool = False) -> dict[str, Any]:
        state = _read_state()
        if include_descriptions:
            areas = [state.get(name, {}).get("cards", []) for name in ["hand", "jokers", "consumeables", "pack"]]
            areas.extend(state.get("shop", {}).values())
            for cards in areas:
                for card in cards:
                    if card.get("facing") != "back": card["effect"] = assistant.catalog.describe(card.get("key", ""), card, state)
        return compact_state(state) if compact else state

    def get_raw_game_state() -> dict[str, Any]:
        state = client.get_state()
        assistant.observe(state)
        return state

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
        expected_revision: str | None = None,
        card_uids: list[str] | None = None,
        control_mode: str | None = None,
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
            expected_revision=expected_revision,
            card_uids=card_uids,
            control_mode=control_mode,
        )

    def wait_until_actionable(timeout: float = 30.0, poll_interval: float = 0.25) -> dict[str, Any]:
        return assistant.observe(client.wait_until_actionable(timeout=timeout, poll_interval=poll_interval))

    def continue_run(stake: int | None = None, seed: str | None = None) -> dict[str, Any]:
        state = _read_state()
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
        state = _read_state()
        if _is_pack_screen(_screen_name(state)):
            return _execute_action("choose_option", "use", area="pack", index=int(option_id))

        blind_name = _blind_from_option(option_id)
        if blind_name:
            return _execute_action("choose_option", "select_blind", blind=blind_name)

        return _execute_action("choose_option", "use", area="pack", index=int(option_id))

    def skip_choice() -> dict[str, Any]:
        state = _read_state()
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

    def play_hand(card_indices: list[int] | None = None, expected_revision: str | None = None) -> dict[str, Any]:
        return _execute_action("play_hand", "play_hand", card_indices=card_indices, expected_revision=expected_revision)

    def discard_selected(card_indices: list[int] | None = None, expected_revision: str | None = None) -> dict[str, Any]:
        return _execute_action("discard_selected", "discard", card_indices=card_indices, expected_revision=expected_revision)

    def end_turn() -> dict[str, Any]:
        state = _read_state()
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
        return {"history": assistant.history(capped, "action") or list(reversed(action_history[-capped:]))}

    def get_run_summary() -> dict[str, Any]:
        state = _read_state()
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

    def get_deck_summary(include_cards: bool = False) -> dict[str, Any]:
        state = _read_state()
        if "deck" not in state: return {"available": False, "reason": "Restart Balatro to load the new Mod"}
        deck = dict(state["deck"])
        if not include_cards: deck.pop("cards", None)
        return {"available": True, "revision": state.get("revision"), **deck}

    def describe_card(key: str | None = None, area: str = "jokers", index: int | None = None) -> dict[str, Any]:
        state = _read_state()
        card = None
        if index is not None:
            cards = state.get("shop", {}).get(area.removeprefix("shop_"), []) if area.startswith("shop_") else state.get(area, {}).get("cards", [])
            if not 1 <= index <= len(cards): raise ValueError("Invalid card area/index")
            card = cards[index - 1]
            if card.get("facing") == "back": return {"available": False, "reason": "Card is face down"}
            key = card.get("key")
        if not key: raise ValueError("Provide a center key or area and index")
        return assistant.catalog.describe(key, card, state)

    def get_scoring_model() -> dict[str, Any]:
        _read_state()
        return {"catalog": assistant.catalog.status, "scoring_data": assistant.catalog.scoring_data(), "cached_hand_definitions": assistant.hand_definitions,
                "supported_global_jokers": sorted(analysis.PASSIVE | analysis.X_JOKERS),
                "scope": "Pure deterministic model; each preview lists unmodeled effects and reports no exact score if partial"}

    def get_hand_history(limit: int = 10) -> dict[str, Any]:
        state = _read_state()
        limit = max(1, min(limit, 1000))
        entries = assistant.history(limit, "hand_result")
        observations = state.get("observations", {})
        last = observations.get("last_hand")
        candidates = ([last] if last else []) + list(reversed(observations.get("hands", []))) + [x["hand"] for x in entries]
        history, seen = [], set()
        for hand in candidates:
            if hand.get("id") not in seen:
                history.append(hand)
                seen.add(hand.get("id"))
        return {"last_hand": last, "history": history[:limit],
                "available": bool(state.get("capabilities", {}).get("scoring_observations")), "warnings": assistant.warnings}

    def preview_hand(card_indices: list[int] | None = None) -> dict[str, Any]:
        state = _read_state()
        result = analysis.preview_hand(state, card_indices)
        result["revision"] = state.get("revision")
        return _analysis_result("preview_hand", {"card_indices": card_indices}, result)

    def compare_plays(choices: list[list[int]]) -> dict[str, Any]:
        if not 1 <= len(choices) <= 30: raise ValueError("Compare 1..30 choices")
        state = _read_state()
        results = [analysis.preview_hand(state, choice) for choice in choices]
        strategy = assistant.config["strategy"]
        usable = [(i, r) for i, r in enumerate(results) if r.get("status") == "supported"]
        passing = [(i, r) for i, r in usable if r.get("passes_blind")]
        pool = passing or usable
        if strategy["objective"] == "record" or not passing:
            ranked = sorted(pool, key=lambda pair: pair[1]["score"], reverse=True)
        else:
            ranked = sorted(pool, key=lambda pair: (pair[1]["any_glass_break_probability"] if strategy["preserve_glass"] else 0, -pair[1]["score"]))
        return _analysis_result("compare_plays", {"choices": choices}, {"choices": results, "recommended_choice": ranked[0][0] + 1 if ranked else None,
                                "strategy": strategy, "revision": state.get("revision")})

    def compare_joker_swap(shop_index: int, replace_index: int, card_indices: list[int] | None = None,
                           placement: int | None = None) -> dict[str, Any]:
        state = _read_state()
        result = analysis.compare_swap(state, assistant.catalog, shop_index, replace_index, card_indices, placement, assistant.config["strategy"]["horizon_rounds"])
        result["below_cash_reserve"] = result["cash_after"] < assistant.config["strategy"]["min_cash"]
        result["strategy"] = assistant.config["strategy"]
        return _analysis_result("compare_joker_swap", {"shop_index": shop_index, "replace_index": replace_index, "placement": placement}, result)

    def compare_consumable(index: int, card_indices: list[int] | None = None) -> dict[str, Any]:
        result = analysis.compare_consumable(_read_state(), assistant.catalog, index, card_indices)
        return _analysis_result("compare_consumable", {"index": index}, result)

    def configure_assistant(patch: dict[str, Any], persist: bool = False) -> dict[str, Any]:
        result = assistant.configure(patch, persist=persist)
        assistant.write("configuration", configuration=result, persisted=persist)
        return {"configuration": result, "persisted": persist, "restart_for_language_change": "language" in patch}

    def get_assistant_config() -> dict[str, Any]:
        return {"configuration": assistant.config, "catalog": assistant.catalog.status, "warnings": assistant.warnings}

    def set_control_mode(mode: str, persist: bool = False) -> dict[str, Any]:
        if mode not in {"assist", "auto"}: raise ValueError("Mode must be assist or auto")
        result = _execute_action("set_control_mode", "set_control_mode", control_mode=mode)
        assistant.configure({"control_mode": mode}, persist=persist)
        if result.get("state"): assistant.observe(result["state"])
        return result

    def reorder_cards(area: str, card_uids: list[str], expected_revision: str | None = None) -> dict[str, Any]:
        return _execute_action("reorder_cards", "reorder_cards", area=area, card_uids=card_uids, expected_revision=expected_revision)

    def watch_state(after_revision: str | None = None, timeout: float = 25, poll_interval: float = .25) -> dict[str, Any]:
        return assistant.watch(client, after_revision, timeout, poll_interval)

    def get_log_history(limit: int = 20, kind: str | None = None) -> dict[str, Any]:
        return {"history": assistant.history(limit, kind), "logging": assistant.config["logging"], "warnings": assistant.warnings}

    return {
        "get_deck_summary": get_deck_summary, "describe_card": describe_card, "get_scoring_model": get_scoring_model,
        "get_hand_history": get_hand_history, "preview_hand": preview_hand, "compare_plays": compare_plays,
        "compare_joker_swap": compare_joker_swap, "compare_consumable": compare_consumable,
        "configure_assistant": configure_assistant, "get_assistant_config": get_assistant_config,
        "set_control_mode": set_control_mode, "reorder_cards": reorder_cards, "watch_state": watch_state, "get_log_history": get_log_history,
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
    def get_game_state(compact: bool = False, include_descriptions: bool = False) -> dict[str, Any]:
        """Read the current Balatro state snapshot."""
        return handlers["get_game_state"](compact=compact, include_descriptions=include_descriptions)

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
        expected_revision: str | None = None,
        card_uids: list[str] | None = None,
        control_mode: str | None = None,
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
            expected_revision=expected_revision,
            card_uids=card_uids,
            control_mode=control_mode,
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
    def play_hand(card_indices: list[int] | None = None, expected_revision: str | None = None) -> dict[str, Any]:
        """Play highlighted cards, or the supplied 1-based hand card indices."""
        return handlers["play_hand"](card_indices=card_indices, expected_revision=expected_revision)

    @mcp.tool
    def discard_selected(card_indices: list[int] | None = None, expected_revision: str | None = None) -> dict[str, Any]:
        """Discard highlighted cards, or the supplied 1-based hand card indices."""
        return handlers["discard_selected"](card_indices=card_indices, expected_revision=expected_revision)

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

    descriptions = {
        "get_deck_summary": "Read current playing-deck composition and draw/discard counts. Does not reveal draw order.",
        "describe_card": "Explain a card, blind, voucher or tag using localization reloaded from the installed game at MCP startup.",
        "get_scoring_model": "Read in-memory scoring definitions and model scope.",
        "get_hand_history": "Read preserved per-hand scores and native scoring trace, including manually played hands.",
        "preview_hand": "Read-only score preview. Partial/unsupported results never claim an exact score.",
        "compare_plays": "Compare candidate hands under the configured goal and glass preservation preference.",
        "compare_joker_swap": "Compare a shop Joker replacement, scoring order, cash cost, growth and known income.",
        "compare_consumable": "Compare using a Planet versus selling it, including permanent Constellation and temporary Campfire growth.",
        "configure_assistant": "Update optional strategy/logging/control preferences; persist only when requested.",
        "get_assistant_config": "Read optional assistant settings, catalog status and logging warnings.",
        "set_control_mode": "Explicitly switch shared game control between human assist and MCP auto mode.",
        "reorder_cards": "Reorder all hand or Joker cards by stable uid, with optional expected state revision.",
        "watch_state": "Wait up to 60 seconds for a revision change and return a compact state and changed sections.",
        "get_log_history": "Read persistent action, analysis, state, game event and hand-result logs across MCP restarts.",
    }
    for name, description in descriptions.items():
        mcp.tool(name=name, description=description)(handlers[name])
    return mcp


def main() -> None:
    server = create_server()
    transport = os.getenv("BALATRO_MCP_TRANSPORT", "stdio")
    server.run(transport=transport)


if __name__ == "__main__":
    main()
