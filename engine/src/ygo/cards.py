"""Card *definitions* (the printed, immutable card) and the card registry.

A ``CardDef`` is the static template for a card — its printed stats and text.
The mutable, in-play copy of a card is a ``CardInstance`` (see ``state.py``).

Card effects are *not* modelled here yet: at Milestone 1 every monster we use is
vanilla. The ``effects`` field is reserved for the declarative effect layer (M2),
which we'll author against current rulings rather than the loose v6.0 wording.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from .card_effects import EFFECTS
from .enums import Attribute, CardType, MonsterCategory, SpellTrapProperty
from .paths import CARD_DB_DIR, DEFAULT_CARD_DB


def _load_image_ids() -> dict[str, int]:
    """name -> YGOPRODeck image id, produced by scripts/download_card_images.py."""
    path = CARD_DB_DIR / "card_image_ids.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


_IMAGE_IDS = _load_image_ids()

# The CSV Type column folds race + categories together, e.g.
#   "Aqua"                         -> vanilla Aqua monster
#   "Insect  / Effect"             -> Insect monster with an effect
#   "Spellcaster  / Fusion / Effect"
#   "Magic" / "Trap"               -> Spell / Trap card
_CATEGORY_WORDS = {c.value.lower(): c for c in MonsterCategory}


@dataclass(frozen=True)
class CardDef:
    """The printed card. Immutable and shared by all instances of that card."""

    name: str
    card_type: CardType
    text: str = ""

    # --- monster fields (None for spells/traps) ---
    attribute: Attribute | None = None
    race: str | None = None
    level: int | None = None
    attack: int | None = None
    defense: int | None = None
    categories: frozenset[MonsterCategory] = field(default_factory=frozenset)

    # --- spell/trap fields (None for monsters) ---
    subtype: SpellTrapProperty | None = None  # the Spell/Trap icon (Equip, Quick-Play, ...)

    # --- meta ---
    status: str | None = None  # banlist: Forbidden / Limited / Semi-Limited / None
    image_id: int | None = None  # YGOPRODeck art id (None -> no downloaded art)

    # Reserved for the declarative effect layer (Milestone 2).
    effects: tuple = ()

    # ----- convenience predicates -----
    @property
    def is_monster(self) -> bool:
        return self.card_type is CardType.MONSTER

    @property
    def is_spell(self) -> bool:
        return self.card_type is CardType.SPELL

    @property
    def is_trap(self) -> bool:
        return self.card_type is CardType.TRAP

    @property
    def has_effect(self) -> bool:
        """True if this monster has an effect (i.e. is not vanilla)."""
        return MonsterCategory.EFFECT in self.categories

    @property
    def is_vanilla(self) -> bool:
        """A monster with no effect text — needs zero rules logic."""
        return self.is_monster and not self.has_effect

    @property
    def is_fusion(self) -> bool:
        return MonsterCategory.FUSION in self.categories

    @property
    def is_ritual(self) -> bool:
        return MonsterCategory.RITUAL in self.categories

    @property
    def goes_in_extra_deck(self) -> bool:
        return self.is_fusion

    @property
    def is_permanent(self) -> bool:
        """A Spell/Trap that stays on the field after activating (vs. going to GY)."""
        return self.subtype in (
            SpellTrapProperty.CONTINUOUS,
            SpellTrapProperty.EQUIP,
            SpellTrapProperty.FIELD,
        )

    @property
    def can_normal_summon(self) -> bool:
        """True if this monster reaches the field via Normal/Tribute Summon.

        Fusion monsters need a Fusion Summon; Ritual monsters need a Ritual
        Summon — neither can be Normal/Tribute Summoned.
        """
        return self.is_monster and not self.is_fusion and not self.is_ritual


# --------------------------------------------------------------------------- #
#  Parsing helpers
# --------------------------------------------------------------------------- #
def _clean(value: str | None) -> str:
    return (value or "").strip()


def _to_int(value: str | None):
    """Parse a numeric cell that may be empty or a float like '3000.0'."""
    s = _clean(value)
    if not s or s.lower() == "nan":
        return None
    return int(float(s))


def _parse_attribute(value: str | None) -> Attribute | None:
    s = _clean(value).upper()
    return Attribute[s] if s in Attribute.__members__ else None


def _parse_property(value: str | None) -> SpellTrapProperty | None:
    s = _clean(value)
    for prop in SpellTrapProperty:
        if prop.value.lower() == s.lower():
            return prop
    return None


def _parse_monster_type(type_field: str) -> tuple[str, frozenset[MonsterCategory]]:
    """Split a monster Type line into (race, categories).

    Examples:
      "Aqua"                    -> ("Aqua", {NORMAL})
      "Insect  / Effect"        -> ("Insect", {EFFECT})
      "Spellcaster / Fusion / Effect" -> ("Spellcaster", {FUSION, EFFECT})
    """
    parts = [p.strip() for p in type_field.split("/") if p.strip()]
    race = parts[0] if parts else type_field.strip()
    categories = {
        _CATEGORY_WORDS[p.lower()] for p in parts[1:] if p.lower() in _CATEGORY_WORDS
    }
    if not categories:
        categories = {MonsterCategory.NORMAL}
    return race, frozenset(categories)


def card_from_row(row: dict) -> CardDef:
    """Build a CardDef from one CSV row."""
    name = _clean(row.get("Name"))
    type_field = _clean(row.get("Type"))
    text = _clean(row.get("Description"))
    status = _clean(row.get("Status")) or None

    effects = EFFECTS.get(name, ())
    image_id = _IMAGE_IDS.get(name)

    if type_field == "Magic":  # v6.0 wording for Spell
        return CardDef(
            name=name,
            card_type=CardType.SPELL,
            text=text,
            subtype=_parse_property(row.get("Property")) or SpellTrapProperty.NORMAL,
            status=status,
            image_id=image_id,
            effects=effects,
        )
    if type_field == "Trap":
        return CardDef(
            name=name,
            card_type=CardType.TRAP,
            text=text,
            subtype=_parse_property(row.get("Property")) or SpellTrapProperty.NORMAL,
            status=status,
            image_id=image_id,
            effects=effects,
        )

    race, categories = _parse_monster_type(type_field)
    return CardDef(
        name=name,
        card_type=CardType.MONSTER,
        text=text,
        attribute=_parse_attribute(row.get("Attribute")),
        race=race,
        level=_to_int(row.get("Level")),
        attack=_to_int(row.get("Attack")),
        defense=_to_int(row.get("Defense")),
        categories=categories,
        status=status,
        image_id=image_id,
        effects=effects,
    )


class CardRegistry:
    """An immutable, name-keyed lookup of every CardDef in a card pool."""

    def __init__(self, cards: dict[str, CardDef]):
        self._by_name = cards

    @classmethod
    def load_csv(cls, path: Path | str = DEFAULT_CARD_DB) -> "CardRegistry":
        path = Path(path)
        by_name: dict[str, CardDef] = {}
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                card = card_from_row(row)
                if not card.name:
                    continue
                # First definition wins on duplicate names.
                by_name.setdefault(card.name, card)
        return cls(by_name)

    def get(self, name: str) -> CardDef | None:
        return self._by_name.get(name.strip())

    def __contains__(self, name: str) -> bool:
        return name.strip() in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)

    def __iter__(self):
        return iter(self._by_name.values())
