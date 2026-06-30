"""Effects Batch 119: Spellbinding Circle locks a targeted opponent monster.

A Continuous Trap that attaches to 1 opponent monster (equipped_to) and bars it from
attacking or changing battle position, until the Circle leaves or the monster is destroyed
(the engine's orphan-equip cleanup handles the latter).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ChangePosition, DeclareAttack, _battle_phase_actions, _main_phase_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _place_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def test_activation_attaches_and_locks():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", B, 0)
    circle = _place_st(s, "Spellbinding Circle", A)
    ctx = EffectContext(state=s, controller=A, source_iid=circle.iid, targets=[foe.iid])
    for prim in EFFECTS["Spellbinding Circle"][0].resolve:
        prim.execute(ctx)
    assert circle.equipped_to == foe.iid
    assert s.monster_attack_locked(foe.iid)
    assert s.monster_position_locked(foe.iid)


def test_locked_monster_cannot_attack():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", B, 0)
    other = _spawn(s, "Celtic Guardian", B, 1)  # an unlocked ally that still may attack
    circle = _place_st(s, "Spellbinding Circle", A)
    circle.equipped_to = foe.iid
    s.turn_player, s.phase = B, Phase.BATTLE
    attackers = {a.attacker for a in _battle_phase_actions(s, B) if isinstance(a, DeclareAttack)}
    assert foe.iid not in attackers
    assert other.iid in attackers


def test_locked_monster_cannot_change_position():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", B, 0)
    foe.summoned_this_turn = False  # otherwise eligible to change position
    circle = _place_st(s, "Spellbinding Circle", A)
    circle.equipped_to = foe.iid
    s.turn_player, s.phase = B, Phase.MAIN_1
    changes = {a.iid for a in _main_phase_actions(s, B) if isinstance(a, ChangePosition)}
    assert foe.iid not in changes


def test_circle_destroyed_when_target_leaves():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", B, 0)
    circle = _place_st(s, "Spellbinding Circle", A)
    circle.equipped_to = foe.iid
    s.send_to_graveyard(foe.iid)  # the locked monster is destroyed
    Engine(s, [Agent(), Agent()])._cleanup_equips()
    assert circle.zone is Zone.GRAVEYARD  # "when that monster is destroyed, destroy this card"


def test_negated_circle_does_not_lock():
    s = _fresh()
    foe = _spawn(s, "Summoned Skull", B, 0)
    circle = _place_st(s, "Spellbinding Circle", A)
    circle.equipped_to = foe.iid
    _place_st(s, "Royal Decree", A)  # negates all other Traps -> Circle off
    assert not s.monster_attack_locked(foe.iid)
    assert not s.monster_position_locked(foe.iid)
