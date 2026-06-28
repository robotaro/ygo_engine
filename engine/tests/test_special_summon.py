"""Slice 6 tests: Special Summon from the Graveyard (Monster Reborn, Call of the
Haunted) — graveyard targeting, control change, and the linked-destruction bond."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.paths import DECKS_DIR
from ygo.serialize import legal_to_dict, match_intent
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _in_graveyard(state, name, player):
    inst = state.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    state.players[player].graveyard.append(inst.iid)
    return inst


def _in_hand(state, name, player=0):
    inst = state.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    state.players[player].hand.append(inst.iid)
    return inst


def _reborn_iids_offered(state, player):
    return {
        a.iid
        for a in legal_actions(state, player)
        if isinstance(a, ActivateSpell) and state.inst(a.iid).card.name == "Monster Reborn"
    }


# --------------------------------------------------------------------------- #
#  Monster Reborn
# --------------------------------------------------------------------------- #
def test_monster_reborn_revives_from_own_graveyard():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    skull = _in_graveyard(s, "Summoned Skull", 0)
    reborn = _in_hand(s, "Monster Reborn", 0)

    apply(s, ActivateSpell(reborn.iid, targets=(skull.iid,)))

    assert s.inst(skull.iid).zone is Zone.MONSTER
    assert s.inst(skull.iid).controller == 0
    assert s.inst(skull.iid).position is Position.FACE_UP_ATTACK
    assert skull.iid in s.players[0].monster_zones
    assert s.inst(reborn.iid).zone is Zone.GRAVEYARD  # Normal Spell spent


def test_monster_reborn_steals_from_opponent_graveyard():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    skull = _in_graveyard(s, "Summoned Skull", 1)  # in the OPPONENT's GY
    reborn = _in_hand(s, "Monster Reborn", 0)

    apply(s, ActivateSpell(reborn.iid, targets=(skull.iid,)))

    assert s.inst(skull.iid).controller == 0  # now under my control
    assert s.inst(skull.iid).owner == 1  # but still owned by the opponent
    assert skull.iid in s.players[0].monster_zones
    assert skull.iid not in s.players[1].graveyard


def test_monster_reborn_not_offered_with_empty_graveyard():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    reborn = _in_hand(s, "Monster Reborn", 0)
    assert reborn.iid not in _reborn_iids_offered(s, 0)  # no target -> not activatable

    _in_graveyard(s, "Battle Ox", 0)
    assert reborn.iid in _reborn_iids_offered(s, 0)  # now there's something to revive


def test_monster_reborn_blocked_when_monster_zones_full():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    _in_graveyard(s, "Summoned Skull", 0)
    reborn = _in_hand(s, "Monster Reborn", 0)
    filler = [s.spawn_on_field(reg.get("Battle Ox"), 0, i, Position.FACE_UP_ATTACK) for i in range(5)]

    assert reborn.iid not in _reborn_iids_offered(s, 0)  # nowhere to summon

    s.send_to_graveyard(filler[0].iid)  # free a zone
    assert reborn.iid in _reborn_iids_offered(s, 0)


# --------------------------------------------------------------------------- #
#  Call of the Haunted — revive + the two-way bond
# --------------------------------------------------------------------------- #
def _call_of_the_haunted_revives(seed=0):
    """Set up a duel where Call of the Haunted has just revived Summoned Skull."""
    s = GameState.new(("A", "B"), seed=seed)
    s.turn_count, s.turn_player, s.phase = 3, 0, Phase.MAIN_1
    skull = _in_graveyard(s, "Summoned Skull", 0)
    coth = s.create_instance(reg.get("Call Of The Haunted"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(coth.iid)
    s.place_spell_trap(coth.iid, 0, 0, Position.FACE_DOWN)
    coth.set_on_turn = 1  # Set on an earlier turn, so it may activate now

    engine = Engine(s, [GreedyAgent(), GreedyAgent()])
    engine._activate_as_chain(ActivateSpell(coth.iid, targets=(skull.iid,)), 0)
    return s, engine, coth, skull


def test_call_of_the_haunted_revives_and_bonds():
    s, _engine, coth, skull = _call_of_the_haunted_revives()
    assert s.inst(skull.iid).zone is Zone.MONSTER
    assert s.inst(skull.iid).controller == 0
    assert s.inst(coth.iid).zone is Zone.SPELL_TRAP  # Continuous Trap stays on the field
    assert s.inst(coth.iid).is_face_up
    assert s.inst(coth.iid).linked_to == skull.iid  # bonded both ways
    assert s.inst(skull.iid).linked_to == coth.iid


def test_destroying_call_of_the_haunted_destroys_the_monster():
    s, engine, coth, skull = _call_of_the_haunted_revives()
    s.send_to_graveyard(coth.iid)  # e.g. Mystical Space Typhoon hits the trap
    engine._check_field_to_gy_triggers()
    assert s.inst(skull.iid).zone is Zone.GRAVEYARD  # the revived monster follows


def test_revived_monster_leaving_destroys_call_of_the_haunted():
    s, engine, coth, skull = _call_of_the_haunted_revives()
    s.send_to_graveyard(skull.iid)  # e.g. destroyed in battle
    engine._check_field_to_gy_triggers()
    assert s.inst(coth.iid).zone is Zone.GRAVEYARD  # the trap is destroyed in turn


def test_call_of_the_haunted_revives_sangan_and_chains_its_trigger():
    # Reviving Sangan then losing it should still fire Sangan's "sent to GY" search.
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, 0, Phase.MAIN_1
    sangan = _in_graveyard(s, "Sangan", 0)
    elf = s.create_instance(reg.get("Mystical Elf"), owner=0, zone=Zone.DECK)  # 800 ATK -> searchable
    s.players[0].deck.append(elf.iid)
    coth = s.create_instance(reg.get("Call Of The Haunted"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(coth.iid)
    s.place_spell_trap(coth.iid, 0, 0, Position.FACE_DOWN)
    coth.set_on_turn = 1

    engine = Engine(s, [GreedyAgent(), GreedyAgent()])
    engine._activate_as_chain(ActivateSpell(coth.iid, targets=(sangan.iid,)), 0)
    assert s.inst(sangan.iid).zone is Zone.MONSTER

    s.send_to_graveyard(coth.iid)  # trap destroyed -> Sangan destroyed -> Sangan triggers
    engine._check_field_to_gy_triggers()
    assert s.inst(sangan.iid).zone is Zone.GRAVEYARD
    assert elf.iid in s.players[0].hand  # Sangan searched on the way out


# --------------------------------------------------------------------------- #
#  Integration: a full bot duel with the revival cards in both decks
# --------------------------------------------------------------------------- #
def test_bot_duel_with_revival_cards_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=11,
    )
    s = duel.state
    for pl in (0, 1):
        for name in ("Monster Reborn", "Call Of The Haunted", "Call Of The Haunted"):
            inst = s.create_instance(reg.get(name), owner=pl, zone=Zone.DECK)
            s.players[pl].deck.append(inst.iid)
        s.shuffle_deck(pl)

    result = Engine(s, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)


# --------------------------------------------------------------------------- #
#  Web contract: the client sees GY-target activations and they round-trip
# --------------------------------------------------------------------------- #
def test_web_contract_monster_reborn_targets_graveyard():
    s = GameState.new(("You", "CPU"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    skull = _in_graveyard(s, "Summoned Skull", 0)
    reborn = _in_hand(s, "Monster Reborn", 0)

    legal = legal_to_dict(s, 0, with_pass=True)
    assert [skull.iid] in legal["activatable"].get(str(reborn.iid), [])

    action = match_intent(
        {"kind": "activate", "iid": reborn.iid, "targets": [skull.iid]},
        legal_actions(s, 0),
        s,
    )
    assert isinstance(action, ActivateSpell) and action.targets == (skull.iid,)


def test_web_contract_set_call_of_the_haunted_is_activatable():
    s = GameState.new(("You", "CPU"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, 0, Phase.MAIN_1
    skull = _in_graveyard(s, "Summoned Skull", 0)
    coth = s.create_instance(reg.get("Call Of The Haunted"), owner=0, zone=Zone.DECK)
    s.players[0].deck.append(coth.iid)
    s.place_spell_trap(coth.iid, 0, 0, Position.FACE_DOWN)
    coth.set_on_turn = 1

    legal = legal_to_dict(s, 0, with_pass=True)
    assert [skull.iid] in legal["activatable"].get(str(coth.iid), [])  # a Set trap, clickable
