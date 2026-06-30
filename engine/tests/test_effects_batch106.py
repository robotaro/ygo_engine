"""Effects Batch 106: Alligator's Sword Dragon.

A Fusion ("Baby Dragon" + "Alligator's Sword") that can attack the opponent directly if
the only face-up monsters they control are EARTH, WATER, or FIRE.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.card_effects import FUSIONS
from ygo.deckbuild import is_functional
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, _battle_phase_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _can_direct(s, attacker):
    return any(
        isinstance(a, DeclareAttack) and a.attacker == attacker and a.target is None
        for a in _battle_phase_actions(s, A)
    )


def test_alligator_fusion_recipe_and_functional():
    assert FUSIONS["Alligator's Sword Dragon"] == ("Baby Dragon", "Alligator's Sword")
    assert is_functional(reg.get("Alligator's Sword Dragon"))


def test_direct_attack_when_opponent_all_earth_water_fire():
    s = _fresh()
    gator = _spawn(s, "Alligator's Sword Dragon", A, 0)
    _spawn(s, "7 Colored Fish", B, 0)  # WATER
    _spawn(s, "Petit Moth", B, 1)  # EARTH
    assert s.can_attack_directly(gator.iid)
    assert _can_direct(s, gator.iid)  # may bypass the EARTH/WATER monsters


def test_no_direct_attack_when_opponent_has_a_dark_monster():
    s = _fresh()
    gator = _spawn(s, "Alligator's Sword Dragon", A, 0)
    _spawn(s, "7 Colored Fish", B, 0)  # WATER
    _spawn(s, "Summoned Skull", B, 1)  # DARK -> blocks the bypass
    assert not s.can_attack_directly(gator.iid)
    assert not _can_direct(s, gator.iid)


def test_face_down_opponent_monster_does_not_block():
    s = _fresh()
    gator = _spawn(s, "Alligator's Sword Dragon", A, 0)
    _spawn(s, "Summoned Skull", B, 0, Position.FACE_DOWN_DEFENSE)  # DARK but face-down
    assert s.can_attack_directly(gator.iid)  # only face-up attributes are checked
