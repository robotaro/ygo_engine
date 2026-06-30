"""Effects Batch 94: the Water / "Umi" cluster.

- A Legendary Ocean: a Field Spell always treated as "Umi"; all WATER monsters gain
  200 ATK/DEF.
- Tornado Wall: while you control a face-up Umi, you take no battle damage from attacking
  monsters.
- The Legendary Fisherman: while Umi is face-up, it cannot be selected as an attack target.

Deferred (documented): A Legendary Ocean's WATER Level-reduction, Fisherman's unaffected-
by-Spells, Tornado Wall's self-destruct when Umi leaves.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _field_spell(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_field_spell(inst.iid, player, Position.FACE_UP_ATTACK)
    return inst


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


# --------------------------------------------------------------- A Legendary Ocean


def test_legendary_ocean_is_treated_as_umi():
    s = _fresh()
    assert not s.controls_face_up_umi(A)
    _field_spell(s, "A Legendary Ocean", A)
    assert s.controls_face_up_umi(A)  # name is always treated as "Umi"
    assert not s.controls_face_up_umi(B)  # only its controller


def test_legendary_ocean_boosts_water_monsters():
    s = _fresh()
    fish = _spawn(s, "7 Colored Fish", A, 0)  # WATER, 1800 ATK
    base = s.effective_attack(fish.iid)
    _field_spell(s, "A Legendary Ocean", A)
    assert s.effective_attack(fish.iid) == base + 200
    assert s.effective_defense(fish.iid) == 800 + 200


# ------------------------------------------------------------------- Tornado Wall


def test_tornado_wall_needs_umi():
    s = _fresh()
    _faceup_st(s, "Tornado Wall", A)
    assert not s.takes_no_battle_damage(A)  # no Umi yet -> not immune
    _field_spell(s, "A Legendary Ocean", A)  # treated as Umi
    assert s.takes_no_battle_damage(A)  # Tornado Wall + Umi -> immune
    assert not s.takes_no_battle_damage(B)  # the opponent isn't covered


def test_tornado_wall_stops_battle_damage():
    s = _fresh(tp=B, phase=Phase.BATTLE)
    defender = _spawn(s, "7 Colored Fish", A, 0)  # 1800, weaker than the attacker
    _faceup_st(s, "Tornado Wall", A)
    _field_spell(s, "A Legendary Ocean", A)
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    s.players[A].life_points = 8000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(attacker.iid, defender.iid), B)
    assert s.players[A].life_points == 8000  # no battle damage taken (Tornado Wall + Umi)


# ----------------------------------------------------------- The Legendary Fisherman


def test_fisherman_untargetable_only_while_umi():
    s = _fresh()
    fisher = _spawn(s, "The Legendary Fisherman", A, 0)
    assert not s.is_protected_attack_target(fisher.iid)  # no Umi -> targetable
    _field_spell(s, "A Legendary Ocean", A)
    assert s.is_protected_attack_target(fisher.iid)  # Umi up -> cannot be targeted


def test_fisherman_protection_keeps_other_monsters_targetable():
    s = _fresh()
    fisher = _spawn(s, "The Legendary Fisherman", A, 0)
    other = _spawn(s, "7 Colored Fish", A, 1)
    _field_spell(s, "A Legendary Ocean", A)
    assert s.is_protected_attack_target(fisher.iid)  # self_only -> just the Fisherman
    assert not s.is_protected_attack_target(other.iid)  # a teammate stays attackable
