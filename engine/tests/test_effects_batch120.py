"""Effects Batch 120: House of Adhesive Tape.

Trap Hole's mirror: when your opponent Normal/Flip Summons a monster with DEF 500 or less,
destroy it. Tests the new Trigger.max_def gate via the summon response window.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import NormalSummon, Pass, SpecialSummonFromHand, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


class ActivateByName(Agent):
    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, A, Phase.MAIN_1
    return s


def _in_hand(s, name, player=A):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _set_tape(s, player=B, index=0):
    inst = s.create_instance(reg.get("House of Adhesive Tape"), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = 1
    return inst


def _normal_then_window(eng, s, iid, player=A):
    apply(s, NormalSummon(iid))
    eng._response_window({"kind": "summon", "player": player, "monster": iid, "summon_kind": "normal"})


def test_destroys_a_low_def_normal_summon():
    s = _fresh()
    petit = _in_hand(s, "Petit Moth")  # DEF 200 <= 500
    tape = _set_tape(s)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("House of Adhesive Tape")])
    _normal_then_window(eng, s, petit.iid)
    assert s.inst(petit.iid).zone is Zone.GRAVEYARD  # destroyed
    assert s.inst(tape.iid).zone is Zone.GRAVEYARD  # the Trap resolved + went to GY


def test_ignores_a_high_def_summon():
    s = _fresh()
    celtic = _in_hand(s, "Celtic Guardian")  # DEF 1200 > 500
    tape = _set_tape(s)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("House of Adhesive Tape")])
    _normal_then_window(eng, s, celtic.iid)
    assert s.inst(celtic.iid).zone is Zone.MONSTER  # too much DEF -> not offered
    assert s.inst(tape.iid).zone is Zone.SPELL_TRAP  # never activated


def test_ignores_a_special_summon():
    s = _fresh()
    s.spawn_on_field(reg.get("Summoned Skull"), B, 0, Position.FACE_UP_ATTACK)  # enables Cyber Dragon
    cyber = _in_hand(s, "Cyber Dragon")
    tape = _set_tape(s, index=1)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("House of Adhesive Tape")])
    apply(s, SpecialSummonFromHand(cyber.iid))
    eng._response_window({"kind": "summon", "player": A, "monster": cyber.iid, "summon_kind": "special"})
    assert s.inst(cyber.iid).zone is Zone.MONSTER  # Normal/Flip only -> a Special Summon is safe
    assert s.inst(tape.iid).zone is Zone.SPELL_TRAP
