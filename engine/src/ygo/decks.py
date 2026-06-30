"""Load deck blueprints (text exports) into lists of card definitions.

Supports the ygoprodeck export format, e.g.::

    //ydk decklist
    3 Blue-Eyes White Dragon
    1 Lord of D.
    ...
    #EXTRA DECK / EXTRA DECK
    1 Some Fusion Monster

Cards missing from the registry are reported (not silently dropped) so we can
see exactly what a given blueprint needs from the card pool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .cards import CardDef, CardRegistry

_LINE_RE = re.compile(r"^\s*(\d+)\s+(.+?)\s*$")


@dataclass
class DeckList:
    """A resolved deck: main/extra CardDefs plus any unresolved names."""

    name: str
    main: list[CardDef] = field(default_factory=list)
    extra: list[CardDef] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def main_size(self) -> int:
        return len(self.main)

    @property
    def extra_size(self) -> int:
        return len(self.extra)


def parse_blueprint(path: Path | str) -> list[tuple[str, int, str]]:
    """Parse a blueprint into ``(section, count, card_name)`` rows.

    ``section`` is "main" or "extra". Counts are expanded by the caller.
    """
    path = Path(path)
    rows: list[tuple[str, int, str]] = []
    section = "main"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("//") or line.startswith("#"):
            # Only a real header (e.g. "#EXTRA DECK") switches section — a comment
            # that merely mentions "extra deck" must not.
            if line.lstrip("/#! ").upper().startswith("EXTRA"):
                section = "extra"
            continue  # comment / section header
        match = _LINE_RE.match(line)
        if not match:
            continue
        count, name = int(match.group(1)), match.group(2).strip()
        rows.append((section, count, name))
    return rows


def _blueprint_title(path: Path) -> str | None:
    """A deck's display name from its leading ``# Title`` comment, if any.

    ``to_blueprint_text`` writes the deck name as ``# <name>`` on line 1, so a
    saved deck round-trips its real name (casing and spaces) instead of falling
    back to the slugged filename. ``#EXTRA DECK`` (no space after ``#``) and
    ``//`` comments are not titles.
    """
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"^#\s+(.+)$", line)
        return match.group(1).strip() if match else None
    return None


def load_decklist(path: Path | str, registry: CardRegistry, name: str | None = None) -> DeckList:
    """Resolve a blueprint file against the card registry."""
    path = Path(path)
    deck = DeckList(name=name or _blueprint_title(path) or path.stem)
    for section, count, card_name in parse_blueprint(path):
        card = registry.get(card_name)
        if card is None:
            deck.missing.extend([card_name] * count)
            continue
        target = deck.extra if (section == "extra" or card.goes_in_extra_deck) else deck.main
        target.extend([card] * count)
    return deck
