"""Decision makers. An agent answers "which legal move?" — humans and bots alike.

The engine hands an agent the current state plus the list of legal actions and
asks it to pick one. This single interface is what makes the engine bot-friendly:
a RandomAgent (great for fuzz-testing the rules), a GreedyAgent (a watchable
baseline), or — later — a learned policy all plug in the same way. The eventual
web client is just a "remote agent" that ships the choice over the wire.
"""

from __future__ import annotations

import random

from .enums import Phase, Position, Zone
from .moves import (
    Action,
    ActivateSpell,
    DeclareAttack,
    DiscardCard,
    NormalSummon,
    Pass,
    SetSpellTrap,
)
from .state import GameState


class Agent:
    def decide(self, state: GameState, legal: list[Action]) -> Action:
        raise NotImplementedError

    def respond(self, state: GameState, options: list[Action], event):
        """Chain response window: activate one of ``options`` or None to pass."""
        return None

    def choose_targets(self, state: GameState, source_iid: int, spec, candidates: list[int]):
        """Pick ``spec.count`` targets for a forced effect.

        Sensible default for removal effects: prefer the opponent's monsters,
        strongest first (avoids self-targeting when better options exist).
        """
        me = state.inst(source_iid).controller
        ranked = sorted(
            candidates,
            key=lambda i: (state.inst(i).controller == me, -(state.inst(i).card.attack or 0)),
        )
        return tuple(ranked[: spec.count])


class RandomAgent(Agent):
    """Picks uniformly at random. Useful for fuzzing every rules path."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def decide(self, state: GameState, legal: list[Action]) -> Action:
        return self.rng.choice(legal)

    def respond(self, state: GameState, options: list[Action], event):
        return self.rng.choice([*options, None])

    def choose_targets(self, state: GameState, source_iid: int, spec, candidates: list[int]):
        return tuple(self.rng.sample(candidates, spec.count))


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
        inst = state.inst(iid)
        if inst.zone is Zone.MONSTER:
            return state.effective_attack(iid)  # include Equip boosts on the field
        return inst.card.attack or 0

    @staticmethod
    def _pass_or_first(legal: list[Action]) -> Action:
        for a in legal:
            if isinstance(a, Pass):
                return a
        return legal[0]

    # No-target spells the CPU happily fires when legal (no choice to get wrong).
    AUTO_SPELLS = {"Pot of Greed", "Fissure", "Tremendous Fire", "Hinotama", "Raigeki"}

    def _main(self, state: GameState, legal: list[Action]) -> Action:
        player = state.turn_player  # Main Phase actions are the turn player's
        for a in legal:
            if (
                isinstance(a, ActivateSpell)
                and not a.targets
                and state.inst(a.iid).card.name in self.AUTO_SPELLS
            ):
                return a
        summons = [a for a in legal if isinstance(a, NormalSummon)]
        if summons:
            # biggest ATK, fewest tributes
            return max(summons, key=lambda a: (self._atk(state, a.iid), -len(a.tributes)))
        # Equip a Spell onto our own strongest monster, if we drew one.
        equips = [
            a
            for a in legal
            if isinstance(a, ActivateSpell)
            and state.inst(a.iid).card.is_permanent
            and a.targets
            and state.inst(a.targets[0]).controller == player
        ]
        if equips:
            return max(equips, key=lambda a: self._atk(state, a.targets[0]))
        # Otherwise, Set a Trap so it can be sprung on the opponent's turn.
        sets = [a for a in legal if isinstance(a, SetSpellTrap) and state.inst(a.iid).card.is_trap]
        if sets:
            return sets[0]
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
                    other = state.effective_attack(a.target)
                    score = (2, atk - other) if atk > other else (-1, atk - other)
                else:  # face-up defense
                    dfn = state.effective_defense(a.target)
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

    def respond(self, state: GameState, options: list[Action], event):
        # Fire a triggered Trap when it comes up; don't waste Quick-Play spells.
        for a in options:
            if state.inst(a.iid).card.is_trap:
                return a
        return None
