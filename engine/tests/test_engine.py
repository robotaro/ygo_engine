"""Turn-loop tests: combat math, win conditions, determinism, and fuzzing."""

from __future__ import annotations

from ygo.agents import GreedyAgent, RandomAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, apply
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

ALPHA = DECKS_DIR / "vanilla" / "beatdown_alpha.txt"
BETA = DECKS_DIR / "vanilla" / "beatdown_beta.txt"


def _battle_state(reg, attacker_name, target_name, target_pos):
    """Two monsters facing off, ready for a single attack in the Battle Phase."""
    state = GameState.new(("A", "B"), seed=0)
    state.phase = Phase.BATTLE
    state.turn_count = 2  # battle is legal (not the first turn)
    atk = state.spawn_on_field(reg.get(attacker_name), 0, 0, Position.FACE_UP_ATTACK)
    tgt = state.spawn_on_field(reg.get(target_name), 1, 0, target_pos)
    return state, atk, tgt


def test_attack_beats_weaker_attacker():
    reg = CardRegistry.load_csv()
    # Blue-Eyes (3000 ATK) attacks Battle Ox (1700 ATK)
    state, boew, ox = _battle_state(reg, "Blue-Eyes White Dragon", "Battle Ox", Position.FACE_UP_ATTACK)
    apply(state, DeclareAttack(boew.iid, ox.iid))
    assert state.inst(ox.iid).zone is Zone.GRAVEYARD  # destroyed
    assert state.players[1].life_points == 8000 - (3000 - 1700)
    assert state.players[0].monster_zones[0] == boew.iid  # attacker survives


def test_attack_into_bigger_attacker_is_suicide():
    reg = CardRegistry.load_csv()
    state, ox, boew = _battle_state(reg, "Battle Ox", "Blue-Eyes White Dragon", Position.FACE_UP_ATTACK)
    apply(state, DeclareAttack(ox.iid, boew.iid))
    assert state.inst(ox.iid).zone is Zone.GRAVEYARD  # attacker destroyed
    assert state.players[0].life_points == 8000 - (3000 - 1700)  # attacker takes the damage


def test_attack_defender_no_piercing():
    reg = CardRegistry.load_csv()
    # high-ATK attacker vs a face-up Defense monster: destroyed, but no LP damage
    state, boew, ox = _battle_state(reg, "Blue-Eyes White Dragon", "Battle Ox", Position.FACE_UP_DEFENSE)
    apply(state, DeclareAttack(boew.iid, ox.iid))
    assert state.inst(ox.iid).zone is Zone.GRAVEYARD
    assert state.players[1].life_points == 8000  # no piercing in vanilla v6.0


def test_direct_attack_reduces_life_points():
    reg = CardRegistry.load_csv()
    state = GameState.new(("A", "B"), seed=0)
    state.phase = Phase.BATTLE
    state.turn_count = 2
    boew = state.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    apply(state, DeclareAttack(boew.iid, None))
    assert state.players[1].life_points == 8000 - 3000


def test_full_duel_completes_and_is_deterministic():
    def play(seed):
        duel = new_duel(ALPHA, BETA, names=("Alpha", "Beta"), seed=seed)
        result = Engine(duel.state, [GreedyAgent(), GreedyAgent()]).run()
        return result, duel.state

    r1, s1 = play(123)
    r2, s2 = play(123)
    assert r1.winner in (0, 1, None)
    # same seed -> identical outcome
    assert (r1.winner, r1.reason) == (r2.winner, r2.reason)
    assert s1.turn_count == s2.turn_count
    assert [p.life_points for p in s1.players] == [p.life_points for p in s2.players]


def test_random_agents_never_crash_the_rules():
    # fuzz: many random duels must complete without raising
    for seed in range(15):
        duel = new_duel(ALPHA, BETA, seed=seed)
        result = Engine(
            duel.state, [RandomAgent(seed), RandomAgent(seed + 100)], max_turns=300
        ).run()
        assert result.winner in (0, 1, None)
