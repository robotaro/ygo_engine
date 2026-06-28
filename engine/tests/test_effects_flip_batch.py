"""Effects Batch 4: more Flip effects, reusing the flip timing (Man-Eater Bug is
the template). Poison Mummy burns 500, Skelengel draws 1, Nobleman-Eater Bug
destroys 2 monsters when flipped."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _eng(s):
    return Engine(s, [GreedyAgent(), GreedyAgent()])


def test_poison_mummy_burns_500_on_flip():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    pm = s.spawn_on_field(reg.get("Poison Mummy"), 0, 0, Position.FACE_DOWN_DEFENSE)
    _eng(s)._trigger_flip_effect(pm.iid)
    assert s.players[1].life_points == 7500


def test_skelengel_draws_on_flip():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    for _ in range(3):  # give player 0 a deck to draw from
        i = s.create_instance(reg.get("Mystical Elf"), 0, Zone.DECK)
        s.players[0].deck.append(i.iid)
    sk = s.spawn_on_field(reg.get("Skelengel"), 0, 0, Position.FACE_DOWN_DEFENSE)
    before = len(s.players[0].hand)
    _eng(s)._trigger_flip_effect(sk.iid)
    assert len(s.players[0].hand) == before + 1


def test_nobleman_eater_bug_destroys_two_on_flip():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    neb = s.spawn_on_field(reg.get("Nobleman-Eater Bug"), 0, 0, Position.FACE_DOWN_DEFENSE)
    a = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    b = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)
    _eng(s)._trigger_flip_effect(neb.iid)
    assert s.inst(a.iid).zone is Zone.GRAVEYARD
    assert s.inst(b.iid).zone is Zone.GRAVEYARD
