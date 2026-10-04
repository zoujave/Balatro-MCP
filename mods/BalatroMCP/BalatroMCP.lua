local mod_path = SMODS and SMODS.current_mod and SMODS.current_mod.path or ""

local function load_mcp_module(path)
    local full_path = mod_path .. path
    local source = assert(SMODS.NFS.read(full_path), "BalatroMCP failed to read " .. full_path)
    local loader = loadstring or load
    return assert(loader(source, "=[BalatroMCP \"" .. path .. "\"]"))()
end

BalatroMCP = BalatroMCP or {}
BalatroMCP.version = "0.2.0"
BalatroMCP.JSON = load_mcp_module("balatro_mcp/json.lua")
BalatroMCP.state = load_mcp_module("balatro_mcp/state.lua")
BalatroMCP.actions = load_mcp_module("balatro_mcp/actions.lua")
BalatroMCP.observations = load_mcp_module("balatro_mcp/observations.lua")
BalatroMCP.observations.initialize(BalatroMCP)
BalatroMCP.HttpServer = load_mcp_module("balatro_mcp/http_server.lua")
BalatroMCP.port = tonumber(os.getenv("BALATRO_MCP_PORT") or "8080") or 8080
BalatroMCP.server = BalatroMCP.HttpServer.new(BalatroMCP, {
    host = "127.0.0.1",
    port = BalatroMCP.port,
})

function BalatroMCP.update(dt)
    BalatroMCP.observations.install(BalatroMCP)
    if BalatroMCP.server and BalatroMCP.server.update then
        BalatroMCP.server:update(dt)
    end
end

local balatro_mcp_game_update = Game.update
function Game:update(dt)
    balatro_mcp_game_update(self, dt)
    if BalatroMCP and BalatroMCP.update then
        BalatroMCP.update(dt)
    end
end

if sendInfoMessage then
    sendInfoMessage("Balatro MCP loaded", "BalatroMCP")
end
