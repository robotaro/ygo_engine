"""Booster packs: the catalogue and the pull mechanic.

Packs are the data we scraped from the 8 GBA games (``assets/card_packs/gba``).
Each file is a ``# metadata`` header (price in DP, cards-per-pack) followed by
card names grouped under ``## Rarity`` lines, e.g.::

    # Pack: Live Vehicles — GX Duel Academy (GBA, 2006)
    # Cards per pack: 3 | Price: 400 DP | Cards in pack: 12 | ...
    ## Secret Rare
    Power Bond
    ## Common
    Cycroid
    ...

Opening a pack spends DP and rolls ``cards_per_pack`` cards, weighted so commons
are plentiful and Secret Rares are a treat, with one guaranteed Rare-or-better.
Only cards in the v6.0 pool can be pulled (so everything is ownable/usable);
"filter" packs that list a rule instead of cards are excluded from the shop.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from .cards import CardRegistry
from .paths import CARD_PACKS_DIR

# Pull odds per slot. Commons dominate; Secret Rares are rare. "(Unsorted)" cards
# (rarity unknown in the source) are treated as commons.
RARITY_WEIGHTS = {
    "Common": 100,
    "(Unsorted)": 100,
    "Rare": 28,
    "Super Rare": 9,
    "Ultra Rare": 3,
    "Secret Rare": 1,
}
RARE_OR_BETTER = ("Rare", "Super Rare", "Ultra Rare", "Secret Rare")

# Rarest first — used to pick a flagship card for a pack's box art.
_COVER_RARITY_ORDER = ("Secret Rare", "Ultra Rare", "Super Rare", "Rare", "Common", "(Unsorted)")

DEFAULT_CARDS_PER_PACK = 3
DEFAULT_PRICE = 100  # for old packs whose source listed no price


@dataclass
class PackDef:
    """One booster pack: where to buy it and what can come out."""

    id: str  # path under card_packs/ without suffix, e.g. "gba/gx_duel_academy/live_vehicles"
    name: str
    game: str
    price: int
    cards_per_pack: int
    by_rarity: dict[str, list[str]] = field(default_factory=dict)

    @property
    def card_names(self) -> list[str]:
        return [n for names in self.by_rarity.values() for n in names]

    @property
    def cover_card(self) -> str | None:
        """The card to use as the pack's box art: its namesake if the pack is
        named after one of its own cards, otherwise its rarest (flagship) card."""
        if not self.card_names:
            return None
        want = self.name.lower()
        for n in self.card_names:  # named after a card it actually contains?
            if n.lower() == want:
                return n
        # ...or a card whose name extends the pack's (Exodia -> Exodia the Forbidden One).
        contains = sorted((n for n in self.card_names if want in n.lower()), key=len)
        if contains:
            return contains[0]
        for rarity in _COVER_RARITY_ORDER:  # otherwise the flagship/rarest card
            if self.by_rarity.get(rarity):
                return self.by_rarity[rarity][0]
        return self.card_names[0]

    @property
    def distinct(self) -> int:
        return len(self.card_names)

    @property
    def purchasable(self) -> bool:
        """A real, openable pack: has a concrete card list to pull from."""
        return self.distinct >= 1


_HEADER_NAME = re.compile(r"^#\s*Pack:\s*(.+?)\s*$")
_PRICE = re.compile(r"Price:\s*(\d+)")
_PER_PACK = re.compile(r"Cards per pack:\s*(\d+)")


def _parse_pack(path: Path, root: Path, registry: CardRegistry) -> PackDef:
    """Parse one pack file, keeping only card names that resolve to the pool."""
    rel = path.relative_to(root).with_suffix("")
    game = rel.parts[1] if len(rel.parts) > 1 else "gba"
    name = rel.stem.replace("_", " ").title()
    price = DEFAULT_PRICE
    per_pack = DEFAULT_CARDS_PER_PACK
    by_rarity: dict[str, list[str]] = {}
    rarity = "Common"

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("## "):
            rarity = line[3:].strip()
            continue
        if line.startswith("#"):
            m = _HEADER_NAME.match(line)
            if m:
                name = m.group(1).split(" — ")[0].strip()
            if (pm := _PRICE.search(line)) is not None:
                price = int(pm.group(1))
            if (cm := _PER_PACK.search(line)) is not None:
                per_pack = int(cm.group(1))
            continue
        # a card name line — keep only if it's in the v6 pool
        if registry.get(line.strip()) is not None:
            by_rarity.setdefault(rarity, []).append(line.strip())

    return PackDef(
        id=rel.as_posix(),
        name=name,
        game=game,
        price=price,
        cards_per_pack=per_pack,
        by_rarity=by_rarity,
    )


def list_packs(registry: CardRegistry) -> list[PackDef]:
    """Every purchasable pack across all games, cheapest first."""
    if not CARD_PACKS_DIR.is_dir():
        return []
    packs = [
        _parse_pack(p, CARD_PACKS_DIR, registry)
        for p in sorted(CARD_PACKS_DIR.rglob("*.txt"))
    ]
    purchasable = [p for p in packs if p.purchasable]
    purchasable.sort(key=lambda p: (p.price, p.name))
    return purchasable


def get_pack(pack_id: str, registry: CardRegistry) -> PackDef | None:
    """Resolve a pack by id (traversal-guarded).

    Uses a ``parents``-based containment check, not a string prefix: the latter
    would wrongly admit a sibling like ``card_packs_x/...`` whose path merely
    *starts with* the root's string.
    """
    if not pack_id:
        return None
    root = CARD_PACKS_DIR.resolve()
    path = (root / pack_id).with_suffix(".txt").resolve()
    if root not in path.parents:  # outside the packs dir -> reject
        return None
    if not path.is_file():
        return None
    pack = _parse_pack(path, root, registry)
    return pack if pack.purchasable else None


def _weighted_rarity(rarities: list[str], rng: random.Random) -> str:
    weights = [RARITY_WEIGHTS.get(r, RARITY_WEIGHTS["Common"]) for r in rarities]
    return rng.choices(rarities, weights=weights, k=1)[0]


def open_pack(pack: PackDef, rng: random.Random) -> list[str]:
    """Roll ``cards_per_pack`` card names, weighted by rarity.

    One slot is guaranteed Rare-or-better when the pack has any such cards.
    Avoids repeating a card within the same pack while alternatives remain.
    """
    rarities = [r for r, names in pack.by_rarity.items() if names]
    if not rarities:
        return []
    rare_pool = [r for r in rarities if r in RARE_OR_BETTER]
    slots = min(pack.cards_per_pack, max(1, pack.distinct))

    pulled: list[str] = []
    for i in range(slots):
        guaranteed = i == slots - 1 and rare_pool and not any(
            c in (n for r in rare_pool for n in pack.by_rarity[r]) for c in pulled
        )
        choices = rare_pool if guaranteed else rarities
        # try a few times to avoid a duplicate within the pack
        for _ in range(8):
            rarity = _weighted_rarity(choices, rng)
            card = rng.choice(pack.by_rarity[rarity])
            if card not in pulled or pack.distinct <= len(pulled):
                break
        pulled.append(card)
    return pulled
