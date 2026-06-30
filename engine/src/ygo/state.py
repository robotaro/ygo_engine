"""The mutable game state — the single source of truth for a duel in progress.

Design:
  * Every card on the table is a ``CardInstance`` with a unique ``iid``.
  * ``GameState.cards`` is the one place instances live; zones (deck, hand,
    monster zones, ...) hold only ``iid``s. Moving a card is then just editing
    list membership + a couple of fields on the instance — no duplication, and
    serialization is trivial.
  * RNG is seeded and carried on the state, so duels are deterministic and
    reproducible (essential for replays and bot self-play).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cards import CardDef
from .effects import (
    ActivationLock,
    AttackLifeCost,
    AttackTributeCost,
    BanishInsteadOfGraveyard,
    BurnOnHandDiscard,
    OpponentMillToAttack,
    CannotBeSpecialSummoned,
    CannotAttackUnlessControlRace,
    HalvesBattleDamageDealt,
    SameNameAnthem,
    NoBattleDamageWhileUmi,
    AttackTargetProtection,
    BattleIndestructible,
    CanAttackDirectly,
    CardEffectNegation,
    DebuffsAttackTargetAtk,
    DestroyAttachedEquips,
    EquipMod,
    FieldMod,
    SafeAttacker,
    DamageStepBonus,
    MultiAttacker,
    NoHandLimit,
    Piercing,
    SelfStatMod,
    SpecialSummonLock,
    SpellCounterHolder,
)
from .enums import Phase, Position, SpellTrapProperty, Zone

STARTING_LIFE_POINTS = 8000
MAX_MONSTER_ZONES = 5
MAX_SPELL_TRAP_ZONES = 5

# Holding all five of these in hand at once wins the Duel (Exodia the Forbidden One) —
# checked by GameState.exodia_winner after every hand change. A genuine alternate win
# condition, so it lives in the kernel rather than as a card effect.
EXODIA_PIECES = frozenset(
    {
        "Exodia the Forbidden One",
        "Right Arm of the Forbidden One",
        "Left Arm of the Forbidden One",
        "Right Leg of the Forbidden One",
        "Left Leg of the Forbidden One",
    }
)

# Cards that count as "Umi" on the field — the original plus those whose name is always
# treated as "Umi" (A Legendary Ocean). Several WATER cards key off a face-up "Umi".
_UMI_NAMES = frozenset({"Umi", "A Legendary Ocean"})


# The field→Graveyard trigger kinds, all drained off the ``gy_from_field`` queue:
# any send ("sent_to_gy_from_field"), and the destruction-only refinements that read the
# stamped death cause — "destroyed_by_battle", "destroyed_by_effect", and the unified
# "destroyed" (battle OR effect, but not a tribute/discard/mill send).
_GY_TRIGGER_KINDS = frozenset(
    {"sent_to_gy_from_field", "destroyed_by_battle", "destroyed_by_effect", "destroyed"}
)


def _has_gy_trigger(card: CardDef) -> bool:
    """Whether a card carries a field→Graveyard trigger (Black Pendant's destroyed
    burn, Horn of the Unicorn) — so non-monsters with one get queued to ``gy_from_field``
    (monsters are always queued)."""
    return any(
        e.timing == "trigger" and e.trigger is not None and e.trigger.kind in _GY_TRIGGER_KINDS
        for e in card.effects
    )


@dataclass
class CardInstance:
    """A specific copy of a card as it exists in a duel."""

    iid: int
    card: CardDef
    owner: int  # player index (0/1) who owns the card (it returns here)
    controller: int  # player index whose side it is currently on
    zone: Zone
    zone_index: int = 0  # slot index within a positional zone (monster/spell-trap)
    position: Position | None = None  # only meaningful on the field

    # Per-turn flags (reset by the engine each turn).
    summoned_this_turn: bool = False
    attacked_this_turn: bool = False
    attacks_made_this_turn: int = 0  # how many attacks declared this turn (multi-attackers)
    position_changed_this_turn: bool = False
    # True once this monster has destroyed an opponent's monster by battle this turn
    # (Insect Queen's End-Phase token recursion reads it). A per-turn flag.
    destroyed_a_monster_by_battle_this_turn: bool = False
    # The turn on which a Spell/Trap was Set face-down (it can't activate that turn).
    set_on_turn: int | None = None
    # For an Equip card: the iid of the monster it is attached to.
    equipped_to: int | None = None
    # The monster this Equip was attached to at the moment it was sent to the GY —
    # captured by send_to_graveyard so a "when this leaves the field" parting effect can
    # still find it (Big Bang Shot banishes it). Cleared whenever the card enters a zone.
    last_equipped_to: int | None = None
    # A two-way bond (Call of the Haunted): if either partner leaves the field,
    # the other is destroyed. Set on both the card and the monster it summoned.
    linked_to: int | None = None
    # Take-control bookkeeping (Slice 9). While a monster is on loan,
    # ``control_reverts_to`` is the player it returns to. ``control_until_end_of_turn``
    # (Change of Heart) is the turn whose End Phase ends the loan;
    # ``control_equip_iid`` (Snatch Steal) is the Equip granting control — control
    # reverts when that Equip leaves the field.
    control_reverts_to: int | None = None
    control_until_end_of_turn: int | None = None
    control_equip_iid: int | None = None
    # Gemini (Dual) monster: it's a Normal Monster (no effect) until a 2nd Normal
    # Summon ("Gemini Summon") flips this True. Reset when it leaves the field.
    gemini_unlocked: bool = False
    # Union monster: the turn it last equipped/unequipped itself (its once-per-turn
    # gate). Turn-stamped, so it expires on its own; reset when it leaves the field.
    union_acted_on_turn: int | None = None
    # Temporary ATK/DEF deltas (combat tricks "until the end of this turn"). They
    # accumulate here and the engine clears them in the End Phase.
    temp_atk: int = 0
    temp_def: int = 0
    # Permanent ATK/DEF deltas stamped by an effect and carried for the monster's life
    # on the field (Slate Warrior's "gains 500" / "the destroyer loses 500", Zombyra's
    # "loses 200 each time it destroys"). Never cleared by the turn reset.
    perm_atk: int = 0
    perm_def: int = 0
    # The monster(s) Tributed as this card's activation cost (Spiritual Fire Art,
    # Burst Breath). Recorded when the cost is paid so the payload can read the
    # tributed monster's printed stats after it has gone to the Graveyard.
    tributed_iids: list[int] = field(default_factory=list)
    # Counters sitting on this card, keyed by type ("spell", ...). Cleared when the
    # card leaves the field (Royal Magical Library, Mythical Beast Cerberus).
    counters: dict[str, int] = field(default_factory=dict)
    # True for a card sent to the GY *by battle* this trip (Mystic Tomato & friends
    # recruit only when "destroyed by battle"). Stamped by send_to_graveyard, read
    # by the engine's "destroyed_by_battle" trigger while draining the GY queue.
    died_by_battle: bool = False
    # True for a card destroyed *by a card effect* this trip (vs. a non-destruction send
    # — tribute, discard, mill, cost). Stamped by send_to_graveyard(by_effect=True), which
    # the Destroy* primitives pass; read by the "destroyed_by_effect" and unified
    # "destroyed" triggers (Babycerasaurus, Granadora) while draining the GY queue.
    died_by_effect: bool = False
    # True for a card that was in Defense Position when it was destroyed by battle this
    # trip. Stamped by send_to_graveyard; read by Shinato's "destroyed a Defense-Position
    # monster by battle" burn (its original ATK), which fires just after combat.
    died_in_defense: bool = False
    # True while this monster is face-up on the field having reached it via a Special
    # Summon (vs. Normal/Tribute/Flip Summon or Set). Stamped True in state.special_summon
    # (and on a Token), reset to False by place_monster (Normal Summon/Set) and on leaving
    # the field — read by "destroy all Special Summoned monsters" (Fossil Dyna/Jowgen).
    was_special_summoned: bool = False
    # True while this monster is face-up on the field having reached it via a Tribute
    # Summon (a Normal Summon that tributed 1+ monsters). Stamped in moves._summon,
    # reset by place_monster / on leaving the field — read by "an opponent's monster
    # that was Tribute Summoned declares an attack" (Blast Held by a Tribute).
    was_tribute_summoned: bool = False
    # True while this card sits in a Deck it was *planted* in by an effect (Parasite
    # Paracide buries itself in the opponent's Deck). Its "when drawn" effect fires only
    # for a planted copy — a naturally-drawn copy does nothing — and the flag is consumed
    # the moment that effect resolves.
    planted_in_deck: bool = False
    # The turn this card last activated a "once per turn" Ignition effect. Turn-stamped
    # so it expires on its own; reset when the card leaves the field.
    effect_activated_on_turn: int | None = None
    # The turn an effect disabled this card's attack ("cannot attack the turn this
    # effect is activated"). Turn-stamped; read by attack enumeration.
    attack_disabled_on_turn: int | None = None

    # The last turn_count through which this monster's battle position is frozen
    # (Goblin Attack Force after it attacks). Absolute, so it survives turn resets and
    # expires once turn_count passes it; read by the position-change action enumeration.
    position_locked_until: int | None = None

    # The turn_count whose End Phase this monster is to be destroyed in (Limiter Removal
    # marks the Machines it doubled). Cleared when the card leaves the field.
    destroy_at_end_phase: int | None = None

    @property
    def name(self) -> str:
        return self.card.name

    @property
    def is_face_up(self) -> bool:
        return self.position is not None and self.position.is_face_up

    def reset_turn_flags(self) -> None:
        """Clear the once-per-turn summon/battle bookkeeping — at the start of a turn,
        on a control change, and when the card leaves the field."""
        self.summoned_this_turn = False
        self.attacked_this_turn = False
        self.attacks_made_this_turn = 0
        self.position_changed_this_turn = False
        self.destroyed_a_monster_by_battle_this_turn = False

    @property
    def effects_active(self) -> bool:
        """Whether this card's effects currently function. A Gemini monster is a
        Normal Monster until Gemini Summoned; every other card is always live."""
        return not (self.card.is_gemini and not self.gemini_unlocked)


@dataclass
class PlayerState:
    """One player's side of the board."""

    name: str
    life_points: int = STARTING_LIFE_POINTS

    # Ordered piles (list[-1] == top of deck, the next card drawn).
    deck: list[int] = field(default_factory=list)
    hand: list[int] = field(default_factory=list)
    graveyard: list[int] = field(default_factory=list)
    extra_deck: list[int] = field(default_factory=list)
    banished: list[int] = field(default_factory=list)

    # Positional zones (fixed-length; None == empty slot).
    monster_zones: list[int | None] = field(
        default_factory=lambda: [None] * MAX_MONSTER_ZONES
    )
    spell_trap_zones: list[int | None] = field(
        default_factory=lambda: [None] * MAX_SPELL_TRAP_ZONES
    )
    field_zone: int | None = None

    # Turn-scoped "you take no battle damage for the rest of this turn" immunity (Winged
    # Kuriboh): holds the turn_count it was granted on, so it lapses automatically once the
    # turn advances. Read by GameState.takes_no_battle_damage.
    no_battle_damage_until_turn: int | None = None


@dataclass
class GameState:
    """The complete state of a duel."""

    players: list[PlayerState]
    cards: dict[int, CardInstance] = field(default_factory=dict)
    turn_player: int = 0
    turn_count: int = 1
    phase: Phase = Phase.DRAW
    normal_summon_used: bool = False  # one Normal Summon/Set per turn; reset each turn
    chain: list = field(default_factory=list)  # ChainLink stack, last-in-first-out
    attack_negated: bool = False  # transient flag set while resolving an attack response
    attack_redirect: int | None = None  # a response set a new attack target (Call of the Earthbound)
    reflect_battle_damage: bool = False  # Dimension Wall: my battle damage hits the attacker
    forced_attack_target: int | None = None  # Staunch Defender: attacks this turn must hit only this monster
    # Turn-scoped action locks: "kind:player" -> the last turn_count the lock is active
    # (inclusive). kinds: "special_summon"/"spell"/"trap"/"set" (Guard Dog, Sonic Jammer,
    # Whirlwind Weasel, Searchlightman). Auto-expires by turn; pruned in engine._begin_turn.
    action_locks: dict = field(default_factory=dict)
    gy_from_field: list = field(default_factory=list)  # monsters just sent field->GY (trigger queue)
    pending_draws: list = field(default_factory=list)  # (player, drawn_iids) per draw event — the draw-trigger queue
    # Monsters just Summoned — (iid, summoner, kind) the engine drains to open the
    # opponent's response window + fire the monster's own "when Summoned" trigger (and,
    # for "flip", its Flip Effect). Special Summons are queued by the special_summon
    # chokepoint; Normal/Flip Summons by the engine. Tokens (spawn_on_field) are not.
    summon_events: list = field(default_factory=list)
    # Transient record of the attacker that just dealt battle damage to its opponent —
    # (dealer_iid, amount) — for the engine's "inflicts battle damage" Trigger. Set in
    # _resolve_attack, drained by the engine after the attack, cleared each declaration.
    battle_damage_dealt: tuple | None = None
    # Transient record of (destroyer_iid, destroyed_iid) pairs from the attack just
    # resolved — for the engine's "when this card destroys a monster by battle" SELF
    # Trigger (Masked Chopper, Guardian Angel Joan). Reset each _resolve_attack, drained
    # by the engine after the attack.
    battle_destroyed_by: list = field(default_factory=list)
    # Transient (attacker_iid, defender_iid) of the monster-vs-monster battle just
    # resolved — for the engine's "when this card battles an opponent's monster" Trigger
    # (D.D. Warrior Lady's mutual banish). None on a direct attack. Reset each
    # _resolve_attack, drained by the engine after the attack.
    battle_pair: tuple | None = None
    # Transient (victim_player, amount) of the battle damage the attack just dealt — for
    # the engine's "when you take battle damage" Trap window (Numinous Healer, Attack and
    # Receive, Damage Condenser). At most one player takes battle damage per attack. Reset
    # each _resolve_attack, drained by the engine after the attack.
    battle_damage_taken: tuple | None = None
    # (victim, amount) pairs of EFFECT damage (burn) dealt during the current chain, appended
    # by InflictDamage. Drained by the engine after a chain resolves to open a "when you take
    # damage" window (Numinous Healer / Attack and Receive — but NOT LP costs). Transient.
    effect_damage_pending: list = field(default_factory=list)
    # (player, amount) pairs of LIFE-POINT GAINS, appended by state.gain_life_points (the one
    # sink every healing path routes through). Drained by the engine's "when you gain Life
    # Points" window (Fire Princess) after a chain, a draw-trigger sweep, or the Standby
    # upkeep. Transient.
    lp_gain_pending: list = field(default_factory=list)
    # Player indices that take NO battle damage for the CURRENT attack only (Kuriboh's
    # discard). Reset by the engine at each attack declaration, set by the damage-step
    # window before damage is calculated, read by _resolve_attack's _take_battle_damage.
    battle_damage_prevented: set = field(default_factory=set)
    # Set by an effect to end the current Battle Phase immediately (The Unhappy Maiden);
    # read and reset by the engine's Battle-Phase loop.
    battle_phase_ended: bool = False
    seed: int = 0
    rng: random.Random = field(default_factory=random.Random)
    _next_iid: int = 0

    @classmethod
    def new(cls, player_names: tuple[str, str], seed: int = 0) -> "GameState":
        return cls(
            players=[PlayerState(player_names[0]), PlayerState(player_names[1])],
            seed=seed,
            rng=random.Random(seed),
        )

    # ----- instance creation -----
    def create_instance(self, card: CardDef, owner: int, zone: Zone) -> CardInstance:
        iid = self._next_iid
        self._next_iid += 1
        inst = CardInstance(iid=iid, card=card, owner=owner, controller=owner, zone=zone)
        self.cards[iid] = inst
        return inst

    # ----- lookups -----
    def inst(self, iid: int) -> CardInstance:
        return self.cards[iid]

    def opponent_of(self, player: int) -> int:
        return 1 - player

    # ----- basic pile operations (used by setup; the kernel will extend these) -----
    def shuffle_deck(self, player: int) -> None:
        self.rng.shuffle(self.players[player].deck)

    def draw(self, player: int, count: int = 1) -> list[int]:
        """Draw ``count`` cards from the top of the deck into the hand.

        Returns the iids drawn. Stops early if the deck runs out (the
        deck-out loss condition is the engine's job, not this primitive's).
        """
        p = self.players[player]
        drawn: list[int] = []
        for _ in range(count):
            if not p.deck:
                break
            iid = p.deck.pop()  # top of deck == end of list
            p.hand.append(iid)
            self.cards[iid].zone = Zone.HAND
            self.cards[iid].position = None
            drawn.append(iid)
        if drawn:  # "when you draw a card(s)" fires once per draw event, for the engine to process
            self.pending_draws.append((player, tuple(drawn)))
        return drawn

    # ----- card movement (used by the move/effect layer) -----
    def _remove_from_current_location(self, iid: int) -> None:
        """Detach a card from whatever zone currently holds it."""
        inst = self.cards[iid]
        if inst.zone in (Zone.MONSTER, Zone.SPELL_TRAP, Zone.FIELD):
            owner = self.players[inst.controller]  # field cards sit on the controller's side
            if inst.zone is Zone.MONSTER:
                owner.monster_zones[owner.monster_zones.index(iid)] = None
            elif inst.zone is Zone.SPELL_TRAP:
                owner.spell_trap_zones[owner.spell_trap_zones.index(iid)] = None
            else:
                owner.field_zone = None
        else:
            piles = {
                Zone.HAND: "hand",
                Zone.DECK: "deck",
                Zone.GRAVEYARD: "graveyard",
                Zone.BANISHED: "banished",
                Zone.EXTRA_DECK: "extra_deck",
            }
            getattr(self.players[inst.owner], piles[inst.zone]).remove(iid)

    def place_monster(self, iid: int, player: int, index: int, position: Position) -> None:
        """Put a card into a Monster Zone slot in the given battle position."""
        self._remove_from_current_location(iid)
        inst = self.cards[iid]
        self.players[player].monster_zones[index] = iid
        inst.zone = Zone.MONSTER
        inst.controller = player
        inst.zone_index = index
        inst.position = position
        inst.died_by_battle = False  # a revived monster carries no stale battle-death flag
        inst.died_by_effect = False  # nor a stale effect-destruction flag
        inst.died_in_defense = False  # nor a stale Defense-death flag
        inst.was_special_summoned = False  # Normal Summon/Set; special_summon re-stamps True
        inst.was_tribute_summoned = False  # moves._summon re-stamps True for a Tribute Summon

    def special_summon(
        self, iid: int, player: int, position: Position, *, index: int | None = None
    ) -> bool:
        """The single Special Summon chokepoint for an existing card instance — used by
        every SS route (hand-SS, revival, recruiter, Union re-summon, Fusion, Ritual).

        Honours the Special Summon lock (Barrier Statues / Vanity), finds a free Monster
        Zone (preferring ``index`` when given and empty), places the monster and stamps
        the per-turn summon bookkeeping. Returns True if the monster reached the field,
        or False (a no-op) if a lock barred it or no zone was free. Callers that pay a
        cost first (Fusion/Ritual materials) should also gate on ``special_summon_locked``
        up front so they don't waste the cost on a fizzle. (Tokens are synthesised with
        no source location, so ``CreateToken`` spawns them directly instead.)"""
        inst = self.cards[iid]
        if any(isinstance(m, CannotBeSpecialSummoned) for m in inst.card.continuous):
            return False  # Susa Soldier: a printed restriction — never Special Summonable
        if self.special_summon_locked(player, inst.card):
            return False
        if index is None or self.players[player].monster_zones[index] is not None:
            index = self.first_empty_monster_zone(player)
        if index is None:
            return False
        self.place_monster(iid, player, index, position)
        inst.summoned_this_turn = True
        inst.was_special_summoned = True  # read by "destroy all Special Summoned monsters"
        # Queue the summon so the engine can open the opponent's response window
        # (Bottomless Trap Hole, Black Horn of Heaven) and fire the monster's own
        # "when Special Summoned" Trigger — uniformly, from whatever route summoned it.
        self.summon_events.append((iid, player, "special"))
        return True

    def move_control(self, iid: int, new_controller: int, index: int) -> None:
        """Move a monster already on the field to ``new_controller``'s Monster Zone
        ``index`` — changing control, not ownership — keeping its battle position.
        Resets per-turn flags so it can act normally under its new controller."""
        inst = self.cards[iid]
        self._remove_from_current_location(iid)
        self.players[new_controller].monster_zones[index] = iid
        inst.controller = new_controller
        inst.zone = Zone.MONSTER
        inst.zone_index = index
        inst.reset_turn_flags()

    def swap_control(self, a: int, b: int) -> None:
        """Exchange control of two on-field monsters (Creature Swap, Invader of the
        Throne): each takes the other's Monster Zone on the opposite player's side, a
        permanent swap (ownership unchanged, positions kept). Both are pulled out first
        so a full board on either side cannot deadlock the placement."""
        ia, ib = self.cards[a], self.cards[b]
        pa, za = ia.controller, ia.zone_index
        pb, zb = ib.controller, ib.zone_index
        self._remove_from_current_location(a)
        self._remove_from_current_location(b)
        for iid, player, index in ((a, pb, zb), (b, pa, za)):
            inst = self.cards[iid]
            self.players[player].monster_zones[index] = iid
            inst.controller = player
            inst.zone = Zone.MONSTER
            inst.zone_index = index
            inst.reset_turn_flags()

    def _clear_field_flags(self, inst: "CardInstance") -> None:
        """Reset the per-instance bookkeeping a card carries while on the field."""
        inst.controller = inst.owner
        inst.position = None
        inst.reset_turn_flags()
        inst.set_on_turn = None
        inst.equipped_to = None
        inst.last_equipped_to = None
        inst.linked_to = None
        inst.control_reverts_to = None
        inst.control_until_end_of_turn = None
        inst.control_equip_iid = None
        inst.gemini_unlocked = False  # a Gemini re-locks once it leaves the field
        inst.union_acted_on_turn = None
        inst.counters = {}  # counters fall off when the card leaves the field
        inst.temp_atk = 0
        inst.temp_def = 0
        inst.perm_atk = 0  # permanent stat changes (Zombyra, Slate Warrior, a debuffed
        inst.perm_def = 0  # killer) don't outlive the field — a revived copy is back to base
        inst.died_by_battle = False  # re-stamped by send_to_graveyard if a battle death
        inst.died_by_effect = False  # re-stamped by send_to_graveyard if an effect destruction
        inst.died_in_defense = False  # re-stamped by send_to_graveyard for a Defense battle death
        inst.was_special_summoned = False  # re-stamped by special_summon on a fresh summon
        inst.was_tribute_summoned = False  # re-stamped by moves._summon on a fresh Tribute Summon
        inst.tributed_iids = []  # the tribute-cost record doesn't outlive the field
        inst.effect_activated_on_turn = None  # a revived card may use its once/turn again
        inst.attack_disabled_on_turn = None
        inst.destroy_at_end_phase = None
        inst.position_locked_until = None  # a position lock doesn't outlive the field
        inst.planted_in_deck = False  # a card leaving the field carries no stale plant flag

    def gain_life_points(self, player: int, amount: int) -> None:
        """The single Life-Point GAIN sink (ygopro's Duel.Recover): add ``amount`` to
        ``player``'s Life Points and record the gain so the engine's "when you gain Life
        Points" window (Fire Princess) can react to it. A gain of 0 or less is a no-op and
        records nothing — you cannot "gain" non-positive LP. Every healing path (the
        GainLifePoints primitive, the Standby/draw-trigger upkeep markers) routes through
        here so the window sees them all."""
        if amount <= 0:
            return
        self.players[player].life_points += amount
        self.lp_gain_pending.append((player, amount))

    def takes_no_battle_damage(self, player: int) -> bool:
        """Whether ``player`` is currently immune to battle damage — either for this one
        attack (Kuriboh's discard added them to ``battle_damage_prevented``) or for the
        rest of this turn (Winged Kuriboh set ``no_battle_damage_until_turn`` to the
        current turn). Read at every battle-damage site so the source is one place."""
        if player in self.battle_damage_prevented:
            return True
        if self.players[player].no_battle_damage_until_turn == self.turn_count:
            return True
        # Tornado Wall: no battle damage from attacking monsters while you control Umi.
        if self.controls_face_up_umi(player) and any(
            True for _src, _mod in self.active_markers(NoBattleDamageWhileUmi, (player,))
        ):
            return True
        return False

    def controls_face_up_umi(self, player: int) -> bool:
        """Whether ``player`` controls a face-up "Umi" — or a card always treated as Umi
        (A Legendary Ocean). The enabler several WATER cards key off."""
        for iid in self.field_cards(player, monsters=False):
            inst = self.cards[iid]
            if inst.is_face_up and inst.card.name in _UMI_NAMES:
                return True
        return False

    def send_to_graveyard(self, iid: int, by_battle: bool = False, by_effect: bool = False) -> None:
        """Move a card to its *owner's* Graveyard, clearing field flags. ``by_battle``
        marks a battle destruction so a "destroyed by battle" trigger can tell it
        apart from an effect destruction (Mystic Tomato recruits only on battle);
        ``by_effect`` marks a destruction *by a card effect* (the Destroy* primitives
        pass it) so a "destroyed by a card effect" / unified "destroyed" trigger fires —
        while a non-destruction send (tribute, discard, mill, cost) leaves both False."""
        inst = self.cards[iid]
        # Banisher of the Light: any card that would reach the GY is banished instead.
        # A Token never rests anywhere, so it follows its normal "removed from game" path.
        if not inst.card.is_token and self._graveyard_redirected_to_banish():
            self.banish(iid)
            return
        from_field = inst.zone in (Zone.MONSTER, Zone.SPELL_TRAP, Zone.FIELD)
        from_hand = inst.zone == Zone.HAND  # a hand card reaching the GY *is* a discard
        was_defense = inst.position in (Position.FACE_UP_DEFENSE, Position.FACE_DOWN_DEFENSE)
        owner = inst.owner
        self._remove_from_current_location(iid)
        if inst.card.is_token:
            # A Token that leaves the field is removed from the game — it never rests
            # in the Graveyard, so it raises no "sent to GY" trigger and is forgotten.
            self._clear_field_flags(inst)
            del self.cards[iid]
            return
        inst.zone = Zone.GRAVEYARD
        equipped = inst.equipped_to  # capture before flags clear (for an Equip's parting effect)
        self._clear_field_flags(inst)
        inst.last_equipped_to = equipped
        inst.died_by_battle = by_battle and from_field
        inst.died_by_effect = by_effect and from_field
        inst.died_in_defense = by_battle and from_field and was_defense
        self.players[inst.owner].graveyard.append(iid)
        # Queue "sent from the field to the Graveyard" triggers for the engine. Every
        # monster is queued (cheap; the engine skips those with no such trigger), plus
        # any Spell/Trap that actually carries one (Black Pendant, Horn of the Unicorn).
        if from_field and (inst.card.is_monster or _has_gy_trigger(inst.card)):
            self.gy_from_field.append(iid)
        # Magical Thorn: a card discarded from a hand burns its owner for each opponent's
        # face-up Magical Thorn (the trigger belongs to the discarder's opponent).
        if from_hand:
            self._burn_for_hand_discard(owner)

    def _graveyard_redirected_to_banish(self) -> bool:
        """Whether a live Banisher of the Light (either side) is redirecting every
        send-to-Graveyard into a banish."""
        for _src, _mod in self.active_markers(BanishInsteadOfGraveyard):
            return True
        return False

    def _burn_for_hand_discard(self, discarder: int) -> None:
        """Pay out Magical Thorn: every face-up ``BurnOnHandDiscard`` the *opponent* of
        ``discarder`` controls inflicts its damage on ``discarder`` for this one
        discarded card (callers fire once per card, so the per-card total is exact)."""
        opp = self.opponent_of(discarder)
        for _src, mod in self.active_markers(BurnOnHandDiscard, players=(opp,)):
            self.players[discarder].life_points -= mod.amount

    def banish(self, iid: int) -> None:
        """Remove a card from play to its *owner's* banished pile, clearing field
        flags. Banishing is not 'sent to the Graveyard', so it raises no GY trigger
        (a card removed this way skips Sangan-style "sent to GY" effects)."""
        inst = self.cards[iid]
        self._remove_from_current_location(iid)
        inst.zone = Zone.BANISHED
        self._clear_field_flags(inst)
        self.players[inst.owner].banished.append(iid)

    def return_to_hand(self, iid: int) -> None:
        """Bounce a card to its *owner's* hand (Spirit monsters at the End Phase,
        and future bounce effects), clearing its field bookkeeping."""
        inst = self.cards[iid]
        self._remove_from_current_location(iid)
        inst.zone = Zone.HAND
        self._clear_field_flags(inst)
        self.players[inst.owner].hand.append(iid)

    def return_to_deck(self, iid: int, to_top: bool = True) -> None:
        """Return a card to its *owner's* Deck — placed on top (``to_top``) or
        shuffled in — clearing its field bookkeeping. The top of the deck is the
        end of the list (``draw`` pops from there)."""
        inst = self.cards[iid]
        self._remove_from_current_location(iid)
        inst.zone = Zone.DECK
        self._clear_field_flags(inst)
        deck = self.players[inst.owner].deck
        deck.append(iid)
        if not to_top:
            self.rng.shuffle(deck)

    def send_to_player_deck(self, iid: int, player: int, *, shuffle: bool = True, planted: bool = False) -> None:
        """Send a card into a *specific* player's Deck — not necessarily its owner's.
        Parasite Paracide buries itself in the opponent's Deck this way. Ownership
        transfers to that player so the owner-keyed piles (deck/hand/GY) stay
        consistent: the card now lives entirely on their side, and they draw it like
        any other card. ``planted`` flags it so its 'when drawn' effect fires only
        for this buried copy."""
        inst = self.cards[iid]
        self._remove_from_current_location(iid)
        self._clear_field_flags(inst)  # resets controller to the OLD owner; overridden below
        inst.zone = Zone.DECK
        inst.owner = player
        inst.controller = player
        inst.planted_in_deck = planted
        deck = self.players[player].deck
        deck.append(iid)
        if shuffle:
            self.rng.shuffle(deck)

    # ----- derived stats (the "layers": printed value + active modifiers) -----
    def _equip_mods_on(self, monster_iid: int):
        """Yield (EquipMod, equip_controller) for every face-up Equip attached here whose
        own effect isn't negated — an Equip Spell goes inert under Imperial Order, matching
        the Field/Equip suppression documented in ``_active_continuous_sources``."""
        for player in self.players:
            for sid in player.spell_trap_zones:
                if sid is None:
                    continue
                equip = self.cards[sid]
                if equip.equipped_to == monster_iid and equip.is_face_up and not self.effect_negated(sid):
                    for mod in equip.card.continuous:
                        if isinstance(mod, EquipMod):  # an Equip may also carry non-stat passives
                            yield mod, equip.controller

    def _mod_delta(self, mod, controller: int, which: str, host_iid: int) -> int:
        flat = mod.atk if which == "atk" else mod.defn
        per = mod.scale_atk if which == "atk" else mod.scale_defn
        if mod.scaling is None:
            return flat
        if mod.scaling == "lp_megamorph":
            # Megamorph: the equipped monster's ATK becomes double its original ATK while
            # your LP < the opponent's, or half while your LP > theirs (DEF untouched).
            if which != "atk":
                return 0
            base = self.cards[host_iid].card.attack or 0
            me, opp = self.players[controller].life_points, self.players[self.opponent_of(controller)].life_points
            if me < opp:
                return base  # base + base = double
            if me > opp:
                return -(base // 2)  # base - base/2 = half
            return 0
        if mod.scaling == "face_up_monsters":
            count = sum(
                1 for i in self.players[controller].monster_zones if i is not None and self.cards[i].is_face_up
            )
            return flat + per * count
        if mod.scaling == "spell_trap":
            count = sum(1 for i in self.players[controller].spell_trap_zones if i is not None)
            return flat + per * count
        return flat

    # ----- field/continuous layers (face-up Field & Continuous Spells) -----
    def _active_continuous_sources(self):
        """Yield (card_instance, controller) for every face-up Field/Continuous/Equip
        card on the field — the sources that radiate passive modifiers (FieldMod,
        EquipMod, AttackRestriction). A card whose effects are negated by a face-up
        class negator (Imperial Order negates Spell effects → a Field/Equip Spell's
        boost vanishes; Royal Decree negates a Continuous Trap's rider) is skipped."""
        for idx, player in enumerate(self.players):
            fz = player.field_zone
            if fz is not None and self.cards[fz].is_face_up and not self.effect_negated(fz):
                yield self.cards[fz], idx
            for sid in player.spell_trap_zones:
                if sid is None:
                    continue
                inst = self.cards[sid]
                # A monster absorbed as an Equip (Relinquished / Thousand-Eyes Restrict)
                # sits in a Spell/Trap Zone but radiates none of its own passives.
                if inst.is_face_up and not inst.card.is_monster and not self.effect_negated(sid):
                    yield inst, idx

    def active_passives(self):
        """Yield (modifier, controller) for every passive on a face-up field card —
        FieldMods, AttackRestrictions, EquipMods alike. Consumers filter by type."""
        for src, ctrl in self._active_continuous_sources():
            for mod in src.card.continuous:
                yield mod, ctrl

    def _field_mod_applies(self, mod: FieldMod, monster: "CardInstance", controller: int) -> bool:
        card = monster.card
        if mod.races and card.race not in mod.races:
            return False
        if mod.attributes and card.attribute not in mod.attributes:
            return False
        if mod.side == "self" and monster.controller != controller:
            return False
        if mod.side == "opponent" and monster.controller == controller:
            return False
        if mod.only_opponent_battle_phase and not (
            self.phase is Phase.BATTLE and self.turn_player != controller
        ):
            return False  # Soul of Purity and Light: only during the opponent's Battle Phase
        return True

    def _field_delta(self, monster_iid: int, which: str) -> int:
        monster = self.cards[monster_iid]
        total = 0
        for mod, ctrl in self.active_passives():
            if isinstance(mod, FieldMod) and self._field_mod_applies(mod, monster, ctrl):
                total += mod.atk if which == "atk" else mod.defn
        # Monster-borne field anthems (Bladefly: all WIND +500 / all EARTH −400): a face-up
        # monster whose effects are live radiates its FieldMod riders to every matching
        # monster on the field (both sides), suppressed under Skill Drain / while inactive.
        for ctrl, pl in enumerate(self.players):
            for sid in pl.monster_zones:
                if sid is None:
                    continue
                src = self.cards[sid]
                if not src.is_face_up or not src.effects_active or self.monster_effects_negated(sid):
                    continue
                for mod in src.card.continuous:
                    if not isinstance(mod, FieldMod) or not self._field_mod_applies(mod, monster, ctrl):
                        continue
                    if mod.source_in_defense and src.position is not Position.FACE_UP_DEFENSE:
                        continue  # Fairy King Truesdale only radiates while it's in Defense
                    total += mod.atk if which == "atk" else mod.defn
        # Aqua Chorus: a monster sharing its name with another face-up monster (either
        # side) gains the anthem's value, once per active Aqua Chorus.
        name = monster.card.name
        if any(
            i is not None
            and i != monster_iid
            and self.cards[i].is_face_up
            and self.cards[i].card.name == name
            for pl in self.players
            for i in pl.monster_zones
        ):
            for _src, mod in self.active_markers(SameNameAnthem):
                total += mod.atk if which == "atk" else mod.defn
        return total

    def _self_mod_active(self, mod, controller: int) -> bool:
        """Whether a SelfStatMod's optional activation gates all hold for ``controller``
        (a gate left unset is ignored). Controls a named monster / hand size cap / empty
        Spell & Trap Zones — Boot-Up Soldier, Cybernetic Cyclopean, Theban Nightmare."""
        p = self.players[controller]
        if mod.active_if_control_name_contains is not None and not any(
            i is not None
            and self.cards[i].is_face_up
            and mod.active_if_control_name_contains in self.cards[i].card.name
            for i in p.monster_zones
        ):
            return False
        if mod.active_if_hand_at_most is not None and len(p.hand) > mod.active_if_hand_at_most:
            return False
        if mod.active_if_empty_spell_trap and any(z is not None for z in p.spell_trap_zones):
            return False
        return True

    def _self_stat_delta(self, monster_iid: int, which: str) -> int:
        """A monster's own continuous self-boost (SelfStatMod), e.g. Goggle Golem's
        unlocked ATK. Suppressed while the monster's effect is inactive (a Gemini
        not yet Gemini Summoned) or negated by Skill Drain."""
        inst = self.cards[monster_iid]
        if not inst.effects_active or self.monster_effects_negated(monster_iid):
            return 0
        total = 0
        for mod in inst.card.continuous:
            if not isinstance(mod, SelfStatMod):
                continue
            if not self._self_mod_active(mod, inst.controller):
                continue  # a gated boost (Boot-Up Soldier, Theban Nightmare) is dormant
            flat = mod.atk if which == "atk" else mod.defn
            if mod.scaling == "face_up_attr_monsters":
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                count = sum(
                    1
                    for pl in self.players
                    for i in pl.monster_zones
                    if i is not None
                    and i != monster_iid
                    and self.cards[i].is_face_up
                    and (mod.count_attribute is None or self.cards[i].card.attribute == mod.count_attribute)
                )
                total += flat + per * count
            elif mod.scaling == "graveyard_monsters":
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                gy = self.players[inst.controller].graveyard
                count = sum(
                    1
                    for i in gy
                    if self.cards[i].card.is_monster
                    and (mod.count_attribute is None or self.cards[i].card.attribute == mod.count_attribute)
                    and (mod.count_race is None or self.cards[i].card.race == mod.count_race)
                    and (mod.count_name_contains is None or mod.count_name_contains in self.cards[i].card.name)
                )
                total += flat + per * count
            elif mod.scaling == "controlled_monsters":
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                count = sum(
                    1
                    for i in self.players[inst.controller].monster_zones
                    if i is not None
                    and self.cards[i].is_face_up
                    and not (mod.count_exclude_self and i == monster_iid)
                    and (mod.count_attribute is None or self.cards[i].card.attribute == mod.count_attribute)
                    and (mod.count_race is None or self.cards[i].card.race == mod.count_race)
                    and (mod.count_name_contains is None or mod.count_name_contains in self.cards[i].card.name)
                )
                total += flat + per * count
            elif mod.scaling == "equips_on_self":
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                count = sum(
                    1
                    for pl in self.players
                    for sid in pl.spell_trap_zones
                    if sid is not None
                    and self.cards[sid].equipped_to == monster_iid
                    and self.cards[sid].is_face_up
                )
                total += flat + per * count
            elif mod.scaling == "race_on_field":
                # Insect Queen: +scale per face-up monster of count_race anywhere on the
                # field (both sides, including this card itself).
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                count = sum(
                    1
                    for pl in self.players
                    for i in pl.monster_zones
                    if i is not None
                    and self.cards[i].is_face_up
                    and (mod.count_race is None or self.cards[i].card.race == mod.count_race)
                )
                total += flat + per * count
            elif mod.scaling == "opponent_monsters":
                # Nuvia the Wicked: -scale per face-up monster the OPPONENT controls (none ->
                # no change, which also covers the "if your opponent controls any" wording).
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                opp = self.opponent_of(inst.controller)
                count = sum(
                    1 for i in self.players[opp].monster_zones
                    if i is not None and self.cards[i].is_face_up
                )
                total += flat + per * count
            elif mod.scaling == "hand_size":
                # Muka Muka (+300), Enraged Muka Muka (+400), Flash Assailant (-400): scale
                # per card in the controller's hand. The source is on the field, never in
                # hand, so it never counts itself.
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                total += flat + per * len(self.players[inst.controller].hand)
            elif mod.scaling == "named_in_graveyards":
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                count = sum(
                    1
                    for pl in self.players
                    for i in pl.graveyard
                    if self.cards[i].card.name in mod.count_names
                )
                total += flat + per * count
            elif mod.scaling == "absorbed_monster":
                # Relinquished / Thousand-Eyes Restrict: this card's ATK/DEF become equal
                # to the monster it has absorbed (equipped to it, sitting in a S/T zone).
                for pl in self.players:
                    for sid in pl.spell_trap_zones:
                        if sid is None:
                            continue
                        eq = self.cards[sid]
                        if eq.equipped_to == monster_iid and eq.card.is_monster:
                            total += (eq.card.attack or 0) if which == "atk" else (eq.card.defense or 0)
            elif mod.scaling == "opponent_field_and_gy_race":
                # Buster Blader: +500 ATK for every Dragon-Type the OPPONENT controls
                # (face-up) AND every Dragon-Type in the opponent's Graveyard.
                per = mod.scale_atk if which == "atk" else mod.scale_defn
                opp = self.players[self.opponent_of(inst.controller)]
                field = sum(
                    1
                    for i in opp.monster_zones
                    if i is not None
                    and self.cards[i].is_face_up
                    and (mod.count_race is None or self.cards[i].card.race == mod.count_race)
                )
                gy = sum(
                    1
                    for i in opp.graveyard
                    if self.cards[i].card.is_monster
                    and (mod.count_race is None or self.cards[i].card.race == mod.count_race)
                )
                total += flat + per * (field + gy)
            else:
                total += flat
        return total

    def _spell_counter_delta(self, monster_iid: int, which: str) -> int:
        """A monster's stat boost per Spell Counter on it (Mythical Beast Cerberus
        gains 500 ATK each). Suppressed while the monster's effect is inactive or
        negated by Skill Drain."""
        inst = self.cards[monster_iid]
        if not inst.effects_active or self.monster_effects_negated(monster_iid):
            return 0
        n = inst.counters.get("spell", 0)
        if not n:
            return 0
        return sum(
            n * (mod.per_counter_atk if which == "atk" else mod.per_counter_def)
            for mod in inst.card.continuous
            if isinstance(mod, SpellCounterHolder)
        )

    def _self_rider(self, iid: int, marker_type):
        """The first active continuous rider of ``marker_type`` on the monster's own
        card, or None. A card's own riders are suppressed while its effect is off (a
        Gemini that hasn't been Gemini Summoned) or while a Skill Drain-style negator
        shuts off its effects — those guards live here, once."""
        inst = self.cards[iid]
        if not inst.effects_active or self.monster_effects_negated(iid):
            return None
        return next((m for m in inst.card.continuous if isinstance(m, marker_type)), None)

    def has_piercing(self, iid: int) -> bool:
        """Whether the monster deals piercing battle damage to a defender it breaks —
        from its own Piercing rider, or granted by a face-up Equip (Big Bang Shot)."""
        if self._self_rider(iid, Piercing) is not None:
            return True
        return any(mod.grants_piercing for mod, _ in self._equip_mods_on(iid))

    def damage_step_bonus(self, iid: int, opposing_iid: int | None, *, is_attacker: bool, which: str) -> int:
        """The Damage-Step-only ATK/DEF swing ``iid`` gets in a battle against
        ``opposing_iid`` (None = a direct attack). ``is_attacker`` says which side of the
        battle ``iid`` is on; ``which`` is "atk"/"defn". Combat-only — never part of the
        monster's continuous stats. Suppressed while the effect is inactive or negated."""
        inst = self.cards.get(iid)
        if inst is None:
            return 0
        allowed = ("attacking", "either") if is_attacker else ("attacked", "either")

        def _contribution(mod: DamageStepBonus) -> int:
            if mod.when not in allowed:
                return 0
            if mod.vs_direct:
                if opposing_iid is not None:
                    return 0
            else:
                if opposing_iid is None:
                    return 0
                other = self.cards[opposing_iid].card
                if mod.vs_race is not None and other.race != mod.vs_race:
                    return 0
                if mod.vs_attribute is not None and other.attribute != mod.vs_attribute:
                    return 0
            if mod.half_opposing_atk:
                # Metalmorph: only an ATK swing, only with a defender present.
                if which != "atk" or opposing_iid is None:
                    return 0
                return self.effective_attack(opposing_iid) // 2
            return mod.atk if which == "atk" else mod.defn

        total = 0
        # The monster's OWN damage-step riders — suppressed while its effect is inactive
        # or negated (Skill Drain).
        if inst.effects_active and not self.monster_effects_negated(iid):
            for mod in inst.card.continuous:
                if isinstance(mod, DamageStepBonus):
                    total += _contribution(mod)
        # Equip-sourced riders (Metalmorph) ride onto the equipped monster, gated by the
        # equip being face-up and un-negated — NOT by the host's effect state (so they
        # persist under Skill Drain, which only negates monster effects).
        for player in self.players:
            for sid in player.spell_trap_zones:
                if sid is None:
                    continue
                equip = self.cards[sid]
                if equip.equipped_to == iid and equip.is_face_up and not self.effect_negated(sid):
                    for mod in equip.card.continuous:
                        if isinstance(mod, DamageStepBonus):
                            total += _contribution(mod)
        return total

    def can_attack_directly(self, iid: int) -> bool:
        """Whether the monster may declare a direct attack despite the opponent having
        monsters (a face-up CanAttackDirectly rider). Alligator's Sword Dragon gates the
        bypass on every face-up opponent monster having an allowed attribute."""
        mod = self._self_rider(iid, CanAttackDirectly)
        if mod is None:
            return False
        if mod.only_if_opponent_attributes:
            opp = self.opponent_of(self.cards[iid].controller)
            if any(
                self.cards[i].card.attribute not in mod.only_if_opponent_attributes
                for i in self.players[opp].monster_zones
                if i is not None and self.cards[i].is_face_up
            ):
                return False  # a face-up opponent monster with a disallowed attribute blocks it
        return True

    def is_battle_indestructible(self, iid: int) -> bool:
        """Whether the monster cannot be destroyed by battle — an unconditional
        BattleIndestructible rider (Marshmallon), or a SafeAttacker (Rocket Warrior) during
        its controller's own Battle Phase (when it is the attacker)."""
        if self._self_rider(iid, BattleIndestructible) is not None:
            return True
        return self._safe_attacker_active(iid)

    def _safe_attacker_active(self, iid: int) -> bool:
        """Whether ``iid``'s SafeAttacker rider is live right now: its controller's Battle
        Phase (so it covers the monster only while attacking, not while it defends on the
        opponent's turn). False for an iid no longer in play — combat may destroy a token
        attacker before this is read."""
        inst = self.cards.get(iid)
        if inst is None or self._self_rider(iid, SafeAttacker) is None:
            return False
        return self.turn_player == inst.controller and self.phase is Phase.BATTLE

    def attacker_takes_no_self_battle_damage(self, iid: int) -> bool:
        """Whether the controller of attacking monster ``iid`` takes no battle damage from a
        battle involving it (Rocket Warrior, during its own Battle Phase)."""
        return self._safe_attacker_active(iid)

    def attacker_target_debuff(self, iid: int) -> int:
        """How much ATK the monster that ``iid`` just attacked loses until the end of the
        turn (Rocket Warrior = 500), or 0 if ``iid`` has no such rider or is no longer in
        play (a token attacker may have been destroyed in the battle)."""
        if iid not in self.cards:
            return 0
        rider = self._self_rider(iid, DebuffsAttackTargetAtk)
        return rider.amount if rider is not None else 0

    def max_attacks(self, iid: int) -> int:
        """How many attacks the monster may declare this Battle Phase — 2+ for a
        face-up MultiAttacker (Hayabusa Knight), else 1."""
        mod = self._self_rider(iid, MultiAttacker)
        return mod.times if mod is not None else 1

    def attack_life_cost(self, iid: int) -> int:
        """The Life Points the controller must pay to declare an attack with this
        monster (Dark Elf = 1000), or 0 if none. Suppressed while the monster's effect
        is inactive or negated (Skill Drain) — then it may attack for free."""
        mod = self._self_rider(iid, AttackLifeCost)
        return mod.amount if mod is not None else 0

    def attack_tribute_cost(self, iid: int) -> int:
        """How many other monsters the controller must Tribute to declare an attack with
        this monster (Panther Warrior = 1), or 0 if none. Suppressed while its effect is
        inactive or negated (Skill Drain) — then it may attack for free."""
        mod = self._self_rider(iid, AttackTributeCost)
        return mod.count if mod is not None else 0

    def attack_tribute_fodder(self, iid: int) -> list[int]:
        """The OTHER monsters the controller could Tribute to pay this monster's
        attack-Tribute cost — every face-up/face-down monster they control except the
        attacker itself, weakest (lowest ATK) first so the headless payer keeps its board."""
        inst = self.cards[iid]
        others = [
            i for i in self.players[inst.controller].monster_zones if i is not None and i != iid
        ]
        return sorted(others, key=lambda i: self.cards[i].card.attack or 0)

    def attack_deck_cost(self, player: int) -> int:
        """How many cards ``player`` must mill from the top of their own Deck to declare
        an attack — imposed by each face-up Gravekeeper's Servant the opponent controls.
        A player who cannot pay (too few cards in Deck) cannot declare an attack."""
        opp = self.opponent_of(player)
        return sum(
            mod.count for _src, mod in self.active_markers(OpponentMillToAttack, players=(opp,))
        )

    def deals_halved_battle_damage(self, iid: int) -> bool:
        """Whether the battle damage this monster inflicts to the opponent is halved
        (Susa Soldier). Suppressed while its effect is inactive or negated (Skill Drain)."""
        return self._self_rider(iid, HalvesBattleDamageDealt) is not None

    def attack_barred_needs_ally(self, iid: int) -> bool:
        """Whether this monster is barred from declaring an attack because it carries a
        CannotAttackUnlessControlRace rider and its controller controls no *other* monster
        of that race (Cave Dragon needs a second Dragon). Suppressed under Skill Drain."""
        mod = self._self_rider(iid, CannotAttackUnlessControlRace)
        if mod is None:
            return False
        controller = self.cards[iid].controller
        return not any(
            i is not None and i != iid and self.cards[i].is_face_up and self.cards[i].card.race == mod.race
            for i in self.players[controller].monster_zones
        )

    def field_cards(
        self,
        player: int,
        *,
        monsters: bool = True,
        spell_traps: bool = True,
        field: bool = True,
        face_up_only: bool = False,
        face_down_only: bool = False,
    ) -> list[int]:
        """The iids of ``player``'s cards on the field, filtered by zone kind and facing.
        The single source for "iterate a side's zones" — used by the field-wide rider
        scans, mass removal/return primitives and target pools. Returns a snapshot list,
        so destroying a card mid-iteration is safe."""
        p = self.players[player]
        out: list[int] = []
        if monsters:
            out += [i for i in p.monster_zones if i is not None]
        if spell_traps:
            out += [i for i in p.spell_trap_zones if i is not None]
        if field and p.field_zone is not None:
            out.append(p.field_zone)
        if face_up_only:
            out = [i for i in out if self.cards[i].is_face_up]
        if face_down_only:
            out = [i for i in out if not self.cards[i].is_face_up]
        return out

    def active_markers(self, marker_type, players=(0, 1), *, respect_negation=True):
        """Yield (card_instance, marker) for every face-up card on the given side(s)
        whose effect is live (a Gemini not yet Gemini Summoned is skipped) and which
        carries a continuous rider of ``marker_type``. The one place that owns the
        "scan the field for a live continuous marker" pattern — so the effects_active
        guard can never be forgotten by a caller (it was, twice, before this).

        ``respect_negation`` (default True) also skips a Spell/Trap whose effects are
        shut off by a face-up class negator (Imperial Order negates a Field Spell's
        FieldMod; Jinzo negates a Continuous Trap's rider). The negator scan itself
        passes False to avoid recursing on its own predicate."""
        for pl in players:
            for iid in self.field_cards(pl, face_up_only=True):
                inst = self.cards[iid]
                if not inst.effects_active:
                    continue
                if respect_negation and self.effect_negated(iid):
                    continue
                for mod in inst.card.continuous:
                    if isinstance(mod, marker_type):
                        yield inst, mod

    def _class_negator(self, iid: int, *, prevent_activation_only: bool) -> bool:
        """Whether a face-up ``CardEffectNegation`` shuts off the Spell/Trap ``iid``.
        ``prevent_activation_only`` restricts the scan to negators that forbid
        *activating* the class (Jinzo/Spell Canceller), vs. any negator of the class
        (also Royal Decree/Imperial Order, which only negate the resolved effect)."""
        inst = self.cards.get(iid)
        if inst is None:
            return False
        if inst.card.is_spell:
            kind = "spell"
        elif inst.card.is_trap:
            kind = "trap"
        else:
            return False  # a monster is handled by monster_effects_negated (Skill Drain)
        for src, mod in self.active_markers(CardEffectNegation, respect_negation=False):
            if mod.negates != kind:
                continue
            if prevent_activation_only and not mod.prevent_activation:
                continue
            if mod.exclude_self and src.iid == iid:
                continue
            if mod.whose == "opponent" and inst.controller == src.controller:
                continue
            if mod.whose == "self" and inst.controller != src.controller:
                continue
            return True
        return False

    def hand_limit_suppressed(self, player: int) -> bool:
        """Whether ``player`` has no End-Phase hand-size limit right now. Infinite Cards
        (``NoHandLimit(whose="both")``) lifts the discard-to-6 for both players while it is
        face-up; the marker is skipped if its card's effect is negated (Imperial Order)."""
        for src, mod in self.active_markers(NoHandLimit):
            if mod.whose == "both":
                return True
            if mod.whose == "controller" and src.controller == player:
                return True
            if mod.whose == "opponent" and src.controller != player:
                return True
        return False

    def destroys_attached_equips(self, iid: int) -> bool:
        """Whether the monster ``iid`` destroys any Equip Card equipped to it (Gearfried
        the Iron Knight). False while it is face-down, its effect is inactive, or it is
        negated (Skill Drain) — then equips attach normally."""
        inst = self.cards.get(iid)
        if inst is None or not inst.is_face_up or not inst.effects_active:
            return False
        if self.monster_effects_negated(iid):
            return False
        return any(isinstance(m, DestroyAttachedEquips) for m in inst.card.continuous)

    def action_locked(self, kind: str, player: int) -> bool:
        """Whether a turn-scoped lock currently forbids ``player`` from ``kind``
        ("special_summon"/"spell"/"trap"/"set"). Set by ApplyActionLock (Guard Dog &
        co); expires once the stamped turn passes."""
        until = self.action_locks.get(f"{kind}:{player}")
        return until is not None and self.turn_count <= until

    def cannot_activate_card(self, iid: int) -> bool:
        """Whether the Spell/Trap ``iid`` cannot be *activated* right now — a face-up
        negator forbids activating its class (Jinzo bars Traps, Spell Canceller bars
        Spells), or a turn-scoped lock bars it (Sonic Jammer / Whirlwind Weasel). Gated
        into every Spell/Trap activation enumeration."""
        inst = self.cards.get(iid)
        if inst is not None:
            if inst.card.is_spell and self.action_locked("spell", inst.controller):
                return True
            if inst.card.is_trap and self.action_locked("trap", inst.controller):
                return True
            if self._activation_locked_by_monster(inst):
                return True
        return self._class_negator(iid, prevent_activation_only=True)

    def _activation_locked_by_monster(self, inst) -> bool:
        """Whether a face-up ActivationLock monster bars its controller's opponent from
        activating ``inst`` right now (Mirage Dragon / Invader of Darkness / Mechanical
        Hound). Scope-checked: class, Quick-Play-only, Battle-Phase-only, empty-hand."""
        for src, mod in self.active_markers(ActivationLock):
            if inst.controller != self.opponent_of(src.controller):
                continue  # the lock only hits the source controller's opponent
            if mod.locks == "spell" and not inst.card.is_spell:
                continue
            if mod.locks == "trap" and not inst.card.is_trap:
                continue
            if mod.quick_play_only and inst.card.subtype is not SpellTrapProperty.QUICK_PLAY:
                continue
            if mod.during_battle_phase_only and self.phase is not Phase.BATTLE:
                continue
            if mod.requires_empty_hand and self.players[src.controller].hand:
                continue
            return True
        return False

    def effect_negated(self, iid: int) -> bool:
        """Whether the *effects* of the face-up card ``iid`` are negated — its chain link
        does not resolve and its continuous riders go inert. Dispatches by card kind:

          * Spell/Trap — a class negator (Jinzo/Royal Decree negate Traps; Spell
            Canceller/Imperial Order negate Spells).
          * Monster — a Skill Drain-style negator (``monster_effects_negated``).

        The single predicate that ``_resolve_chain``, ``active_markers`` and
        ``_active_continuous_sources`` all read, so every negation class flows through
        the same gate."""
        inst = self.cards.get(iid)
        if inst is None:
            return False
        if inst.card.is_monster:
            return self.monster_effects_negated(iid)
        return self._class_negator(iid, prevent_activation_only=False)

    def monster_effects_negated(self, iid: int) -> bool:
        """Whether the face-up monster ``iid``'s effects are negated by a Skill Drain-style
        negator (``CardEffectNegation`` with ``negates="monster"``). Only a monster that is
        *face-up on the field right now* is negated — an effect resolving from the GY (a
        recruiter destroyed in battle) or after the monster has left is NOT, matching Skill
        Drain's "while they are face-up on the field" (and its "their effects can still be
        activated": activation is never gated, only resolution and the continuous riders)."""
        inst = self.cards.get(iid)
        if inst is None or inst.zone is not Zone.MONSTER or not inst.is_face_up:
            return False
        for src, mod in self.active_markers(CardEffectNegation, respect_negation=False):
            if mod.negates != "monster":
                continue
            if mod.exclude_self and src.iid == iid:
                continue
            if mod.whose == "opponent" and inst.controller == src.controller:
                continue
            if mod.whose == "self" and inst.controller != src.controller:
                continue
            return True
        return False

    def _controls_other_required(self, mod, src_iid: int, controller: int) -> bool:
        """Whether an AttackTargetProtection's "control another monster" gate holds: the
        controller controls a face-up monster OTHER than the source matching the gate (any
        / a race / an attribute). True when no such gate is set."""
        if not (
            mod.requires_control_other
            or mod.requires_control_other_race is not None
            or mod.requires_control_other_attribute is not None
        ):
            return True
        for m in self.players[controller].monster_zones:
            if m is None or m == src_iid or not self.cards[m].is_face_up:
                continue
            card = self.cards[m].card
            if mod.requires_control_other_race is not None and card.race != mod.requires_control_other_race:
                continue
            if (
                mod.requires_control_other_attribute is not None
                and card.attribute != mod.requires_control_other_attribute
            ):
                continue
            return True
        return False

    def is_protected_attack_target(self, iid: int) -> bool:
        """Whether the monster ``iid`` cannot be selected as an attack target by the
        opponent — a face-up AttackTargetProtection on its controller's side covers it
        (Decoyroid, Marauding Captain, Queen's Bodyguard, Marshmallon Glasses)."""
        inst = self.cards.get(iid)
        if inst is None or inst.zone is not Zone.MONSTER:
            return False
        controller = inst.controller
        for src, mod in self.active_markers(AttackTargetProtection, (controller,)):
            if mod.requires_face_up_umi and not self.controls_face_up_umi(controller):
                continue  # The Legendary Fisherman is only untargetable while Umi is up
            if mod.requires_control_name_contains is not None and not any(
                m is not None
                and self.cards[m].is_face_up
                and mod.requires_control_name_contains in self.cards[m].card.name
                for m in self.players[controller].monster_zones
            ):
                continue
            if not self._controls_other_required(mod, src.iid, controller):
                continue  # Command Knight needs "another monster" (Freya/Hunter Owl: of a kind)
            if mod.self_only and iid != src.iid:
                continue  # the rider shields only its own source monster
            if mod.exclude_self and src.iid == iid:
                continue
            if (
                mod.exclude_name_contains is not None
                and mod.exclude_name_contains in inst.card.name
            ):
                continue
            if mod.race is not None and inst.card.race != mod.race:
                continue
            if mod.name_contains is not None and mod.name_contains not in inst.card.name:
                continue
            return True
        return False

    def special_summon_locked(self, player: int, card: "CardDef") -> bool:
        """Whether ``player`` is currently prevented from Special Summoning ``card`` by a
        face-up Special-Summon lock (Vanity's Fiend/Ruler, the Barrier Statues) or a
        turn-scoped lock (Guard Dog). Read by every Special Summon route — a locked summon
        simply does not happen."""
        if self.action_locked("special_summon", player):
            return True
        for src, mod in self.active_markers(SpecialSummonLock):
            if mod.whose == "opponent" and player == src.controller:
                continue  # only the source controller's opponent is locked
            if mod.except_attribute is not None and card.attribute == mod.except_attribute:
                continue
            return True
        return False

    def _effective_stat(self, iid: int, which: str) -> int:
        """A monster's effective ATK or DEF (``which`` is "atk"/"def"): printed base
        plus every layer — Equip mods, Field mods, the monster's own SelfStatMod,
        Spell-Counter scaling, and the until-end-of-turn temp delta. Floored at 0."""
        inst = self.cards[iid]
        if not inst.card.is_monster:
            return 0
        base = (inst.card.attack if which == "atk" else inst.card.defense) or 0
        temp = inst.temp_atk if which == "atk" else inst.temp_def
        perm = inst.perm_atk if which == "atk" else inst.perm_def
        total = base + temp + perm
        total += sum(self._mod_delta(mod, ctrl, which, iid) for mod, ctrl in self._equip_mods_on(iid))
        total += self._field_delta(iid, which)
        total += self._self_stat_delta(iid, which)
        total += self._spell_counter_delta(iid, which)
        return max(0, total)

    def effective_attack(self, iid: int) -> int:
        return self._effective_stat(iid, "atk")

    def effective_defense(self, iid: int) -> int:
        return self._effective_stat(iid, "def")

    def exodia_winner(self) -> int | None:
        """The player holding all five "Forbidden One" pieces in hand wins the Duel
        (Exodia). Returns that player's index, or None if neither holds the full set.
        The engine re-checks this after any hand change (a draw, a search to hand)."""
        for pl in (0, 1):
            held = {self.cards[i].card.name for i in self.players[pl].hand}
            if EXODIA_PIECES <= held:
                return pl
        return None

    def spawn_on_field(
        self, card: CardDef, player: int, index: int, position: Position, owner: int | None = None
    ) -> CardInstance:
        """Create a fresh instance directly in a Monster Zone.

        Convenience for tokens, special summons from "limbo", and tests — the
        card isn't drawn from any pile first.
        """
        inst = self.create_instance(card, owner if owner is not None else player, Zone.MONSTER)
        self.players[player].monster_zones[index] = inst.iid
        inst.controller = player
        inst.zone_index = index
        inst.position = position
        return inst

    def place_spell_trap(self, iid: int, player: int, index: int, position: Position) -> None:
        """Put a card into a Spell & Trap Zone slot."""
        self._remove_from_current_location(iid)
        inst = self.cards[iid]
        self.players[player].spell_trap_zones[index] = iid
        inst.zone = Zone.SPELL_TRAP
        inst.controller = player
        inst.zone_index = index
        inst.position = position

    def place_field_spell(self, iid: int, player: int, position: Position) -> None:
        """Put a Field Spell into the Field Zone, destroying the one already there
        (only one Field Spell per player can be face-up at a time)."""
        existing = self.players[player].field_zone
        if existing is not None and existing != iid:
            self.send_to_graveyard(existing)
        self._remove_from_current_location(iid)
        inst = self.cards[iid]
        self.players[player].field_zone = iid
        inst.zone = Zone.FIELD
        inst.controller = player
        inst.position = position

    def first_empty_monster_zone(self, player: int) -> int | None:
        for i, slot in enumerate(self.players[player].monster_zones):
            if slot is None:
                return i
        return None

    def first_empty_spell_trap_zone(self, player: int) -> int | None:
        for i, slot in enumerate(self.players[player].spell_trap_zones):
            if slot is None:
                return i
        return None
