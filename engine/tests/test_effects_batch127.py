"""Effects Batch 127: Waboku.

"You take no battle damage from your opponent's monsters this turn. Your monsters cannot be
destroyed by battle this turn." A quick Trap pairing PreventBattleDamageThisTurn with the new
PreventBattleDestructionThisTurn (a turn-scoped per-player battle-indestructible flag).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=B, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 4, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _place_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def _activate_waboku(s, controller):
    trap = _place_st(s, "Waboku", controller)
    ctx = EffectContext(state=s, controller=controller, source_iid=trap.iid, targets=[])
    for prim in EFFECTS["Waboku"][0].resolve:
        prim.execute(ctx)
    return trap


def test_waboku_sets_turn_scoped_immunity_for_its_controller_only():
    s = _fresh()
    mine = _spawn(s, "Mystical Elf", A, 0)
    theirs = _spawn(s, "Summoned Skull", B, 0)
    _activate_waboku(s, A)
    assert s.takes_no_battle_damage(A) is True
    assert s.is_battle_indestructible(mine.iid) is True
    # The opponent gets neither protection.
    assert s.takes_no_battle_damage(B) is False
    assert s.is_battle_indestructible(theirs.iid) is False


def test_waboku_monster_survives_attack_and_controller_takes_no_damage():
    s = _fresh()
    mine = _spawn(s, "Mystical Elf", A, 0)  # 800 ATK — would die and cost 1700 LP
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    _activate_waboku(s, A)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(attacker.iid, mine.iid), B)
    assert s.inst(mine.iid).zone is Zone.MONSTER  # not destroyed by battle
    assert s.players[A].life_points == 8000  # no battle damage


def test_waboku_lapses_next_turn():
    s = _fresh()
    mine = _spawn(s, "Mystical Elf", A, 0)
    _activate_waboku(s, A)
    s.turn_count += 1  # a later turn
    assert s.takes_no_battle_damage(A) is False
    assert s.is_battle_indestructible(mine.iid) is False
