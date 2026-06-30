"""Effects Batch 85: battle-damage prevention (deck-impact #18 -- Kuriboh).

All battle damage to a player now flows through one chokepoint (_resolve_attack's
_take_battle_damage), which consults GameState.takes_no_battle_damage. Two cards drive it:

- Kuriboh: a HAND quick effect offered by the engine's new damage-step window when the
  opponent's monster attacks. Discarding it (the cost) zeroes the battle damage the
  activating player takes from THAT battle only -- via the per-battle GameState.
  battle_damage_prevented set, reset at each attack declaration. Offered only to the
  attacked player (not the attacker).
- Winged Kuriboh: reuses Batch 83's unified "destroyed" GY trigger (battle OR effect); on
  death it grants its controller the turn-scoped no-battle-damage immunity
  (PlayerState.no_battle_damage_until_turn), which lapses when the turn advances.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _battle_state(tp=0):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


class _Activator(Agent):
    """Activates the first offered response option, else passes."""

    def respond(self, state, options, event):
        return options[0] if options else None


# ================================ Kuriboh (per-battle, from hand) ================================


def test_kuriboh_prevents_direct_attack_damage():
    s = _battle_state(tp=0)
    atk = _spawn(s, "Summoned Skull", 0, 0)  # 2500, direct attack
    kuriboh = _in_hand(s, "Kuriboh", 1)  # the attacked player holds it
    before = s.players[1].life_points
    Engine(s, [Agent(), _Activator()])._declare_attack(DeclareAttack(atk.iid, None), 0)
    assert s.players[1].life_points == before  # zero battle damage
    assert s.inst(kuriboh.iid).zone is Zone.GRAVEYARD  # discarded as the cost
    assert s.battle_damage_dealt is None  # so the attacker "inflicted" nothing (no Don Zaloog)


def test_kuriboh_prevents_damage_when_its_monster_loses():
    s = _battle_state(tp=0)
    atk = _spawn(s, "Summoned Skull", 0, 0)  # 2500
    wall = _spawn(s, "Celtic Guardian", 1, 0)  # 1400 ATK -> would deal 1100
    _in_hand(s, "Kuriboh", 1)
    before = s.players[1].life_points
    Engine(s, [Agent(), _Activator()])._declare_attack(DeclareAttack(atk.iid, wall.iid), 0)
    assert s.players[1].life_points == before  # the 1100 is prevented
    assert s.inst(wall.iid).zone is Zone.GRAVEYARD  # the monster is still destroyed


def test_kuriboh_is_not_offered_to_the_attacker():
    # Kuriboh = "if your OPPONENT's monster attacks" -> only the attacked player may use it.
    s = _battle_state(tp=0)
    weak = _spawn(s, "Celtic Guardian", 0, 0)  # 1400 attacker
    strong = _spawn(s, "Summoned Skull", 1, 0)  # 2500 defender
    kuriboh = _in_hand(s, "Kuriboh", 0)  # the ATTACKER holds Kuriboh
    before = s.players[0].life_points
    Engine(s, [_Activator(), Agent()])._declare_attack(DeclareAttack(weak.iid, strong.iid), 0)
    assert s.players[0].life_points == before - 1100  # attacker takes 2500-1400, no Kuriboh
    assert s.inst(kuriboh.iid).zone is Zone.HAND  # never offered, still in hand


def test_kuriboh_only_protects_that_one_battle():
    s = _battle_state(tp=0)
    a1 = _spawn(s, "Summoned Skull", 0, 0)  # 2500
    a2 = _spawn(s, "Summoned Skull", 0, 1)  # 2500
    _in_hand(s, "Kuriboh", 1)  # exactly one Kuriboh
    eng = Engine(s, [Agent(), _Activator()])
    eng._declare_attack(DeclareAttack(a1.iid, None), 0)  # prevented
    eng._declare_attack(DeclareAttack(a2.iid, None), 0)  # Kuriboh spent -> full damage
    assert s.players[1].life_points == 8000 - 2500  # only the second attack landed


def test_no_kuriboh_means_normal_damage():
    s = _battle_state(tp=0)
    atk = _spawn(s, "Summoned Skull", 0, 0)
    # player 1 has no Kuriboh; an eager activator must find nothing to do.
    before = s.players[1].life_points
    Engine(s, [Agent(), _Activator()])._declare_attack(DeclareAttack(atk.iid, None), 0)
    assert s.players[1].life_points == before - 2500


# ============================ Winged Kuriboh (turn-scoped, on death) ============================


def test_winged_kuriboh_grants_turn_immunity_after_a_battle_death():
    s = _battle_state(tp=0)
    beater = _spawn(s, "Summoned Skull", 0, 0)  # 2500
    wk = _spawn(s, "Winged Kuriboh", 1, 0)  # 300 ATK, in Attack Position
    second = _spawn(s, "Summoned Skull", 0, 1)  # 2500 for a follow-up swing
    eng = Engine(s, [Agent(), Agent()])
    before = s.players[1].life_points
    eng._declare_attack(DeclareAttack(beater.iid, wk.iid), 0)
    assert s.inst(wk.iid).zone is Zone.GRAVEYARD
    assert before - s.players[1].life_points == 2200  # that battle's damage still lands (2500-300)
    assert s.players[1].no_battle_damage_until_turn == s.turn_count  # immunity now set
    lp_mid = s.players[1].life_points
    eng._declare_attack(DeclareAttack(second.iid, None), 0)
    assert s.players[1].life_points == lp_mid  # no further battle damage this turn


def test_winged_kuriboh_immunity_fires_on_effect_destruction_too():
    s = _battle_state(tp=1)
    wk = _spawn(s, "Winged Kuriboh", 0, 0)
    s.send_to_graveyard(wk.iid, by_effect=True)  # destroyed by a card effect
    Engine(s, [Agent(), Agent()])._check_field_to_gy_triggers()
    assert s.players[0].no_battle_damage_until_turn == s.turn_count


def test_winged_kuriboh_immunity_lapses_next_turn():
    s = _battle_state(tp=0)
    s.players[1].no_battle_damage_until_turn = s.turn_count  # granted this turn
    atk = _spawn(s, "Summoned Skull", 0, 0)
    s.turn_count += 2  # the turn advances; the stamp is now stale
    before = s.players[1].life_points
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(atk.iid, None), 0)
    assert s.players[1].life_points == before - 2500  # immunity has lapsed
