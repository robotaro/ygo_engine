"""Record duels and replay them deterministically.

The engine is a pure ``(state, action) -> state'`` driven by seeded randomness on
the state, and every choice flows through one of an :class:`~ygo.agents.Agent`'s
callbacks. So a duel is fully determined by **(seed, both decks, the stream of
agent choices)** — record those and you can reproduce the game move-for-move.

Two cooperating wrappers do the work, with zero changes to the engine kernel:

  * :class:`RecordingAgent` wraps any agent and logs every callback's result.
  * :class:`ReplayAgent` feeds a recorded log back, returning the same choices.

A :class:`Replay` bundles the setup + per-seat decision logs + the outcome (and,
optionally, an omniscient board snapshot after every change — a scrubbable
timeline for a UI/debugger). It round-trips to JSON.

Recording captures the *index* of each chosen Action (decide/respond) and the
*iids* of chosen cards (the choose_* callbacks); both are stable across a
deterministic re-run, so replay never needs to serialise an Action.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import moves
from .agents import Agent
from .engine import Engine
from .serialize import full_snapshot
from .setup import new_duel


class ReplayError(RuntimeError):
    """The recorded decision stream didn't line up with the engine's requests —
    i.e. the replay diverged (usually means the engine logic changed)."""


# Action subclasses are simple frozen dataclasses (int / int|None / tuple[int] /
# bool fields), so we serialise the chosen Action itself rather than an index into
# the legal list — robust to list ordering and to HumanAgent's reconstructed
# actions (which carry a chosen ``zone_index`` the legal candidate lacks).
_ACTION_TYPES = {
    cls.__name__: cls
    for cls in vars(moves).values()
    if isinstance(cls, type) and issubclass(cls, moves.Action)
}


def _encode_action(action: moves.Action) -> dict:
    payload = {
        f.name: (list(v) if isinstance(v, tuple) else v)
        for f in fields(action)
        for v in (getattr(action, f.name),)
    }
    return {"type": type(action).__name__, "fields": payload}


def _decode_action(data: dict) -> moves.Action:
    cls = _ACTION_TYPES[data["type"]]
    kwargs = {k: (tuple(v) if isinstance(v, list) else v) for k, v in data["fields"].items()}
    return cls(**kwargs)


# --------------------------------------------------------------------------- #
#  Recording / replaying agents
# --------------------------------------------------------------------------- #
class RecordingAgent(Agent):
    """Wrap an agent; defer every decision to it and log what it chose."""

    def __init__(self, inner: Agent):
        self.inner = inner
        self.log: list[dict] = []

    def decide(self, state, legal):
        action = self.inner.decide(state, legal)
        self.log.append({"k": "decide", "a": _encode_action(action)})
        return action

    def respond(self, state, options, event):
        action = self.inner.respond(state, options, event)
        self.log.append({"k": "respond", "a": _encode_action(action) if action is not None else None})
        return action

    def choose_targets(self, state, source_iid, spec, candidates):
        chosen = self.inner.choose_targets(state, source_iid, spec, candidates)
        self.log.append({"k": "targets", "v": list(chosen)})
        return chosen

    def choose_card(self, state, prompt, option_iids):
        chosen = self.inner.choose_card(state, prompt, option_iids)
        self.log.append({"k": "card", "v": chosen})
        return chosen

    def choose_cost_fodder(self, state, controller, candidates, count, *, kind="discard"):
        chosen = self.inner.choose_cost_fodder(state, controller, candidates, count, kind=kind)
        self.log.append({"k": "fodder", "v": list(chosen)})
        return chosen

    def choose_tributes(self, state, controller, candidates, required):
        chosen = self.inner.choose_tributes(state, controller, candidates, required)
        self.log.append({"k": "tributes", "v": list(chosen)})
        return chosen


class ReplayAgent(Agent):
    """Return the recorded choices, in order. Raises if the stream diverges."""

    def __init__(self, log: list[dict]):
        self._log = list(log)
        self._pos = 0

    def _next(self, kind: str) -> dict:
        if self._pos >= len(self._log):
            raise ReplayError(f"replay exhausted: engine asked for {kind!r} but the log ran out")
        entry = self._log[self._pos]
        self._pos += 1
        if entry["k"] != kind:
            raise ReplayError(f"replay diverged: expected {entry['k']!r}, engine wanted {kind!r}")
        return entry

    def decide(self, state, legal):
        return _decode_action(self._next("decide")["a"])

    def respond(self, state, options, event):
        data = self._next("respond")["a"]
        return _decode_action(data) if data is not None else None

    def choose_targets(self, state, source_iid, spec, candidates):
        return tuple(self._next("targets")["v"])

    def choose_card(self, state, prompt, option_iids):
        return self._next("card")["v"]

    def choose_cost_fodder(self, state, controller, candidates, count, *, kind="discard"):
        return tuple(self._next("fodder")["v"])

    def choose_tributes(self, state, controller, candidates, required):
        return tuple(self._next("tributes")["v"])


# --------------------------------------------------------------------------- #
#  The replay artifact
# --------------------------------------------------------------------------- #
@dataclass
class Replay:
    deck_a: str
    deck_b: str
    names: tuple[str, str]
    seed: int
    starting_hand: int = 5
    decisions: list[list[dict]] = field(default_factory=list)  # one log per seat
    result: dict | None = None  # {"winner": int|None, "reason": str}
    snapshots: list[dict] | None = None  # omniscient board after each change (optional)

    # -- persistence --
    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data["names"] = list(self.names)  # JSON has no tuples
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | str) -> "Replay":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["names"] = tuple(data["names"])
        return cls(**data)


# --------------------------------------------------------------------------- #
#  Record / replay drivers
# --------------------------------------------------------------------------- #
def record_duel(
    deck_a: Path | str,
    deck_b: Path | str,
    inner_agents: list[Agent],
    *,
    names: tuple[str, str] = ("Player 1", "Player 2"),
    seed: int = 0,
    starting_hand: int = 5,
    capture_snapshots: bool = False,
    log=None,
) -> Replay:
    """Play a duel with ``inner_agents`` while recording every choice."""
    duel = new_duel(deck_a, deck_b, names=names, seed=seed, starting_hand=starting_hand)
    recorders = [RecordingAgent(a) for a in inner_agents]

    snapshots: list[dict] = []
    on_change = (lambda: snapshots.append(full_snapshot(duel.state))) if capture_snapshots else None

    engine = Engine(duel.state, recorders, log=log, on_change=on_change)
    result = engine.run()

    return Replay(
        deck_a=str(deck_a),
        deck_b=str(deck_b),
        names=names,
        seed=seed,
        starting_hand=starting_hand,
        decisions=[r.log for r in recorders],
        result={"winner": result.winner, "reason": result.reason},
        snapshots=snapshots or None,
    )


@dataclass
class ReplayOutcome:
    result: dict  # {"winner", "reason"} reproduced this run
    final_state: object  # the GameState at the end (for rendering)
    snapshots: list[dict] | None


def replay_duel(replay: Replay, *, capture_snapshots: bool = False, log=None) -> ReplayOutcome:
    """Re-run a recorded duel, returning the reproduced outcome and final state."""
    duel = new_duel(
        replay.deck_a,
        replay.deck_b,
        names=replay.names,
        seed=replay.seed,
        starting_hand=replay.starting_hand,
    )
    agents = [ReplayAgent(log_) for log_ in replay.decisions]

    snapshots: list[dict] = []
    on_change = (lambda: snapshots.append(full_snapshot(duel.state))) if capture_snapshots else None

    engine = Engine(duel.state, agents, log=log, on_change=on_change)
    result = engine.run()
    return ReplayOutcome(
        result={"winner": result.winner, "reason": result.reason},
        final_state=duel.state,
        snapshots=snapshots or None,
    )


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> None:
    """``record [seed] [out.json]`` to capture a bot duel, or ``<file.json>`` to
    replay one and render the final board."""
    import sys

    from .agents import GreedyAgent
    from .paths import DECKS_DIR
    from .render import render

    argv = sys.argv[1:] if argv is None else argv

    if argv and argv[0] == "record":
        seed = int(argv[1]) if len(argv) > 1 else 2
        out = Path(argv[2]) if len(argv) > 2 else Path("replay.json")
        deck_a = DECKS_DIR / "vanilla" / "beatdown_alpha.txt"
        deck_b = DECKS_DIR / "vanilla" / "beatdown_beta.txt"
        replay = record_duel(
            deck_a, deck_b, [GreedyAgent(), GreedyAgent()], names=("Alpha", "Beta"), seed=seed
        )
        replay.save(out)
        moves_n = sum(len(log) for log in replay.decisions)
        print(f"recorded {moves_n} decisions → {out}")
        print(f"result: {replay.result['reason']}")
        # Prove it reproduces.
        again = replay_duel(replay)
        ok = again.result == replay.result
        print(f"replay reproduces result: {'YES' if ok else 'NO'}")
        return

    if not argv:
        print("usage: python -m ygo.replay record [seed] [out.json] | python -m ygo.replay <file.json>")
        return

    replay = Replay.load(argv[0])
    outcome = replay_duel(replay)
    print(render(outcome.final_state, viewer=0))
    print(f"\n{outcome.result['reason']}")
    match = outcome.result == replay.result
    print(f"matches recorded outcome: {'YES' if match else 'NO — replay diverged'}")


if __name__ == "__main__":
    main()
