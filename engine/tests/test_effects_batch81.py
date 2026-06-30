"""Effects Batch 81: deck-COMPLETION targets (each is the last unimplemented card in
several GBA decks).

Black Magic Ritual is a Ritual Spell for "Magician of Black Chaos" (a clone of Black
Luster Ritual). Harpie Lady Sisters is a Nomi Winged Beast — barred from Normal Summon,
reachable only via Elegant Egotist (Batch 75). Big Bang Shot is an Equip: +400 ATK,
grants piercing (new ``EquipMod.grants_piercing`` read by ``GameState.has_piercing``), and
banishes the monster it was attached to when it leaves the field (new
``BanishEquippedMonster`` primitive + ``CardInstance.last_equipped_to`` captured by
``send_to_graveyard`` before the field flags are cleared).
"""

from __future__ import annotations

from ygo.agents import Agent, GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    ActivateSpell,
    DeclareAttack,
    NormalSummon,
    SetMonster,
    SpecialSummonFromHand,
    apply,
    legal_actions,
)
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_deck(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _equip(s, name, player, monster_iid, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_UP_ATTACK)
    inst.equipped_to = monster_iid
    return inst


# ------------------------------------------------------------------ Black Magic Ritual


def test_black_magic_ritual_summons_magician_of_black_chaos():
    s = _fresh()
    mbc = _in_hand(s, "Magician of Black Chaos", 0)  # Lv8 Ritual Monster
    ritual = _in_hand(s, "Black Magic Ritual", 0)
    f1 = _in_hand(s, "Summoned Skull", 0)  # Lv6
    f2 = _in_hand(s, "Mystical Elf", 0)  # Lv4 -> total 10 >= 8
    Engine(s, [GreedyAgent(), GreedyAgent()])._activate_as_chain(
        ActivateSpell(ritual.iid, targets=()), 0
    )
    assert s.inst(mbc.iid).zone is Zone.MONSTER  # Ritual Summoned from the hand
    assert s.inst(ritual.iid).zone is Zone.GRAVEYARD  # the Ritual Spell is spent
    # exactly enough fodder was Tributed
    assert {s.inst(f1.iid).zone, s.inst(f2.iid).zone} <= {Zone.GRAVEYARD, Zone.HAND}
    assert s.inst(f1.iid).zone is Zone.GRAVEYARD or s.inst(f2.iid).zone is Zone.GRAVEYARD


def test_black_magic_ritual_not_activatable_without_fodder():
    s = _fresh()
    _in_hand(s, "Magician of Black Chaos", 0)
    ritual = _in_hand(s, "Black Magic Ritual", 0)  # no Tribute fodder in hand/field
    assert not any(
        isinstance(a, ActivateSpell) and a.iid == ritual.iid for a in legal_actions(s, 0)
    )


# ------------------------------------------------------------------- Harpie Lady Sisters


def test_harpie_lady_sisters_cannot_be_normal_summoned():
    s = _fresh()
    sisters = _in_hand(s, "Harpie Lady Sisters", 0)
    assert not reg.get("Harpie Lady Sisters").can_normal_summon
    offered = [
        a
        for a in legal_actions(s, 0)
        if isinstance(a, (NormalSummon, SetMonster, SpecialSummonFromHand)) and a.iid == sisters.iid
    ]
    assert offered == []  # no Normal Summon, no Set, and no self-Special-Summon


def test_harpie_lady_sisters_can_still_be_special_summoned():
    s = _fresh()
    sisters = _in_deck(s, "Harpie Lady Sisters", 0)
    # The Nomi flag bars Normal Summon but must NOT block a Special Summon (Elegant Egotist).
    assert s.special_summon(sisters.iid, 0, Position.FACE_UP_ATTACK)
    assert s.inst(sisters.iid).zone is Zone.MONSTER


# ------------------------------------------------------------------------ Big Bang Shot


def test_big_bang_shot_boosts_attack_by_400():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # 800
    _equip(s, "Big Bang Shot", 0, monster.iid)
    assert s.effective_attack(monster.iid) == 800 + 400


def test_big_bang_shot_grants_piercing():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    assert not s.has_piercing(monster.iid)
    _equip(s, "Big Bang Shot", 0, monster.iid)
    assert s.has_piercing(monster.iid)


def test_big_bang_shot_pierces_a_defense_monster_in_combat():
    s = _fresh()
    attacker = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)  # 2500
    _equip(s, "Big Bang Shot", 0, attacker.iid)  # -> 2900 ATK, piercing
    wall = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_DEFENSE)  # DEF 2000
    apply(s, DeclareAttack(attacker.iid, wall.iid))
    assert s.inst(wall.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 8000 - (2900 - 2000)  # piercing damage = 900


def test_big_bang_shot_banishes_the_monster_when_the_equip_is_destroyed():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    shot = _equip(s, "Big Bang Shot", 0, monster.iid)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(shot.iid)  # e.g. Mystical Space Typhoon hits the Equip
    eng._check_field_to_gy_triggers()
    assert s.inst(shot.iid).zone is Zone.GRAVEYARD
    assert s.inst(monster.iid).zone is Zone.BANISHED  # the equipped monster is banished


def test_big_bang_shot_no_banish_when_the_monster_left_first():
    s = _fresh()
    monster = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    shot = _equip(s, "Big Bang Shot", 0, monster.iid)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(monster.iid)  # the monster is destroyed; the Equip is orphaned
    eng._check_field_to_gy_triggers()
    assert s.inst(shot.iid).zone is Zone.GRAVEYARD  # orphaned Equip goes to the GY
    assert s.inst(monster.iid).zone is Zone.GRAVEYARD  # already gone -> not banished, no crash
