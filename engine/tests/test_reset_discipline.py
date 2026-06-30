"""Reset-discipline tests (inspired by ygopro-core's RESET_* model).

Every per-instance transient flag belongs to exactly one reset bucket with one clearer:
  * field-scoped (RESET_LEAVE)        -> ``GameState._clear_field_flags``
  * per-turn (RESET_SELF/OPPO_TURN)   -> ``CardInstance.reset_turn_flags`` (both players,
                                          fired at the start of every turn)
  * phase-scoped (RESET_PHASE)        -> End-Phase temp-stat / end-phase-destroy clears
  * chain-scoped (RESET_CHAIN)        -> chain cleanup

The first test is a *guard*: it reflectively mutates every non-structural ``CardInstance``
field and asserts ``_clear_field_flags`` resets it — so a future batch that adds a
field-scoped flag without clearing it (the leak class the post-Batch-82 audit found, e.g.
``perm_atk``/``position_locked_until``) fails here instead of silently corrupting a revived
copy. The other two pin the audit fixes #5 (``summoned_this_turn`` cross-turn leak) and #6
(a negated attack consuming the attack).
"""

from __future__ import annotations

import dataclasses

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import CardInstance, GameState

reg = CardRegistry.load_csv()

# Structural identity/location fields — not leak-prone per-instance flags.
PERSISTENT = {"iid", "card", "owner", "controller", "zone", "zone_index", "position"}


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _default_of(f):
    if f.default is not dataclasses.MISSING:
        return f.default
    return f.default_factory()


# ------------------------------------------------------- reflective leave-the-field guard


def test_clear_field_flags_resets_every_field_scoped_transient():
    s = _fresh()
    inst = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    fields = [f for f in dataclasses.fields(CardInstance) if f.name not in PERSISTENT]
    # Mutate every non-structural field to a non-default sentinel.
    for f in fields:
        d = _default_of(f)
        if isinstance(d, bool):
            setattr(inst, f.name, True)
        elif isinstance(d, int):
            setattr(inst, f.name, 7)
        elif isinstance(d, list):
            setattr(inst, f.name, [9])
        elif isinstance(d, dict):
            setattr(inst, f.name, {"x": 1})
        else:  # default None
            setattr(inst, f.name, 7)
    s._clear_field_flags(inst)
    leaked = [f.name for f in fields if getattr(inst, f.name) != _default_of(f)]
    assert not leaked, f"field-scoped flags not reset on leaving the field: {leaked}"


# ----------------------------------------------------- #5: summoned_this_turn cross-turn


def test_summoned_this_turn_does_not_leak_into_the_opponents_turn():
    s = _fresh(tp=0)
    opp = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    opp.summoned_this_turn = True  # summoned on player 1's previous turn
    Engine(s, [Agent(), Agent()])._begin_turn(0)  # player 0's turn begins
    assert opp.summoned_this_turn is False  # a new turn -> no longer "summoned this turn"


def test_begin_turn_resets_both_players_per_turn_flags():
    s = _fresh(tp=0)
    mine = s.spawn_on_field(reg.get("Celtic Guardian"), 0, 0, Position.FACE_UP_ATTACK)
    theirs = s.spawn_on_field(reg.get("Gemini Elf"), 1, 0, Position.FACE_UP_ATTACK)
    for m in (mine, theirs):
        m.attacked_this_turn = True
        m.attacks_made_this_turn = 1
    Engine(s, [Agent(), Agent()])._begin_turn(0)
    assert mine.attacks_made_this_turn == 0 and not mine.attacked_this_turn
    assert theirs.attacks_made_this_turn == 0 and not theirs.attacked_this_turn


# ----------------------------------------------------- #6: a negated attack is consumed


class _NegateOnce(Agent):
    """Activates the first response option exactly once (to fire a set Negate Attack)."""

    def __init__(self):
        self.fired = False

    def respond(self, state, options, event):
        if not self.fired and options:
            self.fired = True
            return options[0]
        return None


def test_negated_attack_consumes_the_attack_no_replay():
    s = _fresh(tp=0, phase=Phase.BATTLE)
    attacker = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    target = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    trap = s.create_instance(reg.get("Negate Attack"), owner=1, zone=Zone.HAND)
    s.players[1].hand.append(trap.iid)
    idx = s.first_empty_spell_trap_zone(1)
    s.place_spell_trap(trap.iid, 1, idx, Position.FACE_DOWN)
    trap.set_on_turn = s.turn_count - 1  # set earlier -> activatable now
    eng = Engine(s, [Agent(), _NegateOnce()])  # player 1 (defender) negates
    eng._declare_attack(DeclareAttack(attacker.iid, target.iid), 0)
    assert s.attack_negated
    # The attack was consumed (no replay): a single-attack monster can't swing again.
    assert attacker.attacks_made_this_turn == 1
