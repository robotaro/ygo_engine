"""Monster Ignition effects are reachable by the client contract and the CPU.

serialize.legal_to_dict must surface ActivateMonsterEffect (so the web client can
offer it) and match_intent must resolve an "activateMonster" intent back to the
action; GreedyAgent must fire a no-downside monster Ignition effect. Without these
the Royal Magical Library / Breaker family were unplayable by anyone but RandomAgent."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, Pass, legal_actions
from ygo.serialize import legal_to_dict, match_intent
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _library_state():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    lib = s.spawn_on_field(reg.get("Royal Magical Library"), 0, 0, Position.FACE_UP_ATTACK)
    lib.counters["spell"] = 3  # enough to pay the draw effect's counter cost
    return s, lib


def test_legal_to_dict_exposes_monster_activatable():
    s, lib = _library_state()
    d = legal_to_dict(s, 0, with_pass=True)
    assert str(lib.iid) in d["monsterActivatable"]  # the client can now offer it
    assert d["monsterActivatable"][str(lib.iid)] == [[]]  # one activation, no target


def test_match_intent_resolves_an_activate_monster_intent():
    s, lib = _library_state()
    legal = legal_actions(s, 0)
    action = match_intent({"kind": "activateMonster", "iid": lib.iid, "targets": []}, legal, s)
    assert isinstance(action, ActivateMonsterEffect) and action.iid == lib.iid


def test_match_intent_rejects_an_illegal_activate_monster():
    s, lib = _library_state()
    lib.counters["spell"] = 1  # no longer payable -> not legal
    legal = legal_actions(s, 0)
    assert match_intent({"kind": "activateMonster", "iid": lib.iid, "targets": []}, legal, s) is None


def test_greedy_agent_fires_a_monster_ignition_effect():
    s, lib = _library_state()
    legal = legal_actions(s, 0) + [Pass()]
    action = GreedyAgent().decide(s, legal)
    assert isinstance(action, ActivateMonsterEffect) and action.iid == lib.iid
