"""Effects Batch 52: Special Summon from the hand on an attack.

New primitives SpecialSummonFromHand (deterministic highest-ATK eligible pick, like
SearchFromDeck) and RevealRandomHandCardSummonOrGY (A Hero Emerges' random reveal),
both routing through the state.special_summon chokepoint. A Hero Emerges reveals a random
hand card (summon a freely-summonable monster, else to the GY); Relieve Monster bounces a
monster you control then Special Summons a Level 4-or-lower monster from your hand.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import resolve_effect, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()

ATTACKER, DEFENDER = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ATTACKER, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _hand(s, name, player=DEFENDER):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _set_trap(s, name, player=DEFENDER):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _event(attacker_iid, target_iid=None):
    return {"kind": "attack_declared", "player": ATTACKER, "attacker": attacker_iid, "target": target_iid}


def _offered(s, trap_iid, event):
    return any(a.iid == trap_iid for a in response_options(s, DEFENDER, event, 2))


A_HERO = EFFECTS["A Hero Emerges"][0]
RELIEVE = EFFECTS["Relieve Monster"][0]


# --------------------------------------------------------------------------- #
#  A Hero Emerges
# --------------------------------------------------------------------------- #
def test_a_hero_emerges_summons_the_revealed_monster():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    mon = _hand(s, "Celtic Guardian")  # the only hand card -> the random pick is fixed
    trap = _set_trap(s, "A Hero Emerges")
    event = _event(atk.iid, None)
    assert _offered(s, trap.iid, event)
    resolve_effect(s, A_HERO, trap.iid, (), event)
    assert s.inst(mon.iid).zone is Zone.MONSTER
    assert s.inst(mon.iid).controller == DEFENDER
    assert s.inst(mon.iid).was_special_summoned


def test_a_hero_emerges_sends_nonmonster_to_graveyard():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    spell = _hand(s, "Pot of Greed")  # not a monster -> to the GY
    trap = _set_trap(s, "A Hero Emerges")
    resolve_effect(s, A_HERO, trap.iid, (), _event(atk.iid, None))
    assert s.inst(spell.iid).zone is Zone.GRAVEYARD


def test_a_hero_emerges_not_offered_with_empty_hand():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    trap = _set_trap(s, "A Hero Emerges")  # the Set card is the only thing; hand is empty
    s.players[DEFENDER].hand.clear()
    assert not _offered(s, trap.iid, _event(atk.iid, None))


# --------------------------------------------------------------------------- #
#  Relieve Monster
# --------------------------------------------------------------------------- #
def test_relieve_monster_bounces_then_summons_a_level4():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    target = _spawn(s, "Summoned Skull", DEFENDER, 0)  # Level 6 -> bounced, not re-summoned
    fresh = _hand(s, "Celtic Guardian")  # Level 4 -> the eligible Special Summon
    trap = _set_trap(s, "Relieve Monster")
    event = _event(atk.iid, target.iid)
    assert _offered(s, trap.iid, event)
    resolve_effect(s, RELIEVE, trap.iid, (target.iid,), event)
    assert s.inst(target.iid).zone is Zone.HAND  # the targeted monster bounced
    assert s.inst(fresh.iid).zone is Zone.MONSTER  # the Level 4 took the field
    assert s.inst(fresh.iid).was_special_summoned


def test_relieve_monster_just_bounces_with_no_eligible_monster():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    target = _spawn(s, "Mystical Elf", DEFENDER, 0)  # Level 4, but bounced to hand
    high = _hand(s, "Des Frog")  # Level 5 -> NOT eligible (max_level 4)
    trap = _set_trap(s, "Relieve Monster")
    # The bounced Mystical Elf (Level 4) is the only eligible monster afterwards, so it
    # would be re-summoned; to test the "no eligible" branch we instead bounce the Level-5.
    target2 = _spawn(s, "Des Frog", DEFENDER, 1)
    s.send_to_graveyard(target.iid)  # remove the Level-4 distraction
    resolve_effect(s, RELIEVE, trap.iid, (target2.iid,), _event(atk.iid, target2.iid))
    assert s.inst(target2.iid).zone is Zone.HAND  # bounced
    # Both Des Frogs (Level 5) are ineligible -> nothing was Special Summoned.
    assert not s.inst(high.iid).was_special_summoned
    assert s.inst(high.iid).zone is Zone.HAND
