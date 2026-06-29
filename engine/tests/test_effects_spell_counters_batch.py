"""Effects Batch 20: Spell Counters.

Cards with a SpellCounterHolder accumulate 1 Spell Counter each time a Spell
resolves (up to a max). Royal Magical Library spends 3 (a monster Ignition effect's
counter cost) to draw 1. Mythical Beast Cerberus gains 500 ATK per counter and
loses them at the end of a Battle Phase in which it battled."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, ActivateSpell, DeclareAttack, Pass, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


class PassAgent(Agent):
    def decide(self, state, legal):
        return next(a for a in legal if isinstance(a, Pass))

    def respond(self, state, options, event):
        return None


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _stock_deck(s, player=0, n=5):
    for _ in range(n):
        inst = s.create_instance(reg.get("Mystical Elf"), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


# --- accumulation: a Spell resolving places a Spell Counter (up to max) ----------
def test_library_gains_a_spell_counter_when_a_spell_resolves():
    s = _fresh()
    _stock_deck(s, 0, 6)
    lib = s.spawn_on_field(reg.get("Royal Magical Library"), 0, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    pot = _in_hand(s, "Pot of Greed", 0)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert s.inst(lib.iid).counters.get("spell") == 1


def test_library_spell_counters_cap_at_three():
    s = _fresh()
    _stock_deck(s, 0, 12)
    lib = s.spawn_on_field(reg.get("Royal Magical Library"), 0, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    for _ in range(4):  # activate 4 Spells
        spark = _in_hand(s, "Sparks", 0)
        eng._activate_as_chain(ActivateSpell(spark.iid), 0)
    assert s.inst(lib.iid).counters["spell"] == 3  # capped at the max


# --- the counter-cost Ignition effect: remove 3 to draw 1 -----------------------
def test_library_effect_unavailable_below_three_counters():
    s = _fresh()
    lib = s.spawn_on_field(reg.get("Royal Magical Library"), 0, 0, Position.FACE_UP_ATTACK)
    lib.counters["spell"] = 2
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert actions == []  # not enough counters to pay the cost


def test_library_removes_three_counters_to_draw():
    s = _fresh()
    _stock_deck(s, 0, 3)
    lib = s.spawn_on_field(reg.get("Royal Magical Library"), 0, 0, Position.FACE_UP_ATTACK)
    lib.counters["spell"] = 3
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert actions and actions[0].iid == lib.iid  # now it can be activated
    eng = Engine(s, [Agent(), Agent()])
    deck_before = len(s.players[0].deck)
    eng._activate_monster_effect(ActivateMonsterEffect(lib.iid), 0)
    assert s.inst(lib.iid).counters["spell"] == 0  # 3 removed as the cost
    assert len(s.players[0].deck) == deck_before - 1  # drew 1
    assert s.inst(lib.iid).zone is Zone.MONSTER  # the monster stays on the field


# --- Mythical Beast Cerberus: +500 ATK per counter, wiped after it battles -------
def test_cerberus_gains_500_attack_per_counter():
    s = _fresh()
    cerb = s.spawn_on_field(reg.get("Mythical Beast Cerberus"), 0, 0, Position.FACE_UP_ATTACK)
    assert s.effective_attack(cerb.iid) == 1400  # no counters yet
    cerb.counters["spell"] = 2
    assert s.effective_attack(cerb.iid) == 1400 + 1000  # +500 each


def test_cerberus_loses_its_counters_at_the_end_of_a_battle_phase_it_fought():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    cerb = s.spawn_on_field(reg.get("Mythical Beast Cerberus"), 0, 0, Position.FACE_UP_ATTACK)
    cerb.counters["spell"] = 3
    prey = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)  # 800 ATK

    class AttackOnce(Agent):
        def __init__(self):
            self.done = False

        def decide(self, state, legal):
            if not self.done:
                for a in legal:
                    if isinstance(a, DeclareAttack) and a.attacker == cerb.iid:
                        self.done = True
                        return a
            return next(a for a in legal if isinstance(a, Pass))

    eng = Engine(s, [AttackOnce(), Agent()])
    eng._battle_phase(0)
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD  # Cerberus (2900) crushed it
    assert s.inst(cerb.iid).counters.get("spell", 0) == 0  # counters wiped after battling


def test_cerberus_keeps_counters_if_it_does_not_battle():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    cerb = s.spawn_on_field(reg.get("Mythical Beast Cerberus"), 0, 0, Position.FACE_UP_ATTACK)
    cerb.counters["spell"] = 3
    eng = Engine(s, [PassAgent(), PassAgent()])  # nobody attacks
    eng._battle_phase(0)
    assert s.inst(cerb.iid).counters["spell"] == 3  # never battled -> kept


# --- counters fall off when the card leaves the field ---------------------------
def test_counters_are_cleared_when_the_card_leaves_the_field():
    s = _fresh()
    lib = s.spawn_on_field(reg.get("Royal Magical Library"), 0, 0, Position.FACE_UP_ATTACK)
    lib.counters["spell"] = 3
    s.send_to_graveyard(lib.iid)
    assert s.inst(lib.iid).counters == {}
