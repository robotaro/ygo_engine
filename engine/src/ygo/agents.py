"""Decision makers. An agent answers "which legal move?" — humans and bots alike.

The engine hands an agent the current state plus the list of legal actions and
asks it to pick one. This single interface is what makes the engine bot-friendly:
a RandomAgent (great for fuzz-testing the rules), a GreedyAgent (a watchable
baseline), or — later — a learned policy all plug in the same way. The eventual
web client is just a "remote agent" that ships the choice over the wire.
"""

from __future__ import annotations

import random

from .enums import Phase, Position
from .moves import Action, ActivateSpell, DeclareAttack, DiscardCard, NormalSummon, Pass
from .state import GameState


class Agent:
    def decide(self, state: GameState, legal: list[Action]) -> Action:
        raise NotImplementedError


class RandomAgent(Agent):
    """Picks uniformly at random. Useful for fuzzing every rules path."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def decide(self, state: GameState, legal: list[Action]) -> Action:
        return self.rng.choice(legal)


class GreedyAgent(Agent):
    """A simple, watchable beatdown heuristic.

    Summon the biggest body, attack only when it's favourable, and dump the
    weakest card when over the hand limit. Not clever — just not silly.
    """

    def decide(self, state: GameState, legal: list[Action]) -> Action:
        phase = state.phase
        if phase in (Phase.MAIN_1, Phase.MAIN_2):
            return self._main(state, legal)
        if phase is Phase.BATTLE:
            return self._battle(state, legal)
        if phase is Phase.END:
            return self._end(state, legal)
        return self._pass_or_first(legal)

    # -- helpers --
    @staticmethod
    def _atk(state: GameState, iid: int) -> int:
        return state.inst(iid).card.attack or 0

    @staticmethod
    def _pass_or_first(legal: list[Action]) -> Action:
        for a in legal:
            if isinstance(a, Pass):
                return a
        return legal[0]

    def _main(self, state: GameState, legal: list[Action]) -> Action:
        # Free card advantage: always pop Pot of Greed.
        for a in legal:
            if isinstance(a, ActivateSpell) and state.inst(a.iid).card.name == "Pot of Greed":
                return a
        summons = [a for a in legal if isinstance(a, NormalSummon)]
        if summons:
            # biggest ATK, fewest tributes
            return max(summons, key=lambda a: (self._atk(state, a.iid), -len(a.tributes)))
        return self._pass_or_first(legal)

    def _battle(self, state: GameState, legal: list[Action]) -> Action:
        attacks = [a for a in legal if isinstance(a, DeclareAttack)]
        best: DeclareAttack | None = None
        best_score: tuple[int, int] | None = None
        for a in attacks:
            atk = self._atk(state, a.attacker)
            if a.target is None:
                score = (3, atk)  # direct attack: always great
            else:
                tgt = state.inst(a.target)
                if tgt.position is Position.FACE_DOWN_DEFENSE:
                    score = (1, atk)  # unknown DEF — mild gamble
                elif tgt.position is Position.FACE_UP_ATTACK:
                    other = tgt.card.attack or 0
                    score = (2, atk - other) if atk > other else (-1, atk - other)
                else:  # face-up defense
                    dfn = tgt.card.defense or 0
                    score = (1, 0) if atk > dfn else (-1, atk - dfn)
            if best_score is None or score > best_score:
                best, best_score = a, score
        if best is not None and best_score is not None and best_score[0] >= 1:
            return best
        return self._pass_or_first(legal)

    def _end(self, state: GameState, legal: list[Action]) -> Action:
        discards = [a for a in legal if isinstance(a, DiscardCard)]
        if discards:
            return min(discards, key=lambda a: self._atk(state, a.iid))
        return self._pass_or_first(legal)
