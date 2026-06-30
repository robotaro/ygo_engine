"""Effects Batch 121: Crass Clown.

When manually switched from Defense to Attack Position, return 1 monster the opponent
controls to its owner's hand — the mirror of Dream Clown (switch to Defense -> destroy),
via a new "changed_to_attack" Trigger.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ChangePosition, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def test_crass_clown_bounces_on_switch_to_attack():
    s = _fresh(tp=A)
    clown = _spawn(s, "Crass Clown", A, 0, Position.FACE_UP_DEFENSE)
    clown.summoned_this_turn = False  # so it may change position this turn
    foe = _spawn(s, "Summoned Skull", B, 0)
    eng = Engine(s, [Agent(), Agent()])
    apply(s, ChangePosition(clown.iid))
    assert s.inst(clown.iid).position is Position.FACE_UP_ATTACK
    eng._emit_trigger(clown.iid, "changed_to_attack", "self")
    assert s.inst(foe.iid).zone is Zone.HAND  # returned to its owner's hand
    assert foe.iid in s.players[B].hand


def test_crass_clown_no_trigger_switching_to_defense():
    s = _fresh(tp=A)
    clown = _spawn(s, "Crass Clown", A, 0, Position.FACE_UP_ATTACK)
    foe = _spawn(s, "Summoned Skull", B, 0)
    apply(s, ChangePosition(clown.iid))  # ATK -> DEF, not the trigger direction
    assert s.inst(clown.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(foe.iid).zone is Zone.MONSTER  # nothing bounced


def test_crass_clown_fires_through_the_main_loop():
    s = _fresh(tp=A)
    clown = _spawn(s, "Crass Clown", A, 0, Position.FACE_UP_DEFENSE)
    clown.summoned_this_turn = False
    foe = _spawn(s, "Summoned Skull", B, 0)

    class FlipThenPass(Agent):
        def decide(self, state, legal):
            cp = next((a for a in legal if isinstance(a, ChangePosition) and a.iid == clown.iid), None)
            return cp if cp is not None else next(a for a in legal if type(a).__name__ == "Pass")

    eng = Engine(s, [FlipThenPass(), Agent()])
    eng._interactive_phase(A)
    assert s.inst(clown.iid).position is Position.FACE_UP_ATTACK
    assert s.inst(foe.iid).zone is Zone.HAND  # bounced via the real loop hook
