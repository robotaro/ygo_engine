"""Player moves: the action types, legal-move enumeration, and how moves apply.

This is the engine's *action space*. ``legal_actions(state, player)`` lists what
the turn player may do right now; ``apply(state, action)`` mutates the state and
returns a short human-readable description (for the log / replay).

Keeping moves as plain data with a single ``apply`` keeps the engine a clean
``(state, action) -> state'`` function — exactly what bots and replays need.

At Milestone 1 only the turn player acts (vanilla decks have no fast effects, so
there are no priority windows yet). The Chain + priority slot in at M2.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .enums import Phase, Position
from .state import GameState

HAND_SIZE_LIMIT = 6


# --------------------------------------------------------------------------- #
#  Action types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Action:
    """Base class for a player move."""


@dataclass(frozen=True)
class NormalSummon(Action):
    """Normal/Tribute Summon a monster from the hand in face-up Attack Position."""

    iid: int
    tributes: tuple[int, ...] = ()
    zone_index: int | None = None  # None -> first empty zone (UI may pin a slot)


@dataclass(frozen=True)
class SetMonster(Action):
    """Set a monster from the hand face-down in Defense Position."""

    iid: int
    tributes: tuple[int, ...] = ()
    zone_index: int | None = None


@dataclass(frozen=True)
class FlipSummon(Action):
    """Flip a face-down Defense monster up into Attack Position."""

    iid: int


@dataclass(frozen=True)
class ChangePosition(Action):
    """Switch a face-up monster between Attack and Defense Position."""

    iid: int


@dataclass(frozen=True)
class DeclareAttack(Action):
    """Attack with ``attacker``; ``target=None`` is a direct attack."""

    attacker: int
    target: int | None = None


@dataclass(frozen=True)
class DiscardCard(Action):
    """Discard a card (used to meet the End Phase hand-size limit)."""

    iid: int


@dataclass(frozen=True)
class Pass(Action):
    """Proceed past the current decision point (advance phase / end Battle)."""


# --------------------------------------------------------------------------- #
#  Summoning requirements
# --------------------------------------------------------------------------- #
def tributes_required(level: int | None) -> int:
    """Level 1-4 -> 0, Level 5-6 -> 1, Level 7+ -> 2."""
    lvl = level or 0
    if lvl <= 4:
        return 0
    return 1 if lvl <= 6 else 2


# --------------------------------------------------------------------------- #
#  Legal-move enumeration
# --------------------------------------------------------------------------- #
def legal_actions(state: GameState, player: int) -> list[Action]:
    """Enumerate the turn player's legal moves for the current phase.

    ``Pass`` is *not* included here; the engine adds it where passing is allowed.
    """
    phase = state.phase
    if phase in (Phase.MAIN_1, Phase.MAIN_2):
        return _main_phase_actions(state, player)
    if phase is Phase.BATTLE:
        return _battle_phase_actions(state, player)
    if phase is Phase.END:
        return _end_phase_actions(state, player)
    return []


def _main_phase_actions(state: GameState, player: int) -> list[Action]:
    p = state.players[player]
    actions: list[Action] = []

    if not state.normal_summon_used:
        controlled = [m for m in p.monster_zones if m is not None]
        has_empty = state.first_empty_monster_zone(player) is not None
        for iid in p.hand:
            card = state.inst(iid).card
            if not card.can_normal_summon:
                continue
            need = tributes_required(card.level)
            if need == 0:
                if has_empty:
                    actions.append(NormalSummon(iid))
                    actions.append(SetMonster(iid))
            elif len(controlled) >= need:
                # tributing frees the zone(s), so no pre-existing empty slot needed
                for combo in combinations(controlled, need):
                    actions.append(NormalSummon(iid, tributes=combo))
                    actions.append(SetMonster(iid, tributes=combo))

    # battle-position changes (not on the turn a monster was summoned/already changed)
    for iid in p.monster_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if inst.summoned_this_turn or inst.position_changed_this_turn:
            continue
        if inst.position is Position.FACE_DOWN_DEFENSE:
            actions.append(FlipSummon(iid))
        elif inst.position in (Position.FACE_UP_ATTACK, Position.FACE_UP_DEFENSE):
            actions.append(ChangePosition(iid))

    return actions


def _battle_phase_actions(state: GameState, player: int) -> list[Action]:
    opp = state.opponent_of(player)
    opp_monsters = [m for m in state.players[opp].monster_zones if m is not None]
    actions: list[Action] = []
    for iid in state.players[player].monster_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if inst.position is not Position.FACE_UP_ATTACK or inst.attacked_this_turn:
            continue
        if opp_monsters:
            actions.extend(DeclareAttack(iid, t) for t in opp_monsters)
        else:
            actions.append(DeclareAttack(iid, None))  # direct attack
    return actions


def _end_phase_actions(state: GameState, player: int) -> list[Action]:
    p = state.players[player]
    if len(p.hand) <= HAND_SIZE_LIMIT:
        return []
    return [DiscardCard(iid) for iid in p.hand]


# --------------------------------------------------------------------------- #
#  Applying a move
# --------------------------------------------------------------------------- #
def apply(state: GameState, action: Action) -> str:
    """Mutate ``state`` by ``action``; return a short description for the log."""
    if isinstance(action, NormalSummon):
        return _summon(state, action.iid, action.tributes, action.zone_index, face_up=True)
    if isinstance(action, SetMonster):
        return _summon(state, action.iid, action.tributes, action.zone_index, face_up=False)
    if isinstance(action, FlipSummon):
        inst = state.inst(action.iid)
        inst.position = Position.FACE_UP_ATTACK
        inst.position_changed_this_turn = True
        return f"Flip Summons {inst.name}"
    if isinstance(action, ChangePosition):
        inst = state.inst(action.iid)
        if inst.position is Position.FACE_UP_ATTACK:
            inst.position = Position.FACE_UP_DEFENSE
            new = "Defense"
        else:
            inst.position = Position.FACE_UP_ATTACK
            new = "Attack"
        inst.position_changed_this_turn = True
        return f"switches {inst.name} to {new} Position"
    if isinstance(action, DeclareAttack):
        return _resolve_attack(state, action)
    if isinstance(action, DiscardCard):
        name = state.inst(action.iid).name
        state.send_to_graveyard(action.iid)
        return f"discards {name}"
    raise ValueError(f"cannot apply action: {action!r}")


def _summon(
    state: GameState,
    iid: int,
    tributes: tuple[int, ...],
    zone_index: int | None,
    *,
    face_up: bool,
) -> str:
    inst = state.inst(iid)
    player = inst.owner  # the card is in the summoner's hand
    for tribute_iid in tributes:
        state.send_to_graveyard(tribute_iid)

    if zone_index is None or state.players[player].monster_zones[zone_index] is not None:
        zone_index = state.first_empty_monster_zone(player)

    position = Position.FACE_UP_ATTACK if face_up else Position.FACE_DOWN_DEFENSE
    state.place_monster(iid, player, zone_index, position)
    inst.summoned_this_turn = True
    state.normal_summon_used = True

    verb = "Normal Summons" if face_up else "Sets"
    extra = f" (tributing {len(tributes)})" if tributes else ""
    return f"{verb} {inst.name}{extra}"


def _resolve_attack(state: GameState, action: DeclareAttack) -> str:
    """Resolve one attack using the v6.0 Determining Damage rules (no piercing)."""
    attacker = state.inst(action.attacker)
    attacker.attacked_this_turn = True
    me = attacker.controller
    opp = state.opponent_of(me)
    atk = attacker.card.attack or 0

    if action.target is None:
        state.players[opp].life_points -= atk
        return f"{attacker.name} attacks directly — {atk} damage"

    target = state.inst(action.target)
    prefix = ""
    if target.position is Position.FACE_DOWN_DEFENSE:
        target.position = Position.FACE_UP_DEFENSE
        prefix = f"(flips up {target.name}) "

    if target.position is Position.FACE_UP_ATTACK:
        other = target.card.attack or 0
        if atk > other:
            state.send_to_graveyard(target.iid)
            state.players[opp].life_points -= atk - other
            return f"{prefix}{attacker.name} ({atk}) destroys {target.name} ({other}) — {atk - other} damage"
        if atk < other:
            state.send_to_graveyard(attacker.iid)
            state.players[me].life_points -= other - atk
            return f"{prefix}{attacker.name} ({atk}) is destroyed by {target.name} ({other}) — {other - atk} damage to attacker"
        state.send_to_graveyard(attacker.iid)
        state.send_to_graveyard(target.iid)
        return f"{prefix}{attacker.name} and {target.name} ({atk}) destroy each other"

    # defending monster: ATK vs DEF, no piercing in v6.0 vanilla play
    dfn = target.card.defense or 0
    if atk > dfn:
        state.send_to_graveyard(target.iid)
        return f"{prefix}{attacker.name} ({atk}) destroys defending {target.name} (DEF {dfn})"
    if atk < dfn:
        state.players[me].life_points -= dfn - atk
        return f"{prefix}{attacker.name} ({atk}) bounces off {target.name} (DEF {dfn}) — {dfn - atk} damage to attacker"
    return f"{prefix}{attacker.name} ({atk}) cannot break {target.name} (DEF {dfn})"
