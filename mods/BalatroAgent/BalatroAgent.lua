local mod_path = SMODS and SMODS.current_mod and SMODS.current_mod.path or ""

local function load_agent_module(path)
    local full_path = mod_path .. path
    local source = assert(SMODS.NFS.read(full_path), "BalatroAgent failed to read " .. full_path)
    local loader = loadstring or load
    return assert(loader(source, "=[BalatroAgent \"" .. path .. "\"]"))()
end

BalatroAgent = BalatroAgent or {}
BalatroAgent.version = "0.1.0"
BalatroAgent.JSON = load_agent_module("balatro_agent/json.lua")
BalatroAgent.state = load_agent_module("balatro_agent/state.lua")
BalatroAgent.actions = load_agent_module("balatro_agent/actions.lua")
BalatroAgent.HttpServer = load_agent_module("balatro_agent/http_server.lua")
BalatroAgent.port = tonumber(os.getenv("BALATRO_AGENT_PORT") or "8080") or 8080
BalatroAgent.server = BalatroAgent.HttpServer.new(BalatroAgent, {
    host = "127.0.0.1",
    port = BalatroAgent.port,
})

function BalatroAgent.update(dt)
    if BalatroAgent.server and BalatroAgent.server.update then
        BalatroAgent.server:update(dt)
    end
end

local balatro_agent_game_update = Game.update
function Game:update(dt)
    balatro_agent_game_update(self, dt)
    if BalatroAgent and BalatroAgent.update then
        BalatroAgent.update(dt)
    end
end

if sendInfoMessage then
    sendInfoMessage("Balatro MCP loaded", "BalatroAgent")
end
