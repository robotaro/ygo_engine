"""The player's persistent profile: Duelist Points, card library, and decks.

This is the save file the meta-game is built around. A profile owns:

* **Duelist Points (DP)** — the currency, earned by winning duels/tournaments
  and spent on booster packs.
* **collection** — ``{card_name: count}``, every card you own. Decks may only be
  built from cards in here (collection-gated, the GBA-style loop).
* **decks** — ids (paths under ``deck_blueprints/``) of the decks you've built,
  plus the bundled Starter Deck you begin with.
* **stats** — win/loss/duel tallies, packs opened.

A brand-new profile is seeded with the **Starter Deck: Yugi** cards and a small
DP stake, so you can duel immediately and afford a pack or two.

Stored as JSON at ``$YGO_PROFILE_DIR/profile.json`` (default ``REPO_ROOT/profile/``,
gitignored). Single-profile for now; the path helper leaves room for more later.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .paths import DECKS_DIR, REPO_ROOT

# The classic LOB-era starter deck the player begins with — also "your deck"
# until you build your own. Id is its path under deck_blueprints/.
STARTER_DECK_ID = "ygored/Starter-Deck-Yugi.txt"

STARTING_DP = 2000  # enough for a couple of packs out of the gate
WIN_DP = 200  # awarded for winning a duel
LOSS_DP = 50  # consolation so a losing streak isn't a dead end


def profile_dir() -> Path:
    """Where the save file lives (override with ``$YGO_PROFILE_DIR``)."""
    return Path(os.environ.get("YGO_PROFILE_DIR", REPO_ROOT / "profile"))


def profile_path() -> Path:
    return profile_dir() / "profile.json"


def _parse_decklist_counts(path: Path) -> dict[str, int]:
    """``{card_name: count}`` from a blueprint, ignoring comments/section headers.

    Handles both blueprint dialects (``Main``/``Extra`` headers and ``//`` /
    ``#EXTRA DECK`` comments) without needing the card registry.
    """
    counts: Counter[str] = Counter()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        m = re.match(r"^(\d+)\s*x?\s+(.+)$", line)
        if m:
            counts[m.group(2).strip()] += int(m.group(1))
        # bare lines like "Main"/"Extra"/"Side" have no count -> skipped
    return dict(counts)


def starter_collection() -> dict[str, int]:
    """The cards a new player owns: exactly the Starter Deck Yugi contents."""
    return _parse_decklist_counts(DECKS_DIR / STARTER_DECK_ID)


@dataclass
class Profile:
    """A player's save state."""

    name: str = "Duelist"
    duelist_points: int = STARTING_DP
    collection: dict[str, int] = field(default_factory=dict)
    decks: list[str] = field(default_factory=list)  # user-built deck ids
    active_deck: str = STARTER_DECK_ID
    stats: dict[str, int] = field(default_factory=lambda: {"wins": 0, "losses": 0, "duels": 0})
    packs_opened: int = 0
    tournament: dict | None = None  # active tournament run (see tournament.py), or None

    # -- collection helpers ------------------------------------------------- #
    def owns(self, card_name: str, count: int = 1) -> bool:
        return self.collection.get(card_name, 0) >= count

    def add_cards(self, cards: dict[str, int] | Counter) -> None:
        for name, n in cards.items():
            if n:
                self.collection[name] = self.collection.get(name, 0) + int(n)

    def remove_cards(self, cards: dict[str, int] | Counter) -> None:
        """Remove cards from the collection (e.g. when sold), pruning entries
        that hit zero. Raises ValueError if you don't own enough of any card —
        checked up front so the collection is never left half-mutated."""
        for name, n in cards.items():
            have = self.collection.get(name, 0)
            if int(n) > have:
                raise ValueError(f"Don't own {n}x {name} (have {have})")
        for name, n in cards.items():
            if int(n) <= 0:
                continue
            remaining = self.collection.get(name, 0) - int(n)
            if remaining > 0:
                self.collection[name] = remaining
            else:
                self.collection.pop(name, None)

    def total_cards(self) -> int:
        return sum(self.collection.values())

    def deck_ids(self) -> list[str]:
        """Decks you can play with: the Starter Deck plus everything you built."""
        ids = [STARTER_DECK_ID, *self.decks]
        seen: set[str] = set()
        return [d for d in ids if not (d in seen or seen.add(d))]

    def missing_for_deck(self, deck_counts: dict[str, int]) -> dict[str, int]:
        """How many copies of each card the deck needs beyond what you own.

        Empty dict == the deck is fully buildable from your collection.
        """
        short: dict[str, int] = {}
        for name, need in deck_counts.items():
            have = self.collection.get(name, 0)
            if need > have:
                short[name] = need - have
        return short

    # -- DP helpers --------------------------------------------------------- #
    def can_afford(self, cost: int) -> bool:
        return self.duelist_points >= cost

    def spend(self, cost: int) -> None:
        if cost > self.duelist_points:
            raise ValueError(f"Not enough DP: need {cost}, have {self.duelist_points}")
        self.duelist_points -= cost

    def earn(self, amount: int) -> None:
        self.duelist_points += max(0, int(amount))

    def record_result(self, won: bool) -> int:
        """Tally a duel and award DP. Returns the DP earned."""
        self.stats["duels"] = self.stats.get("duels", 0) + 1
        if won:
            self.stats["wins"] = self.stats.get("wins", 0) + 1
            reward = WIN_DP
        else:
            self.stats["losses"] = self.stats.get("losses", 0) + 1
            reward = LOSS_DP
        self.earn(reward)
        return reward

    # -- serialise ---------------------------------------------------------- #
    def to_json_obj(self) -> dict:
        return {
            "name": self.name,
            "duelist_points": self.duelist_points,
            "collection": self.collection,
            "decks": self.decks,
            "active_deck": self.active_deck,
            "stats": self.stats,
            "packs_opened": self.packs_opened,
            "tournament": self.tournament,
        }

    @classmethod
    def from_json_obj(cls, obj: dict) -> "Profile":
        return cls(
            name=obj.get("name", "Duelist"),
            duelist_points=int(obj.get("duelist_points", STARTING_DP)),
            collection=dict(obj.get("collection", {})),
            decks=list(obj.get("decks", [])),
            active_deck=obj.get("active_deck", STARTER_DECK_ID),
            stats=dict(obj.get("stats", {"wins": 0, "losses": 0, "duels": 0})),
            packs_opened=int(obj.get("packs_opened", 0)),
            tournament=obj.get("tournament"),
        )


def new_profile() -> Profile:
    """A fresh save: Starter Deck cards owned, a DP stake, no built decks."""
    return Profile(
        duelist_points=STARTING_DP,
        collection=starter_collection(),
        decks=[],
        active_deck=STARTER_DECK_ID,
    )


def load_profile() -> Profile:
    """Load the save, creating (and persisting) a fresh one if none exists."""
    path = profile_path()
    if path.is_file():
        return Profile.from_json_obj(json.loads(path.read_text(encoding="utf-8")))
    profile = new_profile()
    save_profile(profile)
    return profile


def save_profile(profile: Profile) -> Path:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_json_obj(), indent=2), encoding="utf-8")
    return path
