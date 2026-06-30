"""Effects Batch 90: heavy disruption — Solemn Judgment + Tribe-Infecting Virus.

Solemn Judgment (Counter Trap): "Pay half your LP; negate a Summon OR a Spell/Trap
activation, and if you do, destroy that card." Two effects, one per seam: the quick
chain-response (negate a S/T activation, like Magic Jammer/Dark Bribe) and the Summon
window (destroy the Normal-Summoned monster, like Horn of Heaven). Both pay half LP
first — LoseHalfLifePoints subtracts directly, so it's a cost, not damage.

Tribe-Infecting Virus: "Discard 1; declare 1 Type; destroy all face-up monsters of that
Type." A monster Ignition effect; headless it declares the Type that nets the most enemy
monsters destroyed.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, NormalSummon, Pass, apply, resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()


class ActivateByName(Agent):
    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


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


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


# ---------------------------------------------------- Solemn Judgment: negate a Spell


def test_solemn_judgment_negates_a_spell_and_pays_half_lp():
    s = _fresh()
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    pot = _in_hand(s, "Pot of Greed", 0)
    sj = _set_card(s, "Solemn Judgment", 1)
    s.players[1].life_points = 8000
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Solemn Judgment")])
    deck_before = len(s.players[0].deck)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert s.inst(pot.iid).zone is Zone.GRAVEYARD  # negated + destroyed
    assert s.inst(sj.iid).zone is Zone.GRAVEYARD  # the Counter Trap is one-shot
    assert len(s.players[0].deck) == deck_before  # Pot of Greed drew nothing
    assert s.players[1].life_points == 4000  # paid half its LP
    assert s.chain == []


def test_pot_of_greed_resolves_when_solemn_not_used():
    s = _fresh()
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    pot = _in_hand(s, "Pot of Greed", 0)
    _set_card(s, "Solemn Judgment", 1)
    eng = Engine(s, [ActivateByName("x"), ActivateByName("x")])  # nobody responds
    deck_before = len(s.players[0].deck)
    eng._activate_as_chain(ActivateSpell(pot.iid), 0)
    assert len(s.players[0].deck) == deck_before - 2  # Pot drew its 2


# ---------------------------------------------------- Solemn Judgment: negate a Summon


def _normal_summon_then_window(eng, s, iid, player=0):
    apply(s, NormalSummon(iid))
    eng._response_window(
        {"kind": "summon", "player": player, "monster": iid, "summon_kind": "normal"}
    )


def test_solemn_judgment_negates_a_summon_and_pays_half_lp():
    s = _fresh()
    elf = _in_hand(s, "Mystical Elf", 0)
    sj = _set_card(s, "Solemn Judgment", 1)
    s.players[1].life_points = 6000
    eng = Engine(s, [ActivateByName("x"), ActivateByName("Solemn Judgment")])
    _normal_summon_then_window(eng, s, elf.iid)
    assert s.inst(elf.iid).zone is Zone.GRAVEYARD  # the Summon was negated -> destroyed
    assert s.inst(sj.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 3000  # paid half


# ---------------------------------------------------------- Tribe-Infecting Virus


def test_tribe_virus_declares_the_type_that_nets_the_most_enemy_kills():
    s = _fresh()
    # Opponent: 2 Spellcasters + 1 Warrior. Me: 1 Spellcaster.
    foe_sc1 = _spawn(s, "Dark Magician", 1, 0)
    foe_sc2 = _spawn(s, "Mystical Elf", 1, 1)
    foe_war = _spawn(s, "Celtic Guardian", 1, 2)
    my_sc = _spawn(s, "Skilled Dark Magician", 0, 1)
    virus = _spawn(s, "Tribe-Infecting Virus", 0, 0)
    resolve_effect(s, EFFECTS["Tribe-Infecting Virus"][0], virus.iid)
    # Spellcaster nets 2-1=1 (best); both opponent Spellcasters die, and so does mine.
    assert s.inst(foe_sc1.iid).zone is Zone.GRAVEYARD
    assert s.inst(foe_sc2.iid).zone is Zone.GRAVEYARD
    assert s.inst(my_sc.iid).zone is Zone.GRAVEYARD  # my own declared-Type monster too
    assert s.inst(foe_war.iid).zone is Zone.MONSTER  # the Warrior survives


def test_tribe_virus_discard_cost_gates_activation():
    from ygo.moves import legal_actions, ActivateMonsterEffect

    s = _fresh()
    _spawn(s, "Summoned Skull", 1, 0)  # an opponent monster to target
    virus = _spawn(s, "Tribe-Infecting Virus", 0, 0)
    # Empty hand -> the discard cost is unpayable -> the effect is not offered.
    assert not any(
        isinstance(a, ActivateMonsterEffect) and a.iid == virus.iid
        for a in legal_actions(s, 0)
    )
    _in_hand(s, "Mystical Elf", 0)  # now there's a card to discard
    assert any(
        isinstance(a, ActivateMonsterEffect) and a.iid == virus.iid
        for a in legal_actions(s, 0)
    )


def test_tribe_virus_inert_when_opponent_has_no_faceup_monster():
    from ygo.moves import legal_actions, ActivateMonsterEffect

    s = _fresh()
    virus = _spawn(s, "Tribe-Infecting Virus", 0, 0)
    _in_hand(s, "Mystical Elf", 0)  # has discard fodder, but no enemy target
    assert not any(
        isinstance(a, ActivateMonsterEffect) and a.iid == virus.iid
        for a in legal_actions(s, 0)
    )
