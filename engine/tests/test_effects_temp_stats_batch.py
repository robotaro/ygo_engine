"""Effects Batch 5: temporary (until-end-of-turn) ATK/DEF combat tricks, on the
new ModifyStatsTemporary primitive. The boost folds into effective stats and the
engine clears it in the End Phase."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.effects import EffectContext, ModifyStatsTemporary
from ygo.engine import Engine
from ygo.enums import Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def test_temp_modifier_adds_then_clears_at_end_phase():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    m = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)  # 2500
    ctx = EffectContext(state=s, controller=0, source_iid=m.iid, targets=[m.iid])
    ModifyStatsTemporary(atk=700).execute(ctx)
    assert s.effective_attack(m.iid) == 3200

    Engine(s, [GreedyAgent(), GreedyAgent()])._end_phase(0)
    assert s.effective_attack(m.iid) == 2500  # wore off


def test_temp_modifiers_stack():
    s = GameState.new(("A", "B"), seed=0)
    m = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    ctx = EffectContext(state=s, controller=0, source_iid=m.iid, targets=[m.iid])
    ModifyStatsTemporary(atk=700).execute(ctx)
    ModifyStatsTemporary(atk=500).execute(ctx)
    assert s.effective_attack(m.iid) == 2500 + 1200


def test_negative_temp_modifier_floors_at_zero():
    s = GameState.new(("A", "B"), seed=0)
    weak = next(c for c in reg if c.is_monster and 0 < (c.attack or 0) <= 400)
    m = s.spawn_on_field(weak, 0, 0, Position.FACE_UP_ATTACK)
    ctx = EffectContext(state=s, controller=0, source_iid=m.iid, targets=[m.iid])
    ModifyStatsTemporary(atk=-5000).execute(ctx)
    assert s.effective_attack(m.iid) == 0  # clamped, not negative


def test_rush_recklessly_pumps_a_target():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_player = 0
    from ygo.moves import ActivateSpell, apply

    m = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    rr = s.create_instance(reg.get("Rush Recklessly"), 0, Zone.HAND)
    s.players[0].hand.append(rr.iid)
    apply(s, ActivateSpell(rr.iid, targets=(m.iid,)))
    assert s.effective_attack(m.iid) == 3200
    assert s.inst(rr.iid).zone is Zone.GRAVEYARD  # Quick-Play spent


def test_reinforcements_trap_buffs_in_a_response_window():
    s = GameState.new(("A", "B"), seed=0)
    m = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    from ygo.moves import response_options

    # Set Reinforcements last turn so it's live now.
    r = s.create_instance(reg.get("Reinforcements"), 0, Zone.HAND)
    s.players[0].hand.append(r.iid)
    s.place_spell_trap(r.iid, 0, 0, Position.FACE_DOWN)
    s.inst(r.iid).set_on_turn = 1
    s.turn_count = 2
    opts = response_options(s, 0, event=None, last_speed=1)
    assert any(o.iid == r.iid for o in opts)  # offered as a speed-2 quick response
