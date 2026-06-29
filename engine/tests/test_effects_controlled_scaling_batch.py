"""Effects Batch 55: continuous ATK scaling by the controller's own face-up monsters.

New SelfStatMod scaling mode "controlled_monsters": +scale per face-up monster the
controller controls matching count_name_contains / count_race / count_attribute (the
source counts itself when it matches, unless count_exclude_self). Read through the same
_self_stat_delta chokepoint as the other scaling modes (so Skill Drain still suppresses it).
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


def test_amazoness_paladin_scales_with_amazoness_count():
    s = _fresh()
    pal = _spawn(s, "Amazoness Paladin", ME, 0)  # base 1700, counts itself
    assert s.effective_attack(pal.iid) == 1700 + 100  # 1 Amazoness (itself)
    _spawn(s, "Amazoness Swords Woman", ME, 1)  # a second Amazoness
    assert s.effective_attack(pal.iid) == 1700 + 200


def test_botanical_lion_scales_with_plants():
    s = _fresh()
    lion = _spawn(s, "Botanical Lion", ME, 0)  # base 1600, Plant-Type (counts itself)
    assert s.effective_attack(lion.iid) == 1600 + 300
    _spawn(s, "Botanical Lion", ME, 1)  # a second Plant
    assert s.effective_attack(lion.iid) == 1600 + 600


def test_only_your_side_is_counted():
    s = _fresh()
    pal = _spawn(s, "Amazoness Paladin", ME, 0)
    _spawn(s, "Amazoness Swords Woman", OPP, 0)  # the opponent's Amazoness does NOT count
    assert s.effective_attack(pal.iid) == 1700 + 100


def test_battleguards_pump_each_other():
    s = _fresh()
    lava = _spawn(s, "Lava Battleguard", ME, 0)  # base 1550, +500 per Swamp Battleguard
    assert s.effective_attack(lava.iid) == 1550  # no partner yet -> no bonus
    swamp = _spawn(s, "Swamp Battleguard", ME, 1)  # base 1800, +500 per Lava Battleguard
    assert s.effective_attack(lava.iid) == 1550 + 500
    assert s.effective_attack(swamp.iid) == 1800 + 500


def test_elemental_hero_heat_scales_with_heroes():
    s = _fresh()
    heat = _spawn(s, "Elemental HERO Heat", ME, 0)  # base 1600
    assert s.effective_attack(heat.iid) == 1600 + 200  # counts itself
    _spawn(s, "Elemental HERO Heat", ME, 1)
    assert s.effective_attack(heat.iid) == 1600 + 400


def test_amazoness_tiger_pumps_and_protects_other_amazoness():
    s = _fresh()
    tiger = _spawn(s, "Amazoness Tiger", ME, 0)  # base 1100, +400 per Amazoness
    pal = _spawn(s, "Amazoness Paladin", ME, 1)  # another Amazoness
    other = _spawn(s, "Celtic Guardian", ME, 2)  # not an Amazoness
    assert s.effective_attack(tiger.iid) == 1100 + 800  # 2 Amazoness
    assert s.is_protected_attack_target(pal.iid)  # the other Amazoness is protected
    assert not s.is_protected_attack_target(tiger.iid)  # except this one (the decoy)
    assert not s.is_protected_attack_target(other.iid)  # a non-Amazoness is attackable
