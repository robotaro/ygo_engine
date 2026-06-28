"""Slice 7 tests: Field Spells as field-wide stat layers (Sogen / Yami / Gaia
Power), Field-Zone replacement, MST destroying a Field Spell, and the continuous
attack restriction (The Dark Door)."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, apply, legal_actions, target_candidates
from ygo.effects import TargetSpec
from ygo.paths import DECKS_DIR
from ygo.serialize import legal_to_dict, state_to_dict
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _attacks(state, player):
    return [a for a in legal_actions(state, player) if isinstance(a, DeclareAttack)]


# --------------------------------------------------------------------------- #
#  Field Spells — field-wide stat layers
# --------------------------------------------------------------------------- #
def test_sogen_boosts_both_sides_warriors_only():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    ox = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)  # Beast-Warrior 1700
    foe = s.spawn_on_field(reg.get("Axe Raider"), 1, 0, Position.FACE_UP_ATTACK)  # Warrior 1700 (opp)
    elf = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)  # Spellcaster 800

    sogen = _in_hand(s, "Sogen", 0)
    apply(s, ActivateSpell(sogen.iid, targets=()))

    assert s.players[0].field_zone == sogen.iid
    assert s.effective_attack(ox.iid) == 1900  # my Beast-Warrior +200
    assert s.effective_attack(foe.iid) == 1900  # opponent's Warrior +200 too (both sides)
    assert s.effective_attack(elf.iid) == 800  # Spellcaster untouched


def test_yami_boosts_spellcasters_and_weakens_fairies():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    elf = s.spawn_on_field(reg.get("Gemini Elf"), 0, 0, Position.FACE_UP_ATTACK)  # Spellcaster 1900
    fairy = s.spawn_on_field(reg.get("Dunames Dark Witch"), 1, 0, Position.FACE_UP_ATTACK)  # Fairy 1800

    apply(s, ActivateSpell(_in_hand(s, "Yami", 0).iid, targets=()))
    assert s.effective_attack(elf.iid) == 2100  # +200 Spellcaster
    assert s.effective_attack(fairy.iid) == 1600  # -200 Fairy


def test_gaia_power_boosts_attack_and_drops_defense_of_earth():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    ox = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)  # EARTH 1700/1000
    apply(s, ActivateSpell(_in_hand(s, "Gaia Power", 0).iid, targets=()))
    assert s.effective_attack(ox.iid) == 2200  # +500
    assert s.effective_defense(ox.iid) == 600  # -400


def test_activating_a_second_field_spell_destroys_the_first():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    sogen = _in_hand(s, "Sogen", 0)
    apply(s, ActivateSpell(sogen.iid, targets=()))
    yami = _in_hand(s, "Yami", 0)
    apply(s, ActivateSpell(yami.iid, targets=()))

    assert s.players[0].field_zone == yami.iid
    assert s.inst(sogen.iid).zone is Zone.GRAVEYARD  # replaced -> to the GY


def test_field_spell_swings_combat():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    elf = s.spawn_on_field(reg.get("Gemini Elf"), 0, 0, Position.FACE_UP_ATTACK)  # Spellcaster 1900
    foe = s.spawn_on_field(reg.get("Vorse Raider"), 1, 0, Position.FACE_UP_ATTACK)  # Beast-Warrior 1900
    apply(s, ActivateSpell(_in_hand(s, "Yami", 0).iid, targets=()))  # Gemini Elf -> 2100
    assert s.effective_attack(elf.iid) == 2100

    s.phase = Phase.BATTLE
    Engine(s, [GreedyAgent(), GreedyAgent()])._declare_attack(DeclareAttack(elf.iid, foe.iid), 0)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # 2100 beats the un-boosted 1900
    assert s.players[1].life_points == 8000 - 200


def test_mst_can_destroy_a_field_spell_and_remove_its_layer():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    ox = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)
    sogen = _in_hand(s, "Sogen", 1)  # the OPPONENT's Field Spell
    s.place_field_spell(sogen.iid, 1, Position.FACE_UP_ATTACK)
    assert s.effective_attack(ox.iid) == 1900  # boosted by the opponent's Sogen (both sides)

    # Field Spells are part of the "spell_trap_field" target pool now.
    assert sogen.iid in target_candidates(s, 0, TargetSpec(where="spell_trap_field"))
    apply(s, ActivateSpell(_in_hand(s, "Mystical Space Typhoon", 0).iid, targets=(sogen.iid,)))

    assert s.inst(sogen.iid).zone is Zone.GRAVEYARD
    assert s.effective_attack(ox.iid) == 1700  # the layer is gone


# --------------------------------------------------------------------------- #
#  Continuous Spell — The Dark Door (one attack per Battle Phase)
# --------------------------------------------------------------------------- #
def _dark_door_on_field(s, player=0):
    door = s.create_instance(reg.get("The Dark Door"), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(door.iid)
    s.place_spell_trap(door.iid, player, 0, Position.FACE_UP_ATTACK)
    return door


def test_the_dark_door_limits_to_one_attack():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    a = s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Axe Raider"), 0, 1, Position.FACE_UP_ATTACK)  # opp has no monsters
    _dark_door_on_field(s, 0)

    assert len(_attacks(s, 0)) == 2  # both could attack directly
    s.inst(a.iid).attacked_this_turn = True  # one attacks
    assert _attacks(s, 0) == []  # no second attack allowed this Battle Phase


def test_the_dark_door_engine_lets_only_one_attack_through():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    s.spawn_on_field(reg.get("Battle Ox"), 0, 0, Position.FACE_UP_ATTACK)  # 1700
    s.spawn_on_field(reg.get("Axe Raider"), 0, 1, Position.FACE_UP_ATTACK)  # 1700
    _dark_door_on_field(s, 0)

    Engine(s, [GreedyAgent(), GreedyAgent()])._battle_phase(0)
    assert s.players[1].life_points == 8000 - 1700  # only ONE of the two got to attack


# --------------------------------------------------------------------------- #
#  Web contract + integration
# --------------------------------------------------------------------------- #
def test_web_contract_field_spell_activatable_without_a_spell_trap_zone():
    s = GameState.new(("You", "CPU"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    sogen = _in_hand(s, "Sogen", 0)
    assert legal_to_dict(s, 0, with_pass=True)["activatable"].get(str(sogen.iid)) == [[]]

    # Fill every Spell/Trap zone — a Field Spell still activates (it uses the Field Zone).
    for i in range(5):
        st = s.create_instance(reg.get("Mirror Force"), owner=0, zone=Zone.DECK)
        s.players[0].deck.append(st.iid)
        s.place_spell_trap(st.iid, 0, i, Position.FACE_DOWN)
    assert legal_to_dict(s, 0, with_pass=True)["activatable"].get(str(sogen.iid)) == [[]]


def test_serialize_exposes_subtype_and_field_zone():
    s = GameState.new(("You", "CPU"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    sogen = _in_hand(s, "Sogen", 0)
    assert state_to_dict(s, 0)["you"]["hand"][0]["subtype"] == "Field"  # board can tell it's a Field Spell
    apply(s, ActivateSpell(sogen.iid, targets=()))
    fz = state_to_dict(s, 0)["you"]["fieldZone"]
    assert fz is not None and fz["name"] == "Sogen"


def test_bot_duel_with_field_spells_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=5,
    )
    assert not duel.missing_report  # all Slice 7 card names resolve
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
