"""Effects Batch 6: targeted / 'highest stat' monster removal Spells.
Smashing Ground (highest DEF the opponent controls), Hammer Shot (highest ATK
face-up Attack monster, either side), Soul Taker (destroy a face-up opponent
monster, then they gain 1000 LP)."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _cast(s, name, targets=(), player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    apply(s, ActivateSpell(inst.iid, targets=targets))


def test_smashing_ground_destroys_highest_def_opponent_monster():
    s = GameState.new(("A", "B"), seed=0)
    low = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # DEF 1200
    high = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)  # DEF 2000
    _cast(s, "Smashing Ground", player=0)
    assert s.inst(high.iid).zone is Zone.GRAVEYARD
    assert s.inst(low.iid).zone is Zone.MONSTER


def test_hammer_shot_destroys_highest_atk_attack_monster():
    s = GameState.new(("A", "B"), seed=0)
    mine = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # 800
    big = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # 2500
    _cast(s, "Hammer Shot", player=0)
    assert s.inst(big.iid).zone is Zone.GRAVEYARD  # highest ATK, regardless of side
    assert s.inst(mine.iid).zone is Zone.MONSTER


def test_hammer_shot_ignores_defense_position():
    s = GameState.new(("A", "B"), seed=0)
    defender = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_DEFENSE)
    attacker = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    _cast(s, "Hammer Shot", player=0)
    assert s.inst(defender.iid).zone is Zone.MONSTER  # not Attack Position
    assert s.inst(attacker.iid).zone is Zone.GRAVEYARD


def test_soul_taker_destroys_and_gifts_1000():
    s = GameState.new(("A", "B"), seed=0)
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    _cast(s, "Soul Taker", targets=(foe.iid,), player=0)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD
    assert s.players[1].life_points == 9000  # opponent gains 1000


def test_soul_taker_only_targets_face_up():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    face_down = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_DOWN_DEFENSE)
    st = s.create_instance(reg.get("Soul Taker"), 0, Zone.HAND)
    s.players[0].hand.append(st.iid)
    targets = {
        t for a in legal_actions(s, 0)
        if isinstance(a, ActivateSpell) and a.iid == st.iid for t in a.targets
    }
    assert face_down.iid not in targets  # can't target a face-down monster
