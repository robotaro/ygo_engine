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
    AttackTargetProtection,
    BattleIndestructible,
    CanAttackDirectly,
    CardEffectNegation,
    EquipMod,
    FieldMod,
    DamageStepBonus,
    MultiAttacker,
    Piercing,
    SelfStatMod,
    SpecialSummonLock,
    SpellCounterHolder,
)
from .enums import Phase, Position, SpellTrapProperty, Zone

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
    attacks_made_this_turn: int = 0  # how many attacks declared this turn (multi-attackers)
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
    # The turn this card last activated a "once per turn" Ignition effect. Turn-stamped
    # so it expires on its own; reset when the card leaves the field.
    effect_activated_on_turn: int | None = None
    # The turn an effect disabled this card's attack ("cannot attack the turn this
    # effect is activated"). Turn-stamped; read by attack enumeration.
    attack_disabled_on_turn: int | None = None

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
    attack_redirect: int | None = None  # a response set a new attack target (Call of the Earthbound)
    reflect_battle_damage: bool = False  # Dimension Wall: my battle damage hits the attacker
    forced_attack_target: int | None = None  # Staunch Defender: attacks this turn must hit only this monster
    # Turn-scoped action locks: "kind:player" -> the last turn_count the lock is active
    # (inclusive). kinds: "special_summon"/"spell"/"trap"/"set" (Guard Dog, Sonic Jammer,
    # Whirlwind Weasel, Searchlightman). Auto-expires by turn; pruned in engine._begin_turn.
    action_locks: dict = field(default_factory=dict)
    gy_from_field: list = field(default_factory=list)  # monsters just sent field->GY (trigger queue)
    pending_draws: list = field(default_factory=list)  # players who just drew (draw-trigger queue)
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
        inst.was_special_summoned = False  # re-stamped by special_summon on a fresh summon
        inst.was_tribute_summoned = False  # re-stamped by moves._summon on a fresh Tribute Summon
        inst.tributed_iids = []  # the tribute-cost record doesn't outlive the field
        inst.effect_activated_on_turn = None  # a revived card may use its once/turn again
        inst.attack_disabled_on_turn = None

    def send_to_graveyard(self, iid: int, by_battle: bool = False) -> None:
        """Move a card to its *owner's* Graveyard, clearing field flags. ``by_battle``
        marks a battle destruction so a "destroyed by battle" trigger can tell it
        apart from an effect destruction (Mystic Tomato recruits only on battle)."""
        inst = self.cards[iid]
        from_field = inst.zone in (Zone.MONSTER, Zone.SPELL_TRAP, Zone.FIELD)
        self._remove_from_current_location(iid)
        if inst.card.is_token:
            # A Token that leaves the field is removed from the game — it never rests
            # in the Graveyard, so it raises no "sent to GY" trigger and is forgotten.
            self._clear_field_flags(inst)
            del self.cards[iid]
            return
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
        card on the field — the sources that radiate passive modifiers (FieldMod,
        EquipMod, AttackRestriction). A card whose effects are negated by a face-up
        class negator (Imperial Order negates Spell effects → a Field/Equip Spell's
        boost vanishes; Royal Decree negates a Continuous Trap's rider) is skipped."""
        for idx, player in enumerate(self.players):
            fz = player.field_zone
            if fz is not None and self.cards[fz].is_face_up and not self.effect_negated(fz):
                yield self.cards[fz], idx
            for sid in player.spell_trap_zones:
                if sid is not None and self.cards[sid].is_face_up and not self.effect_negated(sid):
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
        """Whether the monster deals piercing battle damage to a defender it breaks."""
        return self._self_rider(iid, Piercing) is not None

    def damage_step_bonus(self, iid: int, opposing_iid: int | None, *, is_attacker: bool, which: str) -> int:
        """The Damage-Step-only ATK/DEF swing ``iid`` gets in a battle against
        ``opposing_iid`` (None = a direct attack). ``is_attacker`` says which side of the
        battle ``iid`` is on; ``which`` is "atk"/"defn". Combat-only — never part of the
        monster's continuous stats. Suppressed while the effect is inactive or negated."""
        inst = self.cards.get(iid)
        if inst is None or not inst.effects_active or self.monster_effects_negated(iid):
            return 0
        total = 0
        for mod in inst.card.continuous:
            if not isinstance(mod, DamageStepBonus):
                continue
            allowed = ("attacking", "either") if is_attacker else ("attacked", "either")
            if mod.when not in allowed:
                continue
            if mod.vs_direct:
                if opposing_iid is not None:
                    continue
            else:
                if opposing_iid is None:
                    continue
                other = self.cards[opposing_iid].card
                if mod.vs_race is not None and other.race != mod.vs_race:
                    continue
                if mod.vs_attribute is not None and other.attribute != mod.vs_attribute:
                    continue
            total += mod.atk if which == "atk" else mod.defn
        return total

    def can_attack_directly(self, iid: int) -> bool:
        """Whether the monster may declare a direct attack despite the opponent having
        monsters (a face-up CanAttackDirectly rider)."""
        return self._self_rider(iid, CanAttackDirectly) is not None

    def is_battle_indestructible(self, iid: int) -> bool:
        """Whether the monster cannot be destroyed by battle (a BattleIndestructible rider)."""
        return self._self_rider(iid, BattleIndestructible) is not None

    def max_attacks(self, iid: int) -> int:
        """How many attacks the monster may declare this Battle Phase — 2+ for a
        face-up MultiAttacker (Hayabusa Knight), else 1."""
        mod = self._self_rider(iid, MultiAttacker)
        return mod.times if mod is not None else 1

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
