"""Win rewards: a win grants a free booster-pack pick from the opponent's game."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from ygo.server import app as srv  # noqa: E402


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("YGO_PROFILE_DIR", str(tmp_path))
    return tmp_path


def _a_gba_game_with_packs():
    pack = next(p for p in srv._all_packs() if p.game)
    return pack.game


def test_opponent_game_parses_gba_deck_ids():
    assert srv.opponent_game("gba/eternal_duelist_soul/Yami Yugi.txt") == "eternal_duelist_soul"
    assert srv.opponent_game("ygored/Starter-Deck-Yugi.txt") is None
    assert srv.opponent_game(None) is None


def test_no_reward_when_none_pending(iso):
    data = srv.rewards()
    assert data["pending"] is False
    assert data["packs"] == []


def test_win_sets_pending_reward_and_no_dp(iso):
    game = _a_gba_game_with_packs()
    profile = srv.load_profile()
    before_dp = profile.duelist_points
    # Simulate the WS result handler's reward branch.
    profile.record_result(True, dp=0)
    profile.add_reward({"game": game})
    srv.save_profile(profile)

    assert srv.load_profile().duelist_points == before_dp  # no DP for the win
    data = srv.rewards()
    assert data["pending"] is True and data["game"] == game
    assert len(data["packs"]) >= 1
    assert all("art" in p and p["name"] for p in data["packs"])


def test_claim_reward_grants_cards_and_clears(iso):
    game = _a_gba_game_with_packs()
    profile = srv.load_profile()
    profile.add_reward({"game": game})
    srv.save_profile(profile)

    choices = srv.rewards()["packs"]
    chosen = choices[0]
    before = srv.load_profile().total_cards()
    res = srv.claim_reward({"packId": chosen["id"]})

    assert len(res["pulled"]) >= 1
    assert srv.load_profile().total_cards() > before
    assert srv.load_profile().pending_rewards == []
    assert srv.rewards()["pending"] is False


def test_reward_queue_survives_a_second_win(iso):
    # Two wins before either reward is claimed: both must queue (no lost reward).
    games = {p.game for p in srv._all_packs()}
    g1, g2 = sorted(games)[:2]
    profile = srv.load_profile()
    profile.add_reward({"game": g1})
    profile.add_reward({"game": g2})
    srv.save_profile(profile)

    assert srv.rewards()["pendingCount"] == 2
    assert srv.rewards()["game"] == g1  # oldest first (FIFO)

    first = next(p for p in srv._all_packs() if p.game == g1)
    srv.claim_reward({"packId": first.id})
    # The second reward is still pending after claiming the first.
    assert srv.load_profile().pending_rewards == [{"game": g2}]
    assert srv.rewards()["game"] == g2


def test_claim_rejects_pack_from_another_game(iso):
    games = {p.game for p in srv._all_packs()}
    assert len(games) >= 2
    g1, g2 = sorted(games)[:2]
    profile = srv.load_profile()
    profile.add_reward({"game": g1})
    srv.save_profile(profile)
    other = next(p for p in srv._all_packs() if p.game == g2)
    with pytest.raises(HTTPException) as e:
        srv.claim_reward({"packId": other.id})
    assert e.value.status_code == 400


def test_claim_without_pending_is_400(iso):
    with pytest.raises(HTTPException) as e:
        srv.claim_reward({"packId": "whatever"})
    assert e.value.status_code == 400


def test_loss_still_pays_consolation_dp(iso):
    profile = srv.load_profile()
    before = profile.duelist_points
    earned = profile.record_result(False)
    assert earned > 0 and profile.duelist_points == before + earned
