"""Effects Batch 11: "up to N" targeting (variable count).

TargetSpec(up_to=True) lets a card target between 1 and ``count`` cards. Penguin
Soldier returns up to 2 monsters to the hand; Hade-Hane up to 3. Covered here:
the enumeration (every non-empty subset up to the max), the activation gate (at
least 1 candidate), and the agents' variable-count picks."""

from __future__ import annotations

from ygo.agents import Agent, RandomAgent
from ygo.cards import CardRegistry
from ygo.effects import TargetSpec
from ygo.engine import Engine
from ygo.enums import Position, Zone
from ygo.moves import _enumerate_targets
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _eng(s):
    return Engine(s, [Agent(), Agent()])


# --- enumeration of "up to N" subsets ------------------------------------------
def test_up_to_enumerates_all_nonempty_subsets():
    s = GameState.new(("A", "B"), seed=0)
    a = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    b = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    spec = TargetSpec(count=2, where="any_monster", up_to=True)
    sets = _enumerate_targets(s, 0, spec)
    assert {frozenset(t) for t in sets} == {
        frozenset({a.iid}),
        frozenset({b.iid}),
        frozenset({a.iid, b.iid}),
    }  # 1- and 2-card subsets, never the empty set


def test_up_to_caps_subset_size_at_available_when_fewer_than_max():
    s = GameState.new(("A", "B"), seed=0)
    only = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    spec = TargetSpec(count=3, where="any_monster", up_to=True)
    sets = _enumerate_targets(s, 0, spec)
    assert sets == [(only.iid,)]  # only one candidate -> just the singleton


# --- Penguin Soldier: FLIP, up to 2 monsters to hand ---------------------------
def test_penguin_soldier_bounces_up_to_two_monsters():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    peng = s.spawn_on_field(reg.get("Penguin Soldier"), 0, 0, Position.FACE_DOWN_DEFENSE)
    m1 = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    m2 = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)
    _eng(s)._trigger_flip_effect(peng.iid)  # base Agent greedily takes the max (2)
    assert s.inst(m1.iid).zone is Zone.HAND
    assert s.inst(m2.iid).zone is Zone.HAND


def test_penguin_soldier_fires_with_only_one_target():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    peng = s.spawn_on_field(reg.get("Penguin Soldier"), 0, 0, Position.FACE_DOWN_DEFENSE)
    lone = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    _eng(s)._trigger_flip_effect(peng.iid)  # up-to-2 still works with a single target
    assert s.inst(lone.iid).zone is Zone.HAND


# --- agents pick a valid variable count ----------------------------------------
def test_random_agent_picks_a_valid_count_for_up_to():
    s = GameState.new(("A", "B"), seed=0)
    a = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    b = s.spawn_on_field(reg.get("Summoned Skull"), 1, 1, Position.FACE_UP_ATTACK)
    spec = TargetSpec(count=2, where="any_monster", up_to=True)
    agent = RandomAgent(seed=1)
    for _ in range(20):  # never crashes, always 1..2 distinct valid picks
        picked = agent.choose_targets(s, a.iid, spec, [a.iid, b.iid])
        assert 1 <= len(picked) <= 2
        assert len(set(picked)) == len(picked)
        assert all(p in (a.iid, b.iid) for p in picked)
