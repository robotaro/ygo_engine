"""Deck construction: validation, banlist, pool search, playability, serialisation."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.deckbuild import (
    EXTRA_MAX,
    MAIN_MIN,
    BanList,
    DeckBuilder,
    deck_playability,
    is_functional,
    search_pool,
    to_blueprint_text,
    validate_deck,
)
from ygo.decks import load_decklist
from ygo.enums import CardType

REG = CardRegistry.load_csv()

# Main-deck vanillas only: a Normal *Fusion* monster is also "vanilla" but lives
# in the Extra Deck, so exclude those here.
_VANILLA = [c.name for c in REG if c.is_vanilla and not c.goes_in_extra_deck]
_FUSION = [c.name for c in REG if c.goes_in_extra_deck]


def _legal_builder() -> DeckBuilder:
    """20 distinct vanilla monsters × 2 = a 40-card, copy-legal Main Deck."""
    b = DeckBuilder(REG, name="Legal Test Deck")
    for name in _VANILLA[:20]:
        b.add(name, 2)
    return b


# --------------------------------------------------------------------------- #
#  Validation
# --------------------------------------------------------------------------- #
def test_legal_deck_passes():
    report = _legal_builder().validate()
    assert report.is_legal, report.summary()
    assert report.main_size == 40
    assert not report.errors


def test_main_too_small():
    b = DeckBuilder(REG)
    b.add(_VANILLA[0], 3)  # only 3 cards
    report = b.validate()
    assert not report.is_legal
    assert any("minimum" in e.message for e in report.errors)


def test_copy_limit_error():
    b = _legal_builder()
    b.add(_VANILLA[0], 2)  # now 4 copies of that card
    report = b.validate()
    assert not report.is_legal
    assert any(_VANILLA[0] in e.message and "maximum" in e.message for e in report.errors)


def test_extra_deck_over_limit():
    assert len(_FUSION) >= EXTRA_MAX + 1, "pool should have >15 Fusion monsters"
    b = _legal_builder()
    for name in _FUSION[: EXTRA_MAX + 1]:
        b.add(name, 1)
    report = b.validate()
    assert report.extra_size == EXTRA_MAX + 1
    assert any("Extra Deck" in e.message for e in report.errors)


def test_banlist_limits_copies():
    banned = BanList(name="test", limits={_VANILLA[0]: 1})
    b = DeckBuilder(REG, banlist=banned)
    for name in _VANILLA[:20]:
        b.add(name, 2)  # 2 copies of a Limited card -> illegal
    report = b.validate()
    assert not report.is_legal
    assert any(_VANILLA[0] in e.message for e in report.errors)


def test_unknown_card_is_error():
    deck = _legal_builder().to_decklist()
    deck.missing.append("Totally Not A Real Card")
    report = validate_deck(deck)
    assert not report.is_legal
    assert any("Totally Not A Real Card" in e.message for e in report.errors)


# --------------------------------------------------------------------------- #
#  Pool search
# --------------------------------------------------------------------------- #
def test_search_by_type():
    spells = search_pool(REG, card_type=CardType.SPELL)
    assert spells and all(c.card_type is CardType.SPELL for c in spells)


def test_search_by_text_and_limit():
    hits = search_pool(REG, text="dragon", limit=5)
    assert 0 < len(hits) <= 5
    assert all("dragon" in (c.name + c.text).lower() for c in hits)


def test_search_functional_only():
    hits = search_pool(REG, functional_only=True, limit=50)
    assert hits and all(is_functional(c) for c in hits)


# --------------------------------------------------------------------------- #
#  Playability
# --------------------------------------------------------------------------- #
def test_vanilla_deck_fully_playable():
    play = _legal_builder().to_decklist()
    report = deck_playability(play)
    assert report.pct == 100.0
    assert not report.nonfunctional


def test_unimplemented_effect_lowers_playability():
    dead = next((c for c in REG if c.has_effect and not is_functional(c)), None)
    if dead is None:
        return  # every effect implemented — nothing to assert
    b = _legal_builder()
    b.remove(_VANILLA[0], 2)  # free up copies, stay near 40
    b.add(dead.name, 2)
    report = deck_playability(b.to_decklist())
    assert report.pct < 100.0
    assert dead.name in report.nonfunctional


# --------------------------------------------------------------------------- #
#  Serialisation round-trip
# --------------------------------------------------------------------------- #
def test_blueprint_round_trip(tmp_path):
    original = _legal_builder()
    path = tmp_path / "deck.txt"
    original.save(path)

    reloaded = load_decklist(path, REG)
    assert not reloaded.missing
    assert reloaded.main_size == original.main_size
    # same multiset of card names survives the round trip
    from collections import Counter

    assert Counter(c.name for c in reloaded.main) == original.main_counts


def test_blueprint_text_has_extra_header():
    b = _legal_builder()
    b.add(_FUSION[0], 1)
    text = to_blueprint_text(b.to_decklist())
    assert "#EXTRA DECK" in text
    assert _FUSION[0] in text


# --------------------------------------------------------------------------- #
#  Builder mechanics
# --------------------------------------------------------------------------- #
def test_builder_add_remove_and_routing():
    b = DeckBuilder(REG)
    b.add(_VANILLA[0], 3)
    assert b.main_counts[_VANILLA[0]] == 3
    b.remove(_VANILLA[0], 1)
    assert b.main_counts[_VANILLA[0]] == 2
    b.remove(_VANILLA[0], 5)  # over-remove clamps to gone
    assert _VANILLA[0] not in b.main_counts

    b.add(_FUSION[0], 1)  # a Fusion routes to the Extra Deck automatically
    assert _FUSION[0] in b.extra_counts and b.extra_size == 1


def test_builder_rejects_unknown_card():
    b = DeckBuilder(REG)
    try:
        b.add("Totally Not A Real Card")
    except KeyError:
        return
    raise AssertionError("expected KeyError for an unknown card")
