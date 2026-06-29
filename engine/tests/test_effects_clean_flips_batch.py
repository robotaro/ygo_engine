"""Effects Batch 61: more clean Flip effects (existing primitives, no new mechanism).

Position change (Bite Shoes / Gravitic Orb), Graveyard recovery (DUCKER Mobile Cannon /
Mask of Darkness via ReturnFromGraveyardToHand) and take-control-until-End-Phase (Rafflesia
Seduction / Jowls of Dark Demise / Dragon Manipulator via TakeControl).
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import resolve_effect, target_candidates
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ME, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _to_gy(s, name, player=ME):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _flip_resolve(s, name, source_iid, targets=()):
    resolve_effect(s, EFFECTS[name][0], source_iid, targets, None)


def test_bite_shoes_toggles_a_monster():
    s = _fresh()
    shoes = _spawn(s, "Bite Shoes", ME, 0)
    victim = _spawn(s, "Summoned Skull", OPP, 0)  # face-up Attack -> Defense
    _flip_resolve(s, "Bite Shoes", shoes.iid, (victim.iid,))
    assert s.inst(victim.iid).position is Position.FACE_UP_DEFENSE


def test_gravitic_orb_toggles_all_opponent_monsters():
    s = _fresh()
    orb = _spawn(s, "Gravitic Orb", ME, 0)
    a = _spawn(s, "Summoned Skull", OPP, 0)
    b = _spawn(s, "Celtic Guardian", OPP, 1, Position.FACE_UP_DEFENSE)
    mine = _spawn(s, "Gemini Elf", ME, 1)  # my monster is untouched
    _flip_resolve(s, "Gravitic Orb", orb.iid)
    assert s.inst(a.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(b.iid).position is Position.FACE_UP_ATTACK
    assert s.inst(mine.iid).position is Position.FACE_UP_ATTACK


def test_ducker_recovers_a_level4_monster_from_gy():
    s = _fresh()
    ducker = _spawn(s, "DUCKER Mobile Cannon", ME, 0)
    mon = _to_gy(s, "Celtic Guardian")  # Level 4 -> eligible
    _to_gy(s, "Summoned Skull")  # Level 6 -> not eligible
    _flip_resolve(s, "DUCKER Mobile Cannon", ducker.iid)
    assert s.inst(mon.iid).zone is Zone.HAND


def test_mask_of_darkness_recovers_a_trap():
    s = _fresh()
    mask = _spawn(s, "Mask of Darkness", ME, 0)
    trap = _to_gy(s, "Sakuretsu Armor")
    _flip_resolve(s, "Mask of Darkness", mask.iid)
    assert s.inst(trap.iid).zone is Zone.HAND


def test_rafflesia_takes_control_until_end_phase():
    s = _fresh()
    raff = _spawn(s, "Rafflesia Seduction", ME, 0)
    prey = _spawn(s, "Summoned Skull", OPP, 0)
    _flip_resolve(s, "Rafflesia Seduction", raff.iid, (prey.iid,))
    assert s.inst(prey.iid).controller == ME
    assert s.inst(prey.iid).control_until_end_of_turn == s.turn_count


def test_jowls_takes_control():
    s = _fresh()
    jowls = _spawn(s, "Jowls of Dark Demise", ME, 0)
    prey = _spawn(s, "Gemini Elf", OPP, 0)
    _flip_resolve(s, "Jowls of Dark Demise", jowls.iid, (prey.iid,))
    assert s.inst(prey.iid).controller == ME


def test_dragon_manipulator_only_targets_dragons():
    s = _fresh()
    manip = _spawn(s, "Dragon Manipulator", ME, 0)
    dragon = _spawn(s, "Luster Dragon", OPP, 0)  # Dragon -> eligible
    _spawn(s, "Summoned Skull", OPP, 1)  # Fiend -> not eligible
    cands = target_candidates(s, ME, EFFECTS["Dragon Manipulator"][0].target)
    assert cands == [dragon.iid]
    _flip_resolve(s, "Dragon Manipulator", manip.iid, (dragon.iid,))
    assert s.inst(dragon.iid).controller == ME
