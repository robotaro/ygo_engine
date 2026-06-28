"""Effects Batch 1: the classic Field Spells, authored as pure FieldMod layers.
Verifies the race/attribute filters, both-players application, and the +ATK/-DEF
"glass cannon" terrains."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Position, Zone
from ygo.moves import apply, ActivateSpell
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _activate_field(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    apply(s, ActivateSpell(inst.iid))
    return inst


def test_forest_boosts_its_races_on_both_sides():
    s = GameState.new(("A", "B"), seed=0)
    beast = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # Spellcaster, unaffected
    insect = s.spawn_on_field(reg.get("Hercules Beetle"), 1, 0, Position.FACE_UP_ATTACK)  # Insect (opp side)
    base_insect = reg.get("Hercules Beetle").attack
    _activate_field(s, "Forest", 0)
    assert s.effective_attack(insect.iid) == base_insect + 200  # opponent's Insect is boosted too
    assert s.effective_attack(beast.iid) == reg.get("Mystical Elf").attack  # Spellcaster: unaffected


def test_jurassic_world_boosts_dinosaurs_300():
    s = GameState.new(("A", "B"), seed=0)
    dino = next(c for c in reg if c.is_monster and c.race == "Dinosaur" and (c.attack or 0) > 0)
    m = s.spawn_on_field(dino, 0, 0, Position.FACE_UP_ATTACK)
    _activate_field(s, "Jurassic World", 0)
    assert s.effective_attack(m.iid) == (dino.attack or 0) + 300
    assert s.effective_defense(m.iid) == (dino.defense or 0) + 300


def test_molten_destruction_plus_atk_minus_def():
    s = GameState.new(("A", "B"), seed=0)
    fire = next(c for c in reg if c.is_monster and c.attribute and c.attribute.value == "FIRE" and (c.defense or 0) >= 400)
    m = s.spawn_on_field(fire, 0, 0, Position.FACE_UP_ATTACK)
    _activate_field(s, "Molten Destruction", 0)
    assert s.effective_attack(m.iid) == (fire.attack or 0) + 500
    assert s.effective_defense(m.iid) == (fire.defense or 0) - 400


def test_umi_boosts_water_races_and_weakens_machines():
    s = GameState.new(("A", "B"), seed=0)
    aqua = next(c for c in reg if c.is_monster and c.race == "Aqua" and (c.attack or 0) > 0)
    machine = next(c for c in reg if c.is_monster and c.race == "Machine" and (c.attack or 0) >= 200)
    a = s.spawn_on_field(aqua, 0, 0, Position.FACE_UP_ATTACK)
    mac = s.spawn_on_field(machine, 0, 1, Position.FACE_UP_ATTACK)
    _activate_field(s, "Umi", 0)
    assert s.effective_attack(a.iid) == (aqua.attack or 0) + 200
    assert s.effective_attack(mac.iid) == (machine.attack or 0) - 200


def test_field_spell_replaced_clears_its_layer():
    s = GameState.new(("A", "B"), seed=0)
    fire = next(c for c in reg if c.is_monster and c.attribute and c.attribute.value == "FIRE" and (c.attack or 0) > 0)
    m = s.spawn_on_field(fire, 0, 0, Position.FACE_UP_ATTACK)
    _activate_field(s, "Molten Destruction", 0)
    assert s.effective_attack(m.iid) == (fire.attack or 0) + 500
    _activate_field(s, "Acidic Downpour", 0)  # a new Field Spell replaces the old one
    # Molten Destruction is gone; Acidic Downpour only touches EARTH, so a FIRE monster is back to base.
    assert s.effective_attack(m.iid) == (fire.attack or 0)
