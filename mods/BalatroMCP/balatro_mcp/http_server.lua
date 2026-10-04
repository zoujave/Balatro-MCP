local socket = require("socket")

local HttpServer = {}
HttpServer.__index = HttpServer

local DEFAULT_HOST = "127.0.0.1"
local DEFAULT_PORT = 8080
local MAX_CLIENTS_PER_TICK = 8
local MAX_READS_PER_TICK = 16

local STATUS_TEXT = {
    [200] = "OK",
    [400] = "Bad Request",
    [404] = "Not Found",
    [405] = "Method Not Allowed",
    [409] = "Conflict",
    [500] = "Internal Server Error",
    [503] = "Service Unavailable",
}

local function now()
    if love and love.timer and love.timer.getTime then
        return love.timer.getTime()
    end
    return os.time()
end

local function lower(value)
    return string.lower(value or "")
end

local function trim(value)
    return (value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

local function split_path(path)
    local clean = path or "/"
    local question = clean:find("?", 1, true)
    if question then
        clean = clean:sub(1, question - 1)
    end
    if clean == "" then
        clean = "/"
    end
    return clean
end

local function envelope_ok(data)
    return {
        ok = true,
        data = data or {},
    }
end

local function envelope_error(code, message, details, retryable)
    return {
        ok = false,
        error = {
            code = code or "internal_error",
            message = message or "Request failed.",
            details = details,
            retryable = retryable and true or false,
        },
    }
end

local function parse_request(raw)
    local header_end = raw:find("\r\n\r\n", 1, true)
    if not header_end then
        return nil
    end

    local header_text = raw:sub(1, header_end - 1)
    local body_start = header_end + 4
    local lines = {}
    for line in (header_text .. "\r\n"):gmatch("(.-)\r\n") do
        lines[#lines + 1] = line
    end

    local method, path = (lines[1] or ""):match("^(%S+)%s+(%S+)%s+HTTP/%d%.%d$")
    if not method or not path then
        return nil, "invalid_request"
    end

    local headers = {}
    for i = 2, #lines do
        local key, value = lines[i]:match("^([^:]+):%s*(.*)$")
        if key then
            headers[lower(trim(key))] = trim(value)
        end
    end

    local content_length = tonumber(headers["content-length"] or "0") or 0
    local available = #raw - body_start + 1
    if available < content_length then
        return nil
    end

    local body = raw:sub(body_start, body_start + content_length - 1)
    return {
        method = method,
        path = split_path(path),
        headers = headers,
        body = body,
        consumed = body_start + content_length - 1,
    }
end

function HttpServer.new(mcp, options)
    options = options or {}
    local self = setmetatable({
        mcp = mcp,
        host = options.host or DEFAULT_HOST,
        port = options.port or DEFAULT_PORT,
        clients = {},
        started_at = now(),
        last_error = nil,
    }, HttpServer)

    local server, err = socket.bind(self.host, self.port)
    if not server then
        self.last_error = err or "socket_bind_failed"
        return self
    end

    server:settimeout(0)
    self.server = server
    return self
end

function HttpServer:close_client(client_state)
    if client_state and client_state.socket then
        pcall(function()
            client_state.socket:close()
        end)
    end
end

function HttpServer:write_response(client_state, status, payload)
    local body = self.mcp.JSON.encode(payload)
    local response = table.concat({
        "HTTP/1.1 " .. tostring(status) .. " " .. (STATUS_TEXT[status] or "OK"),
        "Content-Type: application/json; charset=utf-8",
        "Content-Length: " .. tostring(#body),
        "Connection: close",
        "Access-Control-Allow-Origin: *",
        "",
        body,
    }, "\r\n")
    client_state.response = response
    client_state.write_offset = 1
end

function HttpServer:flush_response(client_state)
    local remaining = client_state.response:sub(client_state.write_offset)
    local sent, err, partial = client_state.socket:send(remaining)
    client_state.write_offset = client_state.write_offset + (sent or partial or 0)
    return client_state.write_offset > #client_state.response or (err and err ~= 'timeout') and true or false
end

function HttpServer:health_payload()
    return {
        service = "balatro-mcp",
        version = self.mcp.version or "0.0.0",
        host = self.host,
        port = self.port,
        uptime_seconds = math.max(0, now() - self.started_at),
        state_available = self.mcp.state ~= nil,
        actions_available = self.mcp.actions ~= nil,
        last_error = self.last_error,
    }
end

function HttpServer:state_payload()
    if self.mcp.state and self.mcp.state.build_state then
        return self.mcp.state.build_state(self.mcp)
    end

    return {
        state_version = 1,
        screen = "UNKNOWN",
        available_actions = {},
        actions = {},
        message = "State module is not loaded yet.",
    }
end

function HttpServer:available_actions_payload()
    local state = self:state_payload()
    return {
        actions = state.actions or {},
        available_actions = state.available_actions or {},
    }
end

function HttpServer:action_payload(request)
    if not self.mcp.actions or not self.mcp.actions.execute then
        return 503, envelope_error("actions_unavailable", "Action module is not loaded yet.", nil, true)
    end

    local body = {}
    if request.body and request.body ~= "" then
        body = self.mcp.JSON.decode(request.body)
    end

    local result, action_error = self.mcp.actions.execute(self.mcp, body or {})
    if not result and action_error then
        return action_error.status or 409, envelope_error(
            action_error.code,
            action_error.message,
            action_error.details,
            action_error.retryable
        )
    end

    return 200, envelope_ok(result)
end

function HttpServer:handle_request(request)
    local route = request.method .. " " .. request.path

    -- GET /health
    if route == "GET /health" then
        return 200, envelope_ok(self:health_payload())
    end

    -- GET /state
    if route == "GET /state" then
        return 200, envelope_ok(self:state_payload())
    end

    -- GET /actions/available
    if route == "GET /actions/available" then
        return 200, envelope_ok(self:available_actions_payload())
    end

    -- POST /action
    if route == "POST /action" then
        return self:action_payload(request)
    end

    if request.path == "/health" or request.path == "/state" or
        request.path == "/actions/available" or request.path == "/action" then
        return 405, envelope_error("method_not_allowed", "HTTP method is not allowed for this route.")
    end

    return 404, envelope_error("not_found", "Unknown route.", { path = request.path })
end

function HttpServer:handle_client(client_state)
    if client_state.response then return self:flush_response(client_state) end
    local request, parse_error = parse_request(client_state.buffer)
    if parse_error then
        self:write_response(client_state, 400, envelope_error(parse_error, "Malformed HTTP request."))
        return self:flush_response(client_state)
    end
    if not request then
        return false
    end

    local ok, status, payload = pcall(function()
        local response_status, response_payload = self:handle_request(request)
        return response_status, response_payload
    end)

    if ok then
        self:write_response(client_state, status, payload)
    else
        self.last_error = tostring(status)
        self:write_response(client_state, 500, envelope_error("internal_error", tostring(status), nil, true))
    end

    return self:flush_response(client_state)
end

function HttpServer:accept_clients()
    if not self.server then
        return
    end

    for _ = 1, MAX_CLIENTS_PER_TICK do
        local client = self.server:accept()
        if not client then
            return
        end

        client:settimeout(0)
        self.clients[#self.clients + 1] = {
            socket = client,
            buffer = "",
            accepted_at = now(),
        }
    end
end

function HttpServer:read_clients()
    for index = #self.clients, 1, -1 do
        local client_state = self.clients[index]
        for _ = 1, MAX_READS_PER_TICK do
            local data, err, partial = client_state.socket:receive("*a")
            local chunk = data or partial
            if chunk and chunk ~= "" then
                client_state.buffer = client_state.buffer .. chunk
            end
            if err == "timeout" then
                break
            end
            if err == "closed" then
                break
            end
            if not err then
                break
            end
        end

        local done = false
        if client_state.buffer ~= "" then
            done = self:handle_client(client_state)
        end

        if done or now() - client_state.accepted_at > 5 then
            self:close_client(client_state)
            table.remove(self.clients, index)
        end
    end
end

function HttpServer:update()
    self:accept_clients()
    self:read_clients()
end

return HttpServer
