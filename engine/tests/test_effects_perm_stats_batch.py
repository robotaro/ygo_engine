"""Effects Batch 73: permanent ATK debuffs (Slate Warrior, Zombyra), Megamorph, Nimble
Momonga.

Adds permanent ATK/DEF deltas (`CardInstance.perm_atk/perm_def`, summed in
`_effective_stat`): Slate Warrior gains 500 on Flip and makes its battle-destroyer lose
500; Zombyra loses 200 each time it destroys by battle. Megamorph is an Equip whose
`lp_megamorph` EquipMod doubles/halves the host's original ATK by the LP comparison.
Nimble Momonga, destroyed by battle, gains 1000 LP and Special Summons its copies from
the Deck (the SpecialSummonFromDeck `count`).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _attack(s, attacker, target):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), s.turn_player)


# ------------------------------------------------------------------ Slate Warrior


def test_slate_warrior_flip_gains_500_permanently():
    s = _fresh()
    slate = _spawn(s, "Slate Warrior", ME, 0, pos=Position.FACE_DOWN_DEFENSE)
    flip_effect = EFFECTS["Slate Warrior"][0]
    ctx = EffectContext(state=s, controller=ME, source_iid=slate.iid)
    for prim in flip_effect.resolve:
        prim.execute(ctx)
    assert slate.perm_atk == 500 and slate.perm_def == 500
    assert s.effective_attack(slate.iid) == 1900 + 500


def test_slate_warrior_makes_its_battle_destroyer_lose_500():
    s = _fresh(tp=OPP)
    skull = _spawn(s, "Summoned Skull", OPP, 0)  # 2500 attacker, survives
    slate = _spawn(s, "Slate Warrior", ME, 0)  # 1900, destroyed by battle
    _attack(s, skull.iid, slate.iid)
    assert slate.zone is Zone.GRAVEYARD
    assert skull.perm_atk == -500 and skull.perm_def == -500
    assert s.effective_attack(skull.iid) == 2500 - 500


# ----------------------------------------------------------------- Zombyra the Dark


def test_zombyra_loses_200_each_time_it_destroys():
    s = _fresh(tp=ME)
    zombyra = _spawn(s, "Zombyra the Dark", ME, 0)  # 2100 attacker
    prey = _spawn(s, "Celtic Guardian", OPP, 0)  # 1400, destroyed
    _attack(s, zombyra.iid, prey.iid)
    assert prey.zone is Zone.GRAVEYARD
    assert zombyra.perm_atk == -200
    assert s.effective_attack(zombyra.iid) == 2100 - 200


# --------------------------------------------------------------------- Megamorph


def _equip_megamorph(s, host, player):
    eq = s.create_instance(reg.get("Megamorph"), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(eq.iid)
    s.place_spell_trap(eq.iid, player, 0, Position.FACE_UP_ATTACK)
    eq.equipped_to = host.iid
    return eq


def test_megamorph_doubles_when_behind_halves_when_ahead():
    s = _fresh()
    host = _spawn(s, "Summoned Skull", ME, 0)  # original ATK 2500
    _equip_megamorph(s, host, ME)
    s.players[ME].life_points, s.players[OPP].life_points = 3000, 8000  # behind -> double
    assert s.effective_attack(host.iid) == 5000
    s.players[ME].life_points, s.players[OPP].life_points = 8000, 3000  # ahead -> half
    assert s.effective_attack(host.iid) == 1250
    s.players[ME].life_points, s.players[OPP].life_points = 4000, 4000  # equal -> unchanged
    assert s.effective_attack(host.iid) == 2500


# ---------------------------------------------------------------- Nimble Momonga


def test_nimble_momonga_gains_lp_and_summons_copies_from_deck():
    s = _fresh(tp=OPP)
    skull = _spawn(s, "Summoned Skull", OPP, 0)  # 2500, destroys Nimble
    # Defense Position so the kill deals no battle damage — isolates the +1000 LP gain.
    nimble = _spawn(s, "Nimble Momonga", ME, 0, pos=Position.FACE_UP_DEFENSE)
    for _ in range(2):
        i = s.create_instance(reg.get("Nimble Momonga"), owner=ME, zone=Zone.DECK)
        s.players[ME].deck.append(i.iid)
    lp_before = s.players[ME].life_points
    _attack(s, skull.iid, nimble.iid)
    assert nimble.zone is Zone.GRAVEYARD
    assert s.players[ME].life_points == lp_before + 1000
    on_field = [i for i in s.players[ME].monster_zones if i is not None]
    assert len(on_field) == 2  # the two deck copies
    assert all(s.inst(i).position is Position.FACE_DOWN_DEFENSE for i in on_field)
