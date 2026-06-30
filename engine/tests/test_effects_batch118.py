"""Effects Batch 118: Mirror Wall halves opponent attackers' ATK.

A Continuous Trap: every opponent monster that attacks while it is face-up has its ATK
halved for as long as the Wall stays on the field. (The pay-2000-each-Standby cost is the
existing StandbyUpkeep infra.)
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import HalvesAttackersAtk, StandbyUpkeep
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _battle(tp=A):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _mirror_wall(s, player):
    inst = s.create_instance(reg.get("Mirror Wall"), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def test_mirror_wall_halves_the_attack_and_keeps_it_halved():
    s = _battle(tp=A)
    skull = _spawn(s, "Summoned Skull", A, 0)  # 2500
    _mirror_wall(s, B)  # the defender's Mirror Wall
    apply(s, DeclareAttack(skull.iid, None))  # direct attack
    assert s.players[B].life_points == 8000 - 1250  # halved battle damage
    assert skull.atk_halved_by_wall
    assert s.effective_attack(skull.iid) == 1250  # stays halved while the Wall is up


def test_halving_lifts_when_mirror_wall_leaves():
    s = _battle(tp=A)
    skull = _spawn(s, "Summoned Skull", A, 0)
    wall = _mirror_wall(s, B)
    apply(s, DeclareAttack(skull.iid, None))
    assert s.effective_attack(skull.iid) == 1250
    s.send_to_graveyard(wall.iid)  # Mirror Wall destroyed
    assert s.effective_attack(skull.iid) == 2500  # halving lifts with the Wall gone


def test_no_mirror_wall_no_halving():
    s = _battle(tp=A)
    skull = _spawn(s, "Summoned Skull", A, 0)
    apply(s, DeclareAttack(skull.iid, None))
    assert not skull.atk_halved_by_wall
    assert s.effective_attack(skull.iid) == 2500


def test_mirror_wall_spares_its_controllers_own_attackers():
    s = _battle(tp=B)  # B's turn; B both owns the Wall and attacks
    b_skull = _spawn(s, "Summoned Skull", B, 0)
    _mirror_wall(s, B)
    apply(s, DeclareAttack(b_skull.iid, None))
    assert not b_skull.atk_halved_by_wall  # only the OPPONENT's attackers are caught
    assert s.effective_attack(b_skull.iid) == 2500


def test_mirror_wall_carries_the_standby_pay_cost():
    wall = reg.get("Mirror Wall")
    ups = [m for m in wall.continuous if isinstance(m, StandbyUpkeep)]
    assert any(m.pay_life == 2000 for m in ups)
    assert any(isinstance(m, HalvesAttackersAtk) for m in wall.continuous)
