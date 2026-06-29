"""Effects Batch 51: forced attack target (Staunch Defender).

New state.forced_attack_target + ForceAttackTarget primitive: for the rest of the turn
the attacker may only declare attacks against the chosen monster (enforced in
moves._battle_phase_actions, cleared by engine._begin_turn). Staunch Defender pairs it
with RedirectAttackToTarget so the current attack is also pulled onto the chosen monster.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, _battle_phase_actions, resolve_effect, response_options
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
    return {"kind": "attack_declared", "player": ATTACKER, "attacker": attacker_iid, "target": target_iid}


STAUNCH = EFFECTS["Staunch Defender"][0]


def test_staunch_defender_is_offered_and_targets_your_monsters():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    shield = _spawn(s, "Mystical Elf", DEFENDER, 0)
    trap = _set_trap(s, "Staunch Defender")
    opts = response_options(s, DEFENDER, _event(atk.iid, shield.iid), 2)
    targets = {a.targets[0] for a in opts if a.iid == trap.iid}
    assert targets == {shield.iid}  # your one face-up monster is the only pick


def test_staunch_defender_redirects_and_locks():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    _spawn(s, "Gemini Elf", ATTACKER, 1)  # a second attacker the lock must also bind
    prey = _spawn(s, "Celtic Guardian", DEFENDER, 0)  # the originally-declared target
    shield = _spawn(s, "Mystical Elf", DEFENDER, 1)  # the monster we force attacks onto
    trap = _set_trap(s, "Staunch Defender")
    resolve_effect(s, STAUNCH, trap.iid, (shield.iid,), _event(atk.iid, prey.iid))
    assert s.attack_redirect == shield.iid  # the current attack is pulled onto the shield
    assert s.forced_attack_target == shield.iid
    # Every legal attack the attacker can now declare must target the shield (no direct).
    targets = [a.target for a in _battle_phase_actions(s, ATTACKER)]
    assert targets and all(t == shield.iid for t in targets)
    assert None not in targets


def test_staunch_lock_lifts_when_the_target_leaves():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    prey = _spawn(s, "Celtic Guardian", DEFENDER, 0)
    shield = _spawn(s, "Mystical Elf", DEFENDER, 1)
    s.forced_attack_target = shield.iid
    s.send_to_graveyard(shield.iid)  # the protected monster is gone
    targets = {a.target for a in _battle_phase_actions(s, ATTACKER)}
    assert prey.iid in targets  # the attacker may attack freely again
    _ = atk


def test_staunch_lock_clears_at_the_start_of_the_next_turn():
    s = _fresh()
    shield = _spawn(s, "Mystical Elf", DEFENDER, 0)
    s.forced_attack_target = shield.iid
    eng = Engine(s, [Agent(), Agent()])
    eng._begin_turn(DEFENDER)
    assert s.forced_attack_target is None
