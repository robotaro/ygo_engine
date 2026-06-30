"""Effects Batch 112: Appropriate — draw 2 each time the opponent draws outside a Draw Phase.

Modelled as a face-up Continuous Trap carrying a DrawOnOpponentDraw marker that the engine's
draw-event loop reads. Fires only for the OPPONENT's draws, and only outside a Draw Phase.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, phase
    return s


def _stock_deck(s, player, n, name="Kuriboh"):
    for _ in range(n):
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


def _place_faceup(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def _draw_and_process(s, who, n=1):
    eng = Engine(s, [Agent(), Agent()])
    s.draw(who, n)
    eng._process_draw_triggers()


def test_opponent_main_phase_draw_triggers_draw_two():
    s = _fresh(Phase.MAIN_1)
    _place_faceup(s, "Appropriate", A)
    _stock_deck(s, A, 5)
    _stock_deck(s, B, 5)
    a_deck, a_hand = len(s.players[A].deck), len(s.players[A].hand)
    _draw_and_process(s, B, 1)  # B draws outside its Draw Phase
    assert len(s.players[A].deck) == a_deck - 2  # A drew 2 off Appropriate
    assert len(s.players[A].hand) == a_hand + 2


def test_no_trigger_during_draw_phase():
    s = _fresh(Phase.DRAW)
    _place_faceup(s, "Appropriate", A)
    _stock_deck(s, A, 5)
    _stock_deck(s, B, 5)
    a_deck = len(s.players[A].deck)
    _draw_and_process(s, B, 1)  # a normal Draw-Phase draw
    assert len(s.players[A].deck) == a_deck  # Appropriate stays silent


def test_controllers_own_draw_does_not_trigger():
    s = _fresh(Phase.MAIN_1)
    _place_faceup(s, "Appropriate", A)
    _stock_deck(s, A, 5)
    a_deck = len(s.players[A].deck)
    _draw_and_process(s, A, 1)  # A (the controller) draws — not the opponent
    assert len(s.players[A].deck) == a_deck - 1  # only the explicit draw, no +2


def test_negated_appropriate_does_not_trigger():
    s = _fresh(Phase.MAIN_1)
    _place_faceup(s, "Appropriate", A)
    _place_faceup(s, "Royal Decree", A)  # negates all other Traps -> Appropriate off
    _stock_deck(s, A, 5)
    _stock_deck(s, B, 5)
    a_deck = len(s.players[A].deck)
    _draw_and_process(s, B, 1)
    assert len(s.players[A].deck) == a_deck  # no response while negated
