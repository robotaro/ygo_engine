"""Effects Batch 78: deck-impact.

Fairy Box reacts to an opponent's attack with a coin toss; on a win the attacking
monster's ATK becomes 0 for the battle (``SetEventAttackerAtkZero``). Darklord Marie
drips 200 LP each of its owner's Standby Phases while in the Graveyard
(``GraveyardStandbyGainLife``, extending the GY-Standby hook). Infinite Dismissal is an
End-Phase floodgate: Level-3-or-lower monsters Normal/Flip Summoned this turn are
destroyed in the End Phase (``EndPhaseSummonSweep``).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _to_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _attack(s, attacker, target):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), s.turn_player)


def _react(eff, s, controller, event):
    ctx = EffectContext(state=s, controller=controller, source_iid=-1, targets=[], event=event)
    for prim in eff.resolve:
        prim.execute(ctx)


class _Rng:
    def __init__(self, val):
        self.val = val

    def random(self):
        return self.val


# ----------------------------------------------------------------------- Fairy Box


def test_fairy_box_zeroes_attacker_on_winning_coin():
    s = _fresh(tp=OPP)
    attacker = _spawn(s, "Summoned Skull", OPP, 0)  # 2500
    s.rng = _Rng(0.0)  # heads -> called it right
    _react(EFFECTS["Fairy Box"][0], s, ME, {"attacker": attacker.iid, "player": OPP})
    assert s.effective_attack(attacker.iid) == 0


def test_fairy_box_does_nothing_on_losing_coin():
    s = _fresh(tp=OPP)
    attacker = _spawn(s, "Summoned Skull", OPP, 0)
    s.rng = _Rng(0.9)  # tails -> called it wrong
    _react(EFFECTS["Fairy Box"][0], s, ME, {"attacker": attacker.iid})
    assert s.effective_attack(attacker.iid) == 2500


def test_fairy_box_zeroed_attacker_loses_the_battle():
    s = _fresh(tp=OPP)
    skull = _spawn(s, "Summoned Skull", OPP, 0)  # 2500
    wall = _spawn(s, "Celtic Guardian", ME, 1)  # 1400
    s.rng = _Rng(0.0)
    _react(EFFECTS["Fairy Box"][0], s, ME, {"attacker": skull.iid})
    _attack(s, skull.iid, wall.iid)  # now 0 ATK vs 1400
    assert skull.zone is Zone.GRAVEYARD
    assert wall.zone is Zone.MONSTER


# ------------------------------------------------------------------- Darklord Marie


def test_darklord_marie_gains_200_each_standby_from_gy():
    s = _fresh(tp=ME, phase=Phase.STANDBY)
    marie = _to_gy(s, "Darklord Marie", ME)
    lp_before = s.players[ME].life_points
    Engine(s, [Agent(), Agent()])._standby_phase(ME)
    assert s.players[ME].life_points == lp_before + 200
    assert marie.zone is Zone.GRAVEYARD  # stays in the GY


def test_darklord_marie_no_gain_on_opponents_standby():
    s = _fresh(tp=ME, phase=Phase.STANDBY)
    _to_gy(s, "Darklord Marie", OPP)  # opponent's copy, on ME's Standby
    lp_before = s.players[OPP].life_points
    Engine(s, [Agent(), Agent()])._standby_phase(ME)
    assert s.players[OPP].life_points == lp_before


# ---------------------------------------------------------------- Infinite Dismissal


def test_infinite_dismissal_destroys_low_level_summons_in_end_phase():
    s = _fresh(tp=ME, phase=Phase.END)
    dis = s.create_instance(reg.get("Infinite Dismissal"), owner=ME, zone=Zone.HAND)
    s.players[ME].hand.append(dis.iid)
    s.place_spell_trap(dis.iid, ME, 0, Position.FACE_UP_ATTACK)
    # Level-1 monster Normal Summoned this turn -> swept.
    low = _spawn(s, "Sinister Serpent", ME, 0)
    low.summoned_this_turn = True
    # Level-6 monster Normal Summoned this turn -> survives (too big).
    big = _spawn(s, "Summoned Skull", ME, 1)
    big.summoned_this_turn = True
    # Level-2 monster Special Summoned this turn -> survives (not a Normal/Flip Summon).
    ss = _spawn(s, "Giant Germ", OPP, 0)
    ss.summoned_this_turn = True
    ss.was_special_summoned = True
    Engine(s, [Agent(), Agent()])._end_phase(ME)
    assert low.zone is Zone.GRAVEYARD
    assert big.zone is Zone.MONSTER
    assert ss.zone is Zone.MONSTER


def test_infinite_dismissal_spares_a_set_monster():
    s = _fresh(tp=ME, phase=Phase.END)
    dis = s.create_instance(reg.get("Infinite Dismissal"), owner=ME, zone=Zone.HAND)
    s.players[ME].hand.append(dis.iid)
    s.place_spell_trap(dis.iid, ME, 0, Position.FACE_UP_ATTACK)
    # A face-down Set Level-1 monster has not been Summoned -> spared.
    setmon = _spawn(s, "Sinister Serpent", ME, 0, pos=Position.FACE_DOWN_DEFENSE)
    setmon.summoned_this_turn = False
    Engine(s, [Agent(), Agent()])._end_phase(ME)
    assert setmon.zone is Zone.MONSTER
