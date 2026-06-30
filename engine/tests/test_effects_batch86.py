"""Effects Batch 86: Nutrient Z (deck-impact #19) — a PRE-damage replacement.

The damage-step window now previews the incoming battle damage (moves.battle_damage_preview,
kept in lockstep with _resolve_attack), so a Set Trap can react to the amount before it
lands. Nutrient Z: "During damage calculation, when you are about to take 2000 or more
battle damage: Gain 4000 LP first." It is offered to whichever player is about to take the
damage (attacker OR defender — Trigger.to_victim) when the previewed amount is 2000+
(Trigger.min_battle_damage); the 4000 gain happens before the (unchanged) battle damage
applies, and itself feeds the Batch 84 life-gain window (Fire Princess).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, apply, battle_damage_preview, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _battle_state(tp=0):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _set_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1  # set on an earlier turn -> activatable now
    return inst


class _Activator(Agent):
    def respond(self, state, options, event):
        return options[0] if options else None


# ------------------------------------------------ the preview agrees with real combat


def test_preview_matches_actual_battle_damage():
    def _check(build, atk_name, atk_pos, tgt):
        s = _battle_state(tp=0)
        a = _spawn(s, atk_name, 0, 0, atk_pos)
        t = build(s)
        prev = battle_damage_preview(s, a.iid, t)
        apply(s, DeclareAttack(a.iid, t))
        assert s.battle_damage_taken == prev, (atk_name, prev, s.battle_damage_taken)

    # direct attack -> defender takes ATK
    _check(lambda s: None, "Summoned Skull", Position.FACE_UP_ATTACK, None)
    # ATK > defender ATK -> defender takes the difference
    s = _battle_state(tp=0)
    a = _spawn(s, "Summoned Skull", 0, 0)  # 2500
    d = _spawn(s, "Celtic Guardian", 1, 0)  # 1400 ATK
    prev = battle_damage_preview(s, a.iid, d.iid)
    apply(s, DeclareAttack(a.iid, d.iid))
    assert s.battle_damage_taken == prev == (1, 1100)
    # attacker's monster is weaker -> attacker takes the difference
    s = _battle_state(tp=0)
    a = _spawn(s, "Celtic Guardian", 0, 0)  # 1400
    d = _spawn(s, "Summoned Skull", 1, 0)  # 2500
    prev = battle_damage_preview(s, a.iid, d.iid)
    apply(s, DeclareAttack(a.iid, d.iid))
    assert s.battle_damage_taken == prev == (0, 1100)
    # clean break on a Defense-Position wall -> no battle damage (preview None)
    s = _battle_state(tp=0)
    a = _spawn(s, "Summoned Skull", 0, 0)  # 2500
    w = _spawn(s, "Mystical Elf", 1, 0, Position.FACE_UP_DEFENSE)  # DEF 2000
    assert battle_damage_preview(s, a.iid, w.iid) is None
    apply(s, DeclareAttack(a.iid, w.iid))
    assert s.battle_damage_taken is None


# ----------------------------------------------------------------- Nutrient Z behaviour


def test_nutrient_z_gains_4000_before_a_big_direct_hit():
    s = _battle_state(tp=0)
    atk = _spawn(s, "Summoned Skull", 0, 0)  # 2500 direct
    nz = _set_trap(s, "Nutrient Z", 1)
    before = s.players[1].life_points
    Engine(s, [Agent(), _Activator()])._declare_attack(DeclareAttack(atk.iid, None), 0)
    assert s.players[1].life_points == before + 4000 - 2500  # gained 4000 first, then took 2500
    assert s.inst(nz.iid).zone is Zone.GRAVEYARD  # the Normal Trap was spent


def test_nutrient_z_not_offered_below_2000():
    s = _battle_state(tp=0)
    atk = _spawn(s, "Celtic Guardian", 0, 0)  # 1400 direct -> under the threshold
    nz = _set_trap(s, "Nutrient Z", 1)
    opts = response_options(
        s, 1, {"kind": "damage_step", "victim": 1, "incoming_damage": 1400}, 1
    )
    assert not any(a.iid == nz.iid for a in opts)
    before = s.players[1].life_points
    Engine(s, [Agent(), _Activator()])._declare_attack(DeclareAttack(atk.iid, None), 0)
    assert s.players[1].life_points == before - 1400  # full damage, NZ never fired
    assert s.inst(nz.iid).zone is Zone.SPELL_TRAP  # still set


def test_nutrient_z_protects_the_attacker_when_its_monster_loses():
    s = _battle_state(tp=0)
    weak = _spawn(s, "Kuriboh", 0, 0)  # 300 ATK attacker
    strong = _spawn(s, "Blue-Eyes White Dragon", 1, 0)  # 3000 ATK
    nz = _set_trap(s, "Nutrient Z", 0)  # the ATTACKER holds it
    before = s.players[0].life_points
    Engine(s, [_Activator(), Agent()])._declare_attack(DeclareAttack(weak.iid, strong.iid), 0)
    assert s.players[0].life_points == before + 4000 - 2700  # 3000-300 = 2700 incoming
    assert s.inst(nz.iid).zone is Zone.GRAVEYARD


def test_nutrient_z_gain_feeds_fire_princess():
    # The 4000 LP gain is a real gain -> the defender's Fire Princess burns the attacker 500.
    s = _battle_state(tp=0)
    atk = _spawn(s, "Summoned Skull", 0, 0)  # 2500 direct
    _spawn(s, "Fire Princess", 1, 1)  # defender's Fire Princess
    _set_trap(s, "Nutrient Z", 1)
    lp0 = s.players[0].life_points
    Engine(s, [Agent(), _Activator()])._declare_attack(DeclareAttack(atk.iid, None), 0)
    assert s.players[0].life_points == lp0 - 500  # Fire Princess fired off the Nutrient Z gain
