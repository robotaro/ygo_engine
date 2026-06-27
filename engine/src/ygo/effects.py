"""The card-effect layer.

An ``Effect`` is the declarative description of one card ability; a ``Primitive``
is one of the fixed "verbs" its resolution is built from. This layer grows as we
add cards — the engine kernel never changes.

Scope:
  * Slice 1 — Ignition Spell effects (Pot of Greed, Dark Hole).
  * Slice 2 — targeting (player-chosen + automatic) and damage.
  * Slice 3 — the Chain: triggers, spell speed, Traps & Quick-Play (Mirror Force,
    Trap Hole, Magic Cylinder, Mystical Space Typhoon).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from .enums import Position

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
    event: dict | None = None  # the triggering event, for Trigger effects

    def side(self, who: str) -> int:
        return self.controller if who == SELF else self.state.opponent_of(self.controller)


@dataclass(frozen=True)
class TargetSpec:
    """What an effect targets, chosen by the controller at activation.

    ``where`` names a pool the engine can enumerate: "opponent_monsters",
    "any_monster", "spell_trap_field".
    """

    count: int = 1
    where: str = "opponent_monsters"


@dataclass(frozen=True)
class Trigger:
    """When a reactive (Trigger-timed) effect may be activated.

    It fires in response to a game event of ``kind`` caused ``by`` the opponent
    (or self). ``subject`` names an event field to auto-target ("monster",
    "attacker"); ``min_atk`` is an optional gate (e.g. Trap Hole needs ATK >= 1000).
    """

    kind: str  # "summon" | "attack_declared"
    by: str = OPPONENT
    subject: str | None = None
    min_atk: int | None = None


# --------------------------------------------------------------------------- #
#  Primitives — the fixed verb library
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
    """Destroy every monster, or only one side's."""

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


@dataclass(frozen=True)
class DestroyTargets(Primitive):
    """Destroy whatever the effect targeted."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.send_to_graveyard(iid)


@dataclass(frozen=True)
class DestroyLowestAtkOpponentMonster(Primitive):
    """Fissure: destroy the opponent's face-up monster with the lowest ATK."""

    def execute(self, ctx: EffectContext) -> None:
        opp = ctx.state.opponent_of(ctx.controller)
        faceup = [
            iid
            for iid in ctx.state.players[opp].monster_zones
            if iid is not None and ctx.state.inst(iid).is_face_up
        ]
        if not faceup:
            return
        victim = min(faceup, key=lambda i: ctx.state.inst(i).card.attack or 0)
        ctx.state.send_to_graveyard(victim)


@dataclass(frozen=True)
class SwitchTargetsToAttack(Primitive):
    """Stop Defense: flip the target face-up into Attack Position."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in ctx.targets:
            ctx.state.inst(iid).position = Position.FACE_UP_ATTACK


@dataclass(frozen=True)
class InflictDamage(Primitive):
    """Reduce a player's Life Points by a fixed amount (burn)."""

    player: str = OPPONENT
    amount: int = 0

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.players[ctx.side(self.player)].life_points -= self.amount


# --- Slice 3: reactive primitives (read the triggering event) ---
@dataclass(frozen=True)
class NegateAttack(Primitive):
    """Stop the current attack from dealing damage / continuing."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.attack_negated = True


@dataclass(frozen=True)
class DestroyAttackingAttackPositionMonsters(Primitive):
    """Mirror Force: destroy all the attacking player's Attack-Position monsters."""

    def execute(self, ctx: EffectContext) -> None:
        attacker_player = (ctx.event or {}).get("player", ctx.state.opponent_of(ctx.controller))
        victims = [
            iid
            for iid in ctx.state.players[attacker_player].monster_zones
            if iid is not None and ctx.state.inst(iid).position is Position.FACE_UP_ATTACK
        ]
        for iid in victims:
            ctx.state.send_to_graveyard(iid)


@dataclass(frozen=True)
class DamageEqualToAttackerAtk(Primitive):
    """Magic Cylinder: inflict the attacking monster's ATK to the attacking player."""

    def execute(self, ctx: EffectContext) -> None:
        event = ctx.event or {}
        attacker = event.get("attacker")
        attacker_player = event.get("player", ctx.state.opponent_of(ctx.controller))
        if attacker is None or attacker not in ctx.state.cards:
            return
        dmg = ctx.state.inst(attacker).card.attack or 0
        ctx.state.players[attacker_player].life_points -= dmg


# --------------------------------------------------------------------------- #
#  Effect — a card ability
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Effect:
    speed: int = 1
    # "ignition" (you choose, your Main Phase) | "quick" (any priority) | "trigger"
    timing: str = "ignition"
    trigger: Trigger | None = None
    target: TargetSpec | None = None
    # Optional activation gate: (state, controller) -> bool.
    condition: Callable[["GameState", int], bool] | None = None
    resolve: tuple[Primitive, ...] = ()
