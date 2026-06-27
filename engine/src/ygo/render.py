"""A plain-text view of the board.

This is for watching duels in the terminal and for debugging bots; the Svelte
client (Milestone 1.5) will render the same GameState graphically. Player 1 (the
opponent) is drawn at the top, mirrored, as if seated across the table.
"""

from __future__ import annotations

from .enums import Position, Zone
from .state import GameState

CELL_W = 16


def _trunc(text: str, width: int = CELL_W - 2) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _field_cell(state: GameState, iid: int | None) -> str:
    if iid is None:
        return "·".center(CELL_W)
    inst = state.inst(iid)
    card = inst.card
    pos = inst.position
    if pos is Position.FACE_DOWN or pos is Position.FACE_DOWN_DEFENSE:
        body = "[face-down]"
    elif card.is_monster:
        tag = "ATK" if pos is Position.FACE_UP_ATTACK else "DEF"
        stat = card.attack if pos is Position.FACE_UP_ATTACK else card.defense
        body = f"{_trunc(card.name, CELL_W - 8)} {tag[0]}{stat}"
    else:
        body = _trunc(card.name)
    return body.center(CELL_W)


def _row(state: GameState, slots: list[int | None]) -> str:
    return "|" + "|".join(_field_cell(state, s) for s in slots) + "|"


def _counts(state: GameState, player: int) -> str:
    p = state.players[player]
    return (
        f"LP {p.life_points:>5}   "
        f"hand {len(p.hand)}  deck {len(p.deck)}  "
        f"GY {len(p.graveyard)}  extra {len(p.extra_deck)}"
    )


def _hand(state: GameState, player: int) -> str:
    p = state.players[player]
    names = [state.inst(iid).name for iid in p.hand]
    lines = [f"  {i+1}. {n}" for i, n in enumerate(names)]
    return "\n".join(lines) if lines else "  (empty)"


def render(state: GameState, *, viewer: int = 0, show_opponent_hand: bool = False) -> str:
    """Render the board from ``viewer``'s seat."""
    me, opp = viewer, state.opponent_of(viewer)
    width = CELL_W * 5 + 6
    bar = "=" * width

    turn_name = state.players[state.turn_player].name
    header = f" Turn {state.turn_count} — {turn_name}'s {state.phase.value.replace('_', ' ')} "

    out = [bar, header.center(width, "-"), bar]

    # Opponent (top, mirrored)
    out.append(f"[{state.players[opp].name}]  {_counts(state, opp)}")
    if show_opponent_hand:
        out.append("  hand:")
        out.append(_hand(state, opp))
    out.append(_row(state, list(reversed(state.players[opp].spell_trap_zones))))
    out.append(_row(state, list(reversed(state.players[opp].monster_zones))))

    out.append("-" * width)

    # Viewer (bottom)
    out.append(_row(state, state.players[me].monster_zones))
    out.append(_row(state, state.players[me].spell_trap_zones))
    out.append(f"[{state.players[me].name}]  {_counts(state, me)}")
    out.append("  hand:")
    out.append(_hand(state, me))
    out.append(bar)
    return "\n".join(out)
