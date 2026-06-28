"""Slice 16 tests: Union monsters. Once per turn, a face-up Union you control can
equip itself to a valid host (becoming an Equip Card that boosts the host) or
unequip and Special Summon itself back. Y-Dragon Head equips to X-Head Cannon and
grants +400 ATK/DEF."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    UnionEquip,
    UnionUnequip,
    apply,
    legal_actions,
    union_hosts,
)
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()
UNION, HOST = "Y-Dragon Head", "X-Head Cannon"


def _board(seed=0, turn=2, player=0):
    s = GameState.new(("A", "B"), seed=seed)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, turn, player
    return s


def _equips(s, player):
    return [a for a in legal_actions(s, player) if isinstance(a, UnionEquip)]


def _unequips(s, player):
    return [a for a in legal_actions(s, player) if isinstance(a, UnionUnequip)]


# --------------------------------------------------------------------------- #
#  Equip
# --------------------------------------------------------------------------- #
def test_union_equips_to_its_host_and_boosts_it():
    s = _board()
    host = s.spawn_on_field(reg.get(HOST), 0, 0, Position.FACE_UP_ATTACK)  # 1800
    union = s.spawn_on_field(reg.get(UNION), 0, 1, Position.FACE_UP_ATTACK)

    assert union_hosts(s, 0, union.iid) == [host.iid]
    equips = _equips(s, 0)
    assert [(a.union_iid, a.host_iid) for a in equips] == [(union.iid, host.iid)]
    apply(s, equips[0])

    assert s.inst(union.iid).zone is Zone.SPELL_TRAP  # now an Equip Card
    assert s.inst(union.iid).equipped_to == host.iid
    assert union.iid not in s.players[0].monster_zones  # left the Monster Zone
    assert s.effective_attack(host.iid) == 2200  # 1800 + 400
    assert s.effective_defense(host.iid) == 1900  # 1500 + 400


def test_union_only_equips_to_the_named_host():
    s = _board()
    s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)  # wrong host
    union = s.spawn_on_field(reg.get(UNION), 0, 1, Position.FACE_UP_ATTACK)
    assert union_hosts(s, 0, union.iid) == []
    assert _equips(s, 0) == []


def test_host_cannot_carry_two_unions():
    s = _board()
    host = s.spawn_on_field(reg.get(HOST), 0, 0, Position.FACE_UP_ATTACK)
    u1 = s.spawn_on_field(reg.get(UNION), 0, 1, Position.FACE_UP_ATTACK)
    u2 = s.spawn_on_field(reg.get(UNION), 0, 2, Position.FACE_UP_ATTACK)
    apply(s, UnionEquip(u1.iid, host.iid))
    assert union_hosts(s, 0, u2.iid) == []  # host already carries a Union


# --------------------------------------------------------------------------- #
#  Once per turn
# --------------------------------------------------------------------------- #
def test_union_acts_once_per_turn():
    s = _board()
    host = s.spawn_on_field(reg.get(HOST), 0, 0, Position.FACE_UP_ATTACK)
    union = s.spawn_on_field(reg.get(UNION), 0, 1, Position.FACE_UP_ATTACK)
    apply(s, UnionEquip(union.iid, host.iid))
    assert s.inst(union.iid).union_acted_on_turn == 2
    assert _unequips(s, 0) == []  # can't immediately unequip the same turn

    s.turn_count = 3  # next turn: it may unequip
    assert [a.union_iid for a in _unequips(s, 0)] == [union.iid]


# --------------------------------------------------------------------------- #
#  Unequip
# --------------------------------------------------------------------------- #
def test_union_unequips_back_to_the_monster_zone():
    s = _board()
    host = s.spawn_on_field(reg.get(HOST), 0, 0, Position.FACE_UP_ATTACK)
    union = s.spawn_on_field(reg.get(UNION), 0, 1, Position.FACE_UP_ATTACK)
    apply(s, UnionEquip(union.iid, host.iid))
    s.turn_count = 3

    apply(s, _unequips(s, 0)[0])
    assert s.inst(union.iid).zone is Zone.MONSTER
    assert s.inst(union.iid).equipped_to is None
    assert union.iid in s.players[0].monster_zones
    assert s.effective_attack(host.iid) == 1800  # boost removed


def test_union_follows_host_to_graveyard_when_host_destroyed():
    s = _board()
    host = s.spawn_on_field(reg.get(HOST), 0, 0, Position.FACE_UP_ATTACK)
    union = s.spawn_on_field(reg.get(UNION), 0, 1, Position.FACE_UP_ATTACK)
    eng = Engine(s, [GreedyAgent(), GreedyAgent()])
    apply(s, UnionEquip(union.iid, host.iid))

    s.send_to_graveyard(host.iid)
    eng._check_field_to_gy_triggers()  # orphaned-Equip cleanup
    assert s.inst(union.iid).zone is Zone.GRAVEYARD


def test_union_relocks_acted_flag_when_it_leaves_the_field():
    s = _board()
    union = s.spawn_on_field(reg.get(UNION), 0, 1, Position.FACE_UP_ATTACK)
    union.union_acted_on_turn = 2
    s.send_to_graveyard(union.iid)
    assert s.inst(union.iid).union_acted_on_turn is None


# --------------------------------------------------------------------------- #
#  Integration
# --------------------------------------------------------------------------- #
def test_bot_duel_with_union_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=13,
    )
    assert not duel.missing_report
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
