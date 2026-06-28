"""The rulebook's vocabulary, expressed as types.

These mirror the v6.0 Official Rulebook (and its glossary) directly: the same
attributes, card types, zones, positions, phases, and the three spell speeds
that govern the Chain.
"""

from __future__ import annotations

from enum import Enum, IntEnum


class CardType(Enum):
    """Top-level card kind. (v6.0 calls Spell Cards "Magic Cards".)"""

    MONSTER = "monster"
    SPELL = "spell"
    TRAP = "trap"


class Attribute(Enum):
    DARK = "DARK"
    LIGHT = "LIGHT"
    EARTH = "EARTH"
    WATER = "WATER"
    FIRE = "FIRE"
    WIND = "WIND"
    DIVINE = "DIVINE"  # reserved for the Egyptian Gods


class MonsterCategory(Enum):
    """A monster's special categories, parsed from the card's Type line.

    A monster may carry several (e.g. ``Spellcaster / Fusion / Effect``, or
    ``Aqua / Flip / Effect``). ``NORMAL`` means a vanilla monster with no effect
    text. The sub-type members (FLIP/SPIRIT/UNION/GEMINI/TOON) always accompany
    EFFECT — they refine *how* an effect monster behaves, they don't replace the
    "is an effect monster" bit.
    """

    NORMAL = "Normal"
    EFFECT = "Effect"
    FUSION = "Fusion"
    RITUAL = "Ritual"
    TOKEN = "Token"
    # Sub-types (v6.0 pool): each rides alongside EFFECT (see card_effects.py).
    FLIP = "Flip"
    SPIRIT = "Spirit"
    UNION = "Union"
    GEMINI = "Gemini"
    TOON = "Toon"


class SpellTrapProperty(Enum):
    """The icon on a Spell/Trap card (its sub-type)."""

    NORMAL = "Normal"
    CONTINUOUS = "Continuous"
    EQUIP = "Equip"
    FIELD = "Field"
    QUICK_PLAY = "Quick-Play"
    RITUAL = "Ritual"
    COUNTER = "Counter"


class Zone(Enum):
    """Where a card instance currently lives."""

    DECK = "deck"
    HAND = "hand"
    MONSTER = "monster_zone"
    SPELL_TRAP = "spell_trap_zone"
    FIELD = "field_zone"
    GRAVEYARD = "graveyard"
    EXTRA_DECK = "extra_deck"
    BANISHED = "banished"  # "removed from play"


class Position(Enum):
    """Battle position + facing for a card on the field.

    Monsters in the deck/hand/graveyard have no position (``None``).
    A Set Spell/Trap uses ``FACE_DOWN``.
    """

    FACE_UP_ATTACK = "face_up_attack"
    FACE_UP_DEFENSE = "face_up_defense"
    FACE_DOWN_DEFENSE = "face_down_defense"  # a Set monster
    FACE_DOWN = "face_down"  # a Set Spell/Trap

    @property
    def is_face_up(self) -> bool:
        return self in (Position.FACE_UP_ATTACK, Position.FACE_UP_DEFENSE)

    @property
    def is_face_down(self) -> bool:
        return not self.is_face_up

    @property
    def is_attack(self) -> bool:
        return self is Position.FACE_UP_ATTACK

    @property
    def is_defense(self) -> bool:
        return self in (Position.FACE_UP_DEFENSE, Position.FACE_DOWN_DEFENSE)


class Phase(Enum):
    """The six phases of a turn, in order."""

    DRAW = "draw_phase"
    STANDBY = "standby_phase"
    MAIN_1 = "main_phase_1"
    BATTLE = "battle_phase"
    MAIN_2 = "main_phase_2"
    END = "end_phase"


#: Canonical phase order for a turn (Battle may be skipped; handled by the engine).
TURN_PHASES: tuple[Phase, ...] = (
    Phase.DRAW,
    Phase.STANDBY,
    Phase.MAIN_1,
    Phase.BATTLE,
    Phase.MAIN_2,
    Phase.END,
)


class SpellSpeed(IntEnum):
    """How fast an effect is; you may only chain with equal-or-higher speed.

    1 = Normal/Continuous/Equip/Field Spells, Continuous/Ignition/Trigger/Flip monster effects.
    2 = Quick-Play Spells, Normal/Continuous Traps, Quick monster effects.
    3 = Counter Traps.
    """

    SPEED_1 = 1
    SPEED_2 = 2
    SPEED_3 = 3
