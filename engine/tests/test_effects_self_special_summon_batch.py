"""Effects Batch 29: cost/condition self-Special-Summon (cannot be Normal Summoned).

Extends ``HandSpecialSummon`` with ``cannot_normal_summon`` (the card is barred from
Normal/Tribute Summon — ``CardDef.can_normal_summon`` returns False) and
``banish_costs`` (a tuple of ``SummonCost`` paid by banishing disjoint GY monsters).
Cards: the Chaos monsters (banish 1 LIGHT + 1 DARK) and Dark Armed Dragon (a board
condition: exactly 3 DARK monsters in the GY).
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Zone
from ygo.moves import (
    NormalSummon,
    SetMonster,
    SpecialSummonFromHand,
    apply,
    legal_actions,
)
from ygo.state import GameState

reg = CardRegistry.load_csv()

BLS = "Black Luster Soldier - Envoy of the Beginning"
DAD = "Dark Armed Dragon"


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _ss_actions(s, iid):
    return [a for a in legal_actions(s, 0) if isinstance(a, SpecialSummonFromHand) and a.iid == iid]


# --- cannot be Normal Summoned -----------------------------------------------------
def test_chaos_monster_is_barred_from_normal_summon():
    s = _fresh()
    bls = _in_hand(s, BLS, 0)
    # Even with the fodder present, it can never be Normal/Tribute Summoned or Set.
    _in_gy(s, "Mystical Elf", 0)  # LIGHT
    _in_gy(s, "Summoned Skull", 0)  # DARK
    summons = [
        a
        for a in legal_actions(s, 0)
        if isinstance(a, (NormalSummon, SetMonster)) and a.iid == bls.iid
    ]
    assert summons == []
    assert not reg.get(BLS).can_normal_summon


# --- the banish cost gates the Special Summon --------------------------------------
def test_chaos_summon_needs_one_light_and_one_dark():
    s = _fresh()
    bls = _in_hand(s, BLS, 0)
    assert _ss_actions(s, bls.iid) == []  # empty GY -> can't pay
    _in_gy(s, "Mystical Elf", 0)  # 1 LIGHT only
    assert _ss_actions(s, bls.iid) == []  # still missing a DARK
    _in_gy(s, "Summoned Skull", 0)  # now 1 DARK too
    assert _ss_actions(s, bls.iid)  # payable


def test_chaos_summon_banishes_disjoint_fodder_and_summons():
    s = _fresh()
    bls = _in_hand(s, BLS, 0)
    light = _in_gy(s, "Mystical Elf", 0)
    dark = _in_gy(s, "Summoned Skull", 0)
    apply(s, SpecialSummonFromHand(bls.iid))
    assert s.inst(bls.iid).zone is Zone.MONSTER
    assert s.inst(light.iid).zone is Zone.BANISHED
    assert s.inst(dark.iid).zone is Zone.BANISHED


def test_chaos_summon_does_not_double_count_a_single_monster():
    s = _fresh()
    bls = _in_hand(s, BLS, 0)
    # One DARK monster can't satisfy both the LIGHT and the DARK sub-cost.
    _in_gy(s, "Summoned Skull", 0)
    _in_gy(s, "Archfiend Soldier", 0)  # another DARK, still no LIGHT
    assert _ss_actions(s, bls.iid) == []


# --- board-condition self-SS (Dark Armed Dragon: exactly 3 DARK) -------------------
def test_dark_armed_dragon_needs_exactly_three_dark():
    s = _fresh()
    dad = _in_hand(s, DAD, 0)
    for _ in range(2):
        _in_gy(s, "Summoned Skull", 0)
    assert _ss_actions(s, dad.iid) == []  # only 2 DARK
    third = _in_gy(s, "Archfiend Soldier", 0)
    assert _ss_actions(s, dad.iid)  # exactly 3 -> summonable
    _in_gy(s, "Vorse Raider", 0)  # a 4th DARK breaks the "exactly 3"
    assert _ss_actions(s, dad.iid) == []
    assert third  # (silence unused-warning; the 3rd DARK is what flipped it on)


def test_dark_armed_dragon_summon_keeps_the_graveyard():
    s = _fresh()
    dad = _in_hand(s, DAD, 0)
    darks = [_in_gy(s, "Summoned Skull", 0) for _ in range(3)]
    apply(s, SpecialSummonFromHand(dad.iid))
    assert s.inst(dad.iid).zone is Zone.MONSTER
    # No banish cost — the 3 DARK monsters stay in the GY.
    assert all(s.inst(d.iid).zone is Zone.GRAVEYARD for d in darks)
