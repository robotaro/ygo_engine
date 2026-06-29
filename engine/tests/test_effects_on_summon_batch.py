"""Effects Batch 21: on-Summon monster Trigger Effects.

A monster's own "when (Normal) Summoned" effect now fires on a fresh Chain
(engine._trigger_summon_effect), after the Summon resolves and survives any
summon-negation window. Breaker the Magical Warrior places 1 Spell Counter on
itself (max 1, non-accumulating) and gains 300 ATK while it holds it; its Ignition
effect removes that counter to destroy a Spell/Trap. Hannibal Necromancer is the
same shape but only destroys a face-up Trap. Gravekeeper's Curse burns 500 on any
Summon; Byser Shock returns every Set card to the hand."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    ActivateMonsterEffect,
    ActivateSpell,
    NormalSummon,
    Pass,
    legal_actions,
    target_candidates,
)
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _set_spell_trap(s, name, player, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    return inst


def _faceup_spell_trap(s, name, player, index):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_UP_ATTACK)
    return inst


class SummonOnce(Agent):
    """Normal Summon a specific monster the first chance it gets, then pass."""

    def __init__(self, iid):
        self.iid, self.done = iid, False

    def decide(self, state, legal):
        if not self.done:
            for a in legal:
                if isinstance(a, NormalSummon) and a.iid == self.iid:
                    self.done = True
                    return a
        return next(a for a in legal if isinstance(a, Pass))


# --- Breaker: on Normal Summon, place 1 Spell Counter on itself -----------------
def test_breaker_places_a_spell_counter_when_normal_summoned():
    s = _fresh()
    breaker = _in_hand(s, "Breaker the Magical Warrior", 0)
    eng = Engine(s, [SummonOnce(breaker.iid), Agent()])
    eng._interactive_phase(0)
    assert s.inst(breaker.iid).counters.get("spell") == 1
    assert s.effective_attack(breaker.iid) == 1600 + 300  # +300 per counter


def test_breaker_summon_trigger_is_normal_summon_only():
    s = _fresh()
    breaker = s.spawn_on_field(
        reg.get("Breaker the Magical Warrior"), 0, 0, Position.FACE_UP_ATTACK
    )
    eng = Engine(s, [Agent(), Agent()])
    eng._trigger_summon_effect(breaker.iid, "special")  # Special Summon -> no counter
    eng._trigger_summon_effect(breaker.iid, "flip")  # Flip Summon -> no counter
    assert s.inst(breaker.iid).counters.get("spell", 0) == 0
    eng._trigger_summon_effect(breaker.iid, "normal")  # Normal Summon -> 1 counter
    assert s.inst(breaker.iid).counters.get("spell") == 1


def test_breaker_counter_does_not_accumulate_when_a_spell_resolves():
    s = _fresh()
    for _ in range(3):  # deck for Pot of Greed to draw from
        d = s.create_instance(reg.get("Mystical Elf"), owner=0, zone=Zone.DECK)
        s.players[0].deck.append(d.iid)
    # Special-summoned Breaker (no on-summon counter); a resolving Spell must not give it one.
    breaker = s.spawn_on_field(
        reg.get("Breaker the Magical Warrior"), 0, 0, Position.FACE_UP_ATTACK
    )
    eng = Engine(s, [Agent(), Agent()])
    pot = _in_hand(s, "Pot of Greed", 0)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert s.inst(breaker.iid).counters.get("spell", 0) == 0  # never accrues from Spells


# --- Breaker: Ignition — remove 1 counter to destroy a Spell/Trap ---------------
def test_breaker_ignition_unavailable_without_a_counter():
    s = _fresh()
    s.spawn_on_field(reg.get("Breaker the Magical Warrior"), 0, 0, Position.FACE_UP_ATTACK)
    _set_spell_trap(s, "Magic Jammer", 1, 0)
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert actions == []  # no Spell Counter to remove


def test_breaker_ignition_removes_a_counter_to_destroy_a_spell_trap():
    s = _fresh()
    breaker = s.spawn_on_field(
        reg.get("Breaker the Magical Warrior"), 0, 0, Position.FACE_UP_ATTACK
    )
    breaker.counters["spell"] = 1
    trap = _set_spell_trap(s, "Magic Jammer", 1, 0)
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert any(a.iid == breaker.iid and trap.iid in a.targets for a in actions)
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(breaker.iid, targets=(trap.iid,)), 0)
    assert s.inst(trap.iid).zone is Zone.GRAVEYARD  # destroyed
    assert s.inst(breaker.iid).counters.get("spell", 0) == 0  # counter spent
    assert s.effective_attack(breaker.iid) == 1600  # boost gone with the counter


# --- Hannibal Necromancer: Ignition destroys only a face-up Trap ----------------
def test_hannibal_ignition_targets_only_face_up_traps():
    s = _fresh()
    s.spawn_on_field(reg.get("Hannibal Necromancer"), 0, 0, Position.FACE_UP_ATTACK)
    trap = _faceup_spell_trap(s, "Magic Jammer", 1, 0)  # a Trap, face-up
    _faceup_spell_trap(s, "Black Pendant", 1, 1)  # a Spell, face-up
    _set_spell_trap(s, "Seven Tools of the Bandit", 1, 2)  # a Trap, but face-down
    spec = next(
        e for e in reg.get("Hannibal Necromancer").effects if e.timing == "ignition"
    ).target
    assert target_candidates(s, 0, spec) == [trap.iid]  # only the face-up Trap


# --- Gravekeeper's Curse: 500 burn on any Summon --------------------------------
def test_gravekeepers_curse_burns_500_on_summon():
    s = _fresh()
    curse = s.spawn_on_field(reg.get("Gravekeeper's Curse"), 0, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    before = s.players[1].life_points
    eng._trigger_summon_effect(curse.iid, "flip")  # any Summon kind triggers it
    assert s.players[1].life_points == before - 500


# --- Byser Shock: return every Set card on the field to its owner's hand ---------
def test_byser_shock_returns_all_set_cards_to_hand():
    s = _fresh()
    byser = s.spawn_on_field(reg.get("Byser Shock"), 0, 0, Position.FACE_UP_ATTACK)
    set_mon = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_DOWN_DEFENSE)
    set_trap = _set_spell_trap(s, "Magic Jammer", 1, 0)
    faceup = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    eng._trigger_summon_effect(byser.iid, "normal")
    assert s.inst(set_mon.iid).zone is Zone.HAND  # Set monster bounced
    assert s.inst(set_trap.iid).zone is Zone.HAND  # Set Trap bounced
    assert s.inst(faceup.iid).zone is Zone.MONSTER  # face-up card untouched
    assert s.inst(byser.iid).zone is Zone.MONSTER  # Byser itself (face-up) untouched
