"""Effects Batch 98: Susa Soldier.

Three printed static abilities, carried as continuous riders:
- cannot be Special Summoned;
- returns to its owner's hand during the End Phase of the turn it is Normal Summoned or
  flipped face-up (a Spirit-like bounce);
- the battle damage it inflicts to the opponent is halved.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


# ----------------------------------------------------------- cannot be Special Summoned


def test_susa_cannot_be_special_summoned():
    s = _fresh()
    susa = _in_gy(s, "Susa Soldier", A)
    ok = s.special_summon(susa.iid, A, Position.FACE_UP_ATTACK)
    assert ok is False  # the printed restriction blocks every SS route
    assert s.inst(susa.iid).zone is Zone.GRAVEYARD  # still in the GY


def test_a_normal_monster_can_still_be_special_summoned():
    s = _fresh()
    fish = _in_gy(s, "7 Colored Fish", A)
    assert s.special_summon(fish.iid, A, Position.FACE_UP_ATTACK) is True


# --------------------------------------------------------------- End-Phase self-bounce


def test_susa_returns_to_hand_at_end_phase():
    s = _fresh(tp=A)
    susa = _spawn(s, "Susa Soldier", A, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._return_spirits(A)
    assert s.inst(susa.iid).zone is Zone.HAND  # bounced back to its owner's hand
    assert s.players[A].monster_zones[0] is None


def test_a_plain_monster_does_not_self_bounce():
    s = _fresh(tp=A)
    fish = _spawn(s, "7 Colored Fish", A, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._return_spirits(A)
    assert s.inst(fish.iid).zone is Zone.MONSTER  # stays on the field


# ----------------------------------------------------------------- halved battle damage


def test_susa_inflicts_half_battle_damage_direct():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    susa = _spawn(s, "Susa Soldier", A, 0)  # 2000 ATK
    s.players[B].life_points = 8000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(susa.iid, None), A)  # direct attack
    assert s.players[B].life_points == 8000 - 1000  # 2000 halved to 1000


def test_susa_inflicts_half_battle_damage_over_a_monster():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    susa = _spawn(s, "Susa Soldier", A, 0)  # 2000 ATK
    foe = _spawn(s, "Petit Moth", B, 0)  # 300 ATK -> 1700 excess, halved to 850
    s.players[B].life_points = 8000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(susa.iid, foe.iid), A)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # destroyed in battle
    assert s.players[B].life_points == 8000 - 850  # (2000-300)//2
