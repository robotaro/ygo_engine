"""Effects Batch 33: recover cards from your Graveyard (to hand / to Deck).

Two new primitives — ReturnFromGraveyardToHand and ReturnFromGraveyardToDeck — add up
to N filtered cards from the controller's Graveyard to the hand / shuffle them into the
Deck. Gated by _gy_has_match so they can't whiff. Cards: Quick Charger (2 low-Level
Batteryman -> hand), Ray of Hope (2 LIGHT monsters -> Deck), Volcanic Recharge (up to 3
Volcanic -> Deck), Monster Eye (pay 1000 LP; 1 Polymerization -> hand).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, ActivateSpell, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _set_spell_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _activate(s, iid, targets=()):
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(iid, targets=targets), 0)


# --- to hand: Quick Charger --------------------------------------------------------
def test_quick_charger_adds_two_batterymen_to_hand():
    s = _fresh()
    b1 = _in_gy(s, "Batteryman AA", 0)  # Level 4 or lower
    b2 = _in_gy(s, "Batteryman C", 0)
    _in_gy(s, "Mystical Elf", 0)  # not a Batteryman -> ignored
    qc = _set_spell_trap(s, "Quick Charger", 0)
    _activate(s, qc.iid)
    assert s.inst(b1.iid).zone is Zone.HAND
    assert s.inst(b2.iid).zone is Zone.HAND
    assert b1.iid in s.players[0].hand and b2.iid in s.players[0].hand


def test_quick_charger_only_offered_with_a_batteryman_in_gy():
    s = _fresh()
    qc = _set_spell_trap(s, "Quick Charger", 0)
    _in_gy(s, "Mystical Elf", 0)  # no Batteryman present
    assert [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == qc.iid] == []
    _in_gy(s, "Batteryman AA", 0)
    assert [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == qc.iid]


# --- to Deck: Ray of Hope / Volcanic Recharge --------------------------------------
def test_ray_of_hope_returns_two_light_monsters_to_deck():
    s = _fresh()
    l1 = _in_gy(s, "Mystical Elf", 0)  # LIGHT
    l2 = _in_gy(s, "Shining Angel", 0)  # LIGHT
    _in_gy(s, "Summoned Skull", 0)  # DARK -> ignored
    deck_before = len(s.players[0].deck)
    ray = _set_spell_trap(s, "Ray of Hope", 0)
    _activate(s, ray.iid)
    assert s.inst(l1.iid).zone is Zone.DECK
    assert s.inst(l2.iid).zone is Zone.DECK
    assert len(s.players[0].deck) == deck_before + 2


def test_volcanic_recharge_caps_at_three():
    s = _fresh()
    vs = [_in_gy(s, "Volcanic Doomfire", 0) for _ in range(4)]  # 4 Volcanic monsters
    rec = _set_spell_trap(s, "Volcanic Recharge", 0)
    _activate(s, rec.iid)
    returned = [v for v in vs if s.inst(v.iid).zone is Zone.DECK]
    assert len(returned) == 3  # "up to 3"


# --- monster Ignition with a life cost: Monster Eye --------------------------------
def test_monster_eye_pays_1000_and_recovers_polymerization():
    s = _fresh()
    eye = s.spawn_on_field(reg.get("Monster Eye"), 0, 0, Position.FACE_UP_ATTACK)
    poly = _in_gy(s, "Polymerization", 0)
    before = s.players[0].life_points
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(eye.iid), 0)
    assert s.players[0].life_points == before - 1000
    assert s.inst(poly.iid).zone is Zone.HAND


def test_monster_eye_not_offered_without_polymerization():
    s = _fresh()
    eye = s.spawn_on_field(reg.get("Monster Eye"), 0, 0, Position.FACE_UP_ATTACK)
    _in_gy(s, "Monster Reborn", 0)  # a Spell, but not Polymerization
    acts = [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect) and a.iid == eye.iid]
    assert acts == []
