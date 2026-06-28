"""The card-effect layer.

An ``Effect`` is the declarative description of one card ability; a ``Primitive``
is one of the fixed "verbs" its resolution is built from. This layer grows as we
add cards — the engine kernel never changes.

Scope:
  * Slice 1 — Ignition Spell effects (Pot of Greed, Dark Hole).
  * Slice 2 — targeting (player-chosen + automatic) and damage.
  * Slice 3 — the Chain: triggers, spell speed, Traps & Quick-Play (Mirror Force,
    Trap Hole, Magic Cylinder, Mystical Space Typhoon).
  * Slice 6 — Special Summon from the Graveyard (Monster Reborn, Call of the
    Haunted), graveyard target pools, and the Call-of-the-Haunted bond.
  * Slice 7 — Field Spells as field-wide stat layers (Sogen/Yami/Gaia Power) and
    a continuous attack restriction (The Dark Door).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from .enums import Attribute, Position, Zone

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
class EquipMod:
    """A continuous ATK/DEF modifier applied while an Equip is face-up & attached.

    Flat: ``EquipMod(atk=1000)``. Scaling: ``EquipMod(scaling="face_up_monsters",
    scale_atk=800, scale_defn=800)`` adds 800 per face-up monster the equip's
    controller has (United We Stand); "spell_trap" counts their Spell/Trap cards
    (Mage Power). Read by ``GameState.effective_attack`` — never stored on the
    monster, so it's always correct as the board changes ("layers").
    """

    atk: int = 0
    defn: int = 0
    scaling: str | None = None  # None | "face_up_monsters" | "spell_trap"
    scale_atk: int = 0
    scale_defn: int = 0


@dataclass(frozen=True)
class FieldMod:
    """A continuous flat ATK/DEF modifier a face-up Field/Continuous Spell radiates
    over every monster on the field that matches its filter (the "field layer").

    A monster qualifies when its race is in ``races`` (empty = any race) *and* its
    attribute is in ``attributes`` (empty = any attribute). ``side``: None = both
    players' monsters (classic Field Spells like Sogen), "self" = only the spell
    controller's monsters, "opponent" = only theirs. Read by
    ``GameState.effective_attack/defense`` — never stored on the monster.
    """

    atk: int = 0
    defn: int = 0
    races: frozenset[str] = frozenset()
    attributes: frozenset[Attribute] = frozenset()
    side: str | None = None  # None | "self" | "opponent"


@dataclass(frozen=True)
class AttackRestriction:
    """A continuous limit on declaring attacks, radiated by a face-up card.

    ``one_per_battle_phase`` (The Dark Door): each player may declare at most one
    attack per Battle Phase. Modelled as data so the kernel stays card-agnostic.
    """

    one_per_battle_phase: bool = False


@dataclass(frozen=True)
class TargetSpec:
    """What an effect targets, chosen by the controller at activation.

    ``where`` names a pool the engine can enumerate: "opponent_monsters",
    "any_monster", "spell_trap_field", "any_graveyard_monster" (either GY),
    "own_graveyard_monster" (the controller's GY only).
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


@dataclass(frozen=True)
class EquipToTarget(Primitive):
    """Attach this Equip card to the targeted monster (it stays on the field)."""

    def execute(self, ctx: EffectContext) -> None:
        equip = ctx.state.inst(ctx.source_iid)
        target = ctx.targets[0] if ctx.targets else None
        from .enums import Zone

        if target is not None and target in ctx.state.cards and ctx.state.inst(target).zone is Zone.MONSTER:
            equip.equipped_to = target
        else:
            ctx.state.send_to_graveyard(ctx.source_iid)  # nothing to equip -> to the GY


# --- Slice 4: monster-effect primitives ---
@dataclass(frozen=True)
class SearchMonsterToHand(Primitive):
    """Sangan (auto): move the best Deck monster with ATK <= max_atk to hand, then shuffle."""

    max_atk: int = 1500

    def execute(self, ctx: EffectContext) -> None:
        player = ctx.state.players[ctx.controller]
        eligible = [
            iid
            for iid in player.deck
            if ctx.state.inst(iid).card.is_monster
            and (ctx.state.inst(iid).card.attack or 0) <= self.max_atk
        ]
        if eligible:
            best = max(eligible, key=lambda i: ctx.state.inst(i).card.attack or 0)
            player.deck.remove(best)
            player.hand.append(best)
            ctx.state.inst(best).zone = Zone.HAND
        ctx.state.rng.shuffle(player.deck)


@dataclass(frozen=True)
class ReturnSpellFromGraveyardToHand(Primitive):
    """Magician of Faith (auto): return the most recently used Spell from your GY to hand."""

    def execute(self, ctx: EffectContext) -> None:
        player = ctx.state.players[ctx.controller]
        spells = [iid for iid in player.graveyard if ctx.state.inst(iid).card.is_spell]
        if not spells:
            return
        iid = spells[-1]
        player.graveyard.remove(iid)
        player.hand.append(iid)
        ctx.state.inst(iid).zone = Zone.HAND


# --- Slice 6: Special Summon from the Graveyard ---
@dataclass(frozen=True)
class SpecialSummonFromGraveyard(Primitive):
    """Special Summon the targeted Graveyard monster to the controller's side.

    The monster arrives face-up Attack (Monster Reborn also allows Defense; we
    keep Attack for now). With ``link`` set (Call of the Haunted), the source card
    and the summoned monster are bonded both ways: if either later leaves the
    field, ``GameState`` / the engine destroy the other (see ``_cleanup_linked``).
    The summon fails quietly with no free Monster Zone or no valid target.
    """

    link: bool = False

    def execute(self, ctx: EffectContext) -> None:
        target = ctx.targets[0] if ctx.targets else None
        if target is None or target not in ctx.state.cards:
            return
        inst = ctx.state.inst(target)
        if inst.zone is not Zone.GRAVEYARD or not inst.card.is_monster:
            return
        index = ctx.state.first_empty_monster_zone(ctx.controller)
        if index is None:
            return
        ctx.state.place_monster(target, ctx.controller, index, Position.FACE_UP_ATTACK)
        inst.summoned_this_turn = True
        if self.link:
            ctx.state.inst(ctx.source_iid).linked_to = target
            inst.linked_to = ctx.source_iid


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
