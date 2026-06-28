"""Effects Batch 10: bounce — return cards to the hand or to the top of the Deck.

To hand: Compulsory Evacuation Device (trap), Hane-Hane / Gravekeeper's Guard
(flips), Giant Trunade (all Spell/Traps). To the top of the Deck: Back to Square
One and Phoenix Wing Wind Blast (both compose Batch 8's discard cost)."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _cast(s, name, targets=(), player=0):
    spell = _in_hand(s, name, player)
    apply(s, ActivateSpell(spell.iid, targets=targets))
    return spell


# --- return to hand ------------------------------------------------------------
def test_compulsory_evacuation_device_returns_a_monster_to_hand():
    s = GameState.new(("A", "B"), seed=0)
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    _cast(s, "Compulsory Evacuation Device", targets=(foe.iid,))
    assert s.inst(foe.iid).zone is Zone.HAND
    assert foe.iid in s.players[1].hand  # back to its owner's hand


def test_hane_hane_bounces_a_monster_on_flip():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    hane = s.spawn_on_field(reg.get("Hane-Hane"), 0, 0, Position.FACE_DOWN_DEFENSE)
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    Engine(s, [GreedyAgent(), GreedyAgent()])._trigger_flip_effect(hane.iid)
    assert s.inst(foe.iid).zone is Zone.HAND


def test_gravekeepers_guard_bounces_an_opponent_monster_on_flip():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    guard = s.spawn_on_field(reg.get("Gravekeeper's Guard"), 0, 0, Position.FACE_DOWN_DEFENSE)
    foe = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    Engine(s, [GreedyAgent(), GreedyAgent()])._trigger_flip_effect(guard.iid)
    assert s.inst(foe.iid).zone is Zone.HAND


def test_giant_trunade_returns_all_spell_traps_to_hand():
    s = GameState.new(("A", "B"), seed=0)
    mine = _in_hand(s, "Messenger of Peace", 0)
    s.place_spell_trap(mine.iid, 0, 0, Position.FACE_UP_ATTACK)
    theirs = _in_hand(s, "Mirror Force", 1)
    s.place_spell_trap(theirs.iid, 1, 0, Position.FACE_DOWN)
    _cast(s, "Giant Trunade")
    assert s.inst(mine.iid).zone is Zone.HAND
    assert s.inst(theirs.iid).zone is Zone.HAND  # both players' S/T return
    assert mine.iid in s.players[0].hand and theirs.iid in s.players[1].hand


# --- return to the top of the Deck (with a discard cost) -----------------------
def test_back_to_square_one_puts_a_monster_on_top_of_deck():
    s = GameState.new(("A", "B"), seed=0)
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    fodder = _in_hand(s, "Mystical Elf")
    _cast(s, "Back to Square One", targets=(foe.iid,))
    assert s.inst(foe.iid).zone is Zone.DECK
    assert s.players[1].deck[-1] == foe.iid  # top of deck == end of the list
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # discard cost paid


def test_phoenix_wing_wind_blast_decks_an_opponent_card():
    s = GameState.new(("A", "B"), seed=0)
    foe_st = _in_hand(s, "Messenger of Peace", 1)
    s.place_spell_trap(foe_st.iid, 1, 0, Position.FACE_UP_ATTACK)
    fodder = _in_hand(s, "Mystical Elf")
    _cast(s, "Phoenix Wing Wind Blast", targets=(foe_st.iid,))
    assert s.inst(foe_st.iid).zone is Zone.DECK  # a Spell/Trap is a valid "card you control" target
    assert s.players[1].deck[-1] == foe_st.iid
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD
