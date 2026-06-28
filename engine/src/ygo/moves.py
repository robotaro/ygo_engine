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

from .effects import OPPONENT, AttackRestriction, EffectContext
from .enums import Phase, Position, SpellTrapProperty, Zone
from .state import GameState

HAND_SIZE_LIMIT = 6


@dataclass
class ChainLink:
    """One activated effect waiting on the Chain (resolved last-in-first-out)."""

    source_iid: int
    effect: object  # an Effect
    controller: int
    targets: tuple[int, ...] = ()
    event: dict | None = None


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
class ActivateSpell(Action):
    """Activate a Spell/Trap (from hand or a Set card); may carry chosen targets."""

    iid: int
    targets: tuple[int, ...] = ()
    zone_index: int | None = None


@dataclass(frozen=True)
class SetSpellTrap(Action):
    """Set a Spell/Trap face-down in a Spell & Trap Zone."""

    iid: int
    zone_index: int | None = None


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

    # Spell activations (Ignition/Quick from the hand) + Set Spell/Trap.
    # A Field Spell goes to the Field Zone, so it doesn't need an open S/T zone.
    has_st_zone = state.first_empty_spell_trap_zone(player) is not None
    for iid in p.hand:
        card = state.inst(iid).card
        if card.is_spell:
            effect = next(
                (e for e in card.effects if e.timing in ("ignition", "quick")), None
            )
            if effect is not None and (
                effect.condition is None or effect.condition(state, player)
            ):
                is_field = card.subtype is SpellTrapProperty.FIELD
                if is_field or has_st_zone:
                    for target_set in _enumerate_targets(state, player, effect.target):
                        actions.append(ActivateSpell(iid, targets=target_set))
        if (card.is_spell or card.is_trap) and has_st_zone:
            actions.append(SetSpellTrap(iid))

    # Activate a Set card already on the field whose effect you may start at will
    # on your own turn (e.g. the Continuous Trap Call of the Haunted). Purely
    # reactive Traps (Mirror Force, Trap Hole) have no "ignition" effect and are
    # offered only in a response window instead.
    for iid in p.spell_trap_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if inst.position is not Position.FACE_DOWN:
            continue
        if inst.set_on_turn is None or inst.set_on_turn >= state.turn_count:
            continue  # can't activate the turn it was Set
        effect = next((e for e in inst.card.effects if e.timing == "ignition"), None)
        if effect is None or (effect.condition is not None and not effect.condition(state, player)):
            continue
        for target_set in _enumerate_targets(state, player, effect.target):
            actions.append(ActivateSpell(iid, targets=target_set))

    return actions


def _enumerate_targets(state: GameState, controller: int, spec) -> list[tuple[int, ...]]:
    """List the legal target sets for an effect (``[()]`` means 'no target')."""
    if spec is None:
        return [()]
    opp = state.opponent_of(controller)
    if spec.where == "opponent_monsters":
        candidates = [i for i in state.players[opp].monster_zones if i is not None]
    elif spec.where == "any_monster":
        candidates = [
            i for pl in (0, 1) for i in state.players[pl].monster_zones if i is not None
        ]
    elif spec.where == "spell_trap_field":
        candidates = _spell_trap_field(state)
    elif spec.where == "any_graveyard_monster":
        candidates = _graveyard_monsters(state, (0, 1))
    elif spec.where == "own_graveyard_monster":
        candidates = _graveyard_monsters(state, (controller,))
    else:
        candidates = []
    if spec.count == 1:
        return [(c,) for c in candidates]
    return [tuple(combo) for combo in combinations(candidates, spec.count)]


def _graveyard_monsters(state: GameState, players: tuple[int, ...]) -> list[int]:
    """Monster iids sitting in the given players' Graveyards (a target pool)."""
    return [
        i
        for pl in players
        for i in state.players[pl].graveyard
        if state.inst(i).card.is_monster
    ]


def target_candidates(state: GameState, controller: int, spec) -> list[int]:
    """Flat list of individual iids an effect controlled by ``controller`` may target."""
    if spec is None:
        return []
    opp = state.opponent_of(controller)
    if spec.where == "opponent_monsters":
        return [i for i in state.players[opp].monster_zones if i is not None]
    if spec.where == "any_monster":
        return [i for pl in (0, 1) for i in state.players[pl].monster_zones if i is not None]
    if spec.where == "spell_trap_field":
        return _spell_trap_field(state)
    if spec.where == "any_graveyard_monster":
        return _graveyard_monsters(state, (0, 1))
    if spec.where == "own_graveyard_monster":
        return _graveyard_monsters(state, (controller,))
    return []


def _spell_trap_field(state: GameState) -> list[int]:
    """Every Spell/Trap on the field, both players' — including Field Spells
    (so Mystical Space Typhoon can destroy a Field Spell too)."""
    out: list[int] = []
    for pl in (0, 1):
        out += [i for i in state.players[pl].spell_trap_zones if i is not None]
        if state.players[pl].field_zone is not None:
            out.append(state.players[pl].field_zone)
    return out


# --------------------------------------------------------------------------- #
#  Chain responses — what a player may activate in a response window
# --------------------------------------------------------------------------- #
def response_options(
    state: GameState, player: int, event: dict | None, last_speed: int
) -> list[ActivateSpell]:
    """Cards ``player`` may activate right now (speed >= last_speed)."""
    options: list[ActivateSpell] = []

    # Set Spell/Traps on the field, set on an earlier turn.
    for iid in state.players[player].spell_trap_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if inst.position is not Position.FACE_DOWN:
            continue
        if inst.set_on_turn is None or inst.set_on_turn >= state.turn_count:
            continue
        effect = inst.card.effects[0] if inst.card.effects else None
        if effect is None or effect.speed < last_speed:
            continue
        options += _activations_for_effect(state, player, iid, effect, event)

    # Quick-Play spells straight from the hand (only on your own turn).
    if state.turn_player == player and state.first_empty_spell_trap_zone(player) is not None:
        for iid in state.players[player].hand:
            card = state.inst(iid).card
            effect = card.effects[0] if card.effects else None
            if not card.is_spell or effect is None or effect.timing != "quick":
                continue
            if effect.speed < last_speed:
                continue
            options += _activations_for_effect(state, player, iid, effect, event)

    return options


def _activations_for_effect(state, player, iid, effect, event):
    if effect.timing == "trigger":
        if event is None or not _trigger_matches(state, player, effect.trigger, event):
            return []
        return [ActivateSpell(iid, targets=_trigger_targets(effect.trigger, event))]
    if effect.timing == "quick":
        if effect.condition is not None and not effect.condition(state, player):
            return []
        return [ActivateSpell(iid, targets=t) for t in _enumerate_targets(state, player, effect.target)]
    return []


def _trigger_matches(state, player, trigger, event) -> bool:
    if trigger is None or trigger.kind != event.get("kind"):
        return False
    if trigger.by == OPPONENT and event.get("player") != state.opponent_of(player):
        return False
    if trigger.min_atk is not None:
        mon = event.get("monster")
        if mon is None or (state.inst(mon).card.attack or 0) < trigger.min_atk:
            return False
    return True


def _trigger_targets(trigger, event) -> tuple[int, ...]:
    if trigger.subject == "monster" and event.get("monster") is not None:
        return (event["monster"],)
    if trigger.subject == "attacker" and event.get("attacker") is not None:
        return (event["attacker"],)
    return ()


def _attacks_locked_out(state: GameState, player: int) -> bool:
    """The Dark Door: with a one-attack-per-Battle-Phase restriction face-up, a
    player who has already declared an attack this turn can't declare another."""
    locked = any(
        isinstance(mod, AttackRestriction) and mod.one_per_battle_phase
        for mod, _ in state.active_passives()
    )
    if not locked:
        return False
    return any(
        state.inst(i).attacked_this_turn
        for i in state.players[player].monster_zones
        if i is not None
    )


def _atk_attack_floor(state: GameState) -> int | None:
    """Messenger of Peace: the (effective) ATK at or above which a monster cannot
    declare an attack — the lowest such threshold among face-up restrictions, or
    None if no such lock is active."""
    floors = [
        mod.min_atk_cannot_attack
        for mod, _ in state.active_passives()
        if isinstance(mod, AttackRestriction) and mod.min_atk_cannot_attack is not None
    ]
    return min(floors) if floors else None


def _battle_phase_actions(state: GameState, player: int) -> list[Action]:
    if _attacks_locked_out(state, player):
        return []
    atk_floor = _atk_attack_floor(state)
    opp = state.opponent_of(player)
    opp_monsters = [m for m in state.players[opp].monster_zones if m is not None]
    actions: list[Action] = []
    for iid in state.players[player].monster_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if inst.position is not Position.FACE_UP_ATTACK or inst.attacked_this_turn:
            continue
        if atk_floor is not None and state.effective_attack(iid) >= atk_floor:
            continue  # Messenger of Peace: too strong to declare an attack
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
    if isinstance(action, ActivateSpell):
        return _activate_spell(state, action)
    if isinstance(action, SetSpellTrap):
        return _set_spell_trap(state, action)
    if isinstance(action, DiscardCard):
        name = state.inst(action.iid).name
        state.send_to_graveyard(action.iid)
        return f"discards {name}"
    raise ValueError(f"cannot apply action: {action!r}")


def place_activated_spell(state: GameState, iid: int, zone_index: int | None = None) -> None:
    """Put an activated Spell face-up in a Spell/Trap zone (it is now 'on the chain')."""
    inst = state.inst(iid)
    player = inst.controller
    if zone_index is None or state.players[player].spell_trap_zones[zone_index] is not None:
        zone_index = state.first_empty_spell_trap_zone(player)
    state.place_spell_trap(iid, player, zone_index, Position.FACE_UP_ATTACK)


def reveal_for_activation(state: GameState, iid: int, zone_index: int | None = None) -> None:
    """Make a card visible as it activates: place a hand card, or flip a Set card up.

    A Field Spell from the hand goes to the Field Zone (replacing the one there).
    """
    inst = state.inst(iid)
    if inst.zone is Zone.HAND:
        if inst.card.subtype is SpellTrapProperty.FIELD:
            state.place_field_spell(iid, inst.owner, Position.FACE_UP_ATTACK)
        else:
            place_activated_spell(state, iid, zone_index)
    else:  # already on the field (Set in the Spell/Trap or Field zone) -> flip up
        inst.position = Position.FACE_UP_ATTACK


def resolve_effect(
    state: GameState,
    effect,
    source_iid: int,
    targets: tuple[int, ...] = (),
    event: dict | None = None,
) -> None:
    """Run the primitives of a single effect."""
    inst = state.inst(source_iid)
    ctx = EffectContext(
        state=state,
        controller=inst.controller,
        source_iid=source_iid,
        targets=list(targets),
        event=event,
    )
    for primitive in effect.resolve:
        primitive.execute(ctx)


def resolve_card_effects(
    state: GameState, source_iid: int, targets: tuple[int, ...] = ()
) -> None:
    """Run every effect on the card at ``source_iid`` (used by the atomic path)."""
    for effect in state.inst(source_iid).card.effects:
        resolve_effect(state, effect, source_iid, targets)


def _set_spell_trap(state: GameState, action: SetSpellTrap) -> str:
    inst = state.inst(action.iid)
    player = inst.controller
    zone_index = action.zone_index
    if zone_index is None or state.players[player].spell_trap_zones[zone_index] is not None:
        zone_index = state.first_empty_spell_trap_zone(player)
    state.place_spell_trap(action.iid, player, zone_index, Position.FACE_DOWN)
    inst.set_on_turn = state.turn_count
    return "Sets a card"


def _activate_spell(state: GameState, action: ActivateSpell) -> str:
    """Atomically activate a Normal Spell: place, resolve, send to GY.

    Used headless (CLI/tests). The interactive engine runs these three steps with
    pauses in between so the activation is watchable; both share the helpers above.
    """
    card = state.inst(action.iid).card
    reveal_for_activation(state, action.iid, action.zone_index)  # routes Field Spells too
    resolve_card_effects(state, action.iid, action.targets)
    # A Normal Spell heads to the Graveyard; a permanent one (Equip/Continuous/Field) stays.
    inst = state.inst(action.iid)
    if inst.zone is Zone.SPELL_TRAP and not card.is_permanent:
        state.send_to_graveyard(action.iid)
    return f"activates {card.name}"


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
    atk = state.effective_attack(action.attacker)

    if action.target is None:
        state.players[opp].life_points -= atk
        return f"{attacker.name} attacks directly — {atk} damage"

    target = state.inst(action.target)
    prefix = ""
    if target.position is Position.FACE_DOWN_DEFENSE:
        target.position = Position.FACE_UP_DEFENSE
        prefix = f"(flips up {target.name}) "

    if target.position is Position.FACE_UP_ATTACK:
        other = state.effective_attack(action.target)
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
    dfn = state.effective_defense(action.target)
    if atk > dfn:
        state.send_to_graveyard(target.iid)
        return f"{prefix}{attacker.name} ({atk}) destroys defending {target.name} (DEF {dfn})"
    if atk < dfn:
        state.players[me].life_points -= dfn - atk
        return f"{prefix}{attacker.name} ({atk}) bounces off {target.name} (DEF {dfn}) — {dfn - atk} damage to attacker"
    return f"{prefix}{attacker.name} ({atk}) cannot break {target.name} (DEF {dfn})"
