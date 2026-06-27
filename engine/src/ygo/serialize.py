"""Translate between the engine and the web client.

Two directions:
  * ``state_to_dict`` — a JSON view of the board from one player's seat, hiding
    information that player shouldn't see (the opponent's hand, face-down cards).
  * ``match_intent`` — turn a client "intent" (drag a card here, attack that) into
    a concrete, *legal* engine Action, or ``None`` if it isn't allowed.

The client thinks in intents; the engine enforces legality. The client never
needs to know the engine's internal action list.
"""

from __future__ import annotations

from .enums import Position
from .moves import (
    Action,
    ActivateSpell,
    ChangePosition,
    DeclareAttack,
    DiscardCard,
    FlipSummon,
    NormalSummon,
    Pass,
    SetMonster,
    legal_actions,
)
from .state import CardInstance, GameState


# --------------------------------------------------------------------------- #
#  State -> client
# --------------------------------------------------------------------------- #
def _card_public(inst: CardInstance) -> dict:
    """Full, visible card info (own cards / face-up cards)."""
    c = inst.card
    return {
        "iid": inst.iid,
        "name": c.name,
        "cardType": c.card_type.value,
        "attack": c.attack,
        "defense": c.defense,
        "level": c.level,
        "attribute": c.attribute.value if c.attribute else None,
        "race": c.race,
        "text": c.text,
    }


def _monster_slot(state: GameState, iid: int | None, *, hide_face_down: bool) -> dict | None:
    if iid is None:
        return None
    inst = state.inst(iid)
    face_down = inst.position in (Position.FACE_DOWN_DEFENSE, Position.FACE_DOWN)
    cell = {
        "iid": inst.iid,
        "position": inst.position.value if inst.position else None,
        "faceDown": face_down,
        "summonedThisTurn": inst.summoned_this_turn,
        "attackedThisTurn": inst.attacked_this_turn,
    }
    if face_down and hide_face_down:
        cell["name"] = None  # hidden from the opponent
    else:
        cell.update(_card_public(inst))
    return cell


def _player_view(state: GameState, player: int, *, is_viewer: bool) -> dict:
    p = state.players[player]
    hide = not is_viewer
    return {
        "name": p.name,
        "lifePoints": p.life_points,
        "hand": (
            [_card_public(state.inst(i)) for i in p.hand]
            if is_viewer
            else [{"hidden": True} for _ in p.hand]
        ),
        "handCount": len(p.hand),
        "deckCount": len(p.deck),
        "extraCount": len(p.extra_deck),
        "graveyard": [_card_public(state.inst(i)) for i in p.graveyard],
        "monsterZones": [_monster_slot(state, i, hide_face_down=hide) for i in p.monster_zones],
        "spellTrapZones": [_monster_slot(state, i, hide_face_down=hide) for i in p.spell_trap_zones],
        "fieldZone": _monster_slot(state, p.field_zone, hide_face_down=hide),
    }


def state_to_dict(state: GameState, viewer: int) -> dict:
    opp = state.opponent_of(viewer)
    return {
        "viewer": viewer,
        "turnPlayer": state.turn_player,
        "turnCount": state.turn_count,
        "phase": state.phase.value,
        "you": _player_view(state, viewer, is_viewer=True),
        "opponent": _player_view(state, opp, is_viewer=False),
    }


# --------------------------------------------------------------------------- #
#  Legal actions -> client (so the UI can highlight affordances)
# --------------------------------------------------------------------------- #
def legal_to_dict(state: GameState, player: int, *, with_pass: bool) -> dict:
    legal = legal_actions(state, player)
    summonable: dict[int, dict] = {}
    attackers: dict[int, list[int | None]] = {}
    flips: list[int] = []
    position_changes: list[int] = []
    discards: list[int] = []
    activatable: list[int] = []

    for a in legal:
        if isinstance(a, NormalSummon):
            entry = summonable.setdefault(a.iid, {"summon": [], "set": []})
            entry["summon"].append(list(a.tributes))
        elif isinstance(a, SetMonster):
            entry = summonable.setdefault(a.iid, {"summon": [], "set": []})
            entry["set"].append(list(a.tributes))
        elif isinstance(a, FlipSummon):
            flips.append(a.iid)
        elif isinstance(a, ChangePosition):
            position_changes.append(a.iid)
        elif isinstance(a, DeclareAttack):
            attackers.setdefault(a.attacker, []).append(a.target)
        elif isinstance(a, ActivateSpell):
            activatable.append(a.iid)
        elif isinstance(a, DiscardCard):
            discards.append(a.iid)

    return {
        # iid -> {"summon": [[tribute_iids]...], "set": [[...]]}
        "summonable": {str(k): v for k, v in summonable.items()},
        # attacker iid -> [target iids... or null for direct]
        "attackers": {str(k): v for k, v in attackers.items()},
        "flips": flips,
        "positionChanges": position_changes,
        "activatable": activatable,
        "discards": discards,
        "canPass": with_pass,
    }


# --------------------------------------------------------------------------- #
#  Client intent -> legal Action
# --------------------------------------------------------------------------- #
def match_intent(intent: dict, legal: list[Action], state: GameState) -> Action | None:
    """Resolve a client intent against the legal action list.

    Summon/Set honour the client's chosen ``zoneIndex`` (for drag-and-drop), but
    only after confirming an equivalent move (same card + tributes) is legal.
    """
    kind = intent.get("kind")

    if kind == "pass":
        return next((a for a in legal if isinstance(a, Pass)), None)

    if kind == "attack":
        attacker = intent.get("attacker")
        target = intent.get("target")  # None = direct
        return next(
            (
                a
                for a in legal
                if isinstance(a, DeclareAttack) and a.attacker == attacker and a.target == target
            ),
            None,
        )

    if kind == "flip":
        iid = intent.get("iid")
        return next((a for a in legal if isinstance(a, FlipSummon) and a.iid == iid), None)

    if kind == "changePosition":
        iid = intent.get("iid")
        return next((a for a in legal if isinstance(a, ChangePosition) and a.iid == iid), None)

    if kind == "discard":
        iid = intent.get("iid")
        return next((a for a in legal if isinstance(a, DiscardCard) and a.iid == iid), None)

    if kind == "activate":
        iid = intent.get("iid")
        if any(isinstance(a, ActivateSpell) and a.iid == iid for a in legal):
            return ActivateSpell(iid=iid, zone_index=intent.get("zoneIndex"))
        return None

    if kind in ("summon", "set"):
        iid = intent.get("iid")
        tributes = tuple(intent.get("tributes", []))
        zone_index = intent.get("zoneIndex")
        want = NormalSummon if kind == "summon" else SetMonster
        legal_match = next(
            (
                a
                for a in legal
                if isinstance(a, want) and a.iid == iid and set(a.tributes) == set(tributes)
            ),
            None,
        )
        if legal_match is None:
            return None
        # rebuild honouring the client's requested zone
        return want(iid=iid, tributes=tributes, zone_index=zone_index)

    return None
