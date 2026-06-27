"""Foundation tests: card pool parsing, deck loading, dealing, determinism."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import CardType, MonsterCategory, Zone
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel

KAIBA = DECKS_DIR / "ygoprodeck" / "kaiba_deck.txt"
YUGI = DECKS_DIR / "ygoprodeck" / "yugi_starter_deck.txt"


def test_card_pool_loads():
    reg = CardRegistry.load_csv()
    assert len(reg) > 1000  # the v6.0 pool is ~1086 cards

    boew = reg.get("Blue-Eyes White Dragon")
    assert boew is not None
    assert boew.card_type is CardType.MONSTER
    assert (boew.attack, boew.defense, boew.level) == (3000, 2500, 8)
    assert boew.is_vanilla  # no effect text

    man_eater = reg.get("Man-Eater Bug")
    assert MonsterCategory.EFFECT in man_eater.categories
    assert not man_eater.is_vanilla

    dark_hole = reg.get("Dark Hole")
    assert dark_hole.card_type is CardType.SPELL


def test_deal_opening_hands():
    duel = new_duel(KAIBA, YUGI, names=("Kaiba", "Yugi"), seed=7)
    state = duel.state
    for p in (0, 1):
        assert len(state.players[p].hand) == 5
        # every dealt card knows it is in the hand
        for iid in state.players[p].hand:
            assert state.inst(iid).zone is Zone.HAND
    # all instances accounted for across deck + hand (no extra deck in these lists)
    for p in (0, 1):
        player = state.players[p]
        assert len(player.deck) + len(player.hand) == sum(
            1 for c in state.cards.values() if c.owner == p and c.zone in (Zone.DECK, Zone.HAND)
        )


def test_shuffle_is_deterministic():
    a = new_duel(KAIBA, YUGI, seed=123)
    b = new_duel(KAIBA, YUGI, seed=123)
    c = new_duel(KAIBA, YUGI, seed=999)

    def hand_names(duel, p):
        return [duel.state.inst(i).name for i in duel.state.players[p].hand]

    assert hand_names(a, 0) == hand_names(b, 0)  # same seed -> same deal
    assert hand_names(a, 0) != hand_names(c, 0)  # different seed -> different deal
