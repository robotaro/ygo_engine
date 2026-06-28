"""Slice 15 tests: Gemini (Dual) monsters. A Gemini is a Normal Monster — its
effect is inert — until you spend a 2nd Normal Summon on the face-up card
("Gemini Summon"), which unlocks the effect. It re-locks if it leaves the field.
Goggle Golem demonstrates it: ATK 1500 normally, 2100 once Gemini Summoned."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import GeminiSummon, NormalSummon, apply, legal_actions
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()
GEMINI = "Goggle Golem"  # Lv4 EARTH Rock 1500/500 -> 2100 ATK when Gemini Summoned


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _gemini_summons(s, player):
    return [a for a in legal_actions(s, player) if isinstance(a, GeminiSummon)]


# --------------------------------------------------------------------------- #
#  Treated as a Normal Monster until Gemini Summoned
# --------------------------------------------------------------------------- #
def test_gemini_effect_inert_until_summoned():
    s = GameState.new(("A", "B"), seed=0)
    g = s.spawn_on_field(reg.get(GEMINI), 0, 0, Position.FACE_UP_ATTACK)
    assert not s.inst(g.iid).gemini_unlocked
    assert not s.inst(g.iid).effects_active  # a locked Gemini's effects don't function
    assert s.effective_attack(g.iid) == 1500  # the self-boost is suppressed


def test_gemini_summon_unlocks_the_effect():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    g = s.spawn_on_field(reg.get(GEMINI), 0, 0, Position.FACE_UP_ATTACK)

    summons = _gemini_summons(s, 0)
    assert [a.iid for a in summons] == [g.iid]
    apply(s, summons[0])

    assert s.inst(g.iid).gemini_unlocked
    assert s.inst(g.iid).effects_active
    assert s.effective_attack(g.iid) == 2100  # 1500 + 600 self-layer now live
    assert s.normal_summon_used  # it consumed the turn's Normal Summon


# --------------------------------------------------------------------------- #
#  Gemini Summon is a Normal Summon (once per turn)
# --------------------------------------------------------------------------- #
def test_gemini_summon_uses_the_normal_summon_for_the_turn():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get(GEMINI), 0, 0, Position.FACE_UP_ATTACK)
    _in_hand(s, "Summoned Skull", 0)  # something we could otherwise Normal Summon

    s.normal_summon_used = True  # already summoned this turn
    assert _gemini_summons(s, 0) == []  # no second Normal Summon available


def test_no_gemini_summon_for_a_face_down_gemini():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get(GEMINI), 0, 0, Position.FACE_DOWN_DEFENSE)
    assert _gemini_summons(s, 0) == []  # must be face-up to Gemini Summon


def test_already_unlocked_gemini_is_not_offered_again():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    g = s.spawn_on_field(reg.get(GEMINI), 0, 0, Position.FACE_UP_ATTACK)
    g.gemini_unlocked = True
    assert _gemini_summons(s, 0) == []


# --------------------------------------------------------------------------- #
#  Re-locks on leaving the field
# --------------------------------------------------------------------------- #
def test_gemini_relocks_when_it_leaves_the_field():
    s = GameState.new(("A", "B"), seed=0)
    g = s.spawn_on_field(reg.get(GEMINI), 0, 0, Position.FACE_UP_ATTACK)
    g.gemini_unlocked = True
    s.send_to_graveyard(g.iid)
    assert not s.inst(g.iid).gemini_unlocked  # back to a Normal Monster in the GY


def test_normal_summoned_from_hand_starts_locked():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    g = _in_hand(s, GEMINI, 0)
    summon = next(a for a in legal_actions(s, 0) if isinstance(a, NormalSummon) and a.iid == g.iid)
    apply(s, summon)
    assert s.inst(g.iid).zone is Zone.MONSTER
    assert not s.inst(g.iid).gemini_unlocked  # first summon = a Normal Monster
    assert s.effective_attack(g.iid) == 1500


# --------------------------------------------------------------------------- #
#  Integration
# --------------------------------------------------------------------------- #
def test_bot_duel_with_gemini_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=11,
    )
    assert not duel.missing_report
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
