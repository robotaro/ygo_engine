"""Effects Batch 70: attack-lock floodgates (AttackRestriction extension).

`AttackRestriction` gains `all_cannot_attack` + `affects` (a blanket lock on one side)
and `max_level_can_attack` (a Level ceiling). The battle-phase action enumeration
(`moves._battle_phase_actions`) consults them via `_attack_floodgates`. Swords of
Revealing Light locks the controller's *opponent* and self-destructs on their 3rd End
Phase (via a CountdownSelfDestruct on an EndPhaseTrigger); Gravity Bind stops Level-4+
monsters on both sides.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, _battle_phase_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _spell(s, name, player, idx):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _attackers(s, player):
    return {a.attacker for a in _battle_phase_actions(s, player) if isinstance(a, DeclareAttack)}


def test_swords_locks_opponent_but_not_controller():
    # Opponent's turn: ME controls Swords -> the opponent cannot declare any attack.
    s = _fresh(tp=OPP)
    _spell(s, "Swords of Revealing Light", ME, 0)
    foe = _spawn(s, "Summoned Skull", OPP, 0)
    assert _attackers(s, OPP) == set()
    assert foe.iid not in _attackers(s, OPP)
    # Controller's own turn: Swords does NOT lock its controller.
    s2 = _fresh(tp=ME)
    _spell(s2, "Swords of Revealing Light", ME, 0)
    mine = _spawn(s2, "Summoned Skull", ME, 0)
    assert mine.iid in _attackers(s2, ME)


def test_swords_self_destructs_on_opponents_third_end_phase():
    s = _fresh(tp=OPP)
    swords = _spell(s, "Swords of Revealing Light", ME, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_end_phase_triggers(OPP)  # 1st opponent End Phase
    assert swords.iid in s.players[ME].spell_trap_zones
    eng._fire_end_phase_triggers(OPP)  # 2nd
    assert swords.iid in s.players[ME].spell_trap_zones
    eng._fire_end_phase_triggers(OPP)  # 3rd -> expires
    assert swords.iid not in s.players[ME].spell_trap_zones
    assert swords.iid in s.players[ME].graveyard


def test_swords_counter_does_not_tick_on_controllers_end_phase():
    s = _fresh(tp=ME)
    swords = _spell(s, "Swords of Revealing Light", ME, 0)
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_end_phase_triggers(ME)  # controller's own End Phase: whose="opponent" -> no tick
    assert swords.counters.get("countdown", 0) == 0
    assert swords.iid in s.players[ME].spell_trap_zones


def test_gravity_bind_blocks_level_4_plus_allows_level_3_or_less():
    s = _fresh(tp=ME)
    _spell(s, "Gravity Bind", ME, 0)
    high = _spawn(s, "Gemini Elf", ME, 0)  # Level 4 -> blocked
    low = _spawn(s, "Sangan", ME, 1)  # Level 3 -> may attack
    attackers = _attackers(s, ME)
    assert low.iid in attackers
    assert high.iid not in attackers


def test_gravity_bind_affects_both_players():
    # Gravity Bind controlled by ME still stops the opponent's Level-4+ monster.
    s = _fresh(tp=OPP)
    _spell(s, "Gravity Bind", ME, 0)
    foe_high = _spawn(s, "Summoned Skull", OPP, 0)  # Level 6 -> blocked
    assert foe_high.iid not in _attackers(s, OPP)
    foe_low = _spawn(s, "Kuriboh", OPP, 1)  # Level 1 -> may attack
    assert foe_low.iid in _attackers(s, OPP)
