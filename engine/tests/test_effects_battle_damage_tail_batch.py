"""Effects Batch 37: more "inflicts battle damage to your opponent" monsters.

All ride the Batch-36 battle-damage hook (_on_battle_damage helper) onto existing
primitives — no new engine work. Masked Sorcerer (draw 1), The Bistro Butcher (opp
draws 2), White Magical Hat (opp discards 1 random), Goe Goe the Gallant Ninja (opp
discards 2 random), Blood Sucker / Goblin Zombie (mill the opponent's top card).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    return s


def _stock_deck(s, player, n=5):
    for _ in range(n):
        inst = s.create_instance(reg.get("Mystical Elf"), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _direct(s, attacker):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, None), 0)


def test_masked_sorcerer_draws_on_damage():
    s = _fresh()
    ms = s.spawn_on_field(reg.get("Masked Sorcerer"), 0, 0, Position.FACE_UP_ATTACK)
    _stock_deck(s, 0)
    before = len(s.players[0].hand)
    _direct(s, ms.iid)
    assert len(s.players[0].hand) == before + 1


def test_bistro_butcher_makes_opponent_draw_two():
    s = _fresh()
    bb = s.spawn_on_field(reg.get("The Bistro Butcher"), 0, 0, Position.FACE_UP_ATTACK)
    _stock_deck(s, 1)
    before = len(s.players[1].hand)
    _direct(s, bb.iid)
    assert len(s.players[1].hand) == before + 2


def test_white_magical_hat_discards_one_random():
    s = _fresh()
    hat = s.spawn_on_field(reg.get("White Magical Hat"), 0, 0, Position.FACE_UP_ATTACK)
    a, b = _in_hand(s, "Summoned Skull", 1), _in_hand(s, "Mystical Elf", 1)
    _direct(s, hat.iid)
    assert sum(1 for x in (a, b) if s.inst(x.iid).zone is Zone.GRAVEYARD) == 1
    assert len(s.players[1].hand) == 1


def test_goe_goe_discards_two_random():
    s = _fresh()
    goe = s.spawn_on_field(reg.get("Goe Goe the Gallant Ninja"), 0, 0, Position.FACE_UP_ATTACK)
    cards = [_in_hand(s, "Mystical Elf", 1) for _ in range(3)]
    _direct(s, goe.iid)
    assert sum(1 for c in cards if s.inst(c.iid).zone is Zone.GRAVEYARD) == 2
    assert len(s.players[1].hand) == 1


def test_blood_sucker_mills_opponent_top_card():
    s = _fresh()
    bs = s.spawn_on_field(reg.get("Blood Sucker"), 0, 0, Position.FACE_UP_ATTACK)
    top = s.create_instance(reg.get("Summoned Skull"), owner=1, zone=Zone.DECK)
    s.players[1].deck.append(top.iid)  # end of list = top of deck
    gy_before = len(s.players[1].graveyard)
    _direct(s, bs.iid)
    assert s.inst(top.iid).zone is Zone.GRAVEYARD
    assert len(s.players[1].graveyard) == gy_before + 1


def test_goblin_zombie_mills_opponent_top_card():
    s = _fresh()
    gz = s.spawn_on_field(reg.get("Goblin Zombie"), 0, 0, Position.FACE_UP_ATTACK)
    _stock_deck(s, 1, 3)
    gy_before = len(s.players[1].graveyard)
    _direct(s, gz.iid)
    assert len(s.players[1].graveyard) == gy_before + 1
