from __future__ import annotations

import copy
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from balatro_mcp.analysis import compare_consumable, compare_swap, preview_hand
from balatro_mcp.catalog import GameCatalog, LuaDataReader
from balatro_mcp.runtime import AssistantRuntime
from balatro_mcp.server import create_server, create_tool_handlers


def archive(path: Path, name: str = "Test Joker") -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("localization/zh_CN.lua", 'return {descriptions={Joker={j_joker={name="' + name + '",text={"{C:mult}+#1#{} Mult"}}}},misc={}}')
        z.writestr("game.lua", 'j_joker={set="Joker",name="Joker",rarity=1,config={mult=4}}')
        for key in ["card.lua", "functions/state_events.lua", "functions/common_events.lua"]: z.writestr(key, name)
    return path


@pytest.fixture
def catalog(tmp_path):
    return GameCatalog(archive(tmp_path / "game.zip"))


@pytest.fixture
def runtime(tmp_path, catalog):
    return AssistantRuntime(tmp_path / "config.json", tmp_path / "logs", catalog)


def playing(rank_: int, suit="Spades", key="m_base", **fields):
    return {"uid": f"{suit}-{rank_}-{key}", "id": rank_, "rank": str(rank_), "suit": suit, "key": key,
            "nominal": 11 if rank_ == 14 else min(rank_, 10), "ability": {}, "facing": "front", **fields}


def joker(key, rarity=2, **attrs):
    return {"key": key, "rarity": rarity, "set": "Joker", "ability": attrs}


@pytest.fixture
def state():
    return {"screen": "SELECTING_HAND", "revision": "session:1", "control": {"mode": "auto"},
            "hand": {"cards": [playing(i) for i in range(2, 7)], "highlighted_indices": [1, 2, 3, 4, 5]},
            "jokers": {"cards": []}, "consumeables": {"cards": []}, "shop": {"jokers": []},
            "deck": {"total": 50, "starting_size": 52}, "blind": {"chips": 100},
            "run": {"dollars": 100, "discards_left": 3, "hands_left": 4, "chips": 0,
                    "hand_levels": {name: {"chips": chips, "mult": mult, "played": 0, "level": 1, "l_chips": 15, "l_mult": 2}
                                    for name, chips, mult in [("Flush", 35, 4), ("Straight Flush", 100, 8), ("Full House", 40, 4),
                                                              ("Flush House", 140, 14), ("Pair", 10, 2), ("High Card", 5, 1)]}}}


def test_catalog_refreshes_at_each_start_but_scoring_source_stays_cached(tmp_path):
    path = archive(tmp_path / "game.zip", "Before")
    first = GameCatalog(path)
    assert first.describe("j_joker")["description"] == ["+4 Mult"]
    sources = first.scoring_data()
    archive(path, "After")
    assert first.describe("j_joker")["name"] == "Before"
    assert first.scoring_data() == sources
    second = GameCatalog(path)
    assert second.describe("j_joker")["name"] == "After"
    assert second.scoring_data()["files"] != sources["files"]


def test_lua_data_reader_rejects_executable_values():
    assert LuaDataReader('{name="中文", data={1,2}, yes=true}').value()["name"] == "中文"
    with pytest.raises(ValueError): LuaDataReader('{x=os.execute("anything")}').value()


def test_unknown_description_variables_are_explicit(catalog):
    catalog.entries["j_custom"] = {"set": "Joker", "name": "Custom", "text": ["#1# and #2#"]}
    result = catalog.describe("j_custom")
    assert result["unresolved_variables"] == [1, 2]
    assert result["description"] == ["#1# and #2#"]


def test_full_house_and_flush_house_are_different(state):
    state["hand"]["cards"] = [playing(8), playing(8), playing(8), playing(14), playing(14, "Clubs")]
    assert preview_hand(state)["hand_type"] == "Full House"
    state["hand"]["cards"][-1]["suit"] = "Spades"
    assert preview_hand(state)["hand_type"] == "Flush House"


def test_ordinary_game_cards_use_c_base_in_play_and_held(state):
    baseline = preview_hand(state)
    for card in state["hand"]["cards"]: card["key"] = "c_base"
    state["hand"]["cards"].append(playing(10, "Clubs", "c_base"))
    result = preview_hand(state)
    assert result["status"] == "supported"
    assert result["score"] == baseline["score"]


def test_multiple_manual_hands_between_polls_are_logged_once(runtime, state):
    hands = [{"id": f"hand-{i}", "score": i * 100, "complete": True, "source": "human"} for i in range(1, 4)]
    state["observations"] = {"hands": hands, "last_hand": {**hands[-1], "trace": [{"chips": 10, "mult": 30}]}}
    runtime.observe(state)
    runtime.observe(state)
    records = runtime.history(20, "hand_result")
    assert len(records) == 3
    assert records[0]["hand"]["trace"] == [{"chips": 10, "mult": 30}]
    restarted = AssistantRuntime(runtime.config_path, runtime.log_dir, runtime.catalog)
    restarted.observe(state)
    assert len(restarted.history(20, "hand_result")) == 3


def test_independent_servers_append_large_journal_records_safely(runtime):
    other = AssistantRuntime(runtime.config_path, runtime.log_dir, runtime.catalog)
    def append(writer):
        for i in range(10): writer.write("concurrent_test", payload="x" * 200000, number=i)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(append, [runtime, other]))
    lines = next(runtime.log_dir.glob("events-*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 20
    assert all(len(json.loads(line)["payload"]) == 200000 for line in lines)
    assert not runtime.warnings and not other.warnings


def test_hack_glass_and_baseball_order_without_mutation(state):
    state["hand"]["cards"] = [playing(i) for i in [2, 3, 4, 5, 7]]
    state["hand"]["cards"][2].update(key="m_glass", ability={"x_mult": 2, "extra": 4})
    state["jokers"]["cards"] = [joker("j_hack", extra=1), joker("j_baseball", rarity=3, extra=1.5)]
    original = copy.deepcopy(state)
    result = preview_hand(state)
    # Base 35 + (2+3+4+5+7) + Hack repeats (2+3+4+5).
    assert result["score"] == (35 + 21 + 14) * 4 * 4 * 1.5
    assert result["glass_risks"][0]["break_probability"] == .25
    assert result["any_glass_break_probability"] == .25
    assert state == original


def test_erosion_position_changes_baseball_amplification(state):
    state["hand"]["cards"] = [playing(i) for i in [2, 3, 4, 5, 7]]
    a = joker("j_erosion", extra=4)
    b = joker("j_blackboard", extra=3)
    c = joker("j_baseball", rarity=3, extra=1.5)
    state["jokers"]["cards"] = [a, b, c]
    first = preview_hand(state)["score"]
    state["jokers"]["cards"] = [b, a, c]
    assert first > preview_hand(state)["score"]
    assert first == (35 + 21) * (4 + 8) * 1.5 * 3 * 1.5


def test_held_steel_red_seal_and_mime(state):
    state["hand"]["cards"] = [playing(i) for i in [2, 3, 4, 5, 7]] + [playing(9, "Clubs", "m_steel", ability={"h_x_mult": 1.5}, seal="Red")]
    state["jokers"]["cards"] = [joker("j_mime", extra=1)]
    result = preview_hand(state)
    assert result["mult"] == 4 * 1.5 ** 3


def test_copy_cycle_and_unknown_joker_never_claim_exact_score(state):
    state["jokers"]["cards"] = [joker("j_brainstorm", rarity=3)]
    assert preview_hand(state)["status"] == "partial"
    state["jokers"]["cards"] = [joker("j_custom")]
    assert preview_hand(state)["score"] is None
    assert "j_custom" in preview_hand(state)["unsupported_effects"]


def test_face_down_card_and_invalid_indices(state):
    state["hand"]["cards"][0]["facing"] = "back"
    assert preview_hand(state)["status"] == "unsupported"
    with pytest.raises(ValueError): preview_hand(state, [1, 1])
    with pytest.raises(ValueError): preview_hand(state, [99])


def test_stone_has_no_rank_or_face_effects(state):
    state["hand"]["cards"] = [playing(12, key="m_stone", ability={"bonus": 50})]
    state["hand"]["highlighted_indices"] = [1]
    state["jokers"]["cards"] = [joker("j_scary_face", extra=30), joker("j_even_steven", extra=4)]
    result = preview_hand(state)
    assert result["score"] == 55
    assert result["status"] == "supported"


def test_photograph_skips_debuffed_face(state):
    state["hand"]["cards"] = [playing(11, debuffed=True), playing(12), playing(13)]
    state["hand"]["highlighted_indices"] = [1, 2, 3]
    state["jokers"]["cards"] = [joker("j_splash"), joker("j_photograph", extra=2)]
    assert preview_hand(state)["score"] == 50


def test_blind_before_play_side_effects_do_not_claim_exact_score(state):
    state["blind"]["key"] = "bl_hook"
    assert preview_hand(state)["score"] is None
    state["blind"]["disabled"] = True
    assert preview_hand(state)["status"] == "supported"


def test_planet_use_and_sell_compare_permanent_and_temporary_growth(state, catalog):
    state["jokers"]["cards"] = [joker("j_constellation", x_mult=2.5, extra=.1), joker("j_campfire", rarity=3, x_mult=1.25, extra=.25)]
    state["consumeables"]["cards"] = [{"key": "c_mercury", "set": "Planet", "ability": {"hand_type": "Pair"}, "sell_cost": 1}]
    original = copy.deepcopy(state)
    result = compare_consumable(state, catalog, 1)
    assert result["use"]["mult"] / result["baseline"]["mult"] == pytest.approx(1.04)
    assert result["sell"]["mult"] / result["baseline"]["mult"] == pytest.approx(1.2)
    assert result["use_growth_permanent"]
    assert state == original


def test_swap_reports_lost_income_and_cash(state, catalog):
    state["jokers"]["cards"] = [joker("j_rocket", extra={"dollars": 15, "increase": 2})]
    state["jokers"]["cards"][0]["sell_cost"] = 2
    state["shop"]["jokers"] = [{**joker("j_erosion", extra=4), "cost": 4}]
    result = compare_swap(state, catalog, 1, 1, horizon_rounds=3)
    assert result["net_cost"] == 2
    assert result["cash_after"] == 98
    assert result["known_income_lost_over_horizon"] == 45


class FakeGame:
    def __init__(self, state): self.state, self.actions = state, []
    def get_state(self): return copy.deepcopy(self.state)
    def execute_action(self, action, **kwargs):
        self.actions.append((action, kwargs))
        if action == "set_control_mode": self.state["control"]["mode"] = kwargs["control_mode"]
        return {"action": action, "state": self.get_state()}


def test_hand_history_still_reads_native_memory_when_logging_disabled(runtime, state):
    runtime.configure({"logging": {"enabled": False}})
    hands = [{"id": f"h-{i}", "score": i, "complete": True} for i in range(1, 4)]
    state["observations"] = {"hands": hands, "last_hand": {**hands[-1], "trace": [{"mult": 3}]}}
    tools = create_tool_handlers(FakeGame(state), runtime)
    result = tools["get_hand_history"](2)
    assert [hand["score"] for hand in result["history"]] == [3, 2]
    assert result["history"][0]["trace"] == [{"mult": 3}]
    assert not runtime.log_dir.exists()


def test_assist_blocks_actions_but_can_handoff_and_failures_are_logged(runtime, state):
    state["control"]["mode"] = "assist"
    game = FakeGame(state)
    tools = create_tool_handlers(game, runtime)
    tools["get_game_state"]()
    with pytest.raises(ValueError, match="Assist"): tools["play_hand"]([1, 2, 3, 4, 5])
    assert game.actions == []
    assert runtime.history(1, "action")[0]["success"] is False
    tools["set_control_mode"]("auto")
    tools["play_hand"]([1, 2, 3, 4, 5])
    assert game.actions[-1][1]["expected_revision"] == "session:1"
    assert game.actions[-1][1]["client_context"]["request_id"]


def test_stale_revision_blocks_before_any_action(runtime, state):
    game = FakeGame(state)
    tools = create_tool_handlers(game, runtime)
    tools["get_game_state"]()
    game.state["revision"] = "session:2"
    with pytest.raises(ValueError, match="Stale"): tools["play_hand"]([1, 2, 3, 4, 5])
    assert not game.actions


def test_configuration_persists_and_logs_survive_restart(runtime, state):
    runtime.configure({"strategy": {"objective": "endless", "min_cash": 30}}, persist=True)
    runtime.observe(state)
    runtime.record_action("play_hand", "play_hand", {}, state, result={"score": 42})
    second = AssistantRuntime(runtime.config_path, runtime.log_dir, runtime.catalog)
    assert second.config["strategy"]["objective"] == "endless"
    assert second.history(1, "action")[0]["result"]["score"] == 42
    with pytest.raises(ValueError): second.configure({"strategy": {"horizon_rounds": -1}})


def test_native_events_and_hand_results_are_deduplicated_across_restart(runtime, state):
    state["observations"] = {"events": [{"id": "game:1", "kind": "hand_scored"}],
                             "last_hand": {"id": "hand:1", "complete": True, "score": 42}}
    runtime.observe(state)
    runtime.observe(state)
    second = AssistantRuntime(runtime.config_path, runtime.log_dir, runtime.catalog)
    second.observe(state)
    assert len(second.history(20, "game_event")) == 1
    assert len(second.history(20, "hand_result")) == 1


def test_watch_timeout_and_changed_state(runtime, state):
    game = FakeGame(state)
    result = runtime.watch(game, "session:1", timeout=0)
    assert not result["changed"]
    game.state["revision"] = "session:2"
    assert runtime.watch(game, "session:1", timeout=0)["changed"]


def test_strategy_prefers_glass_preservation_when_both_pass(runtime, state):
    state["hand"]["cards"] = [playing(i) for i in [2, 3, 5, 7, 9]] + [playing(4, key="m_glass", ability={"x_mult": 2, "extra": 4})]
    tools = create_tool_handlers(FakeGame(state), runtime)
    result = tools["compare_plays"]([[1, 2, 3, 4, 5], [1, 2, 3, 4, 6]])
    assert result["recommended_choice"] == 1
    runtime.configure({"strategy": {"objective": "record"}})
    assert tools["compare_plays"]([[1, 2, 3, 4, 5], [1, 2, 3, 4, 6]])["recommended_choice"] == 2


def test_new_tools_are_registered_with_schemas(state):
    import asyncio
    server = create_server(FakeGame(state))
    tools = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in tools}
    for name in ["get_deck_summary", "describe_card", "preview_hand", "compare_plays", "compare_joker_swap",
                 "compare_consumable", "configure_assistant", "reorder_cards", "watch_state", "set_control_mode", "get_log_history"]:
        assert name in by_name
    assert "expected_revision" in by_name["reorder_cards"].parameters["properties"]
