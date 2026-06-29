"""Slice 3 tests: Set Spell/Trap, spell speed, response windows, and the Chain."""

from __future__ import annotations

from ygo.agents import Agent, GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    DeclareAttack,
    Pass,
    SetMonster,
    SetSpellTrap,
    apply,
    legal_actions,
    response_options,
)
from ygo.serialize import legal_to_dict, match_intent
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()


class ActivateByName(Agent):
    """A test agent that springs a named card whenever a window allows it."""

    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _set_card(state, name, player, index, set_on_turn=1):
    inst = state.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    state.players[player].deck.append(inst.iid)
    state.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = set_on_turn
    return inst


def _battle_setup(attacker_name="Blue-Eyes White Dragon"):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    attacker = s.spawn_on_field(reg.get(attacker_name), 0, 0, Position.FACE_UP_ATTACK)
    return s, attacker


# --------------------------------------------------------------------------- #
#  Setting Spell/Traps
# --------------------------------------------------------------------------- #
def test_set_spell_trap_goes_face_down_and_records_turn():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count = Phase.MAIN_1, 3
    trap = s.create_instance(reg.get("Mirror Force"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(trap.iid)
    assert any(isinstance(a, SetSpellTrap) and a.iid == trap.iid for a in legal_actions(s, 0))
    apply(s, SetSpellTrap(trap.iid))
    inst = s.inst(trap.iid)
    assert inst.zone is Zone.SPELL_TRAP
    assert inst.position is Position.FACE_DOWN
    assert inst.set_on_turn == 3


def test_set_intent_disambiguates_monster_from_spell_trap():
    # A "set" intent must resolve to SetMonster or SetSpellTrap based on the card.
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count = Phase.MAIN_1, 2
    mon = s.create_instance(reg.get("Battle Ox"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(mon.iid)
    trap = s.create_instance(reg.get("Mirror Force"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(trap.iid)
    legal = legal_actions(s, 0)
    assert isinstance(match_intent({"kind": "set", "iid": mon.iid, "tributes": []}, legal, s), SetMonster)
    assert isinstance(match_intent({"kind": "set", "iid": trap.iid}, legal, s), SetSpellTrap)


def test_trap_cannot_activate_the_turn_it_was_set():
    s, attacker = _battle_setup()
    _set_card(s, "Mirror Force", 1, 0, set_on_turn=2)  # set THIS turn
    event = {"kind": "attack_declared", "player": 0, "attacker": attacker.iid, "target": None}
    assert response_options(s, 1, event, last_speed=1) == []


def test_trap_can_activate_a_later_turn():
    s, attacker = _battle_setup()
    _set_card(s, "Mirror Force", 1, 0, set_on_turn=1)  # set earlier
    event = {"kind": "attack_declared", "player": 0, "attacker": attacker.iid, "target": None}
    assert len(response_options(s, 1, event, last_speed=1)) == 1


# --------------------------------------------------------------------------- #
#  Spell speed gating
# --------------------------------------------------------------------------- #
def test_spell_speed_gates_responses():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    # a face-up Spell/Trap to give MST a legal target
    _set_card(s, "Trap Hole", 1, 0, set_on_turn=1)
    mst = s.create_instance(reg.get("Mystical Space Typhoon"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(mst.iid)
    assert response_options(s, 0, None, last_speed=2)  # MST (speed 2) may respond to speed 2
    assert response_options(s, 0, None, last_speed=3) == []  # ...but not to a Counter (speed 3)


# --------------------------------------------------------------------------- #
#  Reactive cards via the engine
# --------------------------------------------------------------------------- #
def test_mirror_force_negates_attack_and_destroys_attackers():
    s, attacker = _battle_setup()
    _set_card(s, "Mirror Force", 1, 0)
    eng = Engine(s, [GreedyAgent(), ActivateByName("Mirror Force")])
    eng._declare_attack(DeclareAttack(attacker.iid, None), 0)
    assert s.inst(attacker.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 8000  # direct attack was negated
    assert s.chain == []  # chain cleaned up


def test_magic_cylinder_reflects_attacker_atk():
    s, attacker = _battle_setup("Blue-Eyes White Dragon")  # 3000 ATK
    _set_card(s, "Magic Cylinder", 1, 0)
    eng = Engine(s, [GreedyAgent(), ActivateByName("Magic Cylinder")])
    eng._declare_attack(DeclareAttack(attacker.iid, None), 0)
    assert s.players[0].life_points == 8000 - 3000  # reflected to the attacker
    assert s.inst(attacker.iid).zone is Zone.MONSTER  # not destroyed, just negated


def test_trap_hole_destroys_a_big_summon_but_not_a_small_one():
    # big summon -> destroyed
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    big = s.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    _set_card(s, "Trap Hole", 1, 0)
    Engine(s, [GreedyAgent(), ActivateByName("Trap Hole")])._response_window(
        {"kind": "summon", "player": 0, "monster": big.iid, "summon_kind": "normal"}
    )
    assert s.inst(big.iid).zone is Zone.GRAVEYARD

    # small summon (ATK < 1000) -> Trap Hole can't be activated
    s2 = GameState.new(("A", "B"), seed=0)
    s2.turn_count, s2.turn_player = 2, 0
    small = s2.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # 800 ATK
    _set_card(s2, "Trap Hole", 1, 0)
    Engine(s2, [GreedyAgent(), ActivateByName("Trap Hole")])._response_window(
        {"kind": "summon", "player": 0, "monster": small.iid, "summon_kind": "normal"}
    )
    assert s2.inst(small.iid).zone is Zone.MONSTER


def test_full_chain_resolves_last_in_first_out():
    # P0 attacks; P1 chains Magic Cylinder; P0 chains MST onto the Cylinder.
    # LIFO: MST resolves first (destroys the Cylinder card), but the Cylinder's
    # already-activated effect still resolves -> 3000 reflected to P0.
    s, attacker = _battle_setup("Blue-Eyes White Dragon")  # 3000
    cylinder = _set_card(s, "Magic Cylinder", 1, 0)
    mst = s.create_instance(reg.get("Mystical Space Typhoon"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(mst.iid)

    eng = Engine(s, [ActivateByName("Mystical Space Typhoon"), ActivateByName("Magic Cylinder")])
    eng._declare_attack(DeclareAttack(attacker.iid, None), 0)

    assert s.players[0].life_points == 8000 - 3000  # Cylinder still reflected
    assert s.inst(cylinder.iid).zone is Zone.GRAVEYARD  # MST destroyed the Cylinder card
    assert s.inst(mst.iid).zone is Zone.GRAVEYARD  # spent Quick-Play to GY
    assert s.chain == []


# --------------------------------------------------------------------------- #
#  Integration: a full bot duel with traps must not crash the chain
# --------------------------------------------------------------------------- #
def test_bot_duel_with_traps_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=4,
    )
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)


def test_mst_can_target_either_players_spell_trap():
    # Web-contract regression: Mystical Space Typhoon must offer BOTH players'
    # Spell/Trap cards as targets (the board UI once only wired your own row).
    s = GameState.new(("You", "CPU"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    mst = s.create_instance(reg.get("Mystical Space Typhoon"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(mst.iid)
    mine = s.create_instance(reg.get("Mirror Force"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(mine.iid)
    s.place_spell_trap(mine.iid, 0, 0, Position.FACE_DOWN)
    mine.set_on_turn = 1
    foe = s.create_instance(reg.get("Trap Hole"), owner=1, zone=Zone.DECK)
    s.players[1].deck.append(foe.iid)
    s.place_spell_trap(foe.iid, 1, 0, Position.FACE_DOWN)
    foe.set_on_turn = 1

    tsets = legal_to_dict(s, 0, with_pass=True)["activatable"].get(str(mst.iid), [])
    assert [mine.iid] in tsets  # your own Set card
    assert [foe.iid] in tsets  # AND the opponent's
    action = match_intent(
        {"kind": "activate", "iid": mst.iid, "targets": [foe.iid]}, legal_actions(s, 0), s
    )
    assert action is not None and action.targets == (foe.iid,)
