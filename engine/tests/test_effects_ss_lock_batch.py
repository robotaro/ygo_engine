"""Effects Batch 41: Special Summon locks (Barrier Statues / Vanity).

A face-up SpecialSummonLock rider stops Special Summons via every route — read by
GameState.special_summon_locked, which each SS site consults (hand-SS enumeration,
SpecialSummonFromGraveyard/FromDeck, CreateToken, Fusion/Ritual summon). ``whose``
picks who is locked ("both" / opponent-only); ``except_attribute`` lets one attribute
through (the Barrier Statues). Cards: Vanity's Fiend, Vanity's Ruler, Barrier Statue
of the Inferno (except FIRE), Barrier Statue of the Torrent (except WATER).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, SpecialSummonFromHand, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

DARK = reg.get("Summoned Skull")  # DARK Fiend (non-FIRE, non-WATER)
FIRE = reg.get("UFO Turtle")  # FIRE Machine
WATER = reg.get("Mother Grizzly")  # WATER Beast-Warrior


def _fresh(turn_player=0):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, turn_player, Phase.MAIN_1
    return s


# --- the predicate -----------------------------------------------------------------
def test_vanitys_fiend_locks_both_players():
    s = _fresh()
    s.spawn_on_field(reg.get("Vanity's Fiend"), 0, 0, Position.FACE_UP_ATTACK)
    assert s.special_summon_locked(0, DARK)  # controller is locked too
    assert s.special_summon_locked(1, DARK)  # and so is the opponent


def test_vanitys_ruler_locks_only_the_opponent():
    s = _fresh()
    s.spawn_on_field(reg.get("Vanity's Ruler"), 0, 0, Position.FACE_UP_ATTACK)
    assert not s.special_summon_locked(0, DARK)  # the controller may still Special Summon
    assert s.special_summon_locked(1, DARK)  # the opponent cannot


def test_barrier_statue_inferno_allows_only_fire():
    s = _fresh()
    s.spawn_on_field(reg.get("Barrier Statue of the Inferno"), 0, 0, Position.FACE_UP_ATTACK)
    for pl in (0, 1):
        assert not s.special_summon_locked(pl, FIRE)  # FIRE slips through
        assert s.special_summon_locked(pl, DARK)  # everything else is locked
        assert s.special_summon_locked(pl, WATER)


def test_barrier_statue_torrent_allows_only_water():
    s = _fresh()
    s.spawn_on_field(reg.get("Barrier Statue of the Torrent"), 0, 0, Position.FACE_UP_ATTACK)
    assert not s.special_summon_locked(0, WATER)
    assert s.special_summon_locked(0, FIRE)


# --- the routes honour the lock ----------------------------------------------------
def _can_hand_ss(s, player, iid):
    return any(
        isinstance(a, SpecialSummonFromHand) and a.iid == iid
        for a in legal_actions(s, player)
    )


def test_hand_special_summon_is_gated_by_the_lock():
    # Player 1 holds Cyber Dragon; the opponent controls a monster and player 1 controls
    # none, so its hand-SS condition holds.
    s = _fresh(turn_player=1)
    cyber = s.create_instance(reg.get("Cyber Dragon"), 1, Zone.HAND)
    s.players[1].hand.append(cyber.iid)
    skull = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    assert _can_hand_ss(s, 1, cyber.iid)  # offered with no lock present
    # Swap the plain opponent monster for Vanity's Fiend (still satisfies the condition,
    # now also locks both players) -> the hand-SS vanishes.
    s.send_to_graveyard(skull.iid)
    s.spawn_on_field(reg.get("Vanity's Fiend"), 0, 0, Position.FACE_UP_ATTACK)
    assert not _can_hand_ss(s, 1, cyber.iid)


def _activate(s, spell_iid, targets=()):
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(spell_iid, targets=targets), 0)


def test_monster_reborn_revival_is_blocked_by_the_lock():
    s = _fresh()
    dead = s.create_instance(reg.get("Summoned Skull"), 0, Zone.GRAVEYARD)
    s.players[0].graveyard.append(dead.iid)
    reborn = s.create_instance(reg.get("Monster Reborn"), 0, Zone.HAND)
    s.players[0].hand.append(reborn.iid)
    idx = next(i for i, z in enumerate(s.players[0].spell_trap_zones) if z is None)
    s.place_spell_trap(reborn.iid, 0, idx, Position.FACE_DOWN)
    reborn.set_on_turn = s.turn_count - 1
    s.spawn_on_field(reg.get("Vanity's Fiend"), 0, 1, Position.FACE_UP_ATTACK)
    _activate(s, reborn.iid, targets=(dead.iid,))
    assert s.inst(dead.iid).zone is Zone.GRAVEYARD  # the revival fizzled


def _set_spell_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def test_scapegoat_makes_no_tokens_under_a_lock():
    s = _fresh()
    s.spawn_on_field(reg.get("Vanity's Fiend"), 0, 0, Position.FACE_UP_ATTACK)
    goat = _set_spell_trap(s, "Scapegoat", 0)
    _activate(s, goat.iid)
    tokens = [
        i for i in s.players[0].monster_zones if i is not None and s.inst(i).card.is_token
    ]
    assert tokens == []  # the Sheep Tokens are barred by the lock


def test_union_cannot_unequip_summon_under_a_lock():
    # Regression: a Union monster returning to the Monster Zone is a Special Summon, so
    # it must honour the lock too. Routing every SS site through state.special_summon
    # closed this gap (the Union route had silently skipped the check).
    from ygo.moves import UnionEquip, UnionUnequip, apply, legal_actions

    s = _fresh()
    host = s.spawn_on_field(reg.get("X-Head Cannon"), 0, 0, Position.FACE_UP_ATTACK)
    union = s.spawn_on_field(reg.get("Y-Dragon Head"), 0, 1, Position.FACE_UP_ATTACK)
    apply(s, UnionEquip(union.iid, host.iid))
    s.turn_count = 3
    s.spawn_on_field(reg.get("Vanity's Fiend"), 0, 2, Position.FACE_UP_ATTACK)
    # The unequip (a Special Summon) is neither offered nor performed under the lock.
    assert not any(isinstance(a, UnionUnequip) for a in legal_actions(s, 0))
    apply(s, UnionUnequip(union.iid))
    assert s.inst(union.iid).zone is Zone.SPELL_TRAP  # still equipped — summon barred


def test_no_lock_means_normal_special_summons():
    s = _fresh()
    assert not s.special_summon_locked(0, DARK)
    assert not s.special_summon_locked(1, FIRE)
