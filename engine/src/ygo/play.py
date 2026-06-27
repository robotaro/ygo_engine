"""Play a full vanilla duel between two bots and narrate it.

Run with::

    uv run python -m ygo.play            # GreedyAgent vs GreedyAgent, seed 2
    uv run python -m ygo.play 7 random   # seed 7, RandomAgent vs RandomAgent
"""

from __future__ import annotations

import sys

from .agents import GreedyAgent, RandomAgent
from .engine import Engine
from .paths import DECKS_DIR
from .render import render
from .setup import new_duel


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    seed = int(argv[0]) if argv else 2
    kind = argv[1] if len(argv) > 1 else "greedy"

    deck_a = DECKS_DIR / "vanilla" / "beatdown_alpha.txt"
    deck_b = DECKS_DIR / "vanilla" / "beatdown_beta.txt"
    duel = new_duel(deck_a, deck_b, names=("Alpha", "Beta"), seed=seed)

    make = (lambda s: RandomAgent(s)) if kind == "random" else (lambda s: GreedyAgent())
    engine = Engine(duel.state, [make(seed), make(seed + 1)], log=print)

    result = engine.run()

    print("\nFinal board:")
    print(render(duel.state, viewer=0))
    print(f"\n{result.reason}")


if __name__ == "__main__":
    main()
