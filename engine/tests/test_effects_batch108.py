"""Effects Batch 108: Standby/End-Phase upkeep beatsticks.

- Solar Flare Dragon: cannot be selected as an attack target while you control another
  Pyro (self-only AttackTargetProtection gated on another Pyro), and burns the opponent
  for 500 at each of your End Phases.
- Legendary Fiend: once per turn during your Standby Phase, permanently gains 700 ATK.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import StandbyTrigger
from ygo.engine import Engine
from ygo.enums import Phase, Position
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.STANDBY):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


# ----------------------------------------------------------- Solar Flare Dragon


def test_solar_flare_unprotected_alone():
    s = _fresh()
    sfd = _spawn(s, "Solar Flare Dragon", A, 0)  # no other Pyro
    assert not s.is_protected_attack_target(sfd.iid)


def test_solar_flare_protected_with_another_pyro():
    s = _fresh()
    sfd = _spawn(s, "Solar Flare Dragon", A, 0)
    sfd2 = _spawn(s, "Solar Flare Dragon", A, 1)  # another Pyro -> mutual protection
    assert s.is_protected_attack_target(sfd.iid)
    assert s.is_protected_attack_target(sfd2.iid)


def test_solar_flare_non_pyro_ally_does_not_protect():
    s = _fresh()
    sfd = _spawn(s, "Solar Flare Dragon", A, 0)
    _spawn(s, "Celtic Guardian", A, 1)  # a Warrior, not a Pyro
    assert not s.is_protected_attack_target(sfd.iid)


def test_solar_flare_burns_opponent_each_end_phase():
    s = _fresh(tp=A, phase=Phase.END)
    _spawn(s, "Solar Flare Dragon", A, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_end_phase_triggers(A)  # A's End Phase
    assert s.players[B].life_points == 8000 - 500


def test_solar_flare_burn_only_on_controllers_end_phase():
    s = _fresh(tp=B, phase=Phase.END)
    _spawn(s, "Solar Flare Dragon", A, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_end_phase_triggers(B)  # the OPPONENT's End Phase -> no burn
    assert s.players[B].life_points == 8000


# ----------------------------------------------------------------- Legendary Fiend


def _standby(eng, inst, tp):
    mod = next(m for m in inst.card.continuous if isinstance(m, StandbyTrigger))
    eng._fire_standby_trigger(inst, mod, tp)


def test_legendary_fiend_gains_700_each_standby():
    s = _fresh()
    lf = _spawn(s, "Legendary Fiend", A, 0)  # base 1500
    eng = Engine(s, [Agent(), Agent()])
    _standby(eng, lf, A)
    assert s.effective_attack(lf.iid) == 1500 + 700
    _standby(eng, lf, A)  # accumulates turn over turn (permanent gain)
    assert s.effective_attack(lf.iid) == 1500 + 1400


def test_legendary_fiend_only_on_own_standby():
    s = _fresh()
    lf = _spawn(s, "Legendary Fiend", A, 0)
    eng = Engine(s, [Agent(), Agent()])
    _standby(eng, lf, B)  # opponent's Standby Phase -> no gain
    assert s.effective_attack(lf.iid) == 1500
