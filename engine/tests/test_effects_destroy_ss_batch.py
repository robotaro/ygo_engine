"""Effects Batch 44: "destroy all Special Summoned monsters" floodgates.

A persistent per-monster ``was_special_summoned`` flag, stamped True in the single
``state.special_summon`` chokepoint (and on a Token), reset to False by Normal
Summon/Set (``place_monster``) and on leaving the field. Read by the new
``DestroyAllSpecialSummoned`` primitive (both sides, face-up). Cards:

  * Fossil Dyna Pachycephalo — Flip: destroy all SS monsters + a continuous "neither
    player can Special Summon" lock (reusing SpecialSummonLock).
  * Jowgen the Spiritualist — Ignition (discard 1) destroy all SS + the same lock.
  * Special Hurricane — Normal Spell: discard 1, destroy all SS monsters.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import DestroyAllSpecialSummoned
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, ActivateSpell
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(turn_player=0):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, turn_player, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _ss(s, name, player, idx=None):
    """Special Summon a fresh instance from limbo via the chokepoint."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    ok = s.special_summon(inst.iid, player, Position.FACE_UP_ATTACK, index=idx)
    assert ok
    return inst


# --------------------------------------------------------------------------- #
#  The flag
# --------------------------------------------------------------------------- #
def test_normal_summon_is_not_flagged():
    s = _fresh()
    skull = s.create_instance(reg.get("Summoned Skull"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(skull.iid)
    s.place_monster(skull.iid, 0, 0, Position.FACE_UP_ATTACK)  # the Normal Summon path
    assert not s.inst(skull.iid).was_special_summoned


def test_special_summon_is_flagged():
    s = _fresh()
    revived = _ss(s, "Summoned Skull", 0)
    assert s.inst(revived.iid).was_special_summoned


def test_token_is_flagged():
    # Scapegoat makes 4 Sheep Tokens — all Special Summoned.
    s = _fresh()
    goat = s.create_instance(reg.get("Scapegoat"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(goat.iid)
    idx = next(i for i, z in enumerate(s.players[0].spell_trap_zones) if z is None)
    s.place_spell_trap(goat.iid, 0, idx, Position.FACE_DOWN)
    goat.set_on_turn = s.turn_count - 1
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(goat.iid), 0)
    tokens = [i for i in s.players[0].monster_zones if i is not None]
    assert tokens and all(s.inst(i).was_special_summoned for i in tokens)


def test_flag_resets_when_the_monster_leaves_and_is_normal_summoned():
    s = _fresh()
    mon = _ss(s, "Summoned Skull", 0)
    assert s.inst(mon.iid).was_special_summoned
    s.send_to_graveyard(mon.iid)
    s.place_monster(mon.iid, 0, 0, Position.FACE_UP_ATTACK)  # later Normal Summoned
    assert not s.inst(mon.iid).was_special_summoned


# --------------------------------------------------------------------------- #
#  The primitive
# --------------------------------------------------------------------------- #
def test_destroy_all_special_summoned_spares_normal_monsters():
    s = _fresh()
    normal = _spawn(s, "Celtic Guardian", 0, 0)  # spawn_on_field -> not flagged
    summoned = _ss(s, "Summoned Skull", 1)
    from ygo.moves import resolve_effect
    from ygo.effects import Effect

    resolve_effect(s, Effect(resolve=(DestroyAllSpecialSummoned(),)), normal.iid, (), None)
    assert s.inst(normal.iid).zone is Zone.MONSTER  # Normal-summoned -> spared
    assert s.inst(summoned.iid).zone is Zone.GRAVEYARD  # SS -> destroyed


# --------------------------------------------------------------------------- #
#  Fossil Dyna Pachycephalo
# --------------------------------------------------------------------------- #
def test_fossil_dyna_flip_destroys_special_summoned():
    s = _fresh()
    dyna = _spawn(s, "Fossil Dyna Pachycephalo", 0, 0, Position.FACE_DOWN_DEFENSE)
    ss_mon = _ss(s, "Cyber Dragon", 1)
    normal = _spawn(s, "Celtic Guardian", 1, 1)
    Engine(s, [Agent(), Agent()])._trigger_flip_effect(dyna.iid)
    assert s.inst(ss_mon.iid).zone is Zone.GRAVEYARD
    assert s.inst(normal.iid).zone is Zone.MONSTER


def test_fossil_dyna_locks_special_summons():
    s = _fresh()
    _spawn(s, "Fossil Dyna Pachycephalo", 0, 0)
    dark = reg.get("Summoned Skull")
    assert s.special_summon_locked(0, dark)
    assert s.special_summon_locked(1, dark)


# --------------------------------------------------------------------------- #
#  Jowgen the Spiritualist
# --------------------------------------------------------------------------- #
def test_jowgen_locks_special_summons():
    s = _fresh()
    _spawn(s, "Jowgen the Spiritualist", 0, 0)
    assert s.special_summon_locked(0, reg.get("Cyber Dragon"))
    assert s.special_summon_locked(1, reg.get("Cyber Dragon"))


def test_jowgen_discards_to_destroy_special_summoned():
    s = _fresh()
    ss_mon = _ss(s, "Cyber Dragon", 1)  # Special Summoned before Jowgen's lock is up
    jowgen = _spawn(s, "Jowgen the Spiritualist", 0, 0)
    fodder = s.create_instance(reg.get("Celtic Guardian"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(fodder.iid)
    Engine(s, [Agent(), Agent()])._activate_monster_effect(
        ActivateMonsterEffect(jowgen.iid, targets=()), 0
    )
    assert s.inst(ss_mon.iid).zone is Zone.GRAVEYARD
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the discard was paid


# --------------------------------------------------------------------------- #
#  Special Hurricane
# --------------------------------------------------------------------------- #
def test_special_hurricane_discards_to_destroy_special_summoned():
    s = _fresh()
    hurricane = s.create_instance(reg.get("Special Hurricane"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(hurricane.iid)
    fodder = s.create_instance(reg.get("Mystical Elf"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(fodder.iid)
    ss_mon = _ss(s, "Cyber Dragon", 1)
    normal = _spawn(s, "Celtic Guardian", 1, 1)
    idx = next(i for i, z in enumerate(s.players[0].spell_trap_zones) if z is None)
    s.place_spell_trap(hurricane.iid, 0, idx, Position.FACE_DOWN)
    hurricane.set_on_turn = s.turn_count - 1
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(hurricane.iid), 0)
    assert s.inst(ss_mon.iid).zone is Zone.GRAVEYARD
    assert s.inst(normal.iid).zone is Zone.MONSTER
