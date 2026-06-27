"""A single duel session: the engine running in a thread, talking to one browser.

The engine is synchronous and blocks an agent on its turn. To let a human play
over an async WebSocket, we run the engine in a worker thread and back the human
"agent" with two thread-safe queues:

  * outbound — messages the server pushes to the browser (state, log, decision, result)
  * inbound  — intents the browser sends back (drag a card here, attack that)

``HumanAgent.decide`` simply blocks on ``inbound`` until the player chooses; the
GreedyAgent opponent runs inline. No engine changes were needed beyond an
``on_change`` notification hook.
"""

from __future__ import annotations

import queue
import time
from pathlib import Path

from ..agents import Agent, GreedyAgent
from ..engine import Engine
from ..moves import Action, Pass
from ..serialize import legal_to_dict, match_intent, state_to_dict
from ..setup import new_duel
from ..state import GameState

_ABORT = object()  # sentinel pushed to inbound to unblock a waiting human on disconnect


class EngineAborted(Exception):
    """Raised inside the engine thread when the client disconnects."""


def _describe_event(state: GameState, event: dict | None, viewer: int) -> str:
    if not event:
        return "Respond?"
    actor = state.players[event["player"]].name
    if event["kind"] == "attack_declared":
        return f"{actor} is attacking with {state.inst(event['attacker']).name}"
    if event["kind"] == "summon":
        return f"{actor} Summoned {state.inst(event['monster']).name}"
    return f"{actor} acted"


def _option_label(state: GameState, option) -> str:
    label = state.inst(option.iid).card.name
    if option.targets:
        names = ", ".join(state.inst(t).name for t in option.targets)
        label += f" → {names}"
    return label


class HumanAgent(Agent):
    def __init__(self, session: "GameSession", player: int):
        self.session = session
        self.player = player

    def decide(self, state: GameState, legal: list[Action]) -> Action:
        with_pass = any(isinstance(a, Pass) for a in legal)
        while True:
            self.session.send(
                {
                    "type": "decision",
                    "context": "main",
                    "player": self.player,
                    "state": state_to_dict(state, self.player),
                    "legal": legal_to_dict(state, self.player, with_pass=with_pass),
                }
            )
            intent = self.session.wait_for_intent()
            if intent is None:
                raise EngineAborted()
            action = match_intent(intent, legal, state)
            if action is not None:
                return action
            self.session.send({"type": "illegal", "intent": intent})

    def respond(self, state: GameState, options: list[Action], event):
        """Chain response window: pick a card to activate, or pass."""
        self.session.send(
            {
                "type": "decision",
                "context": "response",
                "player": self.player,
                "state": state_to_dict(state, self.player),
                "event": _describe_event(state, event, self.player),
                "options": [
                    {"iid": o.iid, "targets": list(o.targets), "label": _option_label(state, o)}
                    for o in options
                ],
            }
        )
        while True:
            intent = self.session.wait_for_intent()
            if intent is None:
                raise EngineAborted()
            if intent.get("kind") == "pass":
                return None
            iid, targets = intent.get("iid"), set(intent.get("targets", []))
            chosen = next(
                (o for o in options if o.iid == iid and set(o.targets) == targets), None
            )
            if chosen is not None:
                return chosen
            self.session.send({"type": "illegal", "intent": intent})


class GameSession:
    def __init__(self, *, deck_a: Path, deck_b: Path, seed: int = 0, human_player: int = 0):
        self.deck_a = deck_a
        self.deck_b = deck_b
        self.seed = seed
        self.human_player = human_player
        self.outbound: queue.Queue = queue.Queue()
        self.inbound: queue.Queue = queue.Queue()
        self.state: GameState | None = None
        self.engine: Engine | None = None

    # ----- lifecycle (run on the engine worker thread) -----
    def run(self) -> None:
        names = ["CPU", "CPU"]
        names[self.human_player] = "You"
        duel = new_duel(
            self.deck_a, self.deck_b, names=tuple(names), seed=self.seed
        )
        self.state = duel.state

        agents: list[Agent] = [GreedyAgent(), GreedyAgent()]
        agents[self.human_player] = HumanAgent(self, self.human_player)

        self.engine = Engine(
            self.state,
            agents,
            log=self._on_log,
            on_change=self._push_state,
            pacer=lambda: time.sleep(0.7),  # let resolution steps breathe in the UI
        )
        self._push_state()
        try:
            result = self.engine.run()
        except EngineAborted:
            return
        self.send(
            {
                "type": "result",
                "winner": result.winner,
                "reason": result.reason,
                "youWin": result.winner == self.human_player,
            }
        )

    # ----- engine -> client -----
    def _on_log(self, message: str) -> None:
        self.send({"type": "log", "message": message})

    def _push_state(self) -> None:
        if self.state is not None:
            self.send({"type": "state", "state": state_to_dict(self.state, self.human_player)})

    def send(self, message: dict) -> None:
        self.outbound.put(message)

    # ----- client -> engine -----
    def submit_intent(self, intent: dict) -> None:
        self.inbound.put(intent)

    def wait_for_intent(self):
        item = self.inbound.get()
        return None if item is _ABORT else item

    def abort(self) -> None:
        self.inbound.put(_ABORT)
