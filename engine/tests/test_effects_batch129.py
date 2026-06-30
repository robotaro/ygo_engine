"""Effects Batch 129: Reverse Trap.

"Until the End Phase, all effects that add or subtract ATK or DEF are reversed." A quick Trap:
ReverseStatChangesThisTurn stamps a turn-scoped global flag; _effective_stat negates the summed
additive modifier layer while it is active, leaving the printed base (and the Mirror Wall
halving, a multiplication) untouched.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _activate_reverse(s, controller=A):
    ctx = EffectContext(state=s, controller=controller, source_iid=-1, targets=[])
    for prim in EFFECTS["Reverse Trap"][0].resolve:
        prim.execute(ctx)


def test_reverses_a_positive_temp_modifier():
    s = _fresh()
    m = _spawn(s, "Celtic Guardian", A, 0)  # base 1400
    m.temp_atk += 600  # normally 2000
    assert s.effective_attack(m.iid) == 2000
    _activate_reverse(s)
    assert s.effective_attack(m.iid) == 1400 - 600  # 800


def test_reverses_a_negative_temp_modifier():
    s = _fresh()
    m = _spawn(s, "Celtic Guardian", A, 0)
    m.temp_atk -= 500  # normally 900
    _activate_reverse(s)
    assert s.effective_attack(m.iid) == 1400 + 500  # 1900


def test_reverses_an_equip_boost():
    s = _fresh()
    m = _spawn(s, "Celtic Guardian", A, 0)
    axe = s.create_instance(reg.get("Axe of Despair"), owner=A, zone=Zone.DECK)  # +1000
    s.players[A].deck.append(axe.iid)
    s.place_spell_trap(axe.iid, A, 0, Position.FACE_UP_ATTACK)
    axe.equipped_to = m.iid
    assert s.effective_attack(m.iid) == 2400
    _activate_reverse(s)
    assert s.effective_attack(m.iid) == 1400 - 1000  # 400


def test_base_unaffected_and_floors_at_zero():
    s = _fresh()
    m = _spawn(s, "Celtic Guardian", A, 0)
    _activate_reverse(s)
    assert s.effective_attack(m.iid) == 1400  # no modifiers -> base unchanged
    m.temp_atk += 2000  # reversed -> 1400 - 2000 = -600 -> floored
    assert s.effective_attack(m.iid) == 0


def test_lapses_when_the_turn_advances():
    s = _fresh()
    m = _spawn(s, "Celtic Guardian", A, 0)
    m.temp_atk += 600
    _activate_reverse(s)
    assert s.effective_attack(m.iid) == 800
    s.turn_count += 1
    assert s.effective_attack(m.iid) == 2000  # reversal gone
