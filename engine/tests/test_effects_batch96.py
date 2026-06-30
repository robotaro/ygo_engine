"""Effects Batch 96: the Weevil insect-trap pair.

- Acid Trap Hole: a Normal Trap — target 1 face-down Defense-Position monster, flip it
  up, then destroy it if its DEF is 2000 or less; otherwise set it back face-down.
- Drill Bug: when it inflicts battle damage to the opponent, fetch 1 "Parasite Paracide"
  from your Deck, shuffle, and place it on top of your Deck.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, legal_actions, resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _set_st(s, name, player):
    """Set a Spell/Trap face-down on an earlier turn so it is legally activatable now."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _in_deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


# ---------------------------------------------------------------- Acid Trap Hole


def test_acid_trap_hole_destroys_low_defense():
    s = _fresh()
    trap = _faceup_st(s, "Acid Trap Hole", A)
    victim = _spawn(s, "7 Colored Fish", B, 0, Position.FACE_DOWN_DEFENSE)  # DEF 800 <= 2000
    effect = EFFECTS["Acid Trap Hole"][0]
    resolve_effect(s, effect, trap.iid, targets=(victim.iid,))
    assert victim.iid in s.players[B].graveyard  # destroyed
    assert s.inst(victim.iid).zone is Zone.GRAVEYARD


def test_acid_trap_hole_returns_high_defense_face_down():
    s = _fresh()
    trap = _faceup_st(s, "Acid Trap Hole", A)
    # Labyrinth Wall: DEF 3000 > 2000 -> survives, returned face-down
    wall = _spawn(s, "Labyrinth Wall", B, 0, Position.FACE_DOWN_DEFENSE)
    effect = EFFECTS["Acid Trap Hole"][0]
    resolve_effect(s, effect, trap.iid, targets=(wall.iid,))
    assert s.inst(wall.iid).zone is Zone.MONSTER  # not destroyed
    assert s.inst(wall.iid).position is Position.FACE_DOWN_DEFENSE  # set back down


def test_acid_trap_hole_only_targets_face_down():
    s = _fresh(tp=A)
    inst = _set_st(s, "Acid Trap Hole", A)  # Set face-down, activatable this turn
    _spawn(s, "7 Colored Fish", B, 0, Position.FACE_UP_ATTACK)  # face-up -> not a legal target
    acts = [a for a in legal_actions(s, A) if getattr(a, "iid", None) == inst.iid]
    assert not acts  # no face-down monster to target -> the trap isn't offered
    # give it a face-down monster and it becomes activatable
    _spawn(s, "Summoned Skull", B, 1, Position.FACE_DOWN_DEFENSE)
    acts = [a for a in legal_actions(s, A) if getattr(a, "iid", None) == inst.iid]
    assert acts


# -------------------------------------------------------------------- Drill Bug


def test_drill_bug_sets_parasite_on_top_after_battle_damage():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    bug = _spawn(s, "Drill Bug", A, 0)  # 1100 ATK
    parasite = _in_deck(s, "Parasite Paracide", A)
    _in_deck(s, "7 Colored Fish", A)
    _in_deck(s, "Summoned Skull", A)
    s.players[B].life_points = 8000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(bug.iid, None), A)  # direct attack -> battle damage
    assert s.players[B].life_points == 8000 - 1100
    assert s.players[A].deck[-1] == parasite.iid  # Parasite is now on top (end of deck)


def test_drill_bug_quiet_with_no_parasite_in_deck():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    bug = _spawn(s, "Drill Bug", A, 0)
    _in_deck(s, "7 Colored Fish", A)
    s.players[B].life_points = 8000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(bug.iid, None), A)
    assert s.players[B].life_points == 8000 - 1100  # damage still happens, no crash
