"""Slice 17 tests: Toon monsters. They need a face-up Toon World (pay 1000 LP) to
be Summoned and to stay on the field; they can't attack the turn they're Summoned;
and they attack the opponent directly unless the opponent controls a Toon (then
they must attack that Toon). If Toon World leaves, the Toons are destroyed."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    ActivateSpell,
    DeclareAttack,
    NormalSummon,
    apply,
    controls_toon_world,
    legal_actions,
)
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()
TOON = "Toon Gemini Elf"  # L4 1900 — a Toon monster (not a Gemini monster)


def _board(turn=2, player=0):
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, turn, player
    return s


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _toon_world(s, player=0):
    inst = s.create_instance(reg.get("Toon World"), player, Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, 0, Position.FACE_UP_ATTACK)
    return inst


def _summons(s, player, iid):
    return [a for a in legal_actions(s, player) if isinstance(a, NormalSummon) and a.iid == iid]


def _attacks(s, player, iid):
    return [a for a in legal_actions(s, player) if isinstance(a, DeclareAttack) and a.attacker == iid]


# --------------------------------------------------------------------------- #
#  Toon vs Gemini are distinct sub-types
# --------------------------------------------------------------------------- #
def test_toon_gemini_elf_is_a_toon_not_a_gemini():
    c = reg.get(TOON)
    assert c.is_toon and not c.is_gemini


# --------------------------------------------------------------------------- #
#  Need Toon World to Summon
# --------------------------------------------------------------------------- #
def test_cannot_normal_summon_a_toon_without_toon_world():
    s = _board()
    toon = _in_hand(s, TOON, 0)
    assert _summons(s, 0, toon.iid) == []  # no Toon World -> can't summon


def test_can_normal_summon_a_toon_with_toon_world():
    s = _board()
    _toon_world(s, 0)
    toon = _in_hand(s, TOON, 0)
    assert len(_summons(s, 0, toon.iid)) == 1


def test_toon_world_activation_pays_1000_life():
    s = _board()
    tw = _in_hand(s, "Toon World", 0)
    assert s.players[0].life_points == 8000
    apply(s, ActivateSpell(tw.iid))
    assert s.players[0].life_points == 7000
    assert s.inst(tw.iid).zone is Zone.SPELL_TRAP  # a Continuous Spell, stays face-up
    assert controls_toon_world(s, 0)


# --------------------------------------------------------------------------- #
#  Attacking
# --------------------------------------------------------------------------- #
def test_toon_cannot_attack_the_turn_summoned():
    s = _board()
    _toon_world(s, 0)
    toon = s.spawn_on_field(reg.get(TOON), 0, 1, Position.FACE_UP_ATTACK)
    toon.summoned_this_turn = True
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # a target exists
    s.phase = Phase.BATTLE
    assert _attacks(s, 0, toon.iid) == []  # summoning sickness for Toons


def test_toon_attacks_directly_when_opponent_has_no_toon():
    s = _board()
    _toon_world(s, 0)
    toon = s.spawn_on_field(reg.get(TOON), 0, 1, Position.FACE_UP_ATTACK)
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    s.phase = Phase.BATTLE
    targets = {a.target for a in _attacks(s, 0, toon.iid)}
    assert None in targets  # may attack directly past the opponent's monster
    assert foe.iid in targets  # ...or attack the monster, its choice


def test_toon_must_attack_opponents_toon():
    s = _board()
    _toon_world(s, 0)
    _toon_world(s, 1)
    toon = s.spawn_on_field(reg.get(TOON), 0, 1, Position.FACE_UP_ATTACK)
    opp_toon = s.spawn_on_field(reg.get(TOON), 1, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 1, Position.FACE_UP_ATTACK)
    s.phase = Phase.BATTLE
    targets = {a.target for a in _attacks(s, 0, toon.iid)}
    assert targets == {opp_toon.iid}  # forced onto the opposing Toon; no direct attack


# --------------------------------------------------------------------------- #
#  Toon World leaving destroys the Toons
# --------------------------------------------------------------------------- #
def test_toons_destroyed_when_toon_world_leaves():
    s = _board()
    tw_iid = _in_hand(s, "Toon World", 0).iid
    s.place_spell_trap(tw_iid, 0, 0, Position.FACE_UP_ATTACK)
    toon = s.spawn_on_field(reg.get(TOON), 0, 1, Position.FACE_UP_ATTACK)
    eng = Engine(s, [GreedyAgent(), GreedyAgent()])

    s.send_to_graveyard(tw_iid)  # Toon World destroyed
    eng._check_field_to_gy_triggers()
    assert s.inst(toon.iid).zone is Zone.GRAVEYARD


def test_toon_survives_while_toon_world_stays():
    s = _board()
    _toon_world(s, 0)
    toon = s.spawn_on_field(reg.get(TOON), 0, 1, Position.FACE_UP_ATTACK)
    Engine(s, [GreedyAgent(), GreedyAgent()])._check_field_to_gy_triggers()
    assert s.inst(toon.iid).zone is Zone.MONSTER  # Toon World present -> safe


# --------------------------------------------------------------------------- #
#  Integration
# --------------------------------------------------------------------------- #
def test_bot_duel_with_toon_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=17,
    )
    assert not duel.missing_report
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
