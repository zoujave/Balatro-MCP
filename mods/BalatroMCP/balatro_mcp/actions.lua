local Actions = {}

local ACTION_LOCK_SECONDS = {
    start_run = 1.5,
    select_blind = 1.0,
    skip_blind = 0.5,
    select_cards = 0.1,
    play_hand = 1.0,
    discard = 0.6,
    cash_out = 1.2,
    end_shop = 1.0,
    reroll_shop = 0.7,
    reroll_boss = 0.7,
    buy = 0.7,
    use = 0.7,
    sell = 0.2,
    skip_booster = 0.7,
    sort_hand = 0.1,
    return_to_menu = 1.2,
}

local function current_time()
    if love and love.timer and love.timer.getTime then
        return love.timer.getTime()
    end
    return os.clock()
end

local function fail(code, message, details, status, retryable)
    return nil, {
        code = code or "invalid_action",
        message = message or "Action is not available.",
        details = details,
        status = status or 409,
        retryable = retryable and true or false,
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

local function set_action_lock(mcp, action)
    if not mcp then
        return
    end

    local seconds = ACTION_LOCK_SECONDS[action] or 0.5
    if seconds <= 0 then
        return
    end

    mcp.pending_action = action
    mcp.action_lock_until = current_time() + seconds
end

local function ok(mcp, action, message)
    set_action_lock(mcp, action)
    return {
        action = action,
        message = message or "Action queued.",
        state = current_state(mcp),
    }
end

local function callback_error(code, err)
    return fail(code or "callback_failed", tostring(err), nil, 500, true)
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

local function same_hand_selection(indices)
    if not G or not G.hand or type(G.hand.highlighted) ~= "table" or type(G.hand.cards) ~= "table" then
        return false
    end
    if #indices ~= #G.hand.highlighted then
        return false
    end

    local selected = {}
    for _, highlighted in ipairs(G.hand.highlighted) do
        for index, card in ipairs(G.hand.cards) do
            if card == highlighted then
                selected[index] = true
                break
            end
        end
    end

    for _, index in ipairs(indices) do
        if not selected[index] then
            return false
        end
    end
    return true
end

local function select_hand_cards(request)
    local indices = normalize_indices(request)
    if not indices then
        return true, false
    end
    if not G or not G.hand or not G.hand.cards then
        return fail("hand_unavailable", "Hand is not available.", nil, 503)
    end

    if same_hand_selection(indices) then
        return true, true
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

    return true, false
end

local function fake_event(card, id)
    return {
        config = {
            ref_table = card,
            id = id,
        },
    }
end

local function find_ui_child(root, ids)
    if not root or type(root.get_UIE_by_ID) ~= "function" then
        return nil
    end

    for _, id in ipairs(ids) do
        local ok_find, child = pcall(root.get_UIE_by_ID, root, id)
        if ok_find and child then
            return child
        end
    end

    return nil
end

local function get_blind_choice_key(request)
    if not G or not G.GAME or not G.GAME.round_resets then
        return nil
    end

    local requested = request.blind
    if requested and requested ~= "" then
        local requested_lower = string.lower(tostring(requested))
        for _, key in ipairs({ "Small", "Big", "Boss" }) do
            if string.lower(key) == requested_lower then
                return key
            end
        end
    end

    if request.option_index then
        return ({ "Small", "Big", "Boss" })[tonumber(request.option_index)]
    end

    if G.GAME.blind_on_deck and G.GAME.round_resets.blind_choices[G.GAME.blind_on_deck] then
        return G.GAME.blind_on_deck
    end

    for _, key in ipairs({ "Small", "Big", "Boss" }) do
        local state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states[key]
        if state == "Select" then
            return key
        end
    end

    return nil
end

local function get_blind_select_button(blind_key)
    local choice_box = G.blind_select_opts and G.blind_select_opts[string.lower(tostring(blind_key or ""))]
    if choice_box and choice_box.get_UIE_by_ID then
        return choice_box:get_UIE_by_ID("select_blind_button")
    end
    return nil
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

    if not G.blind_select or not G.blind_prompt_box then
        return fail("not_ready", "Blind selection UI is not ready yet.", nil, 503, true)
    end

    local blind_key = get_blind_choice_key(request)
    local choice_key = blind_key and G.GAME.round_resets.blind_choices[blind_key]
    local choice = choice_key and G.P_BLINDS and G.P_BLINDS[choice_key]
    if not choice then
        return fail("invalid_blind", "Requested blind is not available.", { blind = blind_key })
    end

    local state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states[blind_key]
    if state ~= "Select" and blind_key ~= G.GAME.blind_on_deck then
        return fail("invalid_blind", "Requested blind is not the current selectable blind.", { blind = blind_key, state = state })
    end

    local select_button = get_blind_select_button(blind_key)
    if not select_button or not select_button.UIBox then
        return fail("not_ready", "Blind select button is not ready yet.", nil, 503, true)
    end

    select_button.config.ref_table = select_button.config.ref_table or choice
    G.FUNCS.select_blind(select_button)
    return ok(mcp, "select_blind", "Blind selection queued.")
end

local function action_skip_blind(mcp)
    if state_name() ~= "BLIND_SELECT" then
        return fail("invalid_state", "Blind selection is not active.", { screen = state_name() })
    end

    if not G.blind_select or not G.blind_prompt_box then
        return fail("not_ready", "Blind selection UI is not ready yet.", nil, 503, true)
    end

    local blind_key = G.GAME.blind_on_deck or "Small"
    if blind_key == "Boss" then
        return fail("invalid_blind", "Boss blinds cannot be skipped.")
    end
    local choice_box = G.blind_select_opts and G.blind_select_opts[string.lower(blind_key)]
    local tag_container = choice_box and choice_box:get_UIE_by_ID("tag_container")
    if not tag_container then
        return fail("not_ready", "Blind skip reward UI is not ready yet.", nil, 503, true)
    end
    local ok_call, err = pcall(G.FUNCS.skip_blind, { UIBox = choice_box })
    if not ok_call then
        return callback_error("skip_blind_failed", err)
    end
    return ok(mcp, "skip_blind", "Blind skip queued.")
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
        return fail("blocked", "The current blind is temporarily blocking hand play.", nil, 503, true)
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
    -- The payout remains from the previous round until the native total button appears.
    local button
    if G and G.round_eval and G.I and G.I.UIBOX then
        for _, box in ipairs(G.I.UIBOX) do
            if type(box.get_UIE_by_ID) == "function" then
                local candidate = box:get_UIE_by_ID("cash_out_button")
                if candidate and candidate.config and candidate.config.button == "cash_out" then
                    button = candidate
                    break
                end
            end
        end
    end
    if not button or not G.GAME or not G.GAME.current_round or type(G.GAME.current_round.dollars) ~= "number" then
        return fail("not_ready", "Round evaluation payout is still resolving.", nil, 503, true)
    end
    local ok_call, callback_err = pcall(G.FUNCS.cash_out, button)
    if not ok_call then
        return fail("callback_error", "Cash out callback failed.", { detail = tostring(callback_err) })
    end
    return ok(mcp, "cash_out", "Cash out queued.")
end

local function action_end_shop(mcp)
    if state_name() ~= "SHOP" then
        return fail("invalid_state", "Shop is not active.", { screen = state_name() })
    end
    if G.CONTROLLER and G.CONTROLLER.locks and G.CONTROLLER.locks.toggle_shop then
        return fail("not_ready", "Shop transition is already in progress.", nil, 503, true)
    end
    if not G.shop then
        return fail("not_ready", "Shop UI is not ready yet.", nil, 503, true)
    end

    local shop_button = find_ui_child(G.shop, { "next_round_button", "next_round", "toggle_shop" }) or G.shop
    local ok_call, err = pcall(G.FUNCS.toggle_shop, shop_button)
    if not ok_call then
        return callback_error("end_shop_failed", err)
    end
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
    if not mcp.state.can_reroll_boss() then
        return fail("not_available", "Boss reroll requires an affordable, unused voucher allowance.")
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

    if not G.FUNCS or type(G.FUNCS.sell_card) ~= "function" then
        return fail("not_ready", "Sell callback is unavailable.", nil, 503)
    end
    local ok_call, callback_err = pcall(G.FUNCS.sell_card, fake_event(card))
    if not ok_call then
        return fail("callback_error", "Sell callback failed.", { detail = tostring(callback_err) })
    end
    return ok(mcp, "sell", "Card sale queued.")
end

local function action_skip_booster(mcp)
    local screen = state_name()
    if not screen:find("_PACK") and screen ~= "SMODS_BOOSTER_OPENED" then
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

    if action_lock_active(mcp) then
        return fail("action_pending", "Previous action is still resolving.", {
            pending_action = mcp and mcp.pending_action,
            retry_after_seconds = math.max(0, (tonumber(mcp and mcp.action_lock_until) or 0) - current_time()),
        }, 503, true)
    end

    local handler = HANDLERS[action]
    if not handler then
        return fail("unknown_action", "Unknown action.", { action = action }, 404)
    end

    return handler(mcp, request)
end

return Actions
