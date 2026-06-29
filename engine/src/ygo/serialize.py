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
    ActivateMonsterEffect,
    ActivateSpell,
    ChangePosition,
    DeclareAttack,
    DiscardCard,
    FlipSummon,
    GeminiSummon,
    NormalSummon,
    Pass,
    SetMonster,
    SetSpellTrap,
    SpecialSummonFromHand,
    UnionEquip,
    UnionUnequip,
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
        "subtype": c.subtype.value if c.subtype else None,  # Field / Equip / Continuous / ...
        "attack": c.attack,
        "defense": c.defense,
        "level": c.level,
        "attribute": c.attribute.value if c.attribute else None,
        "race": c.race,
        "text": c.text,
        "imageId": c.image_id,
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
        if inst.card.is_monster:  # current (post-modifier) stats for the board
            cell["effAtk"] = state.effective_attack(iid)
            cell["effDef"] = state.effective_defense(iid)
        if inst.card.is_gemini:  # Gemini: show whether the effect is unlocked
            cell["geminiUnlocked"] = inst.gemini_unlocked
        if inst.equipped_to is not None:
            cell["equippedTo"] = inst.equipped_to
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
        "banished": [_card_public(state.inst(i)) for i in p.banished],
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
        "chain": [
            {
                "controller": link.controller,
                "youAreController": link.controller == viewer,
                "name": state.inst(link.source_iid).name,
            }
            for link in state.chain
        ],
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
    activatable: dict[int, list[list[int]]] = {}
    monster_activatable: dict[int, list[list[int]]] = {}
    settable: list[int] = []
    gemini_summonable: list[int] = []
    special_summonable: list[int] = []
    union_equippable: dict[int, list[int]] = {}
    union_unequippable: list[int] = []

    for a in legal:
        if isinstance(a, NormalSummon):
            entry = summonable.setdefault(a.iid, {"summon": [], "set": []})
            entry["summon"].append(list(a.tributes))
        elif isinstance(a, SetMonster):
            entry = summonable.setdefault(a.iid, {"summon": [], "set": []})
            entry["set"].append(list(a.tributes))
        elif isinstance(a, SpecialSummonFromHand):
            special_summonable.append(a.iid)
        elif isinstance(a, GeminiSummon):
            gemini_summonable.append(a.iid)
        elif isinstance(a, UnionEquip):
            union_equippable.setdefault(a.union_iid, []).append(a.host_iid)
        elif isinstance(a, UnionUnequip):
            union_unequippable.append(a.union_iid)
        elif isinstance(a, FlipSummon):
            flips.append(a.iid)
        elif isinstance(a, ChangePosition):
            position_changes.append(a.iid)
        elif isinstance(a, DeclareAttack):
            attackers.setdefault(a.attacker, []).append(a.target)
        elif isinstance(a, ActivateSpell):
            activatable.setdefault(a.iid, []).append(list(a.targets))
        elif isinstance(a, ActivateMonsterEffect):
            monster_activatable.setdefault(a.iid, []).append(list(a.targets))
        elif isinstance(a, SetSpellTrap):
            settable.append(a.iid)
        elif isinstance(a, DiscardCard):
            discards.append(a.iid)

    return {
        # iid -> {"summon": [[tribute_iids]...], "set": [[...]]}
        "summonable": {str(k): v for k, v in summonable.items()},
        # attacker iid -> [target iids... or null for direct]
        "attackers": {str(k): v for k, v in attackers.items()},
        "flips": flips,
        "geminiSummonable": gemini_summonable,
        # iids in hand that may Special Summon themselves (Cyber Dragon, etc.)
        "specialSummonable": special_summonable,
        # union iid -> [valid host iids]; equipped-Union iids that may unequip
        "unionEquippable": {str(k): v for k, v in union_equippable.items()},
        "unionUnequippable": union_unequippable,
        "positionChanges": position_changes,
        # iid -> [[target iids]...]; [[]] means "activatable, no target"
        "activatable": {str(k): v for k, v in activatable.items()},
        # face-up monster iid -> [[target iids]...]; an Ignition effect (Royal Magical
        # Library, Breaker) you may start from a monster you control
        "monsterActivatable": {str(k): v for k, v in monster_activatable.items()},
        "settable": settable,
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

    if kind == "geminiSummon":
        iid = intent.get("iid")
        return next((a for a in legal if isinstance(a, GeminiSummon) and a.iid == iid), None)

    if kind == "specialSummon":
        iid = intent.get("iid")
        return next(
            (a for a in legal if isinstance(a, SpecialSummonFromHand) and a.iid == iid), None
        )

    if kind == "unionEquip":
        union = intent.get("union")
        host = intent.get("host")
        return next(
            (
                a
                for a in legal
                if isinstance(a, UnionEquip) and a.union_iid == union and a.host_iid == host
            ),
            None,
        )

    if kind == "unionUnequip":
        union = intent.get("union")
        return next(
            (a for a in legal if isinstance(a, UnionUnequip) and a.union_iid == union), None
        )

    if kind == "changePosition":
        iid = intent.get("iid")
        return next((a for a in legal if isinstance(a, ChangePosition) and a.iid == iid), None)

    if kind == "discard":
        iid = intent.get("iid")
        return next((a for a in legal if isinstance(a, DiscardCard) and a.iid == iid), None)

    if kind == "activate":
        iid = intent.get("iid")
        targets = tuple(intent.get("targets", []))
        match = next(
            (
                a
                for a in legal
                if isinstance(a, ActivateSpell) and a.iid == iid and set(a.targets) == set(targets)
            ),
            None,
        )
        if match is None:
            return None
        return ActivateSpell(iid=iid, targets=targets, zone_index=intent.get("zoneIndex"))

    if kind == "activateMonster":
        iid = intent.get("iid")
        targets = tuple(intent.get("targets", []))
        match = next(
            (
                a
                for a in legal
                if isinstance(a, ActivateMonsterEffect)
                and a.iid == iid
                and set(a.targets) == set(targets)
            ),
            None,
        )
        return ActivateMonsterEffect(iid=iid, targets=targets) if match is not None else None

    if kind == "set":
        # A card iid is either a Spell/Trap (Set face-down in the S/T row) or a
        # monster (Set face-down in Defense) — disambiguate by what's legal.
        iid = intent.get("iid")
        if any(isinstance(a, SetSpellTrap) and a.iid == iid for a in legal):
            return SetSpellTrap(iid=iid, zone_index=intent.get("zoneIndex"))
        tributes = tuple(intent.get("tributes", []))
        if any(
            isinstance(a, SetMonster) and a.iid == iid and set(a.tributes) == set(tributes)
            for a in legal
        ):
            return SetMonster(iid=iid, tributes=tributes, zone_index=intent.get("zoneIndex"))
        return None

    if kind == "summon":
        iid = intent.get("iid")
        tributes = tuple(intent.get("tributes", []))
        if any(
            isinstance(a, NormalSummon) and a.iid == iid and set(a.tributes) == set(tributes)
            for a in legal
        ):
            return NormalSummon(iid=iid, tributes=tributes, zone_index=intent.get("zoneIndex"))
        return None

    return None
