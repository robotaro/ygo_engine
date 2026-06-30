"""Effects Batch 82: Blast Sphere (deck-impact target).

Blast Sphere is a face-down Defense Position Machine with a two-part effect:

  Part 1 (reactive, before damage calculation) — when an opponent's monster attacks it,
  it equips ITSELF to the attacking monster (a monster card becoming an Equip Card, the
  same move a Union monster makes). Because its target has left the monster zone, the
  attack fizzles. New engine hook ``Engine._fire_attacked_trigger`` fires a monster's own
  ``Trigger(kind="attacked", by=OPPONENT)`` before damage calc and re-checks the target;
  new primitive ``EquipSelfToAttacker`` does the equip (no-op when the controller has no
  free Spell/Trap Zone -> the monster battles normally).

  Part 2 (delayed) — on its controller's opponent's (= the attacker's) next Standby Phase
  it destroys the equipped monster and inflicts its ATK as damage. Modelled with a
  ``StandbyTrigger(whose="opponent", requires_equipped=True)`` (inert while Blast Sphere
  is still a face-up monster) firing the new ``DestroyEquipHostThenBurn`` primitive.
  Destroying the host orphans Blast Sphere, so it is cleaned to the GY and fires once.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1  # A controls Blast Sphere (the defender); B is the turn player (the attacker)


def _fresh(tp=B, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _attack(s, eng, attacker_iid, target_iid):
    eng._declare_attack(DeclareAttack(attacker_iid, target_iid), B)


# --------------------------------------------------------------- Part 1: equip on attack


def test_blast_sphere_equips_to_attacker_and_fizzles_the_attack():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    _attack(s, eng, attacker.iid, blast.iid)
    # Blast Sphere left the monster zone and is now an Equip on the attacker.
    assert blast.zone is Zone.SPELL_TRAP
    assert blast.equipped_to == attacker.iid
    # The attacker is unharmed and still on the field; the attack fizzled (no damage).
    assert attacker.zone is Zone.MONSTER
    assert s.players[A].life_points == 8000
    assert s.players[B].life_points == 8000


def test_blast_sphere_battles_normally_when_no_spell_trap_zone_is_free():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_DOWN_DEFENSE)  # DEF 1400
    # Fill every one of A's Spell/Trap Zones so the equip has nowhere to go.
    for i in range(len(s.players[A].spell_trap_zones)):
        f = s.create_instance(reg.get("Axe of Despair"), owner=A, zone=Zone.DECK)
        s.players[A].deck.append(f.iid)
        s.place_spell_trap(f.iid, A, i, Position.FACE_DOWN)
    eng = Engine(s, [Agent(), Agent()])
    _attack(s, eng, attacker.iid, blast.iid)
    # No equip happened; Blast Sphere was flipped and destroyed in battle.
    assert blast.equipped_to is None
    assert blast.zone is Zone.GRAVEYARD
    assert attacker.zone is Zone.MONSTER


# ----------------------------------------------------------- Part 2: delayed Standby kill


def test_blast_sphere_destroys_host_and_burns_on_the_attackers_standby():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    _attack(s, eng, attacker.iid, blast.iid)
    assert blast.equipped_to == attacker.iid
    # The attacker's controller (B) reaches their next Standby Phase.
    s.phase = Phase.STANDBY
    eng._standby_phase(B)
    assert attacker.zone is Zone.GRAVEYARD  # the equipped monster is destroyed
    assert s.players[B].life_points == 8000 - 2500  # burned for its ATK on the field
    assert blast.zone is Zone.GRAVEYARD  # orphaned equip -> GY (fires exactly once)


def test_blast_sphere_standby_is_inert_before_it_equips():
    s = _fresh(phase=Phase.STANDBY)
    # Face-UP (so it passes the standby scan's is-face-up filter) but not yet equipped.
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_UP_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    eng._standby_phase(B)
    assert blast.zone is Zone.MONSTER  # requires_equipped gate keeps the destroy inert
    assert s.players[A].life_points == 8000
    assert s.players[B].life_points == 8000


def test_blast_sphere_does_not_fire_on_its_controllers_own_standby():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    _attack(s, eng, attacker.iid, blast.iid)
    # On A's OWN Standby Phase the "opponent's Standby" effect must NOT fire.
    s.phase = Phase.STANDBY
    eng._standby_phase(A)
    assert attacker.zone is Zone.MONSTER  # host survives
    assert blast.equipped_to == attacker.iid  # still waiting for B's Standby
    assert s.players[B].life_points == 8000


def test_blast_sphere_equips_to_a_monster_you_own_if_the_opponent_attacks_with_it():
    # Blast Sphere equips to WHOEVER attacked it, regardless of who owns the attacker.
    # The only way the attacker is a card you own is if your opponent took control of it
    # (Brain Control / Snatch Steal) and swung with it — it still equips and is destroyed.
    s = _fresh()
    # A monster OWNED by A (the defender) but currently CONTROLLED by B (the attacker).
    stolen = s.spawn_on_field(reg.get("Summoned Skull"), B, 0, Position.FACE_UP_ATTACK, owner=A)
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    _attack(s, eng, stolen.iid, blast.iid)
    assert blast.equipped_to == stolen.iid  # equips to the attacker you own
    # On B's Standby Phase it destroys that monster and burns its current controller (B).
    s.phase = Phase.STANDBY
    eng._standby_phase(B)
    assert stolen.zone is Zone.GRAVEYARD
    assert s.players[stolen.owner].graveyard and stolen.iid in s.players[A].graveyard  # to A's GY
    assert s.players[B].life_points == 8000 - 2500  # the controller (B) takes the burn


def test_blast_sphere_burn_follows_control_of_the_equipped_monster():
    # GBA combo (Change of Heart / give-away): the explosion damages whoever CONTROLS the
    # equipped monster when it explodes — read at Standby resolution, not at equip time.
    # Push that monster to the other side first and the burn follows it there.
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)  # 2500 ATK, B's monster
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    _attack(s, eng, attacker.iid, blast.iid)
    assert blast.equipped_to == attacker.iid
    # Control of the about-to-explode monster is handed to A before the Standby Phase.
    idx = s.first_empty_monster_zone(A)
    s.move_control(attacker.iid, A, idx)
    assert attacker.controller == A
    s.phase = Phase.STANDBY
    eng._standby_phase(B)
    assert attacker.zone is Zone.GRAVEYARD          # still destroyed
    assert s.players[A].life_points == 8000 - 2500  # the NEW controller (A) eats the burn
    assert s.players[B].life_points == 8000          # the original controller is spared


def test_blast_sphere_is_discarded_if_the_host_leaves_before_the_standby():
    s = _fresh()
    attacker = _spawn(s, "Summoned Skull", B, 0)
    blast = _spawn(s, "Blast Sphere", A, 0, Position.FACE_DOWN_DEFENSE)
    eng = Engine(s, [Agent(), Agent()])
    _attack(s, eng, attacker.iid, blast.iid)
    # The host is destroyed by other means; Blast Sphere is orphaned and cleaned up.
    s.send_to_graveyard(attacker.iid)
    eng._check_field_to_gy_triggers()
    assert blast.zone is Zone.GRAVEYARD
    # A later opponent Standby Phase does nothing (no host, Blast Sphere gone).
    before = s.players[B].life_points
    s.phase = Phase.STANDBY
    eng._standby_phase(B)
    assert s.players[B].life_points == before
