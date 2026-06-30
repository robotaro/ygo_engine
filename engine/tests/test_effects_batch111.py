"""Effects Batch 111: Gearfried the Iron Knight destroys Equip Cards equipped to it.

A continuous rider enforced at the equip chokepoint (EquipToTarget): an Equip Spell may
target and resolve on Gearfried, but it is destroyed (sent to the GY) instead of attaching.
A normal monster equips fine, and a negated/inactive Gearfried lets equips attach.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.effects import EffectContext, EquipToTarget
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1
EQUIP = "Mage Power"  # a plain Equip Spell with no parting "sent to GY" effect


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _place_equip(s, player):
    inst = s.create_instance(reg.get(EQUIP), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _equip(s, equip, target, controller=A):
    EquipToTarget().execute(EffectContext(state=s, controller=controller, source_iid=equip.iid, targets=[target]))


def test_predicate_true_for_faceup_gearfried():
    s = _fresh()
    gear = _spawn(s, "Gearfried the Iron Knight", A, 0)
    assert s.destroys_attached_equips(gear.iid)


def test_equip_on_gearfried_is_destroyed():
    s = _fresh()
    gear = _spawn(s, "Gearfried the Iron Knight", A, 0)
    equip = _place_equip(s, A)
    _equip(s, equip, gear.iid)
    assert equip.equipped_to is None  # never attached
    assert equip.zone is Zone.GRAVEYARD
    assert equip.iid in s.players[A].graveyard


def test_opponents_equip_on_gearfried_is_also_destroyed():
    s = _fresh()
    gear = _spawn(s, "Gearfried the Iron Knight", A, 0)
    equip = _place_equip(s, B)  # the opponent equips it
    _equip(s, equip, gear.iid, controller=B)
    assert equip.equipped_to is None
    assert equip.zone is Zone.GRAVEYARD


def test_equip_on_a_normal_monster_attaches():
    s = _fresh()
    other = _spawn(s, "Celtic Guardian", A, 0)
    equip = _place_equip(s, A)
    _equip(s, equip, other.iid)
    assert equip.equipped_to == other.iid
    assert equip.zone is Zone.SPELL_TRAP


def test_face_down_gearfried_does_not_destroy_equips():
    s = _fresh()
    gear = _spawn(s, "Gearfried the Iron Knight", A, 0, pos=Position.FACE_DOWN)
    assert not s.destroys_attached_equips(gear.iid)  # not face-up -> rider dormant
    equip = _place_equip(s, A)
    _equip(s, equip, gear.iid)
    assert equip.equipped_to == gear.iid  # attaches normally


def test_skill_drain_negated_gearfried_lets_equips_attach():
    s = _fresh()
    gear = _spawn(s, "Gearfried the Iron Knight", A, 0)
    drain = s.create_instance(reg.get("Skill Drain"), owner=B, zone=Zone.DECK)
    s.players[B].deck.append(drain.iid)
    s.place_spell_trap(drain.iid, B, s.first_empty_spell_trap_zone(B), Position.FACE_UP_ATTACK)
    assert s.monster_effects_negated(gear.iid)
    assert not s.destroys_attached_equips(gear.iid)  # negated -> rider off
    equip = _place_equip(s, A)
    _equip(s, equip, gear.iid)
    assert equip.equipped_to == gear.iid  # attaches normally under Skill Drain
