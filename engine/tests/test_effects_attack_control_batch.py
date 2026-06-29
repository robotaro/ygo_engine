"""Effects Batch 49: take-control-the-attack + battle-damage reflection.

Magical Arm Shield reuses TakeControl(until_end_of_turn) + RedirectAttackToTarget
(plus a new TargetSpec.exclude_attacker so it can't grab the attacker itself) to steal
a monster and make the attacker battle it. Dimension Wall sets state.reflect_battle_damage
(new), read by moves._resolve_attack so the defender's battle damage hits the attacker.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()

ATTACKER, DEFENDER = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ATTACKER, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _set_trap(s, name, player=DEFENDER):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _event(attacker_iid, target_iid=None):
    return {"kind": "attack_declared", "player": ATTACKER, "attacker": attacker_iid, "target": target_iid}


class _ActivateTrap(Agent):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def respond(self, state, options, event):
        for opt in options:
            if opt.iid in state.cards and state.inst(opt.iid).card.name == self.name:
                return opt
        return None


# --------------------------------------------------------------------------- #
#  Dimension Wall
# --------------------------------------------------------------------------- #
def test_dimension_wall_reflects_direct_damage():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500, attacks directly
    _set_trap(s, "Dimension Wall")
    eng = Engine(s, [Agent(), _ActivateTrap("Dimension Wall")])
    eng._declare_attack(DeclareAttack(atk.iid, None), ATTACKER)
    assert s.players[DEFENDER].life_points == 8000  # the defender takes nothing
    assert s.players[ATTACKER].life_points == 8000 - 2500  # the attacker takes it instead


def test_dimension_wall_reflects_combat_difference():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500
    weak = _spawn(s, "Celtic Guardian", DEFENDER, 0)  # 1400 -> dies, diff 1100
    _set_trap(s, "Dimension Wall")
    eng = Engine(s, [Agent(), _ActivateTrap("Dimension Wall")])
    eng._declare_attack(DeclareAttack(atk.iid, weak.iid), ATTACKER)
    assert s.inst(weak.iid).zone is Zone.GRAVEYARD
    assert s.players[DEFENDER].life_points == 8000  # the 1100 difference is reflected
    assert s.players[ATTACKER].life_points == 8000 - 1100


def test_battle_damage_normal_without_dimension_wall():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(atk.iid, None), ATTACKER)
    assert s.players[DEFENDER].life_points == 8000 - 2500  # normal direct hit


# --------------------------------------------------------------------------- #
#  Magical Arm Shield
# --------------------------------------------------------------------------- #
def test_magical_arm_shield_excludes_the_attacker_from_targets():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    _spawn(s, "Celtic Guardian", ATTACKER, 1)  # a second opponent monster
    _spawn(s, "Mystical Elf", DEFENDER, 0)  # the defender controls a monster (gate)
    trap = _set_trap(s, "Magical Arm Shield")
    opts = response_options(s, DEFENDER, _event(atk.iid), 2)
    targets = {a.targets[0] for a in opts if a.iid == trap.iid}
    assert atk.iid not in targets  # never offered the attacker
    assert targets  # but the other opponent monster is offered


def test_magical_arm_shield_steals_and_redirects():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500, attacks directly
    prey = _spawn(s, "Celtic Guardian", ATTACKER, 1)  # 1400 -> stolen, then battled
    _spawn(s, "Mystical Elf", DEFENDER, 0)
    _set_trap(s, "Magical Arm Shield")
    eng = Engine(s, [Agent(), _ActivateTrap("Magical Arm Shield")])
    eng._declare_attack(DeclareAttack(atk.iid, None), ATTACKER)
    # The stolen monster was destroyed by the attacker (control had moved to the defender),
    # so the defender took only the 1100 combat difference, not the full 2500 direct hit.
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD
    assert s.players[DEFENDER].life_points == 8000 - 1100
    assert s.inst(prey.iid).owner == ATTACKER  # ownership unchanged; only control moved


def test_magical_arm_shield_not_offered_without_a_monster():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    _spawn(s, "Celtic Guardian", ATTACKER, 1)
    trap = _set_trap(s, "Magical Arm Shield")  # defender controls no monster
    opts = response_options(s, DEFENDER, _event(atk.iid), 2)
    assert not any(a.iid == trap.iid for a in opts)
