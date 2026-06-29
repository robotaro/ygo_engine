"""Smoke fuzz: a handful of seeded RandomAgent self-play games must run without raising.

The full driver and the authored-card deck live in ``scripts/fuzz_selfplay.py``; this runs
a small, fast slice of it on every pytest run so random long-game play stays exercised in
CI. Run the deep version manually for more games:

    uv run python scripts/fuzz_selfplay.py 200
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ isn't a package on the path; add it so the canonical fuzzer can be imported.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fuzz_selfplay  # noqa: E402


@pytest.mark.parametrize("seed", range(10))
def test_random_selfplay_does_not_crash(seed):
    """Each seeded game plays to completion without the engine raising."""
    fuzz_selfplay.play_game(seed)
