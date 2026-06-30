"""Single-player tournament: a gauntlet bracket of opponents played for DP.

A tournament run is a plain dict stored on the profile (so it persists and can be
resumed). You face the opponents in order with one chosen deck; win to advance,
lose and you're eliminated. Win the final and you're champion — for a DP bonus on
top of the per-duel winnings.

The bracket is single-player: only *your* matches are real duels, so a "bracket"
is, from your seat, a fixed gauntlet — exactly how the GBA championships played.
"""

from __future__ import annotations

DP_PER_ROUND = 250  # champion bonus = this × number of opponents in the bracket


def start_run(name: str, deck_id: str, opponents: list[dict]) -> dict:
    """Begin a fresh run. ``opponents`` is an ordered ``[{id,name,portrait}]``."""
    return {
        "active": True,
        "name": name,
        "deck": deck_id,
        "opponents": opponents,
        "round": 0,  # index of the opponent you're facing now
        "wins": 0,
        "eliminated": False,
        "champion": False,
        "reward": DP_PER_ROUND * len(opponents),
    }


def current_opponent(run: dict | None) -> dict | None:
    """The opponent you face next, or None if the run is over/inactive."""
    if not run or not run.get("active"):
        return None
    opponents = run.get("opponents", [])
    i = run.get("round", 0)
    return opponents[i] if i < len(opponents) else None


def advance(run: dict, won: bool) -> tuple[dict, int]:
    """Apply a match result. Returns ``(run, bonus_dp)`` (bonus only on winning it all)."""
    if not run or not run.get("active"):
        return run, 0
    if not won:
        run["active"] = False
        run["eliminated"] = True
        return run, 0
    run["wins"] = run.get("wins", 0) + 1
    run["round"] = run.get("round", 0) + 1
    if run["round"] >= len(run.get("opponents", [])):
        run["active"] = False
        run["champion"] = True
        return run, int(run.get("reward", 0))
    return run, 0
