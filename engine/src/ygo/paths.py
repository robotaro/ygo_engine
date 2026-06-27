"""Filesystem locations for bundled game assets.

The card database, deck blueprints, card images, and rulebook live in the
repo's top-level ``assets/`` directory, two levels above this package.
"""

from __future__ import annotations

from pathlib import Path

# repo/engine/src/ygo/paths.py -> parents[3] == repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

ASSETS = REPO_ROOT / "assets"
CARD_DB_DIR = ASSETS / "card_databases"
DECKS_DIR = ASSETS / "deck_blueprints"
MANUAL_DIR = ASSETS / "manual"

# The v6.0 "Stairway to the Destined Duel" worldwide-edition card pool.
DEFAULT_CARD_DB = CARD_DB_DIR / "card_db_worldwide_edition_stariway_to_the_destined_duel.csv"
