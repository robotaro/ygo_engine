"""The hybrid card-valuation model: every card gets a sensible price, rarity and
power both register, prices snap up to multiples of 50, and packs are floored at
their resale value so reselling pulls is never profitable."""

from __future__ import annotations

import pytest

from ygo import pricing
from ygo.cards import CardRegistry
from ygo.packs import list_packs

reg = CardRegistry.load_csv()


def _card(name):
    c = reg.get(name)
    assert c is not None, f"{name} not in pool"
    return c


def test_every_card_is_priced_and_positive():
    for card in reg:
        v = pricing.card_value(card, reg)
        assert v >= pricing.ROUND_TO
        assert pricing.sell_value(card, reg) >= pricing.ROUND_TO


def test_all_prices_round_up_to_50():
    for name in ("Battle Ox", "Blue-Eyes White Dragon", "Pot of Greed", "Kuriboh", "Sangan"):
        card = _card(name)
        assert pricing.card_value(card, reg) % pricing.ROUND_TO == 0
        assert pricing.sell_value(card, reg) % pricing.ROUND_TO == 0
        assert pricing.pack_price(list_packs(reg)[0], reg) % pricing.ROUND_TO == 0


def test_round_up_examples():
    # 923 -> 950, 1000 -> 1000 (round up, exact multiples stay).
    assert pricing._round_up(923) == 950
    assert pricing._round_up(1000) == 1000
    assert pricing._round_up(1) == 50


def test_sell_is_below_buy():
    for name in ("Blue-Eyes White Dragon", "Pot of Greed", "Mirror Force", "Summoned Skull"):
        card = _card(name)
        assert pricing.sell_value(card, reg) < pricing.buy_value(card, reg)


def test_rarity_orders_price():
    # A Secret-Rare bomb is worth far more than a Common vanilla beater.
    common = pricing.card_value(_card("Battle Ox"), reg)
    secret = pricing.card_value(_card("Blue-Eyes White Dragon"), reg)
    assert secret > 5 * common


def test_banlist_premium_applies():
    # Forbidden staples (×2.0) beat an equally-rare card that isn't restricted.
    pot = pricing.card_value(_card("Pot of Greed"), reg)  # Secret + Forbidden
    bews = pricing.card_value(_card("Blue-Eyes White Dragon"), reg)  # Secret, legal
    assert pot > bews


def test_power_lifts_value_among_no_pack_cards():
    # For cards with no pack printing (priced purely on power + banlist), a
    # stronger unrestricted monster is worth more than a weaker one.
    rmap = pricing.rarity_map(reg)
    ref = pricing.reference_banlist()
    no_pack = [
        c
        for c in reg
        if c.name not in rmap and c.is_monster and pricing._status_cap(c, ref) is None
    ]
    no_pack.sort(key=pricing.power_score)
    weak, strong = no_pack[0], no_pack[-1]
    assert pricing.card_value(strong, reg) > pricing.card_value(weak, reg)


def test_no_pack_cards_still_priced():
    rmap = pricing.rarity_map(reg)
    no_pack = [c for c in reg if c.name not in rmap]
    assert no_pack, "expected some pool cards to appear in no pack"
    for card in no_pack:
        assert pricing.card_value(card, reg) > 0


def test_price_detail_shape():
    detail = pricing.price_detail(_card("Dark Magician"), reg)
    assert detail["rarity"] in pricing.RARITY_NAMES.values()
    assert detail["buy"] == detail["value"]
    assert detail["sell"] < detail["buy"]


def test_no_pack_is_profitable_to_resell():
    """The arbitrage invariant: for EVERY purchasable pack, buying it and selling
    the pulls must not turn a profit (resale EV <= effective pack price)."""
    offenders = []
    for pack in list_packs(reg):
        profit = pricing.pack_resale_profit(pack, reg)
        if profit > 0:
            offenders.append((pack.name, round(profit)))
    assert not offenders, f"packs profitable to buy-and-resell: {offenders}"


def test_pack_price_never_below_source():
    for pack in list_packs(reg):
        assert pricing.pack_price(pack, reg) >= pack.price
