"""Effects Batch 130: Ultimate Offering.

Continuous Trap: once on the field, its PayLifeForExtraNormalSummon(500) marker lets the
Main-Phase enumeration offer EXTRA Normal Summons/Sets that each charge 500 LP, after the free
Normal Summon for the turn is spent. (The opponent's-Battle-Phase window is deferred.)
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import NormalSummon, SetMonster, _main_phase_actions, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _place_offering(s, player, position=Position.FACE_UP_ATTACK):
    inst = s.create_instance(reg.get("Ultimate Offering"), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), position)
    return inst


def _paid_summons(s, player, iid):
    return [
        a
        for a in _main_phase_actions(s, player)
        if isinstance(a, (NormalSummon, SetMonster)) and a.iid == iid and a.pay_life == 500
    ]


def test_no_extra_summon_without_offering():
    s = _fresh()
    card = _hand(s, "Celtic Guardian", A)
    s.normal_summon_used = True  # free Normal Summon already spent
    assert _paid_summons(s, A, card.iid) == []


def test_offering_grants_a_paid_summon_after_the_free_one():
    s = _fresh()
    card = _hand(s, "Celtic Guardian", A)
    _place_offering(s, A)
    s.normal_summon_used = True
    paid = _paid_summons(s, A, card.iid)
    assert paid, "Ultimate Offering should offer a 500-LP Normal Summon once the free one is used"
    apply(s, NormalSummon(card.iid, pay_life=500))
    assert s.inst(card.iid).zone is Zone.MONSTER
    assert s.players[A].life_points == 8000 - 500


def test_only_free_summon_offered_before_the_normal_summon_is_used():
    s = _fresh()
    card = _hand(s, "Celtic Guardian", A)
    _place_offering(s, A)
    # normal_summon_used is False: the free summon (pay_life 0) is offered, not the paid one.
    free = [
        a for a in _main_phase_actions(s, A)
        if isinstance(a, NormalSummon) and a.iid == card.iid and a.pay_life == 0
    ]
    assert free
    assert _paid_summons(s, A, card.iid) == []


def test_not_offered_when_life_points_too_low():
    s = _fresh()
    card = _hand(s, "Celtic Guardian", A)
    _place_offering(s, A)
    s.normal_summon_used = True
    s.players[A].life_points = 500  # paying would not leave LP above 0
    assert _paid_summons(s, A, card.iid) == []


def test_not_offered_while_offering_is_face_down():
    s = _fresh()
    card = _hand(s, "Celtic Guardian", A)
    _place_offering(s, A, position=Position.FACE_DOWN)
    s.normal_summon_used = True
    assert _paid_summons(s, A, card.iid) == []
