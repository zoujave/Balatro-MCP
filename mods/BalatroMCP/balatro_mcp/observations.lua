local Observations = {}
local unpack_values = unpack or table.unpack
local function packed(...) return {n = select('#', ...), ...} end

local function emit(mcp, kind, fields)
    mcp.event_sequence = (mcp.event_sequence or 0) + 1
    local event = fields or {}
    event.id = mcp.instance_id .. ':' .. tostring(mcp.event_sequence)
    event.sequence = mcp.event_sequence
    event.kind = kind
    event.timestamp = os.time()
    event.run_id = mcp.run_id
    mcp.events[#mcp.events + 1] = event
    if #mcp.events > 256 then table.remove(mcp.events, 1) end
    return event
end

function Observations.initialize(mcp)
    mcp.instance_id = tostring(os.time()) .. '-' .. tostring({}):gsub('[^%w]', '')
    mcp.events, mcp.hands, mcp.hooks = {}, {}, {}
    mcp.control_mode = 'assist'
end

local function guarded(mcp, fn)
    local success, err = pcall(fn)
    if not success then mcp.observation_error = tostring(err) end
end

local function wrap(mcp, owner, key, before, after)
    local original = owner and owner[key]
    if type(original) ~= 'function' or mcp.hooks[key] then return end
    local wrapper = function(...)
        local args = packed(...)
        if before then guarded(mcp, function() before(unpack_values(args, 1, args.n)) end) end
        local results = packed(original(unpack_values(args, 1, args.n)))
        if after then guarded(mcp, function() after(results, unpack_values(args, 1, args.n)) end) end
        return unpack_values(results, 1, results.n)
    end
    owner[key], mcp.hooks[key] = wrapper, wrapper
end

local function capture_reference(mcp)
    local state = mcp.state.build_state(mcp)
    local reference = {}
    for _, key in ipairs({'run', 'blind', 'deck', 'jokers'}) do reference[key] = state[key] end
    reference.screen, reference.hand = 'SELECTING_HAND', {cards = {}, highlighted_indices = {}}
    for _, card in ipairs(G.play and G.play.cards or {}) do
        reference.hand.cards[#reference.hand.cards + 1] = mcp.state.card_payload(card, #reference.hand.cards + 1)
        reference.hand.highlighted_indices[#reference.hand.highlighted_indices + 1] = #reference.hand.cards
    end
    for _, card in ipairs(G.hand and G.hand.cards or {}) do
        reference.hand.cards[#reference.hand.cards + 1] = mcp.state.card_payload(card, #reference.hand.cards + 1)
    end
    return reference
end

function Observations.install(mcp)
    local funcs = G and G.FUNCS
    if not funcs then return end
    for _, key in ipairs({'play_cards_from_highlighted', 'discard_cards_from_highlighted', 'buy_from_shop',
                          'sell_card', 'use_card', 'reroll_shop', 'cash_out', 'select_blind', 'skip_blind'}) do
        wrap(mcp, funcs, key, function(event)
            local source = mcp.current_actor or 'human'
            local card = type(event) == 'table' and event.config and event.config.ref_table
            emit(mcp, 'ui_action', {action = key, source = source,
                 card_uid = type(card) == 'table' and card.sort_id and ('c' .. tostring(card.sort_id)) or nil,
                 request_id = mcp.current_request_id})
            if key == 'play_cards_from_highlighted' then
                mcp.pending_play_source = source
                mcp.pending_play_request = mcp.current_request_id
            end
        end)
    end
    wrap(mcp, funcs, 'evaluate_play', function()
        local reference = capture_reference(mcp)
        local event = emit(mcp, 'hand_started', {source = mcp.pending_play_source or 'human', request_id = mcp.pending_play_request})
        mcp.active_hand = {id = event.id, source = event.source, request_id = event.request_id,
                          run_id = mcp.run_id, round = G.GAME.round, ante = G.GAME.round_resets.ante,
                          reference_state = reference, played_indices = reference.hand.highlighted_indices,
                          trace = {}, complete = false}
        mcp.pending_play_source, mcp.pending_play_request = nil, nil
    end)
    wrap(mcp, _G, 'update_hand_text', function(config, values)
        local hand = mcp.active_hand
        if not hand or hand.complete or type(values) ~= 'table' then return end
        local entry = mcp.state.snapshot_value(values)
        if #hand.trace < 512 then hand.trace[#hand.trace + 1] = {phase = 'game_score_update', values = entry} end
        if type(values.chips) == 'number' and values.chips > 0 then hand.final_chips = values.chips end
        if type(values.mult) == 'number' and values.mult > 0 then hand.final_mult = values.mult end
        if values.handname and values.handname ~= '' then hand.display_name = values.handname end
    end)
    wrap(mcp, _G, 'check_and_set_high_score', nil, function(results, score, amount)
        if score ~= 'hand' or type(amount) ~= 'number' or not mcp.active_hand then return end
        local hand = mcp.active_hand
        if hand.complete then return end
        hand.score, hand.complete = math.floor(amount), true
        hand.hand_type = G.GAME.last_hand_played
        hand.completed_at = os.time()
        mcp.last_hand = hand
        mcp.hands[#mcp.hands + 1] = hand
        if #mcp.hands > 50 then table.remove(mcp.hands, 1) end
        emit(mcp, 'hand_scored', {hand_id = hand.id, score = hand.score, hand_type = hand.hand_type,
             source = hand.source, request_id = hand.request_id})
    end)
    if Card then
        wrap(mcp, Card, 'calculate_joker', nil, function(results, card, context)
            local hand = mcp.active_hand
            if not hand or hand.complete or type(results[1]) ~= 'table' or #hand.trace >= 512 then return end
            local phase = 'joker'
            for _, name in ipairs({'before', 'individual', 'repetition', 'joker_main', 'other_joker', 'after'}) do
                if context and context[name] then phase = name end
            end
            hand.trace[#hand.trace + 1] = {phase = phase, key = card.config and card.config.center and card.config.center.key,
                                         card_uid = card.sort_id and ('c' .. tostring(card.sort_id)),
                                         result = mcp.state.snapshot_value(results[1])}
        end)
    end
end

function Observations.payload(mcp)
    local hands = {}
    -- Keep scores from hands played between polls without resending fifty full traces.
    for _, hand in ipairs(mcp.hands or {}) do
        hands[#hands + 1] = {id = hand.id, score = hand.score, complete = hand.complete,
             source = hand.source, request_id = hand.request_id, run_id = hand.run_id,
             round = hand.round, ante = hand.ante, hand_type = hand.hand_type, completed_at = hand.completed_at}
    end
    return {last_hand = mcp.last_hand, hands = hands, events = mcp.events or {}, sequence = mcp.event_sequence or 0,
            error = mcp.observation_error, hand_count = #(mcp.hands or {})}
end

return Observations
