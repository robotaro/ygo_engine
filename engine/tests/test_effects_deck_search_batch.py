"""Effects Batch 15: generalised Deck search ("add 1 [X] from your Deck to hand").

A CardFilter both gates activation (a matching card must be in the Deck) and
selects the fetch (deterministic: the highest-ATK match), then the Deck shuffles.
Cards: Reinforcement of the Army (Lv<=4 Warrior), Summoner's Art (Lv>=5 Normal
Monster), Terraforming (Field Spell), Fusion Sage (Polymerization), E - Emergency
Call (Elemental HERO), Gladiator Proving Ground (Lv<=4 Gladiator Beast), Toon
Table of Contents (any "Toon" card)."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_deck(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _activatable(s, iid, player=0):
    return [a for a in legal_actions(s, player) if isinstance(a, ActivateSpell) and a.iid == iid]


# --- Reinforcement of the Army: Level 4 or lower Warrior -----------------------
def test_reinforcement_fetches_a_low_level_warrior():
    s = GameState.new(("A", "B"), seed=0)
    target = _in_deck(s, "Gearfried the Iron Knight")  # Warrior, Level 4
    decoy = _in_deck(s, "Summoned Skull")  # Fiend — not a Warrior
    spell = _in_hand(s, "Reinforcement of the Army")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(target.iid).zone is Zone.HAND
    assert s.inst(decoy.iid).zone is Zone.DECK  # untouched
    assert s.inst(spell.iid).zone is Zone.GRAVEYARD


def test_reinforcement_excludes_high_level_warriors():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 1, 0
    big = _in_deck(s, "Gilford the Lightning")  # Warrior, but Level 8 -> too high
    spell = _in_hand(s, "Reinforcement of the Army")
    assert _activatable(s, spell.iid) == []  # no Level 4 or lower Warrior to fetch
    apply(s, ActivateSpell(spell.iid))  # a forced resolve still fetches nothing
    assert s.inst(big.iid).zone is Zone.DECK


def test_search_not_activatable_without_a_valid_target():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 1, 0
    _in_deck(s, "Summoned Skull")  # no Warrior in the Deck
    spell = _in_hand(s, "Reinforcement of the Army")
    assert _activatable(s, spell.iid) == []
    _in_deck(s, "Marauding Captain")  # now a Level 3 Warrior exists
    assert _activatable(s, spell.iid)


# --- Summoner's Art: Level 5 or higher Normal Monster --------------------------
def test_summoners_art_fetches_high_level_normal_monster_only():
    s = GameState.new(("A", "B"), seed=0)
    target = _in_deck(s, "Summoned Skull")  # Normal Monster, Level 6
    effect_mon = _in_deck(s, "Gilford the Lightning")  # Level 8 but an Effect Monster
    spell = _in_hand(s, "Summoner's Art")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(target.iid).zone is Zone.HAND
    assert s.inst(effect_mon.iid).zone is Zone.DECK  # not a Normal Monster


# --- Terraforming: any Field Spell ---------------------------------------------
def test_terraforming_fetches_a_field_spell():
    s = GameState.new(("A", "B"), seed=0)
    field = _in_deck(s, "Sogen")  # Field Spell
    other_spell = _in_deck(s, "Pot of Greed")  # a Normal Spell, not a Field Spell
    spell = _in_hand(s, "Terraforming")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(field.iid).zone is Zone.HAND
    assert s.inst(other_spell.iid).zone is Zone.DECK


# --- Fusion Sage: exactly Polymerization ---------------------------------------
def test_fusion_sage_fetches_polymerization_by_name():
    s = GameState.new(("A", "B"), seed=0)
    poly = _in_deck(s, "Polymerization")
    spell = _in_hand(s, "Fusion Sage")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(poly.iid).zone is Zone.HAND


# --- E - Emergency Call: Elemental HERO (name substring) -----------------------
def test_e_emergency_call_fetches_an_elemental_hero():
    s = GameState.new(("A", "B"), seed=0)
    hero = _in_deck(s, "Elemental HERO Avian")
    decoy = _in_deck(s, "Summoned Skull")
    spell = _in_hand(s, "E - Emergency Call")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(hero.iid).zone is Zone.HAND
    assert s.inst(decoy.iid).zone is Zone.DECK


# --- Gladiator Proving Ground: Level <=4 Gladiator Beast -----------------------
def test_gladiator_proving_ground_fetches_a_low_level_gladiator_beast():
    s = GameState.new(("A", "B"), seed=0)
    gb = _in_deck(s, "Gladiator Beast Andal")  # Level 4 Gladiator Beast
    spell = _in_hand(s, "Gladiator Proving Ground")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(gb.iid).zone is Zone.HAND


# --- Toon Table of Contents: any "Toon" card -----------------------------------
def test_toon_table_fetches_any_toon_named_card():
    s = GameState.new(("A", "B"), seed=0)
    toon = _in_deck(s, "Blue-Eyes Toon Dragon")  # name contains "Toon"
    spell = _in_hand(s, "Toon Table of Contents")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(toon.iid).zone is Zone.HAND


# --- the fetch shuffles the rest of the Deck back ------------------------------
def test_search_leaves_the_rest_of_the_deck_intact():
    s = GameState.new(("A", "B"), seed=0)
    target = _in_deck(s, "Marauding Captain")
    others = [_in_deck(s, "Summoned Skull") for _ in range(3)]
    spell = _in_hand(s, "Reinforcement of the Army")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(target.iid).zone is Zone.HAND
    assert {o.iid for o in others} == {i for i in s.players[0].deck}  # the 3 decoys remain
