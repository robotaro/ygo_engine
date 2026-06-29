"""Effects Batch 66: "when this card destroys a monster by battle" SELF Triggers.

Combat records each (destroyer, destroyed) pair (moves._battle_destroy ->
GameState.battle_destroyed_by); after the attack the engine fires the destroyer's SELF
"destroys_by_battle" Trigger (engine._fire_destroys_by_battle_trigger), with the dead
monster's iid on the event so the payload can read its original ATK or banish it.
Authored: Masked Chopper (burn 2000), Guardian Angel Joan (gain LP = destroyed monster's
ATK), Hydrogeddon (recruit another from Deck), Divine Knight Ishzark (banish it), Blue
Thunder T-45 (Special Summon a Token).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, ME, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _attack(s, attacker, target=None):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), ME)


def test_masked_chopper_burns_2000_when_it_destroys_a_monster():
    s = _fresh()
    chopper = _spawn(s, "Masked Chopper", ME, 0)  # ATK 100
    chopper.temp_atk = 3000  # pump it so it actually wins combat
    # A Defense-Position prey: a clean break deals no battle damage, isolating the burn.
    prey = _spawn(s, "Mystical Elf", OPP, 0, pos=Position.FACE_UP_DEFENSE)  # DEF 2000
    _attack(s, chopper.iid, prey.iid)
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD
    assert s.players[OPP].life_points == 8000 - 2000


def test_masked_chopper_does_not_burn_when_it_loses():
    s = _fresh()
    chopper = _spawn(s, "Masked Chopper", ME, 0)  # ATK 100
    wall = _spawn(s, "Summoned Skull", OPP, 0)  # ATK 2500 -> Chopper dies
    _attack(s, chopper.iid, wall.iid)
    assert s.inst(chopper.iid).zone is Zone.GRAVEYARD
    assert s.players[OPP].life_points == 8000  # Chopper never destroyed anything


def test_guardian_angel_joan_gains_lp_equal_to_destroyed_atk():
    s = _fresh()
    joan = _spawn(s, "Guardian Angel Joan", ME, 0)  # ATK 2800
    prey = _spawn(s, "Summoned Skull", OPP, 0)  # original ATK 2500
    _attack(s, joan.iid, prey.iid)
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD
    assert s.players[ME].life_points == 8000 + 2500


def test_mutual_destruction_does_not_fire_the_trigger():
    s = _fresh()
    joan = _spawn(s, "Guardian Angel Joan", ME, 0)  # ATK 2800
    rival = _spawn(s, "Summoned Skull", OPP, 0)
    s.inst(rival.iid).temp_atk = 300  # 2500 + 300 = 2800 -> both destroyed
    _attack(s, joan.iid, rival.iid)
    assert s.inst(joan.iid).zone is Zone.GRAVEYARD
    assert s.players[ME].life_points == 8000  # Joan died with the kill -> no LP gain


def test_hydrogeddon_recruits_another_from_the_deck():
    s = _fresh()
    hydro = _spawn(s, "Hydrogeddon", ME, 0)  # ATK 1600
    prey = _spawn(s, "Mystical Elf", OPP, 0)  # ATK 800
    deck_copy = s.create_instance(reg.get("Hydrogeddon"), owner=ME, zone=Zone.DECK)
    s.players[ME].deck.append(deck_copy.iid)
    _attack(s, hydro.iid, prey.iid)
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD
    assert s.inst(deck_copy.iid).zone is Zone.MONSTER  # the 2nd Hydrogeddon is summoned


def test_divine_knight_ishzark_banishes_the_destroyed_monster():
    s = _fresh()
    ishzark = _spawn(s, "Divine Knight Ishzark", ME, 0)  # ATK 2300
    prey = _spawn(s, "Mystical Elf", OPP, 0)  # ATK 800
    _attack(s, ishzark.iid, prey.iid)
    assert s.inst(prey.iid).zone is Zone.BANISHED
    assert prey.iid not in s.players[OPP].graveyard


def test_blue_thunder_summons_a_token_on_destruction():
    s = _fresh()
    blue = _spawn(s, "Blue Thunder T-45", ME, 0)  # ATK 1700
    prey = _spawn(s, "Mystical Elf", OPP, 0)  # ATK 800
    before = sum(1 for i in s.players[ME].monster_zones if i is not None)
    _attack(s, blue.iid, prey.iid)
    after = [s.inst(i) for i in s.players[ME].monster_zones if i is not None]
    assert any(m.card.is_token and m.name == "Thunder Option Token" for m in after)
    assert len(after) == before + 1
