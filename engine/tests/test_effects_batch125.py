"""Effects Batch 125: Sword of Dragon's Soul.

"Equip only to a Warrior monster. It gains 700 ATK. After damage calculation, if the equipped
monster battled a Dragon: destroy that monster at the end of the Battle Phase." The standard
Warrior-only equip (_equip_effect + EquipMod 700) plus the DestroysBattledDragon rider, which
the engine reads post-combat off the face-up Equip and drains when the Battle Phase ends.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _equip_sword(s, host, controller, idx=0):
    sword = s.create_instance(reg.get("Sword of Dragon's Soul"), owner=controller, zone=Zone.DECK)
    s.players[controller].deck.append(sword.iid)
    s.place_spell_trap(sword.iid, controller, idx, Position.FACE_UP_ATTACK)
    sword.equipped_to = host.iid
    return sword


def test_sword_grants_700_atk():
    s = _fresh()
    warrior = _spawn(s, "Obnoxious Celtic Guard", A, 0)  # 1400 ATK
    _equip_sword(s, warrior, A)
    assert s.effective_attack(warrior.iid) == 1400 + 700


def test_battled_dragon_that_survives_is_destroyed_at_end_of_battle_phase():
    s = _fresh()
    warrior = _spawn(s, "Obnoxious Celtic Guard", A, 0)  # 1400 + 700 = 2100 ATK
    _equip_sword(s, warrior, A)
    glider = _spawn(s, "Kaiser Glider", B, 0, Position.FACE_UP_DEFENSE)  # DEF 2200 — survives
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(warrior.iid, glider.iid), A)
    assert glider.zone is Zone.MONSTER  # survived combat (2100 ATK < 2200 DEF)
    assert glider.iid in s.destroy_at_battle_phase_end  # but it's queued
    eng._destroy_battled_dragons_at_end_of_battle_phase()
    assert glider.zone is Zone.GRAVEYARD
    assert s.destroy_at_battle_phase_end == set()


def test_dragon_destroyed_in_combat_is_not_requeued():
    s = _fresh()
    warrior = _spawn(s, "Obnoxious Celtic Guard", A, 0)  # 2100 ATK with the Sword
    _equip_sword(s, warrior, A)
    luster = _spawn(s, "Luster Dragon", B, 0, Position.FACE_UP_DEFENSE)  # DEF 1600 — dies in combat
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(warrior.iid, luster.iid), A)
    assert luster.zone is Zone.GRAVEYARD  # already destroyed by battle
    assert luster.iid not in s.destroy_at_battle_phase_end


def test_battling_a_non_dragon_does_not_queue_it():
    s = _fresh()
    warrior = _spawn(s, "Obnoxious Celtic Guard", A, 0)  # 2100 ATK with the Sword
    _equip_sword(s, warrior, A)
    wall = _spawn(s, "Labyrinth Wall", B, 0, Position.FACE_UP_DEFENSE)  # Rock 0/3000 — survives
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(warrior.iid, wall.iid), A)
    assert wall.zone is Zone.MONSTER
    assert s.destroy_at_battle_phase_end == set()  # not a Dragon -> not queued


def test_destroy_runs_through_the_real_battle_phase_loop():
    s = _fresh()
    warrior = _spawn(s, "Obnoxious Celtic Guard", A, 0)
    _equip_sword(s, warrior, A)
    glider = _spawn(s, "Kaiser Glider", B, 0, Position.FACE_UP_DEFENSE)

    class AttackThenPass(Agent):
        def decide(self, state, legal):
            atk = next((a for a in legal if isinstance(a, DeclareAttack) and a.attacker == warrior.iid), None)
            return atk if atk is not None else next(a for a in legal if type(a).__name__ == "Pass")

    eng = Engine(s, [AttackThenPass(), Agent()])
    eng._battle_phase(A)
    assert glider.zone is Zone.GRAVEYARD  # destroyed when the Battle Phase loop ended
