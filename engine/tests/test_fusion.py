"""Slice 11 tests: Fusion Summoning. Polymerization sends a Fusion Monster's named
materials from hand/field to the Graveyard and Special Summons it from the Extra
Deck. Material matching is by exact card name; the choice of which Fusion to make
goes through the agent's choose_card hook."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, legal_actions, makeable_fusions
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


def _to_extra(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.EXTRA_DECK)
    s.players[player].extra_deck.append(inst.iid)
    return inst


def _activatable_poly(s, player=0):
    return [
        a
        for a in legal_actions(s, player)
        if isinstance(a, ActivateSpell) and s.inst(a.iid).card.name == "Polymerization"
    ]


# --------------------------------------------------------------------------- #
#  makeable_fusions — recipe matching
# --------------------------------------------------------------------------- #
def test_makeable_when_materials_in_hand():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_hand(s, "Gaia The Fierce Knight", 0)
    _in_hand(s, "Curse of Dragon", 0)
    gaia = _to_extra(s, "Gaia the Dragon Champion", 0)

    options = makeable_fusions(s, 0)
    assert [fid for fid, _ in options] == [gaia.iid]


def test_not_makeable_when_a_material_is_missing():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_hand(s, "Gaia The Fierce Knight", 0)  # only one of the two materials
    _to_extra(s, "Gaia the Dragon Champion", 0)
    assert makeable_fusions(s, 0) == []


def test_makeable_from_a_full_field_of_materials():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get("Gaia The Fierce Knight"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Curse of Dragon"), 0, 1, Position.FACE_UP_ATTACK)
    for i in range(2, 5):  # fill the rest of the Monster Zones
        s.spawn_on_field(reg.get("Mystical Elf"), 0, i, Position.FACE_UP_ATTACK)
    _to_extra(s, "Gaia the Dragon Champion", 0)
    # Field is full, but the two materials will free a slot when they leave.
    assert len(makeable_fusions(s, 0)) == 1


# --------------------------------------------------------------------------- #
#  Polymerization — the Fusion Summon
# --------------------------------------------------------------------------- #
def test_polymerization_fusion_summons_from_hand():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    knight = _in_hand(s, "Gaia The Fierce Knight", 0)
    curse = _in_hand(s, "Curse of Dragon", 0)
    gaia = _to_extra(s, "Gaia the Dragon Champion", 0)
    poly = _in_hand(s, "Polymerization", 0)

    _engine(s)._activate_as_chain(ActivateSpell(poly.iid, targets=()), 0)

    assert s.inst(gaia.iid).zone is Zone.MONSTER  # the Fusion is on the field
    assert s.inst(gaia.iid).controller == 0
    assert s.inst(knight.iid).zone is Zone.GRAVEYARD  # materials sent to the GY
    assert s.inst(curse.iid).zone is Zone.GRAVEYARD
    assert s.inst(poly.iid).zone is Zone.GRAVEYARD  # Polymerization spent


def test_polymerization_fusion_summons_from_field():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    knight = s.spawn_on_field(reg.get("Gaia The Fierce Knight"), 0, 0, Position.FACE_UP_ATTACK)
    curse = s.spawn_on_field(reg.get("Curse of Dragon"), 0, 1, Position.FACE_UP_ATTACK)
    gaia = _to_extra(s, "Gaia the Dragon Champion", 0)
    poly = _in_hand(s, "Polymerization", 0)

    _engine(s)._activate_as_chain(ActivateSpell(poly.iid, targets=()), 0)
    assert s.inst(gaia.iid).zone is Zone.MONSTER
    assert s.inst(knight.iid).zone is Zone.GRAVEYARD
    assert s.inst(curse.iid).zone is Zone.GRAVEYARD


def test_polymerization_not_activatable_without_materials():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _to_extra(s, "Gaia the Dragon Champion", 0)
    _in_hand(s, "Polymerization", 0)  # no materials in hand/field
    assert _activatable_poly(s, 0) == []


def test_greedy_chooses_the_strongest_fusion():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    # Materials for two different Fusions in hand at once.
    _in_hand(s, "Gaia The Fierce Knight", 0)
    _in_hand(s, "Curse of Dragon", 0)  # -> Gaia the Dragon Champion (2600)
    _in_hand(s, "Flame Manipulator", 0)
    _in_hand(s, "Masaki the Legendary Swordsman", 0)  # -> Flame Swordsman (1800)
    _to_extra(s, "Gaia the Dragon Champion", 0)
    flame = _to_extra(s, "Flame Swordsman", 0)
    poly = _in_hand(s, "Polymerization", 0)

    assert len(makeable_fusions(s, 0)) == 2
    _engine(s)._activate_as_chain(ActivateSpell(poly.iid, targets=()), 0)

    # GreedyAgent.choose_card picks the higher-ATK Fusion (Gaia the Dragon Champion).
    gaia_iid = next(i for i in s.players[0].monster_zones if i and s.inst(i).name == "Gaia the Dragon Champion")
    assert s.inst(gaia_iid).zone is Zone.MONSTER
    assert s.inst(flame.iid).zone is Zone.EXTRA_DECK  # the weaker one stayed home


def test_fusion_monster_can_attack_the_turn_it_is_summoned():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_hand(s, "Gaia The Fierce Knight", 0)
    _in_hand(s, "Curse of Dragon", 0)
    gaia = _to_extra(s, "Gaia the Dragon Champion", 0)
    poly = _in_hand(s, "Polymerization", 0)
    _engine(s)._activate_as_chain(ActivateSpell(poly.iid, targets=()), 0)

    s.phase = Phase.BATTLE
    from ygo.moves import DeclareAttack

    attacks = [a for a in legal_actions(s, 0) if isinstance(a, DeclareAttack)]
    assert any(a.attacker == gaia.iid for a in attacks)


def test_bot_duel_with_fusions_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=5,
    )
    assert not duel.missing_report
    # Fusion monsters routed to the Extra Deck, materials to the main deck.
    assert any(c.name == "Gaia the Dragon Champion" for c in duel.decklists[0].extra)
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
