"""Effects Batch 131: Last Will.

Armed version: activating Last Will arms its controller for the turn (ArmLastWill); the next
time a monster they control is sent to their Graveyard, Engine._fire_last_will_for Special
Summons 1 monster with 1500 or less ATK from their Deck (highest-ATK eligible), once that turn.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _arm(s, controller=A):
    ctx = EffectContext(state=s, controller=controller, source_iid=-1, targets=[])
    for prim in EFFECTS["Last Will"][0].resolve:
        prim.execute(ctx)


def _drain(s):
    Engine(s, [Agent(), Agent()])._check_field_to_gy_triggers()


def test_summons_highest_eligible_on_a_monster_death():
    s = _fresh()
    victim = _spawn(s, "Mystical Elf", A, 0)
    cg = _deck(s, "Celtic Guardian", A)  # 1400 — eligible, highest
    _deck(s, "Mystical Elf", A)  # 800 — eligible, lower
    skull = _deck(s, "Summoned Skull", A)  # 2500 — NOT eligible
    _arm(s, A)
    s.send_to_graveyard(victim.iid, by_effect=True)
    _drain(s)
    assert s.inst(cg.iid).zone is Zone.MONSTER  # the 1400 came out
    assert s.inst(skull.iid).zone is Zone.DECK  # the 2500 was ineligible
    assert s.players[A].last_will_fired_turn == s.turn_count


def test_fires_only_once_per_turn():
    s = _fresh()
    v1 = _spawn(s, "Mystical Elf", A, 0)
    v2 = _spawn(s, "Mystical Elf", A, 1)
    _deck(s, "Celtic Guardian", A)
    _deck(s, "Celtic Guardian", A)
    _arm(s, A)
    s.send_to_graveyard(v1.iid, by_effect=True)
    _drain(s)
    after_first = sum(1 for i in s.players[A].monster_zones if i is not None)
    s.send_to_graveyard(v2.iid, by_effect=True)
    _drain(s)
    after_second = sum(1 for i in s.players[A].monster_zones if i is not None)
    assert after_second == after_first - 1  # the 2nd death just removed a monster, no new SS


def test_no_summon_when_not_armed():
    s = _fresh()
    victim = _spawn(s, "Mystical Elf", A, 0)
    cg = _deck(s, "Celtic Guardian", A)
    s.send_to_graveyard(victim.iid, by_effect=True)
    _drain(s)
    assert s.inst(cg.iid).zone is Zone.DECK  # nothing armed -> no summon


def test_no_eligible_monster_does_not_consume_the_use():
    s = _fresh()
    victim = _spawn(s, "Mystical Elf", A, 0)
    skull = _deck(s, "Summoned Skull", A)  # 2500 only — nothing <=1500
    _arm(s, A)
    s.send_to_graveyard(victim.iid, by_effect=True)
    _drain(s)
    assert s.inst(skull.iid).zone is Zone.DECK
    assert s.players[A].last_will_fired_turn is None  # not marked fired


def test_arming_lapses_next_turn():
    s = _fresh()
    victim = _spawn(s, "Mystical Elf", A, 0)
    cg = _deck(s, "Celtic Guardian", A)
    _arm(s, A)
    s.turn_count += 1  # a later turn
    s.send_to_graveyard(victim.iid, by_effect=True)
    _drain(s)
    assert s.inst(cg.iid).zone is Zone.DECK  # arming expired
