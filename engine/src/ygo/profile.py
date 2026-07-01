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
import shutil
import tempfile
import threading
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import DECKS_DIR, REPO_ROOT

# The classic LOB-era starter deck the player begins with — also "your deck"
# until you build your own. Id is its path under deck_blueprints/.
STARTER_DECK_ID = "ygored/Starter-Deck-Yugi.txt"

STARTING_DP = 2000  # enough for a couple of packs out of the gate
WIN_DP = 200  # awarded for winning a duel
LOSS_DP = 50  # consolation so a losing streak isn't a dead end

# Every read-modify-write of the save file goes through this lock (see
# ``profile_transaction``) so two concurrent mutations — a duel result landing
# while a purchase is in flight — can't lose an update. Reentrant so a
# transaction can call ``save_profile`` (which also takes the lock) without
# deadlocking.
_LOCK = threading.RLock()


def profile_dir() -> Path:
    """Where the save file lives (override with ``$YGO_PROFILE_DIR``)."""
    return Path(os.environ.get("YGO_PROFILE_DIR", REPO_ROOT / "profile"))


def profile_path() -> Path:
    return profile_dir() / "profile.json"


def starter_collection() -> dict[str, int]:
    """The cards a new player owns: exactly the Starter Deck Yugi contents.

    Reuses the shared blueprint parser (:func:`ygo.decks.parse_blueprint`) rather
    than a private reimplementation, so both understand the same file syntax.
    """
    from .decks import parse_blueprint

    counts: Counter[str] = Counter()
    for _section, count, name in parse_blueprint(DECKS_DIR / STARTER_DECK_ID):
        counts[name] += count
    return dict(counts)


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
    # A FIFO queue of unclaimed win rewards (e.g. ``{"game": ...}``). A queue, not a
    # single slot, so a second win before the first reward is claimed isn't lost.
    pending_rewards: list[dict] = field(default_factory=list)

    # -- reward queue helpers ----------------------------------------------- #
    def add_reward(self, reward: dict) -> None:
        self.pending_rewards.append(reward)

    def next_reward(self) -> dict | None:
        """Peek at the oldest unclaimed reward (the one a claim will resolve)."""
        return self.pending_rewards[0] if self.pending_rewards else None

    def claim_next_reward(self) -> dict | None:
        """Pop and return the oldest unclaimed reward, or None if the queue is empty."""
        return self.pending_rewards.pop(0) if self.pending_rewards else None

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

    def record_result(self, won: bool, *, dp: int | None = None) -> int:
        """Tally a duel and award DP. Returns the DP awarded.

        ``dp`` overrides the default win/loss amount — pass ``dp=0`` to skip the
        award (e.g. when a win grants a booster-pack pick instead of DP).
        """
        self.stats["duels"] = self.stats.get("duels", 0) + 1
        if won:
            self.stats["wins"] = self.stats.get("wins", 0) + 1
            reward = WIN_DP if dp is None else dp
        else:
            self.stats["losses"] = self.stats.get("losses", 0) + 1
            reward = LOSS_DP if dp is None else dp
        self.earn(reward)
        return reward

    # -- serialise ---------------------------------------------------------- #
    def to_json_obj(self) -> dict:
        """The JSON-serialisable form (a plain ``dataclasses.asdict``)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: dict) -> "Profile":
        """Rebuild a Profile from stored JSON, validating and repairing as we go.

        A save file is user-writable and can be truncated/corrupted, so we never
        trust it blindly: DP is clamped to a non-negative int, collection counts
        to positive ints, and the legacy single-slot ``pending_reward`` is
        migrated to the ``pending_rewards`` queue. Structurally-broken input
        (not even a JSON object) raises rather than silently yielding garbage.
        """
        if not isinstance(obj, dict):
            raise ValueError("profile save is not a JSON object")

        def _nonneg_int(value, default: int = 0) -> int:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return default

        collection: dict[str, int] = {}
        for name, count in (obj.get("collection") or {}).items():
            n = _nonneg_int(count, 0)
            if n > 0 and isinstance(name, str):
                collection[name] = n

        stats_raw = obj.get("stats")
        stats = (
            {str(k): _nonneg_int(v, 0) for k, v in stats_raw.items()}
            if isinstance(stats_raw, dict)
            else {}
        )
        for key in ("wins", "losses", "duels"):
            stats.setdefault(key, 0)

        decks = [d for d in (obj.get("decks") or []) if isinstance(d, str)]

        # A queue of unclaimed rewards; migrate the legacy single ``pending_reward``.
        rewards = obj.get("pending_rewards")
        if rewards is None:
            legacy = obj.get("pending_reward")
            rewards = [legacy] if isinstance(legacy, dict) else []
        rewards = [r for r in rewards if isinstance(r, dict)]

        tournament = obj.get("tournament")
        if not isinstance(tournament, dict):
            tournament = None

        return cls(
            name=str(obj.get("name", "Duelist")),
            duelist_points=_nonneg_int(obj.get("duelist_points", STARTING_DP), STARTING_DP),
            collection=collection,
            decks=decks,
            active_deck=str(obj.get("active_deck", STARTER_DECK_ID)),
            stats=stats,
            packs_opened=_nonneg_int(obj.get("packs_opened", 0), 0),
            tournament=tournament,
            pending_rewards=rewards,
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
    """Load the save, or return a fresh (in-memory) one if none exists.

    Pure read: it never writes to disk (a fresh profile is persisted only on the
    first explicit create/mutation). A corrupt/truncated file is moved aside to a
    timestamped ``.corrupt`` backup and recovered from the last-good ``.bak`` (or
    a fresh profile) rather than bricking the save.
    """
    path = profile_path()
    if not path.is_file():
        return new_profile()
    try:
        return Profile.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError):
        return _recover_corrupt_profile(path)


def _recover_corrupt_profile(path: Path) -> Profile:
    """Quarantine an unreadable save and fall back to the last-good copy / fresh."""
    stamp = time.strftime("%Y%m%dT%H%M%S")
    try:
        path.replace(path.with_name(f"{path.name}.corrupt.{stamp}"))
    except OSError:
        pass
    bak = path.with_name(f"{path.name}.bak")
    if bak.is_file():
        try:
            profile = Profile.from_dict(json.loads(bak.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError):
            profile = None
        if profile is not None:
            save_profile(profile)  # reinstate the recovered save as the live file
            return profile
    return new_profile()


def save_profile(profile: Profile) -> Path:
    """Persist the profile atomically (never a torn write).

    Writes to a temp file in the same directory, ``flush`` + ``fsync``, then
    ``os.replace`` onto profile.json — so a crash mid-write leaves either the old
    file or the new one intact, never a half-written one. The previous good copy
    is kept as ``profile.json.bak`` for corruption recovery.
    """
    path = profile_path()
    data = json.dumps(asdict(profile), indent=2)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".profile.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            # Keep a last-good copy for corruption recovery. Copy (not move) so
            # profile.json is never momentarily absent for a concurrent reader.
            if path.is_file():
                try:
                    shutil.copy2(path, path.with_name(f"{path.name}.bak"))
                except OSError:
                    pass
            os.replace(tmp_name, path)  # atomic swap: readers see old or new, never torn
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    return path


@contextmanager
def profile_transaction():
    """Atomic read-modify-write of the save file.

    ``with profile_transaction() as p:`` loads the profile, hands it to the body
    to mutate, then saves it — all inside the module lock, so overlapping
    mutations serialise instead of clobbering each other. If the body raises
    (e.g. an HTTP 400 for an unaffordable purchase, before any mutation) the save
    is skipped, leaving the file untouched.
    """
    with _LOCK:
        profile = load_profile()
        yield profile
        save_profile(profile)
