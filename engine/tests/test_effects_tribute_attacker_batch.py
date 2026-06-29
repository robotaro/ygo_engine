"""Effects Batch 53: was-Tribute-Summoned gate (Blast Held by a Tribute).

New persistent CardInstance.was_tribute_summoned flag, stamped in moves._summon when a
Normal Summon paid 1+ tributes (reset by place_monster / on leaving the field, mirroring
was_special_summoned). A new Trigger.attacker_was_tribute_summoned gates an attack_declared
Trap on the declaring attacker carrying that flag.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, NormalSummon, apply, resolve_effect, response_options
from ygo.state import GameState

reg = CardRegistry.load_csv()

ATTACKER, DEFENDER = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ATTACKER, Phase.BATTLE
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _set_trap(s, name, player=DEFENDER):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _event(attacker_iid, target_iid=None):
    return {"kind": "attack_declared", "player": ATTACKER, "attacker": attacker_iid, "target": target_iid}


def _offered(s, trap_iid, event):
    return any(a.iid == trap_iid for a in response_options(s, DEFENDER, event, 2))


BLAST = EFFECTS["Blast Held by a Tribute"][0]


def test_tribute_summon_stamps_the_flag():
    s = _fresh()
    s.phase = Phase.MAIN_1
    fodder = _spawn(s, "Mystical Elf", ATTACKER, 0)
    skull = _hand(s, "Summoned Skull", ATTACKER)  # Level 6 -> needs 1 tribute
    apply(s, NormalSummon(skull.iid, tributes=(fodder.iid,)))
    assert s.inst(skull.iid).was_tribute_summoned
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD


def test_normal_summon_without_tribute_does_not_stamp():
    s = _fresh()
    s.phase = Phase.MAIN_1
    elf = _hand(s, "Celtic Guardian", ATTACKER)  # Level 4 -> no tribute
    apply(s, NormalSummon(elf.iid))
    assert not s.inst(elf.iid).was_tribute_summoned


def test_blast_held_offered_and_wipes_attackers_with_burn():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)
    atk.was_tribute_summoned = True  # it reached the field via a Tribute Summon
    other = _spawn(s, "Gemini Elf", ATTACKER, 1)  # a second ATK monster they control
    trap = _set_trap(s, "Blast Held by a Tribute")
    event = _event(atk.iid, None)
    assert _offered(s, trap.iid, event)
    resolve_effect(s, BLAST, trap.iid, (), event)
    assert s.inst(atk.iid).zone is Zone.GRAVEYARD
    assert s.inst(other.iid).zone is Zone.GRAVEYARD
    assert s.players[ATTACKER].life_points == 8000 - 1000


def test_blast_held_not_offered_against_a_non_tribute_attacker():
    s = _fresh()
    atk = _spawn(s, "Summoned Skull", ATTACKER, 0)  # was_tribute_summoned defaults False
    trap = _set_trap(s, "Blast Held by a Tribute")
    assert not _offered(s, trap.iid, _event(atk.iid, None))
