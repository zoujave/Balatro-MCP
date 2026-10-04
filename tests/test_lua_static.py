from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOD_DIR = ROOT / "mods" / "BalatroMCP"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_steamodded_manifest_points_to_entrypoint() -> None:
    manifest_path = MOD_DIR / "BalatroMCP.json"

    manifest = json.loads(read_text(manifest_path))

    assert manifest["id"] == "BalatroMCP"
    assert manifest["name"] == "Balatro MCP"
    assert manifest["main_file"] == "BalatroMCP.lua"
    assert manifest["prefix"] == "bmcp"
    assert "Steamodded" in manifest["dependencies"]


def test_lua_entrypoint_wraps_game_update() -> None:
    entrypoint = read_text(MOD_DIR / "BalatroMCP.lua")

    assert "BalatroMCP" in entrypoint
    assert "Game.update" in entrypoint
    assert "BalatroMCP.update" in entrypoint
    assert "balatro_mcp/json.lua" in entrypoint
    assert "BALATRO_MCP_PORT" in entrypoint


def test_http_server_uses_nonblocking_local_routes() -> None:
    http_server = read_text(MOD_DIR / "balatro_mcp" / "http_server.lua")

    assert 'require("socket")' in http_server
    assert "127.0.0.1" in http_server
    assert "8080" in http_server
    assert ":settimeout(0)" in http_server
    assert 'GET /health' in http_server
    assert 'GET /state' in http_server
    assert 'GET /actions/available' in http_server
    assert 'POST /action' in http_server
    assert "Content-Type: application/json" in http_server


def test_state_module_exports_balatro_payload_sections() -> None:
    state_module = read_text(MOD_DIR / "balatro_mcp" / "state.lua")

    assert "build_state" in state_module
    for section in [
        "session",
        "run",
        "blind",
        "hand",
        "jokers",
        "consumeables",
        "shop",
        "pack",
    ]:
        assert section in state_module


def test_action_module_exposes_core_balatro_actions() -> None:
    action_module = read_text(MOD_DIR / "balatro_mcp" / "actions.lua")

    for action in [
        "start_run",
        "select_blind",
        "skip_blind",
        "play_hand",
        "discard",
        "cash_out",
        "end_shop",
        "reroll_shop",
        "buy",
        "use",
        "sell",
        "skip_booster",
        "sort_hand",
    ]:
        assert action in action_module

    assert "G.FUNCS.play_cards_from_highlighted" in action_module
    assert "G.FUNCS.discard_cards_from_highlighted" in action_module
    assert "G.FUNCS.go_to_menu" not in action_module
    assert "G:main_menu" in action_module


def test_select_blind_uses_current_blind_config_not_raw_key() -> None:
    action_module = read_text(MOD_DIR / "balatro_mcp" / "actions.lua")

    assert "not G.blind_select or not G.blind_prompt_box" in action_module
    assert "state == \"Select\"" in action_module
    assert "local choice = choice_key and G.P_BLINDS and G.P_BLINDS[choice_key]" in action_module
    assert "get_UIE_by_ID(\"select_blind_button\")" in action_module
    assert "G.FUNCS.select_blind(select_button)" in action_module


def test_state_only_exposes_ui_backed_actions_when_ready() -> None:
    state_module = read_text(MOD_DIR / "balatro_mcp" / "state.lua")

    assert 'if screen == "MENU" then' in state_module
    assert 'screen == "SPLASH"' not in state_module
    assert "local blind_ui_ready = G and G.blind_select and G.blind_prompt_box" in state_module
    assert 'if screen == "BLIND_SELECT" and blind_ui_ready then' in state_module
    assert 'if screen == "GAME_OVER" then' in state_module
    assert "if G and G.STAGE == G.STAGES.RUN then" not in state_module


def test_lua_actions_use_pending_action_lock() -> None:
    action_module = read_text(MOD_DIR / "balatro_mcp" / "actions.lua")
    state_module = read_text(MOD_DIR / "balatro_mcp" / "state.lua")

    assert "ACTION_LOCK_SECONDS" in action_module
    assert "action_lock_active(mcp)" in action_module
    assert '"action_pending"' in action_module
    assert "set_action_lock(mcp, action)" in action_module
    assert "busy = action_lock_active(mcp)" in state_module
    assert "if busy then" in state_module


def test_cash_out_waits_for_round_eval_payout_to_finish() -> None:
    action_module = read_text(MOD_DIR / "balatro_mcp" / "actions.lua")
    state_module = read_text(MOD_DIR / "balatro_mcp" / "state.lua")

    assert "round_eval_ready" in state_module
    assert "local can_cash_out = round_eval_ready()" in state_module
    assert 'if screen == "ROUND_EVAL" and can_cash_out then' in state_module
    assert "current_round.dollars" in state_module
    assert "current_round.dollars" in action_module
    assert 'get_UIE_by_ID("cash_out_button")' in action_module
    assert 'get_UIE_by_ID("cash_out_button")' in state_module
    assert "pcall(G.FUNCS.cash_out, button)" in action_module
    cash_out = action_module.split("local function action_cash_out(mcp)", 1)[1].split("local function action_end_shop", 1)[0]
    assert "clear_queue" not in cash_out
    assert "ease_dollars" not in cash_out


def test_play_hand_treats_temporary_blind_blocks_as_retryable() -> None:
    action_module = read_text(MOD_DIR / "balatro_mcp" / "actions.lua")

    assert "same_hand_selection" in action_module
    assert "return true, true" in action_module
    assert '"The current blind is temporarily blocking hand play."' in action_module
    assert 'fail("blocked", "The current blind is temporarily blocking hand play.", nil, 503, true)' in action_module


def test_windows_scripts_cover_install_start_validate_and_package() -> None:
    scripts = {
        "install-local.ps1": [
            "D:\\SteamLibrary\\steamapps\\common\\Balatro",
            "AppData",
            "BalatroMCP",
            "Mods",
        ],
        "start-mcp-stdio.ps1": ["uv run balatro-mcp-server"],
        "start-mcp-network.ps1": ["uv run balatro-network-mcp-server"],
        "validate-local.ps1": ["http://127.0.0.1:8080/health", "SkipGameLaunch", "LaunchGame"],
        "package-release.ps1": ["Compress-Archive", "BalatroMCP"],
    }

    for script, expected_fragments in scripts.items():
        content = read_text(ROOT / "scripts" / script)
        for fragment in expected_fragments:
            assert fragment in content

    validate_script = read_text(ROOT / "scripts" / "validate-local.ps1")
    assert "balatro-mcp" in validate_script
    assert "BALATRO_MCP_PORT" in validate_script

    install_script = read_text(ROOT / "scripts" / "install-local.ps1")
    assert "BalatroAgent" in install_script
    assert "Removed legacy BalatroAgent" in install_script

    package_script = read_text(ROOT / "scripts" / "package-release.ps1")
    assert ".venv" in package_script
    assert "__pycache__" in package_script
