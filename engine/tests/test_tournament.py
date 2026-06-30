"""Tournament bracket logic (pure, no server)."""

from __future__ import annotations

from ygo import tournament as tour

OPPS = [{"id": f"o{i}", "name": f"Foe {i}", "portrait": None} for i in range(3)]


def test_start_run_shape_and_reward():
    run = tour.start_run("Cup", "deck.txt", OPPS)
    assert run["active"] and not run["champion"] and not run["eliminated"]
    assert run["round"] == 0 and run["wins"] == 0
    assert run["reward"] == tour.DP_PER_ROUND * len(OPPS)
    assert tour.current_opponent(run)["id"] == "o0"


def test_win_all_becomes_champion_with_bonus():
    run = tour.start_run("Cup", "deck.txt", OPPS)
    bonus_total = 0
    for i in range(len(OPPS)):
        run, bonus = tour.advance(run, True)
        bonus_total += bonus
    assert run["champion"] and not run["active"]
    assert run["wins"] == len(OPPS)
    assert bonus_total == run["reward"]
    assert tour.current_opponent(run) is None


def test_a_loss_eliminates_with_no_bonus():
    run = tour.start_run("Cup", "deck.txt", OPPS)
    run, bonus = tour.advance(run, True)  # win round 1
    run, bonus = tour.advance(run, False)  # lose round 2
    assert run["eliminated"] and not run["active"]
    assert bonus == 0
    assert run["wins"] == 1


def test_advance_on_finished_run_is_noop():
    run = tour.start_run("Cup", "deck.txt", OPPS)
    run["active"] = False
    same, bonus = tour.advance(run, True)
    assert bonus == 0 and same is run
