"""Effects Batch 60: more attribute anthems (both sides) + a position-gated anthem.

Harpie Lady 1 / Hoshiningen / Little Chimera reuse the Batch 56 monster-borne FieldMod
(both sides) with no new engine work. Fairy King Truesdale adds FieldMod.source_in_defense:
its Plant anthem only radiates while the source monster is itself in face-up Defense Position.
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


def test_harpie_lady_1_boosts_all_wind_both_sides():
    s = _fresh()
    harpie = _spawn(s, "Harpie Lady 1", ME, 0)  # WIND 1300 -> +300
    mine = _spawn(s, "Luster Dragon", ME, 1)  # WIND 1900 -> +300
    theirs = _spawn(s, "Luster Dragon", OPP, 0)  # the opponent's WIND is boosted too
    assert s.effective_attack(harpie.iid) == 1300 + 300
    assert s.effective_attack(mine.iid) == 1900 + 300
    assert s.effective_attack(theirs.iid) == 1900 + 300


def test_hoshiningen_boosts_light_and_weakens_dark():
    s = _fresh()
    hoshi = _spawn(s, "Hoshiningen", ME, 0)  # LIGHT 500 -> +500
    dark = _spawn(s, "Summoned Skull", OPP, 0)  # DARK 2500 -> -400
    assert s.effective_attack(hoshi.iid) == 500 + 500
    assert s.effective_attack(dark.iid) == 2500 - 400


def test_little_chimera_boosts_fire_and_weakens_water():
    s = _fresh()
    chimera = _spawn(s, "Little Chimera", ME, 0)  # FIRE 600 -> +500
    water = _spawn(s, "Mother Grizzly", ME, 1)  # WATER 1400 -> -400
    assert s.effective_attack(chimera.iid) == 600 + 500
    assert s.effective_attack(water.iid) == 1400 - 400


def test_fairy_king_truesdale_only_radiates_in_defense():
    s = _fresh()
    king = _spawn(s, "Fairy King Truesdale", ME, 0, Position.FACE_UP_DEFENSE)  # Plant 2200/1500
    not_plant = _spawn(s, "Celtic Guardian", ME, 1)  # Warrior -> never boosted
    assert s.effective_attack(king.iid) == 2200 + 500  # +500 ATK while in Defense
    assert s.effective_defense(king.iid) == 1500 + 500
    assert s.effective_attack(not_plant.iid) == 1400  # a non-Plant gets nothing
    # Switch the king to Attack Position: the anthem goes dormant.
    king.position = Position.FACE_UP_ATTACK
    assert s.effective_attack(king.iid) == 2200
    assert s.effective_defense(king.iid) == 1500
