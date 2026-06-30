"""Effects Batch 110: Infinite Cards lifts the End-Phase hand-size limit.

The discard-to-6 rule already exists (moves._end_phase_actions / HAND_SIZE_LIMIT). This
Continuous Spell is the floodgate that suppresses it for *both* players while face-up.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.deckbuild import is_functional
from ygo.enums import Position, Zone
from ygo.moves import HAND_SIZE_LIMIT, DiscardCard, _end_phase_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    return GameState.new(("A", "B"), seed=0)


def _give_hand(s, player, n):
    for _ in range(n):
        inst = s.create_instance(reg.get("Kuriboh"), player, Zone.HAND)
        s.players[player].hand.append(inst.iid)


def _place_face_up(s, name, player, pos=Position.FACE_UP_ATTACK):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, pos)
    return inst


# --------------------------------------------------------------- the baseline rule


def test_over_the_limit_forces_discards():
    s = _fresh()
    _give_hand(s, A, HAND_SIZE_LIMIT + 2)  # 8 cards
    acts = _end_phase_actions(s, A)
    assert len(acts) == HAND_SIZE_LIMIT + 2
    assert all(isinstance(a, DiscardCard) for a in acts)


def test_at_the_limit_no_discards():
    s = _fresh()
    _give_hand(s, A, HAND_SIZE_LIMIT)  # exactly 6
    assert _end_phase_actions(s, A) == []


# ------------------------------------------------------------- Infinite Cards floodgate


def test_infinite_cards_is_functional_now():
    assert is_functional(reg.get("Infinite Cards"))


def test_infinite_cards_lifts_the_limit_for_controller():
    s = _fresh()
    _give_hand(s, A, 9)
    _place_face_up(s, "Infinite Cards", A)
    assert s.hand_limit_suppressed(A)
    assert _end_phase_actions(s, A) == []  # no forced discards


def test_infinite_cards_lifts_the_limit_for_both_players():
    s = _fresh()
    _give_hand(s, B, 9)
    _place_face_up(s, "Infinite Cards", A)  # A controls it; B is exempt too
    assert s.hand_limit_suppressed(B)
    assert _end_phase_actions(s, B) == []


def test_face_down_infinite_cards_does_not_lift_the_limit():
    s = _fresh()
    _give_hand(s, A, 8)
    _place_face_up(s, "Infinite Cards", A, pos=Position.FACE_DOWN)  # set, not active
    assert not s.hand_limit_suppressed(A)
    assert len(_end_phase_actions(s, A)) == 8
