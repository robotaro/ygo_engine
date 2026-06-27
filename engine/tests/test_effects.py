"""Slice 1 effect tests: activating Normal Spells resolves their primitives."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _spell_in_hand(state, player, name):
    inst = state.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    state.players[player].hand.append(inst.iid)
    return inst


def test_pot_of_greed_draws_two():
    state = GameState.new(("A", "B"), seed=1)
    state.phase = Phase.MAIN_1
    # stock the deck so there's something to draw
    for _ in range(5):
        d = state.create_instance(reg.get("Battle Ox"), owner=0, zone=Zone.DECK)
        state.players[0].deck.append(d.iid)
    pot = _spell_in_hand(state, 0, "Pot of Greed")

    before = len(state.players[0].hand)
    apply(state, ActivateSpell(pot.iid))
    # +2 drawn, -1 for the Pot itself leaving the hand
    assert len(state.players[0].hand) == before + 2 - 1
    assert state.inst(pot.iid).zone is Zone.GRAVEYARD


def test_dark_hole_destroys_all_monsters():
    state = GameState.new(("A", "B"), seed=1)
    state.phase = Phase.MAIN_1
    state.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    state.spawn_on_field(reg.get("Battle Ox"), 1, 0, Position.FACE_UP_ATTACK)
    state.spawn_on_field(reg.get("Vorse Raider"), 1, 1, Position.FACE_DOWN_DEFENSE)
    dark_hole = _spell_in_hand(state, 0, "Dark Hole")

    apply(state, ActivateSpell(dark_hole.iid))
    assert all(s is None for s in state.players[0].monster_zones)
    assert all(s is None for s in state.players[1].monster_zones)
    assert len(state.players[1].graveyard) == 2  # both opponent monsters


def test_raigeki_only_hits_opponent():
    state = GameState.new(("A", "B"), seed=1)
    state.phase = Phase.MAIN_1
    mine = state.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    state.spawn_on_field(reg.get("Battle Ox"), 1, 0, Position.FACE_UP_ATTACK)
    raigeki = _spell_in_hand(state, 0, "Raigeki")

    apply(state, ActivateSpell(raigeki.iid))
    assert state.players[0].monster_zones[0] == mine.iid  # my monster survives
    assert all(s is None for s in state.players[1].monster_zones)


def test_spell_appears_as_legal_action_in_main_phase():
    state = GameState.new(("A", "B"), seed=1)
    state.phase = Phase.MAIN_1
    pot = _spell_in_hand(state, 0, "Pot of Greed")
    actions = legal_actions(state, 0)
    assert any(isinstance(a, ActivateSpell) and a.iid == pot.iid for a in actions)
