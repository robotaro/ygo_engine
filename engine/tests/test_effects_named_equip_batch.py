"""Effects Batch 24: name-restricted Equip Spells.

An Equip's target can be filtered by exact card name (TargetSpec.names — Cyber
Shield only on Harpie Lady / Harpie Lady Sisters) or by an archetype substring
(TargetSpec.name_contains — Ancient Gear Tank on any "Ancient Gear" monster). The
flat boost is an EquipMod; the ones with a parting effect reuse the Batch 19 "sent
from field to GY" trigger (Ancient Gear Tank / Fuhma Shuriken burn, Magic Formula
gains LP)."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import target_candidates
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _equip(s, name, player, monster_iid, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_UP_ATTACK)
    inst.equipped_to = monster_iid
    return inst


def _equip_target_spec(name):
    return reg.get(name).effects[0].target


# --- name filtering of the equip target ------------------------------------------
def test_cyber_shield_targets_only_named_harpies():
    s = _fresh()
    harpie = s.spawn_on_field(reg.get("Harpie Lady"), 0, 0, Position.FACE_UP_ATTACK)
    elf = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)
    cands = target_candidates(s, 0, _equip_target_spec("Cyber Shield"))
    assert harpie.iid in cands and elf.iid not in cands


def test_ancient_gear_tank_targets_the_archetype_by_substring():
    s = _fresh()
    gear = s.spawn_on_field(reg.get("Ancient Gear Beast"), 0, 0, Position.FACE_UP_ATTACK)
    other = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)
    cands = target_candidates(s, 0, _equip_target_spec("Ancient Gear Tank"))
    assert gear.iid in cands and other.iid not in cands


def test_fuhma_shuriken_targets_only_ninja_monsters():
    s = _fresh()
    ninja = s.spawn_on_field(reg.get("Armed Ninja"), 0, 0, Position.FACE_UP_ATTACK)
    other = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)
    cands = target_candidates(s, 0, _equip_target_spec("Fuhma Shuriken"))
    assert ninja.iid in cands and other.iid not in cands


# --- the boosts ------------------------------------------------------------------
def test_cyber_shield_boosts_harpie_by_500():
    s = _fresh()
    harpie = s.spawn_on_field(reg.get("Harpie Lady"), 0, 0, Position.FACE_UP_ATTACK)
    base = reg.get("Harpie Lady").attack
    _equip(s, "Cyber Shield", 0, harpie.iid)
    assert s.effective_attack(harpie.iid) == base + 500


# --- the parting effects ---------------------------------------------------------
def test_ancient_gear_tank_burns_600_when_it_leaves_the_field():
    s = _fresh()
    gear = s.spawn_on_field(reg.get("Ancient Gear Beast"), 0, 0, Position.FACE_UP_ATTACK)
    tank = _equip(s, "Ancient Gear Tank", 0, gear.iid)
    assert s.effective_attack(gear.iid) == reg.get("Ancient Gear Beast").attack + 600
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(tank.iid)  # the Equip is destroyed
    eng._check_field_to_gy_triggers()
    assert s.players[1].life_points == 7400  # 600 to the opponent


def test_magic_formula_gains_1000_lp_when_sent_to_gy():
    s = _fresh()
    dm = s.spawn_on_field(reg.get("Dark Magician"), 0, 0, Position.FACE_UP_ATTACK)
    formula = _equip(s, "Magic Formula", 0, dm.iid)
    assert s.effective_attack(dm.iid) == reg.get("Dark Magician").attack + 700
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(dm.iid)  # equipped monster leaves -> equip orphaned to GY
    eng._check_field_to_gy_triggers()
    assert s.inst(formula.iid).zone is Zone.GRAVEYARD
    assert s.players[0].life_points == 9000  # gained 1000 LP
