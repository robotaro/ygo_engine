"""Effects Batch 103: Multiply.

Tribute 1 face-up "Kuriboh"; Special Summon as many "Kuriboh Tokens"
(Fiend/DARK/Level 1/ATK 300/DEF 200) as possible in Defense Position. Exercises the new
reusable tribute_names cost filter.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, can_pay_costs, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _tokens(s, player):
    return [
        i for i in s.players[player].monster_zones
        if i is not None and s.cards[i].card.name == "Kuriboh Token"
    ]


def test_multiply_swarms_kuriboh_tokens():
    s = _fresh(tp=A)
    kuriboh = _spawn(s, "Kuriboh", A, 0)
    multiply = _in_hand(s, "Multiply", A)
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_as_chain(ActivateSpell(multiply.iid), A)
    assert s.inst(kuriboh.iid).zone is Zone.GRAVEYARD  # the Kuriboh was Tributed (cost)
    toks = _tokens(s, A)
    assert len(toks) >= 1  # filled the freed zone(s)
    assert all(s.cards[i].position is Position.FACE_UP_DEFENSE for i in toks)
    assert s.cards[toks[0]].card.attack == 300  # Kuriboh Token stats


def test_multiply_fills_all_empty_zones():
    s = _fresh(tp=A)
    _spawn(s, "Kuriboh", A, 0)  # the only monster -> 4 other zones free, +1 freed = 5
    multiply = _in_hand(s, "Multiply", A)
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_as_chain(ActivateSpell(multiply.iid), A)
    assert len(_tokens(s, A)) == 5  # all five Monster Zones now hold a Token


def test_multiply_needs_a_face_up_kuriboh():
    s = _fresh(tp=A)
    multiply = _in_hand(s, "Multiply", A)
    # No Kuriboh on the field -> not activatable.
    assert not any(isinstance(a, ActivateSpell) and a.iid == multiply.iid for a in legal_actions(s, A))
    assert not can_pay_costs(s, A, multiply.iid, EFFECTS["Multiply"][0])
    # A face-up Kuriboh makes it activatable.
    _spawn(s, "Kuriboh", A, 0)
    assert any(isinstance(a, ActivateSpell) and a.iid == multiply.iid for a in legal_actions(s, A))


def test_multiply_tribute_name_filter_rejects_other_monsters():
    s = _fresh(tp=A)
    _spawn(s, "Summoned Skull", A, 0)  # not a Kuriboh
    multiply = _in_hand(s, "Multiply", A)
    # The condition fails (no face-up Kuriboh) so it cannot be activated...
    assert not can_pay_costs(s, A, multiply.iid, EFFECTS["Multiply"][0])
