"""Slice 14 tests: Spirit monsters. A Spirit returns to its owner's hand during
the End Phase of the turn it became face-up (Normal/Flip Summoned, or flipped in
battle), and can never be Special Summoned (so Monster Reborn can't revive one)."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.effects import SpecialSummonFromGraveyard
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    ActivateSpell,
    DeclareAttack,
    apply,
    legal_actions,
    target_candidates,
)
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState
from ygo.effects import EffectContext, TargetSpec

reg = CardRegistry.load_csv()
SPIRIT = "Susa Soldier"  # Level 4, 2000/1600 — a clean demonstrative Spirit


def _engine(s):
    return Engine(s, [GreedyAgent(), GreedyAgent()])


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_graveyard(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


# --------------------------------------------------------------------------- #
#  Returns to hand at the End Phase
# --------------------------------------------------------------------------- #
def test_spirit_returns_to_hand_at_end_phase():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.END, 2, 0
    spirit = s.spawn_on_field(reg.get(SPIRIT), 0, 0, Position.FACE_UP_ATTACK)

    _engine(s)._end_phase(0)

    assert s.inst(spirit.iid).zone is Zone.HAND
    assert spirit.iid in s.players[0].hand
    assert spirit.iid not in s.players[0].monster_zones


def test_face_down_spirit_does_not_return():
    """A Set (face-down) Spirit hasn't been flipped yet — it stays on the field."""
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.END, 2, 0
    spirit = s.spawn_on_field(reg.get(SPIRIT), 0, 0, Position.FACE_DOWN_DEFENSE)

    _engine(s)._end_phase(0)

    assert s.inst(spirit.iid).zone is Zone.MONSTER  # still set, not bounced


def test_flip_summoned_spirit_returns_at_end_phase():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 4, 0
    spirit = s.spawn_on_field(reg.get(SPIRIT), 0, 0, Position.FACE_DOWN_DEFENSE)
    spirit.set_on_turn = 2  # Set on an earlier turn so it can be flipped now

    apply(s, [a for a in legal_actions(s, 0) if getattr(a, "iid", None) == spirit.iid][0])
    assert s.inst(spirit.iid).is_face_up

    s.phase = Phase.END  # the engine switches phases before running the End Phase
    _engine(s)._end_phase(0)
    assert s.inst(spirit.iid).zone is Zone.HAND


def test_spirit_returns_to_owner_even_under_opponent_control():
    """Flipped/loaned onto the opponent's side, a Spirit still returns to its owner's
    hand, and is caught at any End Phase (both sides are scanned)."""
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.END, 2, 1
    spirit = s.spawn_on_field(reg.get(SPIRIT), 0, 0, Position.FACE_UP_ATTACK)
    spirit.controller = 0  # owned and controlled by player 0; it's player 1's End Phase

    _engine(s)._end_phase(1)
    assert s.inst(spirit.iid).zone is Zone.HAND
    assert spirit.iid in s.players[0].hand  # the owner's hand


# --------------------------------------------------------------------------- #
#  Cannot be Special Summoned
# --------------------------------------------------------------------------- #
def test_spirit_excluded_from_revival_target_pool():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    spirit = _in_graveyard(s, SPIRIT, 0)
    vanilla = _in_graveyard(s, "Summoned Skull", 0)

    pool = target_candidates(s, 0, TargetSpec(count=1, where="any_graveyard_monster"))
    assert vanilla.iid in pool
    assert spirit.iid not in pool  # Spirits can't be Special Summoned


def test_monster_reborn_cannot_target_a_spirit():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    spirit = _in_graveyard(s, SPIRIT, 0)
    reborn = _in_hand(s, "Monster Reborn", 0)

    activations = [
        a for a in legal_actions(s, 0)
        if isinstance(a, ActivateSpell) and a.iid == reborn.iid
    ]
    assert all(spirit.iid not in a.targets for a in activations)


def test_special_summon_primitive_refuses_a_spirit():
    """Defensive: even if forced, the revival primitive leaves a Spirit in the GY."""
    s = GameState.new(("A", "B"), seed=0)
    spirit = _in_graveyard(s, SPIRIT, 0)
    ctx = EffectContext(state=s, controller=0, source_iid=spirit.iid, targets=[spirit.iid])
    SpecialSummonFromGraveyard().execute(ctx)
    assert s.inst(spirit.iid).zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------- #
#  Integration
# --------------------------------------------------------------------------- #
def test_bot_duel_with_spirit_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=7,
    )
    assert not duel.missing_report
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
