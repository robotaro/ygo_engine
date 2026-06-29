"""Effects Batch 56: monster-borne attribute anthems (Bladefly & co).

state._field_delta now also reads FieldMod riders off face-up MONSTERS (not just Field/
Spell/Trap cards), so a monster can radiate a field-wide ATK swing by Attribute to every
matching monster on both sides — suppressed under Skill Drain / while its effects are off.
The elemental boosters each +500 ATK to one Attribute, -400 ATK to the opposing one.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ME, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def test_bladefly_boosts_wind_including_itself():
    s = _fresh()
    fly = _spawn(s, "Bladefly", ME, 0)  # WIND 600 -> +500 (its own anthem hits itself)
    assert s.effective_attack(fly.iid) == 600 + 500


def test_bladefly_weakens_earth_and_reaches_both_sides():
    s = _fresh()
    _spawn(s, "Bladefly", ME, 0)
    earth = _spawn(s, "Celtic Guardian", ME, 1)  # EARTH 1400 -> -400
    opp_wind = _spawn(s, "Luster Dragon", OPP, 0)  # WIND 1900 on the other side -> +500
    assert s.effective_attack(earth.iid) == 1400 - 400
    assert s.effective_attack(opp_wind.iid) == 1900 + 500


def test_opposing_anthems_stack():
    s = _fresh()
    _spawn(s, "Bladefly", ME, 0)  # WIND +500 / EARTH -400
    _spawn(s, "Milus Radiant", ME, 1)  # EARTH +500 / WIND -400
    wind = _spawn(s, "Luster Dragon", ME, 2)  # 1900: +500 -400 = +100
    earth = _spawn(s, "Gemini Elf", ME, 3)  # 1900: -400 +500 = +100
    assert s.effective_attack(wind.iid) == 1900 + 100
    assert s.effective_attack(earth.iid) == 1900 + 100


def test_anthem_suppressed_while_face_down():
    s = _fresh()
    fly = _spawn(s, "Bladefly", ME, 0)
    wind = _spawn(s, "Luster Dragon", ME, 1)  # 1900 -> +500 while Bladefly is face-up
    assert s.effective_attack(wind.iid) == 1900 + 500
    # Flip Bladefly face-down: a face-down monster radiates nothing.
    s.inst(fly.iid).position = Position.FACE_DOWN_DEFENSE
    assert s.effective_attack(wind.iid) == 1900
