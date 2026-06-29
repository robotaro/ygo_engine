"""A Gemini monster is a Normal Monster until Gemini Summoned (effects_active False),
so its continuous riders and triggers must stay inert until then. That guard was
applied in some engine reads (draw triggers, self-stat riders) but missing from the
Spell-Counter accumulation/wipe and the on-summon trigger — this pins all three.
"""

from __future__ import annotations

import dataclasses

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import SpellCounterHolder
from ygo.engine import Engine
from ygo.enums import Phase, Position
from ygo.state import GameState

reg = CardRegistry.load_csv()
GEMINI = reg.get("Aquarian Alessa")  # any Gemini monster


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _gemini_with(*riders):
    return dataclasses.replace(GEMINI, continuous=tuple(riders))


def test_disabled_gemini_does_not_accumulate_spell_counters():
    s = _fresh()
    card = _gemini_with(SpellCounterHolder(max_counters=3, accumulates=True))
    inst = s.spawn_on_field(card, 0, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    assert not inst.effects_active  # not yet Gemini Summoned
    eng._place_spell_counters()
    assert inst.counters.get("spell", 0) == 0  # inert while a Normal Monster
    inst.gemini_unlocked = True
    eng._place_spell_counters()
    assert inst.counters.get("spell", 0) == 1  # live once Gemini Summoned


def test_disabled_gemini_does_not_wipe_spell_counters_after_battle():
    s = _fresh()
    card = _gemini_with(SpellCounterHolder(max_counters=3, wipe_after_battle=True))
    inst = s.spawn_on_field(card, 0, 0, Position.FACE_UP_ATTACK)
    inst.counters["spell"] = 2
    inst.attacked_this_turn = True
    eng = Engine(s, [Agent(), Agent()])
    eng._wipe_spell_counters_after_battle()
    assert inst.counters["spell"] == 2  # a disabled holder doesn't wipe


def test_disabled_gemini_does_not_fire_on_summon_trigger():
    # _trigger_summon_effect must respect effects_active too: a Gemini's "when Summoned"
    # effect doesn't fire on its initial Normal Summon (only after Gemini Summon).
    s = _fresh()
    inst = s.spawn_on_field(GEMINI, 0, 0, Position.FACE_UP_ATTACK)
    assert not inst.effects_active
    eng = Engine(s, [Agent(), Agent()])
    eng._trigger_summon_effect(inst.iid, "normal")  # must not raise / must no-op
