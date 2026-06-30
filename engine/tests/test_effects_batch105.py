"""Effects Batch 105: Cyber Harpie Lady.

Its name is always treated as "Harpie Lady", so Harpie support recognises it — modelled
as a NameTreatedAs rider read by card_matches_traits (exact and substring name checks).
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.deckbuild import is_functional
from ygo.effects import CardFilter, card_matches_traits

reg = CardRegistry.load_csv()


def test_cyber_harpie_is_functional():
    assert is_functional(reg.get("Cyber Harpie Lady"))


def test_cyber_harpie_matches_harpie_lady_by_exact_name():
    cyber = reg.get("Cyber Harpie Lady")
    # An exact-name filter for "Harpie Lady" (e.g. Cyber Shield's equip target) sees it.
    assert card_matches_traits(cyber, names=frozenset({"Harpie Lady"}))
    assert CardFilter(names=frozenset({"Harpie Lady"})).matches(cyber)


def test_cyber_harpie_matches_harpie_lady_by_substring():
    cyber = reg.get("Cyber Harpie Lady")
    assert card_matches_traits(cyber, name_contains=frozenset({"Harpie Lady"}))


def test_plain_card_keeps_its_own_name():
    fish = reg.get("7 Colored Fish")
    assert not card_matches_traits(fish, names=frozenset({"Harpie Lady"}))
    # And the real Harpie Lady still matches itself.
    assert card_matches_traits(reg.get("Harpie Lady"), names=frozenset({"Harpie Lady"}))


def test_cyber_harpie_still_matches_its_own_name():
    cyber = reg.get("Cyber Harpie Lady")
    assert card_matches_traits(cyber, names=frozenset({"Cyber Harpie Lady"}))
