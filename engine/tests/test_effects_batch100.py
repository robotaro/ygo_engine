"""Effects Batch 100: position & flip control.

- Dream Clown: when manually switched from Attack to face-up Defense Position, destroy 1
  monster the opponent controls (a new "changed_to_defense" Trigger).
- Invader of the Throne: FLIP — switch control of 1 opponent monster with this card (a
  permanent control swap), but not during the Battle Phase.
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


# --------------------------------------------------------------------- Dream Clown


def test_dream_clown_destroys_on_switch_to_defense():
    s = _fresh(tp=A)
    clown = _spawn(s, "Dream Clown", A, 0, Position.FACE_UP_ATTACK)
    clown.summoned_this_turn = False  # so it may change position this turn
    foe = _spawn(s, "Summoned Skull", B, 0)
    eng = Engine(s, [Agent(), Agent()])
    # Drive the position change through the same path the main loop uses.
    apply(s, ChangePosition(clown.iid))
    assert s.inst(clown.iid).position is Position.FACE_UP_DEFENSE
    eng._emit_trigger(clown.iid, "changed_to_defense", "self")
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # the opponent's monster is destroyed


def test_dream_clown_no_trigger_switching_to_attack():
    s = _fresh(tp=A)
    clown = _spawn(s, "Dream Clown", A, 0, Position.FACE_UP_DEFENSE)
    foe = _spawn(s, "Summoned Skull", B, 0)
    apply(s, ChangePosition(clown.iid))  # DEF -> ATK, not the trigger direction
    assert s.inst(clown.iid).position is Position.FACE_UP_ATTACK
    # the main loop only emits on a switch *to* Defense, so the foe survives
    assert s.inst(foe.iid).zone is Zone.MONSTER


def test_dream_clown_fires_through_the_main_loop():
    s = _fresh(tp=A)
    clown = _spawn(s, "Dream Clown", A, 0, Position.FACE_UP_ATTACK)
    clown.summoned_this_turn = False
    foe = _spawn(s, "Summoned Skull", B, 0)

    class FlipThenPass(Agent):
        def decide(self, state, legal):
            cp = next((a for a in legal if isinstance(a, ChangePosition) and a.iid == clown.iid), None)
            return cp if cp is not None else next(a for a in legal if type(a).__name__ == "Pass")

    eng = Engine(s, [FlipThenPass(), Agent()])
    eng._interactive_phase(A)
    assert s.inst(clown.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # destroyed via the real loop hook


# ------------------------------------------------------------- Invader of the Throne


def test_invader_swaps_control_on_flip_summon():
    s = _fresh(tp=A, phase=Phase.MAIN_1)
    invader = _spawn(s, "Invader of the Throne", A, 0, Position.FACE_DOWN_DEFENSE)
    foe = _spawn(s, "Summoned Skull", B, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._trigger_flip_effect(invader.iid)
    # Invader is now on B's side; the Summoned Skull is now A's.
    assert s.inst(invader.iid).controller == B
    assert s.inst(foe.iid).controller == A
    assert invader.iid in s.players[B].monster_zones
    assert foe.iid in s.players[A].monster_zones


def test_invader_keeps_ownership_after_swap():
    s = _fresh(tp=A)
    invader = _spawn(s, "Invader of the Throne", A, 0, Position.FACE_DOWN_DEFENSE)
    foe = _spawn(s, "Summoned Skull", B, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._trigger_flip_effect(invader.iid)
    assert s.inst(invader.iid).owner == A  # control changed, ownership did not
    assert s.inst(foe.iid).owner == B


def test_invader_does_not_swap_during_battle_phase():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    invader = _spawn(s, "Invader of the Throne", A, 0, Position.FACE_DOWN_DEFENSE)
    foe = _spawn(s, "Summoned Skull", B, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._trigger_flip_effect(invader.iid)  # flipped in combat -> condition blocks the swap
    assert s.inst(invader.iid).controller == A  # unchanged
    assert s.inst(foe.iid).controller == B
