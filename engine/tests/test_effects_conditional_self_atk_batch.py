"""Effects Batch 57: conditional flat self-ATK (gated SelfStatMod).

New declarative SelfStatMod activation gates (active_if_control_name_contains /
active_if_hand_at_most / active_if_empty_spell_trap), checked in state._self_mod_active:
the whole modifier contributes 0 unless every set gate holds for the controller.
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


def _to_hand(s, name, player=ME):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def test_cybernetic_cyclopean_only_with_empty_hand():
    s = _fresh()
    cyc = _spawn(s, "Cybernetic Cyclopean", ME, 0)  # base 1400
    assert s.effective_attack(cyc.iid) == 1400 + 1000  # hand starts empty
    _to_hand(s, "Pot of Greed")  # now you hold a card -> gate fails
    assert s.effective_attack(cyc.iid) == 1400


def test_boot_up_soldier_needs_a_gadget():
    s = _fresh()
    boot = _spawn(s, "Boot-Up Soldier - Dread Dynamo", ME, 0)  # base 0
    assert s.effective_attack(boot.iid) == 0  # no Gadget controlled
    _spawn(s, "Green Gadget", ME, 1)
    assert s.effective_attack(boot.iid) == 2000


def test_boot_up_soldier_gadget_must_be_yours_and_face_up():
    s = _fresh()
    boot = _spawn(s, "Boot-Up Soldier - Dread Dynamo", ME, 0)
    _spawn(s, "Green Gadget", OPP, 0)  # the opponent's Gadget doesn't count
    assert s.effective_attack(boot.iid) == 0
    gadget = _spawn(s, "Green Gadget", ME, 1, Position.FACE_DOWN_DEFENSE)  # face-down -> no
    assert s.effective_attack(boot.iid) == 0
    gadget.position = Position.FACE_UP_ATTACK
    assert s.effective_attack(boot.iid) == 2000


def test_theban_nightmare_needs_empty_hand_and_spell_trap():
    s = _fresh()
    theban = _spawn(s, "Theban Nightmare", ME, 0)  # base 1500
    assert s.effective_attack(theban.iid) == 1500 + 1500  # empty hand + empty S/T
    # Place a Set Spell/Trap (place_spell_trap pulls it from the hand) -> the S/T gate fails
    # while the hand is empty again, so the boost is off purely on the S/T condition.
    st = s.create_instance(reg.get("Pot of Greed"), owner=ME, zone=Zone.HAND)
    s.players[ME].hand.append(st.iid)
    s.place_spell_trap(st.iid, ME, 0, Position.FACE_DOWN)
    assert not s.players[ME].hand  # hand empty; only the S/T gate is now violated
    assert s.effective_attack(theban.iid) == 1500
