"""Regression tests for the Wave-1 game-logic bug fixes (audit items #1-#9).

Each guards a specific bug the audit confirmed:

  #1 Six burn primitives subtracted Life Points directly instead of routing through the
     recorded damage sink, so "when you take damage" reactions (Numinous Healer) never fired
     off them. All now route through ``GameState.deal_damage``.
  #2 Magic Cylinder reflected PRINTED ATK, not EFFECTIVE ATK (pumps/equips ignored).
  #3 A double-KO (both players to 0 in one step) awarded the loop's-first-loser a WIN instead
     of a DRAW.
  #4 The End-Phase hand-size discard loop could trigger a Magical Thorn burn but never checked
     Life Points, so a lethal discard went undetected.
  #5 ``battle_damage_preview`` had drifted from ``_resolve_attack`` (Mirror Wall halving, Susa
     Soldier halved damage, Rocket Warrior self-immunity), mis-firing the Nutrient Z window.
  #6 The transient attack flags leaked into the next attack on the bare ``apply(DeclareAttack)``
     path (they were reset only in the engine's ``_declare_attack``).
  #7 The Dark Door read ``attacked_this_turn`` (set at declaration, even for a fizzle) instead
     of ``attacks_made_this_turn``, wrongly denying a legitimate attack replay.
  #8 'Cemetary Bomb' was defined twice in the EFFECTS literal; a guard now rejects a duplicate
     key so a future redefinition can't silently shadow a card.
  #9 Unknown pool / scaling keys silently returned 0 instead of failing loudly on a typo.
"""

from __future__ import annotations

import ast
import collections
import dataclasses
import pathlib

import pytest

import ygo.card_effects as ce
from ygo.agents import Agent
from ygo.card_effects import _register
from ygo.cards import CardRegistry
from ygo.effects import (
    EffectContext,
    EquipMod,
    DamageEqualToAttackerAtk,
    SelfStatMod,
    _count_pool,
)
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, _attacks_locked_out, apply, battle_damage_preview
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


def _set_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1  # set earlier -> activatable now
    return inst


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


class _Activator(Agent):
    def respond(self, state, options, event):
        return options[0] if options else None


class _Discarder(Agent):
    def decide(self, state, legal):
        return legal[0]


# ----------------------------------------------- #1 + #2 Magic Cylinder -> Numinous Healer


def test_magic_cylinder_reflects_effective_atk_and_triggers_numinous_healer():
    s = _fresh(tp=1)  # player 1 is the attacking player
    attacker = _spawn(s, "Summoned Skull", 1, 0)  # printed ATK 2500
    s.inst(attacker.iid).temp_atk = 500  # pumped: effective ATK is now 3000
    cyl = _set_trap(s, "Magic Cylinder", player=0)
    _set_trap(s, "Numinous Healer", player=1)  # the burned (attacking) player holds the healer
    ctx = EffectContext(
        state=s, controller=0, source_iid=cyl.iid,
        event={"attacker": attacker.iid, "player": 1},
    )
    DamageEqualToAttackerAtk().execute(ctx)
    # #2: reflects the EFFECTIVE ATK (3000), not the printed 2500.
    assert s.effect_damage_pending == [(1, 3000)]
    assert s.players[1].life_points == 8000 - 3000
    # #1: routing through deal_damage opens the "took damage" window -> the healer fires.
    before = s.players[1].life_points
    Engine(s, [Agent(), _Activator()])._fire_effect_damage_window()
    assert s.players[1].life_points == before + 1000  # Numinous Healer heals 1000


def test_full_salvo_burn_records_effect_damage():
    # A second burn primitive (Full Salvo) that previously bypassed the sink now records it.
    from ygo.effects import DiscardHandThenBurn

    s = _fresh(tp=0)
    for _ in range(3):
        _in_hand(s, "Mystical Elf", 0)
    ctx = EffectContext(state=s, controller=0, source_iid=s.players[0].hand[0])
    DiscardHandThenBurn(per=200).execute(ctx)
    assert s.effect_damage_pending == [(1, 600)]  # 3 cards x 200, recorded for the window
    assert s.players[1].life_points == 8000 - 600


# ------------------------------------------------------------- #3 double-KO is a draw


def test_double_ko_via_tremendous_fire_is_a_draw():
    s = _fresh(tp=0)
    s.players[0].life_points = 400  # SELF takes 500
    s.players[1].life_points = 900  # OPPONENT takes 1000
    fire = _in_hand(s, "Tremendous Fire", 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_as_chain(ActivateSpell(fire.iid, targets=()), 0)
    assert s.players[0].life_points <= 0 and s.players[1].life_points <= 0
    eng._check_life_points()
    assert eng.result is not None
    assert eng.result.winner is None  # a DRAW, not a win for whoever is checked first


def test_single_ko_still_awards_the_win():
    s = _fresh(tp=0)
    s.players[1].life_points = 100
    eng = Engine(s, [Agent(), Agent()])
    _in_hand(s, "Hinotama", 0)  # burns opponent 500
    eng._activate_as_chain(ActivateSpell(s.players[0].hand[-1], targets=()), 0)
    eng._check_life_points()
    assert eng.result is not None and eng.result.winner == 0


# ---------------------------------------------- #4 End-Phase discard burn checks Life Points


def test_end_phase_discard_burn_can_end_the_duel():
    s = _fresh(tp=0, phase=Phase.END)
    for _ in range(8):  # over the 6-card hand-size limit -> must discard
        _in_hand(s, "Mystical Elf", 0)
    _faceup_st(s, "Magical Thorn", 1)  # opponent's: burns the discarder 500 per discarded card
    s.players[0].life_points = 400  # a single 500 burn is lethal
    eng = Engine(s, [_Discarder(), Agent()])
    eng._end_phase(0)
    assert eng.result is not None
    assert eng.result.winner == 1  # player 0 burned itself out discarding


# --------------------------------------- #5 preview matches resolution (halving/immunity)


def test_preview_matches_resolution_under_mirror_wall():
    s = _fresh(tp=0, phase=Phase.BATTLE)
    a = _spawn(s, "Summoned Skull", 0, 0)  # 2500
    _faceup_st(s, "Mirror Wall", 1)  # opponent's Mirror Wall halves attackers' ATK
    preview = battle_damage_preview(s, a.iid, None)  # direct attack
    before = s.players[1].life_points
    apply(s, DeclareAttack(a.iid, None))
    actual = before - s.players[1].life_points
    assert actual == 1250  # 2500 halved
    assert preview == (1, actual)  # preview agreed with the resolver


def test_preview_matches_resolution_for_susa_soldier():
    s = _fresh(tp=0, phase=Phase.BATTLE)
    susa = _spawn(s, "Susa Soldier", 0, 0)  # 2000, halves the battle damage it inflicts
    preview = battle_damage_preview(s, susa.iid, None)
    before = s.players[1].life_points
    apply(s, DeclareAttack(susa.iid, None))
    actual = before - s.players[1].life_points
    assert actual == 1000  # 2000 halved
    assert preview == (1, actual)


# --------------------------------------------- #6 transient flags reset on direct apply path


def test_stale_transient_attack_flags_reset_on_direct_apply():
    s = _fresh(tp=0)
    a = _spawn(s, "Summoned Skull", 0, 0)  # 2500
    # Leftover flags as if from a previous attack (a resolved Dimension Wall + Kuriboh).
    s.reflect_battle_damage = True
    s.battle_damage_prevented = {1}
    s.attack_negated = True
    s.attack_redirect = 999
    before_opp = s.players[1].life_points
    before_me = s.players[0].life_points
    apply(s, DeclareAttack(a.iid, None))  # bare apply path (no engine _declare_attack ahead)
    # Reset worked: the opponent takes the FULL hit; the attacker is unharmed.
    assert s.players[1].life_points == before_opp - 2500
    assert s.players[0].life_points == before_me
    assert s.reflect_battle_damage is False
    assert s.battle_damage_prevented == set()


# --------------------------------------------------------- #7 The Dark Door allows a replay


def test_dark_door_allows_replay_after_a_fizzle():
    s = _fresh(tp=0, phase=Phase.BATTLE)
    a = _spawn(s, "Battle Ox", 0, 0)
    _faceup_st(s, "The Dark Door", 0)
    inst = s.inst(a.iid)
    # A fizzled/negated attack: DECLARED (attacked_this_turn) but never COMPLETED.
    inst.attacked_this_turn = True
    inst.attacks_made_this_turn = 0
    assert _attacks_locked_out(s, 0) is False  # the replay is still allowed
    # A completed attack DOES lock out further attacks.
    inst.attacks_made_this_turn = 1
    assert _attacks_locked_out(s, 0) is True


# ------------------------------------------------------------- #8 duplicate-key guard


def test_register_raises_on_duplicate_key():
    d = {"Widget": (1,)}
    with pytest.raises(ValueError):
        _register(d, {"Widget": (2,)})  # would silently shadow the existing "Widget"
    _register(d, {"Gadget": (3,)})  # a fresh key merges fine
    assert d == {"Widget": (1,), "Gadget": (3,)}


def test_effects_source_has_no_duplicate_keys():
    # AST scan of the source guards the Cemetary-Bomb class of bug (a key redefined WITHIN the
    # dict literal, which Python silently collapses before any runtime guard could see it).
    tree = ast.parse(pathlib.Path(ce.__file__).read_text())
    counts: collections.Counter = collections.Counter()

    def record(d: ast.Dict) -> None:
        for k in d.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                counts[k.value] += 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            tgt = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if getattr(tgt, "id", None) == "EFFECTS" and isinstance(node.value, ast.Dict):
                record(node.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_register":
            if (
                len(node.args) == 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "EFFECTS"
                and isinstance(node.args[1], ast.Dict)
            ):
                record(node.args[1])
    dups = {k: c for k, c in counts.items() if c > 1}
    assert not dups, f"duplicate EFFECTS keys: {dups}"


# ------------------------------------------------- #9 unknown pool / scaling fails loudly


def test_unknown_count_pool_raises():
    s = _fresh()
    src = _spawn(s, "Summoned Skull", 0, 0)
    ctx = EffectContext(state=s, controller=0, source_iid=src.iid)
    with pytest.raises(ValueError):
        _count_pool(ctx, "not_a_real_pool")
    assert _count_pool(ctx, "own_monsters") == 1  # a valid pool still works


def test_unknown_equip_scaling_raises():
    s = _fresh()
    m = _spawn(s, "Mystical Elf", 0, 0)
    with pytest.raises(ValueError):
        s._mod_delta(EquipMod(scaling="bogus_scaling"), 0, "atk", m.iid)
    # a known scaling still computes (Mage Power-style, no S/T on field -> 0)
    assert s._mod_delta(EquipMod(scaling="spell_trap", scale_atk=500), 0, "atk", m.iid) == 0


def test_unknown_self_stat_scaling_raises():
    s = _fresh()
    # Base on a plain (non-Gemini) monster so its effects are live, then give it a bogus mod.
    bogus = dataclasses.replace(
        reg.get("Mystical Elf"), continuous=(SelfStatMod(scaling="bogus_scaling", scale_atk=100),)
    )
    inst = s.spawn_on_field(bogus, 0, 0, Position.FACE_UP_ATTACK)
    with pytest.raises(ValueError):
        s.effective_attack(inst.iid)
