"""Regression tests for the post-Batch-82 tech-debt audit fixes (#1-#4).

Each guards a specific latent bug the audit surfaced and verified:

  #1 ``_trigger_summon_effect`` dropped the ``effect.condition`` check that every other
     trigger-firer applies, so a conditional "when Special Summoned" effect fired even
     when its condition was false (Mazera DeVille discarding 3 with no "Pandemonium").
  #2 ``_clear_field_flags`` reset the temp stat deltas but not the PERMANENT ones
     (``perm_atk``/``perm_def``), so a monster that took a permanent stat change and later
     revived (same iid) came back at the wrong ATK.
  #3 ``_equip_mods_on`` ignored ``effect_negated``, so an Equip Spell's ATK/DEF boost (and
     a granted-piercing rider) survived Imperial Order — which the engine documents should
     nullify Spell effects on the field.
  #4 The StandbyUpkeep loop branch omitted the negation gate its StandbyTrigger sibling
     has, so a negated card's per-Standby upkeep still fired (Cure Mermaid healing under
     Skill Drain; Burning Land burning under Imperial Order).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _faceup_st(s, name, player):
    """Put a Spell/Trap face-up on the field (its activated state)."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _equip(s, name, player, monster_iid):
    inst = _faceup_st(s, name, player)
    inst.equipped_to = monster_iid
    return inst


def _field_spell(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_field_spell(inst.iid, player, Position.FACE_UP_ATTACK)
    return inst


# ------------------------------------------------------------------ #1 Mazera DeVille


def test_mazera_deville_does_not_discard_without_pandemonium():
    s = _fresh()
    mazera = _spawn(s, "Mazera DeVille", 0, 0)  # Special-Summon trigger gated on Pandemonium
    for _ in range(5):
        _in_hand(s, "Mystical Elf", 1)
    before = len(s.players[1].hand)
    Engine(s, [Agent(), Agent()])._trigger_summon_effect(mazera.iid, "special")
    assert len(s.players[1].hand) == before  # condition is false -> effect must not fire


def test_mazera_deville_discards_three_with_pandemonium():
    s = _fresh()
    mazera = _spawn(s, "Mazera DeVille", 0, 0)
    _field_spell(s, "Pandemonium", 0)  # the condition is now satisfied
    for _ in range(5):
        _in_hand(s, "Mystical Elf", 1)
    before = len(s.players[1].hand)
    Engine(s, [Agent(), Agent()])._trigger_summon_effect(mazera.iid, "special")
    assert len(s.players[1].hand) == before - 3  # opponent discards 3


# ----------------------------------------------------------------- #2 perm_atk on leave


def test_permanent_stat_change_clears_when_a_monster_leaves_the_field():
    s = _fresh()
    m = _spawn(s, "Summoned Skull", 0, 0)  # vanilla, base ATK 2500
    base = s.effective_attack(m.iid)
    m.perm_atk = -500  # a permanent debuff accrued while on the field
    assert s.effective_attack(m.iid) == base - 500
    s.send_to_graveyard(m.iid)
    assert m.perm_atk == 0  # cleared by _clear_field_flags


def test_revived_monster_returns_to_base_atk_not_the_old_permanent_debuff():
    s = _fresh()
    m = _spawn(s, "Summoned Skull", 0, 0)
    base = s.effective_attack(m.iid)
    m.perm_atk = -500
    s.send_to_graveyard(m.iid)
    assert s.special_summon(m.iid, 0, Position.FACE_UP_ATTACK)  # revive (same iid)
    assert s.effective_attack(m.iid) == base  # back to base, not base - 500


# --------------------------------------------------- #3 Imperial Order vs Equip Spells


def test_imperial_order_negates_an_equip_spells_atk_boost():
    s = _fresh()
    m = _spawn(s, "Mystical Elf", 0, 0)  # base 800
    _equip(s, "Axe of Despair", 0, m.iid)  # +1000
    assert s.effective_attack(m.iid) == 800 + 1000
    _faceup_st(s, "Imperial Order", 1)  # negate all Spell effects on the field
    assert s.effective_attack(m.iid) == 800  # the equip boost is suppressed


def test_imperial_order_negates_equip_granted_piercing():
    s = _fresh()
    m = _spawn(s, "Mystical Elf", 0, 0)
    _equip(s, "Big Bang Shot", 0, m.iid)  # +400 and grants piercing
    assert s.has_piercing(m.iid)
    _faceup_st(s, "Imperial Order", 1)
    assert not s.has_piercing(m.iid)  # the granted-piercing rider is suppressed too


# --------------------------------------------------- #4 negated per-Standby upkeep


def test_cure_mermaid_does_not_heal_under_skill_drain():
    s = _fresh(phase=Phase.STANDBY)
    _spawn(s, "Cure Mermaid", 0, 0)  # StandbyUpkeep gain_life 800 (a monster)
    _faceup_st(s, "Skill Drain", 0)  # negate all face-up monster effects
    before = s.players[0].life_points
    Engine(s, [Agent(), Agent()])._standby_phase(0)
    assert s.players[0].life_points == before  # the heal is negated


def test_cure_mermaid_heals_without_skill_drain():
    s = _fresh(phase=Phase.STANDBY)
    _spawn(s, "Cure Mermaid", 0, 0)
    before = s.players[0].life_points
    Engine(s, [Agent(), Agent()])._standby_phase(0)
    assert s.players[0].life_points == before + 800  # control: the upkeep still fires


def test_burning_land_does_not_burn_under_imperial_order():
    s = _fresh(phase=Phase.STANDBY)
    _faceup_st(s, "Burning Land", 0)  # StandbyUpkeep burn_life 500 (a Continuous Spell)
    _faceup_st(s, "Imperial Order", 1)  # negate all Spell effects on the field
    before = s.players[0].life_points
    Engine(s, [Agent(), Agent()])._standby_phase(0)
    assert s.players[0].life_points == before  # the burn is negated
