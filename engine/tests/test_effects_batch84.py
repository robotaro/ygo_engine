"""Effects Batch 84: "when you gain Life Points" (TIMING_RECOVER) -- Fire Princess.

state.gain_life_points is now the single LP-gain sink: every healing path (the
GainLifePoints primitive, the Standby-upkeep Cure Mermaid marker, the Solemn-Wishes
draw-trigger marker) routes through it and records the gain to GameState.lp_gain_pending.
The engine drains that queue -- after a chain resolves, after a draw-trigger sweep, and at
the end of the Standby Phase -- and fires each gaining player's face-up LifeGainTrigger
once per gain EVENT.

Fire Princess: "Each time you gain Life Points, inflict 500 damage to your opponent." It is
the sole pre-Synchro consumer, but it pairs with the classic LP engines (Solemn Wishes,
Cure Mermaid, any healing Spell), so those combos are covered end-to-end here.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import LifeGainTrigger
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


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


def _drive_gain_window(s, player, amount):
    """Record a gain and run the real "when you gain Life Points" window."""
    s.lp_gain_pending = [(player, amount)]
    Engine(s, [Agent(), Agent()])._fire_life_gain_window()


# ----------------------------------------------------- the gain sink records the gain


def test_gain_life_points_records_only_positive_gains():
    s = _fresh()
    s.gain_life_points(0, 800)
    assert s.lp_gain_pending == [(0, 800)] and s.players[0].life_points == 8800
    s.lp_gain_pending = []
    s.gain_life_points(0, 0)  # not a gain
    s.gain_life_points(0, -300)  # not a gain
    assert s.lp_gain_pending == [] and s.players[0].life_points == 8800


# ----------------------------------------------------- the window fires Fire Princess


def test_fire_princess_burns_opponent_500_on_a_gain():
    s = _fresh()
    _spawn(s, "Fire Princess", 0, 0)
    before_opp = s.players[1].life_points
    _drive_gain_window(s, player=0, amount=1000)
    assert s.players[1].life_points == before_opp - 500  # flat 500, regardless of amount


def test_fire_princess_does_not_fire_when_the_opponent_gains():
    s = _fresh()
    _spawn(s, "Fire Princess", 0, 0)  # player 0's Fire Princess
    before_opp = s.players[1].life_points
    _drive_gain_window(s, player=1, amount=1000)  # player 1 (the opponent) gains
    assert s.players[1].life_points == before_opp  # "each time YOU gain" -> does not fire


def test_two_fire_princesses_each_fire():
    s = _fresh()
    _spawn(s, "Fire Princess", 0, 0)
    _spawn(s, "Fire Princess", 0, 1)
    before_opp = s.players[1].life_points
    _drive_gain_window(s, player=0, amount=500)
    assert s.players[1].life_points == before_opp - 1000  # both continuous copies fire


def test_fire_princess_inert_under_skill_drain():
    s = _fresh()
    _spawn(s, "Fire Princess", 0, 0)
    _faceup_st(s, "Skill Drain", 1)  # negates all face-up monster effects
    assert not list(s.active_markers(LifeGainTrigger, (0,)))  # scan skips the negated monster
    before_opp = s.players[1].life_points
    _drive_gain_window(s, player=0, amount=1000)
    assert s.players[1].life_points == before_opp  # no burn while negated


# --------------------------------------------- end-to-end through the real LP-gain paths


def test_fire_princess_fires_on_a_healing_effect_chain():
    # A real chain: GainLifePoints routes through the sink; _run_chain's tail drains the
    # life-gain window. Dian Keto the Cure Master gains its controller 1000.
    s = _fresh()
    _spawn(s, "Fire Princess", 0, 0)
    cure = s.create_instance(reg.get("Dian Keto the Cure Master"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(cure.iid)
    from ygo.moves import ActivateSpell

    eng = Engine(s, [Agent(), Agent()])
    lp0, lp1 = s.players[0].life_points, s.players[1].life_points
    eng._activate_as_chain(ActivateSpell(cure.iid, targets=()), 0)
    assert s.players[0].life_points == lp0 + 1000  # healed 1000
    assert s.players[1].life_points == lp1 - 500  # Fire Princess burned the opponent


def test_fire_princess_fires_on_solemn_wishes_draw_gain():
    # Solemn Wishes (DrawTrigger gain 500) -> _process_draw_triggers tail drains the window.
    s = _fresh()
    _spawn(s, "Fire Princess", 0, 0)
    _faceup_st(s, "Solemn Wishes", 0)
    for name in ("Kuriboh", "Kuriboh"):  # something to draw
        c = s.create_instance(reg.get(name), owner=0, zone=Zone.DECK)
        s.players[0].deck.append(c.iid)
    lp0, lp1 = s.players[0].life_points, s.players[1].life_points
    eng = Engine(s, [Agent(), Agent()])
    s.draw(0, 1)  # queues the draw trigger
    eng._process_draw_triggers()
    assert s.players[0].life_points == lp0 + 500  # Solemn Wishes gain
    assert s.players[1].life_points == lp1 - 500  # Fire Princess burn off that gain


def test_fire_princess_fires_on_cure_mermaid_standby_gain():
    # Cure Mermaid (StandbyUpkeep gain) -> _standby_phase tail drains the window.
    s = _fresh(tp=0, phase=Phase.STANDBY)
    _spawn(s, "Fire Princess", 0, 0)
    _spawn(s, "Cure Mermaid", 0, 1, pos=Position.FACE_UP_ATTACK)
    lp0, lp1 = s.players[0].life_points, s.players[1].life_points
    Engine(s, [Agent(), Agent()])._standby_phase(0)
    assert s.players[0].life_points > lp0  # Cure Mermaid healed its controller
    assert s.players[1].life_points == lp1 - 500  # Fire Princess burned off that gain
