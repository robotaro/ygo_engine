"""The player profile / save system: collection, DP economy, owned-only decks."""

from __future__ import annotations

import json
import threading

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
    clone = P.Profile.from_dict(json.loads(json.dumps(prof.to_json_obj())))
    assert clone.to_json_obj() == prof.to_json_obj()


def test_load_does_not_write_on_read(tmp_path, monkeypatch):
    # A read must not create the file (only an explicit create/mutation persists).
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    assert not P.profile_path().exists()
    prof = P.load_profile()  # returns a fresh in-memory profile, writes nothing
    assert not P.profile_path().exists()
    prof.add_cards({"Dark Magician": 1})
    P.save_profile(prof)  # explicit save persists
    assert P.profile_path().exists()
    reloaded = P.load_profile()
    assert reloaded.collection["Dark Magician"] == prof.collection["Dark Magician"]


# --------------------------------------------------------------------------- #
#  Durability: atomic write, corruption recovery, concurrency, validation
# --------------------------------------------------------------------------- #
def test_save_is_atomic_no_temp_left_behind(tmp_path, monkeypatch):
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    P.save_profile(P.new_profile())
    # The atomic write cleans up after itself — no stray temp files.
    assert not list(tmp_path.glob(".profile.*.tmp"))
    assert P.profile_path().is_file()


def test_concurrent_transactions_dont_lose_updates(tmp_path, monkeypatch):
    # Two threads each running N transactions on the SAME field: with the lock,
    # every increment survives (STARTING_DP + 2N). Without it, load→save races
    # would clobber updates and land well short.
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    P.save_profile(P.new_profile())

    n = 50
    start = threading.Barrier(2)

    def bump():
        start.wait()
        for _ in range(n):
            with P.profile_transaction() as prof:
                prof.duelist_points += 1
                prof.add_cards({"Kuriboh": 1})

    threads = [threading.Thread(target=bump) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = P.load_profile()
    assert final.duelist_points == P.STARTING_DP + 2 * n
    assert final.collection.get("Kuriboh", 0) == 2 * n


def test_truncated_profile_is_recovered_not_bricked(tmp_path, monkeypatch):
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    P.save_profile(P.new_profile())
    # A truncated/torn write on disk.
    P.profile_path().write_text('{"duelist_points": 500, "collec', encoding="utf-8")

    prof = P.load_profile()  # must recover, not raise
    assert isinstance(prof, P.Profile)
    # The unreadable file was quarantined rather than repeatedly re-parsed.
    assert list(tmp_path.glob("profile.json.corrupt.*")), "corrupt file not quarantined"


def test_corrupt_profile_restores_last_good_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    p = P.new_profile()
    p.duelist_points = 777
    P.save_profile(p)  # profile.json = 777 (no .bak yet)
    p.duelist_points = 888
    P.save_profile(p)  # .bak = 777, profile.json = 888
    P.profile_path().write_text("}}not json{{", encoding="utf-8")

    recovered = P.load_profile()
    assert recovered.duelist_points == 777  # restored from the last-good .bak
    assert P.profile_path().is_file()  # reinstated as the live save


def test_from_dict_repairs_garbage_values():
    prof = P.Profile.from_dict(
        {
            "duelist_points": -50,  # negative -> clamped to 0
            "collection": {"Kuriboh": 3, "Debt": -2, "Zero": 0, 123: 4},
            "packs_opened": "oops",  # non-int -> 0
        }
    )
    assert prof.duelist_points == 0
    assert prof.collection == {"Kuriboh": 3}  # negatives/zero/non-str keys dropped
    assert prof.packs_opened == 0
    assert prof.stats == {"wins": 0, "losses": 0, "duels": 0}


def test_from_dict_migrates_legacy_pending_reward():
    assert P.Profile.from_dict({"pending_reward": {"game": "x"}}).pending_rewards == [
        {"game": "x"}
    ]
    assert P.Profile.from_dict({"pending_reward": None}).pending_rewards == []
    # The new field wins if both are present.
    both = P.Profile.from_dict({"pending_reward": {"game": "old"}, "pending_rewards": []})
    assert both.pending_rewards == []
