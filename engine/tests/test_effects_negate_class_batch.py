"""Effects Batch 42: negate-while-face-up class locks (whole Spell/Trap negators).

A face-up ``CardEffectNegation`` rider shuts off a whole card class on the field:

  * Jinzo / Spell Canceller — ``prevent_activation=True``: Traps (resp. Spells) cannot
    even be activated, AND their effects on the field are negated.
  * Royal Decree / Imperial Order — ``prevent_activation=False``: the card still
    activates, but its effect is negated on resolution (and its continuous riders go
    inert). ``exclude_self`` keeps the negator itself live.

Hook points, all consulted off the negator marker via ``GameState``:
  * ``cannot_activate_card`` — every Spell/Trap activation enumeration (main phase +
    response window) skips a barred card.
  * ``effect_negated`` — ``_resolve_chain`` treats a negated link like an explicitly
    negated one; ``_active_continuous_sources`` / ``active_markers`` skip a negated
    card's passive riders (a Field Spell's FieldMod under Imperial Order).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, legal_actions, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(turn_player=0):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, turn_player, Phase.MAIN_1
    return s


def _spawn_monster(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _set_st(s, name, player):
    """Set a Spell/Trap face-down on an earlier turn (so it's activatable now)."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _place_active_st(s, name, player):
    """Put a Continuous Spell/Trap face-up on the field (its activated state)."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _activate(s, iid, controller=0, targets=()):
    Engine(s, [Agent(), Agent()])._activate_as_chain(
        ActivateSpell(iid, targets=targets), controller
    )


# --------------------------------------------------------------------------- #
#  Predicates
# --------------------------------------------------------------------------- #
def test_jinzo_bars_traps_only():
    s = _fresh()
    _spawn_monster(s, "Jinzo", 0, 0)
    trap = _set_st(s, "Just Desserts", 1)
    spell = _set_st(s, "Ookazi", 1)
    assert s.cannot_activate_card(trap.iid)  # a Trap can't be activated under Jinzo
    assert s.effect_negated(trap.iid)  # and its effect would be negated
    assert not s.cannot_activate_card(spell.iid)  # Spells are untouched
    assert not s.effect_negated(spell.iid)


def test_spell_canceller_bars_spells_only():
    s = _fresh()
    _spawn_monster(s, "Spell Canceller", 0, 0)
    trap = _set_st(s, "Just Desserts", 1)
    spell = _set_st(s, "Ookazi", 1)
    assert s.cannot_activate_card(spell.iid)
    assert s.effect_negated(spell.iid)
    assert not s.cannot_activate_card(trap.iid)
    assert not s.effect_negated(trap.iid)


def test_royal_decree_negates_effects_but_not_activation():
    s = _fresh()
    decree = _place_active_st(s, "Royal Decree", 0)
    other = _set_st(s, "Just Desserts", 1)
    # Decree negates other Traps' EFFECTS but does not bar their activation.
    assert not s.cannot_activate_card(other.iid)
    assert s.effect_negated(other.iid)
    # exclude_self: Royal Decree does not negate itself (it stays a live negator).
    assert not s.effect_negated(decree.iid)


def test_imperial_order_negates_spell_effects_not_activation():
    s = _fresh()
    _place_active_st(s, "Imperial Order", 0)
    spell = _set_st(s, "Ookazi", 1)
    assert not s.cannot_activate_card(spell.iid)
    assert s.effect_negated(spell.iid)


def test_monster_is_never_self_barred():
    # Jinzo is a monster — it has no Spell/Trap class, so the negation never targets it.
    s = _fresh()
    jinzo = _spawn_monster(s, "Jinzo", 0, 0)
    assert not s.cannot_activate_card(jinzo.iid)
    assert not s.effect_negated(jinzo.iid)


# --------------------------------------------------------------------------- #
#  Enumeration gating
# --------------------------------------------------------------------------- #
def _offered(actions, iid):
    return any(isinstance(a, ActivateSpell) and a.iid == iid for a in actions)


def test_jinzo_removes_set_trap_from_legal_actions():
    s = _fresh(turn_player=1)
    trap = _set_st(s, "Just Desserts", 1)
    assert _offered(legal_actions(s, 1), trap.iid)  # offered with no Jinzo
    _spawn_monster(s, "Jinzo", 0, 0)
    assert not _offered(legal_actions(s, 1), trap.iid)  # barred once Jinzo is up


def test_jinzo_removes_trap_from_response_window():
    # Player 0 Normal Summons a 2500-ATK monster; player 1 holds a Set Trap Hole that
    # reacts to it. The response window offers Trap Hole — until Jinzo bars all Traps.
    s = _fresh(turn_player=0)
    skull = _spawn_monster(s, "Summoned Skull", 0, 0)
    trap = _set_st(s, "Trap Hole", 1)
    event = {"kind": "summon", "player": 0, "monster": skull.iid, "summon_kind": "normal"}
    assert _offered(response_options(s, 1, event, 2), trap.iid)
    _spawn_monster(s, "Jinzo", 0, 1)
    assert not _offered(response_options(s, 1, event, 2), trap.iid)


def test_spell_canceller_removes_hand_spell_from_legal_actions():
    s = _fresh(turn_player=1)
    ookazi = _hand(s, "Ookazi", 1)
    assert _offered(legal_actions(s, 1), ookazi.iid)
    _spawn_monster(s, "Spell Canceller", 0, 0)
    assert not _offered(legal_actions(s, 1), ookazi.iid)


# --------------------------------------------------------------------------- #
#  Chain-resolution negation
# --------------------------------------------------------------------------- #
def test_royal_decree_negates_a_resolving_trap():
    s = _fresh()
    _place_active_st(s, "Royal Decree", 0)
    _spawn_monster(s, "Summoned Skull", 1, 0)
    _spawn_monster(s, "Celtic Guardian", 1, 1)  # player 1 controls 2 monsters
    desserts = _set_st(s, "Just Desserts", 0)  # would burn player 1 for 500 x 2 = 1000
    before = s.players[1].life_points
    _activate(s, desserts.iid, controller=0)
    assert s.players[1].life_points == before  # the burn was negated


def test_imperial_order_negates_a_resolving_spell():
    s = _fresh()
    _place_active_st(s, "Imperial Order", 0)
    ookazi = _set_st(s, "Ookazi", 0)  # would burn the opponent 800
    before = s.players[1].life_points
    _activate(s, ookazi.iid, controller=0)
    assert s.players[1].life_points == before


def test_burn_resolves_normally_without_a_negator():
    # Negative control: same Ookazi, no Imperial Order -> the 800 burn lands.
    s = _fresh()
    ookazi = _set_st(s, "Ookazi", 0)
    before = s.players[1].life_points
    _activate(s, ookazi.iid, controller=0)
    assert s.players[1].life_points == before - 800


# --------------------------------------------------------------------------- #
#  Continuous-rider suppression (FieldMod)
# --------------------------------------------------------------------------- #
def test_imperial_order_suppresses_a_field_spells_boost():
    s = _fresh()
    guardian = _spawn_monster(s, "Celtic Guardian", 0, 0)  # Warrior, 1400 ATK
    s.place_field_spell(_hand(s, "Sogen", 0).iid, 0, Position.FACE_UP_ATTACK)
    assert s.effective_attack(guardian.iid) == 1600  # Sogen: +200 to Warriors
    _place_active_st(s, "Imperial Order", 1)  # negates the Field Spell (a Spell effect)
    assert s.effective_attack(guardian.iid) == 1400  # boost gone


def test_jinzo_does_not_suppress_a_field_spell():
    # Jinzo negates Traps, not Spells -> a Field Spell's boost survives.
    s = _fresh()
    guardian = _spawn_monster(s, "Celtic Guardian", 0, 0)
    s.place_field_spell(_hand(s, "Sogen", 0).iid, 0, Position.FACE_UP_ATTACK)
    _spawn_monster(s, "Jinzo", 1, 0)
    assert s.effective_attack(guardian.iid) == 1600


# --------------------------------------------------------------------------- #
#  Imperial Order's Standby upkeep
# --------------------------------------------------------------------------- #
def test_imperial_order_pays_700_on_controllers_standby():
    s = _fresh(turn_player=0)
    order = _place_active_st(s, "Imperial Order", 0)
    s.phase = Phase.STANDBY
    before = s.players[0].life_points
    Engine(s, [Agent(), Agent()])._standby_phase(0)
    assert s.players[0].life_points == before - 700
    assert s.inst(order.iid).zone is Zone.SPELL_TRAP  # still on the field


def test_imperial_order_dies_if_controller_cannot_pay():
    s = _fresh(turn_player=0)
    order = _place_active_st(s, "Imperial Order", 0)
    s.players[0].life_points = 700  # cannot afford 700 (would not stay above 0)
    s.phase = Phase.STANDBY
    Engine(s, [Agent(), Agent()])._standby_phase(0)
    assert s.inst(order.iid).zone is Zone.GRAVEYARD
