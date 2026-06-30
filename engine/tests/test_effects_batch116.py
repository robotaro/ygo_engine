"""Effects Batch 116: Skull Dice / Graceful Dice — roll a die, swing ATK/DEF by 100×result.

Skull Dice drops the opponent's monsters; Graceful Dice pumps yours; both last until the End
Phase (temp-stat layer). The die roll is forced here by stubbing the RNG.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.enums import Phase, Position
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


class _Die:
    """RNG stub: randint always returns ``val`` (a fixed die result)."""

    def __init__(self, val):
        self.val = val

    def randint(self, a, b):
        return self.val


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _resolve(s, name, controller=A):
    ctx = EffectContext(state=s, controller=controller, source_iid=0)
    for prim in EFFECTS[name][0].resolve:
        prim.execute(ctx)


def test_skull_dice_weakens_opponents_monsters():
    s = _fresh()
    mine = _spawn(s, "Celtic Guardian", A, 0)  # 1400 — A's own monster
    foe = _spawn(s, "Summoned Skull", B, 0)  # 2500 / 1200
    s.rng = _Die(4)
    _resolve(s, "Skull Dice", controller=A)
    assert s.effective_attack(foe.iid) == 2500 - 400  # opponent loses 100 × 4
    assert s.effective_defense(foe.iid) == 1200 - 400
    assert s.effective_attack(mine.iid) == 1400  # A's own board untouched


def test_graceful_dice_pumps_your_monsters():
    s = _fresh()
    mine = _spawn(s, "Celtic Guardian", A, 0)  # 1400 / 1200
    foe = _spawn(s, "Summoned Skull", B, 0)
    s.rng = _Die(3)
    _resolve(s, "Graceful Dice", controller=A)
    assert s.effective_attack(mine.iid) == 1400 + 300
    assert s.effective_defense(mine.iid) == 1200 + 300
    assert s.effective_attack(foe.iid) == 2500  # opponent untouched


def test_skull_dice_floors_at_zero():
    s = _fresh()
    foe = _spawn(s, "Petit Moth", B, 0)  # 300 ATK
    s.rng = _Die(6)  # -600 -> floored to 0
    _resolve(s, "Skull Dice", controller=A)
    assert s.effective_attack(foe.iid) == 0


def test_dice_swing_is_temporary():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", B, 0)
    s.rng = _Die(5)
    _resolve(s, "Skull Dice", controller=A)
    assert s.effective_attack(foe.iid) == 2500 - 500
    foe.temp_atk = 0  # the End-Phase temp clear
    assert s.effective_attack(foe.iid) == 2500
