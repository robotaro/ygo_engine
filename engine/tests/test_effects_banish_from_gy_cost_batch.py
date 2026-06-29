"""Effects Batch 32: banish-from-Graveyard activation cost.

A new ``Effect.banish_from_gy_cost`` (+ ``banish_from_gy_filter``) banishes N monsters
from the controller's Graveyard to activate — gated in enumeration via can_pay_costs
and paid in pay_costs, which excludes the effect's own targets from the fodder (so a
GY-targeting payload never banishes its own target). Cards: Dark Armed Dragon (banish
1 DARK -> destroy 1 card on the field) and Lekunga (banish 2 WATER -> 1 Lekunga Token).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, can_pay_costs, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _effect_actions(s, iid):
    return [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect) and a.iid == iid]


# --- the cost gates the effect -----------------------------------------------------
def test_dark_armed_effect_needs_a_dark_in_gy():
    s = _fresh()
    dad = s.spawn_on_field(reg.get("Dark Armed Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)  # a target on field
    eff = reg.get("Dark Armed Dragon").effects[0]
    assert not can_pay_costs(s, 0, dad.iid, eff)  # empty GY -> can't pay
    _in_gy(s, "Mystical Elf", 0)  # a LIGHT monster -> still no DARK
    assert not can_pay_costs(s, 0, dad.iid, eff)
    _in_gy(s, "Summoned Skull", 0)  # a DARK monster -> now payable
    assert can_pay_costs(s, 0, dad.iid, eff)


def test_dark_armed_banishes_one_dark_and_destroys_a_field_card():
    s = _fresh()
    dad = s.spawn_on_field(reg.get("Dark Armed Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    fodder = _in_gy(s, "Summoned Skull", 0)
    prey = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(dad.iid, targets=(prey.iid,)), 0)
    assert s.inst(fodder.iid).zone is Zone.BANISHED  # the banish cost
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD  # destroyed target


# --- Lekunga: banish 2 WATER -> a Token --------------------------------------------
def test_lekunga_banishes_two_water_and_makes_a_token():
    s = _fresh()
    lek = s.spawn_on_field(reg.get("Lekunga"), 0, 0, Position.FACE_UP_ATTACK)
    w1 = _in_gy(s, "Mother Grizzly", 0)  # WATER
    w2 = _in_gy(s, "Abyss Soldier", 0)  # WATER
    assert _effect_actions(s, lek.iid)  # 2 WATER + a free zone -> activatable
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(lek.iid), 0)
    assert s.inst(w1.iid).zone is Zone.BANISHED
    assert s.inst(w2.iid).zone is Zone.BANISHED
    tokens = [
        s.inst(i)
        for i in s.players[0].monster_zones
        if i is not None and s.inst(i).card.is_token
    ]
    assert len(tokens) == 1 and tokens[0].card.name == "Lekunga Token"
    assert tokens[0].card.attack == 700 and tokens[0].card.race == "Plant"


def test_lekunga_needs_two_water_in_gy():
    s = _fresh()
    lek = s.spawn_on_field(reg.get("Lekunga"), 0, 0, Position.FACE_UP_ATTACK)
    _in_gy(s, "Mother Grizzly", 0)  # only 1 WATER
    assert _effect_actions(s, lek.iid) == []


# --- the cost excludes the effect's targets (cost/target stay disjoint) ------------
def test_banish_cost_excludes_chosen_target():
    # A synthetic effect that both banishes a DARK from GY AND targets a GY monster:
    # the single DARK present is the chosen target, so the cost must find NO fodder.
    from ygo.effects import CardFilter
    from ygo.enums import Attribute
    from ygo.moves import banish_from_gy_fodder

    s = _fresh()
    only_dark = _in_gy(s, "Summoned Skull", 0)
    filt = CardFilter(card_kind="monster", attributes=frozenset({Attribute.DARK}))
    # With the lone DARK excluded (it's the target), there's nothing left to banish.
    assert banish_from_gy_fodder(s, 0, filt, exclude=(only_dark.iid,)) == []
    assert banish_from_gy_fodder(s, 0, filt) == [only_dark.iid]
