"""ygo — a headless Yu-Gi-Oh! rules engine.

Design north star: the engine is a pure, deterministic ``(state, action) -> state'``
core with no UI dependency. That single property buys us save/load, replays,
seeded reproducibility, network play, and bot self-play for free.

Layers (built incrementally):
  * enums / cards / state  — the data model (the rulebook's vocabulary as types)
  * decks / setup          — turn blueprints + the card DB into a live GameState
  * render                 — a text view of the board (also the bot debug view)
  * engine / chain         — turn FSM, battle, the Chain + priority   (later)
  * effects / primitives   — the declarative card-effect layer        (later)
"""

from .enums import (
    Attribute,
    CardType,
    MonsterCategory,
    Phase,
    Position,
    SpellSpeed,
    SpellTrapProperty,
    Zone,
)

__all__ = [
    "Attribute",
    "CardType",
    "MonsterCategory",
    "Phase",
    "Position",
    "SpellSpeed",
    "SpellTrapProperty",
    "Zone",
]
