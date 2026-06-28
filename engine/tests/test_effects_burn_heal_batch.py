"""Effects Batch 3: fixed-amount burn and healing Normal Spells."""

from __future__ import annotations

import pytest

from ygo.cards import CardRegistry
from ygo.enums import Zone
from ygo.moves import ActivateSpell, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _cast(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    apply(s, ActivateSpell(inst.iid))


@pytest.mark.parametrize("name,amount", [("Sparks", 200), ("Final Flame", 600), ("Ookazi", 800)])
def test_burn_reduces_opponent_life(name, amount):
    s = GameState.new(("A", "B"), seed=0)
    _cast(s, name, 0)
    assert s.players[1].life_points == 8000 - amount
    assert s.players[0].life_points == 8000  # no self-damage


@pytest.mark.parametrize(
    "name,amount",
    [
        ("Blue Medicine", 400),
        ("Red Medicine", 500),
        ("Goblin's Secret Remedy", 600),
        ("Soul of the Pure", 800),
        ("Dian Keto the Cure Master", 1000),
    ],
)
def test_heal_increases_own_life(name, amount):
    s = GameState.new(("A", "B"), seed=0)
    _cast(s, name, 0)
    assert s.players[0].life_points == 8000 + amount
    assert s.players[1].life_points == 8000
