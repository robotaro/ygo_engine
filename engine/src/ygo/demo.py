"""Milestone 1, step 1 demo: load the card pool + two decks, deal, show the board.

Run with::

    uv run python -m ygo.demo
"""

from __future__ import annotations

from .paths import DECKS_DIR
from .render import render
from .setup import new_duel


def main() -> None:
    deck_a = DECKS_DIR / "ygoprodeck" / "kaiba_deck.txt"
    deck_b = DECKS_DIR / "ygoprodeck" / "yugi_starter_deck.txt"

    duel = new_duel(deck_a, deck_b, names=("Kaiba", "Yugi"), seed=42)

    print(render(duel.state, viewer=1, show_opponent_hand=True))

    print("\nDeck sizes:")
    for d in duel.decklists:
        print(f"  {d.name:12s} main {d.main_size:>2}  extra {d.extra_size:>2}")

    if duel.missing_report:
        print("\nCards not found in this card pool (skipped):")
        for owner, missing in duel.missing_report.items():
            uniq = sorted(set(missing))
            print(f"  {owner}: {len(missing)} cards — {', '.join(uniq)}")


if __name__ == "__main__":
    main()
