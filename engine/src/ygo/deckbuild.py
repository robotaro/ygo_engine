"""Deck construction: validate, query the pool, edit, and serialise decks.

The rules engine consumes a resolved :class:`~ygo.decks.DeckList`; this module is
the layer *above* it — everything you need to assemble a legal deck before a duel
ever starts:

  * :func:`validate_deck` — check a resolved deck against the v6.0 construction
    rules (main/extra sizes, the 3-copy limit, an optional Forbidden/Limited list).
  * :func:`search_pool` — filter/sort the card pool (the data a builder UI needs).
  * :func:`deck_playability` — how much of a deck actually *works* today, i.e. how
    many of its cards have an implemented effect (vanilla monsters always count).
  * :class:`DeckBuilder` — a small mutable editor: load a blueprint, add/remove
    cards, validate, and write the blueprint back out.

Validation is deliberately data-driven: the construction limits are module-level
constants and the banlist is a pluggable :class:`BanList`, so tightening fidelity
later means editing data, not branching code.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .cards import CardDef, CardRegistry
from .decks import DeckList, load_decklist
from .enums import Attribute, CardType, MonsterCategory

# --------------------------------------------------------------------------- #
#  v6.0 construction rules (the rulebook's "Deck Construction" section)
# --------------------------------------------------------------------------- #
MAIN_MIN = 40
MAIN_MAX = 60
EXTRA_MAX = 15
MAX_COPIES = 3  # at most 3 of any one card by name, across Main + Extra (+ Side)


# --------------------------------------------------------------------------- #
#  Banlist (Forbidden / Limited / Semi-Limited)
# --------------------------------------------------------------------------- #
_BANLIST_LIMITS = {"forbidden": 0, "limited": 1, "semi-limited": 2}


@dataclass(frozen=True)
class BanList:
    """A Forbidden/Limited list: card name -> max copies allowed (0..3).

    Any card not named defaults to :data:`MAX_COPIES`. This is intentionally a
    thin wrapper over a dict so a list can come from anywhere — a JSON file, the
    CSV ``Status`` column, or a test fixture.
    """

    name: str = "none"
    limits: dict[str, int] = field(default_factory=dict)

    def limit_for(self, card_name: str) -> int:
        return self.limits.get(card_name.strip(), MAX_COPIES)

    @classmethod
    def from_status(cls, registry: CardRegistry, *, name: str = "csv-status") -> "BanList":
        """Derive a banlist from each card's ``status`` field (CSV ``Status``
        column: Forbidden / Limited / Semi-Limited). Empty in the current pool,
        but this is the seam to populate once the data lands."""
        limits: dict[str, int] = {}
        for card in registry:
            cap = _BANLIST_LIMITS.get((card.status or "").strip().lower())
            if cap is not None:
                limits[card.name] = cap
        return cls(name=name, limits=limits)

    @classmethod
    def from_json(cls, path: Path | str) -> "BanList":
        """Load ``{"name": ..., "limits": {card_name: max_copies}}`` from JSON."""
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(name=data.get("name", path.stem), limits=dict(data.get("limits", {})))

    def to_json_obj(self) -> dict:
        """The JSON-serialisable form :meth:`from_json` reads back."""
        return {"name": self.name, "limits": dict(self.limits)}

    def counts_by_status(self) -> dict[str, int]:
        """How many cards are Forbidden / Limited / Semi-Limited in this list."""
        out = {"forbidden": 0, "limited": 0, "semi-limited": 0}
        for cap in self.limits.values():
            if cap == 0:
                out["forbidden"] += 1
            elif cap == 1:
                out["limited"] += 1
            elif cap == 2:
                out["semi-limited"] += 1
        return out


# The everyday default: no Forbidden/Limited list at all, just the 3-copy rule.
NO_RESTRICTIONS = BanList(name="No Restrictions")


# --------------------------------------------------------------------------- #
#  Banlist catalogue (bundled presets + the player's own custom lists)
# --------------------------------------------------------------------------- #
#  Presets live in assets/banlists/*.json; the player's custom lists live in
#  assets/banlists/user/ (gitignored, like user decks). A banlist *id* is its
#  path under that directory, without the .json suffix: "none", "ocg_2008_03",
#  "user/my_list". The id "none" always resolves, even with no file present.
USER_BANLIST_SUBDIR = "user"


def _banlists_root() -> Path:
    from .paths import BANLISTS_DIR

    return BANLISTS_DIR


def _resolve_banlist_path(banlist_id: str) -> Path | None:
    """Map a banlist id to its JSON file, refusing to escape the banlists dir."""
    if not banlist_id:
        return None
    root = _banlists_root().resolve()
    candidate = (root / f"{banlist_id}.json").resolve()
    if root not in candidate.parents and candidate != root:
        return None  # path traversal attempt
    return candidate


def load_banlist(banlist_id: str | None) -> BanList:
    """Load a banlist by id. ``None``/``"none"``/missing → :data:`NO_RESTRICTIONS`."""
    if not banlist_id or banlist_id == "none":
        path = _resolve_banlist_path("none")
        return BanList.from_json(path) if path and path.exists() else NO_RESTRICTIONS
    path = _resolve_banlist_path(banlist_id)
    if path is None or not path.exists():
        raise FileNotFoundError(f"unknown banlist: {banlist_id!r}")
    return BanList.from_json(path)


def list_banlists() -> list[dict]:
    """Catalogue every available banlist (bundled + user) for a picker UI.

    Each entry is ``{id, name, builtin, restricted, by_status}`` where
    ``restricted`` is the number of named cards and ``by_status`` breaks that
    down into forbidden/limited/semi-limited. "No Restrictions" leads the list.
    """
    root = _banlists_root()
    entries: list[dict] = []
    seen_none = False
    for path in sorted(root.rglob("*.json")) if root.exists() else []:
        rel = path.relative_to(root)
        banlist_id = rel.with_suffix("").as_posix()
        builtin = USER_BANLIST_SUBDIR not in rel.parts
        try:
            bl = BanList.from_json(path)
        except (json.JSONDecodeError, OSError):
            continue  # skip a corrupt file rather than break the whole catalogue
        if banlist_id == "none":
            seen_none = True
        entries.append(
            {
                "id": banlist_id,
                "name": bl.name,
                "builtin": builtin,
                "restricted": len(bl.limits),
                "by_status": bl.counts_by_status(),
            }
        )
    if not seen_none:  # always offer No Restrictions, even with no file on disk
        entries.insert(
            0,
            {
                "id": "none",
                "name": NO_RESTRICTIONS.name,
                "builtin": True,
                "restricted": 0,
                "by_status": NO_RESTRICTIONS.counts_by_status(),
            },
        )
    # "none" first, then bundled presets, then the player's custom lists.
    entries.sort(key=lambda e: (e["id"] != "none", not e["builtin"], e["name"].lower()))
    return entries


def save_banlist(banlist: BanList, banlist_id: str) -> Path:
    """Write a (custom) banlist to ``assets/banlists/<banlist_id>.json``.

    The id is forced under the ``user/`` subdir so saving can never clobber a
    bundled preset. Returns the path written.
    """
    stem = banlist_id.strip().strip("/")
    if not stem.startswith(f"{USER_BANLIST_SUBDIR}/"):
        stem = f"{USER_BANLIST_SUBDIR}/{stem}"
    path = _resolve_banlist_path(stem)
    user_root = (_banlists_root() / USER_BANLIST_SUBDIR).resolve()
    # Must land strictly inside user/ — never clobber a bundled preset.
    if path is None or user_root not in path.parents:
        raise ValueError(f"invalid banlist id: {banlist_id!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(banlist.to_json_obj(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
#  Validation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Issue:
    """One validation finding. ``error`` makes a deck illegal; ``warning`` doesn't."""

    level: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        mark = "✗" if self.level == "error" else "⚠"
        return f"{mark} {self.message}"


@dataclass
class DeckReport:
    """The outcome of validating a deck."""

    deck_name: str
    main_size: int
    extra_size: int
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def is_legal(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        status = "LEGAL" if self.is_legal else "ILLEGAL"
        head = (
            f"{self.deck_name}: {status}  "
            f"(main {self.main_size}, extra {self.extra_size}, "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s))"
        )
        lines = [head] + [f"    {issue}" for issue in self.issues]
        return "\n".join(lines)


def validate_deck(deck: DeckList, *, banlist: BanList | None = None) -> DeckReport:
    """Check a resolved deck against the v6.0 construction rules.

    Errors (make the deck illegal): main outside 40-60, extra over 15, more
    copies of a card than allowed, and any unresolved card names. Warnings:
    a near-minimum main deck, or an Extra-Deck card that landed in the Main list.
    """
    report = DeckReport(deck.name, deck.main_size, deck.extra_size)
    add = lambda level, msg: report.issues.append(Issue(level, msg))  # noqa: E731

    # -- sizes --
    if deck.main_size < MAIN_MIN:
        add("error", f"Main Deck has {deck.main_size} cards (minimum {MAIN_MIN}).")
    elif deck.main_size > MAIN_MAX:
        add("error", f"Main Deck has {deck.main_size} cards (maximum {MAIN_MAX}).")
    if deck.extra_size > EXTRA_MAX:
        add("error", f"Extra Deck has {deck.extra_size} cards (maximum {EXTRA_MAX}).")

    # -- copy limit (counts across Main + Extra, as the banlist does) --
    counts = Counter(c.name for c in (*deck.main, *deck.extra))
    for name, n in sorted(counts.items()):
        cap = banlist.limit_for(name) if banlist else MAX_COPIES
        cap = min(cap, MAX_COPIES)
        if n > cap:
            if cap == 0:
                add("error", f"{name}: {n} copies — Forbidden (0 allowed).")
            else:
                add("error", f"{name}: {n} copies (maximum {cap}).")

    # -- unresolved names: a deck the pool can't build --
    for name in sorted(set(deck.missing)):
        add("error", f"Unknown card (not in pool): {name}")

    # -- soft hints --
    if MAIN_MIN <= deck.main_size <= MAIN_MIN + 2:
        add("warning", f"Main Deck is at/near the {MAIN_MIN}-card minimum.")
    misplaced = [c.name for c in deck.main if c.goes_in_extra_deck]
    if misplaced:
        add("warning", f"Extra-Deck card(s) in the Main list: {', '.join(sorted(set(misplaced)))}")

    return report


# --------------------------------------------------------------------------- #
#  Playability — how much of a deck actually has implemented behaviour
# --------------------------------------------------------------------------- #
def _needs_logic(card: CardDef) -> bool:
    """A card that requires rules logic to play correctly (vanilla monsters don't)."""
    if card.is_monster:
        return card.has_effect
    return True  # every Spell/Trap does something


# Cards whose behaviour lives in the engine kernel rather than the effect tables, so
# they play correctly despite carrying no EFFECTS/CONTINUOUS entry. The five "Forbidden
# One" pieces win the Duel via GameState.exodia_winner (state.EXODIA_PIECES); only the
# head carries effect text (the limbs are vanilla and already count), but we list all
# five so the source of truth is explicit.
_KERNEL_IMPLEMENTED = frozenset(
    {
        "Exodia the Forbidden One",
        "Right Arm of the Forbidden One",
        "Left Arm of the Forbidden One",
        "Right Leg of the Forbidden One",
        "Left Leg of the Forbidden One",
    }
)


def _has_logic(card: CardDef) -> bool:
    return bool(card.effects or card.continuous or card.hand_summon)


def is_functional(card: CardDef) -> bool:
    """True if the card plays correctly today: a vanilla monster, a card whose effect is
    implemented, or one whose behaviour is handled by the engine kernel (Exodia's win
    condition). A non-vanilla card with no implemented effect is not — it currently sits
    on the board doing nothing."""
    return not _needs_logic(card) or _has_logic(card) or card.name in _KERNEL_IMPLEMENTED


@dataclass
class PlayabilityReport:
    deck_name: str
    total: int
    functional: int
    nonfunctional: list[str]  # distinct card names that need an effect but lack one

    @property
    def pct(self) -> float:
        return 100.0 * self.functional / self.total if self.total else 100.0


def deck_playability(deck: DeckList) -> PlayabilityReport:
    """How playable a deck is right now, by share of cards with working behaviour."""
    cards = [*deck.main, *deck.extra]
    functional = sum(1 for c in cards if is_functional(c))
    dead = sorted({c.name for c in cards if not is_functional(c)})
    return PlayabilityReport(deck.name, len(cards), functional, dead)


# --------------------------------------------------------------------------- #
#  Pool query (what a builder UI lists / filters)
# --------------------------------------------------------------------------- #
def search_pool(
    registry: CardRegistry,
    *,
    text: str | None = None,
    card_type: CardType | None = None,
    attribute: Attribute | None = None,
    race: str | None = None,
    category: MonsterCategory | None = None,
    level: int | None = None,
    min_atk: int | None = None,
    max_atk: int | None = None,
    functional_only: bool = False,
    limit: int | None = None,
) -> list[CardDef]:
    """Filter the card pool. ``text`` matches name or card text (case-insensitive).

    All criteria are ANDed; ``None`` means "don't filter on this". Results are
    sorted by card type then name for stable display.
    """
    needle = text.lower() if text else None

    def keep(c: CardDef) -> bool:
        if needle and needle not in c.name.lower() and needle not in (c.text or "").lower():
            return False
        if card_type is not None and c.card_type is not card_type:
            return False
        if attribute is not None and c.attribute is not attribute:
            return False
        if race is not None and (c.race or "").lower() != race.lower():
            return False
        if category is not None and category not in c.categories:
            return False
        if level is not None and c.level != level:
            return False
        if min_atk is not None and (c.attack or 0) < min_atk:
            return False
        if max_atk is not None and (c.attack or 0) > max_atk:
            return False
        if functional_only and not is_functional(c):
            return False
        return True

    hits = sorted((c for c in registry if keep(c)), key=lambda c: (c.card_type.value, c.name))
    return hits[:limit] if limit is not None else hits


# --------------------------------------------------------------------------- #
#  Blueprint serialisation (round-trips with ygo.decks.parse_blueprint)
# --------------------------------------------------------------------------- #
def _counts_in_order(cards: list[CardDef]) -> list[tuple[str, int]]:
    """Collapse an expanded card list to ``(name, count)`` rows, first-seen order."""
    counts: Counter[str] = Counter()
    order: list[str] = []
    for c in cards:
        if c.name not in counts:
            order.append(c.name)
        counts[c.name] += 1
    return [(name, counts[name]) for name in order]


def to_blueprint_text(deck: DeckList) -> str:
    """Serialise a DeckList to the ``count name`` blueprint format we load from."""
    lines = [f"# {deck.name}"]
    for name, n in _counts_in_order(deck.main):
        lines.append(f"{n} {name}")
    if deck.extra:
        lines.append("#EXTRA DECK")
        for name, n in _counts_in_order(deck.extra):
            lines.append(f"{n} {name}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
#  DeckBuilder — a small mutable editor
# --------------------------------------------------------------------------- #
class DeckBuilder:
    """Assemble or edit a deck against a card pool.

    Cards are routed to Main or Extra automatically by ``goes_in_extra_deck``.
    The builder *allows* illegal states (over the copy limit, wrong size) and
    surfaces them via :meth:`validate` — like a real deck editor that lets you
    build freely and flags problems, rather than blocking each keystroke.
    """

    def __init__(
        self,
        registry: CardRegistry,
        *,
        name: str = "Untitled",
        banlist: BanList | None = None,
    ):
        self.registry = registry
        self.name = name
        self.banlist = banlist
        self._main: Counter[str] = Counter()
        self._extra: Counter[str] = Counter()

    # -- editing --
    def add(self, card_name: str, count: int = 1) -> "DeckBuilder":
        """Add ``count`` copies of a card. Raises if the name isn't in the pool."""
        card = self.registry.get(card_name)
        if card is None:
            raise KeyError(f"Not in card pool: {card_name!r}")
        bucket = self._extra if card.goes_in_extra_deck else self._main
        bucket[card.name] += count
        return self

    def remove(self, card_name: str, count: int = 1) -> "DeckBuilder":
        """Remove up to ``count`` copies of a card (no-op below zero)."""
        card = self.registry.get(card_name)
        key = card.name if card else card_name.strip()
        for bucket in (self._main, self._extra):
            if bucket.get(key):
                bucket[key] = max(0, bucket[key] - count)
                if bucket[key] == 0:
                    del bucket[key]
        return self

    # -- views --
    @property
    def main_counts(self) -> dict[str, int]:
        return dict(self._main)

    @property
    def extra_counts(self) -> dict[str, int]:
        return dict(self._extra)

    @property
    def main_size(self) -> int:
        return sum(self._main.values())

    @property
    def extra_size(self) -> int:
        return sum(self._extra.values())

    def to_decklist(self) -> DeckList:
        deck = DeckList(name=self.name)
        for bucket, target in ((self._main, "main"), (self._extra, "extra")):
            for card_name, n in bucket.items():
                card = self.registry.get(card_name)
                if card is None:  # shouldn't happen via add(), but stay honest
                    deck.missing.extend([card_name] * n)
                    continue
                (deck.extra if card.goes_in_extra_deck else deck.main).extend([card] * n)
        return deck

    def validate(self) -> DeckReport:
        return validate_deck(self.to_decklist(), banlist=self.banlist)

    # -- persistence --
    @classmethod
    def from_blueprint(
        cls,
        path: Path | str,
        registry: CardRegistry,
        *,
        banlist: BanList | None = None,
        name: str | None = None,
    ) -> "DeckBuilder":
        deck = load_decklist(path, registry, name=name)
        builder = cls(registry, name=deck.name, banlist=banlist)
        for card in deck.main:
            builder._main[card.name] += 1
        for card in deck.extra:
            builder._extra[card.name] += 1
        return builder

    def to_blueprint_text(self) -> str:
        return to_blueprint_text(self.to_decklist())

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_blueprint_text(), encoding="utf-8")
        return path
