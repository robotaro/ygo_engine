"""Random self-play fuzzer for the engine.

Runs N seeded ``RandomAgent``-vs-``RandomAgent`` games on a deck stuffed with the cards
whose effects the campaign has authored — heavy on the interacting mechanisms (Special
Summon / negation / attack-reaction / stat-anthem cards) so random play collides them —
and asserts only that no game raises. It complements the deterministic unit tests in
``tests/``: long, randomised game states catch crashes the per-card tests don't (it first
surfaced a latent Token-tribute ``KeyError`` that only a Token tributed mid-game hits).

  uv run python scripts/fuzz_selfplay.py            # default game count
  uv run python scripts/fuzz_selfplay.py 200        # 200 games

Importable, too: ``tests/test_fuzz_smoke.py`` runs a small slice of these games on every
pytest run via ``play_game`` / ``play_games`` below.
"""

from __future__ import annotations

import sys
import traceback

from ygo.agents import RandomAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Zone
from ygo.state import GameState

_REGISTRY = CardRegistry.load_csv()

# A duel deck spanning the authored-effects campaign — both players run it, so the
# mechanisms (locks, class/monster negation, the attack-reaction Traps, the stat anthems)
# routinely meet on the same board. Grouped by the batch that added the cards.
DECK = (
    ["Decoyroid"] * 3
    + ["Marauding Captain"] * 3
    + ["Queen's Bodyguard"] * 2
    + ["Allure Queen LV3"] * 2
    + ["Marshmallon"] * 2
    + ["Marshmallon Glasses"] * 2
    + ["Celtic Guardian"] * 3
    + ["Summoned Skull"] * 3
    + ["Mystical Elf"] * 3
    + ["La Jinn the Mystical Genie of the Lamp"] * 3
    + ["Gemini Elf"] * 3
    + ["Hayabusa Knight"] * 2
    + ["Mad Sword Beast"] * 2
    + ["Smashing Ground"] * 2
    + ["Fissure"] * 2
    + ["Pot of Greed"] * 2
    # Special Summon locks + the SS routes they gate
    + ["Vanity's Fiend"] * 2
    + ["Vanity's Ruler"] * 2
    + ["Barrier Statue of the Inferno"] * 2
    + ["Barrier Statue of the Torrent"] * 2
    + ["Mystic Tomato"] * 2
    + ["UFO Turtle"] * 2
    + ["Mother Grizzly"] * 2
    + ["Monster Reborn"] * 2
    + ["Scapegoat"] * 2
    + ["Cyber Dragon"] * 2
    # response cards that fire on effect-driven Special Summons (window stress)
    + ["Bottomless Trap Hole"] * 2
    + ["Black Horn of Heaven"] * 2
    + ["Torrential Tribute"] * 2
    # class negators + the Spell/Trap/Field they negate
    + ["Jinzo"] * 2
    + ["Spell Canceller"] * 2
    + ["Royal Decree"] * 2
    + ["Imperial Order"] * 2
    + ["Just Desserts"] * 2
    + ["Ookazi"] * 2
    + ["Sogen"] * 2
    + ["Trap Hole"] * 2
    # Skill Drain + monsters whose effects/riders it negates
    + ["Skill Drain"] * 2
    + ["Chaos Necromancer"] * 2
    + ["Airknight Parshath"] * 2
    + ["Gravekeeper's Curse"] * 2
    + ["Man-Eater Bug"] * 2
    # "destroy all Special Summoned monsters" floodgates + was-SS flag
    + ["Fossil Dyna Pachycephalo"] * 2
    + ["Jowgen the Spiritualist"] * 2
    + ["Special Hurricane"] * 2
    + ["Dandylion"] * 2
    # reactive attack-declaration Traps
    + ["Sakuretsu Armor"] * 2
    + ["Negate Attack"] * 2
    + ["Malevolent Catastrophe"] * 2
    + ["Widespread Ruin"] * 2
    + ["Radiant Mirror Force"] * 2
    + ["Dark Mirror Force"] * 2
    # battle-position change
    + ["Block Attack"] * 2
    + ["Book of Moon"] * 2
    + ["Earthquake"] * 2
    + ["No Entry!!"] * 2
    + ["Zero Gravity"] * 2
    + ["Windstorm of Etaqua"] * 2
    + ["Kunai with Chain"] * 2
    + ["Big Shield Gardna"] * 2
    # coin-flip
    + ["Jirai Gumo"] * 2
    + ["Abare Ushioni"] * 2
    + ["Cup of Ace"] * 2
    + ["Barrel Dragon"] * 2
    + ["Blowback Dragon"] * 2
    # attack redirect + cost-bearing attack Trap
    + ["Call of the Earthbound"] * 2
    + ["Jam Defender"] * 2
    + ["Revival Jam"] * 2
    + ["Chaos Burst"] * 2
    # take-control-the-attack + battle-damage reflection
    + ["Magical Arm Shield"] * 2
    + ["Dimension Wall"] * 2
    # "selected as attack target" gate + board-state attack Traps
    + ["Mirage Tube"] * 2
    + ["Froggy Forcefield"] * 2
    + ["Des Frog"] * 2
    + ["Justi-Break"] * 2
    + ["Supercharge"] * 2
    + ["Cycroid"] * 2
    + ["Amazoness Archers"] * 2
    + ["Amazoness Swords Woman"] * 2
    # forced attack target
    + ["Staunch Defender"] * 2
    # Special Summon from hand on an attack
    + ["A Hero Emerges"] * 2
    + ["Relieve Monster"] * 2
    # was-Tribute-Summoned gate
    + ["Blast Held by a Tribute"] * 2
    # monster on-attack-declare (Necrovalley-gated)
    + ["Gravekeeper's Assailant"] * 2
    + ["Necrovalley"] * 2
    # continuous ATK scaling by your own monsters
    + ["Amazoness Paladin"] * 2
    + ["Amazoness Tiger"] * 2
    + ["Botanical Lion"] * 2
    + ["Lava Battleguard"] * 2
    + ["Swamp Battleguard"] * 2
    # monster-borne attribute anthems
    + ["Bladefly"] * 2
    + ["Milus Radiant"] * 2
    + ["Star Boy"] * 2
    + ["Witch's Apprentice"] * 2
    + ["Luster Dragon"] * 2
    # conditional flat self-ATK
    + ["Boot-Up Soldier - Dread Dynamo"] * 2
    + ["Green Gadget"] * 2
    + ["Cybernetic Cyclopean"] * 2
    + ["Theban Nightmare"] * 2
    # Damage-Step combat pumps
    + ["Cipher Soldier"] * 2
    + ["Etoile Cyber"] * 2
    + ["Insect Soldiers of the Sky"] * 2
    + ["Penumbral Soldier Lady"] * 2
    + ["Steamroid"] * 2
    + ["Black Veloci"] * 2
    # archetype/race anthems + self-shield lords
    + ["Command Knight"] * 2
    + ["Freya, Spirit of Victory"] * 2
    + ["Shining Angel"] * 2
    + ["Hunter Owl"] * 2
    + ["Nightmare Penguin"] * 2
    + ["Mother Grizzly"] * 2
    # more attribute anthems + a position-gated anthem
    + ["Harpie Lady 1"] * 2
    + ["Hoshiningen"] * 2
    + ["Little Chimera"] * 2
    + ["Fairy King Truesdale"] * 2
)


def build_state(seed: int) -> GameState:
    """A fresh duel: both players shuffle ``DECK`` (seeded) and draw 5."""
    state = GameState.new(("A", "B"), seed=seed)
    for owner in (0, 1):
        for name in DECK:
            inst = state.create_instance(_REGISTRY.get(name), owner=owner, zone=Zone.DECK)
            state.players[owner].deck.append(inst.iid)
        state.shuffle_deck(owner)
        state.draw(owner, 5)
    return state


def play_game(seed: int, max_turns: int = 120) -> None:
    """Play one seeded RandomAgent-vs-RandomAgent game to completion. Raises if the
    engine raises — that's the property the fuzzer (and the smoke test) checks."""
    state = build_state(seed)
    agents = [RandomAgent(seed=seed), RandomAgent(seed=seed + 1000)]
    Engine(state, agents, max_turns=max_turns).run()


def play_games(n: int, *, start: int = 0, verbose: bool = False) -> int:
    """Play games with seeds ``[start, start + n)``; return the number that crashed
    (printing each traceback when ``verbose``)."""
    fails = 0
    for seed in range(start, start + n):
        try:
            play_game(seed)
        except Exception:
            fails += 1
            if verbose:
                print(f"--- game seed={seed} CRASHED ---")
                traceback.print_exc()
    return fails


def main(argv: list[str]) -> int:
    n = int(argv[1]) if len(argv) > 1 else 80
    fails = play_games(n, verbose=True)
    print(f"\n{n - fails}/{n} games clean" if not fails else f"\n{fails}/{n} games CRASHED")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
