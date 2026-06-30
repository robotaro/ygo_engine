"""Effects Batch 132: Soul Exchange.

Normal Spell: target 1 opponent monster; this turn you may Tribute it (as if you controlled it)
for a Tribute Summon, and you cannot conduct your Battle Phase. ArmSoulExchange records the
target as Tribute fodder (fed into the summon enumeration) and stamps the battle-phase skip.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, NormalSummon, _main_phase_actions, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _arm(s, controller, target_iid):
    ctx = EffectContext(state=s, controller=controller, source_iid=-1, targets=[target_iid])
    for prim in EFFECTS["Soul Exchange"][0].resolve:
        prim.execute(ctx)


def test_tribute_summon_using_the_opponents_monster():
    s = _fresh()
    target = _spawn(s, "Mystical Elf", B, 0)  # the opponent's monster
    skull = _hand(s, "Summoned Skull", A)  # Level 6 -> needs 1 Tribute; A controls none
    # Without Soul Exchange, A cannot Tribute Summon (no fodder).
    pre = [a for a in _main_phase_actions(s, A) if isinstance(a, NormalSummon) and a.iid == skull.iid]
    assert pre == []
    _arm(s, A, target.iid)
    offered = [
        a
        for a in _main_phase_actions(s, A)
        if isinstance(a, NormalSummon) and a.iid == skull.iid and target.iid in a.tributes
    ]
    assert offered, "Soul Exchange should let A Tribute the opponent's monster to summon"
    apply(s, offered[0])
    assert s.inst(skull.iid).zone is Zone.MONSTER  # summoned onto A's side
    assert s.inst(target.iid).zone is Zone.GRAVEYARD
    assert target.iid in s.players[B].graveyard  # to its OWNER's Graveyard


def test_full_board_blocks_summon_with_only_the_opponent_tribute():
    s = _fresh()
    # Fill every one of A's Monster Zones with A's own monsters.
    own = [_spawn(s, "Mystical Elf", A, i) for i in range(len(s.players[A].monster_zones))]
    target = _spawn(s, "Mystical Elf", B, 0)
    skull = _hand(s, "Summoned Skull", A)  # Level 6 -> 1 Tribute
    _arm(s, A, target.iid)
    summons = [a for a in _main_phase_actions(s, A) if isinstance(a, NormalSummon) and a.iid == skull.iid]
    # Tributing A's OWN monster frees a zone -> offered; Tributing only the opponent's does not
    # (it would free a zone on B's side, leaving no room on A's full board).
    assert any(t in {o.iid for o in own} for a in summons for t in a.tributes)
    assert all(a.tributes != (target.iid,) for a in summons)


def test_skips_your_battle_phase():
    s = _fresh(phase=Phase.BATTLE)
    _spawn(s, "Summoned Skull", A, 0)  # an attacker
    target = _spawn(s, "Mystical Elf", B, 0)

    class AlwaysAttack(Agent):
        def decide(self, state, legal):
            atk = next((a for a in legal if isinstance(a, DeclareAttack)), None)
            return atk if atk is not None else next(a for a in legal if type(a).__name__ == "Pass")

    _arm(s, A, target.iid)
    eng = Engine(s, [AlwaysAttack(), Agent()])
    eng._battle_phase(A)
    assert s.players[B].life_points == 8000  # no attack happened — Battle Phase was skipped


def test_fodder_lapses_next_turn():
    s = _fresh()
    target = _spawn(s, "Mystical Elf", B, 0)
    _hand(s, "Summoned Skull", A)
    _arm(s, A, target.iid)
    assert s.soul_exchange_fodder(A) == target.iid
    s.turn_count += 1
    assert s.soul_exchange_fodder(A) is None
