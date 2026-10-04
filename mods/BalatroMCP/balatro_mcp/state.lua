local State = {}

local PACK_STATES = {}

local function safe_call(fn, fallback)
    local ok, result = pcall(fn)
    if ok then
        return result
    end
    return fallback
end

local function reverse_lookup(table_value, needle)
    if type(table_value) ~= "table" then
        return "UNKNOWN"
    end
    for key, value in pairs(table_value) do
        if value == needle then
            return key
        end
    end
    return "UNKNOWN"
end

local function state_name()
    return reverse_lookup(G and G.STATES, G and G.STATE)
end

local function stage_name()
    return reverse_lookup(G and G.STAGES, G and G.STAGE)
end

local function is_pack_state(name)
    PACK_STATES = {
        TAROT_PACK = true,
        PLANET_PACK = true,
        SPECTRAL_PACK = true,
        SMODS_BOOSTER_OPENED = true,
        STANDARD_PACK = true,
        BUFFOON_PACK = true,
    }
    return PACK_STATES[name] == true
end

local function current_time()
    if love and love.timer and love.timer.getTime then
        return love.timer.getTime()
    end
    return os.clock()
end

local function action_lock_active(mcp)
    if not mcp then
        return false
    end

    local lock_until = tonumber(mcp.action_lock_until)
    if lock_until and current_time() < lock_until then
        return true
    end

    mcp.action_lock_until = nil
    mcp.pending_action = nil
    return false
end

local function primitive_table(value, depth)
    depth = depth or 0
    if type(value) ~= "table" then
        return value
    end
    if value.sort_id and value.config and value.config.center then
        return {uid = 'c' .. tostring(value.sort_id), key = value.config.center.key}
    end

    local result = {}
    for key, item in pairs(value) do
        local item_type = type(item)
        if item_type == "string" or item_type == "number" or item_type == "boolean" then
            result[key] = item
        elseif item_type == "table" and depth < 3 then
            result[key] = primitive_table(item, depth + 1)
        end
    end
    return result
end

local function edition_name(card)
    if not card or type(card.edition) ~= "table" then
        return nil
    end
    for key, value in pairs(card.edition) do
        if value == true and key ~= "type" then
            return key
        end
    end
    return card.edition.type
end

local function center_key(card)
    if not card or not card.config then
        return nil
    end
    if card.config.center and card.config.center.key then
        return card.config.center.key
    end
    return card.config.card_key
end

local function center_name(card)
    if not card or not card.config or not card.config.center then
        return nil
    end
    return card.config.center.name or card.config.center.key
end

local function card_payload(card, index)
    if not card then
        return nil
    end

    local ability = card.ability or {}
    local base = card.base or {}
    local config = card.config or {}

    return {
        index = index,
        uid = card.sort_id and ('c' .. tostring(card.sort_id)),
        sort_id = card.sort_id,
        key = center_key(card),
        name = center_name(card),
        rarity = config.center and config.center.rarity,
        blueprint_compat = config.center and config.center.blueprint_compat,
        pinned = card.pinned and true or false,
        set = ability.set or (config.center and config.center.set),
        suit = base.suit,
        rank = base.value,
        id = base.id,
        nominal = base.nominal,
        cost = card.cost,
        sell_cost = card.sell_cost,
        highlighted = card.highlighted and true or false,
        debuffed = card.debuff and true or false,
        seal = card.seal,
        edition = edition_name(card),
        ability = primitive_table(ability),
        facing = card.facing,
    }
end

local function area_cards(area)
    local cards = {}
    if not area or type(area.cards) ~= "table" then
        return cards
    end

    for index, card in ipairs(area.cards) do
        cards[#cards + 1] = card_payload(card, index)
    end
    return cards
end

local function highlighted_indices(area)
    local indices = {}
    if not area or type(area.highlighted) ~= "table" or type(area.cards) ~= "table" then
        return indices
    end

    for _, highlighted in ipairs(area.highlighted) do
        for index, card in ipairs(area.cards) do
            if card == highlighted then
                indices[#indices + 1] = index
                break
            end
        end
    end
    return indices
end

local function add_action(actions, name, description, args)
    actions[#actions + 1] = {
        name = name,
        description = description,
        args = args or {},
    }
end

local function round_eval_ready()
    if not (G and G.round_eval and G.GAME and G.GAME.current_round and
        type(G.GAME.current_round.dollars) == "number") then
        return false
    end
    for _, box in ipairs(G.I and G.I.UIBOX or {}) do
        if type(box.get_UIE_by_ID) == "function" then
            local button = box:get_UIE_by_ID("cash_out_button")
            if button and button.config and button.config.button == "cash_out" then
                return true
            end
        end
    end
    return false
end

function State.can_reroll_boss()
    local game = G and G.GAME
    if not game or state_name() ~= "BLIND_SELECT" then
        return false
    end
    local vouchers = game.used_vouchers or {}
    local resets = game.round_resets or {}
    local affordable = (game.dollars or 0) - (game.bankrupt_at or 0) >= 10
    local allowed = vouchers.v_retcon or
        (vouchers.v_directors_cut and not resets.boss_rerolled)
    return affordable and allowed and true or false
end

local function build_actions(screen, busy)
    local actions = {}
    if busy then
        return actions, {}
    end

    local blind_ui_ready = G and G.blind_select and G.blind_prompt_box
    local can_cash_out = round_eval_ready()

    if screen == "MENU" then
        add_action(actions, "start_run", "Start a new Balatro run.", {
            { name = "stake", type = "number", required = false },
            { name = "seed", type = "string", required = false },
        })
    end

    if screen == "BLIND_SELECT" and blind_ui_ready then
        add_action(actions, "reorder_cards", "Reorder jokers by stable card uid.", {
            {name = "area", type = "string", required = true},
            {name = "card_uids", type = "array", required = true},
        })
        add_action(actions, "select_blind", "Select the current blind on deck.", {
            { name = "blind", type = "string", required = false },
        })
        add_action(actions, "skip_blind", "Skip the current blind and receive its tag.")
        if State.can_reroll_boss() then
            add_action(actions, "reroll_boss", "Reroll the boss blind when vouchers allow it.")
        end
    end

    if screen == "SELECTING_HAND" then
        add_action(actions, "reorder_cards", "Reorder hand or joker cards by stable card uid.", {
            {name = "area", type = "string", required = true},
            {name = "card_uids", type = "array", required = true},
        })
        add_action(actions, "select_cards", "Highlight cards in hand.", {
            { name = "card_indices", type = "array", required = true },
        })
        add_action(actions, "play_hand", "Play highlighted cards or the supplied hand card indices.", {
            { name = "card_indices", type = "array", required = false },
        })
        if G and G.GAME and G.GAME.current_round and (G.GAME.current_round.discards_left or 0) > 0 then
            add_action(actions, "discard", "Discard highlighted cards or the supplied hand card indices.", {
                { name = "card_indices", type = "array", required = false },
            })
        end
        add_action(actions, "sort_hand", "Sort hand by value or suit.", {
            { name = "mode", type = "string", required = false },
        })
    end

    if screen == "ROUND_EVAL" and can_cash_out then
        add_action(actions, "cash_out", "Collect round rewards and enter the shop.")
    end

    if screen == "SHOP" then
        add_action(actions, "reorder_cards", "Reorder jokers by stable card uid.", {
            {name = "area", type = "string", required = true},
            {name = "card_uids", type = "array", required = true},
        })
        add_action(actions, "end_shop", "Leave the shop and return to blind select.")
        add_action(actions, "reroll_shop", "Reroll shop cards if affordable.")
        add_action(actions, "buy", "Buy or redeem a shop card.", {
            { name = "area", type = "string", required = true },
            { name = "index", type = "number", required = true },
        })
    end

    if is_pack_state(screen) then
        add_action(actions, "use", "Choose a card from the open booster pack.", {
            { name = "area", type = "string", required = false },
            { name = "index", type = "number", required = true },
        })
        add_action(actions, "skip_booster", "Skip the current booster pack.")
    end

    if G and G.consumeables and G.consumeables.cards and #G.consumeables.cards > 0 then
        add_action(actions, "use", "Use a consumable card.", {
            { name = "area", type = "string", required = false },
            { name = "index", type = "number", required = true },
            { name = "card_indices", type = "array", required = false },
        })
        add_action(actions, "sell", "Sell a consumable card.", {
            { name = "area", type = "string", required = false },
            { name = "index", type = "number", required = true },
        })
    end

    if G and G.jokers and G.jokers.cards and #G.jokers.cards > 0 then
        add_action(actions, "sell", "Sell a joker.", {
            { name = "area", type = "string", required = false },
            { name = "index", type = "number", required = true },
        })
    end

    if screen == "GAME_OVER" then
        add_action(actions, "return_to_menu", "Return to the main menu.")
    end

    local names = {}
    local seen = {}
    for _, action in ipairs(actions) do
        if not seen[action.name] then
            names[#names + 1] = action.name
            seen[action.name] = true
        end
    end

    return actions, names
end

local function build_blind()
    local game = G and G.GAME or {}
    local blind = game.blind or {}
    local round_resets = game.round_resets or {}
    local choices = {}

    if type(round_resets.blind_choices) == "table" then
        for key, value in pairs(round_resets.blind_choices) do
            choices[#choices + 1] = {
                key = key,
                name = type(value) == "table" and (value.name or value.key) or tostring(value),
                state = round_resets.blind_states and round_resets.blind_states[key],
                tag = round_resets.blind_tags and round_resets.blind_tags[key],
            }
        end
    end

    return {
        on_deck = game.blind_on_deck,
        name = blind.name,
        key = blind.config and blind.config.blind and blind.config.blind.key,
        chips = blind.chips,
        chip_text = blind.chip_text,
        disabled = blind.disabled and true or false,
        choices = choices,
    }
end

local function build_round_scores(scores)
    local result = {}
    if type(scores) ~= "table" then
        return result
    end

    for key, value in pairs(scores) do
        if type(value) == "table" then
            result[key] = primitive_table(value)
        elseif type(value) == "string" or type(value) == "number" or type(value) == "boolean" then
            result[key] = value
        end
    end
    return result
end

local function build_run()
    local game = G and G.GAME or {}
    local round = game.current_round or {}
    local resets = game.round_resets or {}

    return {
        seed = game.pseudorandom and game.pseudorandom.seed,
        dollars = game.dollars,
        bankrupt_at = game.bankrupt_at,
        chips = game.chips,
        round_score = build_round_scores(game.round_scores),
        ante = resets.ante,
        blind_ante = resets.blind_ante,
        hands_left = round.hands_left,
        discards_left = round.discards_left,
        hands_played = round.hands_played,
        discards_used = round.discards_used,
        reroll_cost = round.reroll_cost,
        free_rerolls = round.free_rerolls,
        current_hand = primitive_table(round.current_hand or {}),
        hand_levels = primitive_table(game.hands or {}),
        round = game.round,
        round_payout = round.dollars,
        cash_out_ready = round_eval_ready(),
        starting_deck_size = game.starting_deck_size,
        probabilities = primitive_table(game.probabilities or {}),
        modifiers = primitive_table(game.modifiers or {}),
    }
end

local function build_shop()
    return {
        jokers = area_cards(G and G.shop_jokers),
        vouchers = area_cards(G and G.shop_vouchers),
        boosters = area_cards(G and G.shop_booster),
    }
end

local function build_pack()
    return {
        choices_left = G and G.GAME and G.GAME.pack_choices,
        size = G and G.GAME and G.GAME.pack_size,
        cards = area_cards(G and G.pack_cards),
    }
end

local function build_tags()
    local result = {}
    for _, tag in ipairs(G and G.GAME and G.GAME.tags or {}) do
        result[#result + 1] = { key = tag.key, name = tag.name, triggered = tag.triggered and true or false, config = primitive_table(tag.config or {}), ability = primitive_table(tag.ability or {}) }
    end
    return result
end

local function build_decks()
    local result = {}
    local pool = G and G.P_CENTER_POOLS and G.P_CENTER_POOLS.Back or {}
    for _, center in ipairs(pool) do
        if not center.omit and not center.wip and not center.demo then
            result[#result + 1] = {
                key = center.key,
                name = center.name,
                order = center.order,
                unlocked = center.unlocked and true or false,
                discovered = center.discovered and true or false,
                unlock_condition = primitive_table(center.unlock_condition or {}),
            }
        end
    end
    table.sort(result, function(a, b) return (a.order or 0) < (b.order or 0) end)
    return result
end

local function build_deck()
    local result = {cards = {}, by_suit = {}, by_rank = {}, by_enhancement = {}, by_seal = {}, by_edition = {},
                    total = #(G and G.playing_cards or {}),
                    starting_size = G and G.GAME and G.GAME.starting_deck_size or 52,
                    draw_count = #(G and G.deck and G.deck.cards or {}),
                    discard_count = #(G and G.discard and G.discard.cards or {})}
    local zones = {}
    for name, area in pairs({hand = G and G.hand, draw = G and G.deck, discard = G and G.discard, play = G and G.play}) do
        for _, card in ipairs(area.cards or {}) do zones[card] = name end
    end
    local function tally(target, key)
        key = tostring(key or 'none')
        target[key] = (target[key] or 0) + 1
    end
    for _, card in ipairs(G and G.playing_cards or {}) do
        local base = card.base or {}
        local entry = {uid = card.sort_id and ('c' .. tostring(card.sort_id)), suit = base.suit, rank = base.value,
                       id = base.id, key = center_key(card), seal = card.seal, edition = edition_name(card),
                       area = zones[card] or 'other', debuffed = card.debuff and true or false}
        result.cards[#result.cards + 1] = entry
        tally(result.by_suit, entry.suit)
        tally(result.by_rank, entry.rank)
        tally(result.by_enhancement, entry.key)
        tally(result.by_seal, entry.seal)
        tally(result.by_edition, entry.edition)
    end
    -- Composition is public information. Never expose hidden draw order.
    table.sort(result.cards, function(a, b) return tostring(a.uid or '') < tostring(b.uid or '') end)
    return result
end

local function stable_value(value)
    if type(value) == 'string' then return 's' .. tostring(#value) .. ':' .. value end
    if type(value) ~= 'table' then return type(value) .. ':' .. tostring(value) end
    local keys, parts = {}, {}
    for key in pairs(value) do keys[#keys + 1] = key end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, key in ipairs(keys) do parts[#parts + 1] = stable_value(key) .. '=' .. stable_value(value[key]) end
    return '{' .. table.concat(parts, '|') .. '}'
end

function State.build_state(mcp)
    local screen = state_name()
    local busy = action_lock_active(mcp)
    local actions, available_actions = build_actions(screen, busy)

    if mcp and mcp.game_identity ~= (G and G.GAME) then
        mcp.game_identity = G and G.GAME
        mcp.run_sequence = (mcp.run_sequence or 0) + 1
        mcp.run_id = (mcp.instance_id or 'local') .. ':run:' .. tostring(mcp.run_sequence)
        mcp.last_hand, mcp.active_hand = nil, nil
    end
    local result = {
        state_version = 2,
        mod_version = mcp and mcp.version or "0.0.0",
        timestamp = os.time(),
        screen = screen,
        stage = stage_name(),
        busy = busy,
        pending_action = busy and mcp and mcp.pending_action or nil,
        actionable = (not busy) and #available_actions > 0,
        available_actions = available_actions,
        actions = actions,
        session = {
            profile = G and G.SETTINGS and G.SETTINGS.profile,
            paused = G and G.SETTINGS and G.SETTINGS.paused and true or false,
            speed = G and G.SETTINGS and G.SETTINGS.GAMESPEED,
        },
        decks = build_decks(),
        deck = build_deck(),
        run_id = mcp and mcp.run_id,
        control = {mode = mcp and mcp.control_mode or 'assist'},
        capabilities = {deck_summary = true, scoring_observations = true, guarded_actions = true,
                        reorder_cards = true, shared_control = true},
        observations = mcp and mcp.observations and mcp.observations.payload(mcp) or {},
        tags = build_tags(),
        run = build_run(),
        blind = build_blind(),
        hand = {
            cards = area_cards(G and G.hand),
            highlighted_indices = highlighted_indices(G and G.hand),
        },
        jokers = {
            cards = area_cards(G and G.jokers),
            limit = G and G.jokers and G.jokers.config and G.jokers.config.card_limit,
        },
        consumeables = {
            cards = area_cards(G and G.consumeables),
            limit = G and G.consumeables and G.consumeables.config and G.consumeables.config.card_limit,
        },
        shop = build_shop(),
        pack = build_pack(),
    }
    if mcp then
        local observed = {}
        for _, key in ipairs({'screen', 'stage', 'session', 'run', 'blind', 'deck', 'hand', 'jokers', 'consumeables', 'shop', 'pack', 'tags', 'control'}) do
            observed[key] = result[key]
        end
        observed.event_sequence = result.observations.sequence
        local fingerprint = stable_value(observed)
        if mcp.state_fingerprint ~= fingerprint then
            mcp.state_fingerprint = fingerprint
            mcp.revision_sequence = (mcp.revision_sequence or 0) + 1
        end
        result.revision = (mcp.instance_id or 'local') .. ':' .. tostring(mcp.revision_sequence or 0)
    end
    return result
end

State.card_payload = card_payload
State.snapshot_value = primitive_table
State.fingerprint_value = stable_value
return State
