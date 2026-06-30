"""Effects Batch 117: Toon Mermaid.

A Level-4 Toon: cannot be Normal Summoned; Special Summoned from the hand (no Tributes)
while you control Toon World; pays 500 LP to declare an attack. The shared Toon rules are
enforced by the engine (Batch 92); these checks cover the per-card pieces.
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
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def _hand_summons(s, player=0):
    return {a.iid for a in legal_actions(s, player) if isinstance(a, SpecialSummonFromHand)}


def test_mermaid_cannot_be_normal_summoned():
    s = _main_phase()
    _toon_world(s, A)
    mermaid = _in_hand(s, "Toon Mermaid")
    assert not any(isinstance(a, NormalSummon) and a.iid == mermaid.iid for a in legal_actions(s, A))


def test_mermaid_needs_toon_world_no_tributes():
    s = _main_phase()
    mermaid = _in_hand(s, "Toon Mermaid")
    assert mermaid.iid not in _hand_summons(s)  # no Toon World -> not offered
    _toon_world(s, A)
    assert mermaid.iid in _hand_summons(s)  # Toon World alone is enough (no Tributes)


def test_mermaid_special_summon_uses_no_tributes_or_normal_summon():
    s = _main_phase()
    _toon_world(s, A)
    mermaid = _in_hand(s, "Toon Mermaid")
    ally = _spawn(s, "Mystical Elf", A, 0)
    apply(s, SpecialSummonFromHand(mermaid.iid))
    assert s.inst(mermaid.iid).zone is Zone.MONSTER
    assert s.inst(ally.iid).zone is Zone.MONSTER  # nothing was Tributed
    assert s.normal_summon_used is False


def test_mermaid_pays_500_lp_to_attack():
    s = _main_phase(tp=A)
    s.phase = Phase.BATTLE
    mermaid = _spawn(s, "Toon Mermaid", A, 0)
    mermaid.summoned_this_turn = False  # summoned a previous turn -> may attack
    _toon_world(s, A)
    s.players[A].life_points = 4000
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(mermaid.iid, None), A)
    assert s.players[A].life_points == 3500  # paid the 500 LP attack cost
