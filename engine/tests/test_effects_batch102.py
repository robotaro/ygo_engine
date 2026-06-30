"""Effects Batch 102: board-conditional stat cards.

- Nuvia the Wicked: if Normal Summoned, destroy itself; while the opponent controls
  monsters, it loses 200 ATK for each.
- Aqua Chorus: a Continuous Trap — monsters sharing a name with another face-up monster
  gain 500 ATK and DEF.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import NormalSummon, apply
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


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


# ------------------------------------------------------------------- Nuvia the Wicked


def test_nuvia_loses_atk_per_opponent_monster():
    s = _fresh()
    nuvia = _spawn(s, "Nuvia the Wicked", A, 0)  # base 2000
    assert s.effective_attack(nuvia.iid) == 2000  # no opponent monsters
    _spawn(s, "Summoned Skull", B, 0)
    _spawn(s, "7 Colored Fish", B, 1)
    assert s.effective_attack(nuvia.iid) == 2000 - 400  # -200 each (2 monsters)


def test_nuvia_self_destructs_on_normal_summon():
    s = _fresh(tp=A)
    nuvia = _in_hand(s, "Nuvia the Wicked", A)
    eng = Engine(s, [Agent(), Agent()])
    apply(s, NormalSummon(nuvia.iid))
    s.summon_events.append((nuvia.iid, A, "normal"))
    eng._check_field_to_gy_triggers()  # drains the summon event -> fires the self-destruct
    assert s.inst(nuvia.iid).zone is Zone.GRAVEYARD  # destroyed itself on Normal Summon


def test_nuvia_atk_floored_at_zero():
    s = _fresh()
    nuvia = _spawn(s, "Nuvia the Wicked", A, 0)  # base 2000
    for i in range(5):
        _spawn(s, "Petit Moth", B, i)  # 5 opponent monsters -> -1000
    assert s.effective_attack(nuvia.iid) == 2000 - 1000


# ------------------------------------------------------------------------ Aqua Chorus


def test_aqua_chorus_boosts_same_named_pair():
    s = _fresh()
    a1 = _spawn(s, "Petit Moth", A, 0)  # base 300
    a2 = _spawn(s, "Petit Moth", B, 0)  # same name, opponent's side
    other = _spawn(s, "Summoned Skull", A, 1)
    base = s.effective_attack(a1.iid)
    _faceup_st(s, "Aqua Chorus", A)
    assert s.effective_attack(a1.iid) == base + 500  # shares a name -> +500
    assert s.effective_attack(a2.iid) == 300 + 500  # the other copy too
    assert s.effective_defense(a1.iid) == 200 + 500  # DEF as well
    assert s.effective_attack(other.iid) == 2500  # unique name -> no boost


def test_aqua_chorus_no_boost_for_unique_names():
    s = _fresh()
    lone = _spawn(s, "Petit Moth", A, 0)
    _spawn(s, "Summoned Skull", B, 0)  # different name
    _faceup_st(s, "Aqua Chorus", A)
    assert s.effective_attack(lone.iid) == 300  # nobody shares its name -> unchanged
