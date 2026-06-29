"""Effects Batch 35: hand disruption — look at the opponent's hand, then strip it.

Two new primitives: DiscardFromHand (a player discards N cards — random, or the
controller's pick after looking) and ReturnFromHandToDeck (return N hand cards to the
Deck, optionally Monsters only). Cards: Confiscation (pay 1000; discard 1 you pick),
Delinquent Duo (pay 1000; 1 random + 1 more), The Forceful Sentry (return 1 to Deck),
Trap Dustshoot (4+ cards -> return a Monster to Deck).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _set_spell_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _activate(s, iid):
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(iid), 0)


# --- Confiscation: pay 1000, discard 1 from the opponent's hand ---------------------
def test_confiscation_pays_1000_and_discards_one():
    s = _fresh()
    conf = _set_spell_trap(s, "Confiscation", 0)
    a = _in_hand(s, "Summoned Skull", 1)
    b = _in_hand(s, "Mystical Elf", 1)
    before = s.players[0].life_points
    _activate(s, conf.iid)
    assert s.players[0].life_points == before - 1000
    discarded = [x for x in (a, b) if s.inst(x.iid).zone is Zone.GRAVEYARD]
    assert len(discarded) == 1  # exactly one opponent card discarded
    assert len(s.players[1].hand) == 1


def test_confiscation_not_offered_against_empty_hand():
    s = _fresh()
    conf = _set_spell_trap(s, "Confiscation", 0)
    # opponent has no hand cards
    assert [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == conf.iid] == []


# --- Delinquent Duo: 1 random + 1 more ---------------------------------------------
def test_delinquent_duo_discards_two_from_a_full_hand():
    s = _fresh()
    duo = _set_spell_trap(s, "Delinquent Duo", 0)
    cards = [_in_hand(s, "Mystical Elf", 1) for _ in range(3)]
    _activate(s, duo.iid)
    gone = [c for c in cards if s.inst(c.iid).zone is Zone.GRAVEYARD]
    assert len(gone) == 2  # 1 random + 1 more
    assert len(s.players[1].hand) == 1


def test_delinquent_duo_discards_only_one_from_a_single_card_hand():
    s = _fresh()
    duo = _set_spell_trap(s, "Delinquent Duo", 0)
    only = _in_hand(s, "Mystical Elf", 1)
    _activate(s, duo.iid)
    assert s.inst(only.iid).zone is Zone.GRAVEYARD
    assert s.players[1].hand == []  # nothing left for the second discard


# --- The Forceful Sentry: return 1 to the Deck -------------------------------------
def test_forceful_sentry_returns_a_card_to_deck():
    s = _fresh()
    sentry = _set_spell_trap(s, "The Forceful Sentry", 0)
    a = _in_hand(s, "Summoned Skull", 1)
    _in_hand(s, "Mystical Elf", 1)
    deck_before = len(s.players[1].deck)
    _activate(s, sentry.iid)
    assert len(s.players[1].hand) == 1
    assert len(s.players[1].deck) == deck_before + 1
    # the returned card is no longer in the GY (it went to the Deck, not discarded)
    assert s.inst(a.iid).zone in (Zone.DECK, Zone.HAND)


# --- Trap Dustshoot: 4+ cards, return a Monster ------------------------------------
def test_trap_dustshoot_needs_four_cards():
    s = _fresh()
    shoot = _set_spell_trap(s, "Trap Dustshoot", 0)
    for _ in range(3):
        _in_hand(s, "Mystical Elf", 1)  # only 3 cards
    assert [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == shoot.iid] == []
    _in_hand(s, "Summoned Skull", 1)  # now 4
    assert [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == shoot.iid]


def test_trap_dustshoot_returns_a_monster_to_deck():
    s = _fresh()
    shoot = _set_spell_trap(s, "Trap Dustshoot", 0)
    monsters = [_in_hand(s, "Mystical Elf", 1) for _ in range(4)]
    deck_before = len(s.players[1].deck)
    _activate(s, shoot.iid)
    assert len(s.players[1].deck) == deck_before + 1
    assert sum(1 for m in monsters if s.inst(m.iid).zone is Zone.DECK) == 1
