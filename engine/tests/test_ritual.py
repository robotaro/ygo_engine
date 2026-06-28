"""Slice 12 tests: Ritual Summoning. A Ritual Spell Tributes monsters whose Levels
total at least the Ritual Monster's Level (from hand or field), then Special
Summons that Ritual Monster from the hand."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, NormalSummon, can_ritual_summon, legal_actions
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _engine(s):
    return Engine(s, [GreedyAgent(), GreedyAgent()])


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _activatable_ritual(s, player=0):
    rituals = {"Black Luster Ritual", "Hamburger Recipe"}
    return [
        a
        for a in legal_actions(s, player)
        if isinstance(a, ActivateSpell) and s.inst(a.iid).card.name in rituals
    ]


# --------------------------------------------------------------------------- #
#  can_ritual_summon — feasibility
# --------------------------------------------------------------------------- #
def test_can_ritual_when_monster_and_fodder_in_hand():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_hand(s, "Hungry Burger", 0)  # Lv6 Ritual Monster
    _in_hand(s, "Summoned Skull", 0)  # Lv6 -> meets the requirement
    assert can_ritual_summon(s, 0, "Hungry Burger")


def test_cannot_ritual_without_the_monster_in_hand():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_hand(s, "Summoned Skull", 0)  # fodder but no Ritual Monster
    assert not can_ritual_summon(s, 0, "Hungry Burger")


def test_cannot_ritual_without_enough_levels():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_hand(s, "Hungry Burger", 0)  # needs Level 6
    _in_hand(s, "Mystical Elf", 0)  # only Lv4
    assert not can_ritual_summon(s, 0, "Hungry Burger")


# --------------------------------------------------------------------------- #
#  The Ritual Summon
# --------------------------------------------------------------------------- #
def test_ritual_summons_from_hand_tributes():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    burger = _in_hand(s, "Hungry Burger", 0)
    recipe = _in_hand(s, "Hamburger Recipe", 0)
    fodder = _in_hand(s, "Summoned Skull", 0)  # Lv6

    _engine(s)._activate_as_chain(ActivateSpell(recipe.iid, targets=()), 0)

    assert s.inst(burger.iid).zone is Zone.MONSTER  # summoned from the hand
    assert s.inst(burger.iid).controller == 0
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # Tributed
    assert s.inst(recipe.iid).zone is Zone.GRAVEYARD  # the Ritual Spell is spent


def test_ritual_summons_using_field_tributes():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    burger = _in_hand(s, "Hungry Burger", 0)
    recipe = _in_hand(s, "Hamburger Recipe", 0)
    skull = s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)  # Lv6

    _engine(s)._activate_as_chain(ActivateSpell(recipe.iid, targets=()), 0)
    assert s.inst(skull.iid).zone is Zone.GRAVEYARD
    assert s.inst(burger.iid).zone is Zone.MONSTER


def test_ritual_from_a_full_field_frees_a_slot():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    burger = _in_hand(s, "Hungry Burger", 0)
    recipe = _in_hand(s, "Hamburger Recipe", 0)
    # Field is full; two of these will be Tributed (Lv4 + Lv4 >= 6), freeing room.
    for i in range(5):
        s.spawn_on_field(reg.get("Battle Ox"), 0, i, Position.FACE_UP_ATTACK)  # Lv4
    assert can_ritual_summon(s, 0, "Hungry Burger")

    _engine(s)._activate_as_chain(ActivateSpell(recipe.iid, targets=()), 0)
    assert s.inst(burger.iid).zone is Zone.MONSTER


def test_ritual_spell_not_activatable_without_fodder():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_hand(s, "Hungry Burger", 0)
    _in_hand(s, "Hamburger Recipe", 0)  # no Tribute fodder at all
    assert _activatable_ritual(s, 0) == []


def test_ritual_monster_is_main_deck_and_not_normal_summonable():
    bls = reg.get("Black Luster Soldier")
    assert bls.is_ritual
    assert not bls.can_normal_summon  # only a Ritual Summon brings it out
    assert not bls.goes_in_extra_deck  # it lives in the Main Deck, not the Extra Deck

    # A Ritual Monster sitting in hand offers no Normal Summon.
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    bls_inst = _in_hand(s, "Black Luster Soldier", 0)
    assert not any(isinstance(a, NormalSummon) and a.iid == bls_inst.iid for a in legal_actions(s, 0))


def test_bot_duel_with_rituals_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=5,
    )
    assert not duel.missing_report
    # Ritual Monsters stay in the Main Deck (not the Extra Deck).
    assert any(c.name == "Black Luster Soldier" for c in duel.decklists[0].main)
    assert all(c.name != "Black Luster Soldier" for c in duel.decklists[0].extra)
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
