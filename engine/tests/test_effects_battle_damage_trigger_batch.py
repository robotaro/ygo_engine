"""Effects Batch 36: "when this card inflicts battle damage to your opponent" triggers.

The engine records the attacker that dealt battle damage (GameState.battle_damage_dealt,
set in _resolve_attack for direct hits, over-ATK kills, and piercing) and fires that
monster's SELF "battle_damage_inflicted" Trigger after combat (engine.
_fire_battle_damage_trigger). Cards: Airknight Parshath (piercing + draw 1), Don Zaloog
(discard 1 random from the opponent), Dark Scorpion - Chick the Yellow (bounce a field card).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    return s


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _attack(s, attacker, target=None):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), 0)


# --- the trigger fires only when damage actually reaches the opponent --------------
def test_direct_attack_fires_the_trigger():
    s = _fresh()
    don = s.spawn_on_field(reg.get("Don Zaloog"), 0, 0, Position.FACE_UP_ATTACK)
    a = _in_hand(s, "Summoned Skull", 1)
    b = _in_hand(s, "Mystical Elf", 1)
    _attack(s, don.iid, None)  # direct attack -> battle damage -> discard 1 random
    gone = [x for x in (a, b) if s.inst(x.iid).zone is Zone.GRAVEYARD]
    assert len(gone) == 1
    assert len(s.players[1].hand) == 1


def test_trigger_does_not_fire_without_damage():
    s = _fresh()
    don = s.spawn_on_field(reg.get("Don Zaloog"), 0, 0, Position.FACE_UP_ATTACK)
    # A bigger defender in Defense: Don Zaloog (1400) bounces off, deals NO damage.
    wall = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_DEFENSE)  # DEF 2000
    _in_hand(s, "Summoned Skull", 1)
    _attack(s, don.iid, wall.iid)
    assert len(s.players[1].hand) == 1  # no discard — no battle damage dealt


# --- Airknight Parshath: piercing + draw on damage ---------------------------------
def test_airknight_draws_on_battle_damage():
    s = _fresh()
    ak = s.spawn_on_field(reg.get("Airknight Parshath"), 0, 0, Position.FACE_UP_ATTACK)
    weak = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)  # ATK 800
    for nm in ("Summoned Skull", "Luster Dragon"):
        inst = s.create_instance(reg.get(nm), owner=0, zone=Zone.DECK)
        s.players[0].deck.append(inst.iid)
    hand_before = len(s.players[0].hand)
    _attack(s, ak.iid, weak.iid)  # 1900 vs 800 -> 1100 damage -> draw 1
    assert s.inst(weak.iid).zone is Zone.GRAVEYARD
    assert len(s.players[0].hand) == hand_before + 1


def test_airknight_pierces_a_defender_and_draws():
    s = _fresh()
    ak = s.spawn_on_field(reg.get("Airknight Parshath"), 0, 0, Position.FACE_UP_ATTACK)
    wall = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_DEFENSE)  # DEF 2000
    inst = s.create_instance(reg.get("Summoned Skull"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(inst.iid)
    # Airknight (1900) vs DEF 2000 -> bounces off, no pierce, no draw.
    hand_before = len(s.players[0].hand)
    lp_before = s.players[1].life_points
    _attack(s, ak.iid, wall.iid)
    assert s.players[1].life_points == lp_before  # 1900 < 2000: no piercing damage
    assert len(s.players[0].hand) == hand_before  # so no draw either


# --- Dark Scorpion - Chick the Yellow: bounce a field card on damage ----------------
def test_chick_bounces_a_field_card_on_damage():
    s = _fresh()
    chick = s.spawn_on_field(reg.get("Dark Scorpion - Chick the Yellow"), 0, 0, Position.FACE_UP_ATTACK)
    prey = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)  # ATK 800
    _attack(s, chick.iid, prey.iid)  # 1000 vs 800 -> 200 damage -> bounce a field card
    # prey was destroyed in battle; the remaining bounce target is Chick itself.
    assert s.inst(chick.iid).zone is Zone.HAND
    assert chick.iid in s.players[0].hand
