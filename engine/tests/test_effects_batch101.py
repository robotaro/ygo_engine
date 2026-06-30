"""Effects Batch 101: Insect Queen.

Three continuous clauses:
- gains 200 ATK for each Insect monster on the field (both sides, itself included);
- cannot declare an attack unless you Tribute 1 monster;
- once per turn during the End Phase, if it destroyed an opponent's monster by battle this
  turn, Special Summon 1 "Insect Monster Token".
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, _battle_phase_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


# --------------------------------------------------------------------- the Insect anthem


def test_insect_queen_counts_itself():
    s = _fresh()
    iq = _spawn(s, "Insect Queen", A, 0)  # base 2200, +200 for itself (an Insect)
    assert s.effective_attack(iq.iid) == 2200 + 200


def test_insect_queen_scales_with_other_insects():
    s = _fresh()
    iq = _spawn(s, "Insect Queen", A, 0)
    _spawn(s, "Petit Moth", A, 1)  # an Insect on my side
    _spawn(s, "Drill Bug", B, 0)  # an Insect on the opponent's side counts too
    assert s.effective_attack(iq.iid) == 2200 + 200 * 3  # itself + 2 others


# ---------------------------------------------------------------- the attack-Tribute cost


def test_insect_queen_cannot_attack_without_tribute_fodder():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    iq = _spawn(s, "Insect Queen", A, 0)  # the only monster -> nothing to Tribute
    _spawn(s, "Petit Moth", B, 0)
    acts = [a for a in _battle_phase_actions(s, A) if isinstance(a, DeclareAttack) and a.attacker == iq.iid]
    assert not acts  # cannot pay the attack-Tribute cost


def test_insect_queen_can_attack_with_tribute_fodder():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    iq = _spawn(s, "Insect Queen", A, 0)
    _spawn(s, "Petit Moth", A, 1)  # fodder to Tribute
    _spawn(s, "Summoned Skull", B, 0)
    acts = [a for a in _battle_phase_actions(s, A) if isinstance(a, DeclareAttack) and a.attacker == iq.iid]
    assert acts


# -------------------------------------------------------------- the End-Phase token clause


def test_insect_queen_spawns_token_after_a_battle_kill():
    s = _fresh(tp=A, phase=Phase.END)
    iq = _spawn(s, "Insect Queen", A, 0)
    iq.destroyed_a_monster_by_battle_this_turn = True  # it killed something in battle
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_end_phase_triggers(A)
    tokens = [
        i for i in s.players[A].monster_zones
        if i is not None and s.cards[i].card.name == "Insect Monster Token"
    ]
    assert len(tokens) == 1  # one Insect Monster Token summoned
    assert s.cards[tokens[0]].card.race == "Insect"


def test_insect_queen_no_token_without_a_battle_kill():
    s = _fresh(tp=A, phase=Phase.END)
    iq = _spawn(s, "Insect Queen", A, 0)  # flag stays False
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_end_phase_triggers(A)
    tokens = [
        i for i in s.players[A].monster_zones
        if i is not None and s.cards[i].card.name == "Insect Monster Token"
    ]
    assert not tokens  # no battle kill -> no token


def test_token_feeds_the_anthem():
    s = _fresh(tp=A, phase=Phase.END)
    iq = _spawn(s, "Insect Queen", A, 0)
    iq.destroyed_a_monster_by_battle_this_turn = True
    eng = Engine(s, [Agent(), Agent()])
    eng._fire_end_phase_triggers(A)
    # Insect Queen (itself) + the new Insect Token = 2 Insects -> +400.
    assert s.effective_attack(iq.iid) == 2200 + 400
