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
    GeminiSummon,
    NormalSummon,
    Pass,
    SetSpellTrap,
    SpecialSummonFromHand,
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

    def choose_card(self, state: GameState, prompt: str, option_iids: list[int]):
        """Pick one card iid from a list (e.g. which Fusion Monster to summon)."""
        return option_iids[0] if option_iids else None

    def choose_discards(self, state: GameState, controller: int, candidates: list[int], count: int):
        """Pick ``count`` cards from the hand to discard as a cost. Default: the
        weakest fodder (lowest ATK, then lowest Level) — keep the good cards."""
        ranked = sorted(
            candidates,
            key=lambda i: (state.inst(i).card.attack or 0, state.inst(i).card.level or 0),
        )
        return tuple(ranked[:count])

    def choose_cost_tributes(self, state: GameState, controller: int, candidates: list[int], count: int):
        """Pick ``count`` of your monsters to Tribute as an activation cost (Spiritual
        Fire Art, Icarus Attack). Count-based (not Level-total). Default: the weakest
        (lowest ATK, then lowest Level) — keep the good monsters on the board."""
        ranked = sorted(
            candidates,
            key=lambda i: (state.inst(i).card.attack or 0, state.inst(i).card.level or 0),
        )
        return tuple(ranked[:count])

    def choose_tributes(self, state: GameState, controller: int, candidates: list[int], required: int):
        """Pick monsters to Tribute whose Levels total >= ``required`` (Ritual
        Summon). Default: when the field is full, Tribute field monsters first to
        free a Zone; otherwise the fewest (highest-Level) Tributes."""
        free = any(i is None for i in state.players[controller].monster_zones)
        ranked = sorted(
            candidates,
            key=lambda i: (
                (state.inst(i).zone is not Zone.MONSTER) if not free else False,
                -(state.inst(i).card.level or 0),
            ),
        )
        chosen, total = [], 0
        for i in ranked:
            if total >= required:
                break
            chosen.append(i)
            total += state.inst(i).card.level or 0
        return tuple(chosen)


class RandomAgent(Agent):
    """Picks uniformly at random. Useful for fuzzing every rules path."""

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def decide(self, state: GameState, legal: list[Action]) -> Action:
        return self.rng.choice(legal)

    def respond(self, state: GameState, options: list[Action], event):
        return self.rng.choice([*options, None])

    def choose_targets(self, state: GameState, source_iid: int, spec, candidates: list[int]):
        hi = min(spec.count, len(candidates))
        n = self.rng.randint(1, hi) if spec.up_to and hi >= 1 else hi
        return tuple(self.rng.sample(candidates, n))

    def choose_card(self, state: GameState, prompt: str, option_iids: list[int]):
        return self.rng.choice(option_iids) if option_iids else None

    def choose_discards(self, state: GameState, controller: int, candidates: list[int], count: int):
        return tuple(self.rng.sample(candidates, count)) if len(candidates) >= count else tuple(candidates)

    def choose_cost_tributes(self, state: GameState, controller: int, candidates: list[int], count: int):
        return tuple(self.rng.sample(candidates, count)) if len(candidates) >= count else tuple(candidates)

    def choose_tributes(self, state: GameState, controller: int, candidates: list[int], required: int):
        pool = list(candidates)
        self.rng.shuffle(pool)
        chosen, total = [], 0
        for i in pool:
            if total >= required:
                break
            chosen.append(i)
            total += state.inst(i).card.level or 0
        return tuple(chosen)


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
        # Revive the strongest monster we can (Monster Reborn, a Set Call of the
        # Haunted) — any activation that targets a monster sitting in a Graveyard.
        revivals = [
            a
            for a in legal
            if isinstance(a, ActivateSpell)
            and a.targets
            and state.inst(a.targets[0]).zone is Zone.GRAVEYARD
            and state.inst(a.targets[0]).card.is_monster
        ]
        if revivals:
            return max(revivals, key=lambda a: state.inst(a.targets[0]).card.attack or 0)
        # Fusion Summon whenever Polymerization can make something (it's a free big body).
        fusions = [
            a
            for a in legal
            if isinstance(a, ActivateSpell)
            and not a.targets
            and state.inst(a.iid).card.name == "Polymerization"
        ]
        if fusions:
            return fusions[0]
        # Ritual Summon when a Ritual Spell can resolve (another free big body).
        rituals = [
            a
            for a in legal
            if isinstance(a, ActivateSpell)
            and not a.targets
            and any(e.timing == "ritual" for e in state.inst(a.iid).card.effects)
        ]
        if rituals:
            return rituals[0]
        # Special Summon from the hand (Cyber Dragon, etc.) — a free body that
        # doesn't cost the Normal Summon, so grab the biggest available.
        hand_ss = [a for a in legal if isinstance(a, SpecialSummonFromHand)]
        if hand_ss:
            return max(hand_ss, key=lambda a: self._atk(state, a.iid))
        summons = [a for a in legal if isinstance(a, NormalSummon)]
        if summons:
            # biggest ATK, fewest tributes
            return max(summons, key=lambda a: (self._atk(state, a.iid), -len(a.tributes)))
        # No fresh body to deploy — unlock a face-up Gemini instead (Gemini Summon).
        geminis = [a for a in legal if isinstance(a, GeminiSummon)]
        if geminis:
            return geminis[0]
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

    def choose_card(self, state: GameState, prompt: str, option_iids: list[int]):
        # Summon the strongest Fusion Monster on offer.
        if not option_iids:
            return None
        return max(option_iids, key=lambda i: state.inst(i).card.attack or 0)
