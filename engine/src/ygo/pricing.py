"""Card valuation: what a card is worth in Duelist Points.

The meta-game's shop economy needs a price for every card — to buy singles and
to sell duplicates back — plus a sane price for every booster pack. We compute
it all from data we already have, with a **hybrid** model that blends three
signals:

* **print rarity** (scarcity) — the rarest printing of the card across the GBA
  booster packs (Common → Secret Rare). ~42% of pool cards appear in *no*
  purchasable pack, so those get a *synthetic* rarity inferred from power +
  banlist status, and still land at a sensible tier.
* **power** (desirability) — ATK/DEF, having an effect, level efficiency, and
  summoning type. Universal: every monster has stats, so nothing is unpriced.
* **banlist** (competitive scarcity) — Forbidden/Limited cards command a
  premium. We read this from a fixed *reference* list (the bundled OCG March
  2008 list, the last pre-Synchro list, matching the pool cutoff) so a card's
  worth is intrinsic and doesn't swing with whatever format you're playing.

    value = (rarity_base + power_bonus) * status_mult   (rounded up to a clean DP step)

Three derived prices come off that intrinsic ``card_value``:

* :func:`buy_value` — the single-card shop price (full value).
* :func:`sell_value` — what selling a duplicate pays (:data:`SELL_RATE` of value).
* :func:`pack_price` — a booster's price, floored at its weighted resale value so
  that buying packs to resell the pulls never turns a profit (a few GBA bulk
  packs ship with a missing-data placeholder price far below their contents).

All prices round **up** to the nearest :data:`ROUND_TO` DP for clean numbers.
"""

from __future__ import annotations

import math
import weakref
from functools import lru_cache

from .banlist import NO_RESTRICTIONS, BanList, load_banlist
from .cards import CardDef, CardRegistry

# Rarity tiers, rarest last. "(Unsorted)" packs (rarity unknown in the source)
# count as Common. Ranks are the keys used throughout this module.
RARITY_NAMES = {0: "Common", 1: "Rare", 2: "Super Rare", 3: "Ultra Rare", 4: "Secret Rare"}
_PACK_RARITY_RANK = {
    "Common": 0,
    "(Unsorted)": 0,
    "Rare": 1,
    "Super Rare": 2,
    "Ultra Rare": 3,
    "Secret Rare": 4,
}

# Base DP per rarity tier — the scarcity backbone of the price.
RARITY_BASE = {0: 15, 1: 50, 2: 150, 3: 400, 4: 1000}

# How many DP each point of power score adds on top of the rarity base.
POWER_PER_POINT = 15

# Banlist premium: Forbidden cards are the format's bombs, Limited next, etc.
# Keyed by the reference list's copy cap (0 = Forbidden, 1 = Limited, 2 = Semi).
STATUS_MULT = {0: 2.0, 1: 1.6, 2: 1.25}

# The list whose restrictions define a card's intrinsic competitive scarcity.
REFERENCE_BANLIST_ID = "ocg_2008_03"

# A duplicate sells for this fraction of its value. Pack prices are floored at
# their weighted resale value (:func:`pack_price`), so even at this rate buying
# packs to resell the pulls loses DP — verified by the arbitrage test.
SELL_RATE = 0.25

# Every price snaps up to a multiple of this many DP, for clean numbers.
ROUND_TO = 50


def _round_up(amount: float) -> int:
    """Round a raw price up to the next multiple of :data:`ROUND_TO` (min one step)."""
    return max(ROUND_TO, int(math.ceil(amount / ROUND_TO) * ROUND_TO))


@lru_cache(maxsize=1)
def reference_banlist() -> BanList:
    """The fixed list used for the competitive-scarcity multiplier."""
    try:
        return load_banlist(REFERENCE_BANLIST_ID)
    except (FileNotFoundError, ValueError):
        return NO_RESTRICTIONS


# Keyed on the registry *object* (not id(registry), which a GC'd-then-reused
# object could collide with, serving a stale map); the weak keys also let a
# retired registry's cache entry be collected.
_RARITY_MAP_CACHE: "weakref.WeakKeyDictionary[CardRegistry, dict[str, int]]" = (
    weakref.WeakKeyDictionary()
)


def rarity_map(registry: CardRegistry) -> dict[str, int]:
    """``{card_name: rarity_rank}`` — each card's *rarest* printing across all
    purchasable packs. Cards in no pack are absent (they get a synthetic rank).

    Built lazily from the pack catalogue and cached per registry; importing
    :mod:`packs` here (rather than at module top) keeps the import graph a DAG.
    """
    cached = _RARITY_MAP_CACHE.get(registry)
    if cached is not None:
        return cached

    from .packs import list_packs

    best: dict[str, int] = {}
    for pack in list_packs(registry):
        for rarity, names in pack.by_rarity.items():
            rank = _PACK_RARITY_RANK.get(rarity, 0)
            for name in names:
                if rank > best.get(name, -1):
                    best[name] = rank
    _RARITY_MAP_CACHE[registry] = best
    return best


def power_score(card: CardDef) -> float:
    """A universal 0..~10 desirability score from a card's printed text/stats.

    Monsters score off their bigger battle stat, with bumps for having an
    effect, being a boss-tier (Ritual/Fusion) summon, and being an efficient
    low-level beater. Spells/Traps have no stats, so they start from a flat
    "this is a tool" value, bumped when their effect is actually implemented.
    """
    if card.is_monster:
        body = max(card.attack or 0, card.defense or 0)
        score = body / 600.0  # a 3000-body monster -> 5.0
        if card.has_effect:
            score += 1.5
        if card.is_ritual or card.is_fusion:
            score += 0.5
        if (card.level or 0) <= 4 and body >= 1800:
            score += 1.0  # efficient beater for its level
        return score
    score = 2.5
    if card.effects or card.continuous:
        score += 1.0  # has an implemented effect, not a dead vanilla spell/trap
    return score


def _status_cap(card: CardDef, banlist: BanList) -> int | None:
    """The reference list's copy cap for this card (0/1/2), or None if unrestricted."""
    cap = banlist.limit_for(card.name)
    return cap if cap in STATUS_MULT else None


def synthetic_rarity_rank(card: CardDef, banlist: BanList | None = None) -> int:
    """Rarity for a card that appears in no pack — inferred from power + banlist.

    Restricted cards are treated as scarce by definition; otherwise the rank
    tracks the power score so a strong card never reads as a bulk common.
    """
    banlist = banlist or reference_banlist()
    cap = _status_cap(card, banlist)
    if cap == 0:  # Forbidden -> Secret
        return 4
    if cap == 1:  # Limited -> Ultra
        return 3
    power = power_score(card)
    if power >= 6:
        return 3
    if power >= 4.5:
        return 2
    if power >= 3:
        return 1
    return 0


def rarity_rank(card: CardDef, registry: CardRegistry, banlist: BanList | None = None) -> int:
    """The card's effective rarity rank — its rarest printing, or a synthetic
    rank when it appears in no purchasable pack."""
    rank = rarity_map(registry).get(card.name)
    if rank is not None:
        return rank
    return synthetic_rarity_rank(card, banlist)


def card_value(card: CardDef, registry: CardRegistry, banlist: BanList | None = None) -> int:
    """The card's intrinsic worth in DP (the single-card shop / buy price)."""
    banlist = banlist or reference_banlist()
    rank = rarity_rank(card, registry, banlist)
    base = RARITY_BASE[rank]
    bonus = int(power_score(card) * POWER_PER_POINT)
    mult = STATUS_MULT.get(_status_cap(card, banlist), 1.0)
    return _round_up((base + bonus) * mult)


def buy_value(card: CardDef, registry: CardRegistry, banlist: BanList | None = None) -> int:
    """What it costs to buy this card as a single (== its intrinsic value)."""
    return card_value(card, registry, banlist)


def sell_value(card: CardDef, registry: CardRegistry, banlist: BanList | None = None) -> int:
    """What selling a duplicate of this card pays out."""
    return _round_up(card_value(card, registry, banlist) * SELL_RATE)


def price_detail(card: CardDef, registry: CardRegistry, banlist: BanList | None = None) -> dict:
    """Everything the UI needs to show a price: rarity label + buy/sell DP."""
    banlist = banlist or reference_banlist()
    rank = rarity_rank(card, registry, banlist)
    value = card_value(card, registry, banlist)
    return {
        "rarity": RARITY_NAMES[rank],
        "value": value,
        "buy": value,
        "sell": _round_up(value * SELL_RATE),
    }


# --------------------------------------------------------------------------- #
#  Pack pricing
# --------------------------------------------------------------------------- #
def weighted_resale_ev(pack, registry: CardRegistry, banlist: BanList | None = None) -> float:
    """Expected DP from selling the contents of one opened pack.

    Uses the real rarity weighting from :func:`packs.open_pack` (commons
    dominate; the final slot is guaranteed Rare-or-better), so it reflects what
    a player actually pulls and resells — not a uniform best case.
    """
    from .packs import RARE_OR_BETTER, RARITY_WEIGHTS

    present = [r for r, names in pack.by_rarity.items() if names]
    if not present:
        return 0.0

    def slot_ev(choices: list[str]) -> float:
        total_w = sum(RARITY_WEIGHTS.get(r, RARITY_WEIGHTS["Common"]) for r in choices)
        if total_w <= 0:
            return 0.0
        ev = 0.0
        for r in choices:
            cards = pack.by_rarity[r]
            avg_sell = sum(sell_value(registry.get(n), registry, banlist) for n in cards) / len(cards)
            ev += (RARITY_WEIGHTS.get(r, RARITY_WEIGHTS["Common"]) / total_w) * avg_sell
        return ev

    rare_pool = [r for r in present if r in RARE_OR_BETTER]
    slots = min(pack.cards_per_pack, max(1, pack.distinct))
    total = 0.0
    for i in range(slots):
        guaranteed = i == slots - 1 and rare_pool
        total += slot_ev(rare_pool if guaranteed else present)
    return total


def pack_price(pack, registry: CardRegistry, banlist: BanList | None = None) -> int:
    """A booster's effective price: its source price, but never below the
    weighted resale value of its contents (so reselling pulls can't profit).
    Rounded up to a clean step."""
    floor = weighted_resale_ev(pack, registry, banlist)
    return _round_up(max(pack.price, floor))


def pack_resale_profit(pack, registry: CardRegistry, banlist: BanList | None = None) -> float:
    """Expected DP profit from buying a pack purely to sell its pulls. Must be
    ``<= 0`` for every purchasable pack (the economy's no-arbitrage invariant)."""
    return weighted_resale_ev(pack, registry, banlist) - pack_price(pack, registry, banlist)
