"""Effects Batch 45: reactive "when an opponent's monster declares an attack" Traps.

The attack-declaration response window already exists (engine._declare_attack opens a
``_response_window`` with an ``attack_declared`` event). These Traps key off it as
speed-2 trigger effects. Tested by enumerating the window (moves.response_options) and
resolving the chosen activation.

Cards: Sakuretsu Armor (destroy the attacker), Negate Attack, Malevolent Catastrophe
(destroy all S/T), Widespread Ruin (opponent's highest-ATK attacker), Radiant Mirror
Force (3+ attackers -> destroy them all), Dark Mirror Force (banish attacker's Defense
Position monsters).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()

ATTACKER, DEFENDER = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ATTACKER, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _set_trap(s, name, player=DEFENDER):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _event(attacker_iid, target_iid=None):
    return {
        "kind": "attack_declared",
        "player": ATTACKER,
        "attacker": attacker_iid,
        "target": target_iid,
    }


def _fire(s, trap, event):
    """Enumerate the response window, find this trap's activation, resolve it."""
    opts = response_options(s, DEFENDER, event, 2)
    act = next((a for a in opts if isinstance(a, ActivateSpell) and a.iid == trap.iid), None)
    assert act is not None, "the trap was not offered in the response window"
    Engine(s, [Agent(), Agent()])._activate_as_chain(act, DEFENDER)
    return act


# --------------------------------------------------------------------------- #
#  Sakuretsu Armor
# --------------------------------------------------------------------------- #
def test_sakuretsu_armor_destroys_the_attacker():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    trap = _set_trap(s, "Sakuretsu Armor")
    act = _fire(s, trap, _event(atk.iid))
    assert act.targets == (atk.iid,)  # subject="attacker" targets the attacker
    assert s.inst(atk.iid).zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------- #
#  Negate Attack
# --------------------------------------------------------------------------- #
def test_negate_attack_negates_the_attack():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    trap = _set_trap(s, "Negate Attack")
    _fire(s, trap, _event(atk.iid))
    assert s.attack_negated
    assert s.inst(atk.iid).zone is Zone.MONSTER  # attacker survives, just stopped


# --------------------------------------------------------------------------- #
#  Malevolent Catastrophe
# --------------------------------------------------------------------------- #
def test_malevolent_catastrophe_destroys_all_spell_traps():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    victim_st = _set_trap(s, "Mirror Force", player=ATTACKER)  # a Set card to be destroyed
    trap = _set_trap(s, "Malevolent Catastrophe")
    _fire(s, trap, _event(atk.iid))
    assert s.inst(victim_st.iid).zone is Zone.GRAVEYARD
    assert s.inst(trap.iid).zone is Zone.GRAVEYARD  # Catastrophe destroys itself too


# --------------------------------------------------------------------------- #
#  Widespread Ruin
# --------------------------------------------------------------------------- #
def test_widespread_ruin_destroys_opponents_highest_atk():
    s = _fresh()
    big = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500 ATK
    small = _spawn(s, "Celtic Guardian", ATTACKER, 1)  # 1400 ATK
    mine = _spawn(s, "Gemini Elf", DEFENDER, 0)  # 1900 ATK — must NOT be touched
    trap = _set_trap(s, "Widespread Ruin")
    _fire(s, trap, _event(big.iid))
    assert s.inst(big.iid).zone is Zone.GRAVEYARD
    assert s.inst(small.iid).zone is Zone.MONSTER
    assert s.inst(mine.iid).zone is Zone.MONSTER  # side=opponent spares my board


# --------------------------------------------------------------------------- #
#  Radiant Mirror Force
# --------------------------------------------------------------------------- #
def test_radiant_mirror_force_needs_three_attackers():
    s = _fresh()
    a1 = _spawn(s, "Summoned Skull", ATTACKER, 0)
    _spawn(s, "Celtic Guardian", ATTACKER, 1)
    trap = _set_trap(s, "Radiant Mirror Force")
    # Only 2 Attack-Position monsters -> the condition fails, so it isn't offered.
    opts = response_options(s, DEFENDER, _event(a1.iid), 2)
    assert not any(a.iid == trap.iid for a in opts)


def test_radiant_mirror_force_destroys_all_attackers():
    s = _fresh()
    a1 = _spawn(s, "Summoned Skull", ATTACKER, 0)
    a2 = _spawn(s, "Celtic Guardian", ATTACKER, 1)
    a3 = _spawn(s, "Gemini Elf", ATTACKER, 2)
    trap = _set_trap(s, "Radiant Mirror Force")
    _fire(s, trap, _event(a1.iid))
    for iid in (a1.iid, a2.iid, a3.iid):
        assert s.inst(iid).zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------- #
#  Dark Mirror Force
# --------------------------------------------------------------------------- #
def test_dark_mirror_force_banishes_defense_attackers():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # the attacker (Attack Position)
    wall = _spawn(s, "Big Shield Gardna", ATTACKER, 1, Position.FACE_UP_DEFENSE)
    trap = _set_trap(s, "Dark Mirror Force")
    _fire(s, trap, _event(atk.iid))
    assert s.inst(wall.iid).zone is Zone.BANISHED
    assert s.inst(atk.iid).zone is Zone.MONSTER  # Attack-Position attacker is untouched
