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
from .enums import Phase, Position, Zone

STARTING_LIFE_POINTS = 8000
MAX_MONSTER_ZONES = 5
MAX_SPELL_TRAP_ZONES = 5


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

    @property
    def name(self) -> str:
        return self.card.name

    @property
    def is_face_up(self) -> bool:
        return self.position is not None and self.position.is_face_up


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

    def send_to_graveyard(self, iid: int) -> None:
        """Move a card to its *owner's* Graveyard, clearing field flags."""
        inst = self.cards[iid]
        from_field = inst.zone in (Zone.MONSTER, Zone.SPELL_TRAP, Zone.FIELD)
        self._remove_from_current_location(iid)
        inst.zone = Zone.GRAVEYARD
        inst.controller = inst.owner
        inst.position = None
        inst.summoned_this_turn = False
        inst.attacked_this_turn = False
        inst.position_changed_this_turn = False
        inst.set_on_turn = None
        inst.equipped_to = None
        inst.linked_to = None
        self.players[inst.owner].graveyard.append(iid)
        # Queue "sent from the field to the Graveyard" triggers for the engine.
        if from_field and inst.card.is_monster:
            self.gy_from_field.append(iid)

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

    def effective_attack(self, iid: int) -> int:
        inst = self.cards[iid]
        if not inst.card.is_monster:
            return 0
        total = (inst.card.attack or 0) + sum(
            self._mod_delta(mod, ctrl, "atk") for mod, ctrl in self._equip_mods_on(iid)
        )
        return max(0, total)

    def effective_defense(self, iid: int) -> int:
        inst = self.cards[iid]
        if not inst.card.is_monster:
            return 0
        total = (inst.card.defense or 0) + sum(
            self._mod_delta(mod, ctrl, "def") for mod, ctrl in self._equip_mods_on(iid)
        )
        return max(0, total)

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
