# Balatro Agent

Balatro Agent is a Steamodded Balatro mod plus MCP server inspired by the architecture of STS2-Agent.

The in-game mod exposes Balatro state and actions through a local HTTP API on `http://127.0.0.1:8080`. The Python package in `mcp_server/` wraps that API as MCP tools for AI clients.

## Current Tool Surface

- `GET /health`
- `GET /state`
- `GET /actions/available`
- `POST /action`

MCP tools:

- `health_check`
- `get_game_state`
- `get_raw_game_state`
- `get_available_actions`
- `act`
- `wait_until_actionable`

## Local Balatro Path

The validation scripts default to:

```powershell
D:\SteamLibrary\steamapps\common\Balatro
```

## Install

Install Lovely and Steamodded first. Then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1 -BalatroPath "D:\SteamLibrary\steamapps\common\Balatro"
```

## Start MCP

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-mcp-stdio.ps1
```

For network MCP:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-mcp-network.ps1
```

## Action Examples

The generic MCP `act` tool accepts the action name plus optional arguments:

```json
{"action": "start_run", "stake": 1}
{"action": "select_blind"}
{"action": "play_hand", "card_indices": [1, 2, 3, 4, 5]}
{"action": "discard", "card_indices": [6, 7]}
{"action": "buy", "area": "shop_jokers", "index": 1}
{"action": "use", "area": "consumeables", "index": 1, "card_indices": [1]}
```

## Validate

Static and MCP tests:

```powershell
pytest tests/test_lua_static.py -q
cd mcp_server
uv run pytest -q
```

Local structure validation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate-local.ps1 -SkipGameLaunch
```

In-game smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate-local.ps1 -LaunchGame
```
