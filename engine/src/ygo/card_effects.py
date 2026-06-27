"""Per-card effect definitions, keyed by card name.

This is the content layer: each entry encodes a card's *current ruling* as data,
composed from the primitive verbs in ``effects.py``. The card pool CSV provides
the roster and flavour text; the actual rules behaviour lives here.

Grows card-by-card. Vanilla monsters never appear (they have no effects).
"""

from __future__ import annotations

from .effects import OPPONENT, DestroyAllMonsters, Draw, Effect

EFFECTS: dict[str, tuple[Effect, ...]] = {
    # --- Slice 1: Ignition Normal Spells, no cost, no targets ---
    "Pot of Greed": (Effect(resolve=(Draw(count=2),)),),
    "Dark Hole": (Effect(resolve=(DestroyAllMonsters(),)),),
    "Raigeki": (Effect(resolve=(DestroyAllMonsters(side=OPPONENT),)),),
}
