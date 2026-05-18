local Json = {}

local function is_array(value)
    if type(value) ~= "table" then
        return false
    end

    local max_index = 0
    local count = 0
    for key, _ in pairs(value) do
        if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
            return false
        end
        if key > max_index then
            max_index = key
        end
        count = count + 1
    end
    return max_index == count
end

local escape_map = {
    ['"'] = '\\"',
    ["\\"] = "\\\\",
    ["\b"] = "\\b",
    ["\f"] = "\\f",
    ["\n"] = "\\n",
    ["\r"] = "\\r",
    ["\t"] = "\\t",
}

local function encode_string(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(char)
        return escape_map[char] or string.format("\\u%04x", string.byte(char))
    end) .. '"'
end

local function encode_value(value, seen)
    local value_type = type(value)
    if value_type == "nil" then
        return "null"
    elseif value_type == "boolean" then
        return value and "true" or "false"
    elseif value_type == "number" then
        if value ~= value or value == math.huge or value == -math.huge then
            return "null"
        end
        return tostring(value)
    elseif value_type == "string" then
        return encode_string(value)
    elseif value_type ~= "table" then
        return encode_string(tostring(value))
    end

    if seen[value] then
        error("cannot JSON encode cyclic table")
    end
    seen[value] = true

    local parts = {}
    if is_array(value) then
        for i = 1, #value do
            parts[#parts + 1] = encode_value(value[i], seen)
        end
        seen[value] = nil
        return "[" .. table.concat(parts, ",") .. "]"
    end

    for key, item in pairs(value) do
        if type(key) == "string" then
            parts[#parts + 1] = encode_string(key) .. ":" .. encode_value(item, seen)
        end
    end
    seen[value] = nil
    return "{" .. table.concat(parts, ",") .. "}"
end

function Json.encode(value)
    if JSON and JSON.encode then
        return JSON.encode(value)
    end
    return encode_value(value, {})
end

function Json.decode(value)
    if JSON and JSON.decode then
        return JSON.decode(value)
    end
    error("JSON.decode is unavailable in this Balatro environment")
end

return Json
