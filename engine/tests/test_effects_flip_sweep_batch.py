"""Effects Batch 25: Flip Effects sweep.

Flip Effects (timing="flip") fire via engine._trigger_flip_effect when a monster is
turned face-up. Each here composes an existing primitive: targeted/typed destruction
(Old Vindictive Magician / White Ninja / Armed Ninja / Crimson Ninja / Trap Master),
bounce (Tornado Bird), burn-per-card (Des Koala), the Batch 23 SS-from-Deck
(Gravekeeper's Spy, Bubonic Vermin), and the Batch 15 Deck search (Machina Defender)."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import target_candidates
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _flip(s, name, player=0, index=0):
    """A just-flipped-up monster (face-up Attack), ready for its Flip Effect."""
    return s.spawn_on_field(reg.get(name), player, index, Position.FACE_UP_ATTACK)


def _spell_trap(s, name, player, index, position=Position.FACE_UP_ATTACK):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, position)
    return inst


def _stock_deck(s, player, names):
    for name in names:
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


def _hand(s, player, names):
    for name in names:
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
        s.players[player].hand.append(inst.iid)


# --- targeted / typed destruction ------------------------------------------------
def test_old_vindictive_magician_destroys_an_opponent_monster():
    s = _fresh()
    ovm = _flip(s, "Old Vindictive Magician", 0, 0)
    prey = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(ovm.iid)
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD


def test_armed_ninja_targets_only_a_spell():
    s = _fresh()
    _flip(s, "Armed Ninja", 0, 0)
    spell = _spell_trap(s, "Black Pendant", 1, 0)  # a Spell
    _spell_trap(s, "Magic Jammer", 1, 1)  # a Trap (not a legal target)
    spec = reg.get("Armed Ninja").effects[0].target
    assert target_candidates(s, 0, spec) == [spell.iid]


def test_crimson_ninja_targets_only_a_trap_and_destroys_it():
    s = _fresh()
    ninja = _flip(s, "Crimson Ninja", 0, 0)
    _spell_trap(s, "Black Pendant", 1, 0)  # a Spell (not a legal target)
    trap = _spell_trap(s, "Magic Jammer", 1, 1)  # a Trap
    spec = reg.get("Crimson Ninja").effects[0].target
    assert target_candidates(s, 0, spec) == [trap.iid]
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(ninja.iid)
    assert s.inst(trap.iid).zone is Zone.GRAVEYARD


def test_white_ninja_destroys_a_defense_position_monster():
    s = _fresh()
    wn = _flip(s, "White Ninja", 0, 0)
    facedown = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_DOWN_DEFENSE)
    attacker = s.spawn_on_field(reg.get("Summoned Skull"), 1, 1, Position.FACE_UP_ATTACK)
    spec = reg.get("White Ninja").effects[0].target
    assert facedown.iid in target_candidates(s, 0, spec)
    assert attacker.iid not in target_candidates(s, 0, spec)  # not in Defense Position
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(wn.iid)
    assert s.inst(facedown.iid).zone is Zone.GRAVEYARD


# --- bounce ----------------------------------------------------------------------
def test_tornado_bird_returns_two_spell_traps_to_hand():
    s = _fresh()
    bird = _flip(s, "Tornado Bird", 0, 0)
    a = _spell_trap(s, "Black Pendant", 1, 0)
    b = _spell_trap(s, "Magic Jammer", 0, 1)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(bird.iid)
    assert s.inst(a.iid).zone is Zone.HAND and s.inst(b.iid).zone is Zone.HAND


# --- burn per card ---------------------------------------------------------------
def test_des_koala_burns_400_per_card_in_opponent_hand():
    s = _fresh()
    koala = _flip(s, "Des Koala", 0, 0)
    _hand(s, 1, ["Mystical Elf", "Summoned Skull", "Black Pendant"])  # 3 cards
    before = s.players[1].life_points
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(koala.iid)
    assert s.players[1].life_points == before - 1200  # 400 x 3


# --- Special Summon / search from the Deck ---------------------------------------
def test_gravekeepers_spy_special_summons_from_deck():
    s = _fresh()
    spy = _flip(s, "Gravekeeper's Spy", 0, 1)
    _stock_deck(s, 0, ["Gravekeeper's Guard"])  # Gravekeeper's, low ATK -> eligible
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(spy.iid)
    summoned = s.players[0].monster_zones[0]
    assert summoned is not None and s.inst(summoned).name == "Gravekeeper's Guard"


def test_bubonic_vermin_summons_itself_face_down():
    s = _fresh()
    v = _flip(s, "Bubonic Vermin", 0, 1)
    _stock_deck(s, 0, ["Bubonic Vermin"])
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(v.iid)
    summoned = s.players[0].monster_zones[0]
    assert summoned is not None and s.inst(summoned).position is Position.FACE_DOWN_DEFENSE


def test_machina_defender_searches_commander_covington():
    s = _fresh()
    md = _flip(s, "Machina Defender", 0, 0)
    _stock_deck(s, 0, ["Commander Covington", "Mystical Elf"])
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(md.iid)
    assert any(s.inst(i).name == "Commander Covington" for i in s.players[0].hand)
