"""Effects Batch 9: banish (remove-from-play) payloads.

Dark Core (discard 1, banish a face-up monster), Dimensional Prison (banish the
attacking monster), Bottomless Trap Hole (banish a Summoned monster with ATK
>= 1500). Banished cards land in the owner's banished pile, not the Graveyard,
and raise no "sent to GY" trigger."""

from __future__ import annotations

from ygo.agents import Agent, GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, Pass, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()


class ActivateByName(Agent):
    """Springs a named card whenever a response window allows it."""

    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _set_card(state, name, player, index, set_on_turn=1):
    inst = state.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    state.players[player].deck.append(inst.iid)
    state.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = set_on_turn
    return inst


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


# --- the banish primitive / state.banish --------------------------------------
def test_banish_moves_a_card_to_the_owners_banished_pile():
    s = GameState.new(("A", "B"), seed=0)
    mon = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    s.banish(mon.iid)
    assert s.inst(mon.iid).zone is Zone.BANISHED
    assert mon.iid in s.players[1].banished  # owner's pile
    assert mon.iid not in s.players[1].graveyard
    assert s.gy_from_field == []  # banishing is not "sent to the Graveyard"


# --- Dark Core: discard 1, banish a face-up monster ----------------------------
def test_dark_core_discards_and_banishes():
    s = GameState.new(("A", "B"), seed=0)
    victim = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    fodder = _in_hand(s, "Mystical Elf")
    spell = _in_hand(s, "Dark Core")
    apply(s, ActivateSpell(spell.iid, targets=(victim.iid,)))
    assert s.inst(victim.iid).zone is Zone.BANISHED
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the discard cost


# --- Dimensional Prison: banish the attacker -----------------------------------
def test_dimensional_prison_banishes_the_attacker_and_fizzles_the_attack():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    attacker = s.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    _set_card(s, "Dimensional Prison", 1, 0)
    eng = Engine(s, [GreedyAgent(), ActivateByName("Dimensional Prison")])
    eng._declare_attack(DeclareAttack(attacker.iid, None), 0)
    assert s.inst(attacker.iid).zone is Zone.BANISHED
    assert s.players[1].life_points == 8000  # the direct attack never landed
    assert s.chain == []


# --- Bottomless Trap Hole: banish a Summoned monster with ATK >= 1500 ----------
def test_bottomless_banishes_a_big_summon():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    big = s.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    _set_card(s, "Bottomless Trap Hole", 1, 0)
    Engine(s, [GreedyAgent(), ActivateByName("Bottomless Trap Hole")])._response_window(
        {"kind": "summon", "player": 0, "monster": big.iid}
    )
    assert s.inst(big.iid).zone is Zone.BANISHED


def test_bottomless_ignores_a_small_summon():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    small = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # 800 ATK
    _set_card(s, "Bottomless Trap Hole", 1, 0)
    Engine(s, [GreedyAgent(), ActivateByName("Bottomless Trap Hole")])._response_window(
        {"kind": "summon", "player": 0, "monster": small.iid}
    )
    assert s.inst(small.iid).zone is Zone.MONSTER  # too weak — Bottomless can't fire
