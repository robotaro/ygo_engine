"""Effects Batch 40: attack-target protection ("cannot be selected as an attack target").

A face-up AttackTargetProtection rider removes certain monsters on its controller's
side from the opponent's attack-target list — they stay on the board (so they don't
open a direct attack), the opponent simply can't aim at them. The battle-phase
enumeration filters them out via GameState.is_protected_attack_target. Cards:
Decoyroid (decoy: protect every other monster), Marauding Captain (protect other
Warriors), Queen's Bodyguard (protect "Allure Queen" monsters), Marshmallon Glasses
(Continuous Spell: protect every monster except "Marshmallon", while you control one).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 1, Phase.BATTLE  # player 1 attacks player 0
    return s


def _attack_targets(s, attacker_iid):
    return {
        a.target
        for a in legal_actions(s, 1)
        if isinstance(a, DeclareAttack) and a.attacker == attacker_iid
    }


def test_decoyroid_forces_attacks_onto_itself():
    s = _fresh()
    decoy = s.spawn_on_field(reg.get("Decoyroid"), 0, 0, Position.FACE_UP_ATTACK)
    beater = s.spawn_on_field(reg.get("Summoned Skull"), 0, 1, Position.FACE_UP_ATTACK)
    atk = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    # The beater is protected; only the Decoyroid may be attacked (no direct attack).
    assert _attack_targets(s, atk.iid) == {decoy.iid}
    assert s.is_protected_attack_target(beater.iid)
    assert not s.is_protected_attack_target(decoy.iid)


def test_marauding_captain_protects_other_warriors_only():
    s = _fresh()
    captain = s.spawn_on_field(reg.get("Marauding Captain"), 0, 0, Position.FACE_UP_ATTACK)
    warrior = s.spawn_on_field(reg.get("Celtic Guardian"), 0, 1, Position.FACE_UP_ATTACK)  # Warrior
    nonwar = s.spawn_on_field(reg.get("Summoned Skull"), 0, 2, Position.FACE_UP_ATTACK)  # Fiend
    atk = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    targets = _attack_targets(s, atk.iid)
    # The other Warrior is protected; the Captain itself and the non-Warrior are not.
    assert warrior.iid not in targets
    assert captain.iid in targets
    assert nonwar.iid in targets
    assert s.is_protected_attack_target(warrior.iid)
    assert not s.is_protected_attack_target(captain.iid)
    assert not s.is_protected_attack_target(nonwar.iid)


def test_queens_bodyguard_protects_named_allure_queen():
    s = _fresh()
    s.spawn_on_field(reg.get("Queen's Bodyguard"), 0, 0, Position.FACE_UP_ATTACK)
    allure = s.spawn_on_field(reg.get("Allure Queen LV3"), 0, 1, Position.FACE_UP_ATTACK)
    atk = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    assert s.is_protected_attack_target(allure.iid)
    assert allure.iid not in _attack_targets(s, atk.iid)


def test_marshmallon_glasses_only_protects_while_marshmallon_present():
    s = _fresh()
    glasses = s.create_instance(reg.get("Marshmallon Glasses"), 0, Zone.HAND)
    s.players[0].hand.append(glasses.iid)
    s.place_spell_trap(glasses.iid, 0, 0, Position.FACE_UP_ATTACK)
    other = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    atk = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    # No Marshmallon on the board yet -> the glasses are dormant.
    assert not s.is_protected_attack_target(other.iid)
    assert other.iid in _attack_targets(s, atk.iid)
    # Bring out Marshmallon -> every other monster becomes un-targetable.
    marsh = s.spawn_on_field(reg.get("Marshmallon"), 0, 1, Position.FACE_UP_ATTACK)
    assert s.is_protected_attack_target(other.iid)
    assert not s.is_protected_attack_target(marsh.iid)  # the decoy stays attackable
    assert _attack_targets(s, atk.iid) == {marsh.iid}


def test_two_marauding_captains_lock_each_other():
    # The classic interaction: each Captain protects every Warrior except itself, so two
    # of them shield one another and the opponent cannot attack either Warrior.
    s = _fresh()
    cap_a = s.spawn_on_field(reg.get("Marauding Captain"), 0, 0, Position.FACE_UP_ATTACK)
    cap_b = s.spawn_on_field(reg.get("Marauding Captain"), 0, 1, Position.FACE_UP_ATTACK)
    atk = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    assert s.is_protected_attack_target(cap_a.iid)
    assert s.is_protected_attack_target(cap_b.iid)
    assert _attack_targets(s, atk.iid) == set()  # nothing legal to attack


def test_unprotected_board_is_unaffected():
    s = _fresh()
    a = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    b = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)
    atk = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    assert _attack_targets(s, atk.iid) == {a.iid, b.iid}
