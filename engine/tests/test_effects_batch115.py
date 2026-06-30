"""Effects Batch 115: White Hole shields its controller's monsters from a chained Dark Hole.

A speed-2 quick Trap that chains to the opponent's "Dark Hole"; it resolves first (LIFO) and
marks its controller's monsters immune to that chain's effect-destruction, so Dark Hole still
wipes the opponent's board but spares yours.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS, _chain_top_is_dark_hole
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ChainLink
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, B, Phase.MAIN_1  # B's turn: B activates Dark Hole
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _place_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def _link(inst, name, controller):
    return ChainLink(inst.iid, EFFECTS[name][0], controller, (), None)


# ----------------------------------------------------------------- the shield


def test_white_hole_shields_controllers_monsters():
    s = _fresh()
    a_mon = _spawn(s, "Celtic Guardian", A, 0)  # White Hole's controller
    b_mon = _spawn(s, "Summoned Skull", B, 0)  # Dark Hole's controller
    dark = _place_st(s, "Dark Hole", B)
    white = _place_st(s, "White Hole", A)
    s.chain = [_link(dark, "Dark Hole", B), _link(white, "White Hole", A)]  # White on top
    Engine(s, [Agent(), Agent()])._resolve_chain()
    assert a_mon.zone is Zone.MONSTER  # A's monster survives
    assert b_mon.zone is not Zone.MONSTER  # B's own monster is still destroyed
    assert s.protected_from_destruction == set()  # flag cleared after the chain


def test_dark_hole_without_white_hole_wipes_both():
    s = _fresh()
    a_mon = _spawn(s, "Celtic Guardian", A, 0)
    b_mon = _spawn(s, "Summoned Skull", B, 0)
    dark = _place_st(s, "Dark Hole", B)
    s.chain = [_link(dark, "Dark Hole", B)]
    Engine(s, [Agent(), Agent()])._resolve_chain()
    assert a_mon.zone is not Zone.MONSTER
    assert b_mon.zone is not Zone.MONSTER


# ----------------------------------------------------------------- the trigger condition


def test_condition_matches_dark_hole_on_top_of_chain():
    s = _fresh()
    dark = _place_st(s, "Dark Hole", B)
    s.chain = [_link(dark, "Dark Hole", B)]
    assert _chain_top_is_dark_hole(s, A)


def test_condition_rejects_a_different_spell():
    s = _fresh()
    rai = _place_st(s, "Raigeki", B)
    s.chain = [_link(rai, "Raigeki", B)]
    assert not _chain_top_is_dark_hole(s, A)
