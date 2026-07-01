"""Forbidden/Limited lists: the model, the file IO, and the catalogue.

A :class:`BanList` maps a card name to how many copies a format allows (0..3);
any card it doesn't name defaults to :data:`MAX_COPIES`. Lists come from JSON
under ``assets/banlists`` — bundled presets at the top level, the player's own
custom lists under ``user/`` (gitignored) — addressed by an *id* that is the
path under that directory without the ``.json`` suffix (``"none"``,
``"ocg_2008_03"``, ``"user/my_list"``).

This lives in its own module (rather than inside :mod:`ygo.deckbuild`) so the
pricing layer can depend on the banlist without pulling in the whole
deck-construction module — keeping the import graph a clean DAG.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .cards import CardRegistry

# At most 3 of any one card by name — the default cap for an unlisted card.
MAX_COPIES = 3

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
    # Imported lazily so tests can monkeypatch ``paths.BANLISTS_DIR`` and have it
    # take effect here (a top-level import would capture the value once).
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
