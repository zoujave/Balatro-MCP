from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOD_DIR = ROOT / "mods" / "BalatroAgent"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_steamodded_manifest_points_to_entrypoint() -> None:
    manifest_path = MOD_DIR / "BalatroAgent.json"

    manifest = json.loads(read_text(manifest_path))

    assert manifest["id"] == "BalatroAgent"
    assert manifest["name"] == "Balatro Agent"
    assert manifest["main_file"] == "BalatroAgent.lua"
    assert manifest["prefix"] == "ba"
    assert "Steamodded" in manifest["dependencies"]


def test_lua_entrypoint_wraps_game_update() -> None:
    entrypoint = read_text(MOD_DIR / "BalatroAgent.lua")

    assert "BalatroAgent" in entrypoint
    assert "Game.update" in entrypoint
    assert "BalatroAgent.update" in entrypoint
    assert "balatro_agent/json.lua" in entrypoint
    assert "BALATRO_AGENT_PORT" in entrypoint


def test_http_server_uses_nonblocking_local_routes() -> None:
    http_server = read_text(MOD_DIR / "balatro_agent" / "http_server.lua")

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
    state_module = read_text(MOD_DIR / "balatro_agent" / "state.lua")

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
    action_module = read_text(MOD_DIR / "balatro_agent" / "actions.lua")

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


def test_windows_scripts_cover_install_start_validate_and_package() -> None:
    scripts = {
        "install-local.ps1": [
            "D:\\SteamLibrary\\steamapps\\common\\Balatro",
            "AppData",
            "BalatroAgent",
            "Mods",
        ],
        "start-mcp-stdio.ps1": ["uv run balatro-agent-mcp-server"],
        "start-mcp-network.ps1": ["uv run balatro-agent-network-mcp-server"],
        "validate-local.ps1": ["http://127.0.0.1:8080/health", "SkipGameLaunch", "LaunchGame"],
        "package-release.ps1": ["Compress-Archive", "BalatroAgent"],
    }

    for script, expected_fragments in scripts.items():
        content = read_text(ROOT / "scripts" / script)
        for fragment in expected_fragments:
            assert fragment in content

    validate_script = read_text(ROOT / "scripts" / "validate-local.ps1")
    assert "balatro-agent" in validate_script
    assert "BALATRO_AGENT_PORT" in validate_script

    package_script = read_text(ROOT / "scripts" / "package-release.ps1")
    assert ".venv" in package_script
    assert "__pycache__" in package_script
