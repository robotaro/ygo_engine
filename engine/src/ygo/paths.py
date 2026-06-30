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
CARD_PACKS_DIR = ASSETS / "card_packs"
BANLISTS_DIR = ASSETS / "banlists"
MANUAL_DIR = ASSETS / "manual"

# The V6.0-legal card pool: the OCG up to the pre-Synchro cutoff (2008-03-14),
# 3,117 cards, built by scripts/build_card_db.py. (The older "Stairway to the
# Destined Duel" worldwide-edition CSV is kept alongside for reference.)
DEFAULT_CARD_DB = CARD_DB_DIR / "card_db_ocg_pre_synchro_v6.csv"
