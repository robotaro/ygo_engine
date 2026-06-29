"""Effects Batch 58: Damage-Step combat pumps (DamageStepBonus rider).

A new DamageStepBonus continuous rider gives a monster a temporary ATK/DEF swing that
applies only during the Damage Step of a qualifying battle — never to its displayed stats.
state.damage_step_bonus folds it into moves._resolve_attack for the attacker, the
attacked monster, or both ("either"), optionally gated on attacking directly / a defending
monster's race / attribute.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ME, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


# --------------------------------------------------------------------------- #
#  Cipher Soldier — +2000 ATK/DEF vs a Warrior (only)
# --------------------------------------------------------------------------- #
def test_cipher_soldier_pumps_against_a_warrior():
    s = _fresh()
    cipher = _spawn(s, "Cipher Soldier", ME, 0)  # 1350; +2000 vs a Warrior -> 3350
    warrior = _spawn(s, "Celtic Guardian", OPP, 0)  # Warrior 1400
    apply(s, DeclareAttack(cipher.iid, warrior.iid))
    assert s.inst(warrior.iid).zone is Zone.GRAVEYARD
    assert s.inst(cipher.iid).zone is Zone.MONSTER
    assert s.players[OPP].life_points == 8000 - (3350 - 1400)
    assert s.effective_attack(cipher.iid) == 1350  # the swing never touches its real ATK


def test_cipher_soldier_no_bonus_against_a_nonwarrior():
    s = _fresh()
    cipher = _spawn(s, "Cipher Soldier", ME, 0)  # 1350, no bonus vs a Fiend
    fiend = _spawn(s, "Summoned Skull", OPP, 0)  # 2500
    apply(s, DeclareAttack(cipher.iid, fiend.iid))
    assert s.inst(cipher.iid).zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------- #
#  Etoile Cyber — +500 ATK only on a direct attack
# --------------------------------------------------------------------------- #
def test_etoile_cyber_pumps_on_a_direct_attack():
    s = _fresh()
    etoile = _spawn(s, "Etoile Cyber", ME, 0)  # 1200 -> 1700 direct
    apply(s, DeclareAttack(etoile.iid, None))
    assert s.players[OPP].life_points == 8000 - 1700


def test_etoile_cyber_no_bonus_against_a_monster():
    s = _fresh()
    etoile = _spawn(s, "Etoile Cyber", ME, 0)  # 1200, no direct bonus
    weak = _spawn(s, "Mystical Elf", OPP, 0)  # 800
    apply(s, DeclareAttack(etoile.iid, weak.iid))
    assert s.players[OPP].life_points == 8000 - (1200 - 800)  # only the plain 400


# --------------------------------------------------------------------------- #
#  Insect Soldiers of the Sky — +1000 ATK vs a WIND monster
# --------------------------------------------------------------------------- #
def test_insect_soldiers_pump_against_wind():
    s = _fresh()
    bug = _spawn(s, "Insect Soldiers of the Sky", ME, 0)  # 1000; +1000 vs WIND -> 2000
    wind = _spawn(s, "Luster Dragon", OPP, 0)  # WIND 1900
    apply(s, DeclareAttack(bug.iid, wind.iid))
    assert s.inst(wind.iid).zone is Zone.GRAVEYARD
    assert s.players[OPP].life_points == 8000 - (2000 - 1900)


def test_insect_soldiers_no_bonus_against_nonwind():
    s = _fresh()
    bug = _spawn(s, "Insect Soldiers of the Sky", ME, 0)  # 1000, no bonus vs EARTH
    earth = _spawn(s, "Celtic Guardian", OPP, 0)  # EARTH 1400
    apply(s, DeclareAttack(bug.iid, earth.iid))
    assert s.inst(bug.iid).zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------- #
#  Penumbral Soldier Lady — +1000 ATK whenever it battles a LIGHT monster
# --------------------------------------------------------------------------- #
def test_penumbral_pumps_battling_a_light_monster():
    s = _fresh()
    lady = _spawn(s, "Penumbral Soldier Lady", ME, 0)  # 2100; +1000 vs LIGHT -> 3100
    light = _spawn(s, "Cyber Dragon", OPP, 0)  # LIGHT 2100 (would tie at 2100)
    apply(s, DeclareAttack(lady.iid, light.iid))
    assert s.inst(light.iid).zone is Zone.GRAVEYARD
    assert s.inst(lady.iid).zone is Zone.MONSTER
    assert s.players[OPP].life_points == 8000 - (3100 - 2100)


# --------------------------------------------------------------------------- #
#  Steamroid — +500 attacking a monster, -500 when attacked
# --------------------------------------------------------------------------- #
def test_steamroid_pumps_when_attacking():
    s = _fresh()
    roid = _spawn(s, "Steamroid", ME, 0)  # 1800; +500 attacking -> 2300
    target = _spawn(s, "Gemini Elf", OPP, 0)  # 1900
    apply(s, DeclareAttack(roid.iid, target.iid))
    assert s.inst(target.iid).zone is Zone.GRAVEYARD
    assert s.players[OPP].life_points == 8000 - (2300 - 1900)


def test_steamroid_weakens_when_attacked():
    s = _fresh()
    roid = _spawn(s, "Steamroid", ME, 0)  # 1800; -500 when attacked -> 1300
    attacker = _spawn(s, "Gemini Elf", OPP, 0)  # 1900 attacks it
    apply(s, DeclareAttack(attacker.iid, roid.iid))
    assert s.inst(roid.iid).zone is Zone.GRAVEYARD  # 1300 < 1900
    assert s.players[ME].life_points == 8000 - (1900 - 1300)
