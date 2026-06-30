"""Effects Batch 109: Goddess of Whim — a coin-flip ATK gamble.

Once per turn she tosses a coin: a winning call doubles her ATK until the End Phase, a
losing call halves it. Driven by the existing CoinFlip win/lose branches over the new
ScaleSelfAtkTemporary primitive. Coin outcomes are forced here by stubbing the RNG.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext, ScaleSelfAtkTemporary
from ygo.enums import Phase, Position
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


class _Rng:
    """Deterministic stand-in for the seeded RNG: .random() always returns ``val``
    (< 0.5 = heads, >= 0.5 = tails for CoinFlip)."""

    def __init__(self, val):
        self.val = val

    def random(self):
        return self.val


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _run_goddess(s, iid):
    ctx = EffectContext(state=s, controller=A, source_iid=iid)
    for prim in EFFECTS["Goddess of Whim"][0].resolve:
        prim.execute(ctx)


def test_goddess_doubles_on_heads():
    s = _fresh()
    g = _spawn(s, "Goddess of Whim", A, 0)  # base 950
    s.rng = _Rng(0.0)  # heads -> called right
    _run_goddess(s, g.iid)
    assert s.effective_attack(g.iid) == 950 * 2


def test_goddess_halves_on_tails():
    s = _fresh()
    g = _spawn(s, "Goddess of Whim", A, 0)
    s.rng = _Rng(0.9)  # tails -> called wrong
    _run_goddess(s, g.iid)
    assert s.effective_attack(g.iid) == 950 // 2


def test_scale_primitive_is_relative_to_current_atk():
    # The scale is off *current* effective ATK, so a prior boost is included.
    s = _fresh()
    g = _spawn(s, "Goddess of Whim", A, 0)
    g.temp_atk += 50  # nudge current ATK to 1000
    ctx = EffectContext(state=s, controller=A, source_iid=g.iid)
    ScaleSelfAtkTemporary(num=2, den=1).execute(ctx)  # double 1000 -> 2000
    assert s.effective_attack(g.iid) == 2000


def test_goddess_boost_clears_at_end_phase():
    s = _fresh()
    g = _spawn(s, "Goddess of Whim", A, 0)
    s.rng = _Rng(0.0)
    _run_goddess(s, g.iid)
    assert s.effective_attack(g.iid) == 1900
    g.temp_atk = 0  # the End-Phase temp-stat clear resets it to base
    assert s.effective_attack(g.iid) == 950
