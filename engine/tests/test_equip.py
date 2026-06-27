"""Slice 5 tests: Equip Spells and the derived-stat ("layers") system."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _equip_in_hand(state, name, player=0):
    inst = state.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    state.players[player].hand.append(inst.iid)
    return inst


def test_axe_of_despair_boosts_attack_and_stays_on_field():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count = Phase.MAIN_1, 2
    ox = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)
    assert s.effective_attack(ox.iid) == 1700
    axe = _equip_in_hand(s, "Axe of Despair")

    apply(s, ActivateSpell(axe.iid, targets=(ox.iid,)))
    assert s.effective_attack(ox.iid) == 1700 + 1000  # boosted
    assert s.inst(axe.iid).zone is Zone.SPELL_TRAP  # Equip stays (permanent), not GY
    assert s.inst(axe.iid).equipped_to == ox.iid


def test_united_we_stand_scales_with_face_up_monsters():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count = Phase.MAIN_1, 2
    hero = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)
    uws = _equip_in_hand(s, "United We Stand")
    apply(s, ActivateSpell(uws.iid, targets=(hero.iid,)))
    assert s.effective_attack(hero.iid) == 1700 + 800  # one face-up monster

    s.spawn_on_field(reg.get("Vorse Raider"), 0, 1, Position.FACE_UP_ATTACK)  # now two
    assert s.effective_attack(hero.iid) == 1700 + 1600
    s.spawn_on_field(reg.get("Gemini Elf"), 0, 2, Position.FACE_DOWN_DEFENSE)  # face-down doesn't count
    assert s.effective_attack(hero.iid) == 1700 + 1600


def test_mage_power_scales_with_spell_and_trap_count():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count = Phase.MAIN_1, 2
    hero = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)
    mp = _equip_in_hand(s, "Mage Power")
    apply(s, ActivateSpell(mp.iid, targets=(hero.iid,)))
    # Mage Power itself counts as a Spell on your field -> +500
    assert s.effective_attack(hero.iid) == 1700 + 500


def test_equipped_monster_wins_combat_via_boost():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    ox = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)  # 1700
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # 2500
    axe = _equip_in_hand(s, "Axe of Despair")
    apply(s, ActivateSpell(axe.iid, targets=(ox.iid,)))  # Ox -> 2700

    s.phase = Phase.BATTLE
    Engine(s, [GreedyAgent(), GreedyAgent()])._declare_attack(DeclareAttack(ox.iid, foe.iid), 0)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # 2700 beats 2500
    assert s.players[1].life_points == 8000 - (2700 - 2500)


def test_equip_destroyed_when_its_monster_leaves():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.BATTLE, 2, 0
    attacker = s.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    ox = s.spawn_on_field(reg.get("Battle Ox"), 1, 0, Position.FACE_UP_ATTACK)  # 1700
    axe = s.create_instance(reg.get("Axe of Despair"), owner=1, zone=Zone.DECK)
    s.players[1].deck.append(axe.iid)
    s.place_spell_trap(axe.iid, 1, 0, Position.FACE_UP_ATTACK)
    axe.equipped_to = ox.iid
    assert s.effective_attack(ox.iid) == 2700

    # Blue-Eyes (3000) destroys the equipped Ox (2700); its Axe should follow to the GY.
    Engine(s, [GreedyAgent(), GreedyAgent()])._declare_attack(DeclareAttack(attacker.iid, ox.iid), 0)
    assert s.inst(ox.iid).zone is Zone.GRAVEYARD
    assert s.inst(axe.iid).zone is Zone.GRAVEYARD  # orphaned Equip cleaned up
