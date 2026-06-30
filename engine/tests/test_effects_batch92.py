"""Effects Batch 92: the Toon monsters.

The engine already enforces the shared Toon rules (a Toon needs your face-up Toon World
to be Summoned, can't attack the turn it's Summoned, attacks directly unless the opponent
controls a Toon, and is destroyed when Toon World leaves). These cards add the per-card
pieces:

- Blue-Eyes Toon Dragon / Toon Summoned Skull: cannot be Normal Summoned; Special Summoned
  from the hand by Tributing 2 / 1 monsters while controlling Toon World; pay 500 LP to
  attack (AttackLifeCost).
- Toon Gemini Elf: a Level-4 Toon; on inflicting battle damage, the opponent discards 1
  random card.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, NormalSummon, SpecialSummonFromHand, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _main_phase(tp=0):
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 3, tp
    return s


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _toon_world(s, player):
    inst = s.create_instance(reg.get("Toon World"), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _hand_summons(s, player=0):
    return {a.iid for a in legal_actions(s, player) if isinstance(a, SpecialSummonFromHand)}


# ----------------------------------------------- Blue-Eyes Toon Dragon (SS-only, 2 tributes)


def test_toon_dragon_cannot_be_normal_summoned():
    s = _main_phase()
    _toon_world(s, A)
    _spawn(s, "Mystical Elf", A, 0)
    _spawn(s, "Celtic Guardian", A, 1)
    toon = _in_hand(s, "Blue-Eyes Toon Dragon")
    assert not any(isinstance(a, NormalSummon) and a.iid == toon.iid for a in legal_actions(s, A))


def test_toon_dragon_needs_toon_world_and_two_tributes():
    s = _main_phase()
    toon = _in_hand(s, "Blue-Eyes Toon Dragon")
    e1 = _spawn(s, "Mystical Elf", A, 0)
    _spawn(s, "Celtic Guardian", A, 1)
    assert toon.iid not in _hand_summons(s)  # no Toon World yet
    tw = _toon_world(s, A)
    assert toon.iid in _hand_summons(s)  # Toon World + 2 monsters -> offered
    # remove a tribute -> only 1 monster -> no longer offered
    s.send_to_graveyard(e1.iid)
    assert toon.iid not in _hand_summons(s)
    assert tw  # (silence lint)


def test_toon_dragon_special_summon_tributes_two():
    s = _main_phase()
    _toon_world(s, A)
    toon = _in_hand(s, "Blue-Eyes Toon Dragon")
    t1 = _spawn(s, "Mystical Elf", A, 0)
    t2 = _spawn(s, "Celtic Guardian", A, 1)
    apply(s, SpecialSummonFromHand(toon.iid))
    assert s.inst(toon.iid).zone is Zone.MONSTER
    assert s.inst(t1.iid).zone is Zone.GRAVEYARD and s.inst(t2.iid).zone is Zone.GRAVEYARD
    assert s.normal_summon_used is False  # a hand SS doesn't use the Normal Summon


def test_toon_summoned_skull_tributes_one():
    s = _main_phase()
    _toon_world(s, A)
    toon = _in_hand(s, "Toon Summoned Skull")
    t1 = _spawn(s, "Mystical Elf", A, 0)
    assert toon.iid in _hand_summons(s)
    apply(s, SpecialSummonFromHand(toon.iid))
    assert s.inst(toon.iid).zone is Zone.MONSTER
    assert s.inst(t1.iid).zone is Zone.GRAVEYARD


# ----------------------------------------------------------- shared Toon rules (per-card)


def test_toon_pays_500_lp_to_attack():
    s = _main_phase(tp=A)
    s.phase = Phase.BATTLE
    toon = _spawn(s, "Blue-Eyes Toon Dragon", A, 0)
    toon.summoned_this_turn = False  # summoned a previous turn -> may attack
    _toon_world(s, A)
    s.players[A].life_points = 4000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(toon.iid, None), A)  # direct (opponent has no Toons)
    assert s.players[A].life_points == 3500  # paid the 500 LP attack cost


def test_toon_destroyed_when_toon_world_leaves():
    s = _main_phase(tp=A)
    toon = _spawn(s, "Blue-Eyes Toon Dragon", A, 0)
    tw = _toon_world(s, A)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(tw.iid)  # Toon World leaves the field
    eng._cleanup_toons()
    assert s.inst(toon.iid).zone is Zone.GRAVEYARD  # the Toon is destroyed with it


# ------------------------------------------------------------------- Toon Gemini Elf


def test_toon_gemini_elf_discards_on_battle_damage():
    s = _main_phase(tp=A)
    s.phase = Phase.BATTLE
    elf = _spawn(s, "Toon Gemini Elf", A, 0)  # 1900 ATK
    elf.summoned_this_turn = False
    _toon_world(s, A)
    foe_card = _in_hand(s, "Summoned Skull", B)  # the opponent's hand card to be discarded
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(elf.iid, None), A)  # direct attack -> battle damage
    assert s.inst(foe_card.iid).zone is Zone.GRAVEYARD  # 1 random card discarded
    assert s.players[B].life_points == 8000 - 1900  # the battle damage landed
