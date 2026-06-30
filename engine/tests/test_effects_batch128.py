"""Effects Batch 128: Dragon Capture Jar.

Continuous Trap: its activation flips every face-up Dragon (both sides) to Defense Position
(ChangeAllPositions(race="Dragon")); while it stays face-up the RacePositionLock("Dragon")
floodgate bars any Dragon from changing its battle position.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.enums import Phase, Position, Zone
from ygo.moves import ChangePosition, FlipSummon, _main_phase_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _place_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def _activate(s, jar, controller):
    ctx = EffectContext(state=s, controller=controller, source_iid=jar.iid, targets=[])
    for prim in EFFECTS["Dragon Capture Jar"][0].resolve:
        prim.execute(ctx)


def test_activation_flips_all_dragons_to_defense_both_sides():
    s = _fresh()
    my_dragon = _spawn(s, "Luster Dragon", A, 0, Position.FACE_UP_ATTACK)
    foe_dragon = _spawn(s, "Kaiser Glider", B, 0, Position.FACE_UP_ATTACK)
    non_dragon = _spawn(s, "Summoned Skull", A, 1, Position.FACE_UP_ATTACK)
    jar = _place_st(s, "Dragon Capture Jar", A)
    _activate(s, jar, A)
    assert my_dragon.position is Position.FACE_UP_DEFENSE
    assert foe_dragon.position is Position.FACE_UP_DEFENSE
    assert non_dragon.position is Position.FACE_UP_ATTACK  # untouched


def test_dragons_position_is_locked_while_jar_is_face_up():
    s = _fresh()
    dragon = _spawn(s, "Luster Dragon", A, 0, Position.FACE_UP_DEFENSE)
    non_dragon = _spawn(s, "Summoned Skull", A, 1, Position.FACE_UP_ATTACK)
    jar = _place_st(s, "Dragon Capture Jar", A)
    assert s.monster_position_locked(dragon.iid) is True
    assert s.monster_position_locked(non_dragon.iid) is False
    # The Dragon is not offered a position change; the non-Dragon is.
    changers = {a.iid for a in _main_phase_actions(s, A) if isinstance(a, (ChangePosition, FlipSummon))}
    assert dragon.iid not in changers
    assert non_dragon.iid in changers


def test_lock_lifts_when_the_jar_is_face_down_or_negated():
    s = _fresh()
    dragon = _spawn(s, "Luster Dragon", A, 0, Position.FACE_UP_DEFENSE)
    jar = _place_st(s, "Dragon Capture Jar", A)
    assert s.monster_position_locked(dragon.iid) is True
    jar.position = Position.FACE_DOWN  # set face-down -> floodgate off
    assert s.monster_position_locked(dragon.iid) is False
