"""Effects Batch 63: turn-scoped lockout Flip effects (ApplyActionLock).

A new turn-scoped lock store (state.action_locks + state.action_locked) bars a player from
an action class for a duration: Special Summon (Guard Dog), Spell activation (Sonic Jammer,
through next turn), Spell+Trap activation (Whirlwind Weasel), Setting (Searchlightman).
The gates live at the existing chokepoints — special_summon_locked, cannot_activate_card,
and the Set-action enumeration — and the locks expire by turn.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import NormalSummon, SetMonster, SetSpellTrap, legal_actions, resolve_effect
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


def _resolve_flip(s, name, source_iid):
    resolve_effect(s, EFFECTS[name][0], source_iid, (), None)


def test_guard_dog_blocks_opponent_special_summon_this_turn_only():
    s = _fresh()
    dog = _spawn(s, "Guard Dog", ME, 0)
    _resolve_flip(s, "Guard Dog", dog.iid)
    card = reg.get("Cyber Dragon")
    assert s.special_summon_locked(OPP, card)
    assert not s.special_summon_locked(ME, card)  # only the opponent is locked
    s.turn_count += 1
    assert not s.special_summon_locked(OPP, card)  # "rest of this turn" -> gone next turn


def test_sonic_jammer_blocks_opponent_spells_through_next_turn():
    s = _fresh()
    jammer = _spawn(s, "Sonic Jammer", ME, 0)
    _resolve_flip(s, "Sonic Jammer", jammer.iid)
    spell = _hand(s, "Pot of Greed", OPP)
    trap = _hand(s, "Trap Hole", OPP)
    assert s.cannot_activate_card(spell.iid)  # Spells barred
    assert not s.cannot_activate_card(trap.iid)  # Traps untouched by Sonic Jammer
    s.turn_count += 1
    assert s.cannot_activate_card(spell.iid)  # still barred next turn
    s.turn_count += 1
    assert not s.cannot_activate_card(spell.iid)  # expired afterwards


def test_whirlwind_weasel_blocks_spells_and_traps():
    s = _fresh()
    weasel = _spawn(s, "Whirlwind Weasel", ME, 0)
    _resolve_flip(s, "Whirlwind Weasel", weasel.iid)
    assert s.cannot_activate_card(_hand(s, "Pot of Greed", OPP).iid)
    assert s.cannot_activate_card(_hand(s, "Trap Hole", OPP).iid)
    assert not s.cannot_activate_card(_hand(s, "Pot of Greed", ME).iid)  # my own are fine


def test_searchlightman_blocks_opponent_setting_but_not_summoning():
    s = _fresh()
    light = _spawn(s, "Searchlightman", ME, 0)
    _resolve_flip(s, "Searchlightman", light.iid)
    s.turn_player, s.phase = OPP, Phase.MAIN_1  # now the locked player's Main Phase
    _hand(s, "Celtic Guardian", OPP)
    _hand(s, "Pot of Greed", OPP)
    acts = legal_actions(s, OPP)
    assert not any(isinstance(a, (SetMonster, SetSpellTrap)) for a in acts)  # no Setting
    assert any(isinstance(a, NormalSummon) for a in acts)  # Normal Summon still allowed
    s.turn_count += 1
    assert any(isinstance(a, SetMonster) for a in legal_actions(s, OPP))  # lock lifts
