"""Effects Batch 22: send-from-field-to-GY activation cost.

A new activation cost: send N cards you control from the field to the Graveyard
(Effect.send_to_gy_cost + a CardFilter / face-up / exclude-self narrowing). Gated
into enumeration by moves.can_pay_costs and paid before the effect resolves.
Levia-Dragon - Daedalus sends a face-up "Umi" to destroy all other cards on the
field; Ultimate Baseball Kid sends another face-up FIRE monster to burn 500 (and
scales +1000 ATK per other face-up FIRE monster)."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _field_spell(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_field_spell(inst.iid, player, Position.FACE_UP_ATTACK)
    return inst


# --- Levia-Dragon - Daedalus: send Umi -> destroy all OTHER cards ---------------
def test_daedalus_unavailable_without_a_face_up_umi():
    s = _fresh()
    s.spawn_on_field(reg.get("Levia-Dragon - Daedalus"), 0, 0, Position.FACE_UP_ATTACK)
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert actions == []  # no "Umi" to send as the cost


def test_daedalus_sends_umi_and_destroys_all_other_cards():
    s = _fresh()
    daed = s.spawn_on_field(reg.get("Levia-Dragon - Daedalus"), 0, 0, Position.FACE_UP_ATTACK)
    umi = _field_spell(s, "Umi", 0)
    mine = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)
    theirs = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert actions and actions[0].iid == daed.iid
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(daed.iid), 0)
    assert s.inst(umi.iid).zone is Zone.GRAVEYARD  # sent as the cost
    assert s.inst(mine.iid).zone is Zone.GRAVEYARD  # other cards destroyed
    assert s.inst(theirs.iid).zone is Zone.GRAVEYARD
    assert s.inst(daed.iid).zone is Zone.MONSTER  # Daedalus itself survives


# --- Ultimate Baseball Kid: +1000 ATK per other FIRE monster, send 1 to burn ----
def test_baseball_kid_scales_with_other_fire_monsters():
    s = _fresh()
    ubk = s.spawn_on_field(reg.get("Ultimate Baseball Kid"), 0, 0, Position.FACE_UP_ATTACK)
    assert s.effective_attack(ubk.iid) == 500  # alone: only itself (excluded)
    s.spawn_on_field(reg.get("Aitsu"), 0, 1, Position.FACE_UP_ATTACK)  # a FIRE monster
    s.spawn_on_field(reg.get("Aitsu"), 1, 0, Position.FACE_UP_ATTACK)  # FIRE, opp side too
    assert s.effective_attack(ubk.iid) == 500 + 2000  # +1000 each, both sides


def test_baseball_kid_unavailable_without_another_fire_monster():
    s = _fresh()
    s.spawn_on_field(reg.get("Ultimate Baseball Kid"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)  # not FIRE
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert actions == []  # no OTHER face-up FIRE monster to send


def test_baseball_kid_sends_a_fire_monster_to_burn_500():
    s = _fresh()
    ubk = s.spawn_on_field(reg.get("Ultimate Baseball Kid"), 0, 0, Position.FACE_UP_ATTACK)
    fodder = s.spawn_on_field(reg.get("Aitsu"), 0, 1, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    before = s.players[1].life_points
    actions = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect)]
    assert actions and actions[0].iid == ubk.iid
    eng._activate_monster_effect(ActivateMonsterEffect(ubk.iid), 0)
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the FIRE monster was the cost
    assert s.players[1].life_points == before - 500  # burn payload
    assert s.inst(ubk.iid).zone is Zone.MONSTER  # Kid itself stays (exclude_self)
