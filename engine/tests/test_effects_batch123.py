"""Effects Batch 123: Lady Assailant of Flames.

"FLIP: Banish the top 3 cards of your Deck; inflict 800 damage to your opponent." A Flip
Effect pairing the new BanishTopOfDeck(SELF) primitive with a flat 800 burn. Last blocker of
T.A. Gardner (Worldwide Edition).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _stock_deck(s, player, n):
    """Put ``n`` known cards into ``player``'s Deck (last appended is the top)."""
    iids = []
    for _ in range(n):
        inst = s.create_instance(reg.get("Mystical Elf"), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)
        iids.append(inst.iid)
    return iids


def test_flip_banishes_top_3_and_burns_800():
    s = _fresh()
    lady = s.spawn_on_field(reg.get("Lady Assailant of Flames"), A, 0, Position.FACE_DOWN_DEFENSE)
    deck = _stock_deck(s, A, 5)
    lp0 = s.players[B].life_points
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(lady.iid)
    top3 = deck[-3:]
    for iid in top3:
        assert s.inst(iid).zone is Zone.BANISHED
        assert iid in s.players[A].banished
    assert len(s.players[A].deck) == 2  # 5 - 3
    assert s.players[B].life_points == lp0 - 800


def test_flip_banishes_own_deck_not_opponents():
    s = _fresh()
    lady = s.spawn_on_field(reg.get("Lady Assailant of Flames"), A, 0, Position.FACE_DOWN_DEFENSE)
    _stock_deck(s, A, 4)
    foe_deck = _stock_deck(s, B, 4)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(lady.iid)
    assert len(s.players[A].deck) == 1
    assert all(s.inst(iid).zone is Zone.DECK for iid in foe_deck)  # opponent's deck untouched


def test_flip_with_fewer_than_3_banishes_what_is_there():
    s = _fresh()
    lady = s.spawn_on_field(reg.get("Lady Assailant of Flames"), A, 0, Position.FACE_DOWN_DEFENSE)
    deck = _stock_deck(s, A, 2)
    lp0 = s.players[B].life_points
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(lady.iid)
    assert all(s.inst(iid).zone is Zone.BANISHED for iid in deck)
    assert s.players[A].deck == []
    assert s.players[B].life_points == lp0 - 800  # the burn still happens
