"""Slice 10 tests: the draw-trigger hook. Solemn Wishes (Continuous Trap) gains
its controller 500 LP each time they draw a card(s) — the Draw Phase draw, a
Pot of Greed draw, etc. — but never on the opponent's draws."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _engine(s):
    return Engine(s, [GreedyAgent(), GreedyAgent()])


def _wishes_faceup(s, player=0):
    """Put a face-up Solemn Wishes in ``player``'s Spell/Trap zone."""
    inst = s.create_instance(reg.get("Solemn Wishes"), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _stack_deck(s, player, n):
    """Give ``player`` a deck of n dummy monsters so draws succeed."""
    for _ in range(n):
        c = s.create_instance(reg.get("Mystical Elf"), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(c.iid)


# --------------------------------------------------------------------------- #
#  Solemn Wishes — draw gains
# --------------------------------------------------------------------------- #
def test_solemn_wishes_gains_on_the_draw_phase():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    _stack_deck(s, 0, 3)
    _wishes_faceup(s, 0)

    _engine(s)._draw_phase(0)
    assert s.players[0].life_points == 8000 + 500


def test_solemn_wishes_gains_on_pot_of_greed():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _stack_deck(s, 0, 5)
    _wishes_faceup(s, 0)
    pot = _in_hand(s, "Pot of Greed", 0)

    _engine(s)._activate_as_chain(ActivateSpell(pot.iid, targets=()), 0)
    assert len(s.players[0].hand) == 2  # drew 2 cards...
    assert s.players[0].life_points == 8000 + 500  # ...but it's one draw -> +500 once


def test_solemn_wishes_does_not_gain_on_opponents_draw():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 1
    _stack_deck(s, 1, 3)
    _wishes_faceup(s, 0)  # yours; the opponent is drawing

    _engine(s)._draw_phase(1)
    assert s.players[0].life_points == 8000  # only "you" gain on your own draws


def test_face_down_solemn_wishes_is_dormant():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    _stack_deck(s, 0, 3)
    wishes = s.create_instance(reg.get("Solemn Wishes"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(wishes.iid)
    s.place_spell_trap(wishes.iid, 0, 0, Position.FACE_DOWN)  # Set, not yet activated

    _engine(s)._draw_phase(0)
    assert s.players[0].life_points == 8000  # no gain while Set face-down


def test_solemn_wishes_activatable_from_set_then_pays_out():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 3, 0
    _stack_deck(s, 0, 3)
    wishes = s.create_instance(reg.get("Solemn Wishes"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(wishes.iid)
    s.place_spell_trap(wishes.iid, 0, 0, Position.FACE_DOWN)
    s.inst(wishes.iid).set_on_turn = 1  # Set on an earlier turn -> activatable now

    eng = _engine(s)
    acts = [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == wishes.iid]
    assert acts, "a Set Continuous Trap should be activatable in your Main Phase"
    eng._activate_as_chain(acts[0], 0)
    assert s.inst(wishes.iid).is_face_up  # flipped up, stays (Continuous)

    eng._draw_phase(0)  # now it pays out on a draw
    assert s.players[0].life_points == 8000 + 500


def test_bot_duel_with_solemn_wishes_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=5,
    )
    assert not duel.missing_report
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
