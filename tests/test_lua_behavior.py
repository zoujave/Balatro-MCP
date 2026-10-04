from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa.lua51")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def lua():
    runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
    runtime.execute('''
        G = {STATES={SHOP=1,SELECTING_HAND=2,BLIND_SELECT=3,ROUND_EVAL=4}, STATE=2,
             STAGES={RUN=1}, STAGE=1, SETTINGS={profile=2, GAMESPEED=4},
             P_CENTER_POOLS={Back={}}, GAME={round=1,round_resets={ante=1},starting_deck_size=52,
             dollars=25, hands={Flush={chips=35,mult=4,level=1,played=0}},current_round={current_hand={},hands_left=4,discards_left=3}},
             FUNCS={}}
        love={timer={getTime=function() return 100 end}}
        function card(id) return {sort_id=id,base={id=id,value=tostring(id),nominal=id,suit='Spades'},
               config={center={key='m_base',name='Default',set='Enhanced'}},ability={},T={x=id,w=1},VT={x=id},states={drag={is=false}}} end
        a,b=card(2),card(3)
        G.hand={cards={a,b},highlighted={a},T={x=0},config={}}
        function G.hand:set_ranks() for i,c in ipairs(self.cards) do c.rank=i end end
        function G.hand:align_cards() table.sort(self.cards,function(a,b)return a.T.x<b.T.x end) end
        G.jokers={cards={},config={card_limit=5}}
        G.deck={cards={}};G.discard={cards={}};G.play={cards={}};G.playing_cards={a,b}
        function update_hand_text(config,values) return nil,42,nil end
        function check_and_set_high_score(score,amount) G.score=amount end
        G.FUNCS.evaluate_play=function()
            update_hand_text({}, {handname='Flush', chips=35, mult=4})
            G.GAME.last_hand_played='Flush'
            check_and_set_high_score('hand',140)
            G.GAME.current_round.current_hand={handname='',chips=0,mult=0}
        end
        G.FUNCS.play_cards_from_highlighted=function() G.play.cards=G.hand.cards;G.hand.cards={};G.FUNCS.evaluate_play() end
    ''')
    runtime.globals().STATE = runtime.execute((ROOT / "mods/BalatroMCP/balatro_mcp/state.lua").read_text(encoding="utf-8"))
    runtime.globals().OBS = runtime.execute((ROOT / "mods/BalatroMCP/balatro_mcp/observations.lua").read_text(encoding="utf-8"))
    runtime.globals().ACTIONS = runtime.execute((ROOT / "mods/BalatroMCP/balatro_mcp/actions.lua").read_text(encoding="utf-8"))
    runtime.execute("mcp={state=STATE, observations=OBS};OBS.initialize(mcp);STATE.build_state(mcp);mcp.control_mode='auto'")
    return runtime


def test_revisions_change_only_for_meaningful_state_and_deck_is_composition(lua):
    lua.execute('''
        first=STATE.build_state(mcp);second=STATE.build_state(mcp)
        assert(first.revision==second.revision)
        assert(first.deck.total==2 and first.deck.by_suit.Spades==2)
        G.deck.cards={b,a};G.hand.cards={};before=STATE.build_state(mcp)
        G.deck.cards={a,b};after=STATE.build_state(mcp)
        assert(before.revision==after.revision)
        G.GAME.dollars=24
        assert(STATE.build_state(mcp).revision~=after.revision)
    ''')


def test_reorder_validation_prevents_partial_mutation_and_preserves_highlights(lua):
    lua.execute('''
        local result,err=ACTIONS.execute(mcp,{action='reorder_cards',area='hand',card_uids={'c2','c2'}})
        assert(not result and err.code=='invalid_order' and G.hand.cards[1]==a)
        local result=ACTIONS.execute(mcp,{action='reorder_cards',area='hand',card_uids={'c3','c2'}})
        assert(result and G.hand.cards[1]==b and G.hand.highlighted[1]==a)
        G.hand:align_cards();assert(G.hand.cards[1]==b)
    ''')


def test_assist_and_stale_state_block_native_action(lua):
    lua.execute('''
        local called=0
        G.FUNCS.reroll_shop=function() called=called+1 end
        mcp.control_mode='assist'
        local result,err=ACTIONS.execute(mcp,{action='reroll_shop'})
        assert(not result and err.code=='assist_mode' and called==0)
        mcp.control_mode='auto'
        local revision=STATE.build_state(mcp).revision
        G.GAME.dollars=10
        local result,err=ACTIONS.execute(mcp,{action='reroll_shop',expected_revision=revision})
        assert(not result and err.code=='stale_state' and called==0)
    ''')


def test_joker_reorder_respects_pinned_cards_and_human_dragging(lua):
    lua.execute('''
        G.STATE=G.STATES.SHOP
        G.jokers.cards={a,b};a.pinned=true
        local result,err=ACTIONS.execute(mcp,{action='reorder_cards',area='jokers',card_uids={'c3','c2'}})
        assert(not result and err.code=='pinned_card' and G.jokers.cards[1]==a)
        a.pinned=nil;b.states.drag.is=true
        local result,err=ACTIONS.execute(mcp,{action='reorder_cards',area='jokers',card_uids={'c3','c2'}})
        assert(not result and err.code=='card_dragging' and G.jokers.cards[1]==a)
        b.states.drag.is=false
        local result=ACTIONS.execute(mcp,{action='reorder_cards',area='jokers',card_uids={'c3','c2'}})
        assert(result and G.jokers.cards[1]==b)
    ''')


def test_retried_request_does_not_reorder_twice(lua):
    lua.execute('''
        local request={action='reorder_cards',area='hand',card_uids={'c3','c2'},client_context={request_id='one'}}
        local first=ACTIONS.execute(mcp,request)
        local second=ACTIONS.execute(mcp,request)
        assert(first and second.duplicate and G.hand.cards[1]==b)
        request.card_uids={'c2','c3'}
        local result,err=ACTIONS.execute(mcp,request)
        assert(not result and err.code=='request_conflict' and G.hand.cards[1]==b)
    ''')


def test_human_scoring_survives_cleared_ui_and_wrappers_preserve_return_values(lua):
    lua.execute('''
        OBS.install(mcp);OBS.install(mcp)
        G.FUNCS.play_cards_from_highlighted()
        local state=STATE.build_state(mcp)
        assert(state.run.current_hand.handname=='')
        assert(state.observations.last_hand.score==140 and state.observations.last_hand.complete)
        assert(state.observations.last_hand.source=='human')
        assert(state.observations.last_hand.hand_type=='Flush')
        assert(#state.observations.hands==1 and state.observations.hands[1].score==140)
        assert(not state.observations.hands[1].trace)
        assert(#state.observations.last_hand.trace==1 and not mcp.observation_error)
        assert(select('#',update_hand_text({},{}))==3)
        assert(#mcp.events==3)
    ''')


def test_http_partial_writes_preserve_whole_response_and_execute_once(lua):
    lua.execute("package.preload.socket=function() return {gettime=function()return 0 end,bind=function()return nil,'test' end} end")
    lua.globals().TESTJSON = lua.execute((ROOT / "mods/BalatroMCP/balatro_mcp/json.lua").read_text(encoding="utf-8"))
    lua.globals().HTTP = lua.execute((ROOT / "mods/BalatroMCP/balatro_mcp/http_server.lua").read_text(encoding="utf-8"))
    lua.execute('''
        local builds=0
        local service={JSON=TESTJSON,state={build_state=function() builds=builds+1;return {screen=string.rep('x',200)} end}}
        local server=HTTP.new(service,{})
        local chunks={}
        local client={buffer='GET /state HTTP/1.1\\r\\n\\r\\n',socket={send=function(self,data)
            local count=math.min(7,#data);chunks[#chunks+1]=data:sub(1,count)
            if count<#data then return nil,'timeout',count end
            return count
        end}}
        for i=1,100 do if server:handle_client(client) then break end end
        local response=table.concat(chunks)
        assert(builds==1 and response:find(string.rep('x',200),1,true))
        assert(client.write_offset>#client.response)
    ''')
