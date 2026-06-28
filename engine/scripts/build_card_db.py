"""Convert the YGOPRODeck card data into the engine's CSV card pool.

Source: a saved JSON blob (``--source FILE``) or a live download (``--download``).
Output: a CSV that ``ygo.cards.CardRegistry.load_csv`` reads directly, plus an
additive merge into ``card_image_ids.json`` (the name -> art-id map the engine
loads). Re-runnable; existing image-id entries for other pools are preserved.

Run:  uv run python scripts/build_card_db.py            # uses the saved v6.0 blob
      uv run python scripts/build_card_db.py --download  # fresh OCG pre-Synchro pull

The engine's CSV `Type` column folds a monster's race and categories together
(e.g. ``Spellcaster / Fusion / Effect``); Spells use the v6.0 word "Magic" and
carry their icon in the `Property` column. The engine has no Flip/Spirit/Union/
Gemini/Toon categories, so those all collapse to a plain `Effect` monster here —
their special behaviour is authored later in card_effects.py (see the TODO in
src/ygo/MONSTER_SUBTYPES_TODO.md).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ygo.paths import CARD_DB_DIR
from ygo.ygoprodeck import load_cards

DEFAULT_SOURCE = CARD_DB_DIR / "card_db_ocg_pre_synchro_v6.json"
DEFAULT_OUT = CARD_DB_DIR / "card_db_ocg_pre_synchro_v6.csv"
IMAGE_MAP = CARD_DB_DIR / "card_image_ids.json"

FIELDNAMES = [
    "Name", "Attribute", "Type", "Level", "Attack", "Defense",
    "Description", "Property", "Status", "Limitation text",
]

# YGOPRODeck `type` -> the engine category tokens appended after the race.
# (Vanilla monsters get no token; the parser defaults them to NORMAL.)
TYPE_CATEGORIES: dict[str, str] = {
    "Normal Monster": "",
    "Effect Monster": "Effect",
    "Flip Effect Monster": "Effect",
    "Gemini Monster": "Effect",
    "Union Effect Monster": "Effect",
    "Spirit Monster": "Effect",
    "Toon Monster": "Effect",
    "Ritual Monster": "Ritual",
    "Ritual Effect Monster": "Ritual / Effect",
    "Token": "Token",
    # "Fusion Monster" is resolved separately (vanilla vs. effect, see below).
}


def _num(value) -> str:
    """Render an ATK/DEF/Level cell; '?' (-1) and missing values become blank."""
    if value is None:
        return ""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    return "" if n < 0 else str(n)


def _type_column(card: dict) -> str:
    """Build the engine's `Type` cell from a YGOPRODeck monster card."""
    race = card.get("race", "")
    ygo_type = card["type"]
    if ygo_type == "Fusion Monster":
        # YGOPRODeck folds vanilla and effect fusions into one `type`; the
        # human-readable string is what distinguishes them.
        cats = "Fusion / Effect" if "Effect" in card.get("humanReadableCardType", "") else "Fusion"
    else:
        cats = TYPE_CATEGORIES.get(ygo_type, "Effect")
    return f"{race} / {cats}" if cats else race


def to_row(card: dict) -> dict[str, str]:
    """Map one YGOPRODeck card to an engine CSV row."""
    ygo_type = card["type"]
    text = card.get("desc", "")

    if ygo_type == "Spell Card":
        return {
            "Name": card["name"], "Type": "Magic", "Description": text,
            "Property": card.get("race", "Normal"),
            "Attribute": "", "Level": "", "Attack": "", "Defense": "",
            "Status": "", "Limitation text": "",
        }
    if ygo_type == "Trap Card":
        return {
            "Name": card["name"], "Type": "Trap", "Description": text,
            "Property": card.get("race", "Normal"),
            "Attribute": "", "Level": "", "Attack": "", "Defense": "",
            "Status": "", "Limitation text": "",
        }

    return {
        "Name": card["name"],
        "Attribute": card.get("attribute", ""),
        "Type": _type_column(card),
        "Level": _num(card.get("level")),
        "Attack": _num(card.get("atk")),
        "Defense": _num(card.get("def")),
        "Description": text,
        "Property": "",
        "Status": "",
        "Limitation text": "",
    }


def write_csv(cards: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [to_row(c) for c in cards]
    rows.sort(key=lambda r: r["Name"].lower())
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} cards -> {out}")


def merge_image_map(cards: list[dict]) -> None:
    """Add this pool's name -> art-id entries, keeping any already present."""
    mapping: dict[str, int] = {}
    if IMAGE_MAP.exists():
        mapping.update(json.loads(IMAGE_MAP.read_text()))
    added = 0
    for c in cards:
        images = c.get("card_images") or []
        if not images:
            continue
        if c["name"] not in mapping:
            added += 1
        mapping[c["name"]] = images[0]["id"]
    IMAGE_MAP.write_text(json.dumps(mapping, indent=0, sort_keys=True))
    print(f"image map: +{added} new names ({len(mapping)} total) -> {IMAGE_MAP}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, help="YGOPRODeck JSON blob to convert")
    ap.add_argument("--download", action="store_true", help="fetch a fresh pool from the API")
    ap.add_argument("--enddate", help="override the API enddate (YYYY-MM-DD)")
    ap.add_argument("--dateregion", choices=("tcg", "ocg"), help="override the API date region")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output CSV path")
    args = ap.parse_args()

    overrides = {k: v for k, v in (("enddate", args.enddate), ("dateregion", args.dateregion)) if v}
    if args.download:
        source = None
    elif args.source:
        source = args.source
    elif DEFAULT_SOURCE.exists():
        source = DEFAULT_SOURCE
    else:
        source = None
    print(f"source: {'API download' if source is None else source}")

    cards = load_cards(source, **overrides)
    print(f"loaded {len(cards)} cards")
    write_csv(cards, args.out)
    merge_image_map(cards)


if __name__ == "__main__":
    main()
