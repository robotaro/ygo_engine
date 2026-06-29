"""Effects Batch 69: during-End-Phase triggers (EndPhaseTrigger).

The End-Phase analogue of StandbyTrigger: a face-up card fires a full Effect on a
fresh Chain during a qualifying End Phase, scoped by `whose` (the controller's own
End Phase / the opponent's / both) and the source's battle position, suppressed while
the source's effects are negated. Authored: Elemental HERO Lady Heat (burn 200 x your
face-up "Elemental HERO"), Little-Winguard (toggle its own position), Garuda the Wind
Spirit (toggle 1 opponent monster on the opponent's End Phase), Lumina, Lightsworn
Summoner (mill top 3 — plus an Ignition revive), The Wicked Worm Beast (return itself
to hand). Also exercises the engine._end_phase wiring and Skill-Drain suppression.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.END
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _trap(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, idx, pos)
    return inst


def _stock_deck(s, player, n, name="Celtic Guardian"):
    for _ in range(n):
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


def _fire_end(s, tp):
    Engine(s, [Agent(), Agent()])._fire_end_phase_triggers(tp)


def test_lady_heat_burns_200_per_faceup_hero():
    s = _fresh(tp=ME)
    _spawn(s, "Elemental HERO Lady Heat", ME, 0)  # 1 HERO -> 200
    _fire_end(s, ME)
    assert s.players[OPP].life_points == 8000 - 200
    # Two HEROes -> 400 from a single Lady Heat.
    s2 = _fresh(tp=ME)
    _spawn(s2, "Elemental HERO Lady Heat", ME, 0)
    _spawn(s2, "Elemental HERO Avian", ME, 1)
    _fire_end(s2, ME)
    assert s2.players[OPP].life_points == 8000 - 400


def test_lady_heat_only_on_your_own_end_phase():
    s = _fresh(tp=OPP)  # the controller's opponent is the turn player
    _spawn(s, "Elemental HERO Lady Heat", ME, 0)
    _fire_end(s, OPP)
    assert s.players[OPP].life_points == 8000  # whose="controller": silent


def test_lady_heat_fires_through_full_end_phase():
    # Confirms engine._end_phase wires the trigger sweep (empty hands -> no discard).
    s = _fresh(tp=ME)
    _spawn(s, "Elemental HERO Lady Heat", ME, 0)
    Engine(s, [Agent(), Agent()])._end_phase(ME)
    assert s.players[OPP].life_points == 8000 - 200


def test_little_winguard_toggles_its_own_position():
    s = _fresh(tp=ME)
    win = _spawn(s, "Little-Winguard", ME, 0, pos=Position.FACE_UP_ATTACK)
    _fire_end(s, ME)
    assert win.position is Position.FACE_UP_DEFENSE
    # Fires only on your own End Phase.
    s2 = _fresh(tp=OPP)
    win2 = _spawn(s2, "Little-Winguard", ME, 0, pos=Position.FACE_UP_ATTACK)
    _fire_end(s2, OPP)
    assert win2.position is Position.FACE_UP_ATTACK


def test_garuda_changes_opponent_monster_on_opponent_end_phase():
    s = _fresh(tp=OPP)  # the controller's opponent is the turn player
    _spawn(s, "Garuda the Wind Spirit", ME, 0)
    prey = _spawn(s, "Celtic Guardian", OPP, 0, pos=Position.FACE_UP_ATTACK)
    _fire_end(s, OPP)
    assert prey.position is Position.FACE_UP_DEFENSE
    # whose="opponent": nothing on the controller's own End Phase.
    s2 = _fresh(tp=ME)
    _spawn(s2, "Garuda the Wind Spirit", ME, 0)
    prey2 = _spawn(s2, "Celtic Guardian", OPP, 0, pos=Position.FACE_UP_ATTACK)
    _fire_end(s2, ME)
    assert prey2.position is Position.FACE_UP_ATTACK


def test_wicked_worm_beast_returns_itself_to_hand():
    s = _fresh(tp=ME)
    worm = _spawn(s, "The Wicked Worm Beast", ME, 0)
    _fire_end(s, ME)
    assert worm.iid in s.players[ME].hand
    assert worm.iid not in s.players[ME].monster_zones


def test_lumina_mills_top_3_on_your_end_phase():
    s = _fresh(tp=ME)
    _spawn(s, "Lumina, Lightsworn Summoner", ME, 0)
    _stock_deck(s, ME, 5)
    deck_before, gy_before = len(s.players[ME].deck), len(s.players[ME].graveyard)
    _fire_end(s, ME)
    assert len(s.players[ME].deck) == deck_before - 3
    assert len(s.players[ME].graveyard) == gy_before + 3


def test_lumina_revive_ignition_is_a_discard_to_summon_lightsworn():
    from ygo.card_effects import EFFECTS

    eff = EFFECTS["Lumina, Lightsworn Summoner"][0]
    assert eff.timing == "ignition"
    assert eff.discard_cost == 1
    assert eff.target is not None and eff.target.max_level == 4
    assert "Lightsworn" in eff.target.name_contains


def test_skill_drain_suppresses_an_end_phase_trigger():
    s = _fresh(tp=ME)
    _spawn(s, "Elemental HERO Lady Heat", ME, 0)
    _trap(s, "Skill Drain", ME, 0)  # negates all face-up monster effects
    _fire_end(s, ME)
    assert s.players[OPP].life_points == 8000  # Lady Heat's burn is shut off
