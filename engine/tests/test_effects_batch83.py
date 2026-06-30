"""Effects Batch 83: the "when this card is destroyed" trigger bucket.

The engine now stamps an effect destruction the way it already stamped a battle death:
every Destroy* primitive routes through ``send_to_graveyard(by_effect=True)``, which sets
``CardInstance.died_by_effect``. A monster's field->GY trigger can then key off *how* it
died, all drained from the same GY queue the recruiters use:

- ``destroyed_by_effect`` -- only a card-effect destruction (Babycerasaurus -> Special
  Summon a Level 4 or lower Dinosaur from the Deck). A battle death does NOT fire it.
- ``destroyed`` -- the unified trigger: battle OR effect destruction, but NOT a
  non-destruction send (tribute, discard, mill). Granadora burns its controller 2000.

A plain send to the GY (no ``by_battle``/``by_effect``) -- a tribute, discard or mill --
leaves both flags False, so neither new trigger fires.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import DestroyAllMonsters, EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _stock_deck(s, player, names):
    for name in names:
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


def _drain(s):
    Engine(s, [Agent(), Agent()])._check_field_to_gy_triggers()


# ============================ Babycerasaurus (destroyed_by_effect) ============================


def test_babycerasaurus_recruits_a_dinosaur_on_effect_destruction():
    s = _fresh()
    _stock_deck(s, 0, ["Sabersaurus"])  # Dinosaur, Lvl 4 -> eligible
    baby = _spawn(s, "Babycerasaurus", 0, 0)
    s.send_to_graveyard(baby.iid, by_effect=True)  # an effect destroys it
    _drain(s)
    summoned = s.players[0].monster_zones[0]
    assert summoned is not None and s.inst(summoned).name == "Sabersaurus"
    assert s.inst(summoned).position is Position.FACE_UP_ATTACK


def test_babycerasaurus_fires_through_a_real_destroy_primitive():
    # End-to-end: Dark Hole-style mass destruction (DestroyAllMonsters) is what tags the
    # death as by-effect, so the recruit fires off the primitive, not a hand-set flag.
    s = _fresh()
    _stock_deck(s, 0, ["Kabazauls"])  # Dinosaur, Lvl 4
    baby = _spawn(s, "Babycerasaurus", 0, 0)
    DestroyAllMonsters().execute(EffectContext(state=s, controller=0, source_iid=baby.iid))
    assert s.inst(baby.iid).zone is Zone.GRAVEYARD
    _drain(s)
    summoned = s.players[0].monster_zones[0]
    assert summoned is not None and s.inst(summoned).name == "Kabazauls"


def test_babycerasaurus_picks_the_highest_atk_eligible_dinosaur():
    s = _fresh()
    # Sabersaurus(1900) & Kabazauls(1700) eligible; Black Tyranno(Lvl 7) over the cap;
    # Celtic Guardian is a Warrior (wrong Type). Highest-ATK eligible -> Sabersaurus.
    _stock_deck(s, 0, ["Kabazauls", "Black Tyranno", "Celtic Guardian", "Sabersaurus"])
    baby = _spawn(s, "Babycerasaurus", 0, 0)
    s.send_to_graveyard(baby.iid, by_effect=True)
    _drain(s)
    summoned = s.players[0].monster_zones[0]
    assert s.inst(summoned).name == "Sabersaurus"


def test_babycerasaurus_does_not_recruit_on_battle_death():
    # "destroyed by a card effect" only -- a battle death must NOT trigger it.
    s = _fresh(tp=1, phase=Phase.BATTLE)
    s.turn_count = 2
    _stock_deck(s, 0, ["Sabersaurus"])
    baby = _spawn(s, "Babycerasaurus", 0, 0)  # 500 ATK
    beater = _spawn(s, "Archfiend Soldier", 1, 0)  # 1900 ATK
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(beater.iid, baby.iid), 1)
    assert s.inst(baby.iid).zone is Zone.GRAVEYARD  # died in battle
    assert all(i is None or s.inst(i).name != "Sabersaurus" for i in s.players[0].monster_zones)


def test_babycerasaurus_does_not_recruit_on_a_plain_send():
    # A non-destruction send (tribute/discard/mill) leaves died_by_effect False.
    s = _fresh()
    _stock_deck(s, 0, ["Sabersaurus"])
    baby = _spawn(s, "Babycerasaurus", 0, 0)
    s.send_to_graveyard(baby.iid)  # neither by_battle nor by_effect
    _drain(s)
    assert all(i is None for i in s.players[0].monster_zones)


def test_babycerasaurus_does_nothing_with_no_eligible_target():
    s = _fresh()
    _stock_deck(s, 0, ["Black Tyranno"])  # Dinosaur but Lvl 7 -> over the cap
    baby = _spawn(s, "Babycerasaurus", 0, 0)
    s.send_to_graveyard(baby.iid, by_effect=True)
    _drain(s)
    assert all(i is None for i in s.players[0].monster_zones)


# ============================ Granadora (summon + unified destroyed) ==========================


def test_granadora_gains_1000_on_summon():
    s = _fresh()
    g = _spawn(s, "Granadora", 0, 0)
    s.players[0].life_points = 8000
    Engine(s, [Agent(), Agent()])._trigger_summon_effect(g.iid, "normal")
    assert s.players[0].life_points == 9000


def test_granadora_burns_2000_when_destroyed_by_effect():
    s = _fresh()
    g = _spawn(s, "Granadora", 0, 0)
    s.players[0].life_points = 8000
    s.send_to_graveyard(g.iid, by_effect=True)
    _drain(s)
    assert s.players[0].life_points == 6000  # the unified "destroyed" trigger fired


def test_granadora_burns_2000_when_destroyed_by_battle():
    # The unified "destroyed" trigger also covers a battle death.
    s = _fresh()
    g = _spawn(s, "Granadora", 0, 0)
    s.players[0].life_points = 8000
    s.send_to_graveyard(g.iid, by_battle=True)
    _drain(s)
    assert s.players[0].life_points == 6000


def test_granadora_does_not_burn_on_a_plain_send():
    # Tributed / discarded / milled -- not "destroyed" -- so no self-burn.
    s = _fresh()
    g = _spawn(s, "Granadora", 0, 0)
    s.players[0].life_points = 8000
    s.send_to_graveyard(g.iid)
    _drain(s)
    assert s.players[0].life_points == 8000
