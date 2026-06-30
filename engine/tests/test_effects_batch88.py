"""Effects Batch 88: Parasite Paracide (deck-impact) — bury-and-ambush Flip Insect.

Two effects compose its trick, riding infrastructure already in place:
 - FLIP -> PlantSelfInOpponentDeck: state.send_to_player_deck buries this card in the
   OPPONENT's Deck (shuffled) and transfers ownership so it lives entirely on their
   side; the copy is flagged ``planted``.
 - timing="drawn" -> when that buried copy is drawn, engine._fire_drawn_card_triggers
   resolves the effect FOR THE DRAWER (Batch 87's per-draw record): SpecialSummonSelf
   onto the drawer's field in face-up Defense + InflictDamage(SELF, 1000) burns them.

A naturally-drawn (un-planted) copy does nothing — only the buried copy ambushes.
The "all the drawer's monsters become Insect-Type" rider is a documented deferral.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _flip_up(s, name, player, index=0):
    """A just-flipped-up monster (face-up Attack), ready for its Flip Effect."""
    return s.spawn_on_field(reg.get(name), player, index, Position.FACE_UP_ATTACK)


def _deck_put(s, player, name):
    """Append a card to ``player``'s deck (top of deck == end of list)."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _draw_one(s, player):
    eng = Engine(s, [Agent(), Agent()])
    s.draw(player, 1)
    eng._process_draw_triggers()


# --------------------------------------------------------------- piece (1): FLIP plant


def test_flip_buries_parasite_in_the_opponents_deck():
    s = _fresh()
    s.players[1].deck.clear()  # so the plant is the only card afterwards
    para = _flip_up(s, "Parasite Paracide", 0, 0)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(para.iid)
    inst = s.inst(para.iid)
    assert inst.zone is Zone.DECK
    assert inst.iid in s.players[1].deck          # in the OPPONENT's deck
    assert inst.iid not in s.players[0].deck
    assert s.players[0].monster_zones.count(para.iid) == 0  # gone from the flipper's field
    assert inst.owner == 1                          # ownership transferred to the opponent
    assert inst.planted_in_deck is True             # flagged so only this copy ambushes


# ------------------------------------------------------------- piece (2): drawn ambush


def test_drawing_the_planted_copy_summons_it_and_burns_the_drawer():
    s = _fresh()
    s.players[1].deck.clear()
    para = _flip_up(s, "Parasite Paracide", 0, 0)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(para.iid)  # now sole card in P1 deck
    before = s.players[1].life_points

    _draw_one(s, 1)

    inst = s.inst(para.iid)
    assert inst.zone is Zone.MONSTER
    assert inst.iid in s.players[1].monster_zones    # summoned onto the DRAWER's field
    assert inst.controller == 1
    assert inst.position is Position.FACE_UP_DEFENSE  # face-up Defense
    assert s.players[1].life_points == before - 1000  # drawer takes 1000
    assert inst.planted_in_deck is False             # the flag is consumed (fires once)


def test_full_flip_then_draw_chain_end_to_end():
    s = _fresh()
    s.players[1].deck.clear()
    _deck_put(s, 1, "Mystical Elf")  # a decoy under the plant
    para = _flip_up(s, "Parasite Paracide", 0, 0)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(para.iid)
    # The shuffle put 2 cards in P1's deck; draw both — whichever order, Parasite ambushes.
    before = s.players[1].life_points
    _draw_one(s, 1)
    _draw_one(s, 1)
    inst = s.inst(para.iid)
    assert inst.zone is Zone.MONSTER and inst.controller == 1
    assert s.players[1].life_points == before - 1000


# ------------------------------------------------------------------ negative / edges


def test_naturally_drawn_unplanted_copy_does_nothing():
    s = _fresh()
    s.players[0].deck.clear()
    para = _deck_put(s, 0, "Parasite Paracide")  # an ordinary copy in your OWN deck
    before = s.players[0].life_points

    _draw_one(s, 0)

    inst = s.inst(para.iid)
    assert inst.zone is Zone.HAND                # just a normal draw to hand
    assert inst.iid in s.players[0].hand
    assert s.players[0].life_points == before    # no burn — it wasn't planted


def test_burn_still_lands_when_the_drawers_field_is_full():
    s = _fresh()
    for i in range(5):  # fill every Monster Zone so the ambush SS can't land
        _flip_up(s, "Mystical Elf", 1, i)
    s.players[1].deck.clear()
    para = _flip_up(s, "Parasite Paracide", 0, 0)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(para.iid)
    before = s.players[1].life_points

    _draw_one(s, 1)

    inst = s.inst(para.iid)
    assert inst.zone is Zone.HAND                 # no free zone -> stays in hand
    assert s.players[1].life_points == before - 1000  # but the 1000 burn still resolves


def test_ambushed_parasite_goes_to_the_drawers_graveyard():
    s = _fresh()
    s.players[1].deck.clear()
    para = _flip_up(s, "Parasite Paracide", 0, 0)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(para.iid)
    _draw_one(s, 1)
    s.send_to_graveyard(para.iid)  # ownership transferred -> the drawer's GY, no pile error
    assert para.iid in s.players[1].graveyard
    assert para.iid not in s.players[0].graveyard
