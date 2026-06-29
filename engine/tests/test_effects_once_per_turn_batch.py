"""Effects Batch 27: once-per-turn monster Ignition effects.

Effect.once_per_turn gates re-activation within a turn (the engine stamps
CardInstance.effect_activated_on_turn, read by moves._off_cooldown). Effect.
disables_attack_this_turn bars the source from attacking after it fires (stamps
attack_disabled_on_turn, read by attack enumeration). Cards: Neo-Spacian Air
Hummingbird (heal per opponent hand card), Cyber Gymnast (discard -> destroy a
face-up Attack monster), Volcanic Slicer / Super Conductor Tyranno (burn, then
can't attack)."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, DeclareAttack, legal_actions, target_candidates
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _monster_effects_for(s, iid):
    return [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect) and a.iid == iid]


# --- the once-per-turn gate ------------------------------------------------------
def test_once_per_turn_effect_is_offered_once_then_locked():
    s = _fresh()
    bird = s.spawn_on_field(reg.get("Neo-Spacian Air Hummingbird"), 0, 0, Position.FACE_UP_ATTACK)
    _in_hand(s, "Mystical Elf", 1)
    _in_hand(s, "Summoned Skull", 1)  # opponent holds 2 cards
    eng = Engine(s, [Agent(), Agent()])
    assert _monster_effects_for(s, bird.iid)  # available before use
    before = s.players[0].life_points
    eng._activate_monster_effect(ActivateMonsterEffect(bird.iid), 0)
    assert s.players[0].life_points == before + 1000  # 500 x 2 cards
    assert _monster_effects_for(s, bird.iid) == []  # locked for the rest of this turn


def test_once_per_turn_resets_on_a_new_turn():
    s = _fresh()
    bird = s.spawn_on_field(reg.get("Neo-Spacian Air Hummingbird"), 0, 0, Position.FACE_UP_ATTACK)
    _in_hand(s, "Mystical Elf", 1)
    Engine(s, [Agent(), Agent()])._activate_monster_effect(ActivateMonsterEffect(bird.iid), 0)
    assert _monster_effects_for(s, bird.iid) == []
    s.turn_count += 2  # back around to this player's next turn
    assert _monster_effects_for(s, bird.iid)  # available again


# --- Cyber Gymnast: discard cost + attack-position-filtered destroy ---------------
def test_cyber_gymnast_targets_only_face_up_attack_monsters():
    s = _fresh()
    s.spawn_on_field(reg.get("Cyber Gymnast"), 0, 0, Position.FACE_UP_ATTACK)
    atk = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_DEFENSE)  # not Attack
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 2, Position.FACE_DOWN_DEFENSE)  # not face-up
    spec = reg.get("Cyber Gymnast").effects[0].target
    assert target_candidates(s, 0, spec) == [atk.iid]


def test_cyber_gymnast_discards_and_destroys():
    s = _fresh()
    gym = s.spawn_on_field(reg.get("Cyber Gymnast"), 0, 0, Position.FACE_UP_ATTACK)
    fodder = _in_hand(s, "Mystical Elf", 0)
    prey = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(gym.iid, targets=(prey.iid,)), 0)
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the discard cost
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD  # destroyed


# --- the "can't attack this turn" rider ------------------------------------------
def test_volcanic_slicer_burns_then_cannot_attack():
    s = _fresh()
    slicer = s.spawn_on_field(reg.get("Volcanic Slicer"), 0, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    before = s.players[1].life_points
    eng._activate_monster_effect(ActivateMonsterEffect(slicer.iid), 0)
    assert s.players[1].life_points == before - 500
    s.phase = Phase.BATTLE
    attacks = [a for a in legal_actions(s, 0) if isinstance(a, DeclareAttack) and a.attacker == slicer.iid]
    assert attacks == []  # barred from attacking this turn


def test_super_conductor_tyranno_tributes_and_burns():
    s = _fresh()
    sct = s.spawn_on_field(reg.get("Super Conductor Tyranno"), 0, 0, Position.FACE_UP_ATTACK)
    fodder = s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    before = s.players[1].life_points
    eng._activate_monster_effect(ActivateMonsterEffect(sct.iid), 0)
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the Tribute cost
    assert s.players[1].life_points == before - 1000
    assert s.inst(sct.iid).attack_disabled_on_turn == s.turn_count
