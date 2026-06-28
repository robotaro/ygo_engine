"""Effects Batch 12: mass Spell/Trap destruction + Defense-position removal.

Heavy Storm (all Spell/Traps on the field), Harpie's Feather Duster (only the
opponent's), Shield Crush (destroy 1 Defense Position monster)."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _place_st(s, name, player, index, position=Position.FACE_UP_ATTACK):
    inst = _in_hand(s, name, player)
    s.place_spell_trap(inst.iid, player, index, position)
    return inst


def test_heavy_storm_destroys_every_spell_trap_on_the_field():
    s = GameState.new(("A", "B"), seed=0)
    mine = _place_st(s, "Messenger of Peace", 0, 0)
    theirs = _place_st(s, "Mirror Force", 1, 0, Position.FACE_DOWN)
    field = _in_hand(s, "Sogen", 1)
    s.place_field_spell(field.iid, 1, Position.FACE_UP_ATTACK)
    storm = _in_hand(s, "Heavy Storm")
    apply(s, ActivateSpell(storm.iid))
    assert s.inst(mine.iid).zone is Zone.GRAVEYARD
    assert s.inst(theirs.iid).zone is Zone.GRAVEYARD
    assert s.inst(field.iid).zone is Zone.GRAVEYARD  # the Field Spell zone too
    assert s.inst(storm.iid).zone is Zone.GRAVEYARD  # the spent spell itself


def test_harpies_feather_duster_destroys_only_opponents_spell_traps():
    s = GameState.new(("A", "B"), seed=0)
    mine = _place_st(s, "Messenger of Peace", 0, 0)
    theirs1 = _place_st(s, "Mirror Force", 1, 0, Position.FACE_DOWN)
    theirs2 = _place_st(s, "Solemn Wishes", 1, 1, Position.FACE_DOWN)
    duster = _in_hand(s, "Harpie's Feather Duster")
    apply(s, ActivateSpell(duster.iid))
    assert s.inst(theirs1.iid).zone is Zone.GRAVEYARD
    assert s.inst(theirs2.iid).zone is Zone.GRAVEYARD
    assert s.inst(mine.iid).zone is Zone.SPELL_TRAP  # your own side is untouched


def test_shield_crush_destroys_a_defense_position_monster():
    s = GameState.new(("A", "B"), seed=0)
    defender = s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_DEFENSE)
    crush = _in_hand(s, "Shield Crush")
    apply(s, ActivateSpell(crush.iid, targets=(defender.iid,)))
    assert s.inst(defender.iid).zone is Zone.GRAVEYARD


def test_shield_crush_cannot_target_an_attack_position_monster():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    attacker = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    facedown = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_DOWN_DEFENSE)
    crush = _in_hand(s, "Shield Crush")
    targets = {
        t for a in legal_actions(s, 0)
        if isinstance(a, ActivateSpell) and a.iid == crush.iid for t in a.targets
    }
    assert attacker.iid not in targets  # Attack Position is not a legal target
    assert facedown.iid in targets  # face-down Defense is
