"""Verbose, omniscient event trace for debugging.

One line per state change, so any duel can be reconstructed move-by-move and any
bug pinned to the exact event that caused it. This is a firehose, not player-facing
narration.

The backbone is a **snapshot diff**: capture the entire internal state, and whenever
the engine advances, print every field that changed. Nothing a card does can slip
past it, because it reads the *resulting state* — not the code path that produced it —
so new cards and new effects are covered for free. Interleaved with the engine's own
causal narration (``· ...`` lines) and animation cues (``FX ...``), the result reads as:
what the engine did, then exactly what changed as a result.

Line shapes:
  ``INIT key = value``   the opening full-state dump (the baseline for later diffs)
  ``· <message>``        a causal narration line (mirrors the on-screen log)
  ``FX {...}``           an animation/event cue (attack declared, effect activated, ...)
  ``Δ key: old -> new``  one field of game state changed (``-`` means absent)
"""

from __future__ import annotations

from .enums import Zone
from .state import GameState

# Per-instance flags surfaced only when set to a non-default value, so the diff stays
# readable — a flag flipping on reads as ``- -> True``, resetting reads as ``True -> -``.
_INSTANCE_FLAGS = (
    "summoned_this_turn",
    "attacked_this_turn",
    "attacks_made_this_turn",
    "attack_cost_paid",
    "position_changed_this_turn",
    "destroyed_a_monster_by_battle_this_turn",
    "gemini_unlocked",
    "died_by_battle",
    "set_on_turn",
    "control_until_end_of_turn",
    "attack_disabled_on_turn",
)


def _loc(inst) -> str:
    """A card's location as ``zone(pN[,zI])`` — the thing that changes when it moves."""
    z = inst.zone
    if z in (Zone.MONSTER, Zone.SPELL_TRAP):
        return f"{z.value}(p{inst.controller},z{inst.zone_index})"
    return f"{z.value}(p{inst.controller})"


def _pile(state: GameState, iids) -> str:
    return "[" + ", ".join(f"{state.inst(i).card.name}#{i}" for i in iids) + "]"


def debug_snapshot(state: GameState) -> dict[str, str]:
    """Flatten the whole board into ``{key: stringified value}``. Diffing two of these
    yields one line per changed field — the atoms of the trace."""
    snap: dict[str, str] = {}

    # --- game-level state ---
    game = {
        "turn": state.turn_count,
        "phase": state.phase.value,
        "turn_player": state.turn_player,
        "normal_summon_used": state.normal_summon_used,
        "forced_attack_target": state.forced_attack_target,
        "direct_damage_dealt_this_turn": state.direct_damage_dealt_this_turn,
        "battle_phase_ended": state.battle_phase_ended,
        "attack_negated": state.attack_negated,
        "attack_redirect": state.attack_redirect,
        "reflect_battle_damage": state.reflect_battle_damage,
        "chain": [state.inst(link.source_iid).card.name for link in state.chain],
        "action_locks": dict(state.action_locks),
    }
    for k, v in game.items():
        snap[f"game.{k}"] = str(v)

    # --- per player ---
    for p in (0, 1):
        pl = state.players[p]
        snap[f"p{p}.LP"] = str(pl.life_points)
        snap[f"p{p}.hand"] = _pile(state, pl.hand)
        snap[f"p{p}.deck_count"] = str(len(pl.deck))
        snap[f"p{p}.graveyard"] = _pile(state, pl.graveyard)
        snap[f"p{p}.banished"] = _pile(state, pl.banished)

    # --- per card instance ---
    for iid, inst in state.cards.items():
        tag = f"c{iid}[{inst.card.name}]"
        snap[f"{tag}.loc"] = _loc(inst)
        if inst.position is not None:  # only on-field cards have a battle position
            snap[f"{tag}.pos"] = inst.position.value
        if inst.counters:
            snap[f"{tag}.counters"] = str(dict(inst.counters))
        if inst.equipped_to is not None:
            snap[f"{tag}.equipped_to"] = str(inst.equipped_to)
        for flag in _INSTANCE_FLAGS:
            val = getattr(inst, flag, None)
            if val not in (False, 0, None):  # only surface non-defaults
                snap[f"{tag}.{flag}"] = str(val)

    return snap


def diff_snapshots(old: dict[str, str], new: dict[str, str]) -> list[str]:
    """``key: old -> new`` for every field that changed (``-`` for absent)."""
    lines = []
    for key in sorted(old.keys() | new.keys()):
        o = old.get(key)
        n = new.get(key)
        if o != n:
            lines.append(f"{key}: {'-' if o is None else o} -> {'-' if n is None else n}")
    return lines
