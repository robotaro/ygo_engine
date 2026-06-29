"""Effects Batch 23: "destroyed by battle" -> Special Summon from the Deck.

The classic recruiter family (Mystic Tomato, Giant Rat, ...). A monster destroyed
by battle is stamped (CardInstance.died_by_battle); the engine's GY-queue drain
fires its "destroyed_by_battle" Trigger, which Special Summons a matching monster
(ATK 1500 or less) from the Deck via SpecialSummonFromDeck. The fetch is
deterministic (highest-ATK eligible match). Effect destruction does NOT recruit."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _battle_state():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 1, Phase.BATTLE  # player 1 is attacking
    return s


def _stock_deck(s, player, names):
    for name in names:
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


def _kill_tomato_in_battle(s):
    """Player 1's 1700 beater runs over player 0's Mystic Tomato (1400)."""
    tomato = s.spawn_on_field(reg.get("Mystic Tomato"), 0, 0, Position.FACE_UP_ATTACK)
    beater = s.spawn_on_field(reg.get("Archfiend Soldier"), 1, 0, Position.FACE_UP_ATTACK)  # 1900
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(beater.iid, tomato.iid), 1)
    return tomato


# --- the recruit fires on battle death and fetches a legal target ----------------
def test_mystic_tomato_recruits_a_dark_monster_on_battle_death():
    s = _battle_state()
    _stock_deck(s, 0, ["Akakieisu"])  # DARK, 1000 ATK -> eligible
    tomato = _kill_tomato_in_battle(s)
    assert s.inst(tomato.iid).zone is Zone.GRAVEYARD  # Tomato died in battle
    summoned = s.players[0].monster_zones[0]
    assert summoned is not None and s.inst(summoned).name == "Akakieisu"
    assert s.inst(summoned).position is Position.FACE_UP_ATTACK


def test_recruiter_fetches_the_highest_atk_match_under_the_cap():
    s = _battle_state()
    # Akakieisu(1000) & Archfiend Mirror(700) are eligible; Archfiend Soldier(1900) is not.
    _stock_deck(s, 0, ["Archfiend Mirror", "Akakieisu", "Archfiend Soldier"])
    _kill_tomato_in_battle(s)
    summoned = s.players[0].monster_zones[0]
    assert s.inst(summoned).name == "Akakieisu"  # highest ATK at or under 1500


def test_recruiter_does_nothing_when_no_eligible_target():
    s = _battle_state()
    _stock_deck(s, 0, ["Archfiend Soldier"])  # 1900 ATK -> over the cap
    _kill_tomato_in_battle(s)
    assert s.players[0].monster_zones[0] is None  # nothing summoned


# --- it must be a *battle* destruction -------------------------------------------
def test_recruiter_does_not_fire_on_effect_destruction():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    _stock_deck(s, 0, ["Akakieisu"])
    tomato = s.spawn_on_field(reg.get("Mystic Tomato"), 0, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(tomato.iid)  # an effect destroys it (by_battle defaults False)
    eng._check_field_to_gy_triggers()
    assert all(i is None for i in s.players[0].monster_zones)  # no recruit


# --- Pyramid Turtle filters by DEF, not ATK --------------------------------------
def test_pyramid_turtle_recruits_by_defense():
    s = _battle_state()
    _stock_deck(s, 0, ["Armored Zombie"])  # Zombie, DEF 0 -> eligible (<= 2000)
    turtle = s.spawn_on_field(reg.get("Pyramid Turtle"), 0, 0, Position.FACE_UP_ATTACK)
    beater = s.spawn_on_field(reg.get("Archfiend Soldier"), 1, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(beater.iid, turtle.iid), 1)
    summoned = s.players[0].monster_zones[0]
    assert summoned is not None and s.inst(summoned).name == "Armored Zombie"
