"""Pure, explicitly scoped score and resource comparisons. Never run game callbacks."""
from __future__ import annotations

import copy
import itertools
import math
from collections import Counter
from typing import Any

RANKS = {"Ace": 14, "King": 13, "Queen": 12, "Jack": 11, **{str(n): n for n in range(2, 11)}}
BASE_HANDS = {"High Card": (5, 1), "Pair": (10, 2), "Two Pair": (20, 2), "Three of a Kind": (30, 3),
              "Straight": (30, 4), "Flush": (35, 4), "Full House": (40, 4), "Four of a Kind": (60, 7),
              "Straight Flush": (100, 8), "Five of a Kind": (120, 12), "Flush House": (140, 14), "Flush Five": (160, 16)}
PASSIVE = {"j_rocket", "j_golden", "j_to_the_moon", "j_baseball", "j_hack", "j_mime", "j_sock_and_buskin",
           "j_hanging_chad", "j_dusk", "j_seltzer", "j_four_fingers", "j_shortcut", "j_smeared", "j_splash"}
X_JOKERS = {"j_constellation", "j_campfire", "j_hologram", "j_lucky_cat", "j_obelisk", "j_ramen"}


def rank(card: dict[str, Any]) -> int:
    if card.get("key") == "m_stone": return 0
    return int(card.get("id") or RANKS.get(str(card.get("rank")), 0))


def ability(card: dict[str, Any], name: str, default: Any = 0) -> Any:
    return card.get("ability", {}).get(name, default)


def xmult(card: dict[str, Any], default: float = 1) -> float:
    return float(ability(card, "x_mult", ability(card, "Xmult", default)) or default)


def is_suit(card: dict[str, Any], suit: str, smeared: bool = False) -> bool:
    if card.get("key") == "m_stone":
        return False
    if card.get("key") == "m_wild" and not card.get("debuffed"):
        return True
    actual = card.get("suit")
    if smeared:
        return actual in ({"Spades", "Clubs"} if suit in {"Spades", "Clubs"} else {"Hearts", "Diamonds"})
    return actual == suit


def classify(cards: list[dict[str, Any]], keys: set[str]) -> tuple[str, list[int], set[str]]:
    real = [(i, c) for i, c in enumerate(cards) if c.get("key") != "m_stone"]
    counts = Counter(rank(c) for _, c in real)
    required = 4 if "j_four_fingers" in keys else 5
    flush = next(([i for i, c in real if is_suit(c, suit, "j_smeared" in keys)] for suit in
                  ["Spades", "Hearts", "Clubs", "Diamonds"] if sum(is_suit(c, suit, "j_smeared" in keys) for _, c in real) >= required), [])
    straight: list[int] = []
    ranks = sorted(set(counts) | ({1} if 14 in counts else set()))
    for values in itertools.combinations(ranks, required):
        if 1 in values and 14 in values:
            continue
        gaps = [b - a for a, b in zip(values, values[1:])]
        if all(1 <= gap <= (2 if "j_shortcut" in keys else 1) for gap in gaps):
            straight = [i for i, c in real if (1 if rank(c) == 14 and 1 in values else rank(c)) in values]
    groups = sorted(counts, key=lambda n: (counts[n], n), reverse=True)
    by_rank = lambda ranks_: [i for i, c in real if rank(c) in ranks_]
    five = bool(groups and counts[groups[0]] >= 5)
    four = bool(groups and counts[groups[0]] >= 4)
    three = bool(groups and counts[groups[0]] >= 3)
    pairs = [n for n in groups if counts[n] >= 2]
    full = three and len(pairs) >= 2
    contains = {"High Card"}
    for condition, name in [(bool(pairs), "Pair"), (len(pairs) >= 2, "Two Pair"), (three, "Three of a Kind"),
                            (full, "Full House"), (four, "Four of a Kind"), (five, "Five of a Kind"),
                            (bool(flush), "Flush"), (bool(straight), "Straight")]:
        if condition:
            contains.add(name)
    # Four Fingers can form a straight flush with separate four-card straight/flush subsets.
    if flush and straight:
        name, scoring = "Straight Flush", sorted(set(flush) | set(straight))
    elif four:
        name, scoring = "Four of a Kind", by_rank([groups[0]])
    elif full:
        name, scoring = "Full House", by_rank(pairs[:2])
    elif flush:
        name, scoring = "Flush", flush
    elif straight:
        name, scoring = "Straight", straight
    elif three:
        name, scoring = "Three of a Kind", by_rank([groups[0]])
    elif len(pairs) >= 2:
        name, scoring = "Two Pair", by_rank(pairs[:2])
    elif pairs:
        name, scoring = "Pair", by_rank(pairs[:1])
    else:
        name = "High Card"
        scoring = [max(real, key=lambda item: rank(item[1]))[0]] if real else []
    if five:
        name, scoring = ("Flush Five" if flush else "Five of a Kind"), by_rank(groups[:1])
    elif full and flush:
        name, scoring = "Flush House", by_rank(pairs[:2])
    scoring = sorted(set(scoring) | {i for i, c in enumerate(cards) if c.get("key") == "m_stone"})
    if "j_splash" in keys:
        scoring = list(range(len(cards)))
    return name, scoring, contains


def effective_jokers(jokers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    result, warnings = [], []
    def resolve(index: int, seen: set[int]) -> dict[str, Any] | None:
        if index < 0 or index >= len(jokers):
            return None
        if index in seen:
            warnings.append("Blueprint/Brainstorm copy cycle")
            return None
        card = jokers[index]
        if card.get("debuffed"):
            return None
        key = card.get("key")
        if key in {"j_blueprint", "j_brainstorm"}:
            target = index + 1 if key == "j_blueprint" else 0
            if 0 <= target < len(jokers) and jokers[target].get("blueprint_compat") is False:
                return None
            return resolve(target, seen | {index})
        return card
    for index, original in enumerate(jokers):
        card = resolve(index, set())
        result.append({**(card or {"key": "inactive", "ability": {}}), "index": index + 1,
                       "rarity": original.get("rarity"), "edition": original.get("edition"),
                       "original_key": original.get("key"), "debuffed": original.get("debuffed", False)})
    return result, warnings


def preview_hand(state: dict[str, Any], card_indices: list[int] | None = None) -> dict[str, Any]:
    hand = state.get("hand", {}).get("cards", [])
    indices = card_indices if card_indices is not None else state.get("hand", {}).get("highlighted_indices", [])
    if not indices or len(indices) > 5 or len(set(indices)) != len(indices) or any(not isinstance(i, int) or i < 1 or i > len(hand) for i in indices):
        raise ValueError("Select 1 to 5 distinct valid hand indices")
    # Physical left-to-right order determines scoring; selection-click order does not.
    indices = sorted(indices)
    played, held = [hand[i - 1] for i in indices], [c for i, c in enumerate(hand, 1) if i not in indices]
    if any(c.get("facing") == "back" for c in played + held):
        return {"status": "unsupported", "unsupported_effects": ["Face-down hand cards"], "card_indices": indices}
    jokers, unsupported = effective_jokers(state.get("jokers", {}).get("cards", []))
    keys = {c.get("key") for c in jokers}
    hand_name, scoring, contains = classify(played, keys)
    run = state.get("run", {})
    level = run.get("hand_levels", {}).get(hand_name, {})
    if not level:
        return {"status": "unsupported", "hand_type": hand_name, "unsupported_effects": ["Hand level data unavailable"]}
    chips, mult = float(level["chips"]), float(level["mult"])
    blind = state.get("blind", {})
    if not blind.get("disabled") and blind.get("key") == "bl_arm" and level.get("level", 1) > 1:
        if "l_chips" not in level or "l_mult" not in level: unsupported.append("bl_arm: hand growth data unavailable")
        else:
            chips, mult = max(1, chips - level["l_chips"]), max(1, mult - level["l_mult"])
    if not blind.get("disabled") and blind.get("key") == "bl_flint":
        chips, mult = max(0, math.floor(chips * .5 + .5)), max(1, math.floor(mult * .5 + .5))
    trace = [{"phase": "base", "source": hand_name, "chips": chips, "mult": mult}]
    def change(source: str, add_chips: float = 0, add_mult: float = 0, factor: float = 1, phase: str = "joker") -> None:
        nonlocal chips, mult
        chips += add_chips
        mult = (mult + add_mult) * factor
        if add_chips or add_mult or factor != 1:
            trace.append({"phase": phase, "source": source, "add_chips": add_chips, "add_mult": add_mult,
                          "x_mult": factor, "chips": chips, "mult": mult})
    first_face = next((i for i in scoring if not played[i].get("debuffed") and 11 <= rank(played[i]) <= 13), None)
    normal = run.get("probabilities", {}).get("normal", 1)
    glass_risks = []
    for position, i in enumerate(scoring):
        card = played[i]
        if card.get("debuffed"):
            continue
        if card.get("key") not in {None, "c_base", "m_base", "m_bonus", "m_mult", "m_wild", "m_glass", "m_steel", "m_stone", "m_gold", "m_lucky"}:
            unsupported.append('enhancement:' + str(card.get('key')))
        repeats = 1 + (1 if card.get("seal") == "Red" else 0)
        for joker in jokers:
            key, extra = joker.get("key"), ability(joker, "extra", 1)
            if key == "j_hack" and rank(card) in {2, 3, 4, 5} and card.get("key") != "m_stone": repeats += int(extra)
            elif key == "j_sock_and_buskin" and 11 <= rank(card) <= 13: repeats += int(extra)
            elif key == "j_hanging_chad" and position == 0: repeats += int(extra)
            elif key == "j_dusk" and run.get("hands_left") == 1: repeats += int(extra)
            elif key == "j_seltzer": repeats += 1
        if card.get("key") == "m_glass":
            glass_risks.append({"card_index": indices[i], "uid": card.get("uid"),
                                "break_probability": min(1, normal / float(ability(card, "extra", 4)))})
        if card.get("key") == "m_lucky":
            unsupported.append("m_lucky random triggers")
        for trigger in range(repeats):
            source = f"card:{indices[i]}:trigger:{trigger + 1}"
            nominal = 0 if card.get("key") == "m_stone" else float(card.get("nominal", min(rank(card), 10) if rank(card) != 14 else 11))
            change(source, nominal + float(ability(card, "bonus")) + float(ability(card, "perma_bonus")),
                   float(ability(card, "mult")) if card.get("key") != "m_lucky" else 0,
                   xmult(card), "played_card")
            for joker in jokers:
                key, extra = joker.get("key"), ability(joker, "extra")
                if key in {"j_greedy_joker", "j_lusty_joker", "j_wrathful_joker", "j_gluttenous_joker"}:
                    suit = {"j_greedy_joker": "Diamonds", "j_lusty_joker": "Hearts", "j_wrathful_joker": "Spades", "j_gluttenous_joker": "Clubs"}[key]
                    if is_suit(card, suit, "j_smeared" in keys): change(key, add_mult=float(extra.get("s_mult", 3) if isinstance(extra, dict) else extra or 3), phase="card_joker")
                elif key == "j_even_steven" and rank(card) in {2, 4, 6, 8, 10}: change(key, add_mult=float(extra or 4), phase="card_joker")
                elif key == "j_odd_todd" and rank(card) in {3, 5, 7, 9, 14}: change(key, add_chips=float(extra or 31), phase="card_joker")
                elif key == "j_fibonacci" and rank(card) in {2, 3, 5, 8, 14}: change(key, add_mult=float(extra or 8), phase="card_joker")
                elif key == "j_scary_face" and 11 <= rank(card) <= 13: change(key, add_chips=float(extra or 30), phase="card_joker")
                elif key == "j_smiley" and 11 <= rank(card) <= 13: change(key, add_mult=float(extra or 5), phase="card_joker")
                elif key == "j_photograph" and i == first_face: change(key, factor=float(extra or 2), phase="card_joker")
            edition = card.get("edition")
            if edition == "foil": change(source + ":foil", add_chips=50, phase="edition")
            elif edition == "holo": change(source + ":holo", add_mult=10, phase="edition")
            elif edition == "polychrome": change(source + ":polychrome", factor=1.5, phase="edition")
            elif edition not in {None, "negative"}: unsupported.append(f"edition:{edition}")
    for index, card in enumerate(held):
        if card.get("debuffed"):
            continue
        if card.get("key") not in {None, "c_base", "m_base", "m_bonus", "m_mult", "m_wild", "m_glass", "m_steel", "m_stone", "m_gold", "m_lucky"}:
            unsupported.append('held enhancement:' + str(card.get('key')))
        repeats = 1 + (1 if card.get("seal") == "Red" else 0) + sum(1 for j in jokers if j.get("key") == "j_mime")
        for _ in range(repeats):
            factor = float(ability(card, "h_x_mult", ability(card, "h_Xmult", 1)) or 1)
            change(f"held:{card.get('uid', index)}", add_mult=float(ability(card, "h_mult")), factor=factor, phase="held_card")
            for joker in jokers:
                if joker.get("key") == "j_baron" and rank(card) == 13:
                    change("j_baron", factor=float(ability(joker, "extra", 1.5)), phase="held_joker")
    card_jokers = {"j_greedy_joker", "j_lusty_joker", "j_wrathful_joker", "j_gluttenous_joker", "j_even_steven", "j_odd_todd", "j_fibonacci", "j_scary_face", "j_smiley", "j_photograph", "j_baron"}
    baseball = [float(ability(j, "extra", 1.5)) for j in jokers if j.get("key") == "j_baseball"]
    for joker in jokers:
        key, extra = joker.get("key"), ability(joker, "extra")
        if joker.get("debuffed"):
            continue
        edition = joker.get("edition")
        if edition == "foil": change(key + ":foil", add_chips=50, phase="edition")
        elif edition == "holo": change(key + ":holo", add_mult=10, phase="edition")
        elif edition not in {None, "polychrome", "negative"}: unsupported.append(f"edition:{edition}")
        if key == "j_joker": change(key, add_mult=float(ability(joker, "mult", 4)))
        elif key == "j_blackboard":
            # Empty held hands also satisfy the game's black-card tally check.
            if all(is_suit(c, "Spades", "j_smeared" in keys) or is_suit(c, "Clubs", "j_smeared" in keys) for c in held): change(key, factor=float(extra or 3))
        elif key == "j_erosion":
            deck = state.get("deck", {})
            if deck.get("total") is None: unsupported.append("j_erosion: deck size unavailable")
            else: change(key, add_mult=max(0, deck.get("starting_size", 52) - deck["total"]) * float(extra or 4))
        elif key in X_JOKERS: change(key, factor=xmult(joker))
        elif key == "j_supernova": change(key, add_mult=float(level.get("played", 0)) + 1)
        elif key == "j_banner": change(key, add_chips=float(extra or 30) * run.get("discards_left", 0))
        elif key == "j_mystic_summit" and run.get("discards_left") == 0: change(key, add_mult=float(extra or 15))
        elif key == "j_half" and len(played) <= 3: change(key, add_mult=float(extra or 20))
        elif key == "j_bull": change(key, add_chips=max(0, run.get("dollars", 0)) * float(extra or 2))
        elif key in {"j_jolly", "j_zany", "j_mad", "j_crazy", "j_droll", "j_sly", "j_wily", "j_clever", "j_devious", "j_crafty"}:
            kind = ability(joker, "type")
            if kind in contains:
                change(key, add_chips=float(ability(joker, "t_chips")), add_mult=float(ability(joker, "t_mult")))
        elif key not in PASSIVE | card_jokers | {"inactive", "j_mystic_summit", "j_half"}: unsupported.append(str(key))
        if joker.get("rarity") == 2:
            for factor in baseball: change("j_baseball:" + str(joker.get("index")), factor=factor)
        if edition == "polychrome": change(key + ":polychrome", factor=1.5, phase="edition")
    if not blind.get("disabled") and blind.get("key") in {"bl_ox", "bl_eye", "bl_mouth", "bl_psychic", "bl_hook", "bl_tooth", "bl_final_heart"}:
        unsupported.append("blind:" + blind["key"])
    if any(v not in (False, None, 0, "", [], {}) for v in run.get("modifiers", {}).values()):
        unsupported.append("Run modifiers require game scoring verification")
    unsupported = sorted(set(unsupported))
    score = math.floor(chips * mult)
    target = max(0, float(blind.get("chips") or 0) - float(run.get("chips") or 0))
    return {"status": "partial" if unsupported else "supported", "hand_type": hand_name,
            "card_indices": indices, "scoring_card_indices": [indices[i] for i in scoring],
            "chips": chips, "mult": mult, "score": score if not unsupported else None,
            "known_effects_score": score, "unsupported_effects": unsupported, "trace": trace,
            "glass_risks": glass_risks, "any_glass_break_probability": 1 - math.prod(1 - x["break_probability"] for x in glass_risks),
            "remaining_target": target, "passes_blind": score >= target if target and not unsupported else None,
            "model": "base-game deterministic effects; unsupported effects are never treated as exact"}


def reference_context(state: dict[str, Any], indices: list[int] | None) -> tuple[dict[str, Any], list[int] | None, str]:
    if state.get("hand", {}).get("cards"):
        return copy.deepcopy(state), indices, "current_hand"
    last = state.get("observations", {}).get("last_hand") or {}
    reference = last.get("reference_state")
    if not reference:
        raise ValueError("No hand is available; read a playing hand or complete one after the new Mod loads")
    reference = copy.deepcopy(reference)
    for key in ["jokers", "deck"]:
        if key in state: reference[key] = copy.deepcopy(state[key])
    for key in ["dollars", "hand_levels", "probabilities"]:
        if key in state.get("run", {}): reference["run"][key] = copy.deepcopy(state["run"][key])
    return reference, indices or last.get("played_indices"), "last_hand_with_current_inventory"


def economy(state: dict[str, Any]) -> dict[str, Any]:
    income, growth = 0.0, []
    for card in state.get("jokers", {}).get("cards", []):
        if card.get("debuffed"): continue
        key, extra = card.get("key"), ability(card, "extra")
        if key == "j_rocket" and isinstance(extra, dict): income += extra.get("dollars", 0)
        elif key == "j_golden": income += float(extra or 4)
        if key in {"j_constellation", "j_campfire", "j_rocket", "j_hologram"}:
            growth.append({"key": key, "increment": extra, "resets_after_boss": key == "j_campfire", "current_x_mult": xmult(card)})
    return {"known_income_per_round": income, "growth": growth, "scope": "known fixed joker income; conditional income and future draws excluded"}


def compare_swap(state: dict[str, Any], catalog: Any, shop_index: int, replace_index: int,
                 card_indices: list[int] | None = None, placement: int | None = None, horizon_rounds: int = 3) -> dict[str, Any]:
    jokers, shop = state.get("jokers", {}).get("cards", []), state.get("shop", {}).get("jokers", [])
    if not 1 <= shop_index <= len(shop) or not 1 <= replace_index <= len(jokers): raise ValueError("Invalid shop or replacement index")
    candidate, removed = shop[shop_index - 1], jokers[replace_index - 1]
    if candidate.get("set") != "Joker": raise ValueError("Selected shop card is not a Joker")
    if ability(removed, "eternal", False): raise ValueError("An Eternal joker cannot be sold")
    if placement is not None and not 1 <= placement <= len(jokers): raise ValueError("Invalid placement")
    context, indices, basis = reference_context(state, card_indices)
    baseline = preview_hand(context, indices)
    changed = copy.deepcopy(context)
    replacement = copy.deepcopy(candidate)
    defaults = catalog.card(candidate["key"])
    replacement["ability"] = {**defaults.get("ability", {}), **replacement.get("ability", {})}
    replacement["blueprint_compat"] = replacement.get("blueprint_compat", defaults.get("blueprint_compat"))
    changed["jokers"]["cards"].pop(replace_index - 1)
    # Selling the old Joker also grows any remaining Campfire before the purchase.
    for card in changed["jokers"]["cards"]:
        if card.get("key") == "j_campfire" and not card.get("debuffed"):
            card["ability"]["x_mult"] = xmult(card) + float(ability(card, "extra", .25))
    changed["jokers"]["cards"].insert((placement or replace_index) - 1, replacement)
    net_cost = float(candidate.get("cost") or 0) - float(removed.get("sell_cost") or 0)
    changed["run"]["dollars"] = state.get("run", {}).get("dollars", 0) - net_cost
    after = preview_hand(changed, indices)
    before_economy, after_economy = economy(context), economy(changed)
    loss = before_economy["known_income_per_round"] - after_economy["known_income_per_round"]
    return {"basis": basis, "before": baseline, "after": after, "net_cost": net_cost,
            "affordable": changed["run"]["dollars"] >= state.get("run", {}).get("bankrupt_at", 0),
            "cash_after": changed["run"]["dollars"], "before_economy": before_economy, "after_economy": after_economy,
            "known_income_lost_over_horizon": loss * horizon_rounds, "horizon_rounds": horizon_rounds,
            "removed": removed.get("key"), "candidate": candidate.get("key"), "placement": placement or replace_index}


def compare_consumable(state: dict[str, Any], catalog: Any, index: int, card_indices: list[int] | None = None) -> dict[str, Any]:
    cards = state.get("consumeables", {}).get("cards", [])
    if not 1 <= index <= len(cards): raise ValueError("Invalid consumable index")
    card = cards[index - 1]
    context, indices, basis = reference_context(state, card_indices)
    baseline = preview_hand(context, indices)
    sold, used = copy.deepcopy(context), copy.deepcopy(context)
    for joker in sold.get("jokers", {}).get("cards", []):
        if joker.get("key") == "j_campfire" and not joker.get("debuffed"):
            joker["ability"]["x_mult"] = xmult(joker) + float(ability(joker, "extra", .25))
    sold["run"]["dollars"] = context.get("run", {}).get("dollars", 0) + (card.get("sell_cost") or 0)
    set_name = card.get("set") or ability(card, "set")
    use_supported = set_name == "Planet"
    if use_supported:
        kind = ability(card, "hand_type", catalog.card(card.get("key", "")).get("ability", {}).get("hand_type"))
        level = used["run"].get("hand_levels", {}).get(kind)
        if level and "l_chips" in level and "l_mult" in level:
            level["level"] = level.get("level", 1) + 1
            level["chips"] += level.get("l_chips", 0)
            level["mult"] += level.get("l_mult", 0)
        else: use_supported = False
        for joker in used.get("jokers", {}).get("cards", []):
            if joker.get("key") == "j_constellation" and not joker.get("debuffed"):
                joker["ability"]["x_mult"] = xmult(joker) + float(ability(joker, "extra", .1))
    return {"basis": basis, "baseline": baseline, "sell": preview_hand(sold, indices),
            "use": preview_hand(used, indices) if use_supported else {"status": "unsupported", "reason": "Only ordinary single-hand Planet effects currently modeled"},
            "sale_income": card.get("sell_cost", 0), "use_growth_permanent": use_supported,
            "sale_campfire_growth_resets_after_boss": True, "card": catalog.describe(card.get("key", ""), card, state)}
