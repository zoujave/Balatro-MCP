# Balatro Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Steamodded Balatro mod plus MCP server that exposes live Balatro state and legal actions to AI clients.

**Architecture:** The Lua mod hosts a non-blocking localhost HTTP API inside Balatro using LuaSocket. A Python FastMCP package wraps that HTTP API with STS2-Agent-style MCP tools and validation scripts install/test the local Windows game integration.

**Tech Stack:** Balatro, Lovely, Steamodded/smods, Lua 5.1/LuaSocket, Python 3.11+, FastMCP, pytest, PowerShell, git/GitHub CLI.

---

### Task 1: Repository Skeleton and Tests

**Files:**
- Create: `README.md`
- Create: `mods/BalatroAgent/BalatroAgent.json`
- Create: `mods/BalatroAgent/BalatroAgent.lua`
- Create: `mods/BalatroAgent/balatro_agent/json.lua`
- Create: `tests/test_lua_static.py`
- Create: `mcp_server/pyproject.toml`
- Create: `mcp_server/src/balatro_agent_mcp/__init__.py`
- Create: `mcp_server/tests/test_client.py`

- [ ] **Step 1: Write failing static tests**

Create tests that assert the Steamodded manifest exists, points to `BalatroAgent.lua`, and the Lua entrypoint wires `Game:update`.

- [ ] **Step 2: Run static tests and confirm they fail**

Run: `pytest tests/test_lua_static.py -q`

Expected: FAIL because the mod files do not exist yet.

- [ ] **Step 3: Add minimal manifest and entrypoint**

Create the Steamodded JSON metadata and a Lua entrypoint that initializes `BalatroAgent`, loads modules, and wraps `Game:update`.

- [ ] **Step 4: Run static tests and confirm they pass**

Run: `pytest tests/test_lua_static.py -q`

Expected: PASS.

### Task 2: Lua HTTP API

**Files:**
- Create: `mods/BalatroAgent/balatro_agent/http_server.lua`
- Modify: `mods/BalatroAgent/BalatroAgent.lua`
- Modify: `tests/test_lua_static.py`

- [ ] **Step 1: Add failing static tests for HTTP routes**

Assert the HTTP module binds `127.0.0.1`, default port `8080`, supports `GET /health`, `GET /state`, `GET /actions/available`, and `POST /action`, and uses non-blocking socket timeouts.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_lua_static.py -q`

Expected: FAIL because `http_server.lua` is missing.

- [ ] **Step 3: Implement non-blocking LuaSocket server**

Add request parsing, JSON envelopes, route dispatch, and safe error responses.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_lua_static.py -q`

Expected: PASS.

### Task 3: State Extraction and Actions

**Files:**
- Create: `mods/BalatroAgent/balatro_agent/state.lua`
- Create: `mods/BalatroAgent/balatro_agent/actions.lua`
- Modify: `mods/BalatroAgent/BalatroAgent.lua`
- Modify: `tests/test_lua_static.py`

- [ ] **Step 1: Add failing static tests for state/action surface**

Assert the mod exposes state builders and action handlers for `start_run`, `select_blind`, `skip_blind`, `play_hand`, `discard`, `cash_out`, `end_shop`, `reroll_shop`, `buy`, `use`, `sell`, `skip_booster`, and `sort_hand`.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_lua_static.py -q`

Expected: FAIL because state/action modules are missing.

- [ ] **Step 3: Implement state and action modules**

Build JSON-safe state snapshots and guarded action execution that returns updated state.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `pytest tests/test_lua_static.py -q`

Expected: PASS.

### Task 4: MCP Server

**Files:**
- Create: `mcp_server/src/balatro_agent_mcp/client.py`
- Create: `mcp_server/src/balatro_agent_mcp/server.py`
- Create: `mcp_server/src/balatro_agent_mcp/network_server.py`
- Create: `mcp_server/tests/test_client.py`
- Create: `mcp_server/tests/test_server.py`

- [ ] **Step 1: Write failing Python tests**

Test client success/error handling, available actions parsing, `act`, and `wait_until_actionable` using a fake local HTTP server.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `cd mcp_server; uv run pytest -q`

Expected: FAIL because Python package code is missing.

- [ ] **Step 3: Implement client and MCP tools**

Add FastMCP tools matching the spec and environment variables `BALATRO_AGENT_API_BASE_URL`, `BALATRO_AGENT_MCP_TOOL_PROFILE`, and network server options.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `cd mcp_server; uv run pytest -q`

Expected: PASS.

### Task 5: Scripts, Docs, and Local Validation

**Files:**
- Create: `scripts/install-local.ps1`
- Create: `scripts/start-mcp-stdio.ps1`
- Create: `scripts/start-mcp-network.ps1`
- Create: `scripts/validate-local.ps1`
- Create: `scripts/package-release.ps1`
- Modify: `README.md`

- [ ] **Step 1: Add failing script validation**

Extend tests to assert scripts exist and mention the local Balatro path `D:\SteamLibrary\steamapps\common\Balatro` where appropriate.

- [ ] **Step 2: Run tests and confirm they fail**

Run: `pytest tests/test_lua_static.py -q`

Expected: FAIL because scripts are missing.

- [ ] **Step 3: Implement scripts and README**

Add install, MCP startup, validation, and release-package scripts plus usage docs.

- [ ] **Step 4: Run automated validation**

Run:

```powershell
pytest tests/test_lua_static.py -q
cd mcp_server; uv run pytest -q
powershell -ExecutionPolicy Bypass -File ..\scripts\validate-local.ps1 -SkipGameLaunch
```

Expected: all pass.

### Task 6: In-Game Smoke Test, Commit, Remote Push

**Files:**
- No new source files unless smoke test reveals a defect.

- [ ] **Step 1: Install locally**

Run: `powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1 -BalatroPath "D:\SteamLibrary\steamapps\common\Balatro"`

Expected: `BalatroAgent` is copied to `%AppData%\Balatro\Mods\BalatroAgent`.

- [ ] **Step 2: Launch Balatro and probe health**

Run: `powershell -ExecutionPolicy Bypass -File scripts\validate-local.ps1 -LaunchGame`

Expected: `GET http://127.0.0.1:8080/health` returns `ok=true`.

- [ ] **Step 3: Commit**

Run:

```powershell
git status -sb
git add .
git commit -m "feat: build Balatro agent mod"
```

- [ ] **Step 4: Create and push remote**

Run:

```powershell
gh repo create Balatro-Agent --private --source . --remote origin --push
```

If the repository already exists, add it as `origin` and push `main`.

- [ ] **Step 5: Final verification**

Run:

```powershell
git status -sb
git remote -v
```

Expected: clean worktree, `origin` points at `Balatro-Agent`.
