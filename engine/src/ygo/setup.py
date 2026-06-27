"""Build a ready-to-play GameState from two deck blueprints.

This is the "Preparing to Duel" step from the rulebook: load both decks into the
Deck Zone, shuffle, and draw the opening hands. (Coin toss / who-goes-first and
the turn loop itself belong to the engine kernel, added next.)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cards import CardRegistry
from .decks import DeckList, load_decklist
from .enums import Zone
from .state import GameState


@dataclass
class DuelSetup:
    state: GameState
    decklists: tuple[DeckList, DeckList]

    @property
    def missing_report(self) -> dict[str, list[str]]:
        """Card names each deck referenced that aren't in the card pool."""
        return {d.name: d.missing for d in self.decklists if d.missing}


def _load_deck_into_state(state: GameState, deck: DeckList, owner: int) -> None:
    player = state.players[owner]
    for card in deck.main:
        inst = state.create_instance(card, owner=owner, zone=Zone.DECK)
        player.deck.append(inst.iid)
    for card in deck.extra:
        inst = state.create_instance(card, owner=owner, zone=Zone.EXTRA_DECK)
        player.extra_deck.append(inst.iid)


def new_duel(
    deck_a: Path | str,
    deck_b: Path | str,
    *,
    names: tuple[str, str] = ("Player 1", "Player 2"),
    seed: int = 0,
    starting_hand: int = 5,
    registry: CardRegistry | None = None,
) -> DuelSetup:
    """Create a duel: load decks, shuffle, deal opening hands."""
    registry = registry or CardRegistry.load_csv()
    state = GameState.new(names, seed=seed)

    decklists = (
        load_decklist(deck_a, registry, name=names[0]),
        load_decklist(deck_b, registry, name=names[1]),
    )
    for owner, deck in enumerate(decklists):
        _load_deck_into_state(state, deck, owner)
        state.shuffle_deck(owner)
        state.draw(owner, starting_hand)

    return DuelSetup(state=state, decklists=decklists)
