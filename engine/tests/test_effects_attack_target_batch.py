"""Effects Batch 50: "selected as an attack target" gate + board-state-gated attack Traps.

A new ``Trigger.target_self_control`` (+ name/normal/level narrows) lets an
``attack_declared`` Trap key off the DEFENDER's monster being attacked rather than the
attacker — "when a face-up monster you control is selected as an attack target". Mirage
Tube (burn 1000), Froggy Forcefield (your Frog targeted -> wipe the attacker's ATK
monsters) and Justi-Break (your Normal monster targeted -> destroy all but face-up ATK
Normal monsters, via DestroyAllMonsters.spare_face_up_attack_normal) ride it. Supercharge
and Amazoness Archers gate on board state (condition) and Amazoness uses the new
ModifyAllStatsTemporary primitive.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, resolve_effect, response_options
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


def _offered(s, trap_iid, event):
    return any(a.iid == trap_iid for a in response_options(s, DEFENDER, event, 2))


class _ActivateTrap(Agent):
    def __init__(self, name):
        super().__init__()
        self.name = name

    def respond(self, state, options, event):
        for opt in options:
            if opt.iid in state.cards and state.inst(opt.iid).card.name == self.name:
                return opt
        return None


# --------------------------------------------------------------------------- #
#  Mirage Tube — Quick-Play, "cannot be activated from hand"
# --------------------------------------------------------------------------- #
def test_mirage_tube_burns_when_your_monster_targeted():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    prey = _spawn(s, "Mystical Elf", DEFENDER, 0)
    _set_trap(s, "Mirage Tube")
    eng = Engine(s, [Agent(), _ActivateTrap("Mirage Tube")])
    eng._declare_attack(DeclareAttack(atk.iid, prey.iid), ATTACKER)
    # Burn 1000 to the attacking player resolves on the chain before combat.
    assert s.players[ATTACKER].life_points == 8000 - 1000


def test_mirage_tube_not_offered_on_direct_attack():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    trap = _set_trap(s, "Mirage Tube")  # no defender monster -> a direct attack
    assert not _offered(s, trap.iid, _event(atk.iid, None))


def test_mirage_tube_cannot_be_activated_from_hand():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    prey = _spawn(s, "Mystical Elf", DEFENDER, 0)
    inst = s.create_instance(reg.get("Mirage Tube"), owner=DEFENDER, zone=Zone.HAND)
    s.players[DEFENDER].hand.append(inst.iid)  # in hand, NOT set
    assert not _offered(s, inst.iid, _event(atk.iid, prey.iid))


# --------------------------------------------------------------------------- #
#  Froggy Forcefield
# --------------------------------------------------------------------------- #
def test_froggy_forcefield_wipes_attackers_when_frog_targeted():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # 2500, attack position
    other = _spawn(s, "Gemini Elf", ATTACKER, 1)  # a second attacker-side ATK monster
    frog = _spawn(s, "Des Frog", DEFENDER, 0)  # a "Frog" you control
    _set_trap(s, "Froggy Forcefield")
    eng = Engine(s, [Agent(), _ActivateTrap("Froggy Forcefield")])
    eng._declare_attack(DeclareAttack(atk.iid, frog.iid), ATTACKER)
    assert s.inst(atk.iid).zone is Zone.GRAVEYARD  # both attacker-side ATK monsters gone
    assert s.inst(other.iid).zone is Zone.GRAVEYARD
    assert s.inst(frog.iid).zone is Zone.MONSTER  # the Frog survives; the attack fizzled


def test_froggy_forcefield_not_offered_for_nonfrog_target():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    prey = _spawn(s, "Celtic Guardian", DEFENDER, 0)  # not a "Frog"
    trap = _set_trap(s, "Froggy Forcefield")
    assert not _offered(s, trap.iid, _event(atk.iid, prey.iid))


# --------------------------------------------------------------------------- #
#  Justi-Break
# --------------------------------------------------------------------------- #
def test_justibreak_spares_only_faceup_attack_normals():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # vanilla, ATK -> spared
    eff_atk = _spawn(s, "Man-Eater Bug", ATTACKER, 1)  # effect monster -> destroyed
    normal = _spawn(s, "Celtic Guardian", DEFENDER, 0)  # vanilla ATK (the target) -> spared
    eff_def = _spawn(s, "Mystic Tomato", DEFENDER, 1)  # effect monster -> destroyed
    trap = _set_trap(s, "Justi-Break")
    event = _event(atk.iid, normal.iid)
    assert _offered(s, trap.iid, event)
    resolve_effect(s, EFFECTS["Justi-Break"][0], trap.iid, (), event)
    assert s.inst(atk.iid).zone is Zone.MONSTER
    assert s.inst(normal.iid).zone is Zone.MONSTER
    assert s.inst(eff_atk.iid).zone is Zone.GRAVEYARD
    assert s.inst(eff_def.iid).zone is Zone.GRAVEYARD


def test_justibreak_not_offered_against_effect_monster():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    prey = _spawn(s, "Mystic Tomato", DEFENDER, 0)  # an effect monster, not Normal
    trap = _set_trap(s, "Justi-Break")
    assert not _offered(s, trap.iid, _event(atk.iid, prey.iid))


# --------------------------------------------------------------------------- #
#  Supercharge
# --------------------------------------------------------------------------- #
def test_supercharge_offered_only_with_roid_machines_and_draws_two():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    roid = _spawn(s, "Cycroid", DEFENDER, 0)  # a Machine "roid"
    for nm in ("Celtic Guardian", "Gemini Elf"):
        di = s.create_instance(reg.get(nm), owner=DEFENDER, zone=Zone.DECK)
        s.players[DEFENDER].deck.append(di.iid)
    trap = _set_trap(s, "Supercharge")
    event = _event(atk.iid, roid.iid)
    assert _offered(s, trap.iid, event)
    before = len(s.players[DEFENDER].hand)
    resolve_effect(s, EFFECTS["Supercharge"][0], trap.iid, (), event)
    assert len(s.players[DEFENDER].hand) == before + 2


def test_supercharge_not_offered_with_a_nonroid_monster():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    roid = _spawn(s, "Cycroid", DEFENDER, 0)
    _spawn(s, "Celtic Guardian", DEFENDER, 1)  # a non-"roid" monster you also control
    trap = _set_trap(s, "Supercharge")
    assert not _offered(s, trap.iid, _event(atk.iid, roid.iid))


# --------------------------------------------------------------------------- #
#  Amazoness Archers
# --------------------------------------------------------------------------- #
def test_amazoness_archers_switches_and_weakens_opponent():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0, Position.FACE_UP_DEFENSE)  # 2500 -> ATK, -500
    _spawn(s, "Amazoness Swords Woman", DEFENDER, 0)  # the "Amazoness" gate
    trap = _set_trap(s, "Amazoness Archers")
    event = _event(atk.iid, None)
    assert _offered(s, trap.iid, event)
    resolve_effect(s, EFFECTS["Amazoness Archers"][0], trap.iid, (), event)
    assert s.inst(atk.iid).position is Position.FACE_UP_ATTACK
    assert s.effective_attack(atk.iid) == 2500 - 500


def test_amazoness_archers_not_offered_without_an_amazoness():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    _spawn(s, "Celtic Guardian", DEFENDER, 0)  # no Amazoness on your field
    trap = _set_trap(s, "Amazoness Archers")
    assert not _offered(s, trap.iid, _event(atk.iid, None))
