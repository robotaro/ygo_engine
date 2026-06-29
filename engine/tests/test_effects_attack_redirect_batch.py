"""Effects Batch 48: attack redirect + a cost-bearing attack Trap.

New state.attack_redirect (set by the RedirectAttackToTarget primitive during the
attack-declaration response window, read by engine._declare_attack to swap the attack
target) + a new "own_monsters" target pool. Cards: Call of the Earthbound (redirect to
a monster you choose), Jam Defender (redirect to your Revival Jam), Chaos Burst (Tribute
1 -> destroy the attacker + 1000 damage).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, apply, response_options
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


def _fire(s, trap, event, controller=DEFENDER):
    opts = response_options(s, controller, event, 2)
    act = next((a for a in opts if a.iid == trap.iid), None)
    assert act is not None, "trap not offered"
    Engine(s, [Agent(), Agent()])._activate_as_chain(act, controller)
    return act


# --------------------------------------------------------------------------- #
#  Redirect mechanism
# --------------------------------------------------------------------------- #
def test_redirect_changes_the_resolved_target():
    # Direct attack redirected onto a chosen monster: that monster takes the hit.
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500 ATK
    decoy = _spawn(s, "Celtic Guardian", DEFENDER, 0, Position.FACE_UP_ATTACK)  # 1400
    trap = _set_trap(s, "Call of the Earthbound")
    act = _fire(s, trap, _event(atk.iid, None))
    assert act.targets == (decoy.iid,)  # the chosen own monster
    assert s.attack_redirect == decoy.iid


class _ActivateTrap(Agent):
    """Activates the named trap the first time it's offered in a response window."""

    def __init__(self, name):
        super().__init__()
        self.name = name

    def respond(self, state, options, event):
        for opt in options:
            if opt.iid in state.cards and state.inst(opt.iid).card.name == self.name:
                return opt
        return None


def test_call_of_the_earthbound_full_attack_resolves_on_new_target():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500
    decoy = _spawn(s, "Celtic Guardian", DEFENDER, 0)  # 1400 -> dies
    _set_trap(s, "Call of the Earthbound")
    # The DEFENDER's agent activates the redirect inside the real attack-response window.
    eng = Engine(s, [Agent(), _ActivateTrap("Call of the Earthbound")])
    eng._declare_attack(DeclareAttack(atk.iid, None), ATTACKER)
    assert s.inst(decoy.iid).zone is Zone.GRAVEYARD  # the redirected monster took the hit
    # took only the 1100 battle difference (2500-1400), not the full 2500 direct hit
    assert s.players[DEFENDER].life_points == 8000 - 1100


def test_jam_defender_redirects_to_revival_jam():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    _spawn(s, "Celtic Guardian", DEFENDER, 0)  # some other monster
    jam = _spawn(s, "Revival Jam", DEFENDER, 1, Position.FACE_UP_DEFENSE)
    trap = _set_trap(s, "Jam Defender")
    act = _fire(s, trap, _event(atk.iid, None))
    assert act.targets == (jam.iid,)
    assert s.attack_redirect == jam.iid


# --------------------------------------------------------------------------- #
#  Chaos Burst
# --------------------------------------------------------------------------- #
def test_chaos_burst_tributes_to_destroy_attacker_and_burn():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    fodder = _spawn(s, "Celtic Guardian", DEFENDER, 0)  # the Tribute
    trap = _set_trap(s, "Chaos Burst")
    _fire(s, trap, _event(atk.iid))
    assert s.inst(atk.iid).zone is Zone.GRAVEYARD  # attacker destroyed
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the Tribute was paid
    assert s.players[ATTACKER].life_points == 7000  # 1000 burn to the opponent


def test_chaos_burst_can_tribute_a_token():
    # Regression: a Tributed Token is removed from the game (deleted from state.cards), so
    # pay_costs must snapshot the fodder's name before paying, not look it up afterwards.
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    import dataclasses

    token = s.spawn_on_field(reg.get("Summoned Skull"), DEFENDER, 0, Position.FACE_UP_ATTACK)
    token.card = dataclasses.replace(token.card, is_token=True)
    trap = _set_trap(s, "Chaos Burst")
    _fire(s, trap, _event(atk.iid))
    assert s.inst(atk.iid).zone is Zone.GRAVEYARD  # attacker destroyed
    assert token.iid not in s.cards  # the Token was Tributed and removed from the game


def test_chaos_burst_not_offered_without_a_tribute():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    trap = _set_trap(s, "Chaos Burst")  # defender controls no monster to Tribute
    opts = response_options(s, DEFENDER, _event(atk.iid), 2)
    assert not any(a.iid == trap.iid for a in opts)
