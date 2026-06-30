"""Effects Batch 104: Cave Dragon.

- Cannot be Normal Summoned/Set while you control a monster.
- Cannot declare an attack unless you control another Dragon-Type monster.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, NormalSummon, SetMonster, _battle_phase_actions, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


# ----------------------------------------------------- the Normal-Summon restriction


def test_cave_dragon_summonable_on_empty_board():
    s = _fresh(tp=A)
    cave = _in_hand(s, "Cave Dragon", A)
    acts = [a for a in legal_actions(s, A) if isinstance(a, (NormalSummon, SetMonster)) and a.iid == cave.iid]
    assert acts  # nothing controlled -> may be Normal Summoned/Set


def test_cave_dragon_not_summonable_while_controlling_a_monster():
    s = _fresh(tp=A)
    cave = _in_hand(s, "Cave Dragon", A)
    _spawn(s, "Petit Moth", A, 0)  # you now control a monster
    acts = [a for a in legal_actions(s, A) if isinstance(a, (NormalSummon, SetMonster)) and a.iid == cave.iid]
    assert not acts  # barred while you control a monster


# --------------------------------------------------------- the attack restriction


def test_cave_dragon_cannot_attack_without_another_dragon():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    cave = _spawn(s, "Cave Dragon", A, 0)
    _spawn(s, "Petit Moth", B, 0)
    assert s.attack_barred_needs_ally(cave.iid)
    acts = [a for a in _battle_phase_actions(s, A) if isinstance(a, DeclareAttack) and a.attacker == cave.iid]
    assert not acts  # no second Dragon -> cannot declare an attack


def test_cave_dragon_can_attack_with_another_dragon():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    cave = _spawn(s, "Cave Dragon", A, 0)
    _spawn(s, "Blue-Eyes White Dragon", A, 1)  # a second Dragon you control
    _spawn(s, "Petit Moth", B, 0)
    assert not s.attack_barred_needs_ally(cave.iid)
    acts = [a for a in _battle_phase_actions(s, A) if isinstance(a, DeclareAttack) and a.attacker == cave.iid]
    assert acts


def test_a_non_dragon_ally_does_not_satisfy_the_restriction():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    cave = _spawn(s, "Cave Dragon", A, 0)
    _spawn(s, "Summoned Skull", A, 1)  # a Fiend, not a Dragon
    _spawn(s, "Petit Moth", B, 0)
    assert s.attack_barred_needs_ally(cave.iid)  # still barred
