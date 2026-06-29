"""Effects Batch 19: "when sent from the field to the Graveyard" triggers.

Equip Spells with a parting effect — they boost via CONTINUOUS while attached, and
fire a trigger when they leave the field for the GY (destroyed directly, or
orphaned when the equipped monster leaves). Black Pendant (burn 500), Horn of the
Unicorn (return itself to the top of the Deck). The state now queues non-monster
cards that carry such a trigger; the engine's existing GY-trigger hook fires it."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
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


# --- Black Pendant: +500 ATK, and burn 500 when it leaves the field --------------
def test_black_pendant_boosts_attack_by_500():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # 800 ATK
    _equip(s, "Black Pendant", 0, monster.iid)
    assert s.effective_attack(monster.iid) == 800 + 500


def test_black_pendant_burns_when_the_equipped_monster_leaves():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    pendant = _equip(s, "Black Pendant", 0, monster.iid)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(monster.iid)  # the equipped monster is destroyed
    eng._check_field_to_gy_triggers()
    assert s.inst(pendant.iid).zone is Zone.GRAVEYARD  # orphaned equip goes to GY
    assert s.players[1].life_points == 7500  # parting burn of 500 to the opponent


def test_black_pendant_burns_when_destroyed_directly():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    pendant = _equip(s, "Black Pendant", 0, monster.iid)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(pendant.iid)  # e.g. Mystical Space Typhoon hits the Equip
    eng._check_field_to_gy_triggers()
    assert s.inst(pendant.iid).zone is Zone.GRAVEYARD
    assert s.inst(monster.iid).zone is Zone.MONSTER  # the monster itself is untouched
    assert s.players[1].life_points == 7500


# --- Horn of the Unicorn: +700 ATK/DEF, and return itself to the Deck ------------
def test_horn_of_the_unicorn_boosts_attack_and_defense():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    _equip(s, "Horn of the Unicorn", 0, monster.iid)
    assert s.effective_attack(monster.iid) == 800 + 700
    assert s.effective_defense(monster.iid) == 2000 + 700


def test_horn_of_the_unicorn_returns_to_top_of_deck_when_it_leaves():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    horn = _equip(s, "Horn of the Unicorn", 0, monster.iid)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(monster.iid)
    eng._check_field_to_gy_triggers()
    assert s.inst(horn.iid).zone is Zone.DECK
    assert s.players[0].deck[-1] == horn.iid  # top of the Deck (the next card drawn)
    assert horn.iid not in s.players[0].graveyard


# --- a plain Equip with no such trigger is not queued (no spurious effect) -------
def test_plain_equip_has_no_parting_effect():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    axe = _equip(s, "Axe of Despair", 0, monster.iid)  # +1000 ATK, no GY trigger
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(monster.iid)
    eng._check_field_to_gy_triggers()
    assert s.inst(axe.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 8000  # nothing happens
