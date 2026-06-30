"""Effects Batch 75: deck-impact mechanisms.

D.D. Warrior Lady fires a "battles an opponent's monster" Trigger (new ``kind``,
recorded in ``state.battle_pair``) and mutually banishes both combatants — whether or
not either was destroyed, so it banishes itself even from the Graveyard. Sinister
Serpent carries a ``GraveyardStandbyReturn`` marker the Standby hook reads off the GY to
add it back to the hand. Elegant Egotist conditionally Special Summons a "Harpie Lady"
(or Harpie Lady Sisters) from the Deck while a Harpie Lady is on the field.
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


def _to_deck_top(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)  # end of list == top of deck
    return inst


def _attack(s, attacker, target):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), s.turn_player)


def _resolve(effect, s, controller, source_iid=-1, targets=()):
    ctx = EffectContext(
        state=s, controller=controller, source_iid=source_iid, targets=list(targets)
    )
    for prim in effect.resolve:
        prim.execute(ctx)


# ------------------------------------------------------------- D.D. Warrior Lady


def test_dd_warrior_lady_banishes_both_after_winning_battle():
    s = _fresh(tp=ME)
    ddwl = _spawn(s, "D.D. Warrior Lady", ME, 0)  # 1500
    prey = _spawn(s, "Celtic Guardian", OPP, 0)  # 1400 ATK -> destroyed
    _attack(s, ddwl.iid, prey.iid)
    assert ddwl.zone is Zone.BANISHED
    assert prey.zone is Zone.BANISHED


def test_dd_warrior_lady_banishes_both_even_when_it_loses():
    s = _fresh(tp=ME)
    ddwl = _spawn(s, "D.D. Warrior Lady", ME, 0)  # 1500, destroyed by Skull
    boss = _spawn(s, "Summoned Skull", OPP, 0)  # 2500 ATK, survives the battle
    _attack(s, ddwl.iid, boss.iid)
    # It banishes itself from the GY and banishes the survivor from the field.
    assert ddwl.zone is Zone.BANISHED
    assert boss.zone is Zone.BANISHED


def test_dd_warrior_lady_banishes_when_attacked_on_defense():
    s = _fresh(tp=OPP)  # opponent's Battle Phase; they attack D.D. Warrior Lady
    ddwl = _spawn(s, "D.D. Warrior Lady", ME, 0, pos=Position.FACE_UP_DEFENSE)  # DEF 1600
    raider = _spawn(s, "Summoned Skull", OPP, 0)  # 2500 ATK breaks the wall
    _attack(s, raider.iid, ddwl.iid)
    assert ddwl.zone is Zone.BANISHED
    assert raider.zone is Zone.BANISHED


def test_dd_warrior_lady_does_not_trigger_on_a_direct_attack():
    s = _fresh(tp=ME)
    ddwl = _spawn(s, "D.D. Warrior Lady", ME, 0)  # 1500 attacks directly (no monster)
    _attack(s, ddwl.iid, None)
    assert ddwl.zone is Zone.MONSTER  # no monster fought -> no banish


# --------------------------------------------------------------- Sinister Serpent


def test_sinister_serpent_returns_from_gy_on_your_standby():
    s = _fresh(tp=ME, phase=Phase.STANDBY)
    serp = _to_gy(s, "Sinister Serpent", ME)
    Engine(s, [Agent(), Agent()])._standby_phase(ME)
    assert serp.zone is Zone.HAND
    assert serp.iid in s.players[ME].hand


def test_sinister_serpent_stays_in_gy_on_opponents_standby():
    s = _fresh(tp=ME, phase=Phase.STANDBY)
    serp = _to_gy(s, "Sinister Serpent", OPP)  # opponent's copy, on ME's Standby
    Engine(s, [Agent(), Agent()])._standby_phase(ME)
    assert serp.zone is Zone.GRAVEYARD


def test_sinister_serpent_returns_only_one_per_standby():
    s = _fresh(tp=ME, phase=Phase.STANDBY)
    a = _to_gy(s, "Sinister Serpent", ME)
    b = _to_gy(s, "Sinister Serpent", ME)
    Engine(s, [Agent(), Agent()])._standby_phase(ME)
    returned = [i for i in (a, b) if i.zone is Zone.HAND]
    assert len(returned) == 1  # "once per turn"


# --------------------------------------------------------------- Elegant Egotist


def test_elegant_egotist_summons_harpie_from_deck():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    _spawn(s, "Harpie Lady", ME, 0)  # the required on-field "Harpie Lady"
    sisters = _to_deck_top(s, "Harpie Lady Sisters", ME)
    eff = EFFECTS["Elegant Egotist"][0]
    assert eff.condition(s, ME) is True
    _resolve(eff, s, ME)
    assert sisters.zone is Zone.MONSTER
    assert sisters.controller == ME


def test_elegant_egotist_condition_false_without_a_harpie_lady():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    _to_deck_top(s, "Harpie Lady Sisters", ME)
    # Sisters on the field does NOT satisfy "a Harpie Lady is on the field".
    _spawn(s, "Summoned Skull", ME, 0)
    eff = EFFECTS["Elegant Egotist"][0]
    assert eff.condition(s, ME) is False
