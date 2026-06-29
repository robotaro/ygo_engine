"""Effects Batch 71: "switch to Defense after attacking" family (DefenseAfterAttack).

A monster with a ``DefenseAfterAttack`` rider is changed to Defense Position once its
attack resolves (Spear Dragon, Axe Dragonute, the Goblin Attack Force family); the
``lock_position`` variants additionally freeze it in Defense until their controller's
next turn. The switch is applied at the tail of ``engine._declare_attack``; the lock is
read by the Main-Phase position-change enumeration.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ChangePosition, DeclareAttack, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _attack(s, attacker, target=None):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), s.turn_player)


def _can_change_position(s, iid):
    return any(isinstance(a, ChangePosition) and a.iid == iid for a in legal_actions(s, ME))


def test_spear_dragon_switches_to_defense_after_attacking():
    s = _fresh(ME)
    spear = _spawn(s, "Spear Dragon", ME, 0)  # direct attack, then auto-switch
    _attack(s, spear.iid, None)
    assert spear.position is Position.FACE_UP_DEFENSE
    assert spear.position_locked_until is None  # Spear Dragon has no position lock
    assert s.players[OPP].life_points == 8000 - 1900  # the direct attack still landed


def test_spear_dragon_keeps_its_piercing_rider():
    from ygo.effects import DefenseAfterAttack, Piercing

    mods = reg.get("Spear Dragon").continuous
    assert any(isinstance(m, Piercing) for m in mods)
    assert any(isinstance(m, DefenseAfterAttack) for m in mods)


def test_monster_without_rider_stays_in_attack():
    s = _fresh(ME)
    skull = _spawn(s, "Summoned Skull", ME, 0)
    _attack(s, skull.iid, None)
    assert skull.position is Position.FACE_UP_ATTACK


def test_goblin_attack_force_locks_position_until_next_turn():
    s = _fresh(ME)
    goblin = _spawn(s, "Goblin Attack Force", ME, 0)
    _attack(s, goblin.iid, None)
    assert goblin.position is Position.FACE_UP_DEFENSE
    assert goblin.position_locked_until == s.turn_count + 2
    # A later turn still inside the lock window: no position change offered.
    s.phase = Phase.MAIN_1
    goblin.summoned_this_turn = False
    goblin.position_changed_this_turn = False
    s.turn_count = goblin.position_locked_until
    assert not _can_change_position(s, goblin.iid)
    # Once turn_count passes the deadline, the lock lifts.
    s.turn_count = goblin.position_locked_until + 1
    assert _can_change_position(s, goblin.iid)


def test_goblin_black_ops_keeps_direct_attack_and_gains_the_drawback():
    # Previously half-authored (direct-attack only); now also switches to Defense + locks.
    from ygo.effects import CanAttackDirectly, DefenseAfterAttack

    mods = reg.get("Goblin Black Ops").continuous
    assert any(isinstance(m, CanAttackDirectly) for m in mods)
    lock = next((m for m in mods if isinstance(m, DefenseAfterAttack)), None)
    assert lock is not None and lock.lock_position


def test_switch_is_a_noop_when_attacker_dies_in_battle():
    s = _fresh(ME)
    spear = _spawn(s, "Spear Dragon", ME, 0)  # 1900 ATK
    wall = _spawn(s, "Summoned Skull", OPP, 0)  # 2500 ATK -> Spear loses
    _attack(s, spear.iid, wall.iid)
    assert spear.zone is Zone.GRAVEYARD  # destroyed; the after-attack switch no-ops safely
