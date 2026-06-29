"""Effects Batch 46: battle-position change.

New primitives ChangeTargetPosition(to) and ChangeAllPositions(side, to, level band),
where ``to`` is "attack"/"defense"/"face_down" or "toggle" (rotate a face-up monster
ATK<->DEF). They only act on face-up monsters (never flip a face-down up, so no Flip
Effect fires). Cards: Block Attack, Book of Moon, Ready for Intercepting (targeted);
Earthquake, No Entry!!, Zero Gravity, Windstorm of Etaqua (mass); Kunai with Chain
(attack-reaction — change the attacker to Defense, stopping the attack).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import ChangeAllPositions, ChangeTargetPosition, Effect
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, response_options, resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(turn_player=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, turn_player, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _resolve(s, primitive, controller=0, targets=()):
    resolve_effect(s, Effect(resolve=(primitive,)), s.players[controller].monster_zones[0] or 0, targets, None)


# --------------------------------------------------------------------------- #
#  The primitives
# --------------------------------------------------------------------------- #
def test_change_target_to_defense_and_face_down():
    s = _fresh()
    a = _spawn(s, "Summoned Skull", 0, 0, Position.FACE_UP_ATTACK)
    b = _spawn(s, "Celtic Guardian", 1, 0, Position.FACE_UP_ATTACK)
    resolve_effect(s, Effect(resolve=(ChangeTargetPosition(to="defense"),)), a.iid, (a.iid,), None)
    assert s.inst(a.iid).position is Position.FACE_UP_DEFENSE
    resolve_effect(s, Effect(resolve=(ChangeTargetPosition(to="face_down"),)), b.iid, (b.iid,), None)
    assert s.inst(b.iid).position is Position.FACE_DOWN_DEFENSE
    assert not s.inst(b.iid).is_face_up


def test_change_target_ignores_face_down_monsters():
    s = _fresh()
    fd = _spawn(s, "Celtic Guardian", 0, 0, Position.FACE_DOWN_DEFENSE)
    resolve_effect(s, Effect(resolve=(ChangeTargetPosition(to="attack"),)), fd.iid, (fd.iid,), None)
    assert s.inst(fd.iid).position is Position.FACE_DOWN_DEFENSE  # untouched (stayed face-down)


def test_change_all_toggle_rotates_face_up_both_sides():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", 0, 0, Position.FACE_UP_ATTACK)
    dfn = _spawn(s, "Big Shield Gardna", 1, 0, Position.FACE_UP_DEFENSE)
    fd = _spawn(s, "Celtic Guardian", 1, 1, Position.FACE_DOWN_DEFENSE)
    resolve_effect(s, Effect(resolve=(ChangeAllPositions(to="toggle"),)), atk.iid, (), None)
    assert s.inst(atk.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(dfn.iid).position is Position.FACE_UP_ATTACK
    assert s.inst(fd.iid).position is Position.FACE_DOWN_DEFENSE  # face-down skipped


def test_change_all_one_side_to_defense():
    s = _fresh()
    mine = _spawn(s, "Summoned Skull", 0, 0, Position.FACE_UP_ATTACK)
    theirs = _spawn(s, "Gemini Elf", 1, 0, Position.FACE_UP_ATTACK)
    resolve_effect(s, Effect(resolve=(ChangeAllPositions(side="opponent", to="defense"),)), mine.iid, (), None)
    assert s.inst(theirs.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(mine.iid).position is Position.FACE_UP_ATTACK  # my side untouched


def test_change_all_level_band():
    s = _fresh()
    low = _spawn(s, "Celtic Guardian", 0, 0, Position.FACE_UP_ATTACK)  # Level 4
    high = _spawn(s, "Summoned Skull", 0, 1, Position.FACE_UP_ATTACK)  # Level 6
    resolve_effect(s, Effect(resolve=(ChangeAllPositions(to="defense", min_level=5),)), low.iid, (), None)
    assert s.inst(low.iid).position is Position.FACE_UP_ATTACK  # Level 4 < 5 -> untouched
    assert s.inst(high.iid).position is Position.FACE_UP_DEFENSE


# --------------------------------------------------------------------------- #
#  Cards (activated through the engine)
# --------------------------------------------------------------------------- #
def _activate_spell(s, name, player, targets=()):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(inst.iid, targets=targets), player)
    return inst


def test_block_attack_card():
    s = _fresh()
    foe = _spawn(s, "Gemini Elf", 1, 0, Position.FACE_UP_ATTACK)
    _activate_spell(s, "Block Attack", 0, targets=(foe.iid,))
    assert s.inst(foe.iid).position is Position.FACE_UP_DEFENSE


def test_book_of_moon_card():
    s = _fresh()
    mon = _spawn(s, "Summoned Skull", 1, 0, Position.FACE_UP_ATTACK)
    _activate_spell(s, "Book of Moon", 0, targets=(mon.iid,))
    assert s.inst(mon.iid).position is Position.FACE_DOWN_DEFENSE


def test_earthquake_card():
    s = _fresh()
    a = _spawn(s, "Summoned Skull", 0, 0, Position.FACE_UP_ATTACK)
    b = _spawn(s, "Gemini Elf", 1, 0, Position.FACE_UP_ATTACK)
    _activate_spell(s, "Earthquake", 0)
    assert s.inst(a.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(b.iid).position is Position.FACE_UP_DEFENSE


def test_kunai_with_chain_stops_the_attack():
    s = _fresh(turn_player=0, phase=Phase.BATTLE)
    atk = _spawn(s, "Summoned Skull", 0, 0, Position.FACE_UP_ATTACK)
    trap = s.create_instance(reg.get("Kunai with Chain"), owner=1, zone=Zone.HAND)
    s.players[1].hand.append(trap.iid)
    idx = next(i for i, z in enumerate(s.players[1].spell_trap_zones) if z is None)
    s.place_spell_trap(trap.iid, 1, idx, Position.FACE_DOWN)
    trap.set_on_turn = s.turn_count - 1
    event = {"kind": "attack_declared", "player": 0, "attacker": atk.iid, "target": None}
    opts = response_options(s, 1, event, 2)
    act = next(a for a in opts if a.iid == trap.iid)
    Engine(s, [Agent(), Agent()])._activate_as_chain(act, 1)
    assert s.inst(atk.iid).position is Position.FACE_UP_DEFENSE  # attacker forced to Defense
