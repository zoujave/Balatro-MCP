"""Verify deck editing preserves unrelated Balatro progress and rejects ambiguity."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("unlock_decks", Path(__file__).parents[1] / "scripts/unlock-decks.py")
unlock_decks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unlock_decks)


def test_edit_preserves_all_unrelated_progress_and_is_idempotent():
    original = 'return {["alerted"]={["b_magic"]=false,},["unlocked"]={["j_joker"]=true,["v_overstock"]=false,["b_red"]=true,["b_magic"]=false,},["discovered"]={["b_magic"]=false,},}'
    updated, changed = unlock_decks.unlock_save_text(original, ["b_red", "b_magic", "b_ghost"])
    expected = original.replace('["b_magic"]=false,},["discovered"]', '["b_magic"]=true,["b_ghost"]=true,},["discovered"]')
    assert updated == expected
    assert changed == ["b_magic", "b_ghost"]
    assert unlock_decks.read_save(unlock_decks.pack_save(updated)) == expected
    assert unlock_decks.unlock_save_text(updated, ["b_red", "b_magic", "b_ghost"]) == (expected, [])


@pytest.mark.parametrize("original", [
    'return {["unlocked"]={["b_magic"]=false,["b_magic"]=true,},}',
    'return {["unlocked"]={["nested"]={},},}',
    'return {["unlocked"]={["b_magic"]=42,},}',
    'return {["unlocked"]={["b_magic"]=truejunk,},}',
    'return {["discovered"]={},}',
])
def test_refuses_ambiguous_or_unrecognized_save(original):
    with pytest.raises(ValueError):
        unlock_decks.unlock_save_text(original, ["b_magic"])


def test_plain_text_save_is_accepted_without_executing_lua():
    original = 'return {["unlocked"]={},}'
    assert unlock_decks.read_save(original.encode()) == original
