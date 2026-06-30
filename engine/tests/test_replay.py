"""Replays reproduce a duel move-for-move from (seed, decks, recorded choices)."""

from __future__ import annotations

from ygo.agents import GreedyAgent, RandomAgent
from ygo.paths import DECKS_DIR
from ygo.replay import Replay, record_duel, replay_duel

DECK_A = DECKS_DIR / "vanilla" / "beatdown_alpha.txt"
DECK_B = DECKS_DIR / "vanilla" / "beatdown_beta.txt"


def _record(seed, agents):
    return record_duel(DECK_A, DECK_B, agents, names=("A", "B"), seed=seed, capture_snapshots=True)


def test_random_duel_replays_identically():
    # RandomAgent exercises every callback and the seeded RNG.
    replay = _record(7, [RandomAgent(1), RandomAgent(2)])
    outcome = replay_duel(replay, capture_snapshots=True)

    assert outcome.result == replay.result  # same winner + reason
    assert outcome.snapshots == replay.snapshots  # identical board at every step
    assert replay.snapshots  # the duel actually produced states


def test_greedy_duel_replays_identically():
    replay = _record(2, [GreedyAgent(), GreedyAgent()])
    outcome = replay_duel(replay)
    assert outcome.result == replay.result


def test_replay_json_round_trip(tmp_path):
    replay = _record(3, [RandomAgent(5), RandomAgent(6)])
    path = replay.save(tmp_path / "duel.json")

    loaded = Replay.load(path)
    assert loaded.seed == replay.seed
    assert loaded.names == replay.names
    assert loaded.decisions == replay.decisions
    assert loaded.result == replay.result

    # A reloaded replay still reproduces the outcome.
    outcome = replay_duel(loaded)
    assert outcome.result == replay.result


def test_different_seeds_differ():
    a = _record(1, [RandomAgent(1), RandomAgent(2)])
    b = _record(2, [RandomAgent(1), RandomAgent(2)])
    # Different seed -> a different game (decision streams shouldn't be identical).
    assert a.decisions != b.decisions
