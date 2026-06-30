"""Effects Batch 99: a Ritual pair + their boss.

- Curse of the Masked Beast: Ritual Spell for "The Masked Beast" (Level 8 fodder).
- Shinato's Ark: Ritual Spell for "Shinato, King of a Higher Plane" (Level 8 fodder).
- Shinato, King of a Higher Plane: when it destroys a Defense-Position monster by battle,
  inflict damage to the opponent equal to that monster's original ATK.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import RITUALS
from ygo.deckbuild import is_functional
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, can_ritual_summon
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


# --------------------------------------------------------------------- Ritual Spells


def test_curse_of_the_masked_beast_recipe():
    assert RITUALS["Curse of the Masked Beast"] == "The Masked Beast"
    assert is_functional(reg.get("Curse of the Masked Beast"))


def test_curse_ritual_summonable_with_level8_fodder():
    s = _fresh()
    _in_hand(s, "The Masked Beast", A)
    _in_hand(s, "Curse of the Masked Beast", A)
    _spawn(s, "Blue-Eyes White Dragon", A, 0)  # Level 8 fodder (>= 8)
    assert can_ritual_summon(s, A, "The Masked Beast")


def test_shinatos_ark_recipe():
    assert RITUALS["Shinato's Ark"] == "Shinato, King of a Higher Plane"
    assert is_functional(reg.get("Shinato's Ark"))
    assert is_functional(reg.get("Shinato, King of a Higher Plane"))


def test_shinato_ark_ritual_summonable():
    s = _fresh()
    _in_hand(s, "Shinato, King of a Higher Plane", A)
    _in_hand(s, "Shinato's Ark", A)
    _spawn(s, "Blue-Eyes White Dragon", A, 0)  # Level 8 fodder
    assert can_ritual_summon(s, A, "Shinato, King of a Higher Plane")


# ------------------------------------------------------- Shinato's defense-burn effect


def test_shinato_burns_defense_monster_original_atk():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    shinato = _spawn(s, "Shinato, King of a Higher Plane", A, 0)  # 3300 ATK
    # 7 Colored Fish in Defense (DEF 800, original ATK 1800) — destroyed, then burned 1800.
    foe = _spawn(s, "7 Colored Fish", B, 0, Position.FACE_UP_DEFENSE)
    s.players[B].life_points = 8000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(shinato.iid, foe.iid), A)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # destroyed (3300 > 800 DEF)
    assert s.players[B].life_points == 8000 - 1800  # burn = the Fish's original ATK


def test_shinato_does_not_burn_attack_position_kill():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    shinato = _spawn(s, "Shinato, King of a Higher Plane", A, 0)  # 3300 ATK
    foe = _spawn(s, "7 Colored Fish", B, 0, Position.FACE_UP_ATTACK)  # 1800 ATK
    s.players[B].life_points = 8000
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(shinato.iid, foe.iid), A)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD
    # only the ordinary battle damage (3300 - 1800 = 1500), no extra defense-burn
    assert s.players[B].life_points == 8000 - 1500
