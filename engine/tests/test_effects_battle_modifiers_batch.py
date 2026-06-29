"""Effects Batch 38: battle modifiers — direct attack & cannot-be-destroyed-by-battle.

Two continuous riders: CanAttackDirectly (the monster may declare a direct attack even
while the opponent controls monsters — read by the battle-phase enumeration) and
BattleIndestructible (the monster survives a combat it would lose, but battle damage
still applies — read by the combat step's _battle_destroy). Cards: Goblin Black Ops /
Raging Flame Sprite (direct), Arcana Force 0 - The Fool / Marshmallon / Spirit Reaper
(indestructible; Spirit Reaper also discards on battle damage).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    return s


def _attacks(s, attacker):
    return [a for a in legal_actions(s, 0) if isinstance(a, DeclareAttack) and a.attacker == attacker]


def _resolve(s, attacker, target):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), 0)


# --- direct attack despite the opponent having monsters ----------------------------
def test_direct_attacker_may_bypass_opponent_monsters():
    s = _fresh()
    goblin = s.spawn_on_field(reg.get("Goblin Black Ops"), 0, 0, Position.FACE_UP_ATTACK)
    blocker = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    targets = {a.target for a in _attacks(s, goblin.iid)}
    assert None in targets  # may attack directly
    assert blocker.iid in targets  # may also attack the monster


def test_direct_attack_deals_full_damage():
    s = _fresh()
    sprite = s.spawn_on_field(reg.get("Raging Flame Sprite"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # a blocker
    before = s.players[1].life_points
    _resolve(s, sprite.iid, None)  # direct, bypassing the blocker
    assert s.players[1].life_points == before - 100  # Raging Flame Sprite's 100 ATK


def test_ordinary_monster_cannot_attack_directly_through_a_blocker():
    s = _fresh()
    skull = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    assert None not in {a.target for a in _attacks(s, skull.iid)}


# --- cannot be destroyed by battle -------------------------------------------------
def test_marshmallon_survives_a_stronger_attacker_but_owner_takes_damage():
    s = _fresh()
    # Opponent's turn isn't needed; we attack our own Marshmallon's controller via B.
    s.turn_player = 1
    attacker = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # 2500
    marsh = s.spawn_on_field(reg.get("Marshmallon"), 0, 0, Position.FACE_UP_ATTACK)  # 300, indestructible
    before = s.players[0].life_points
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker.iid, marsh.iid), 1)
    assert s.inst(marsh.iid).zone is Zone.MONSTER  # survived
    assert s.players[0].life_points == before - (2500 - 300)  # but took the battle damage


def test_indestructible_attacker_survives_attacking_a_bigger_monster():
    s = _fresh()
    fool = s.spawn_on_field(reg.get("Arcana Force 0 - The Fool"), 0, 0, Position.FACE_UP_ATTACK)  # 0 ATK
    wall = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # 2500
    before = s.players[0].life_points
    _resolve(s, fool.iid, wall.iid)
    assert s.inst(fool.iid).zone is Zone.MONSTER  # The Fool survives losing combat
    assert s.players[0].life_points == before - 2500  # still takes the damage


def test_normal_monster_is_destroyed_by_a_stronger_one():
    s = _fresh()
    s.turn_player = 1
    attacker = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    victim = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # 800, normal
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker.iid, victim.iid), 1)
    assert s.inst(victim.iid).zone is Zone.GRAVEYARD  # the control case: it IS destroyed


# --- Spirit Reaper: indestructible AND discards on battle damage -------------------
def test_spirit_reaper_survives_and_discards_on_direct_hit():
    s = _fresh()
    reaper = s.spawn_on_field(reg.get("Spirit Reaper"), 0, 0, Position.FACE_UP_ATTACK)
    a = s.create_instance(reg.get("Summoned Skull"), owner=1, zone=Zone.HAND)
    b = s.create_instance(reg.get("Mystical Elf"), owner=1, zone=Zone.HAND)
    s.players[1].hand.extend([a.iid, b.iid])
    _resolve(s, reaper.iid, None)  # direct attack -> 300 damage -> discard 1 random
    assert sum(1 for x in (a, b) if s.inst(x.iid).zone is Zone.GRAVEYARD) == 1
