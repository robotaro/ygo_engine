"""The engine emits a transient ``fx`` cue at attack resolution so the web UI can
animate combat (bump + impact flash + floating damage + the dying monster's
dissolve) for *both* players — detail a plain board snapshot can't convey."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1  # B is the turn player (attacker); A defends


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, B, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _attack_fx(events):
    hits = [e for e in events if e.get("kind") == "attack"]
    assert len(hits) == 1, f"expected one attack fx, got {events}"
    return hits[0]


def test_attack_fx_reports_destruction_and_battle_damage():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    defender = _spawn(s, "Battle Ox", A, 0)  # 1700 ATK, face-up attack
    events: list[dict] = []
    eng = Engine(s, [Agent(), Agent()], fx=events.append)

    eng._declare_attack(DeclareAttack(attacker.iid, defender.iid), B)

    fx = _attack_fx(events)
    assert fx["attacker"] == attacker.iid
    assert fx["target"] == defender.iid
    assert fx["destroyed"] == [defender.iid]
    assert fx["damage"] == [800, 0]  # seat A took 2500 - 1700, seat B took none


def test_direct_attack_fx_has_no_target_and_full_damage():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK, no blockers
    events: list[dict] = []
    eng = Engine(s, [Agent(), Agent()], fx=events.append)

    eng._declare_attack(DeclareAttack(attacker.iid, None), B)

    fx = _attack_fx(events)
    assert fx["attacker"] == attacker.iid
    assert fx["target"] is None
    assert fx["destroyed"] == []
    assert fx["damage"] == [2500, 0]
