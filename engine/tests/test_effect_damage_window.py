"""Effect-damage window (ygopro's TIMING_DAMAGE): "when you take damage" now fires on
EFFECT damage (burn), not just battle damage.

Confirmed via the ygopro reference tool: Numinous Healer and Attack and Receive read "when
you take damage to your Life Points" (any damage), while Damage Condenser is "when you take
battle damage" (battle only). InflictDamage now records effect damage to
``GameState.effect_damage_pending`` (excluding LP COSTS flagged ``is_cost=True`` — Toon
World, pay-to-negate), and the engine drains it after a chain resolves
(``_fire_effect_damage_window``) to offer the victim a ``Trigger(kind="damage_taken")`` window.
Damage Condenser carries ``battle_only=True`` so it is skipped for effect damage.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.effects import OPPONENT, SELF, EffectContext, InflictDamage
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _set_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1  # set earlier -> activatable now
    return inst


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


class _Activator(Agent):
    def respond(self, state, options, event):
        return options[0] if options else None


def _drive_effect_window(s, victim, amount):
    s.effect_damage_pending = [(victim, amount)]
    agents = [Agent(), Agent()]
    agents[victim] = _Activator()
    Engine(s, agents)._fire_effect_damage_window()


# ------------------------------------------------- InflictDamage records (excludes costs)


def test_inflict_damage_records_effect_damage_but_not_costs():
    s = _fresh()
    src = _spawn(s, "Summoned Skull", 1, 0)
    ctx = EffectContext(state=s, controller=1, source_iid=src.iid)
    InflictDamage(OPPONENT, 800).execute(ctx)  # real burn -> player 0
    assert s.effect_damage_pending == [(0, 800)]
    s.effect_damage_pending = []
    InflictDamage(SELF, 1000, is_cost=True).execute(ctx)  # an LP cost (Toon World-style)
    assert s.effect_damage_pending == []  # a cost is not "damage" -> no window


# ----------------------------------------------------- window fires on effect damage


def test_numinous_healer_fires_on_effect_damage():
    s = _fresh()
    _set_trap(s, "Numinous Healer", player=0)
    before = s.players[0].life_points
    _drive_effect_window(s, victim=0, amount=1000)
    assert s.players[0].life_points == before + 1000  # gained 1000 (no GY copies)


def test_attack_and_receive_fires_on_effect_damage():
    s = _fresh()
    _set_trap(s, "Attack and Receive", player=0)
    before_opp = s.players[1].life_points
    _drive_effect_window(s, victim=0, amount=500)
    assert s.players[1].life_points == before_opp - 700  # burns the opponent 700


def test_numinous_healer_heals_on_a_real_burn_chain():
    # End-to-end through _run_chain: player 1 burns player 0 with Hinotama (500); player 0's
    # Numinous Healer triggers off the effect damage in the post-chain window.
    s = _fresh(tp=1)
    hinotama = _in_hand(s, "Hinotama", 1)
    _set_trap(s, "Numinous Healer", player=0)
    eng = Engine(s, [_Activator(), _Activator()])
    eng._activate_as_chain(ActivateSpell(hinotama.iid, targets=()), 1)
    assert s.players[0].life_points == 8000 - 500 + 1000  # burned 500, then healed 1000


# --------------------------------------------- Damage Condenser is battle-only (skipped)


def test_damage_condenser_skipped_on_effect_damage_but_offered_on_battle():
    s = _fresh()
    cond = _set_trap(s, "Damage Condenser", player=0)
    _in_hand(s, "Mystical Elf", 0)  # a card to discard (its activation cost)
    _in_deck(s, "Celtic Guardian", 0)  # a monster it could Special Summon
    effect_event = {"kind": "damage_taken", "player": 0, "amount": 2000, "damage_kind": "effect"}
    battle_event = {"kind": "damage_taken", "player": 0, "amount": 2000, "damage_kind": "battle"}
    assert not any(a.iid == cond.iid for a in response_options(s, 0, effect_event, 2))
    assert any(a.iid == cond.iid for a in response_options(s, 0, battle_event, 2))
