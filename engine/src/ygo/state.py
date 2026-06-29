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
from .effects import EquipMod, FieldMod, Piercing, SelfStatMod, SpellCounterHolder
from .enums import Phase, Position, Zone

STARTING_LIFE_POINTS = 8000
MAX_MONSTER_ZONES = 5
MAX_SPELL_TRAP_ZONES = 5


def _has_gy_trigger(card: CardDef) -> bool:
    """Whether a card carries a 'sent from the field to the Graveyard' trigger
    (Black Pendant, Horn of the Unicorn) — so non-monsters with one get queued."""
    return any(
        e.timing == "trigger"
        and e.trigger is not None
        and e.trigger.kind == "sent_to_gy_from_field"
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
    position_changed_this_turn: bool = False
    # The turn on which a Spell/Trap was Set face-down (it can't activate that turn).
    set_on_turn: int | None = None
    # For an Equip card: the iid of the monster it is attached to.
    equipped_to: int | None = None
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
        self.position_changed_this_turn = False

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
    gy_from_field: list = field(default_factory=list)  # monsters just sent field->GY (trigger queue)
    pending_draws: list = field(default_factory=list)  # players who just drew (draw-trigger queue)
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
        if drawn:  # "when you draw a card(s)" fires once per draw, for the engine to process
            self.pending_draws.append(player)
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

    def _clear_field_flags(self, inst: "CardInstance") -> None:
        """Reset the per-instance bookkeeping a card carries while on the field."""
        inst.controller = inst.owner
        inst.position = None
        inst.reset_turn_flags()
        inst.set_on_turn = None
        inst.equipped_to = None
        inst.linked_to = None
        inst.control_reverts_to = None
        inst.control_until_end_of_turn = None
        inst.control_equip_iid = None
        inst.gemini_unlocked = False  # a Gemini re-locks once it leaves the field
        inst.union_acted_on_turn = None
        inst.counters = {}  # counters fall off when the card leaves the field
        inst.temp_atk = 0
        inst.temp_def = 0
        inst.died_by_battle = False  # re-stamped by send_to_graveyard if a battle death
        inst.tributed_iids = []  # the tribute-cost record doesn't outlive the field

    def send_to_graveyard(self, iid: int, by_battle: bool = False) -> None:
        """Move a card to its *owner's* Graveyard, clearing field flags. ``by_battle``
        marks a battle destruction so a "destroyed by battle" trigger can tell it
        apart from an effect destruction (Mystic Tomato recruits only on battle)."""
        inst = self.cards[iid]
        from_field = inst.zone in (Zone.MONSTER, Zone.SPELL_TRAP, Zone.FIELD)
        self._remove_from_current_location(iid)
        inst.zone = Zone.GRAVEYARD
        self._clear_field_flags(inst)
        inst.died_by_battle = by_battle and from_field
        self.players[inst.owner].graveyard.append(iid)
        # Queue "sent from the field to the Graveyard" triggers for the engine. Every
        # monster is queued (cheap; the engine skips those with no such trigger), plus
        # any Spell/Trap that actually carries one (Black Pendant, Horn of the Unicorn).
        if from_field and (inst.card.is_monster or _has_gy_trigger(inst.card)):
            self.gy_from_field.append(iid)

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

    # ----- derived stats (the "layers": printed value + active modifiers) -----
    def _equip_mods_on(self, monster_iid: int):
        """Yield (EquipMod, equip_controller) for every face-up Equip attached here."""
        for player in self.players:
            for sid in player.spell_trap_zones:
                if sid is None:
                    continue
                equip = self.cards[sid]
                if equip.equipped_to == monster_iid and equip.is_face_up:
                    for mod in equip.card.continuous:
                        if isinstance(mod, EquipMod):  # an Equip may also carry non-stat passives
                            yield mod, equip.controller

    def _mod_delta(self, mod, controller: int, which: str) -> int:
        flat = mod.atk if which == "atk" else mod.defn
        per = mod.scale_atk if which == "atk" else mod.scale_defn
        if mod.scaling is None:
            return flat
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
        card on the field — the sources that radiate passive modifiers."""
        for idx, player in enumerate(self.players):
            fz = player.field_zone
            if fz is not None and self.cards[fz].is_face_up:
                yield self.cards[fz], idx
            for sid in player.spell_trap_zones:
                if sid is not None and self.cards[sid].is_face_up:
                    yield self.cards[sid], idx

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
        return True

    def _field_delta(self, monster_iid: int, which: str) -> int:
        monster = self.cards[monster_iid]
        total = 0
        for mod, ctrl in self.active_passives():
            if isinstance(mod, FieldMod) and self._field_mod_applies(mod, monster, ctrl):
                total += mod.atk if which == "atk" else mod.defn
        return total

    def _self_stat_delta(self, monster_iid: int, which: str) -> int:
        """A monster's own continuous self-boost (SelfStatMod), e.g. Goggle Golem's
        unlocked ATK. Suppressed while the monster's effect is inactive (a Gemini
        not yet Gemini Summoned)."""
        inst = self.cards[monster_iid]
        if not inst.effects_active:
            return 0
        total = 0
        for mod in inst.card.continuous:
            if not isinstance(mod, SelfStatMod):
                continue
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
            else:
                total += flat
        return total

    def _spell_counter_delta(self, monster_iid: int, which: str) -> int:
        """A monster's stat boost per Spell Counter on it (Mythical Beast Cerberus
        gains 500 ATK each). Suppressed while the monster's effect is inactive."""
        inst = self.cards[monster_iid]
        if not inst.effects_active:
            return 0
        n = inst.counters.get("spell", 0)
        if not n:
            return 0
        return sum(
            n * (mod.per_counter_atk if which == "atk" else mod.per_counter_def)
            for mod in inst.card.continuous
            if isinstance(mod, SpellCounterHolder)
        )

    def has_piercing(self, iid: int) -> bool:
        """Whether the monster deals piercing battle damage to a defender (a face-up
        Piercing rider on its own card, active only while its effect is on)."""
        inst = self.cards[iid]
        return inst.effects_active and any(
            isinstance(mod, Piercing) for mod in inst.card.continuous
        )

    def _effective_stat(self, iid: int, which: str) -> int:
        """A monster's effective ATK or DEF (``which`` is "atk"/"def"): printed base
        plus every layer — Equip mods, Field mods, the monster's own SelfStatMod,
        Spell-Counter scaling, and the until-end-of-turn temp delta. Floored at 0."""
        inst = self.cards[iid]
        if not inst.card.is_monster:
            return 0
        base = (inst.card.attack if which == "atk" else inst.card.defense) or 0
        temp = inst.temp_atk if which == "atk" else inst.temp_def
        total = base + temp
        total += sum(self._mod_delta(mod, ctrl, which) for mod, ctrl in self._equip_mods_on(iid))
        total += self._field_delta(iid, which)
        total += self._self_stat_delta(iid, which)
        total += self._spell_counter_delta(iid, which)
        return max(0, total)

    def effective_attack(self, iid: int) -> int:
        return self._effective_stat(iid, "atk")

    def effective_defense(self, iid: int) -> int:
        return self._effective_stat(iid, "def")

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
