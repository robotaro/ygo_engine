"""Effects Batch 7: Special Summon from the hand (a monster's own ability) +
the piercing battle-damage rider.

Self-SS from hand: Cyber Dragon ("if only your opponent controls a monster"),
The Fiend Megacyber ("opponent controls at least 2 more than you"), Ancient Gear
("if you control an 'Ancient Gear'"). It does not consume the Normal Summon.

Piercing: Mad Sword Beast / Dark Driceratops deal the excess (ATK - DEF) to the
defending player when they attack a Defense Position monster."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    DeclareAttack,
    NormalSummon,
    SpecialSummonFromHand,
    apply,
    legal_actions,
)
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _main_phase(seed=0):
    s = GameState.new(("A", "B"), seed=seed)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    return s


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _hand_summons(s, player=0):
    return {a.iid for a in legal_actions(s, player) if isinstance(a, SpecialSummonFromHand)}


# --- Cyber Dragon: only the opponent controls a monster ------------------------
def test_cyber_dragon_summonable_when_only_opponent_has_a_monster():
    s = _main_phase()
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    cyber = _in_hand(s, "Cyber Dragon")
    assert cyber.iid in _hand_summons(s)
    apply(s, SpecialSummonFromHand(cyber.iid))
    assert s.inst(cyber.iid).zone is Zone.MONSTER
    assert s.inst(cyber.iid).position is Position.FACE_UP_ATTACK


def test_cyber_dragon_not_summonable_when_you_control_a_monster():
    s = _main_phase()
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # you have one
    cyber = _in_hand(s, "Cyber Dragon")
    assert cyber.iid not in _hand_summons(s)


def test_cyber_dragon_not_summonable_when_board_is_empty():
    s = _main_phase()
    cyber = _in_hand(s, "Cyber Dragon")
    assert cyber.iid not in _hand_summons(s)  # opponent controls nothing


def test_self_special_summon_does_not_use_the_normal_summon():
    s = _main_phase()
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    cyber = _in_hand(s, "Cyber Dragon")
    body = _in_hand(s, "Mystical Elf")
    apply(s, SpecialSummonFromHand(cyber.iid))
    assert s.normal_summon_used is False
    # the regular Normal Summon is still available afterwards
    assert any(isinstance(a, NormalSummon) and a.iid == body.iid for a in legal_actions(s, 0))


# --- The Fiend Megacyber: opponent controls >=2 more monsters than you ---------
def test_fiend_megacyber_needs_two_monster_lead():
    s = _main_phase()
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    mega = _in_hand(s, "The Fiend Megacyber")
    assert mega.iid not in _hand_summons(s)  # only a 1-monster lead
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)
    assert mega.iid in _hand_summons(s)  # now a 2-monster lead


# --- Ancient Gear: you control a face-up "Ancient Gear" ------------------------
def test_ancient_gear_needs_a_named_ancient_gear_on_field():
    s = _main_phase()
    gear = _in_hand(s, "Ancient Gear")
    assert gear.iid not in _hand_summons(s)
    s.spawn_on_field(reg.get("Ancient Gear"), 0, 0, Position.FACE_UP_ATTACK)
    assert gear.iid in _hand_summons(s)


def test_self_summon_needs_a_free_monster_zone():
    # Ancient Gear's condition (control a face-up "Ancient Gear") still holds on a
    # full board, so this isolates the open-zone gate.
    s = _main_phase()
    for i in range(5):  # fill every Monster Zone with Ancient Gear copies
        s.spawn_on_field(reg.get("Ancient Gear"), 0, i, Position.FACE_UP_ATTACK)
    gear = _in_hand(s, "Ancient Gear")
    assert gear.iid not in _hand_summons(s)  # condition met, but no open zone


# --- Piercing battle damage ----------------------------------------------------
def test_piercing_does_nothing_when_the_defender_survives():
    s = _main_phase()
    attacker = s.spawn_on_field(reg.get("Mad Sword Beast"), 0, 0, Position.FACE_UP_ATTACK)  # 1400
    s.phase = Phase.BATTLE
    target = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_DEFENSE)  # DEF 2000
    apply(s, DeclareAttack(attacker.iid, target.iid))  # 1400 < 2000: bounces off, no pierce
    assert s.inst(target.iid).zone is Zone.MONSTER
    assert s.players[0].life_points == 8000 - (2000 - 1400)  # attacker's controller takes the gap


def test_mad_sword_beast_pierces_a_weak_defender():
    s = _main_phase()
    attacker = s.spawn_on_field(reg.get("Mad Sword Beast"), 0, 0, Position.FACE_UP_ATTACK)  # 1400
    s.phase = Phase.BATTLE
    target = s.spawn_on_field(reg.get("Hitotsu-Me Giant"), 1, 0, Position.FACE_UP_DEFENSE)  # DEF 1000
    apply(s, DeclareAttack(attacker.iid, target.iid))
    assert s.inst(target.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 8000 - (1400 - 1000)  # excess pierces


def test_non_piercing_attacker_deals_no_break_damage():
    s = _main_phase()
    attacker = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)  # 2500
    s.phase = Phase.BATTLE
    target = s.spawn_on_field(reg.get("Hitotsu-Me Giant"), 1, 0, Position.FACE_UP_DEFENSE)  # DEF 1000
    apply(s, DeclareAttack(attacker.iid, target.iid))
    assert s.inst(target.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 8000  # no piercing -> no damage on the break
