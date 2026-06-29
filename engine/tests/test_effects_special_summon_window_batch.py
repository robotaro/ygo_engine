"""Effects Batch 18: a Special Summon response window.

A Special Summon (from the hand, e.g. Cyber Dragon) now opens a Summon response
window tagged summon_kind="special", so the opponent can react. This unlocks Black
Horn of Heaven (negate a Special Summon) and is a correctness fix: Bottomless Trap
Hole now fires on Special Summons while Trap Hole (Normal/Flip only) correctly does
not. Triggers carry ``summon_kinds`` to keep each card to its kinds."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, NormalSummon, Pass, SpecialSummonFromHand, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()


class ActivateByName(Agent):
    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


class SummonThenPass(Agent):
    """Player 0: Special Summon a named monster from the hand once, then pass."""

    def __init__(self, name):
        self.name = name
        self.done = False

    def decide(self, state, legal):
        if not self.done:
            for a in legal:
                if isinstance(a, SpecialSummonFromHand) and state.inst(a.iid).card.name == self.name:
                    self.done = True
                    return a
        return next(a for a in legal if isinstance(a, Pass))

    def respond(self, state, options, event):
        return None


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _set_card(s, name, player, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = 1
    return inst


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _ss_then_window(eng, s, iid, player=0):
    apply(s, SpecialSummonFromHand(iid))
    eng._response_window({"kind": "summon", "player": player, "monster": iid, "summon_kind": "special"})


def _normal_then_window(eng, s, iid, player=0):
    apply(s, NormalSummon(iid))
    eng._response_window({"kind": "summon", "player": player, "monster": iid, "summon_kind": "normal"})


# --- the real wiring: the main loop opens a window for a Special Summon ----------
def test_engine_opens_a_special_summon_window_and_black_horn_negates():
    s = _fresh()
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # enables Cyber Dragon
    cyber = _in_hand(s, "Cyber Dragon", 0)
    horn = _set_card(s, "Black Horn of Heaven", 1, 0)
    eng = Engine(s, [SummonThenPass("Cyber Dragon"), ActivateByName("Black Horn of Heaven")])
    eng._interactive_phase(0)
    assert s.inst(cyber.iid).zone is Zone.GRAVEYARD  # Special Summon negated -> destroyed
    assert s.inst(horn.iid).zone is Zone.GRAVEYARD


# --- Black Horn only negates Special Summons -----------------------------------
def test_black_horn_does_not_fire_on_a_normal_summon():
    s = _fresh()
    elf = _in_hand(s, "Mystical Elf", 0)
    horn = _set_card(s, "Black Horn of Heaven", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Black Horn of Heaven")])
    _normal_then_window(eng, s, elf.iid)
    assert s.inst(elf.iid).zone is Zone.MONSTER  # Normal Summon is not a valid target
    assert s.inst(horn.iid).zone is Zone.SPELL_TRAP  # never activated


# --- correctness: Trap Hole ignores Special Summons, Bottomless catches them -----
def test_trap_hole_does_not_fire_on_a_special_summon():
    s = _fresh()
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    cyber = _in_hand(s, "Cyber Dragon", 0)  # 2100 ATK
    trap = _set_card(s, "Trap Hole", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Trap Hole")])
    _ss_then_window(eng, s, cyber.iid)
    assert s.inst(cyber.iid).zone is Zone.MONSTER  # Trap Hole is Normal/Flip only
    assert s.inst(trap.iid).zone is Zone.SPELL_TRAP


def test_bottomless_trap_hole_fires_on_a_special_summon():
    s = _fresh()
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    cyber = _in_hand(s, "Cyber Dragon", 0)  # 2100 ATK >= 1500
    bottomless = _set_card(s, "Bottomless Trap Hole", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Bottomless Trap Hole")])
    _ss_then_window(eng, s, cyber.iid)
    assert s.inst(cyber.iid).zone is Zone.BANISHED  # Bottomless banishes a Special Summon
    assert s.inst(bottomless.iid).zone is Zone.GRAVEYARD
