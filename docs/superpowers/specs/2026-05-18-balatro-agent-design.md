# Balatro Agent Design

## Goal

Build a Balatro equivalent of STS2-Agent: an in-game mod exposes live game state and safe game actions over a localhost HTTP API, and a Python MCP server wraps that API for MCP-capable AI clients.

## References Checked

- CharTyr/STS2-Agent exposes a game mod HTTP API plus an MCP server with `health_check`, `get_game_state`, `get_available_actions`, and `act`-style tools.
- Steamodded/smods is a Balatro Lua mod loader. Its loader accepts JSON mod metadata with `id`, `name`, `main_file`, `prefix`, `version`, and dependency fields.
- Steamodded loads LuaSocket in its preflight logging module, so a Balatro mod can host a non-blocking local TCP HTTP server without an external file bridge.
- The local Balatro executable is a LÖVE zip package. The inspected source shows actions such as `G.FUNCS.start_run`, `select_blind`, `play_cards_from_highlighted`, `discard_cards_from_highlighted`, `buy_from_shop`, `use_card`, `reroll_shop`, `cash_out`, and `skip_booster`.

## Scope

The first version should be a playable automation surface, not a full training platform. It will support:

- Local HTTP API on `127.0.0.1:8080`.
- MCP stdio server and optional network MCP server.
- Live state snapshots for menu, blind select, hand play, round evaluation, shop, booster packs, jokers, consumables, and run economy.
- Legal-action descriptors that tell agents which action names and arguments are currently valid.
- Atomic game actions for starting a run, selecting or skipping blinds, selecting hand cards, playing, discarding, cashing out, ending shop, rerolling shop, buying/opening/using/selling cards, choosing or skipping booster cards, sorting hand, and returning to menu.
- Installation and validation scripts for the local Windows Balatro install.

Out of scope for this pass:

- AlphaZero-specific data exports.
- Full SSE event streaming.
- Perfect strategy or poker evaluation outside the game.
- Cross-platform installer automation beyond documented script structure.

## Architecture

`mods/BalatroAgent/` is the Steamodded mod. `BalatroAgent.lua` loads small focused modules:

- `json.lua`: safe JSON encode/decode wrapper around Balatro/Steamodded JSON globals with a fallback encoder.
- `state.lua`: converts `G` into stable JSON-friendly state and action descriptors.
- `actions.lua`: validates action requests, touches Balatro UI/game objects, and returns the post-action state.
- `http_server.lua`: polls a non-blocking LuaSocket listener from `Game:update`, routes HTTP requests, and returns STS2-style envelopes.

`mcp_server/` is a Python package:

- `client.py`: minimal HTTP client with STS2-style error handling.
- `server.py`: FastMCP stdio tools.
- `network_server.py`: optional HTTP MCP app.

`scripts/` contains Windows helpers for install, startup, validation, and release packaging.

## API Shape

All successful HTTP responses use:

```json
{"ok": true, "data": {...}}
```

Errors use:

```json
{"ok": false, "error": {"code": "invalid_action", "message": "...", "details": {...}, "retryable": false}}
```

Endpoints:

- `GET /health`
- `GET /state`
- `GET /actions/available`
- `POST /action`

The MCP server exposes:

- `health_check`
- `get_game_state`
- `get_raw_game_state`
- `get_available_actions`
- `act`
- `wait_until_actionable`

## Testing

Tests are split by layer:

- Python unit tests run against a local fake Balatro HTTP API.
- Static Lua checks verify module structure, metadata, and dangerous blocking patterns.
- Packaging validation verifies the Steamodded mod folder layout.
- Local smoke validation installs the mod to `%AppData%/Balatro/Mods/BalatroAgent`, verifies/installs Steamodded prerequisites when possible, launches Balatro, and probes `http://127.0.0.1:8080/health`.

## Risks

- Balatro UI functions are asynchronous. The mod will return the immediate post-action state and the MCP server will provide `wait_until_actionable`.
- Some UI callbacks require UI element context. For those, actions will either build the minimal compatible `e` table or reimplement the same narrow game-state transition.
- Lovely may be blocked by antivirus. The installer will report this clearly instead of silently masking it.
