"""Effects Batch 17: negate the Summon / a monster effect / negate-and-bounce.

Horn of Heaven (Tribute 1; negate a Normal Summon + destroy), Forced Back (negate
a Normal Summon + bounce to hand), Divine Wrath (discard 1; negate a monster
effect + destroy the monster), Goblin Out of the Frying Pan (pay 500; negate a
Spell + bounce it to hand). The Summon response window fires on Normal Summons, so
these drive the Engine directly."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, NormalSummon, Pass
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


class TargetThen(ActivateByName):
    """Like ActivateByName, but forces a specific target when asked (so a monster
    effect points where the test wants)."""

    def __init__(self, name, target_iid):
        super().__init__(name)
        self.target_iid = target_iid

    def choose_targets(self, state, source_iid, spec, candidates):
        return (self.target_iid,)


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


def _normal_summon_then_window(eng, s, iid, player=0):
    """Mirror the main loop: apply the Normal Summon, then open the Summon window."""
    from ygo.moves import apply

    apply(s, NormalSummon(iid))
    eng._response_window({"kind": "summon", "player": player, "monster": iid})


# --- Horn of Heaven: Tribute 1, negate a Normal Summon + destroy ---------------
def test_horn_of_heaven_negates_a_normal_summon():
    s = _fresh()
    elf = _in_hand(s, "Mystical Elf", 0)
    tribute = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    horn = _set_card(s, "Horn of Heaven", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Horn of Heaven")])
    _normal_summon_then_window(eng, s, elf.iid)
    assert s.inst(elf.iid).zone is Zone.GRAVEYARD  # the Summon was negated -> destroyed
    assert s.inst(tribute.iid).zone is Zone.GRAVEYARD  # Horn's Tribute cost
    assert s.inst(horn.iid).zone is Zone.GRAVEYARD


def test_horn_of_heaven_needs_a_monster_to_tribute():
    s = _fresh()
    elf = _in_hand(s, "Mystical Elf", 0)
    horn = _set_card(s, "Horn of Heaven", 1, 0)  # player 1 controls no monster
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Horn of Heaven")])
    _normal_summon_then_window(eng, s, elf.iid)
    assert s.inst(elf.iid).zone is Zone.MONSTER  # the Summon stands (cost unpayable)
    assert s.inst(horn.iid).zone is Zone.SPELL_TRAP  # never activated


# --- Forced Back: negate a Normal Summon + bounce to hand ----------------------
def test_forced_back_returns_a_summoned_monster_to_hand():
    s = _fresh()
    elf = _in_hand(s, "Mystical Elf", 0)
    fb = _set_card(s, "Forced Back", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Forced Back")])
    _normal_summon_then_window(eng, s, elf.iid)
    assert s.inst(elf.iid).zone is Zone.HAND  # bounced back to the owner's hand
    assert elf.iid in s.players[0].hand
    assert s.inst(fb.iid).zone is Zone.GRAVEYARD


# --- Divine Wrath: discard 1, negate a monster effect + destroy the monster -----
def test_divine_wrath_negates_a_monster_effect_and_destroys_it():
    s = _fresh()
    bug = s.spawn_on_field(reg.get("Man-Eater Bug"), 0, 0, Position.FACE_UP_ATTACK)
    victim = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    wrath = _set_card(s, "Divine Wrath", 1, 0)
    fodder = _in_hand(s, "Mystical Elf", 1)
    eng = Engine(s, [TargetThen("x", victim.iid), ActivateByName("Divine Wrath")])
    eng._trigger_effect(bug.iid, bug.card.effects[0], 0)  # Man-Eater Bug's flip effect
    assert s.inst(bug.iid).zone is Zone.GRAVEYARD  # the monster is destroyed
    assert s.inst(victim.iid).zone is Zone.MONSTER  # its effect was negated -> victim lives
    assert s.inst(wrath.iid).zone is Zone.GRAVEYARD
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the discard cost


def test_divine_wrath_cannot_negate_a_spell():
    s = _fresh()
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    pot = _in_hand(s, "Pot of Greed", 0)
    wrath = _set_card(s, "Divine Wrath", 1, 0)
    _in_hand(s, "Mystical Elf", 1)  # fodder available
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Divine Wrath")])
    deck_before = len(s.players[0].deck)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert s.inst(wrath.iid).zone is Zone.SPELL_TRAP  # only negates monster effects
    assert len(s.players[0].deck) == deck_before - 2  # Pot resolved normally


# --- Goblin Out of the Frying Pan: pay 500, negate a Spell + bounce to hand ------
def test_goblin_out_of_the_frying_pan_negates_a_spell_and_bounces_it():
    s = _fresh()
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    pot = _in_hand(s, "Pot of Greed", 0)
    goblin = _set_card(s, "Goblin Out of the Frying Pan", 1, 0)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Goblin Out of the Frying Pan")])
    deck_before = len(s.players[0].deck)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert s.inst(pot.iid).zone is Zone.HAND  # negated and bounced back to hand
    assert pot.iid in s.players[0].hand
    assert s.inst(goblin.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 7500  # paid 500 LP
    assert len(s.players[0].deck) == deck_before  # Pot of Greed drew nothing
