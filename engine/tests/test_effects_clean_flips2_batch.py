"""Effects Batch 62: more clean Flip effects (GY summon / GY->Deck / LP / count-burn).

Spirit Caller (SpecialSummonFromGraveyard, Normal Level<=3), Des Feral Imp
(ReturnFromGraveyardToDeck), Princess of Tsurugi (CountTimes over the new
"opponent_spell_trap" pool) and The Immortal of Thunder (GainLifePoints on flip + a
sent-to-GY InflictDamage). All on existing primitives.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, ME, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _to_gy(s, name, player=ME):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _set_st(s, name, player=OPP):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    return inst


def test_spirit_caller_revives_a_normal_level3():
    s = _fresh()
    caller = _spawn(s, "Spirit Caller", ME, 0)
    target = _to_gy(s, "Acid Crawler")  # vanilla Level 3 -> eligible
    _to_gy(s, "Summoned Skull")  # Level 6 vanilla -> too big
    _to_gy(s, "Man-Eater Bug")  # effect monster -> not Normal
    resolve_effect(s, EFFECTS["Spirit Caller"][0], caller.iid, (target.iid,), None)
    assert s.inst(target.iid).zone is Zone.MONSTER
    assert s.inst(target.iid).controller == ME


def test_des_feral_imp_shuffles_a_gy_card_into_deck():
    s = _fresh()
    imp = _spawn(s, "Des Feral Imp", ME, 0)
    card = _to_gy(s, "Pot of Greed")
    resolve_effect(s, EFFECTS["Des Feral Imp"][0], imp.iid, (), None)
    assert s.inst(card.iid).zone is Zone.DECK


def test_princess_of_tsurugi_burns_per_opponent_spell_trap():
    s = _fresh()
    princess = _spawn(s, "Princess of Tsurugi", ME, 0)
    _set_st(s, "Sakuretsu Armor")
    _set_st(s, "Trap Hole")
    resolve_effect(s, EFFECTS["Princess of Tsurugi"][0], princess.iid, (), None)
    assert s.players[OPP].life_points == 8000 - 2 * 500


def test_immortal_of_thunder_gains_then_loses():
    s = _fresh()
    thunder = _spawn(s, "The Immortal of Thunder", ME, 0)
    resolve_effect(s, EFFECTS["The Immortal of Thunder"][0], thunder.iid, (), None)
    assert s.players[ME].life_points == 8000 + 3000  # flip: +3000
    resolve_effect(s, EFFECTS["The Immortal of Thunder"][1], thunder.iid, (), None)
    assert s.players[ME].life_points == 8000 + 3000 - 5000  # sent to GY: -5000
