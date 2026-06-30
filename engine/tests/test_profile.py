"""The player profile / save system: collection, DP economy, owned-only decks."""

from __future__ import annotations

import json

from ygo import profile as P


def test_new_profile_seeded_from_starter_deck():
    prof = P.new_profile()
    assert prof.duelist_points == P.STARTING_DP
    # The starter deck is a 50-card singleton list -> 50 distinct cards owned.
    assert len(prof.collection) == 50
    assert prof.total_cards() == 50
    assert prof.active_deck == P.STARTER_DECK_ID
    # Owns the starter deck's cards -> nothing missing to build it.
    assert prof.missing_for_deck(P.starter_collection()) == {}


def test_deck_ids_include_starter_and_dedup():
    prof = P.new_profile()
    prof.decks = ["user/a.txt", "user/b.txt", "user/a.txt"]
    ids = prof.deck_ids()
    assert ids[0] == P.STARTER_DECK_ID
    assert ids.count("user/a.txt") == 1  # deduped
    assert set(ids) == {P.STARTER_DECK_ID, "user/a.txt", "user/b.txt"}


def test_add_cards_and_missing():
    prof = P.new_profile()
    assert prof.missing_for_deck({"Blue-Eyes White Dragon": 3}) == {"Blue-Eyes White Dragon": 3}
    prof.add_cards({"Blue-Eyes White Dragon": 2})
    assert prof.owns("Blue-Eyes White Dragon", 2)
    # still one short of three copies
    assert prof.missing_for_deck({"Blue-Eyes White Dragon": 3}) == {"Blue-Eyes White Dragon": 1}


def test_dp_spend_earn_and_afford():
    prof = P.Profile(duelist_points=300)
    assert prof.can_afford(300) and not prof.can_afford(301)
    prof.spend(100)
    assert prof.duelist_points == 200
    prof.earn(50)
    assert prof.duelist_points == 250
    try:
        prof.spend(10_000)
    except ValueError:
        pass
    else:
        raise AssertionError("overspend should raise")


def test_record_result_awards_dp_and_tallies():
    prof = P.Profile(duelist_points=0)
    earned = prof.record_result(True)
    assert earned == P.WIN_DP and prof.duelist_points == P.WIN_DP
    assert prof.stats == {"wins": 1, "losses": 0, "duels": 1}
    earned2 = prof.record_result(False)
    assert earned2 == P.LOSS_DP
    assert prof.stats == {"wins": 1, "losses": 1, "duels": 2}


def test_json_round_trip():
    prof = P.new_profile()
    prof.add_cards({"Blue-Eyes White Dragon": 3})
    prof.decks.append("user/x.txt")
    prof.record_result(True)
    clone = P.Profile.from_json_obj(json.loads(json.dumps(prof.to_json_obj())))
    assert clone.to_json_obj() == prof.to_json_obj()


def test_load_creates_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    assert not P.profile_path().exists()
    prof = P.load_profile()  # creates + saves a fresh one
    assert P.profile_path().exists()
    prof.add_cards({"Dark Magician": 1})
    P.save_profile(prof)
    reloaded = P.load_profile()
    assert reloaded.collection["Dark Magician"] == prof.collection["Dark Magician"]
