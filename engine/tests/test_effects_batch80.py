"""Effects Batch 80: "when you take battle damage" reactive Traps.

A new post-combat response window — ``engine._fire_damage_taken_window`` — lets the player
who just took battle damage activate a Set Trap that reacts to it. ``moves._resolve_attack``
records ``GameState.battle_damage_taken = (victim, amount)`` at every battle-damage site
(defender hit, attacker loses, Defense bounce; at most one player per attack), and the
engine offers that victim a ``Trigger(kind="battle_damage_taken", by=SELF)`` window after
combat — unlike the generic ``_response_window``, which only ever offers the *opponent* of
the acting player (the victim can be the attacker, when its monster lost the battle).

Cards: Numinous Healer (gain 1000 + 500/GY-copy), Attack and Receive (burn 700), Damage
Condenser (discard 1 -> Special Summon a Deck monster with ATK <= the damage taken).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, apply, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()

ATTACKER, DEFENDER = 0, 1


def _fresh(tp=ATTACKER):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _set_trap(s, name, player=DEFENDER):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1  # set on an earlier turn -> activatable now
    return inst


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _in_deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _dmg_event(victim, amount):
    return {"kind": "damage_taken", "player": victim, "amount": amount, "damage_kind": "battle"}


class _Activator(Agent):
    """Activates the first offered response option, else passes (single-trap tests)."""

    def respond(self, state, options, event):
        return options[0] if options else None


def _drive_window(s, victim, amount):
    """Record battle damage and run the REAL damage-taken window — the victim activates
    its trap (event threaded, activation cost paid), the dealer passes."""
    s.battle_damage_taken = (victim, amount)
    agents = [Agent(), Agent()]
    agents[victim] = _Activator()
    Engine(s, agents)._fire_damage_taken_window()


# ---------------------------------------------------- battle_damage_taken record (moves)


def test_battle_damage_taken_recorded_on_direct_attack():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500, opponent empty -> direct attack
    apply(s, DeclareAttack(atk.iid, None))
    assert s.battle_damage_taken == (DEFENDER, 2500)


def test_battle_damage_taken_recorded_when_attacker_loses():
    s = _fresh()
    weak = _spawn(s, "Celtic Guardian", ATTACKER, 0)  # 1400
    strong = _spawn(s, "Summoned Skull", DEFENDER, 0)  # 2500 ATK
    apply(s, DeclareAttack(weak.iid, strong.iid))
    assert s.battle_damage_taken == (ATTACKER, 1100)  # the attacker takes 2500-1400


def test_no_battle_damage_taken_on_clean_defense_break():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500
    wall = _spawn(s, "Mystical Elf", DEFENDER, 0, pos=Position.FACE_UP_DEFENSE)  # DEF 2000
    apply(s, DeclareAttack(atk.iid, wall.iid))
    assert s.battle_damage_taken is None  # clean break, no piercing -> nobody takes damage


# ------------------------------------------------------------------- Numinous Healer


def test_numinous_healer_gains_1000_plus_500_per_gy_copy():
    s = _fresh()
    _set_trap(s, "Numinous Healer")
    _in_gy(s, "Numinous Healer", DEFENDER)  # one earlier copy already in the GY
    s.players[DEFENDER].life_points = 5000
    _drive_window(s, DEFENDER, 1500)
    assert s.players[DEFENDER].life_points == 5000 + 1000 + 500


def test_numinous_healer_base_gain_with_empty_gy():
    s = _fresh()
    _set_trap(s, "Numinous Healer")
    s.players[DEFENDER].life_points = 4000
    _drive_window(s, DEFENDER, 800)
    assert s.players[DEFENDER].life_points == 5000  # just the base 1000


# ----------------------------------------------------------------- Attack and Receive


def test_attack_and_receive_burns_the_opponent_700():
    s = _fresh()
    _set_trap(s, "Attack and Receive")  # DEFENDER took the damage and activates it
    s.players[ATTACKER].life_points = 8000
    _drive_window(s, DEFENDER, 1200)
    assert s.players[ATTACKER].life_points == 7300  # 700 to the activator's opponent


# ------------------------------------------------------------------- Damage Condenser


def test_damage_condenser_summons_a_capped_monster_for_a_discard():
    s = _fresh()
    _set_trap(s, "Damage Condenser")
    fodder = _in_hand(s, "Mystical Elf", DEFENDER)  # the discard cost
    small = _in_deck(s, "Giant Rat", DEFENDER)  # ATK 1400 <= 1500 -> eligible
    big = _in_deck(s, "Summoned Skull", DEFENDER)  # ATK 2500 > 1500 -> not eligible
    _drive_window(s, DEFENDER, 1500)
    assert s.inst(small.iid).zone is Zone.MONSTER
    assert s.inst(small.iid).position is Position.FACE_UP_ATTACK
    assert s.inst(big.iid).zone is Zone.DECK
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # discarded as the activation cost


def test_damage_condenser_not_offered_without_discard_fodder():
    s = _fresh()
    trap = _set_trap(s, "Damage Condenser")
    _in_deck(s, "Giant Rat", DEFENDER)  # a valid SS target exists...
    # ...but the hand is empty, so the discard cost cannot be paid.
    opts = response_options(s, DEFENDER, _dmg_event(DEFENDER, 1500), 2)
    assert not any(isinstance(a, ActivateSpell) and a.iid == trap.iid for a in opts)


# ------------------------------------------------------ end-to-end window (full attack)


def test_window_fires_for_the_victim_through_a_full_attack():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500 direct attack
    trap = _set_trap(s, "Numinous Healer", DEFENDER)
    s.players[DEFENDER].life_points = 8000
    Engine(s, [Agent(), _Activator()])._declare_attack(DeclareAttack(atk.iid, None), ATTACKER)
    assert s.players[DEFENDER].life_points == 8000 - 2500 + 1000  # took 2500, healed 1000
    assert s.inst(trap.iid).zone is Zone.GRAVEYARD  # the spent Normal Trap left the field


def test_window_not_offered_to_the_dealer():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # ATTACKER deals the damage
    trap = _set_trap(s, "Numinous Healer", ATTACKER)  # the dealer holds the trap
    lp_before = s.players[ATTACKER].life_points
    Engine(s, [_Activator(), Agent()])._declare_attack(DeclareAttack(atk.iid, None), ATTACKER)
    assert s.inst(trap.iid).zone is Zone.SPELL_TRAP  # never offered — the dealer took no damage
    assert s.players[ATTACKER].life_points == lp_before
