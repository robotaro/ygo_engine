"""Effects Batch 124: Kiseitai.

The Blast Sphere shape: a reactive "attacked" Trigger equips the source to the attacking
monster (no damage calculation — the attack fizzles), then a requires_equipped StandbyTrigger
on the opponent's Standby Phase gains its controller LP equal to half the equipped monster's
ATK (the new HalfEquippedHostAtk value source). Last blocker of Tea Gardner (WCT2004).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1  # A controls Kiseitai (defender); B is the turn player (attacker)


def _fresh(tp=B, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def test_kiseitai_equips_to_attacker_and_fizzles_the_attack():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    kis = _spawn(s, "Kiseitai", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(attacker.iid, kis.iid), B)
    assert kis.zone is Zone.SPELL_TRAP
    assert kis.equipped_to == attacker.iid
    assert attacker.zone is Zone.MONSTER  # attack fizzled, attacker unharmed
    assert s.players[A].life_points == 8000
    assert s.players[B].life_points == 8000


def test_kiseitai_gains_half_host_atk_on_opponents_standby():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    kis = _spawn(s, "Kiseitai", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(attacker.iid, kis.iid), B)
    assert kis.equipped_to == attacker.iid
    # B (the equipped monster's controller, A's opponent) reaches their Standby Phase.
    s.phase = Phase.STANDBY
    eng._standby_phase(B)
    assert s.players[A].life_points == 8000 + 2500 // 2  # +1250
    assert kis.zone is Zone.SPELL_TRAP  # Kiseitai stays attached and keeps paying out
    assert attacker.zone is Zone.MONSTER  # the host is not destroyed (unlike Blast Sphere)


def test_kiseitai_does_not_gain_on_its_own_controllers_standby():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)
    kis = _spawn(s, "Kiseitai", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(attacker.iid, kis.iid), B)
    s.phase = Phase.STANDBY
    eng._standby_phase(A)  # A's own Standby — the "opponent's Standby" effect must not fire
    assert s.players[A].life_points == 8000


def test_kiseitai_inert_before_it_equips():
    s = _fresh(phase=Phase.STANDBY)
    # Face-up (passes the standby scan's is-face-up filter) but not yet an Equip Card.
    _spawn(s, "Kiseitai", A, 0, Position.FACE_UP_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    eng._standby_phase(B)
    assert s.players[A].life_points == 8000  # requires_equipped gate keeps it inert
