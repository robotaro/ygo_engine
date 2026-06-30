"""Effects Batch 114: Sebek's Blessing — gain LP equal to direct battle damage.

A Quick-Play gated on having inflicted direct battle damage this turn
(state.direct_damage_dealt_this_turn, set in _resolve_attack on a direct hit), gaining
that much LP via the DirectBattleDamageThisTurn value source. Only direct attacks count.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import DirectBattleDamageThisTurn, EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position
from ygo.moves import DeclareAttack, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1
SEBEK = EFFECTS["Sebek's Blessing"][0]


def _battle(tp=A):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def test_direct_attack_records_damage():
    s = _battle(A)
    skull = _spawn(s, "Summoned Skull", A, 0)  # 2500
    apply(s, DeclareAttack(skull.iid, None))  # direct attack
    assert s.direct_damage_dealt_this_turn == 2500
    assert s.players[B].life_points == 8000 - 2500


def test_attacking_a_monster_is_not_a_direct_hit():
    s = _battle(A)
    skull = _spawn(s, "Summoned Skull", A, 0)  # 2500
    celtic = _spawn(s, "Celtic Guardian", B, 0)  # 1400 — breaking it deals 1100 to B
    apply(s, DeclareAttack(skull.iid, celtic.iid))
    assert s.players[B].life_points == 8000 - 1100  # the excess still hurts
    assert s.direct_damage_dealt_this_turn == 0  # but it is not "direct" damage


def test_condition_gates_on_a_direct_hit():
    s = _battle(A)
    assert not SEBEK.condition(s, A)  # nothing dealt yet
    skull = _spawn(s, "Summoned Skull", A, 0)
    apply(s, DeclareAttack(skull.iid, None))
    assert SEBEK.condition(s, A)  # now a direct hit has landed


def test_sebeks_gains_lp_equal_to_direct_damage():
    s = _battle(A)
    skull = _spawn(s, "Summoned Skull", A, 0)
    apply(s, DeclareAttack(skull.iid, None))  # 2500 direct
    before = s.players[A].life_points
    ctx = EffectContext(state=s, controller=A, source_iid=skull.iid)
    assert DirectBattleDamageThisTurn().value(ctx) == 2500
    for prim in SEBEK.resolve:
        prim.execute(ctx)
    assert s.players[A].life_points == before + 2500


def test_record_resets_at_turn_start():
    s = _battle(A)
    skull = _spawn(s, "Summoned Skull", A, 0)
    apply(s, DeclareAttack(skull.iid, None))
    assert s.direct_damage_dealt_this_turn == 2500
    Engine(s, [Agent(), Agent()])._begin_turn(B)  # the next turn begins
    assert s.direct_damage_dealt_this_turn == 0
    assert not SEBEK.condition(s, B)
