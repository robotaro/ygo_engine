"""Effects Batch 54: monster "when this declares an attack" (condition-gated).

engine._fire_attack_declared_trigger now honours the effect's condition, so a monster's
own attack-declaration Trigger can be gated. Gravekeeper's Assailant flips an opponent's
monster's battle position when it attacks while "Necrovalley" is on the field, via the
new reusable _field_spell_on_field condition.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

ATTACKER, DEFENDER = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ATTACKER, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _field(s, name, player=ATTACKER):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_field_spell(inst.iid, player, Position.FACE_UP_ATTACK)
    return inst


def test_assailant_flips_opponent_position_with_necrovalley():
    s = _fresh()
    assailant = _spawn(s, "Gravekeeper's Assailant", ATTACKER, 0)
    prey = _spawn(s, "Celtic Guardian", DEFENDER, 0)  # face-up Attack -> toggled to Defense
    _field(s, "Necrovalley")
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_attack_declared_trigger(assailant.iid)
    assert s.inst(prey.iid).position is Position.FACE_UP_DEFENSE


def test_assailant_does_nothing_without_necrovalley():
    s = _fresh()
    assailant = _spawn(s, "Gravekeeper's Assailant", ATTACKER, 0)
    prey = _spawn(s, "Celtic Guardian", DEFENDER, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_attack_declared_trigger(assailant.iid)
    assert s.inst(prey.iid).position is Position.FACE_UP_ATTACK  # ungated, no flip
