"""Effects Batch 16: negate the activation (Counter Traps, Spell Speed 3).

Chained in response to an activation, these negate the Chain link directly below
them (it never resolves) and destroy that card. Magic Jammer (discard 1; negate a
Spell), Seven Tools of the Bandit (pay 1000 LP; negate a Trap), Dark Bribe
(opponent draws 1; negate a Spell/Trap). Chains only run through the Engine, so
these drive it directly."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, Pass
from ygo.state import GameState

reg = CardRegistry.load_csv()


class ActivateByName(Agent):
    """Springs a named card whenever a response window offers it; otherwise passes."""

    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _set_card(s, name, player, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = 1
    return inst


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


# --- Magic Jammer: discard 1, negate a Spell -----------------------------------
def test_magic_jammer_negates_a_spell():
    s = _fresh()
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    pot = _in_hand(s, "Pot of Greed", 0)
    jammer = _set_card(s, "Magic Jammer", 1)
    fodder = _in_hand(s, "Summoned Skull", 1)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Magic Jammer")])
    deck_before = len(s.players[0].deck)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert s.inst(pot.iid).zone is Zone.GRAVEYARD  # spent and negated
    assert s.inst(jammer.iid).zone is Zone.GRAVEYARD  # the Counter Trap is one-shot
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the discard cost was paid
    assert len(s.players[0].deck) == deck_before  # Pot of Greed drew nothing
    assert s.chain == []


def test_pot_of_greed_resolves_when_not_countered():
    s = _fresh()
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    pot = _in_hand(s, "Pot of Greed", 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("x")])  # nobody counters
    deck_before = len(s.players[0].deck)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert len(s.players[0].deck) == deck_before - 2  # the normal Pot of Greed draw


def test_magic_jammer_cannot_negate_a_trap():
    s = _fresh()
    jd = _set_card(s, "Just Desserts", 0, 0)  # a Trap, activated by player 0
    jammer = _set_card(s, "Magic Jammer", 1, 0)
    _in_hand(s, "Summoned Skull", 1)  # fodder is available
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Magic Jammer")])
    eng._activate_as_chain(ActivateSpell(jd.iid), 0)
    # Magic Jammer only negates Spells, so it was never offered against a Trap.
    assert s.inst(jammer.iid).zone is Zone.SPELL_TRAP
    assert s.inst(jammer.iid).position is Position.FACE_DOWN
    assert s.inst(jd.iid).zone is Zone.GRAVEYARD  # Just Desserts resolved normally


# --- Seven Tools of the Bandit: pay 1000 LP, negate a Trap ----------------------
def test_seven_tools_pays_1000_and_negates_a_trap():
    s = _fresh()
    for i in range(3):
        s.spawn_on_field(reg.get("Mystical Elf"), 1, i, Position.FACE_UP_ATTACK)  # would-be 1500 burn
    jd = _set_card(s, "Just Desserts", 0, 0)
    seven = _set_card(s, "Seven Tools of the Bandit", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Seven Tools of the Bandit")])
    eng._activate_as_chain(ActivateSpell(jd.iid), 0)
    assert s.inst(jd.iid).zone is Zone.GRAVEYARD  # negated and spent
    assert s.inst(seven.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 7000  # paid 1000; the 1500 burn was negated


def test_seven_tools_not_offered_without_the_life_points():
    s = _fresh()
    s.players[1].life_points = 500  # cannot pay 1000
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    jd = _set_card(s, "Just Desserts", 0, 0)
    seven = _set_card(s, "Seven Tools of the Bandit", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Seven Tools of the Bandit")])
    eng._activate_as_chain(ActivateSpell(jd.iid), 0)
    assert s.inst(seven.iid).zone is Zone.SPELL_TRAP  # could not pay -> never activated
    assert s.inst(jd.iid).zone is Zone.GRAVEYARD  # Just Desserts resolved
    assert s.players[1].life_points == 500 - 500  # took the 500 burn (1 monster)


# --- Dark Bribe: opponent draws 1, negate a Spell/Trap --------------------------
def test_dark_bribe_negates_a_spell_and_gives_opponent_a_draw():
    s = _fresh()
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    pot = _in_hand(s, "Pot of Greed", 0)
    bribe = _set_card(s, "Dark Bribe", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Dark Bribe")])
    deck_before = len(s.players[0].deck)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert s.inst(pot.iid).zone is Zone.GRAVEYARD  # negated and spent
    assert s.inst(bribe.iid).zone is Zone.GRAVEYARD
    # Pot of Greed negated (no +2 draw); Dark Bribe gave the opponent +1.
    assert len(s.players[0].deck) == deck_before - 1
