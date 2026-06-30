"""Audit deck blueprints: legality, completeness, and how playable they are today.

Run with::

    uv run python -m ygo.deckcheck                 # audit every bundled blueprint
    uv run python -m ygo.deckcheck path/to/deck.txt  # detailed report for one deck

"Playable %%" is the share of a deck's cards that work right now — a vanilla
monster always counts; a card with an effect counts only once that effect is
implemented. A deck can be perfectly *legal* yet only partly *functional*.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .cards import CardRegistry
from .deckbuild import deck_playability, validate_deck
from .decks import load_decklist
from .paths import DECKS_DIR


def _report_one(path: Path, registry: CardRegistry) -> None:
    deck = load_decklist(path, registry)
    report = validate_deck(deck)
    play = deck_playability(deck)
    print(report.summary())
    print(f"    playable: {play.functional}/{play.total} cards ({play.pct:.0f}%)")
    if play.nonfunctional:
        print(f"    no effect yet ({len(play.nonfunctional)}): {', '.join(play.nonfunctional)}")


def _audit_all(registry: CardRegistry) -> None:
    paths = sorted(DECKS_DIR.rglob("*.txt"))
    rows = []
    for path in paths:
        deck = load_decklist(path, registry)
        report = validate_deck(deck)
        play = deck_playability(deck)
        rows.append((report.is_legal, play.pct, path.relative_to(DECKS_DIR), report, play))

    legal = sum(1 for r in rows if r[0])
    fully_playable = sum(1 for r in rows if r[0] and r[1] == 100.0)
    print(f"{len(rows)} blueprints — {legal} legal, {fully_playable} legal & 100% playable\n")

    # Most playable legal decks first; illegal decks sink to the bottom.
    for is_legal, pct, rel, report, play in sorted(rows, key=lambda r: (r[0], r[1]), reverse=True):
        flag = "LEGAL  " if is_legal else "ILLEGAL"
        err = "" if is_legal else f"  [{len(report.errors)} err]"
        print(f"  {flag}  play {pct:3.0f}%  main {report.main_size:>2} extra {report.extra_size:>2}  {rel}{err}")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    registry = CardRegistry.load_csv()
    args = [a for a in argv if a != "--all"]
    if args:
        _report_one(Path(args[0]), registry)
    else:
        _audit_all(registry)


if __name__ == "__main__":
    main()
