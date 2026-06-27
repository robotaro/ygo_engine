"""Slice 4 tests: Flip and Trigger monster effects, routed through the Chain."""

from __future__ import annotations

from ygo.agents import Agent, GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, FlipSummon, Pass
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()


class FlipThenPass(Agent):
    """Flip Summon a specific monster once, then pass."""

    def __init__(self, iid):
        self.iid = iid
        self.done = False

    def decide(self, state, legal):
        if not self.done:
            flip = next((a for a in legal if isinstance(a, FlipSummon) and a.iid == self.iid), None)
            if flip is not None:
                self.done = True
                return flip
        return next(a for a in legal if isinstance(a, Pass))


def _spawn(state, name, player, index, position):
    return state.spawn_on_field(reg.get(name), player, index, position)


# --------------------------------------------------------------------------- #
#  Flip effects
# --------------------------------------------------------------------------- #
def test_man_eater_bug_flip_summon_destroys_strongest():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, 0, Phase.MAIN_1
    meb = _spawn(s, "Man-Eater Bug", 0, 0, Position.FACE_DOWN_DEFENSE)
    meb.summoned_this_turn = False  # Set on an earlier turn -> may Flip Summon
    foe = _spawn(s, "Blue-Eyes White Dragon", 1, 0, Position.FACE_UP_ATTACK)

    Engine(s, [FlipThenPass(meb.iid), GreedyAgent()])._interactive_phase(0)
    assert s.inst(meb.iid).position is Position.FACE_UP_ATTACK
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # the flip effect destroyed it


def test_man_eater_bug_destroys_attacker_when_attacked():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    attacker = _spawn(s, "Blue-Eyes White Dragon", 0, 0, Position.FACE_UP_ATTACK)  # 3000
    meb = _spawn(s, "Man-Eater Bug", 1, 0, Position.FACE_DOWN_DEFENSE)  # DEF 600

    Engine(s, [GreedyAgent(), GreedyAgent()])._declare_attack(DeclareAttack(attacker.iid, meb.iid), 0)
    # MEB is crushed by battle, but its Flip Effect still resolves and takes the attacker with it.
    assert s.inst(meb.iid).zone is Zone.GRAVEYARD
    assert s.inst(attacker.iid).zone is Zone.GRAVEYARD


def test_controller_chooses_man_eater_bug_target():
    # Two opponent monsters; the player deliberately picks the WEAKER one,
    # proving the target is a choice (not auto "strongest").
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, 0, Phase.MAIN_1
    meb = _spawn(s, "Man-Eater Bug", 0, 0, Position.FACE_DOWN_DEFENSE)
    meb.summoned_this_turn = False
    strong = _spawn(s, "Blue-Eyes White Dragon", 1, 0, Position.FACE_UP_ATTACK)  # 3000
    weak = _spawn(s, "Battle Ox", 1, 1, Position.FACE_UP_ATTACK)  # 1700

    class PickWeak(FlipThenPass):
        def choose_targets(self, state, source_iid, spec, candidates):
            return (weak.iid,)

    Engine(s, [PickWeak(meb.iid), GreedyAgent()])._interactive_phase(0)
    assert s.inst(weak.iid).zone is Zone.GRAVEYARD  # chosen target destroyed
    assert s.inst(strong.iid).zone is Zone.MONSTER  # the stronger one survives


def test_magician_of_faith_returns_a_spell_from_graveyard():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, 0, Phase.MAIN_1
    mof = _spawn(s, "Magician of Faith", 0, 0, Position.FACE_DOWN_DEFENSE)
    mof.summoned_this_turn = False
    spell = s.create_instance(reg.get("Dark Hole"), owner=0, zone=Zone.GRAVEYARD)
    s.players[0].graveyard.append(spell.iid)

    Engine(s, [FlipThenPass(mof.iid), GreedyAgent()])._interactive_phase(0)
    assert spell.iid in s.players[0].hand
    assert spell.iid not in s.players[0].graveyard


# --------------------------------------------------------------------------- #
#  Trigger effect: Sangan
# --------------------------------------------------------------------------- #
def test_sangan_searches_when_destroyed_by_battle():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    attacker = _spawn(s, "Blue-Eyes White Dragon", 0, 0, Position.FACE_UP_ATTACK)
    sangan = _spawn(s, "Sangan", 1, 0, Position.FACE_UP_ATTACK)  # 1000 ATK
    big = s.create_instance(reg.get("Battle Ox"), owner=1, zone=Zone.DECK)  # 1700 -> ineligible
    small = s.create_instance(reg.get("Mystical Elf"), owner=1, zone=Zone.DECK)  # 800 -> eligible
    s.players[1].deck += [big.iid, small.iid]

    Engine(s, [GreedyAgent(), GreedyAgent()])._declare_attack(DeclareAttack(attacker.iid, sangan.iid), 0)
    assert s.inst(sangan.iid).zone is Zone.GRAVEYARD
    assert small.iid in s.players[1].hand  # searched the eligible (ATK <= 1500) monster
    assert big.iid not in s.players[1].hand


def test_sangan_searches_when_tributed():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, 0, Phase.MAIN_1
    sangan = _spawn(s, "Sangan", 0, 0, Position.FACE_UP_ATTACK)
    small = s.create_instance(reg.get("Mystical Elf"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(small.iid)
    tribute_monster = s.create_instance(reg.get("Summoned Skull"), owner=0, zone=Zone.HAND)  # L6
    s.players[0].hand.append(tribute_monster.iid)

    from ygo.moves import NormalSummon

    class TributeSangan(Agent):
        def decide(self, state, legal):
            for a in legal:
                if isinstance(a, NormalSummon) and a.iid == tribute_monster.iid and sangan.iid in a.tributes:
                    return a
            return next(a for a in legal if isinstance(a, Pass))

    Engine(s, [TributeSangan(), GreedyAgent()])._interactive_phase(0)
    assert s.inst(sangan.iid).zone is Zone.GRAVEYARD  # tributed
    assert small.iid in s.players[0].hand  # Sangan still triggered


# --------------------------------------------------------------------------- #
#  Integration
# --------------------------------------------------------------------------- #
def test_bot_duel_with_effect_monsters_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=8,
    )
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
