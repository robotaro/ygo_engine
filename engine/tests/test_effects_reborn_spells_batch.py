"""Effects Batch 28: reborn-style Spell/Traps — Special Summon another monster
from a Graveyard.

These ride the existing ``SpecialSummonFromGraveyard`` primitive plus three new
engine knobs: ``Effect.life_cost`` (a Life-Point activation cost), the
``opponent_graveyard_monster`` target pool, and ``TargetSpec`` revival bounds
(``max_atk`` / ``normal_only`` / level), with a ``position`` arg on the primitive
for the Defense-Position summons. Cards: Premature Burial, Birthright, Silent Doom,
Soul Resurrection, Limit Reverse, O - Oversoul, Fossil Excavation, Autonomous
Action Unit.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, can_pay_costs, legal_actions, target_candidates
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _set_spell_trap(s, name, player):
    """Place a face-down Spell/Trap in the first free zone, ready to activate."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1  # Set last turn -> activatable now
    return inst


def _in_gy(s, name, player, *, face_up=True):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _activate(s, spell_iid, targets=()):
    Engine(s, [Agent(), Agent()])._activate_as_chain(
        ActivateSpell(spell_iid, targets=targets), 0
    )


# --- TargetSpec revival bounds -----------------------------------------------------
def test_birthright_targets_only_normal_monsters():
    s = _fresh()
    normal = _in_gy(s, "Mystical Elf", 0)  # a Normal (vanilla) monster
    _in_gy(s, "Breaker the Magical Warrior", 0)  # an Effect monster — excluded
    spec = reg.get("Birthright").effects[0].target
    assert target_candidates(s, 0, spec) == [normal.iid]


def test_limit_reverse_caps_attack_at_1000():
    s = _fresh()
    weak = _in_gy(s, "Mystical Elf", 0)  # 800 ATK — eligible
    _in_gy(s, "Summoned Skull", 0)  # 2500 ATK — too strong
    spec = reg.get("Limit Reverse").effects[0].target
    assert target_candidates(s, 0, spec) == [weak.iid]


def test_o_oversoul_targets_named_normal_hero():
    s = _fresh()
    hero = _in_gy(s, "Elemental HERO Clayman", 0)  # Normal "Elemental HERO"
    _in_gy(s, "Mystical Elf", 0)  # Normal, but not a HERO
    spec = reg.get("O - Oversoul").effects[0].target
    assert target_candidates(s, 0, spec) == [hero.iid]


# --- the life-point activation cost ------------------------------------------------
def test_premature_burial_pays_800_and_revives_linked():
    s = _fresh()
    skull = _in_gy(s, "Summoned Skull", 0)
    burial = _set_spell_trap(s, "Premature Burial", 0)
    before = s.players[0].life_points
    _activate(s, burial.iid, targets=(skull.iid,))
    assert s.players[0].life_points == before - 800  # the LP cost
    assert s.inst(skull.iid).zone is Zone.MONSTER
    assert s.inst(skull.iid).position is Position.FACE_UP_ATTACK
    # Equip Spell stays on the field, bonded to the revived monster both ways.
    assert s.inst(burial.iid).zone is Zone.SPELL_TRAP
    assert s.inst(burial.iid).linked_to == skull.iid
    assert s.inst(skull.iid).linked_to == burial.iid


def test_premature_burial_unaffordable_at_low_life():
    s = _fresh()
    _in_gy(s, "Summoned Skull", 0)
    burial = _set_spell_trap(s, "Premature Burial", 0)
    s.players[0].life_points = 800  # exactly the cost -> cannot pay (would hit 0)
    assert not can_pay_costs(s, 0, burial.iid, reg.get("Premature Burial").effects[0])
    s.players[0].life_points = 801
    assert can_pay_costs(s, 0, burial.iid, reg.get("Premature Burial").effects[0])


# --- Defense-Position revival ------------------------------------------------------
def test_silent_doom_revives_in_defense_and_spends():
    s = _fresh()
    elf = _in_gy(s, "Mystical Elf", 0)
    doom = _set_spell_trap(s, "Silent Doom", 0)
    _activate(s, doom.iid, targets=(elf.iid,))
    assert s.inst(elf.iid).zone is Zone.MONSTER
    assert s.inst(elf.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(doom.iid).zone is Zone.GRAVEYARD  # Normal Spell is spent


def test_soul_resurrection_revives_in_defense_and_stays():
    s = _fresh()
    elf = _in_gy(s, "Mystical Elf", 0)
    soul = _set_spell_trap(s, "Soul Resurrection", 0)
    _activate(s, soul.iid, targets=(elf.iid,))
    assert s.inst(elf.iid).position is Position.FACE_UP_DEFENSE
    assert s.inst(soul.iid).zone is Zone.SPELL_TRAP  # Continuous Trap stays, bonded
    assert s.inst(soul.iid).linked_to == elf.iid


# --- discard cost + race filter (Fossil Excavation) --------------------------------
def test_fossil_excavation_discards_and_revives_dinosaur():
    s = _fresh()
    dino = _in_gy(s, "Black Tyranno", 0)  # a Dinosaur
    fossil = _set_spell_trap(s, "Fossil Excavation", 0)
    fodder = s.create_instance(reg.get("Mystical Elf"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(fodder.iid)
    spec = reg.get("Fossil Excavation").effects[0].target
    assert target_candidates(s, 0, spec) == [dino.iid]
    _activate(s, fossil.iid, targets=(dino.iid,))
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the discard cost
    assert s.inst(dino.iid).zone is Zone.MONSTER


# --- stealing from the opponent's Graveyard (Autonomous Action Unit) ---------------
def test_autonomous_action_unit_steals_from_opponent_gy():
    s = _fresh()
    prey = _in_gy(s, "Summoned Skull", 1)  # opponent's GY
    _in_gy(s, "Mystical Elf", 0)  # own GY monster must NOT be eligible
    spec = reg.get("Autonomous Action Unit").effects[0].target
    assert target_candidates(s, 0, spec) == [prey.iid]
    unit = _set_spell_trap(s, "Autonomous Action Unit", 0)
    before = s.players[0].life_points
    _activate(s, unit.iid, targets=(prey.iid,))
    assert s.players[0].life_points == before - 1500
    assert s.inst(prey.iid).zone is Zone.MONSTER
    assert s.inst(prey.iid).controller == 0  # now on the activator's side


def test_revive_spells_are_offered_as_legal_actions():
    s = _fresh()
    _in_gy(s, "Mystical Elf", 0)
    doom = _set_spell_trap(s, "Silent Doom", 0)
    acts = [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == doom.iid]
    assert acts  # a valid GY target + a free zone -> activatable
