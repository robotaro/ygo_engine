"""Slice 9 tests: take-control. Change of Heart borrows an opponent's monster
until the End Phase (the new delayed-revert timing primitive); Snatch Steal takes
control via an Equip (control reverts when the Equip leaves) and gifts its victim
1000 LP at each of their Standby Phases (reusing the Slice 8 Standby hook)."""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, apply, legal_actions
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


def _attacks(s, player):
    return [a for a in legal_actions(s, player) if isinstance(a, DeclareAttack)]


# --------------------------------------------------------------------------- #
#  Change of Heart — borrow until the End Phase
# --------------------------------------------------------------------------- #
def test_change_of_heart_moves_monster_to_your_side():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)

    apply(s, ActivateSpell(_in_hand(s, "Change of Heart", 0).iid, targets=(foe.iid,)))

    assert s.inst(foe.iid).controller == 0  # now on your side...
    assert foe.iid in s.players[0].monster_zones
    assert foe.iid not in s.players[1].monster_zones
    assert s.inst(foe.iid).owner == 1  # ...but still owned by the opponent
    assert s.inst(foe.iid).control_until_end_of_turn == 2


def test_change_of_heart_keeps_face_down_position():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Man-Eater Bug"), 1, 0, Position.FACE_DOWN_DEFENSE)
    apply(s, ActivateSpell(_in_hand(s, "Change of Heart", 0).iid, targets=(foe.iid,)))
    assert s.inst(foe.iid).controller == 0
    assert s.inst(foe.iid).position is Position.FACE_DOWN_DEFENSE  # regardless of position


def test_borrowed_monster_can_attack_this_turn():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # 2500
    apply(s, ActivateSpell(_in_hand(s, "Change of Heart", 0).iid, targets=(foe.iid,)))

    s.phase = Phase.BATTLE
    assert any(a.attacker == foe.iid for a in _attacks(s, 0))  # it can swing for you


def test_change_of_heart_reverts_at_end_phase():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    apply(s, ActivateSpell(_in_hand(s, "Change of Heart", 0).iid, targets=(foe.iid,)))
    assert s.inst(foe.iid).controller == 0

    _engine(s)._end_phase(0)
    assert s.inst(foe.iid).controller == 1  # returned to its owner
    assert foe.iid in s.players[1].monster_zones
    assert s.inst(foe.iid).control_reverts_to is None


def test_borrowed_monster_goes_to_gy_if_owner_field_is_full_at_revert():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    apply(s, ActivateSpell(_in_hand(s, "Change of Heart", 0).iid, targets=(foe.iid,)))
    # The opponent refills all five of their Monster Zones while you hold the loan.
    for i in range(5):
        s.spawn_on_field(reg.get("Mystical Elf"), 1, i, Position.FACE_UP_ATTACK)

    _engine(s)._end_phase(0)
    assert s.inst(foe.iid).zone is Zone.GRAVEYARD  # nowhere to return -> GY
    assert foe.iid in s.players[1].graveyard  # owner's Graveyard


def test_borrowed_monster_does_not_revert_on_a_later_turn():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    apply(s, ActivateSpell(_in_hand(s, "Change of Heart", 0).iid, targets=(foe.iid,)))

    s.turn_count = 3  # a different turn's End Phase must not end this loan
    _engine(s)._end_phase(1)
    assert s.inst(foe.iid).controller == 0


# --------------------------------------------------------------------------- #
#  Snatch Steal — Equip-based control + the Standby LP gift
# --------------------------------------------------------------------------- #
def test_snatch_steal_takes_control_and_equips():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    snatch = _in_hand(s, "Snatch Steal", 0)
    apply(s, ActivateSpell(snatch.iid, targets=(foe.iid,)))

    assert s.inst(foe.iid).controller == 0
    assert s.inst(snatch.iid).zone is Zone.SPELL_TRAP  # the Equip stays on the field
    assert s.inst(snatch.iid).equipped_to == foe.iid
    assert s.inst(foe.iid).control_equip_iid == snatch.iid
    assert s.effective_attack(foe.iid) == 2500  # no crash; Snatch Steal has no stat layer


def test_snatch_steal_control_reverts_when_equip_destroyed():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    snatch = _in_hand(s, "Snatch Steal", 0)
    eng = _engine(s)
    eng._activate_as_chain(ActivateSpell(snatch.iid, targets=(foe.iid,)), 0)
    assert s.inst(foe.iid).controller == 0

    # Blow up the Equip with Mystical Space Typhoon — control snaps back.
    apply(s, ActivateSpell(_in_hand(s, "Mystical Space Typhoon", 0).iid, targets=(snatch.iid,)))
    eng._check_field_to_gy_triggers()
    assert s.inst(snatch.iid).zone is Zone.GRAVEYARD
    assert s.inst(foe.iid).controller == 1  # back to its owner
    assert s.inst(foe.iid).control_equip_iid is None


def test_snatch_steal_equip_to_gy_if_monster_destroyed():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    snatch = _in_hand(s, "Snatch Steal", 0)
    eng = _engine(s)
    eng._activate_as_chain(ActivateSpell(snatch.iid, targets=(foe.iid,)), 0)

    s.send_to_graveyard(foe.iid)  # the snatched monster dies
    eng._check_field_to_gy_triggers()
    assert s.inst(snatch.iid).zone is Zone.GRAVEYARD  # orphaned Equip follows it


def test_snatch_steal_gifts_victim_1000_at_their_standby():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    foe = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    s.players[1].life_points = 5000
    eng = _engine(s)
    eng._activate_as_chain(ActivateSpell(_in_hand(s, "Snatch Steal", 0).iid, targets=(foe.iid,)), 0)

    eng._standby_phase(0)  # the snatcher's own Standby — no gift
    assert s.players[1].life_points == 5000
    eng._standby_phase(1)  # the victim's Standby — they gain 1000
    assert s.players[1].life_points == 6000


# --------------------------------------------------------------------------- #
#  Integration
# --------------------------------------------------------------------------- #
def test_bot_duel_with_take_control_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=5,
    )
    assert not duel.missing_report  # Change of Heart / Snatch Steal resolve
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
