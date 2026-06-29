"""Effects Batch 64: continuous activation locks (ActivationLock rider).

A face-up monster bars its controller's OPPONENT from activating a card class, scoped:
Mirage Dragon / Pitch-Black Warwolf (Traps, Battle Phase only), Invader of Darkness
(Quick-Play Spells), Mechanical Hound (Spells, while the source's controller has an empty
hand). Gated in state.cannot_activate_card via _activation_locked_by_monster.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ME, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def test_mirage_dragon_locks_opponent_traps_only_in_battle_phase():
    s = _fresh()
    _spawn(s, "Mirage Dragon", ME, 0)
    trap = _hand(s, "Trap Hole", OPP)
    spell = _hand(s, "Pot of Greed", OPP)
    s.phase = Phase.MAIN_1
    assert not s.cannot_activate_card(trap.iid)  # outside the Battle Phase: fine
    s.phase = Phase.BATTLE
    assert s.cannot_activate_card(trap.iid)  # locked during the Battle Phase
    assert not s.cannot_activate_card(spell.iid)  # only Traps, not Spells
    assert not s.cannot_activate_card(_hand(s, "Trap Hole", ME).iid)  # my own Trap is fine


def test_pitch_black_warwolf_also_locks_battle_phase_traps():
    s = _fresh()
    _spawn(s, "Pitch-Black Warwolf", ME, 0)
    trap = _hand(s, "Sakuretsu Armor", OPP)
    s.phase = Phase.BATTLE
    assert s.cannot_activate_card(trap.iid)


def test_invader_of_darkness_locks_quick_play_spells():
    s = _fresh()
    _spawn(s, "Invader of Darkness", ME, 0)
    quick = _hand(s, "Book of Moon", OPP)  # Quick-Play
    normal = _hand(s, "Pot of Greed", OPP)  # Normal Spell
    assert s.cannot_activate_card(quick.iid)
    assert not s.cannot_activate_card(normal.iid)  # only Quick-Play is barred


def test_mechanical_hound_locks_spells_only_while_you_have_empty_hand():
    s = _fresh()
    _spawn(s, "Mechanical Hound", ME, 0)
    spell = _hand(s, "Pot of Greed", OPP)
    assert not s.players[ME].hand  # the source controller's hand is empty
    assert s.cannot_activate_card(spell.iid)
    _hand(s, "Celtic Guardian", ME)  # now you hold a card -> the lock lifts
    assert not s.cannot_activate_card(spell.iid)
