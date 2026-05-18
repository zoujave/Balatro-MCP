local Actions = {}

local function fail(code, message, details, status)
    return nil, {
        code = code or "invalid_action",
        message = message or "Action is not available.",
        details = details,
        status = status or 409,
    }
end

local function state_name()
    if not G or not G.STATES then
        return "UNKNOWN"
    end
    for key, value in pairs(G.STATES) do
        if value == G.STATE then
            return key
        end
    end
    return "UNKNOWN"
end

local function current_state(mcp)
    if mcp and mcp.state and mcp.state.build_state then
        return mcp.state.build_state(mcp)
    end
    return {}
end

local function ok(mcp, action, message)
    return {
        action = action,
        message = message or "Action queued.",
        state = current_state(mcp),
    }
end

local function get_index(request)
    return tonumber(request.index or request.option_index or request.card_index)
end

local function get_area(area_name)
    local normalized = area_name or "consumeables"
    local areas = {
        hand = G and G.hand,
        jokers = G and G.jokers,
        consumeables = G and G.consumeables,
        consumables = G and G.consumeables,
        pack = G and G.pack_cards,
        pack_cards = G and G.pack_cards,
        shop_jokers = G and G.shop_jokers,
        shop_vouchers = G and G.shop_vouchers,
        shop_booster = G and G.shop_booster,
        shop_boosters = G and G.shop_booster,
    }
    return areas[normalized], normalized
end

local function get_card_from_area(area_name, index)
    local area, normalized = get_area(area_name)
    if not area or not area.cards then
        return fail("area_unavailable", "Card area is not available.", { area = normalized }, 503)
    end

    local numeric_index = tonumber(index)
    if not numeric_index or numeric_index < 1 or numeric_index > #area.cards then
        return fail("invalid_index", "Card index is out of range.", {
            area = normalized,
            index = index,
            count = #area.cards,
        })
    end

    return area.cards[numeric_index], nil, area
end

local function normalize_indices(request)
    local indices = request.card_indices or request.indices or request.cards
    if not indices and request.card_index then
        indices = { request.card_index }
    end

    if type(indices) ~= "table" then
        return nil
    end

    local result = {}
    for _, value in ipairs(indices) do
        result[#result + 1] = tonumber(value)
    end
    return result
end

local function select_hand_cards(request)
    local indices = normalize_indices(request)
    if not indices then
        return true
    end
    if not G or not G.hand or not G.hand.cards then
        return fail("hand_unavailable", "Hand is not available.", nil, 503)
    end

    G.hand:unhighlight_all()
    for _, index in ipairs(indices) do
        if not index or index < 1 or index > #G.hand.cards then
            return fail("invalid_index", "Hand card index is out of range.", {
                index = index,
                count = #G.hand.cards,
            })
        end
        G.hand:add_to_highlighted(G.hand.cards[index], true)
    end

    return true
end

local function fake_event(card, id)
    return {
        config = {
            ref_table = card,
            id = id,
        },
    }
end

local function action_start_run(mcp, request)
    if not G or not G.FUNCS or not G.FUNCS.start_run then
        return fail("game_unavailable", "Balatro start_run is unavailable.", nil, 503)
    end

    G.FUNCS.start_run(nil, {
        stake = tonumber(request.stake) or 1,
        seed = request.seed,
    })
    return ok(mcp, "start_run", "New run queued.")
end

local function action_select_blind(mcp, request)
    if state_name() ~= "BLIND_SELECT" then
        return fail("invalid_state", "Blind selection is not active.", { screen = state_name() })
    end

    local blind_key = request.blind
    if not blind_key and request.option_index then
        blind_key = ({ "Small", "Big", "Boss" })[tonumber(request.option_index)]
    end
    blind_key = blind_key or (G.GAME and G.GAME.blind_on_deck)

    local choice = G.GAME and G.GAME.round_resets and G.GAME.round_resets.blind_choices and
        G.GAME.round_resets.blind_choices[blind_key]
    if not choice then
        return fail("invalid_blind", "Requested blind is not available.", { blind = blind_key })
    end

    G.FUNCS.select_blind({ config = { ref_table = choice } })
    return ok(mcp, "select_blind", "Blind selection queued.")
end

local function action_skip_blind(mcp)
    if state_name() ~= "BLIND_SELECT" then
        return fail("invalid_state", "Blind selection is not active.", { screen = state_name() })
    end

    local skipped = G.GAME.blind_on_deck or "Small"
    local skip_to = skipped == "Small" and "Big" or skipped == "Big" and "Boss" or "Boss"
    local tag_key = G.GAME.round_resets and G.GAME.round_resets.blind_tags and G.GAME.round_resets.blind_tags[skipped]

    if tag_key and Tag and add_tag then
        add_tag(Tag(tag_key))
    end
    G.GAME.skips = (G.GAME.skips or 0) + 1
    if G.GAME.round_resets and G.GAME.round_resets.blind_states then
        G.GAME.round_resets.blind_states[skipped] = "Skipped"
        G.GAME.round_resets.blind_states[skip_to] = "Select"
    end
    G.GAME.blind_on_deck = skip_to

    if save_run then
        save_run()
    end
    return ok(mcp, "skip_blind", "Blind skipped.")
end

local function action_select_cards(mcp, request)
    local selected, err = select_hand_cards(request)
    if not selected then
        return nil, err
    end
    return ok(mcp, "select_cards", "Hand cards selected.")
end

local function action_play_hand(mcp, request)
    if state_name() ~= "SELECTING_HAND" then
        return fail("invalid_state", "A hand can only be played while selecting hand cards.", { screen = state_name() })
    end

    local selected, err = select_hand_cards(request)
    if not selected then
        return nil, err
    end
    if not G.hand or not G.hand.highlighted or #G.hand.highlighted == 0 then
        return fail("missing_selection", "No hand cards are selected.")
    end
    if G.GAME and G.GAME.blind and G.GAME.blind.block_play then
        return fail("blocked", "The current blind blocks playing a hand.")
    end

    G.FUNCS.play_cards_from_highlighted({})
    return ok(mcp, "play_hand", "Hand play queued.")
end

local function action_discard(mcp, request)
    if state_name() ~= "SELECTING_HAND" then
        return fail("invalid_state", "Cards can only be discarded while selecting hand cards.", { screen = state_name() })
    end
    if not G.GAME or not G.GAME.current_round or (G.GAME.current_round.discards_left or 0) <= 0 then
        return fail("invalid_action", "No discards are left.")
    end

    local selected, err = select_hand_cards(request)
    if not selected then
        return nil, err
    end
    if not G.hand or not G.hand.highlighted or #G.hand.highlighted == 0 then
        return fail("missing_selection", "No hand cards are selected.")
    end

    G.FUNCS.discard_cards_from_highlighted({})
    return ok(mcp, "discard", "Discard queued.")
end

local function action_cash_out(mcp)
    if state_name() ~= "ROUND_EVAL" then
        return fail("invalid_state", "Cash out is only available during round evaluation.", { screen = state_name() })
    end
    G.FUNCS.cash_out({ config = { button = "cash_out" } })
    return ok(mcp, "cash_out", "Cash out queued.")
end

local function action_end_shop(mcp)
    if state_name() ~= "SHOP" then
        return fail("invalid_state", "Shop is not active.", { screen = state_name() })
    end
    G.FUNCS.toggle_shop({})
    return ok(mcp, "end_shop", "Shop exit queued.")
end

local function action_reroll_shop(mcp)
    if state_name() ~= "SHOP" then
        return fail("invalid_state", "Shop is not active.", { screen = state_name() })
    end
    if G.GAME and G.GAME.current_round and
        ((G.GAME.dollars - G.GAME.bankrupt_at) - G.GAME.current_round.reroll_cost < 0) and
        G.GAME.current_round.reroll_cost ~= 0 then
        return fail("not_affordable", "Shop reroll is not affordable.")
    end
    G.FUNCS.reroll_shop({})
    return ok(mcp, "reroll_shop", "Shop reroll queued.")
end

local function action_reroll_boss(mcp)
    if state_name() ~= "BLIND_SELECT" then
        return fail("invalid_state", "Blind selection is not active.", { screen = state_name() })
    end
    G.FUNCS.reroll_boss({})
    return ok(mcp, "reroll_boss", "Boss reroll queued.")
end

local function action_buy(mcp, request)
    if state_name() ~= "SHOP" then
        return fail("invalid_state", "Shop is not active.", { screen = state_name() })
    end

    local card, err = get_card_from_area(request.area or "shop_jokers", get_index(request))
    if not card then
        return nil, err
    end

    local event = fake_event(card, request.buy_and_use and "buy_and_use" or nil)
    if card.ability and (card.ability.set == "Voucher" or card.ability.set == "Booster") then
        G.FUNCS.use_card(event)
    else
        G.FUNCS.buy_from_shop(event)
    end
    return ok(mcp, "buy", "Shop purchase queued.")
end

local function action_use(mcp, request)
    local area_name = request.area
    if not area_name then
        area_name = (state_name():find("_PACK") and "pack") or "consumeables"
    end

    local selected, select_err = select_hand_cards(request)
    if not selected then
        return nil, select_err
    end

    local card, err = get_card_from_area(area_name, get_index(request))
    if not card then
        return nil, err
    end

    G.FUNCS.use_card(fake_event(card))
    return ok(mcp, "use", "Use card queued.")
end

local function action_sell(mcp, request)
    local area_name = request.area or "jokers"
    local card, err = get_card_from_area(area_name, get_index(request))
    if not card then
        return nil, err
    end
    if not card.sell_card then
        return fail("invalid_action", "Selected card cannot be sold.", { area = area_name })
    end

    card:sell_card()
    return ok(mcp, "sell", "Card sold.")
end

local function action_skip_booster(mcp)
    local screen = state_name()
    if not screen:find("_PACK") then
        return fail("invalid_state", "No booster pack is open.", { screen = screen })
    end
    G.FUNCS.skip_booster({})
    return ok(mcp, "skip_booster", "Booster skipped.")
end

local function action_sort_hand(mcp, request)
    local mode = request.mode or request.sort or "value"
    if mode == "suit" then
        G.FUNCS.sort_hand_suit({})
    else
        G.FUNCS.sort_hand_value({})
    end
    return ok(mcp, "sort_hand", "Hand sorted.")
end

local function action_return_to_menu(mcp)
    if not G then
        return fail("game_unavailable", "Balatro game object is unavailable.", nil, 503)
    end

    if G.E_MANAGER and G.E_MANAGER.clear_queue then
        G.E_MANAGER:clear_queue()
    end
    if G.delete_run then
        G:delete_run()
    end
    if G.main_menu then
        G:main_menu("game")
    end
    return ok(mcp, "return_to_menu", "Returned to menu.")
end

local HANDLERS = {
    start_run = action_start_run,
    select_blind = action_select_blind,
    skip_blind = action_skip_blind,
    select_cards = action_select_cards,
    play_hand = action_play_hand,
    discard = action_discard,
    cash_out = action_cash_out,
    end_shop = action_end_shop,
    reroll_shop = action_reroll_shop,
    reroll_boss = action_reroll_boss,
    buy = action_buy,
    use = action_use,
    sell = action_sell,
    skip_booster = action_skip_booster,
    sort_hand = action_sort_hand,
    return_to_menu = action_return_to_menu,
}

function Actions.execute(mcp, request)
    request = request or {}
    local action = request.action or request.name
    if type(action) ~= "string" or action == "" then
        return fail("missing_action", "Request must include an action name.", nil, 400)
    end

    local handler = HANDLERS[action]
    if not handler then
        return fail("unknown_action", "Unknown action.", { action = action }, 404)
    end

    return handler(mcp, request)
end

return Actions
