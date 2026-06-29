"""Effects Batch 26: more Flip Effects.

Extends two primitives — DestroyAllMonsters gains race / level filters (Magnetic
Mosquito destroys face-up Machines, 4-Starred Ladybug of Doom destroys the
opponent's Level 4 monsters) and a new MillFromDeck (Needle Worm decks the
opponent) — plus banish-from-GY (Witch Doctor of Chaos) and a typed destroy
(Reaper of the Cards) on existing primitives."""

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


def _flip(s, name, player=0, index=0):
    return s.spawn_on_field(reg.get(name), player, index, Position.FACE_UP_ATTACK)


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _spell_trap(s, name, player, index):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_UP_ATTACK)
    return inst


def _stock_deck(s, player, names):
    for name in names:
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


# --- banish a Graveyard monster --------------------------------------------------
def test_witch_doctor_banishes_a_graveyard_monster():
    s = _fresh()
    wd = _flip(s, "Witch Doctor of Chaos", 0, 0)
    victim = _in_gy(s, "Summoned Skull", 1)
    assert victim.iid in target_candidates(s, 0, reg.get("Witch Doctor of Chaos").effects[0].target)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(wd.iid)
    assert s.inst(victim.iid).zone is Zone.BANISHED


# --- typed destroy ---------------------------------------------------------------
def test_reaper_of_the_cards_destroys_a_trap():
    s = _fresh()
    reaper = _flip(s, "Reaper of the Cards", 0, 0)
    _spell_trap(s, "Black Pendant", 1, 0)  # a Spell (not a legal target)
    trap = _spell_trap(s, "Magic Jammer", 1, 1)  # a Trap
    spec = reg.get("Reaper of the Cards").effects[0].target
    assert target_candidates(s, 0, spec) == [trap.iid]
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(reaper.iid)
    assert s.inst(trap.iid).zone is Zone.GRAVEYARD


# --- mill ------------------------------------------------------------------------
def test_needle_worm_mills_five_from_opponent_deck():
    s = _fresh()
    worm = _flip(s, "Needle Worm", 0, 0)
    _stock_deck(s, 1, ["Mystical Elf"] * 7)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(worm.iid)
    assert len(s.players[1].deck) == 2  # 7 - 5
    assert len(s.players[1].graveyard) == 5


# --- race-filtered mass destroy --------------------------------------------------
def test_magnetic_mosquito_destroys_only_face_up_machines():
    s = _fresh()
    mosquito = _flip(s, "Magnetic Mosquito", 0, 0)  # Insect — unaffected
    my_machine = s.spawn_on_field(reg.get("Blocker"), 0, 1, Position.FACE_UP_ATTACK)
    their_machine = s.spawn_on_field(reg.get("Battle Footballer"), 1, 0, Position.FACE_UP_ATTACK)
    non_machine = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)
    facedown_machine = s.spawn_on_field(reg.get("Acrobat Monkey"), 1, 2, Position.FACE_DOWN_DEFENSE)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(mosquito.iid)
    assert s.inst(my_machine.iid).zone is Zone.GRAVEYARD
    assert s.inst(their_machine.iid).zone is Zone.GRAVEYARD
    assert s.inst(non_machine.iid).zone is Zone.MONSTER  # not a Machine
    assert s.inst(facedown_machine.iid).zone is Zone.MONSTER  # face-down
    assert s.inst(mosquito.iid).zone is Zone.MONSTER  # the flipper itself (Insect)


# --- level-filtered, one-side mass destroy ---------------------------------------
def test_4starred_ladybug_destroys_opponent_level_4_only():
    s = _fresh()
    bug = _flip(s, "4-Starred Ladybug of Doom", 0, 0)
    my_l4 = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)  # Lv4, mine
    their_l4 = s.spawn_on_field(reg.get("7 Colored Fish"), 1, 0, Position.FACE_UP_ATTACK)  # Lv4
    their_l6 = s.spawn_on_field(reg.get("Summoned Skull"), 1, 1, Position.FACE_UP_ATTACK)  # Lv6
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(bug.iid)
    assert s.inst(their_l4.iid).zone is Zone.GRAVEYARD  # opponent's Level 4
    assert s.inst(their_l6.iid).zone is Zone.MONSTER  # wrong Level
    assert s.inst(my_l4.iid).zone is Zone.MONSTER  # my monster, untouched
