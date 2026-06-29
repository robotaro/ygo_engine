"""Special Summon event unification.

Every Special Summon now flows through state.special_summon, which queues a summon
event; the engine drains that queue (in _check_field_to_gy_triggers) to open the
opponent's response window AND fire the monster's own "when Special Summoned" Trigger
— for effect-driven summons too, not just hand/Normal summons. This closes the gap
where Bottomless Trap Hole couldn't catch a revived/recruited monster and a recruited
monster's on-summon effect never fired.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, Pass
from ygo.state import GameState

reg = CardRegistry.load_csv()


class ActivateByName(Agent):
    """Passes on its own turn; in a response window, activates the named card if offered."""

    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _fresh(turn_player=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, turn_player, phase
    return s


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _set_card(s, name, player, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _set_spell(s, name, player, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


# --- chain-resolution path: Monster Reborn now opens a response window -------------
def test_bottomless_now_catches_a_monster_reborn_revival():
    s = _fresh()
    dead = _in_gy(s, "Summoned Skull", 0)  # 2500 ATK >= 1500
    reborn = _set_spell(s, "Monster Reborn", 0)
    bottomless = _set_card(s, "Bottomless Trap Hole", 1, 1)
    eng = Engine(s, [Agent(), ActivateByName("Bottomless Trap Hole")])
    eng._activate_as_chain(ActivateSpell(reborn.iid, targets=(dead.iid,)), 0)
    # Before the unification the revival got no window; now Bottomless banishes it.
    assert s.inst(dead.iid).zone is Zone.BANISHED
    assert s.inst(bottomless.iid).zone is Zone.GRAVEYARD


def test_on_summon_trigger_fires_for_a_reborn_monster():
    s = _fresh()
    curse = _in_gy(s, "Gravekeeper's Curse", 0)  # "when Summoned: 500 to the opponent"
    reborn = _set_spell(s, "Monster Reborn", 0)
    before = s.players[1].life_points
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_as_chain(ActivateSpell(reborn.iid, targets=(curse.iid,)), 0)
    assert s.inst(curse.iid).zone is Zone.MONSTER  # revived
    assert s.players[1].life_points == before - 500  # its on-summon burn fired


# --- combat path: a recruiter's Deck summon also drains through the same hook ------
def test_recruiter_summon_fires_its_on_summon_trigger():
    s = _fresh(turn_player=1, phase=Phase.BATTLE)
    tomato = s.spawn_on_field(reg.get("Mystic Tomato"), 0, 0, Position.FACE_UP_ATTACK)
    # The only eligible DARK <=1500-ATK recruit in the deck has an on-summon burn.
    s.players[0].deck.append(
        s.create_instance(reg.get("Gravekeeper's Curse"), 0, Zone.DECK).iid
    )
    skull = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    before = s.players[1].life_points
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(skull.iid, tomato.iid), 1)
    curse = next(
        s.inst(i)
        for i in s.players[0].monster_zones
        if i is not None and s.inst(i).card.name == "Gravekeeper's Curse"
    )
    assert curse.zone is Zone.MONSTER  # recruited from the Deck
    assert s.players[1].life_points == before - 500  # and its on-summon trigger fired


def test_recruiter_summon_can_be_negated_by_black_horn():
    s = _fresh(turn_player=1, phase=Phase.BATTLE)
    tomato = s.spawn_on_field(reg.get("Mystic Tomato"), 0, 0, Position.FACE_UP_ATTACK)
    recruit = s.create_instance(reg.get("Gravekeeper's Curse"), 0, Zone.DECK)
    s.players[0].deck.append(recruit.iid)
    skull = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    horn = _set_card(s, "Black Horn of Heaven", 1, 1)
    eng = Engine(s, [Agent(), ActivateByName("Black Horn of Heaven")])
    eng._declare_attack(DeclareAttack(skull.iid, tomato.iid), 1)
    # Black Horn negates the recruiter's Special Summon and destroys the monster.
    assert s.inst(recruit.iid).zone is Zone.GRAVEYARD
    assert s.inst(horn.iid).zone is Zone.GRAVEYARD


# --- regression: an unanswered effect summon still just works ----------------------
def test_reborn_without_a_response_just_summons():
    s = _fresh()
    dead = _in_gy(s, "Summoned Skull", 0)
    reborn = _set_spell(s, "Monster Reborn", 0)
    Engine(s, [Agent(), Agent()])._activate_as_chain(
        ActivateSpell(reborn.iid, targets=(dead.iid,)), 0
    )
    assert s.inst(dead.iid).zone is Zone.MONSTER
