"""HTTP API for the meta-game: profile, collection, pack shop, owned-only decks."""

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


def test_profile_endpoint_fresh(iso):
    prof = srv.get_profile()
    assert prof["duelistPoints"] == 2000
    assert prof["collectionDistinct"] == 50
    # the Starter Deck shows up as an owned, playable deck
    starter = next(d for d in prof["decks"] if d["isStarter"])
    assert starter["owned"] is True
    assert starter["main"] == 50


def test_packs_endpoint_groups_and_prices(iso):
    data = srv.packs()
    assert data["duelistPoints"] == 2000
    flat = [p for g in data["games"] for p in g["packs"]]
    assert len(flat) > 50
    assert all(p["price"] > 0 and p["cardsPerPack"] > 0 for p in flat)


def test_open_pack_spends_dp_and_adds_cards(iso):
    data = srv.packs()
    cheapest = min((p for g in data["games"] for p in g["packs"]), key=lambda p: p["price"])
    before = srv.get_profile()
    res = srv.buy_pack({"packId": cheapest["id"]})
    assert res["spent"] == cheapest["price"]
    assert res["duelistPoints"] == before["duelistPoints"] - cheapest["price"]
    assert len(res["pulled"]) == min(cheapest["cardsPerPack"], cheapest["distinct"])
    after = srv.get_profile()
    assert after["collectionTotal"] == before["collectionTotal"] + len(res["pulled"])
    assert after["packsOpened"] == 1


def test_open_pack_errors(iso):
    with pytest.raises(HTTPException) as e:
        srv.buy_pack({"packId": "gba/nope/missing"})
    assert e.value.status_code == 404

    data = srv.packs()
    priciest = max((p for g in data["games"] for p in g["packs"]), key=lambda p: p["price"])
    if priciest["price"] > 2000:  # unaffordable on a fresh profile
        with pytest.raises(HTTPException) as e2:
            srv.buy_pack({"packId": priciest["id"]})
        assert e2.value.status_code == 400


def test_save_deck_is_owned_only(iso):
    # A deck of cards we don't own is rejected with the shortfall.
    with pytest.raises(HTTPException) as e:
        srv.save_deck({"name": "Dragons", "main": {"Blue-Eyes White Dragon": 3}})
    assert e.value.status_code == 400
    assert "Blue-Eyes White Dragon" in e.value.detail["missing"]

    # A deck built from owned (starter) cards saves and is tracked.
    owned = list(srv.load_profile().collection)[:40]
    res = srv.save_deck({"name": "Starter Remix", "main": {n: 1 for n in owned}})
    assert res["validation"]["legal"] is True
    assert any(d["id"] == res["id"] for d in srv.get_profile()["decks"])

    # Delete removes it again.
    srv.delete_deck(res["id"])
    assert all(d["id"] != res["id"] for d in srv.get_profile()["decks"])


def test_collection_endpoint_returns_owned_with_counts(iso):
    col = srv.collection()
    assert col["distinct"] == 50
    assert len(col["cards"]) == 50
    assert all(c["owned"] >= 1 for c in col["cards"])
    # filtering by type still only returns owned cards
    monsters = srv.collection(type="monster")
    assert all(c["cardType"] == "monster" for c in monsters["cards"])
    assert len(monsters["cards"]) <= 50


def test_tournament_flow(iso):
    data = srv.tournaments()
    assert data["tournament"] is None
    assert len(data["presets"]) >= 1
    preset = data["presets"][0]

    # Start with the owned Starter Deck.
    st = srv.start_tournament({"presetId": preset["id"], "deckId": srv.STARTER_DECK_ID})
    assert st["tournament"]["active"] is True
    assert st["currentOpponent"]["name"] == preset["opponents"][0]["name"]

    before = srv.get_profile()["duelistPoints"]
    bonus_seen = 0
    for _ in range(preset["rounds"]):
        r = srv.advance_tournament({"won": True})
        bonus_seen += r["bonus"]
    assert r["tournament"]["champion"] is True
    assert bonus_seen == preset["reward"]
    # champion bonus landed on top of any per-duel DP
    assert srv.get_profile()["duelistPoints"] == before + preset["reward"]


def test_tournament_rejects_unowned_deck(iso):
    import pytest as _pytest
    from fastapi import HTTPException as _HE

    preset = srv.tournaments()["presets"][0]
    # A bundled GBA deck the fresh profile doesn't own.
    with _pytest.raises(_HE) as e:
        srv.start_tournament({"presetId": preset["id"], "deckId": "gba/eternal_duelist_soul/yami_yugi.txt"})
    assert e.value.status_code == 400


def test_tournament_forfeit(iso):
    preset = srv.tournaments()["presets"][0]
    srv.start_tournament({"presetId": preset["id"], "deckId": srv.STARTER_DECK_ID})
    assert srv.tournament_now()["tournament"]["active"] is True
    srv.forfeit_tournament()
    assert srv.tournament_now()["tournament"] is None


def test_reset_profile(iso):
    srv.buy_pack(
        {"packId": min((p for g in srv.packs()["games"] for p in g["packs"]), key=lambda p: p["price"])["id"]}
    )
    assert srv.get_profile()["packsOpened"] == 1
    fresh = srv.reset_profile()
    assert fresh["packsOpened"] == 0
    assert fresh["duelistPoints"] == 2000
