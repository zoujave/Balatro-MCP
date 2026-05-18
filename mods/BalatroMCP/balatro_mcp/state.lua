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
        STANDARD_PACK = true,
        BUFFOON_PACK = true,
    }
    return PACK_STATES[name] == true
end

local function primitive_table(value)
    if type(value) ~= "table" then
        return value
    end

    local result = {}
    for key, item in pairs(value) do
        local item_type = type(item)
        if item_type == "string" or item_type == "number" or item_type == "boolean" then
            result[key] = item
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
        sort_id = card.sort_id,
        key = center_key(card),
        name = center_name(card),
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

local function build_actions(screen)
    local actions = {}
    local blind_ui_ready = G and G.blind_select and G.blind_prompt_box

    if screen == "MENU" then
        add_action(actions, "start_run", "Start a new Balatro run.", {
            { name = "stake", type = "number", required = false },
            { name = "seed", type = "string", required = false },
        })
    end

    if screen == "BLIND_SELECT" and blind_ui_ready then
        add_action(actions, "select_blind", "Select the current blind on deck.", {
            { name = "blind", type = "string", required = false },
        })
        add_action(actions, "skip_blind", "Skip the current blind and receive its tag.")
        if G and G.GAME and G.GAME.blind_on_deck == "Boss" then
            add_action(actions, "reroll_boss", "Reroll the boss blind when vouchers allow it.")
        end
    end

    if screen == "SELECTING_HAND" then
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

    if screen == "ROUND_EVAL" then
        add_action(actions, "cash_out", "Collect round rewards and enter the shop.")
    end

    if screen == "SHOP" then
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

function State.build_state(mcp)
    local screen = state_name()
    local actions, available_actions = build_actions(screen)

    return {
        state_version = 1,
        mod_version = mcp and mcp.version or "0.0.0",
        timestamp = now and now() or os.time(),
        screen = screen,
        stage = stage_name(),
        actionable = #available_actions > 0,
        available_actions = available_actions,
        actions = actions,
        session = {
            profile = G and G.SETTINGS and G.SETTINGS.profile,
            paused = G and G.SETTINGS and G.SETTINGS.paused and true or false,
            speed = G and G.SETTINGS and G.SETTINGS.GAMESPEED,
        },
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
end

return State
