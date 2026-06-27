"""The card-effect layer (Slice 1).

An ``Effect`` is the declarative description of one card ability, and a
``Primitive`` is one of the fixed "verbs" its resolution is built from. This is
the layer that grows as we add cards — the engine kernel never has to change.

Slice 1 scope: Ignition-timed Spell effects with no cost and no targeting
(Pot of Greed, Dark Hole, Raigeki). Targeting, costs, triggers, and the Chain
arrive in later slices; the shape here is chosen to extend into them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import GameState

# Player references resolved relative to the effect's controller.
SELF = "self"
OPPONENT = "opponent"


@dataclass
class EffectContext:
    """Everything a primitive needs while resolving an effect."""

    state: "GameState"
    controller: int
    source_iid: int
    targets: list[int] = field(default_factory=list)

    def side(self, who: str) -> int:
        return self.controller if who == SELF else self.state.opponent_of(self.controller)


# --------------------------------------------------------------------------- #
#  Primitives — the fixed verb library (grows slowly, deliberately)
# --------------------------------------------------------------------------- #
class Primitive:
    def execute(self, ctx: EffectContext) -> None:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class Draw(Primitive):
    player: str = SELF
    count: int = 1

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.draw(ctx.side(self.player), self.count)


@dataclass(frozen=True)
class DestroyAllMonsters(Primitive):
    """Destroy every monster, or only one side's. (Slice 1: == send to GY.)"""

    side: str | None = None  # None = both players, else SELF / OPPONENT

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        victims = [
            iid
            for pl in players
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None
        ]
        for iid in victims:
            ctx.state.send_to_graveyard(iid)


# --------------------------------------------------------------------------- #
#  Effect — a card ability
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Effect:
    speed: int = 1
    timing: str = "ignition"  # slice 1: only "ignition"
    resolve: tuple[Primitive, ...] = ()
