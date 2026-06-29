"""Effects Batch 47: coin-flip (CoinFlip RNG primitive).

CoinFlip tosses ``count`` coins via the seeded RNG and runs the ``win`` branch if
heads >= ``win_threshold``, else ``lose``. "Toss a coin and call it" is a single
heads (calling is 50/50 with no info); "toss 3 times, 2+ heads" is count=3/threshold=2.
Also: a new engine._fire_attack_declared_trigger hook fires an attacker's own "when
this declares an attack" Trigger (Jirai Gumo). Cards: Jirai Gumo, Abare Ushioni,
Cup of Ace, Barrel Dragon, Blowback Dragon.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import CoinFlip, Draw, Effect, InflictDamage, LoseHalfLifePoints
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, ActivateSpell, resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()

SELF, OPPONENT = "self", "opponent"


class _Coins:
    """A stub RNG: random() returns queued values (so <0.5 == heads is controllable)."""

    def __init__(self, vals):
        self.vals = list(vals)

    def random(self):
        return self.vals.pop(0)

    def shuffle(self, seq):  # passthrough so deck ops don't blow up
        pass


HEADS, TAILS = 0.1, 0.9


def _fresh(turn_player=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, turn_player, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


# --------------------------------------------------------------------------- #
#  Primitives
# --------------------------------------------------------------------------- #
def test_coin_flip_runs_win_on_heads_lose_on_tails():
    s = _fresh()
    src = _spawn(s, "Celtic Guardian", 0, 4)
    eff = Effect(resolve=(CoinFlip(win=(InflictDamage(OPPONENT, 1000),), lose=(InflictDamage(SELF, 1000),)),))
    s.rng = _Coins([HEADS])
    resolve_effect(s, eff, src.iid, (), None)
    assert s.players[1].life_points == 7000 and s.players[0].life_points == 8000
    s.rng = _Coins([TAILS])
    resolve_effect(s, eff, src.iid, (), None)
    assert s.players[0].life_points == 7000


def test_coin_flip_three_tosses_threshold():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", 1, 0)
    from ygo.effects import DestroyTargets

    eff = Effect(resolve=(CoinFlip(win=(DestroyTargets(),), count=3, win_threshold=2),))
    s.rng = _Coins([HEADS, TAILS, HEADS])  # 2 heads -> win
    resolve_effect(s, eff, 0, (foe.iid,), None)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD


def test_coin_flip_three_tosses_below_threshold():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", 1, 0)
    from ygo.effects import DestroyTargets

    eff = Effect(resolve=(CoinFlip(win=(DestroyTargets(),), count=3, win_threshold=2),))
    s.rng = _Coins([HEADS, TAILS, TAILS])  # 1 head -> lose
    resolve_effect(s, eff, 0, (foe.iid,), None)
    assert s.inst(foe.iid).zone is Zone.MONSTER


def test_lose_half_life_points():
    s = _fresh()
    src = _spawn(s, "Celtic Guardian", 0, 4)
    resolve_effect(s, Effect(resolve=(LoseHalfLifePoints(SELF),)), src.iid, (), None)
    assert s.players[0].life_points == 4000


# --------------------------------------------------------------------------- #
#  Cards
# --------------------------------------------------------------------------- #
def test_jirai_gumo_loses_half_lp_on_wrong_call():
    s = _fresh(phase=Phase.BATTLE)
    gumo = _spawn(s, "Jirai Gumo", 0, 0)
    eng = Engine(s, [Agent(), Agent()])
    s.rng = _Coins([HEADS])  # right -> no loss
    eng._fire_attack_declared_trigger(gumo.iid)
    assert s.players[0].life_points == 8000
    s.rng = _Coins([TAILS])  # wrong -> lose half
    eng._fire_attack_declared_trigger(gumo.iid)
    assert s.players[0].life_points == 4000


def test_abare_ushioni_burns_by_coin():
    s = _fresh()
    ushi = _spawn(s, "Abare Ushioni", 0, 0)
    eng = Engine(s, [Agent(), Agent()])
    s.rng = _Coins([HEADS])  # right -> 1000 to opponent
    eng._activate_monster_effect(ActivateMonsterEffect(ushi.iid, targets=()), 0)
    assert s.players[1].life_points == 7000


def test_cup_of_ace_draws_by_coin():
    s = _fresh()
    for owner in (0, 1):
        for _ in range(3):
            inst = s.create_instance(reg.get("Celtic Guardian"), owner=owner, zone=Zone.DECK)
            s.players[owner].deck.append(inst.iid)
    cup = s.create_instance(reg.get("Cup of Ace"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(cup.iid)
    idx = next(i for i, z in enumerate(s.players[0].spell_trap_zones) if z is None)
    s.place_spell_trap(cup.iid, 0, idx, Position.FACE_DOWN)
    cup.set_on_turn = s.turn_count - 1
    s.rng = _Coins([HEADS])  # heads -> I draw 2
    before = len(s.players[0].hand)  # Cup already in the S/T zone, not the hand
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(cup.iid), 0)
    assert len(s.players[0].hand) == before + 2  # drew 2


def test_barrel_dragon_destroys_on_two_heads():
    s = _fresh()
    barrel = _spawn(s, "Barrel Dragon", 0, 0)
    foe = _spawn(s, "Gemini Elf", 1, 0)
    s.rng = _Coins([HEADS, HEADS, TAILS])  # 2 heads -> destroy
    Engine(s, [Agent(), Agent()])._activate_monster_effect(
        ActivateMonsterEffect(barrel.iid, targets=(foe.iid,)), 0
    )
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD
