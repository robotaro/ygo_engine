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

from .enums import Attribute, Position, SpellTrapProperty, Zone

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
class UnionMod:
    """Marks a Union monster and which monsters it may equip *itself* to. A Union
    can, once per turn, equip to a valid host you control (becoming an Equip Card)
    or unequip and Special Summon itself back. ``host_names`` restricts valid hosts
    to those card names (empty = any face-up monster you control); ``host_races``
    restricts by race. The ATK/DEF boost it grants while equipped is a separate
    ``EquipMod`` in the same ``continuous`` list, read through the normal Equip
    layer once the Union sits (attached) in a Spell/Trap zone."""

    host_names: frozenset[str] = frozenset()
    host_races: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SelfStatMod:
    """A continuous ATK/DEF modifier a face-up monster applies to *itself* (the
    monster's own "layer"). Used for effects like Goggle Golem ("the original ATK
    of this card becomes 2100" — a flat self-boost). Read by
    ``GameState.effective_attack/defense`` straight off the monster's own
    ``continuous`` list, and suppressed while the monster's effect is inactive
    (a Gemini that hasn't been Gemini Summoned yet)."""

    atk: int = 0
    defn: int = 0


@dataclass(frozen=True)
class HandSpecialSummon:
    """A monster's built-in ability to Special Summon *itself from the hand* during
    its controller's Main Phase, when a board condition holds (Cyber Dragon, The
    Fiend Megacyber). It is *not* a Chain activation: ``moves`` enumerates it as a
    ``SpecialSummonFromHand`` action — parallel to a Normal Summon, but it does not
    use up the turn's Normal Summon. ``condition`` is ``(state, controller) ->
    bool`` (None = always allowed); ``position`` is the battle position the monster
    arrives in (face-up Attack across the whole v6.0 pool). Carried on its own
    ``CardDef.hand_summon`` slot, not in ``effects``."""

    condition: "Callable[[GameState, int], bool] | None" = None
    position: Position = Position.FACE_UP_ATTACK


@dataclass(frozen=True)
class Piercing:
    """A face-up monster's continuous rider: when it attacks a Defense Position
    monster and its ATK exceeds the target's DEF, the excess (ATK - DEF) is dealt
    to the defending player as battle damage (Dark Driceratops, Mad Sword Beast).
    Read by the battle step off the attacker's own ``continuous`` list; suppressed
    while the monster's effect is inactive (an un-Summoned Gemini)."""


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
    attack per Battle Phase. ``min_atk_cannot_attack`` (Messenger of Peace): no
    monster whose *effective* ATK is at or above this value may declare an attack
    (both players). Modelled as data so the kernel stays card-agnostic.
    """

    one_per_battle_phase: bool = False
    min_atk_cannot_attack: int | None = None


@dataclass(frozen=True)
class StandbyUpkeep:
    """Something a face-up card does at the start of a Standby Phase (Slice 8).

    The engine's Standby hook reads these off *every* face-up card — monster,
    Continuous Spell/Trap, or Field Spell alike — so the behaviour isn't tied to
    a card type (the engine stays card-agnostic). ``whose`` selects which Standby
    Phases it fires on:

      * "controller"  — only the card controller's own Standby Phase
        (Messenger of Peace's cost, Cure Mermaid's recovery).
      * "turn_player" — every Standby Phase, always hitting the active player
        (Burning Land's 500 to whoever's turn it is).
      * "opponent"    — only the controller's *opponent's* Standby Phase, and the
        opponent is the beneficiary (Snatch Steal's 1000 LP to its victim).

    Exactly one knob is set per instance:
      * ``pay_life``  — the beneficiary must pay this to keep the card; if they
        cannot (it would leave them at 0 LP or below), the card is destroyed.
      * ``gain_life`` — the beneficiary gains this much LP.
      * ``burn_life`` — the active (turn) player loses this much LP.
    """

    pay_life: int = 0
    gain_life: int = 0
    burn_life: int = 0
    whose: str = "controller"  # "controller" | "turn_player" | "opponent"


@dataclass(frozen=True)
class DrawTrigger:
    """A face-up card's reaction to its controller drawing (Slice 10).

    The controller gains ``gain_life`` LP each time they draw a card(s) — once per
    draw, regardless of how many cards (Solemn Wishes). Read by the engine after
    every draw; never stored on the card.
    """

    gain_life: int = 0


@dataclass(frozen=True)
class TargetSpec:
    """What an effect targets, chosen by the controller at activation.

    ``where`` names a pool the engine can enumerate: "opponent_monsters",
    "any_monster", "spell_trap_field", "any_graveyard_monster" (either GY),
    "own_graveyard_monster" (the controller's GY only).

    ``races`` / ``attributes`` optionally narrow a monster pool to those races
    (e.g. an Equip that may only attach to a Spellcaster) or attributes — empty
    means "any".
    """

    count: int = 1
    where: str = "opponent_monsters"
    races: frozenset = frozenset()
    attributes: frozenset = frozenset()
    face_up: bool = False  # restrict to face-up monsters (e.g. Soul Taker)
    defense_position: bool = False  # restrict to Defense Position monsters (Shield Crush)
    up_to: bool = False  # ``count`` is a maximum — choose 1..count (Penguin Soldier)


@dataclass(frozen=True)
class CardFilter:
    """A predicate over a *printed* card, for fetching from the Deck (Reinforcement
    of the Army, Terraforming, Fusion Sage). Every set criterion must hold (AND);
    an unset criterion is ignored.

    ``card_kind``: None | "monster" | "spell" | "trap" | "field_spell" |
    "normal_monster". ``names`` matches the exact card name (any of); ``name_contains``
    matches an archetype substring (any of); ``races`` / ``attributes`` narrow a
    monster; ``min_level`` / ``max_level`` bound a monster's Level.
    """

    names: frozenset = frozenset()
    name_contains: frozenset = frozenset()
    races: frozenset = frozenset()
    attributes: frozenset = frozenset()
    card_kind: str | None = None
    min_level: int | None = None
    max_level: int | None = None

    def matches(self, card) -> bool:
        if self.names and card.name not in self.names:
            return False
        if self.name_contains and not any(s in card.name for s in self.name_contains):
            return False
        if self.races and card.race not in self.races:
            return False
        if self.attributes and card.attribute not in self.attributes:
            return False
        if self.min_level is not None and (card.level or 0) < self.min_level:
            return False
        if self.max_level is not None and (card.level or 0) > self.max_level:
            return False
        kind = self.card_kind
        if kind == "monster" and not card.is_monster:
            return False
        if kind == "spell" and not card.is_spell:
            return False
        if kind == "trap" and not card.is_trap:
            return False
        if kind == "field_spell" and not (card.is_spell and card.subtype is SpellTrapProperty.FIELD):
            return False
        if kind == "normal_monster" and not card.is_vanilla:
            return False
        return True


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
#  Dynamic values — an effect amount computed from the board at resolution time
# --------------------------------------------------------------------------- #
class ValueSource:
    """A number computed when an effect resolves, instead of a fixed constant.

    ``InflictDamage`` / ``GainLifePoints`` read either their flat ``amount`` or, if
    one is given, a ``value`` source — the "equal to its ATK" and "for each ..."
    cards. Each subclass returns one int from the ``EffectContext``.
    """

    def value(self, ctx: EffectContext) -> int:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class TargetAttack(ValueSource):
    """The (effective) ATK of a targeted monster; ``index`` picks which target (0 =
    the first/only one). For "equal to its ATK" effects whose value is the monster
    the effect points at — including Traps that auto-target the attacking monster
    (Draining Shield, Enchanted Javelin). 0 if that target has already left play."""

    index: int = 0

    def value(self, ctx: EffectContext) -> int:
        if self.index >= len(ctx.targets):
            return 0
        iid = ctx.targets[self.index]
        if iid not in ctx.state.cards:
            return 0
        return ctx.state.effective_attack(iid)


def _tributed_atk(ctx: EffectContext) -> int:
    """Sum of the printed ATK of the monster(s) Tributed as this card's activation
    cost — read off the source card's recorded ``tributed_iids``. Printed (base)
    ATK, since the tributed monster is now in the Graveyard."""
    src = ctx.state.cards.get(ctx.source_iid)
    if src is None:
        return 0
    return sum(
        (ctx.state.inst(i).card.attack or 0)
        for i in src.tributed_iids
        if i in ctx.state.cards
    )


@dataclass(frozen=True)
class TributedAttack(ValueSource):
    """The (original/printed) ATK of the monster Tributed to pay this card's cost
    (Spiritual Fire Art - Kurenai: "damage equal to that monster's original ATK").
    For a multi-Tribute cost it sums them."""

    def value(self, ctx: EffectContext) -> int:
        return _tributed_atk(ctx)


@dataclass(frozen=True)
class CountTimes(ValueSource):
    """``per`` × the number of cards in a named pool — the "for each ..." burn/heal
    cards (Just Desserts, Secret Barrel, Cemetary Bomb, D.D. Dynamite, Gift of The
    Mystical Elf). Pools are resolved relative to the effect's controller."""

    per: int = 0
    pool: str = "opponent_monsters"

    def value(self, ctx: EffectContext) -> int:
        return self.per * _count_pool(ctx, self.pool)


def _field_card_count(state: "GameState", player: int) -> int:
    """Cards ``player`` controls on the field: their Monster + Spell/Trap zones,
    plus a Field Spell if any."""
    p = state.players[player]
    n = sum(1 for i in p.monster_zones if i is not None)
    n += sum(1 for i in p.spell_trap_zones if i is not None)
    if p.field_zone is not None:
        n += 1
    return n


def _count_pool(ctx: EffectContext, pool: str) -> int:
    """Resolve a CountTimes pool name to a card count, relative to the controller."""
    s = ctx.state
    opp = s.opponent_of(ctx.controller)
    if pool == "opponent_monsters":
        return sum(1 for i in s.players[opp].monster_zones if i is not None)
    if pool == "all_monsters":
        return sum(1 for pl in (0, 1) for i in s.players[pl].monster_zones if i is not None)
    if pool == "opponent_hand":
        return len(s.players[opp].hand)
    if pool == "opponent_hand_and_field":
        return len(s.players[opp].hand) + _field_card_count(s, opp)
    if pool == "opponent_graveyard":
        return len(s.players[opp].graveyard)
    if pool == "opponent_banished":
        return len(s.players[opp].banished)
    return 0


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
    """Destroy every monster, or only one side's. ``face_up_only`` restricts it to
    face-up monsters (Lightning Vortex destroys only face-up monsters)."""

    side: str | None = None  # None = both players, else SELF / OPPONENT
    face_up_only: bool = False

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        victims = [
            iid
            for pl in players
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None and (not self.face_up_only or ctx.state.inst(iid).is_face_up)
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
class BanishTargets(Primitive):
    """Banish (remove from play) whatever the effect targeted — to the owner's
    banished pile instead of the Graveyard (Dark Core, Dimensional Prison). For a
    card that 'destroys then banishes' (Bottomless Trap Hole) the end state is the
    same: the card ends up banished, so we move it there directly."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.banish(iid)


@dataclass(frozen=True)
class BounceTargetsToHand(Primitive):
    """Return the targeted cards to their owners' hands (Compulsory Evacuation
    Device, Hane-Hane, Gravekeeper's Guard)."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.return_to_hand(iid)


@dataclass(frozen=True)
class BounceTargetsToDeck(Primitive):
    """Return the targeted cards to their owners' Decks — on top by default (Back
    to Square One, Phoenix Wing Wind Blast)."""

    to_top: bool = True

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.return_to_deck(iid, to_top=self.to_top)


@dataclass(frozen=True)
class ReturnAllSpellTrapsToHand(Primitive):
    """Giant Trunade: return every Spell/Trap on the field (both players', including
    Field Spells and the activating card itself) to its owner's hand."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        victims: list[int] = []
        for pl in (0, 1):
            victims += [i for i in s.players[pl].spell_trap_zones if i is not None]
            if s.players[pl].field_zone is not None:
                victims.append(s.players[pl].field_zone)
        for iid in victims:
            s.return_to_hand(iid)


@dataclass(frozen=True)
class DestroyAllFieldSpells(Primitive):
    """Burning Land: destroy every Field Spell on the field (both players')."""

    def execute(self, ctx: EffectContext) -> None:
        for player in ctx.state.players:
            fz = player.field_zone
            if fz is not None:
                ctx.state.send_to_graveyard(fz)


@dataclass(frozen=True)
class DestroyAllSpellTraps(Primitive):
    """Heavy Storm (``side=None``) / Harpie's Feather Duster (``side=OPPONENT``):
    destroy every Spell/Trap on the field — the Spell & Trap zones plus the Field
    Spell zone — for both players or only one side."""

    side: str | None = None  # None = both, else SELF / OPPONENT

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        victims: list[int] = []
        for pl in players:
            victims += [i for i in ctx.state.players[pl].spell_trap_zones if i is not None]
            if ctx.state.players[pl].field_zone is not None:
                victims.append(ctx.state.players[pl].field_zone)
        for iid in victims:
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
class ModifyStatsTemporary(Primitive):
    """Add a temporary ATK/DEF change to each targeted monster until the end of this
    turn (combat tricks like Rush Recklessly). The deltas accumulate on the monster
    and the engine clears them in the End Phase."""

    atk: int = 0
    defn: int = 0

    def execute(self, ctx: EffectContext) -> None:
        for iid in ctx.targets:
            inst = ctx.state.cards.get(iid)
            if inst is not None and inst.zone is Zone.MONSTER:
                inst.temp_atk += self.atk
                inst.temp_def += self.defn


@dataclass(frozen=True)
class DestroyHighestDefOpponentMonster(Primitive):
    """Smashing Ground: destroy the opponent's face-up monster with the highest DEF."""

    def execute(self, ctx: EffectContext) -> None:
        opp = ctx.state.opponent_of(ctx.controller)
        faceup = [
            iid
            for iid in ctx.state.players[opp].monster_zones
            if iid is not None and ctx.state.inst(iid).is_face_up
        ]
        if faceup:
            ctx.state.send_to_graveyard(max(faceup, key=ctx.state.effective_defense))


@dataclass(frozen=True)
class DestroyHighestAtkMonster(Primitive):
    """Hammer Shot: destroy the face-up Attack-Position monster (either side) with
    the highest ATK."""

    def execute(self, ctx: EffectContext) -> None:
        cands = [
            iid
            for pl in (0, 1)
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None and ctx.state.inst(iid).position is Position.FACE_UP_ATTACK
        ]
        if cands:
            ctx.state.send_to_graveyard(max(cands, key=ctx.state.effective_attack))


@dataclass(frozen=True)
class DestroyFaceUpMonstersWithDefAtMost(Primitive):
    """Burst Breath: destroy every face-up monster on the field whose (effective)
    DEF is at or below ``threshold`` — a dynamic value (the ATK of the monster
    Tributed as the cost). With no threshold source it destroys nothing."""

    threshold: ValueSource | None = None

    def execute(self, ctx: EffectContext) -> None:
        limit = self.threshold.value(ctx) if self.threshold is not None else -1
        victims = [
            iid
            for pl in (0, 1)
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None
            and ctx.state.inst(iid).is_face_up
            and ctx.state.effective_defense(iid) <= limit
        ]
        for iid in victims:
            ctx.state.send_to_graveyard(iid)


@dataclass(frozen=True)
class SwitchTargetsToAttack(Primitive):
    """Stop Defense: flip the target face-up into Attack Position."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in ctx.targets:
            ctx.state.inst(iid).position = Position.FACE_UP_ATTACK


@dataclass(frozen=True)
class InflictDamage(Primitive):
    """Reduce a player's Life Points (burn). The amount is the flat ``amount``, or
    — when given — a dynamic ``value`` computed at resolution time."""

    player: str = OPPONENT
    amount: int = 0
    value: ValueSource | None = None

    def execute(self, ctx: EffectContext) -> None:
        amount = self.value.value(ctx) if self.value is not None else self.amount
        ctx.state.players[ctx.side(self.player)].life_points -= amount


@dataclass(frozen=True)
class GainLifePoints(Primitive):
    """Increase a player's Life Points (the healing cards). The amount is the flat
    ``amount``, or — when given — a dynamic ``value`` computed at resolution time."""

    player: str = SELF
    amount: int = 0
    value: ValueSource | None = None

    def execute(self, ctx: EffectContext) -> None:
        amount = self.value.value(ctx) if self.value is not None else self.amount
        ctx.state.players[ctx.side(self.player)].life_points += amount


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
class SearchFromDeck(Primitive):
    """Add 1 card matching ``filter`` from the controller's Deck to their hand, then
    shuffle (Reinforcement of the Army, Terraforming, Fusion Sage). The pick is
    deterministic — the highest-ATK match (so a monster fetch grabs the strongest
    eligible body; non-monsters tie at 0 and the first in Deck order is taken),
    mirroring ``SearchMonsterToHand`` since primitives have no agent to ask.
    Activation is gated by a condition so there is always a match when it resolves;
    with none it does nothing."""

    filter: CardFilter = CardFilter()

    def execute(self, ctx: EffectContext) -> None:
        player = ctx.state.players[ctx.controller]
        eligible = [i for i in player.deck if self.filter.matches(ctx.state.inst(i).card)]
        if eligible:
            pick = max(eligible, key=lambda i: ctx.state.inst(i).card.attack or 0)
            player.deck.remove(pick)
            player.hand.append(pick)
            ctx.state.inst(pick).zone = Zone.HAND
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
        if inst.card.is_spirit:
            return  # Spirit monsters can never be Special Summoned
        index = ctx.state.first_empty_monster_zone(ctx.controller)
        if index is None:
            return
        ctx.state.place_monster(target, ctx.controller, index, Position.FACE_UP_ATTACK)
        inst.summoned_this_turn = True
        if self.link:
            ctx.state.inst(ctx.source_iid).linked_to = target
            inst.linked_to = ctx.source_iid


# --- Slice 9: take-control ---
@dataclass(frozen=True)
class TakeControl(Primitive):
    """Move the targeted monster to the controller's side of the field.

    ``until_end_of_turn`` (Change of Heart): control returns to the original
    controller during this turn's End Phase. ``equip`` (Snatch Steal): the source
    Equip card stays attached and control reverts when that Equip leaves the
    field. Keeps the monster's battle position ("regardless of position"). Fails
    quietly (the Equip going to the Graveyard) if the taker has no free Monster
    Zone or the target is gone.
    """

    until_end_of_turn: bool = False
    equip: bool = False

    def execute(self, ctx: EffectContext) -> None:
        target = ctx.targets[0] if ctx.targets else None
        monster = ctx.state.cards.get(target) if target is not None else None
        taker = ctx.controller
        ok = monster is not None and monster.zone is Zone.MONSTER and monster.controller != taker
        index = ctx.state.first_empty_monster_zone(taker) if ok else None
        if not ok or index is None:
            if self.equip:
                ctx.state.send_to_graveyard(ctx.source_iid)  # nothing to take -> to the GY
            return
        original = monster.controller
        ctx.state.move_control(target, taker, index)
        monster.control_reverts_to = original
        if self.until_end_of_turn:
            monster.control_until_end_of_turn = ctx.state.turn_count
        if self.equip:
            ctx.state.inst(ctx.source_iid).equipped_to = target
            monster.control_equip_iid = ctx.source_iid


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
    # Activation cost: discard this many cards from the hand (paid at activation,
    # before resolution). Gated into legal enumeration — the action is only offered
    # when the controller has enough discard fodder (other than the card itself).
    discard_cost: int = 0
    # Activation cost: Tribute this many monsters you control (Spiritual Fire Art,
    # Icarus Attack, Burst Breath). ``tribute_races`` / ``tribute_attributes``
    # restrict which monsters qualify (empty = any). The Tributed monsters are
    # recorded on the source card so the payload can read their printed stats.
    tribute_cost: int = 0
    tribute_races: frozenset = frozenset()
    tribute_attributes: frozenset = frozenset()
    resolve: tuple[Primitive, ...] = ()
