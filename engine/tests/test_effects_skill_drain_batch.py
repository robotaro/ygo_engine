"""Effects Batch 43: Skill Drain — negate the effects of all face-up monsters.

A face-up ``CardEffectNegation(negates="monster")`` (Skill Drain, a Continuous Trap
activated by paying 1000 LP) shuts off every face-up monster's effects on the field,
both sides — read by ``GameState.monster_effects_negated``. It suppresses:

  * a monster's continuous self-riders — SelfStatMod, Piercing, MultiAttacker,
    BattleIndestructible (via ``_self_rider`` / ``_self_stat_delta`` / the
    ``_spell_counter_delta`` chokepoints);
  * AttackTargetProtection / SpecialSummonLock that live ON a monster (Decoyroid,
    Vanity's Fiend — via ``active_markers`` respect_negation);
  * a monster's effect on resolution (its chain link is negated in ``_resolve_chain``).

Only a monster *face-up on the field* is negated — an effect that resolves from the GY
(a recruiter destroyed in battle) is unaffected, matching the ruling. Activation is
never gated ("their effects can still be activated").
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(turn_player=0):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, turn_player, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _drain(s, player=0):
    """Put Skill Drain face-up on the field (its activated state)."""
    inst = s.create_instance(reg.get("Skill Drain"), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _gy_monster(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


# --------------------------------------------------------------------------- #
#  The predicate
# --------------------------------------------------------------------------- #
def test_monster_effects_negated_for_a_face_up_monster():
    s = _fresh()
    skull = _spawn(s, "Summoned Skull", 0, 0)
    assert not s.monster_effects_negated(skull.iid)
    _drain(s)
    assert s.monster_effects_negated(skull.iid)  # both sides are negated
    opp = _spawn(s, "Celtic Guardian", 1, 0)
    assert s.monster_effects_negated(opp.iid)


def test_a_graveyard_effect_is_not_negated():
    # Skill Drain only reaches face-up FIELD monsters; an effect resolving from the GY
    # (a recruiter destroyed in battle) is untouched -> recruiters still work.
    s = _fresh()
    _drain(s)
    dead = _gy_monster(s, "Mystic Tomato", 0)
    assert not s.monster_effects_negated(dead.iid)


# --------------------------------------------------------------------------- #
#  Continuous self-riders suppressed
# --------------------------------------------------------------------------- #
def test_self_stat_mod_is_suppressed():
    s = _fresh()
    _gy_monster(s, "Summoned Skull", 0)
    _gy_monster(s, "Celtic Guardian", 0)  # 2 monsters in player 0's GY
    necro = _spawn(s, "Chaos Necromancer", 0, 0)  # base 0 ATK + 300 per GY monster
    assert s.effective_attack(necro.iid) == 600
    _drain(s)
    assert s.effective_attack(necro.iid) == 0  # the scaling self-boost is off


def test_piercing_is_suppressed():
    s = _fresh()
    park = _spawn(s, "Airknight Parshath", 0, 0)
    assert s.has_piercing(park.iid)
    _drain(s)
    assert not s.has_piercing(park.iid)


def test_multi_attacker_is_suppressed():
    s = _fresh()
    haya = _spawn(s, "Hayabusa Knight", 0, 0)
    assert s.max_attacks(haya.iid) == 2
    _drain(s)
    assert s.max_attacks(haya.iid) == 1


def test_battle_indestructible_is_suppressed():
    s = _fresh()
    marsh = _spawn(s, "Marshmallon", 0, 0)
    assert s.is_battle_indestructible(marsh.iid)
    _drain(s)
    assert not s.is_battle_indestructible(marsh.iid)


# --------------------------------------------------------------------------- #
#  Field-wide riders that live on a monster (via active_markers)
# --------------------------------------------------------------------------- #
def test_attack_target_protection_on_a_monster_is_suppressed():
    s = _fresh()
    _spawn(s, "Decoyroid", 0, 0)  # protects every OTHER monster you control
    ally = _spawn(s, "Celtic Guardian", 0, 1)
    assert s.is_protected_attack_target(ally.iid)
    _drain(s)
    assert not s.is_protected_attack_target(ally.iid)  # Decoyroid's effect is negated


def test_special_summon_lock_on_a_monster_is_suppressed():
    s = _fresh()
    _spawn(s, "Vanity's Fiend", 0, 0)
    dark = reg.get("Summoned Skull")
    assert s.special_summon_locked(1, dark)
    _drain(s)
    assert not s.special_summon_locked(1, dark)  # Vanity's lock is negated


# --------------------------------------------------------------------------- #
#  Effect resolution negated (chain link)
# --------------------------------------------------------------------------- #
def test_on_summon_effect_is_negated_on_resolution():
    s = _fresh()
    curse = _spawn(s, "Gravekeeper's Curse", 0, 0)  # on Summon: 500 damage to opponent
    eng = Engine(s, [Agent(), Agent()])
    before = s.players[1].life_points
    eng._trigger_summon_effect(curse.iid, "normal")
    assert s.players[1].life_points == before - 500  # fires normally
    _drain(s)
    before = s.players[1].life_points
    eng._trigger_summon_effect(curse.iid, "normal")
    assert s.players[1].life_points == before  # negated under Skill Drain


def test_flip_effect_is_negated_on_resolution():
    s = _fresh()
    bug = _spawn(s, "Man-Eater Bug", 0, 0, Position.FACE_UP_ATTACK)
    skull = _spawn(s, "Summoned Skull", 1, 0)
    _drain(s)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(bug.iid)
    assert s.inst(skull.iid).zone is Zone.MONSTER  # destroy effect negated -> Skull lives


# --------------------------------------------------------------------------- #
#  Activation cost
# --------------------------------------------------------------------------- #
def test_skill_drain_activation_pays_1000_lp():
    from ygo.moves import ActivateSpell

    s = _fresh()
    drain = s.create_instance(reg.get("Skill Drain"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(drain.iid)
    idx = next(i for i, z in enumerate(s.players[0].spell_trap_zones) if z is None)
    s.place_spell_trap(drain.iid, 0, idx, Position.FACE_DOWN)
    drain.set_on_turn = s.turn_count - 1
    before = s.players[0].life_points
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(drain.iid), 0)
    assert s.players[0].life_points == before - 1000
    assert s.inst(drain.iid).is_face_up  # stays on the field as a Continuous Trap


def test_no_drain_leaves_everything_normal():
    s = _fresh()
    park = _spawn(s, "Airknight Parshath", 0, 0)
    haya = _spawn(s, "Hayabusa Knight", 0, 1)
    assert s.has_piercing(park.iid)
    assert s.max_attacks(haya.iid) == 2
