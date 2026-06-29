"""Effects Batch 39: attack twice (MultiAttacker).

A continuous MultiAttacker rider lets a monster declare up to ``times`` attacks each
Battle Phase. The engine tracks CardInstance.attacks_made_this_turn (incremented in
_resolve_attack, reset by reset_turn_flags) and the battle-phase enumeration offers an
attack while that count is below GameState.max_attacks(iid). Cards: Hayabusa Knight,
Mataza the Zapper, Twinheaded Beast (all twice).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    return s


def _can_attack(s, iid):
    return any(isinstance(a, DeclareAttack) and a.attacker == iid for a in legal_actions(s, 0))


def _attack(s, attacker, target=None):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), 0)


def test_hayabusa_can_attack_twice_then_is_done():
    s = _fresh()
    haya = s.spawn_on_field(reg.get("Hayabusa Knight"), 0, 0, Position.FACE_UP_ATTACK)
    assert _can_attack(s, haya.iid)
    _attack(s, haya.iid, None)  # first direct attack
    assert s.inst(haya.iid).attacks_made_this_turn == 1
    assert _can_attack(s, haya.iid)  # still has a second attack
    _attack(s, haya.iid, None)  # second direct attack
    assert s.inst(haya.iid).attacks_made_this_turn == 2
    assert not _can_attack(s, haya.iid)  # now used up


def test_two_direct_attacks_deal_damage_twice():
    s = _fresh()
    haya = s.spawn_on_field(reg.get("Hayabusa Knight"), 0, 0, Position.FACE_UP_ATTACK)  # 1000 ATK
    before = s.players[1].life_points
    _attack(s, haya.iid, None)
    _attack(s, haya.iid, None)
    assert s.players[1].life_points == before - 2000  # 1000 x 2


def test_ordinary_monster_attacks_only_once():
    s = _fresh()
    skull = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    assert _can_attack(s, skull.iid)
    _attack(s, skull.iid, None)
    assert not _can_attack(s, skull.iid)  # single attack used up


def test_attack_count_resets_next_turn():
    s = _fresh()
    haya = s.spawn_on_field(reg.get("Twinheaded Beast"), 0, 0, Position.FACE_UP_ATTACK)
    _attack(s, haya.iid, None)
    _attack(s, haya.iid, None)
    assert s.inst(haya.iid).attacks_made_this_turn == 2
    s.inst(haya.iid).reset_turn_flags()  # what the engine does at the start of a turn
    assert s.inst(haya.iid).attacks_made_this_turn == 0
    assert _can_attack(s, haya.iid)
