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

from .effects import OPPONENT, AttackRestriction, EffectContext, card_matches_traits
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
    # Set True by a Counter-Trap negation (Magic Jammer): this link's effect is
    # skipped when the Chain resolves.
    negated: bool = False


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
class SpecialSummonFromHand(Action):
    """Special Summon a monster from the hand using its own built-in ability
    (its ``CardDef.hand_summon``) — e.g. Cyber Dragon. Unlike a Normal Summon it
    does *not* consume the turn's Normal Summon; the board condition is checked at
    enumeration time."""

    iid: int
    zone_index: int | None = None


@dataclass(frozen=True)
class GeminiSummon(Action):
    """A 2nd Normal Summon on a face-up Gemini monster you already control, to
    treat it as an Effect Monster (it stays in its zone/position). Uses up your
    one Normal Summon for the turn."""

    iid: int


@dataclass(frozen=True)
class UnionEquip(Action):
    """Equip a face-up Union monster you control to a valid host (once per turn).
    The Union leaves the Monster Zone and attaches to the host as an Equip Card."""

    union_iid: int
    host_iid: int


@dataclass(frozen=True)
class UnionUnequip(Action):
    """Unequip a Union monster and Special Summon it back in face-up Attack
    Position (once per turn)."""

    union_iid: int


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
class ActivateMonsterEffect(Action):
    """Activate a face-up monster's Ignition effect (e.g. Royal Magical Library
    removes 3 Spell Counters to draw); may carry chosen targets."""

    iid: int
    targets: tuple[int, ...] = ()


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
def controls_toon_world(state: GameState, player: int) -> bool:
    """Whether ``player`` has a face-up "Toon World" — the enabler a Toon monster
    needs to be Summoned and to remain on the field."""
    return any(
        sid is not None
        and state.inst(sid).card.name == "Toon World"
        and state.inst(sid).is_face_up
        for sid in state.players[player].spell_trap_zones
    )


def tributes_required(level: int | None) -> int:
    """Level 1-4 -> 0, Level 5-6 -> 1, Level 7+ -> 2."""
    lvl = level or 0
    if lvl <= 4:
        return 0
    return 1 if lvl <= 6 else 2


# --------------------------------------------------------------------------- #
#  Activation costs (paid from the hand at activation)
# --------------------------------------------------------------------------- #
def _pick(fodder: list[int], count: int, chosen) -> list[int]:
    """The fodder actually paid for a cost: the player's valid picks (capped at
    ``count``), else the first ``count`` eligible (the deterministic headless default)."""
    return [i for i in (chosen or []) if i in fodder][:count] or fodder[:count]


def discard_fodder(state: GameState, controller: int, source_iid: int) -> list[int]:
    """Hand cards the controller may discard to pay a cost — every card except the
    one being activated (a Spell from hand can't discard itself as its own cost)."""
    return [i for i in state.players[controller].hand if i != source_iid]


def tribute_fodder(state: GameState, controller: int, races=frozenset(), attrs=frozenset()) -> list[int]:
    """Monsters ``controller`` may Tribute to pay a cost — those they control,
    narrowed by an optional race / attribute restriction (Spiritual Fire Art needs
    a FIRE monster, Icarus Attack a Winged Beast). Face-down monsters qualify too
    (you know your own Set monster's stats)."""
    out: list[int] = []
    for iid in state.players[controller].monster_zones:
        if iid is None:
            continue
        card = state.inst(iid).card
        if races and card.race not in races:
            continue
        if attrs and card.attribute not in attrs:
            continue
        out.append(iid)
    return out


def send_to_gy_fodder(
    state: GameState, controller: int, source_iid: int, card_filter=None, face_up=False, exclude_self=False
) -> list[int]:
    """Cards ``controller`` controls that may be sent from the field to the GY to pay
    a cost — monsters, Spell/Traps and the Field Spell — narrowed by an optional
    printed-card ``card_filter`` (a CardFilter), a ``face_up`` requirement, and an
    ``exclude_self`` flag (Daedalus sends a face-up "Umi"; Ultimate Baseball Kid
    sends another face-up FIRE monster)."""
    pl = state.players[controller]
    out: list[int] = []
    for iid in list(pl.monster_zones) + list(pl.spell_trap_zones) + [pl.field_zone]:
        if iid is None or (exclude_self and iid == source_iid):
            continue
        inst = state.inst(iid)
        if face_up and not inst.is_face_up:
            continue
        if card_filter is not None and not card_filter.matches(inst.card):
            continue
        out.append(iid)
    return out


def pay_send_to_gy_cost(
    state: GameState,
    controller: int,
    source_iid: int,
    count: int,
    card_filter=None,
    face_up=False,
    exclude_self=False,
    chosen=None,
) -> list[int]:
    """Send ``count`` of ``controller``'s eligible field cards to the GY as a cost.
    ``chosen`` names them (player's pick); without it the first eligible are taken."""
    fodder = send_to_gy_fodder(state, controller, source_iid, card_filter, face_up, exclude_self)
    picks = _pick(fodder, count, chosen)
    for iid in picks:
        state.send_to_graveyard(iid)
    return picks


def pay_discard_cost(
    state: GameState, controller: int, source_iid: int, count: int, chosen=None
) -> list[int]:
    """Discard ``count`` cards from ``controller``'s hand as a cost. ``chosen`` names
    the cards (player's pick); without it, the first eligible cards are taken (the
    deterministic headless default). Returns the discarded iids."""
    fodder = discard_fodder(state, controller, source_iid)
    picks = _pick(fodder, count, chosen)
    for iid in picks:
        state.send_to_graveyard(iid)
    return picks


def banish_from_gy_fodder(state: GameState, controller: int, card_filter=None, exclude=()) -> list[int]:
    """Monsters in ``controller``'s Graveyard that may be banished to pay a cost,
    narrowed by an optional printed-card ``card_filter`` and excluding any iids in
    ``exclude`` (the effect's own targets, so cost and target stay disjoint)."""
    out: list[int] = []
    for iid in state.players[controller].graveyard:
        if iid in exclude:
            continue
        card = state.inst(iid).card
        if not card.is_monster:
            continue
        if card_filter is not None and not card_filter.matches(card):
            continue
        out.append(iid)
    return out


def pay_banish_from_gy_cost(
    state: GameState, controller: int, count: int, card_filter=None, chosen=None, exclude=()
) -> list[int]:
    """Banish ``count`` of ``controller``'s eligible Graveyard monsters as a cost.
    ``chosen`` names them (player's pick); without it the first eligible are taken."""
    fodder = banish_from_gy_fodder(state, controller, card_filter, exclude)
    picks = _pick(fodder, count, chosen)
    for iid in picks:
        state.banish(iid)
    return picks


def pay_counter_cost(state: GameState, source_iid: int, count: int, ctype: str = "spell") -> None:
    """Remove ``count`` counters of ``ctype`` from the source card as a cost (Royal
    Magical Library)."""
    counters = state.inst(source_iid).counters
    counters[ctype] = max(0, counters.get(ctype, 0) - count)


def pay_tribute_cost(
    state: GameState,
    controller: int,
    source_iid: int,
    count: int,
    races=frozenset(),
    attrs=frozenset(),
    chosen=None,
) -> list[int]:
    """Tribute ``count`` of ``controller``'s monsters as a cost. ``chosen`` names the
    monsters (player's pick); without it, the first eligible ones are taken. The
    picks are recorded on the source card (``tributed_iids``) before they go to the
    Graveyard, so the payload can read their printed stats. Returns the iids."""
    fodder = tribute_fodder(state, controller, races, attrs)
    picks = _pick(fodder, count, chosen)
    state.inst(source_iid).tributed_iids = list(picks)
    for iid in picks:
        state.send_to_graveyard(iid)
    return picks


# A uniform table over the three "pick N cards from a fodder pool" activation costs.
# Each entry: (kind, Effect amount-field, fodder fn, pay fn, log-verb template). The
# counter cost is handled separately (it removes counters, not chosen cards). The
# lambdas read the per-cost knobs (races/filter/...) straight off the Effect, so
# ``can_pay_costs`` and ``pay_costs`` can iterate one list instead of four branches.
_FODDER_COSTS = (
    (
        "discard",
        "discard_cost",
        lambda st, c, src, e: discard_fodder(st, c, src),
        lambda st, c, src, n, ch, e: pay_discard_cost(st, c, src, n, ch),
        "discards {names}",
    ),
    (
        "tribute",
        "tribute_cost",
        lambda st, c, src, e: tribute_fodder(st, c, e.tribute_races, e.tribute_attributes),
        lambda st, c, src, n, ch, e: pay_tribute_cost(
            st, c, src, n, e.tribute_races, e.tribute_attributes, ch
        ),
        "Tributes {names}",
    ),
    (
        "send",
        "send_to_gy_cost",
        lambda st, c, src, e: send_to_gy_fodder(
            st, c, src, e.send_to_gy_filter, e.send_to_gy_face_up, e.send_to_gy_exclude_self
        ),
        lambda st, c, src, n, ch, e: pay_send_to_gy_cost(
            st, c, src, n, e.send_to_gy_filter, e.send_to_gy_face_up, e.send_to_gy_exclude_self, ch
        ),
        "sends {names} to the GY",
    ),
)


def can_pay_costs(state: GameState, controller: int, source_iid: int, effect) -> bool:
    """Whether ``controller`` can pay ``effect``'s activation cost right now (gates
    legal enumeration). Covers the discard / Tribute / send-to-GY fodder costs and
    the counter cost."""
    for _kind, amount_attr, fodder_fn, _pay, _verb in _FODDER_COSTS:
        n = getattr(effect, amount_attr)
        if n and len(fodder_fn(state, controller, source_iid, effect)) < n:
            return False
    if effect.counter_cost and (
        state.inst(source_iid).counters.get(effect.counter_type, 0) < effect.counter_cost
    ):
        return False
    if effect.life_cost and state.players[controller].life_points <= effect.life_cost:
        return False
    if effect.banish_from_gy_cost and (
        len(banish_from_gy_fodder(state, controller, effect.banish_from_gy_filter))
        < effect.banish_from_gy_cost
    ):
        return False
    return True


def pay_costs(
    state: GameState, controller: int, source_iid: int, effect, picker=None, targets=()
) -> list[str]:
    """Pay every activation cost on ``effect`` before it resolves. ``picker(kind,
    fodder, count) -> tuple[int, ...]`` lets the player choose the fodder; ``None``
    uses the deterministic default (first eligible). ``targets`` are the effect's
    chosen targets, excluded from the banish-from-GY fodder. Returns one
    human-readable log line per cost paid (the caller decides how to surface them)."""
    lines: list[str] = []
    for kind, amount_attr, fodder_fn, pay_fn, verb in _FODDER_COSTS:
        n = getattr(effect, amount_attr)
        if not n:
            continue
        fodder = fodder_fn(state, controller, source_iid, effect)
        # Snapshot names before paying: a Tributed/sent Token is removed from the game
        # (deleted from state.cards), so its name can't be looked up afterwards.
        names = {i: state.inst(i).name for i in fodder}
        chosen = picker(kind, fodder, n) if picker else None
        paid = pay_fn(state, controller, source_iid, n, chosen, effect)
        lines.append(verb.format(names=", ".join(names.get(i, "a card") for i in paid)))
    if effect.counter_cost:
        pay_counter_cost(state, source_iid, effect.counter_cost, effect.counter_type)
        lines.append(f"removes {effect.counter_cost} {effect.counter_type} counter(s)")
    if effect.life_cost:
        state.players[controller].life_points -= effect.life_cost
        lines.append(f"pays {effect.life_cost} LP")
    if effect.banish_from_gy_cost:
        n = effect.banish_from_gy_cost
        fodder = banish_from_gy_fodder(state, controller, effect.banish_from_gy_filter, tuple(targets))
        chosen = picker("banish_from_gy", fodder, n) if picker else None
        paid = pay_banish_from_gy_cost(
            state, controller, n, effect.banish_from_gy_filter, chosen, tuple(targets)
        )
        lines.append(f"banishes {', '.join(state.inst(i).name for i in paid)} from the GY")
    return lines


def _has_activation_cost(effect) -> bool:
    """Whether ``effect`` carries any activation cost at all (the headless activate
    path pays the first effect that does)."""
    return bool(
        effect.discard_cost
        or effect.tribute_cost
        or effect.send_to_gy_cost
        or effect.counter_cost
        or effect.life_cost
        or effect.banish_from_gy_cost
    )


def _off_cooldown(inst, effect, turn: int) -> bool:
    """Whether a "once per turn" Ignition effect is available — i.e. the source card
    hasn't already used it this turn (always True for effects with no such limit)."""
    return not (effect.once_per_turn and inst.effect_activated_on_turn == turn)


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
            if card.is_toon and not controls_toon_world(state, player):
                continue  # a Toon monster needs your Toon World face-up to be Summoned
            can_set = not state.action_locked("set", player)  # Searchlightman bars Setting
            need = tributes_required(card.level)
            if need == 0:
                if has_empty:
                    actions.append(NormalSummon(iid))
                    if can_set:
                        actions.append(SetMonster(iid))
            elif len(controlled) >= need:
                # tributing frees the zone(s), so no pre-existing empty slot needed
                for combo in combinations(controlled, need):
                    actions.append(NormalSummon(iid, tributes=combo))
                    if can_set:
                        actions.append(SetMonster(iid, tributes=combo))

        # Gemini Summon: spend your Normal Summon to unlock a face-up Gemini you
        # already control (it doesn't move). Treated as a Normal Summon, so it's
        # also gated by the once-per-turn limit above.
        for iid in p.monster_zones:
            if iid is None:
                continue
            inst = state.inst(iid)
            if inst.card.is_gemini and inst.is_face_up and not inst.gemini_unlocked:
                actions.append(GeminiSummon(iid))

    # Special Summon from the hand via a monster's own ability (Cyber Dragon, The
    # Fiend Megacyber, ...). Independent of the Normal Summon; gated by the card's
    # board condition and needing a free Monster Zone.
    if state.first_empty_monster_zone(player) is not None:
        for iid in p.hand:
            rule = state.inst(iid).card.hand_summon
            if rule is None:
                continue
            if rule.condition is not None and not rule.condition(state, player):
                continue
            if state.special_summon_locked(player, state.inst(iid).card):
                continue  # a Barrier Statue / Vanity lock bars this Special Summon
            if _summon_banish_choice(state, player, rule) is None:
                continue  # the banish cost (Chaos: 1 LIGHT + 1 DARK) can't be paid
            actions.append(SpecialSummonFromHand(iid))

    # battle-position changes (not on the turn a monster was summoned/already changed)
    for iid in p.monster_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if inst.summoned_this_turn or inst.position_changed_this_turn:
            continue
        if inst.position_locked_until is not None and state.turn_count <= inst.position_locked_until:
            continue  # Goblin Attack Force: frozen in Defense until its next turn
        if inst.position is Position.FACE_DOWN_DEFENSE:
            actions.append(FlipSummon(iid))
        elif inst.position in (Position.FACE_UP_ATTACK, Position.FACE_UP_DEFENSE):
            actions.append(ChangePosition(iid))

    # Union: once per turn, a face-up Union you control may equip itself to a valid
    # host (needs a free Spell/Trap zone — our simplification: an equipped Union
    # occupies one), and an equipped Union may unequip back (needs a free Monster
    # Zone). Each is gated by the Union's own once-per-turn stamp.
    union_st_free = state.first_empty_spell_trap_zone(player) is not None
    union_mon_free = state.first_empty_monster_zone(player) is not None
    for iid in p.monster_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if not inst.card.is_union or not inst.is_face_up:
            continue
        if inst.union_acted_on_turn == state.turn_count or not union_st_free:
            continue
        actions.extend(UnionEquip(iid, host) for host in union_hosts(state, player, iid))
    for iid in p.spell_trap_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if not (inst.card.is_union and inst.equipped_to is not None):
            continue
        if inst.union_acted_on_turn == state.turn_count or not union_mon_free:
            continue
        if state.special_summon_locked(player, inst.card):
            continue  # unequipping is a Special Summon — barred under a lock
        actions.append(UnionUnequip(iid))

    # Spell activations (Ignition/Quick from the hand) + Set Spell/Trap.
    # A Field Spell goes to the Field Zone, so it doesn't need an open S/T zone.
    has_st_zone = state.first_empty_spell_trap_zone(player) is not None
    for iid in p.hand:
        card = state.inst(iid).card
        if card.is_spell:
            effect = next(
                (e for e in card.effects if e.timing in ("ignition", "quick", "fusion", "ritual")),
                None,
            )
            if (
                effect is not None
                and (effect.condition is None or effect.condition(state, player))
                and can_pay_costs(state, player, iid, effect)
                and not state.cannot_activate_card(iid)  # Spell Canceller bars Spells
            ):
                is_field = card.subtype is SpellTrapProperty.FIELD
                if is_field or has_st_zone:
                    for target_set in _enumerate_targets(state, player, effect.target):
                        actions.append(ActivateSpell(iid, targets=target_set))
        if (card.is_spell or card.is_trap) and has_st_zone and not state.action_locked("set", player):
            actions.append(SetSpellTrap(iid))  # Searchlightman bars Setting

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
        # Ignition Spell/Traps and Set Quick-Play Spells may be started at will on your
        # own turn; purely reactive Traps (timing="trigger") wait for a response window.
        effect = next((e for e in inst.card.effects if e.timing in ("ignition", "quick")), None)
        if effect is None or (effect.condition is not None and not effect.condition(state, player)):
            continue
        if not can_pay_costs(state, player, iid, effect) or not _off_cooldown(inst, effect, state.turn_count):
            continue
        if state.cannot_activate_card(iid):  # Jinzo bars Traps, Spell Canceller bars Spells
            continue
        for target_set in _enumerate_targets(state, player, effect.target):
            actions.append(ActivateSpell(iid, targets=target_set))

    # Monster Ignition effects: a face-up monster you control with an "ignition"
    # effect you may start at will (Royal Magical Library: remove 3 Spell Counters
    # to draw). Gated by its condition and any activation cost (e.g. counters).
    for iid in p.monster_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if not inst.is_face_up or not inst.effects_active:
            continue
        effect = next((e for e in inst.card.effects if e.timing == "ignition"), None)
        if effect is None or (effect.condition is not None and not effect.condition(state, player)):
            continue
        if not can_pay_costs(state, player, iid, effect) or not _off_cooldown(inst, effect, state.turn_count):
            continue
        for target_set in _enumerate_targets(state, player, effect.target):
            actions.append(ActivateMonsterEffect(iid, targets=target_set))

    return actions


def _filter_targets(state: GameState, iids: list[int], spec) -> list[int]:
    """Narrow a candidate pool to ``spec``'s restrictions — race / attribute (an
    Equip only on a Spellcaster), card_kind (a Spell/Trap/Field target), exact name
    or archetype substring, face-up, or Defense Position. No restriction -> unchanged."""
    if spec is None or not (
        spec.races
        or spec.attributes
        or spec.face_up
        or spec.face_down
        or spec.defense_position
        or spec.attack_position
        or spec.card_kind
        or spec.names
        or spec.name_contains
        or spec.max_atk is not None
        or spec.min_level is not None
        or spec.max_level is not None
        or spec.normal_only
    ):
        return iids
    out: list[int] = []
    for i in iids:
        inst = state.inst(i)
        card = inst.card
        if not card_matches_traits(
            card,
            names=spec.names,
            name_contains=spec.name_contains,
            races=spec.races,
            attributes=spec.attributes,
            max_atk=spec.max_atk,
            min_level=spec.min_level,
            max_level=spec.max_level,
        ):
            continue
        if spec.normal_only and not card.is_vanilla:
            continue
        if spec.face_up and not inst.is_face_up:
            continue
        if spec.face_down and inst.is_face_up:
            continue
        if spec.defense_position and inst.position not in (
            Position.FACE_UP_DEFENSE,
            Position.FACE_DOWN_DEFENSE,
        ):
            continue
        if spec.attack_position and inst.position is not Position.FACE_UP_ATTACK:
            continue
        if spec.card_kind and not _kind_matches(card, spec.card_kind):
            continue
        out.append(i)
    return out


def _kind_matches(card, kind: str) -> bool:
    """Whether a Spell/Trap (or Field Spell) target matches a ``card_kind`` filter."""
    if kind == "spell":
        return card.is_spell
    if kind == "trap":
        return card.is_trap
    if kind == "field_spell":
        return card.is_spell and card.subtype is SpellTrapProperty.FIELD
    return True


def _target_pool(state: GameState, controller: int, spec) -> list[int]:
    """The filtered iids a ``spec`` may target — the ``where``->pool dispatch shared
    by ``target_candidates`` and ``_enumerate_targets``. Returns [] for no spec."""
    if spec is None:
        return []
    opp = state.opponent_of(controller)
    if spec.where == "opponent_monsters":
        candidates = [i for i in state.players[opp].monster_zones if i is not None]
    elif spec.where == "own_monsters":
        candidates = [i for i in state.players[controller].monster_zones if i is not None]
    elif spec.where == "any_monster":
        candidates = [i for pl in (0, 1) for i in state.players[pl].monster_zones if i is not None]
    elif spec.where == "spell_trap_field":
        candidates = _spell_trap_field(state)
    elif spec.where == "any_card_field":
        candidates = _all_field_cards(state)
    elif spec.where == "opponent_card_field":
        candidates = _opponent_field_cards(state, controller)
    elif spec.where == "opponent_spell_trap":
        candidates = state.field_cards(opp, monsters=False)  # opponent's S/T + Field Spell
    elif spec.where == "any_graveyard_monster":
        candidates = _graveyard_monsters(state, (0, 1))
    elif spec.where == "own_graveyard_monster":
        candidates = _graveyard_monsters(state, (controller,))
    elif spec.where == "opponent_graveyard_monster":
        candidates = _graveyard_monsters(state, (opp,))
    else:
        candidates = []
    return _filter_targets(state, candidates, spec)


def _enumerate_targets(state: GameState, controller: int, spec) -> list[tuple[int, ...]]:
    """List the legal target sets for an effect (``[()]`` means 'no target')."""
    if spec is None:
        return [()]
    candidates = _target_pool(state, controller, spec)
    if spec.up_to:
        # "up to N": every non-empty subset of size 1..min(N, available).
        sets: list[tuple[int, ...]] = []
        for n in range(1, min(spec.count, len(candidates)) + 1):
            sets += [tuple(combo) for combo in combinations(candidates, n)]
        return sets
    if spec.count == 1:
        return [(c,) for c in candidates]
    return [tuple(combo) for combo in combinations(candidates, spec.count)]


def makeable_fusions(state: GameState, controller: int) -> list[tuple[int, list[int]]]:
    """List ``(fusion_iid, material_iids)`` the controller can Fusion Summon now.

    A Fusion Monster in their Extra Deck qualifies when its named materials (from
    the FUSIONS recipe book) are all present among the monsters in their hand and
    Monster Zones, and they have a free Monster Zone to summon it into.
    """
    from .card_effects import FUSIONS

    p = state.players[controller]
    free = sum(1 for i in p.monster_zones if i is None)
    field = [i for i in p.monster_zones if i is not None]
    pool = [i for i in p.hand if state.inst(i).card.is_monster] + field
    out: list[tuple[int, list[int]]] = []
    for fid in p.extra_deck:
        recipe = FUSIONS.get(state.inst(fid).card.name)
        if not recipe:
            continue
        materials = _match_materials(state, recipe, pool)
        if materials is None:
            continue
        # A zone will be open after the field materials leave (so a full field of
        # exactly the materials is still a legal Fusion).
        on_field = sum(1 for m in materials if m in field)
        if free + on_field >= 1:
            out.append((fid, materials))
    return out


def _match_materials(state: GameState, recipe: tuple[str, ...], pool: list[int]) -> list[int] | None:
    """Assign each required material name to a distinct pool card (no reuse), or
    None if the pool can't satisfy the recipe."""
    remaining = list(pool)
    chosen: list[int] = []
    for name in recipe:
        match = next((i for i in remaining if state.inst(i).card.name == name), None)
        if match is None:
            return None
        remaining.remove(match)
        chosen.append(match)
    return chosen


def ritual_monster_in_hand(state: GameState, controller: int, monster_name: str) -> int | None:
    """The iid of ``monster_name`` in the controller's hand, if present."""
    return next(
        (i for i in state.players[controller].hand if state.inst(i).card.name == monster_name),
        None,
    )


def ritual_tribute_pool(state: GameState, controller: int, exclude_iid: int) -> list[int]:
    """Monsters the controller may Tribute for a Ritual Summon: any monster in
    their Monster Zones, plus levelled monsters in hand (minus the Ritual Monster)."""
    p = state.players[controller]
    pool = [i for i in p.monster_zones if i is not None]
    pool += [
        i
        for i in p.hand
        if i != exclude_iid and state.inst(i).card.is_monster and (state.inst(i).card.level or 0) > 0
    ]
    return pool


def can_ritual_summon(state: GameState, controller: int, monster_name: str) -> bool:
    """Whether the controller could Ritual Summon ``monster_name`` right now: it's
    in hand, the Tribute pool's Levels can reach its Level, and a Monster Zone will
    be open after the Tributes leave."""
    iid = ritual_monster_in_hand(state, controller, monster_name)
    if iid is None:
        return False
    required = state.inst(iid).card.level or 0
    pool = ritual_tribute_pool(state, controller, iid)
    if sum(state.inst(m).card.level or 0 for m in pool) < required:
        return False
    free = sum(1 for i in state.players[controller].monster_zones if i is None)
    on_field = sum(1 for m in pool if state.inst(m).zone is Zone.MONSTER)
    return free + on_field >= 1  # a field Tribute (or an existing gap) opens the slot


def _union_descriptor(state: GameState, union_iid: int):
    """The Union monster's UnionMod (host restriction), or None if it isn't one."""
    from .effects import UnionMod

    return next(
        (m for m in state.inst(union_iid).card.continuous if isinstance(m, UnionMod)),
        None,
    )


def _host_carries_union(state: GameState, controller: int, host_iid: int) -> bool:
    """True if the host already has a Union monster equipped (max one at a time)."""
    return any(
        sid is not None
        and state.inst(sid).card.is_union
        and state.inst(sid).equipped_to == host_iid
        for sid in state.players[controller].spell_trap_zones
    )


def union_hosts(state: GameState, controller: int, union_iid: int) -> list[int]:
    """Valid hosts a face-up Union you control may equip itself to: another face-up
    monster you control matching the Union's name/race restriction, not already
    carrying a Union."""
    mod = _union_descriptor(state, union_iid)
    if mod is None:
        return []
    hosts: list[int] = []
    for hid in state.players[controller].monster_zones:
        if hid is None or hid == union_iid:
            continue
        host = state.inst(hid)
        if not host.is_face_up:
            continue
        if mod.host_names and host.card.name not in mod.host_names:
            continue
        if mod.host_races and host.card.race not in mod.host_races:
            continue
        if _host_carries_union(state, controller, hid):
            continue
        hosts.append(hid)
    return hosts


def _graveyard_monsters(state: GameState, players: tuple[int, ...]) -> list[int]:
    """Monster iids sitting in the given players' Graveyards that may be Special
    Summoned (a revival target pool). Spirit monsters can never be Special Summoned,
    so they're excluded (Monster Reborn / Call of the Haunted can't bring them back)."""
    return [
        i
        for pl in players
        for i in state.players[pl].graveyard
        if state.inst(i).card.is_monster and not state.inst(i).card.is_spirit
    ]


def target_candidates(state: GameState, controller: int, spec) -> list[int]:
    """Flat list of individual iids an effect controlled by ``controller`` may target."""
    return _target_pool(state, controller, spec)


def _spell_trap_field(state: GameState) -> list[int]:
    """Every Spell/Trap on the field, both players' — including Field Spells
    (so Mystical Space Typhoon can destroy a Field Spell too)."""
    return state.field_cards(0, monsters=False) + state.field_cards(1, monsters=False)


def _all_field_cards(state: GameState) -> list[int]:
    """Every card on the field, both players' — monsters and Spells/Traps/Field
    alike (Raigeki Break targets 'any card on the field')."""
    return state.field_cards(0) + state.field_cards(1)


def _opponent_field_cards(state: GameState, controller: int) -> list[int]:
    """Every card the opponent controls — monsters, Spells/Traps, and Field Spell
    (Phoenix Wing Wind Blast / Spiritualism target 'a card your opponent controls')."""
    opp = state.opponent_of(controller)
    out = [i for i in state.players[opp].monster_zones if i is not None]
    out += [i for i in state.players[opp].spell_trap_zones if i is not None]
    if state.players[opp].field_zone is not None:
        out.append(state.players[opp].field_zone)
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
        if state.cannot_activate_card(iid):  # Jinzo bars Traps from a response window too
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
            if state.cannot_activate_card(iid):  # Spell Canceller bars Quick-Play Spells
                continue
            options += _activations_for_effect(state, player, iid, effect, event)

    return options


def _activations_for_effect(state, player, iid, effect, event):
    if effect.timing == "trigger":
        if event is None or not _trigger_matches(state, player, effect.trigger, event):
            return []
        if effect.condition is not None and not effect.condition(state, player):
            return []  # e.g. Radiant Mirror Force needs the attacker to control 3+ monsters
        if not can_pay_costs(state, player, iid, effect):
            return []  # e.g. Horn of Heaven needs a monster to Tribute
        if effect.target is not None:
            # The controller picks the effect's target (Call of the Earthbound chooses the
            # redirected monster), rather than it coming from the trigger's subject.
            sets = _enumerate_targets(state, player, effect.target)
            if effect.target.exclude_attacker and event is not None:
                atkr = event.get("attacker")
                sets = [t for t in sets if atkr not in t]  # Magical Arm Shield's "except"
            return [ActivateSpell(iid, targets=t) for t in sets]
        return [ActivateSpell(iid, targets=_trigger_targets(effect.trigger, event))]
    if effect.timing == "quick":
        if effect.condition is not None and not effect.condition(state, player):
            return []
        if not can_pay_costs(state, player, iid, effect):
            return []
        return [ActivateSpell(iid, targets=t) for t in _enumerate_targets(state, player, effect.target)]
    return []


def _trigger_matches(state, player, trigger, event) -> bool:
    if trigger is None or trigger.kind != event.get("kind"):
        return False
    if trigger.by == OPPONENT and event.get("player") != state.opponent_of(player):
        return False
    if trigger.summon_kinds and event.get("summon_kind") not in trigger.summon_kinds:
        return False  # e.g. Trap Hole ignores Special Summons
    if trigger.min_atk is not None:
        mon = event.get("monster")
        if mon is None or (state.inst(mon).card.attack or 0) < trigger.min_atk:
            return False
    if trigger.target_self_control and not _attack_target_matches(state, player, trigger, event):
        return False
    if trigger.attacker_was_tribute_summoned:
        atkr = event.get("attacker")
        if atkr is None or atkr not in state.cards or not state.inst(atkr).was_tribute_summoned:
            return False
    if trigger.battle_only and event.get("damage_kind") != "battle":
        return False  # Damage Condenser reacts only to battle damage, not effect damage
    return True


def _attack_target_matches(state, player, trigger, event) -> bool:
    """For "when a face-up monster you control is selected as an attack target" Traps
    (Mirage Tube, Froggy Forcefield, Justi-Break): the attack's target must be a face-up
    monster ``player`` controls, narrowed by the trigger's target_* constraints."""
    tgt = event.get("target")
    if tgt is None or tgt not in state.cards:
        return False  # a direct attack has no target monster
    inst = state.inst(tgt)
    if inst.controller != player or inst.zone is not Zone.MONSTER or not inst.is_face_up:
        return False
    card = inst.card
    if trigger.target_name_contains and not any(s in card.name for s in trigger.target_name_contains):
        return False
    if trigger.target_exclude_names and card.name in trigger.target_exclude_names:
        return False
    if trigger.target_normal_only and not card.is_vanilla:
        return False
    if trigger.target_max_level is not None and (card.level or 0) > trigger.target_max_level:
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


def _attack_floodgates(state: GameState, player: int) -> tuple[bool, int | None]:
    """Scan active ``AttackRestriction`` passives for ``player``'s declarations and
    return ``(blanket_blocked, level_cap)``: blanket_blocked = no attack may be declared
    at all (Swords of Revealing Light locks the source controller's opponent); level_cap
    = a monster whose Level is *above* it cannot attack (Gravity Bind, the lowest such
    cap among active locks). ``affects="opponent"`` is resolved against each lock's own
    source controller."""
    blanket = False
    caps: list[int] = []
    for mod, ctrl in state.active_passives():
        if not isinstance(mod, AttackRestriction):
            continue
        restricted_side = state.opponent_of(ctrl) if mod.affects == "opponent" else None
        if mod.all_cannot_attack and (restricted_side is None or player == restricted_side):
            blanket = True
        if mod.max_level_can_attack is not None and (
            restricted_side is None or player == restricted_side
        ):
            caps.append(mod.max_level_can_attack)
    return blanket, (min(caps) if caps else None)


def _toon_attack_targets(state: GameState, opp: int, opp_monsters: list[int]) -> list[int | None]:
    """A Toon may attack directly when the opponent controls no Toon monster; if
    they do, it must attack a Toon. (It may also attack normal monsters.)"""
    opp_toons = [m for m in opp_monsters if state.inst(m).card.is_toon]
    if opp_toons:
        return list(opp_toons)
    return [None, *opp_monsters]  # direct attack, or any opponent monster


def _battle_phase_actions(state: GameState, player: int) -> list[Action]:
    if _attacks_locked_out(state, player):
        return []
    blanket_locked, level_cap = _attack_floodgates(state, player)
    if blanket_locked:
        return []  # Swords of Revealing Light: this side cannot declare any attack
    atk_floor = _atk_attack_floor(state)
    opp = state.opponent_of(player)
    opp_monsters = [m for m in state.players[opp].monster_zones if m is not None]
    actions: list[Action] = []
    for iid in state.players[player].monster_zones:
        if iid is None:
            continue
        inst = state.inst(iid)
        if inst.position is not Position.FACE_UP_ATTACK:
            continue
        if inst.attacks_made_this_turn >= state.max_attacks(iid):
            continue  # used up its attack(s) this Battle Phase (2+ for a MultiAttacker)
        if inst.attack_disabled_on_turn == state.turn_count:
            continue  # an effect this turn barred this monster from attacking
        cost = state.attack_life_cost(iid)
        if cost and state.players[player].life_points <= cost:
            continue  # Dark Elf: cannot pay the LP cost required to declare an attack
        if atk_floor is not None and state.effective_attack(iid) >= atk_floor:
            continue  # Messenger of Peace: too strong to declare an attack
        if level_cap is not None and (inst.card.level or 0) > level_cap:
            continue  # Gravity Bind: too high a Level to declare an attack
        if inst.card.is_toon:
            if inst.summoned_this_turn:
                continue  # a Toon can't attack the turn it's Summoned
            targets = [
                t
                for t in _toon_attack_targets(state, opp, opp_monsters)
                if t is None or not state.is_protected_attack_target(t)
            ]
        elif opp_monsters:
            # A monster the opponent protects (Decoyroid/Marauding Captain decoys) is
            # removed from the target list, but it still occupies the board — so it does
            # not open up a direct attack; only a CanAttackDirectly rider bypasses it.
            targets = [m for m in opp_monsters if not state.is_protected_attack_target(m)]
            if state.can_attack_directly(iid):
                targets.append(None)  # Raging Flame Sprite: may bypass the monsters
        else:
            targets = [None]  # direct attack
        forced = state.forced_attack_target
        if forced is not None and forced in state.players[opp].monster_zones:
            # Staunch Defender: this turn the attacker may only target the chosen monster
            # (and never attack directly). The lock lifts on its own once it leaves the field.
            targets = [forced] if forced in targets else []
        actions.extend(DeclareAttack(iid, t) for t in targets)
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
    if isinstance(action, SpecialSummonFromHand):
        return _special_summon_from_hand(state, action)
    if isinstance(action, GeminiSummon):
        inst = state.inst(action.iid)
        inst.gemini_unlocked = True
        state.normal_summon_used = True
        return f"Gemini Summons {inst.name} (effect unlocked)"
    if isinstance(action, UnionEquip):
        return _union_equip(state, action)
    if isinstance(action, UnionUnequip):
        return _union_unequip(state, action)
    if isinstance(action, FlipSummon):
        inst = state.inst(action.iid)
        inst.position = Position.FACE_UP_ATTACK
        inst.position_changed_this_turn = True
        inst.summoned_this_turn = True  # a Flip Summon is a Summon (Toon attack lock, etc.)
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
    # Pay any activation cost before resolving — the headless path picks the fodder
    # deterministically (the interactive engine asks the player via a picker). Covers
    # all cost types uniformly, so a counter-cost Spell would pay here too.
    controller = state.inst(action.iid).controller
    for effect in card.effects:
        if _has_activation_cost(effect):
            pay_costs(state, controller, action.iid, effect, targets=action.targets)
            break
    resolve_card_effects(state, action.iid, action.targets)
    # A Normal Spell heads to the Graveyard; a permanent one (Equip/Continuous/Field) stays.
    inst = state.inst(action.iid)
    if inst.zone is Zone.SPELL_TRAP and not card.is_permanent:
        state.send_to_graveyard(action.iid)
    return f"activates {card.name}"


def _union_equip(state: GameState, action: UnionEquip) -> str:
    """Equip a Union monster to its host: it leaves the Monster Zone and attaches
    as an Equip Card (occupying a Spell/Trap zone, our simplification). Its EquipMod
    boost then flows through the normal Equip layer."""
    union = state.inst(action.union_iid)
    player = union.controller
    index = state.first_empty_spell_trap_zone(player)
    state.place_spell_trap(action.union_iid, player, index, Position.FACE_UP_ATTACK)
    union.equipped_to = action.host_iid
    union.union_acted_on_turn = state.turn_count
    return f"equips {union.name} to {state.inst(action.host_iid).name} (Union)"


def _union_unequip(state: GameState, action: UnionUnequip) -> str:
    """Unequip a Union monster and Special Summon it back in face-up Attack Position."""
    union = state.inst(action.union_iid)
    player = union.controller
    if not state.special_summon(action.union_iid, player, Position.FACE_UP_ATTACK):
        return f"cannot unequip {union.name} (Special Summon is locked or no zone)"
    union.equipped_to = None
    union.union_acted_on_turn = state.turn_count
    return f"unequips {union.name} (Special Summon)"


def _summon_banish_choice(state: GameState, player: int, rule) -> list[int] | None:
    """Greedily assign disjoint Graveyard monsters to each of ``rule``'s banish
    sub-costs (the Chaos monsters banish 1 LIGHT *and* 1 DARK). Returns the iids to
    banish (``[]`` when there's no cost), or ``None`` when the cost can't be paid.
    The pick is deterministic — first eligible per sub-cost — as interactive choice
    of which monsters to banish is a deferred enhancement (cf. SpecialSummonFromDeck)."""
    costs = getattr(rule, "banish_costs", ()) if rule is not None else ()
    if not costs:
        return []
    gy = state.players[player].graveyard
    chosen: list[int] = []
    used: set[int] = set()
    for sub in costs:
        picks: list[int] = []
        for iid in gy:
            if iid in used:
                continue
            if sub.card_filter.matches(state.inst(iid).card):
                picks.append(iid)
                if len(picks) == sub.count:
                    break
        if len(picks) < sub.count:
            return None
        used.update(picks)
        chosen.extend(picks)
    return chosen


def _special_summon_from_hand(state: GameState, action: SpecialSummonFromHand) -> str:
    """Special Summon a monster from the hand via its own ability. Does not consume
    the Normal Summon; the board condition was already checked at enumeration."""
    inst = state.inst(action.iid)
    player = inst.owner
    rule = inst.card.hand_summon
    to_banish = _summon_banish_choice(state, player, rule) or []
    for b in to_banish:
        state.banish(b)  # pay the banish cost (1 LIGHT + 1 DARK for the Chaos monsters)
    position = rule.position if rule is not None else Position.FACE_UP_ATTACK
    state.special_summon(action.iid, player, position, index=action.zone_index)
    extra = f" (banishing {len(to_banish)})" if to_banish else ""
    return f"Special Summons {inst.name} (from the hand){extra}"


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
    inst.was_tribute_summoned = bool(tributes)  # read by Blast Held by a Tribute
    state.normal_summon_used = True

    verb = "Normal Summons" if face_up else "Sets"
    extra = f" (tributing {len(tributes)})" if tributes else ""
    return f"{verb} {inst.name}{extra}"


def _battle_destroy(state: GameState, iid: int, destroyer_iid: int | None = None) -> None:
    """Destroy a monster as a result of battle — unless it's battle-indestructible
    (Marshmallon, Spirit Reaper), in which case it survives. Battle damage is applied
    separately by the caller, so an indestructible loser still costs its controller LP.
    When it actually dies, record ``(destroyer_iid, iid)`` so the engine can fire the
    destroyer's "when this card destroys a monster by battle" SELF Trigger."""
    if not state.is_battle_indestructible(iid):
        state.send_to_graveyard(iid, by_battle=True)
        if destroyer_iid is not None:
            state.battle_destroyed_by.append((destroyer_iid, iid))


def _resolve_attack(state: GameState, action: DeclareAttack) -> str:
    """Resolve one attack using the v6.0 Determining Damage rules (no piercing)."""
    attacker = state.inst(action.attacker)
    attacker.attacked_this_turn = True
    attacker.attacks_made_this_turn += 1
    me = attacker.controller
    opp = state.opponent_of(me)
    atk = state.effective_attack(action.attacker) + state.damage_step_bonus(
        action.attacker, action.target, is_attacker=True, which="atk"
    )
    state.battle_damage_dealt = None  # reset; set below when the attacker damages opp
    state.battle_destroyed_by = []  # reset; appended below for each combat death
    state.battle_pair = None  # reset; set below once a defending monster is in the battle
    state.battle_damage_taken = None  # reset; set below for whichever player takes damage

    def _take_battle_damage(player_idx: int, amount: int) -> int:
        # Apply battle damage and record (victim, amount) for the engine's "when you take
        # battle damage" Trap window. A player immune this battle/turn (Kuriboh, Winged
        # Kuriboh) takes 0 and the hit is not recorded. Returns the amount actually dealt.
        if state.takes_no_battle_damage(player_idx):
            return 0
        state.players[player_idx].life_points -= amount
        state.battle_damage_taken = (player_idx, amount)
        return amount

    def _hit_defender(amount: int) -> None:
        # Battle damage to the defending player — redirected to the attacker by Dimension
        # Wall (then it's not "damage inflicted to the opponent", so no dealer trigger).
        if state.reflect_battle_damage:
            _take_battle_damage(me, amount)
        else:
            dealt = _take_battle_damage(opp, amount)
            if dealt > 0:  # no "inflicted battle damage" trigger if Kuriboh zeroed it
                state.battle_damage_dealt = (action.attacker, dealt)

    if action.target is None:
        _hit_defender(atk)
        return f"{attacker.name} attacks directly — {atk} damage"

    target = state.inst(action.target)
    state.battle_pair = (action.attacker, action.target)  # a monster-vs-monster battle
    prefix = ""
    if target.position is Position.FACE_DOWN_DEFENSE:
        target.position = Position.FACE_UP_DEFENSE
        prefix = f"(flips up {target.name}) "

    if target.position is Position.FACE_UP_ATTACK:
        other = state.effective_attack(action.target) + state.damage_step_bonus(
            action.target, action.attacker, is_attacker=False, which="atk"
        )
        if atk > other:
            _battle_destroy(state, target.iid, attacker.iid)
            _hit_defender(atk - other)
            return f"{prefix}{attacker.name} ({atk}) destroys {target.name} ({other}) — {atk - other} damage"
        if atk < other:
            _battle_destroy(state, attacker.iid, target.iid)
            _take_battle_damage(me, other - atk)
            return f"{prefix}{attacker.name} ({atk}) is destroyed by {target.name} ({other}) — {other - atk} damage to attacker"
        _battle_destroy(state, attacker.iid, target.iid)
        _battle_destroy(state, target.iid, attacker.iid)
        return f"{prefix}{attacker.name} and {target.name} ({atk}) destroy each other"

    # defending monster: ATK vs DEF. No battle damage on a clean break — unless the
    # attacker has a piercing rider (Dark Driceratops), which deals the excess.
    dfn = state.effective_defense(action.target) + state.damage_step_bonus(
        action.target, action.attacker, is_attacker=False, which="defn"
    )
    if atk > dfn:
        _battle_destroy(state, target.iid, attacker.iid)
        if state.has_piercing(action.attacker):
            dmg = atk - dfn
            _hit_defender(dmg)
            return f"{prefix}{attacker.name} ({atk}) pierces {target.name} (DEF {dfn}) — {dmg} damage"
        return f"{prefix}{attacker.name} ({atk}) destroys defending {target.name} (DEF {dfn})"
    if atk < dfn:
        _take_battle_damage(me, dfn - atk)
        return f"{prefix}{attacker.name} ({atk}) bounces off {target.name} (DEF {dfn}) — {dfn - atk} damage to attacker"
    return f"{prefix}{attacker.name} ({atk}) cannot break {target.name} (DEF {dfn})"
