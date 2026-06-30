"""Effects Batch 113: Rocket Warrior — attack with impunity + weaken the target.

During its controller's Battle Phase it cannot be destroyed by battle and its controller
takes no battle damage from battles involving it (SafeAttacker); after it attacks a monster
that target loses 500 ATK until end of turn (DebuffsAttackTargetAtk). While it *defends* on
the opponent's turn it gets none of this protection.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1
BIG = "Summoned Skull"  # 2500 ATK — bigger than Rocket Warrior's 1500


def _battle(tp=A):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


# ----------------------------------------------- clauses 1 & 2: attack with impunity


def test_rocket_survives_attacking_a_bigger_monster():
    s = _battle(tp=A)
    rocket = _spawn(s, "Rocket Warrior", A, 0)
    skull = _spawn(s, BIG, B, 0)
    apply(s, DeclareAttack(rocket.iid, skull.iid))
    assert rocket.zone is Zone.MONSTER  # not destroyed by the bigger monster
    assert rocket.iid in s.players[A].monster_zones


def test_rocket_controller_takes_no_battle_damage_attacking():
    s = _battle(tp=A)
    rocket = _spawn(s, "Rocket Warrior", A, 0)
    skull = _spawn(s, BIG, B, 0)
    apply(s, DeclareAttack(rocket.iid, skull.iid))
    assert s.players[A].life_points == 8000  # would have lost 1000 without SafeAttacker


# ----------------------------------------------- clause 3: target loses 500 ATK


def test_attack_target_loses_500_atk():
    s = _battle(tp=A)
    rocket = _spawn(s, "Rocket Warrior", A, 0)
    skull = _spawn(s, BIG, B, 0)
    eng = Engine(s, [Agent(), Agent()])
    apply(s, DeclareAttack(rocket.iid, skull.iid))
    eng._apply_attacker_target_debuff()  # the engine step that reads battle_pair
    assert s.effective_attack(skull.iid) == 2500 - 500


# ----------------------------------------------- defending: no protection


def test_rocket_is_destroyed_when_attacked_on_opponents_turn():
    s = _battle(tp=B)  # the opponent's Battle Phase
    rocket = _spawn(s, "Rocket Warrior", A, 0)
    skull = _spawn(s, BIG, B, 0)
    assert not s.is_battle_indestructible(rocket.iid)  # SafeAttacker is dormant off-turn
    apply(s, DeclareAttack(skull.iid, rocket.iid))
    assert rocket.zone is not Zone.MONSTER  # destroyed by the bigger attacker
    assert s.players[A].life_points == 8000 - 1000  # and A takes the battle damage


def test_predicates_track_own_battle_phase():
    s = _battle(tp=A)
    rocket = _spawn(s, "Rocket Warrior", A, 0)
    assert s.is_battle_indestructible(rocket.iid)
    assert s.attacker_takes_no_self_battle_damage(rocket.iid)
    assert s.attacker_target_debuff(rocket.iid) == 500
    s.turn_player = B  # now it's the opponent's turn
    assert not s.is_battle_indestructible(rocket.iid)
    assert not s.attacker_takes_no_self_battle_damage(rocket.iid)
