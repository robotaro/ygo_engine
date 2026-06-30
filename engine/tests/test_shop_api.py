"""The single-card shop API: buy specific cards, sell duplicates, price fields."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from ygo.server import app as srv  # noqa: E402


@pytest.fixture
def iso(tmp_path, monkeypatch):
    """Isolate the save file so tests never touch the real profile."""
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    return tmp_path


def test_cards_endpoint_has_prices(iso):
    data = srv.cards(query="Battle Ox")
    ox = next(c for c in data["cards"] if c["name"] == "Battle Ox")
    assert ox["buy"] == ox["value"] > 0
    assert 0 < ox["sell"] < ox["buy"]
    assert ox["rarity"] in {"Common", "Rare", "Super Rare", "Ultra Rare", "Secret Rare"}
    assert ox["buy"] % 50 == 0 and ox["sell"] % 50 == 0
    assert "inPacks" in ox  # where to grind it (may be empty for orphans)


def test_pack_covered_card_lists_its_packs():
    """A card in packs reports them, and can't be bought as a single."""
    idx = srv._pack_index()
    covered = next(name for name, packs in idx.items() if packs)
    data = srv.cards(query=covered)
    hit = next((c for c in data["cards"] if c["name"] == covered), None)
    assert hit and len(hit["inPacks"]) >= 1
    assert all({"id", "name", "rarity"} <= set(p) for p in hit["inPacks"])


def test_cannot_buy_a_pack_covered_card(iso):
    idx = srv._pack_index()
    covered = next(name for name, packs in idx.items() if packs)
    with pytest.raises(HTTPException) as e:
        srv.shop_buy({"name": covered})
    assert e.value.status_code == 400 and "pack" in e.value.detail.lower()


def test_orphan_card_is_buyable(iso):
    idx = srv._pack_index()
    orphan = next(c.name for c in srv.REGISTRY if c.name not in idx)
    before = srv.get_profile()["duelistPoints"]
    res = srv.shop_buy({"name": orphan})
    assert res["spent"] == res["card"]["buy"]
    assert res["duelistPoints"] == before - res["spent"]


def test_pack_detail_lists_contents():
    pack = srv._all_packs()[0]
    d = srv.pack_detail(pack.id)
    assert d["name"] and d["price"] % 50 == 0
    assert d["groups"] and all(g["rarity"] and g["cards"] for g in d["groups"])
    flat = [c for g in d["groups"] for c in g["cards"]]
    assert len(flat) == pack.distinct


def _orphan_name():
    """A card in no pack — the only kind buyable as a single."""
    idx = srv._pack_index()
    return next(c.name for c in srv.REGISTRY if c.name not in idx)


def test_buy_card_spends_dp_and_grants_card(iso):
    orphan = _orphan_name()
    before = srv.get_profile()["duelistPoints"]
    res = srv.shop_buy({"name": orphan, "qty": 2})
    assert res["qty"] == 2
    assert res["spent"] == res["card"]["buy"] * 2
    assert res["duelistPoints"] == before - res["spent"]
    assert res["owned"] >= 2
    # persisted
    assert srv.collection(query=orphan)["cards"][0]["owned"] >= 2


def test_buy_rejects_when_too_poor(iso):
    orphan = _orphan_name()
    with pytest.raises(HTTPException) as e:
        srv.shop_buy({"name": orphan, "qty": 9999})  # cost far exceeds starting DP
    assert e.value.status_code == 400


def test_sell_card_earns_dp_and_removes_it(iso):
    # A starter card we definitely own.
    coll = srv.collection()["cards"]
    owned_card = next(c for c in coll if c["owned"] >= 1)
    name = owned_card["name"]
    before_dp = srv.get_profile()["duelistPoints"]
    before_owned = owned_card["owned"]
    res = srv.shop_sell({"name": name, "qty": 1})
    assert res["earned"] == res["card"]["sell"]
    assert res["duelistPoints"] == before_dp + res["earned"]
    assert res["owned"] == before_owned - 1


def test_sell_rejects_when_not_owned(iso):
    with pytest.raises(HTTPException) as e:
        srv.shop_sell({"name": "Pot of Greed", "qty": 1})  # not in the starter deck
    assert e.value.status_code == 400


def test_buy_then_sell_loses_the_spread(iso):
    """Round-tripping a card through the shop costs DP (sell < buy), so it's not
    a free store of value."""
    orphan = _orphan_name()
    start = srv.get_profile()["duelistPoints"]
    srv.shop_buy({"name": orphan, "qty": 1})
    srv.shop_sell({"name": orphan, "qty": 1})
    assert srv.get_profile()["duelistPoints"] < start


def test_unknown_card_is_404(iso):
    with pytest.raises(HTTPException) as e:
        srv.shop_buy({"name": "Not A Real Card"})
    assert e.value.status_code == 404
