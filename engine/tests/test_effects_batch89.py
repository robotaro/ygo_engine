"""Effects Batch 89: the Exodia package — highest-leverage deck-coverage move.

- Exodia the Forbidden One: NO effect entry — the five "Forbidden One" pieces win the
  Duel via the engine kernel (state.exodia_winner). deckbuild._KERNEL_IMPLEMENTED now
  counts the head as functional (it was a false negative in the coverage metric).
- Big Eye (Flip): look at the top 5 of your Deck and reorder — the headless engine
  surfaces the highest-ATK monster among them to the top (drawn next).
- Backup Soldier (Normal Trap): while 5+ monsters sit in your GY, add up to 3 non-Effect
  monsters with <=1500 ATK from the GY to your hand.
- Buster Blader: gains 500 ATK for each Dragon the opponent controls or has in their GY.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.deckbuild import is_functional
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _to_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _deck_push(s, player, name):
    """Append to the deck (top of deck == end of list, drawn first)."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


# ----------------------------------------------------------------- Exodia (kernel win)


def test_exodia_head_counts_as_functional():
    # The win condition lives in the kernel, so the head must not read as "dead".
    assert is_functional(reg.get("Exodia the Forbidden One"))
    for limb in (
        "Right Arm of the Forbidden One",
        "Left Arm of the Forbidden One",
        "Right Leg of the Forbidden One",
        "Left Leg of the Forbidden One",
    ):
        assert is_functional(reg.get(limb))


def test_assembling_exodia_wins_the_duel():
    s = _fresh()
    for n in (
        "Exodia the Forbidden One",
        "Right Arm of the Forbidden One",
        "Left Arm of the Forbidden One",
        "Right Leg of the Forbidden One",
        "Left Leg of the Forbidden One",
    ):
        i = s.create_instance(reg.get(n), owner=0, zone=Zone.HAND)
        s.players[0].hand.append(i.iid)
    eng = Engine(s, [Agent(), Agent()])
    eng._check_exodia()
    assert eng.result is not None and eng.result.winner == 0


# --------------------------------------------------------------------------- Big Eye


def test_big_eye_surfaces_the_best_monster_to_the_top():
    s = _fresh()
    big = _spawn(s, "Big Eye", 0, 0)
    # 5-card deck; Summoned Skull (2500) is the strongest among the top-5 window.
    for n in ["Kuriboh", "Mystical Elf", "Summoned Skull", "Celtic Guardian", "Sangan"]:
        _deck_push(s, 0, n)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(big.iid)
    drawn = s.draw(0, 1)
    assert s.inst(drawn[0]).name == "Summoned Skull"  # reordered to the top


def test_big_eye_no_op_on_empty_deck():
    s = _fresh()
    big = _spawn(s, "Big Eye", 0, 0)
    s.players[0].deck.clear()
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(big.iid)  # must not raise
    assert s.players[0].deck == []


# --------------------------------------------------------------------- Backup Soldier


def test_backup_soldier_condition_needs_five_gy_monsters():
    cond = EFFECTS["Backup Soldier"][0].condition
    s = _fresh()
    for _ in range(4):
        _to_gy(s, "Celtic Guardian", 0)
    assert cond(s, 0) is False  # only 4 monsters in the GY
    _to_gy(s, "Mystical Elf", 0)
    assert cond(s, 0) is True  # 5 — armed


def test_backup_soldier_recovers_up_to_three_small_vanilla_monsters():
    s = _fresh()
    trap = _faceup_st(s, "Backup Soldier", 0)
    eligible = ["Celtic Guardian", "Mystical Elf", "Petit Angel"]  # vanilla, <=1500 ATK
    for n in eligible:
        _to_gy(s, n, 0)
    _to_gy(s, "Summoned Skull", 0)  # vanilla but 2500 ATK -> excluded
    _to_gy(s, "Sangan", 0)  # an Effect Monster -> excluded
    before = set(s.players[0].hand)
    resolve_effect(s, EFFECTS["Backup Soldier"][0], trap.iid)
    gained = [s.inst(i).name for i in s.players[0].hand if i not in before]
    assert sorted(gained) == sorted(eligible)  # exactly the 3 eligible, the others stay
    assert {s.inst(i).name for i in s.players[0].graveyard} == {"Summoned Skull", "Sangan"}


# ----------------------------------------------------------------------- Buster Blader


def test_buster_blader_gains_per_opponent_dragon_on_field():
    s = _fresh()
    bb = _spawn(s, "Buster Blader", 0, 0)
    base = s.inst(bb.iid).card.attack
    assert s.effective_attack(bb.iid) == base  # no opposing Dragons yet
    _spawn(s, "Blue-Eyes White Dragon", 1, 0)
    assert s.effective_attack(bb.iid) == base + 500


def test_buster_blader_counts_dragons_in_opponent_graveyard_too():
    s = _fresh()
    bb = _spawn(s, "Buster Blader", 0, 0)
    base = s.inst(bb.iid).card.attack
    _spawn(s, "Blue-Eyes White Dragon", 1, 0)  # one on the field
    _to_gy(s, "Blue-Eyes White Dragon", 1)  # one in the GY
    _to_gy(s, "Summoned Skull", 1)  # a Fiend in the GY -> does not count
    assert s.effective_attack(bb.iid) == base + 1000


def test_buster_blader_ignores_own_dragons():
    s = _fresh()
    bb = _spawn(s, "Buster Blader", 0, 0)
    base = s.inst(bb.iid).card.attack
    _spawn(s, "Blue-Eyes White Dragon", 0, 1)  # MY Dragon — not the opponent's
    assert s.effective_attack(bb.iid) == base


def test_buster_blader_boost_suppressed_under_skill_drain():
    s = _fresh()
    bb = _spawn(s, "Buster Blader", 0, 0)
    _spawn(s, "Blue-Eyes White Dragon", 1, 0)
    _faceup_st(s, "Skill Drain", 1)  # negates face-up monster effects
    assert s.effective_attack(bb.iid) == s.inst(bb.iid).card.attack  # back to base
