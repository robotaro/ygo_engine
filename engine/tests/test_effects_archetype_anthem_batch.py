"""Effects Batch 59: archetype/race anthems + a lord that shields itself.

Reuses the Batch 56 monster-borne FieldMod with side="self" + race/attribute narrows for
the "all your X monsters gain N" lords, and extends AttackTargetProtection with self_only +
"control another monster" gates (requires_control_other / _other_race / _other_attribute) so
Command Knight / Freya / Hunter Owl can shield just themselves while they control a partner.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ME, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


# --------------------------------------------------------------------------- #
#  Command Knight — Warrior anthem + self-shield while controlling another monster
# --------------------------------------------------------------------------- #
def test_command_knight_boosts_warriors_including_itself():
    s = _fresh()
    knight = _spawn(s, "Command Knight", ME, 0)  # Warrior 1200 -> +400
    celtic = _spawn(s, "Celtic Guardian", ME, 1)  # Warrior 1400 -> +400
    assert s.effective_attack(knight.iid) == 1200 + 400
    assert s.effective_attack(celtic.iid) == 1400 + 400


def test_command_knight_shields_itself_only_with_another_monster():
    s = _fresh()
    knight = _spawn(s, "Command Knight", ME, 0)
    assert not s.is_protected_attack_target(knight.iid)  # alone -> attackable
    other = _spawn(s, "Mystical Elf", ME, 1)  # any other monster turns the shield on
    assert s.is_protected_attack_target(knight.iid)
    assert not s.is_protected_attack_target(other.iid)  # the shield covers only Command Knight


# --------------------------------------------------------------------------- #
#  Freya — Fairy anthem + self-shield while controlling another Fairy
# --------------------------------------------------------------------------- #
def test_freya_boosts_fairies_atk_and_def():
    s = _fresh()
    freya = _spawn(s, "Freya, Spirit of Victory", ME, 0)  # Fairy 100/100 -> +400/+400
    angel = _spawn(s, "Shining Angel", ME, 1)  # Fairy 1400/800 -> +400/+400
    assert s.effective_attack(freya.iid) == 100 + 400
    assert s.effective_defense(angel.iid) == 800 + 400


def test_freya_shield_needs_another_fairy_specifically():
    s = _fresh()
    freya = _spawn(s, "Freya, Spirit of Victory", ME, 0)
    _spawn(s, "Celtic Guardian", ME, 1)  # a non-Fairy does NOT switch the shield on
    assert not s.is_protected_attack_target(freya.iid)
    _spawn(s, "Shining Angel", ME, 2)  # another Fairy does
    assert s.is_protected_attack_target(freya.iid)


# --------------------------------------------------------------------------- #
#  Hunter Owl — WIND count-scaling + self-shield while controlling another WIND
# --------------------------------------------------------------------------- #
def test_hunter_owl_scales_with_wind_and_shields_with_another():
    s = _fresh()
    owl = _spawn(s, "Hunter Owl", ME, 0)  # 1000; +500 per WIND (counts itself)
    assert s.effective_attack(owl.iid) == 1000 + 500
    assert not s.is_protected_attack_target(owl.iid)  # only itself so far
    _spawn(s, "Luster Dragon", ME, 1)  # another WIND
    assert s.effective_attack(owl.iid) == 1000 + 1000
    assert s.is_protected_attack_target(owl.iid)


# --------------------------------------------------------------------------- #
#  Nightmare Penguin — WATER anthem + flip-bounce
# --------------------------------------------------------------------------- #
def test_nightmare_penguin_boosts_water():
    s = _fresh()
    penguin = _spawn(s, "Nightmare Penguin", ME, 0)  # Aqua WATER 900 -> +200
    grizzly = _spawn(s, "Mother Grizzly", ME, 1)  # WATER 1400 -> +200
    assert s.effective_attack(penguin.iid) == 900 + 200
    assert s.effective_attack(grizzly.iid) == 1400 + 200


def test_nightmare_penguin_flip_bounces_an_opponent_card():
    s = _fresh()
    penguin = _spawn(s, "Nightmare Penguin", ME, 0)
    victim = _spawn(s, "Summoned Skull", OPP, 0)
    resolve_effect(s, EFFECTS["Nightmare Penguin"][0], penguin.iid, (victim.iid,), None)
    assert s.inst(victim.iid).zone is Zone.HAND
