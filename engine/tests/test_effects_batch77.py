"""Effects Batch 77: deck-impact.

Dark Magician Girl gains 300 ATK per "Dark Magician"/"Magician of Black Chaos" in either
Graveyard (SelfStatMod ``named_in_graveyards``, exact-name match across both GYs). Giant
Germ, destroyed by battle, burns 500 and Special Summons its Deck copies (a battle
recruiter). The Unhappy Maiden, sent to the GY by battle, ends the Battle Phase
immediately (``fn_end_battle_phase`` sets ``state.battle_phase_ended``, read by the loop).
"""

from __future__ import annotations

from ygo.agents import Agent, RandomAgent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _to_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _to_deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _attack(s, attacker, target):
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(attacker, target), s.turn_player)


# --------------------------------------------------------------- Dark Magician Girl


def test_dark_magician_girl_gains_300_per_named_in_either_gy():
    s = _fresh()
    dmg = _spawn(s, "Dark Magician Girl", ME, 0)  # printed 2000 ATK
    assert s.effective_attack(dmg.iid) == 2000
    _to_gy(s, "Dark Magician", ME)  # one in your GY
    _to_gy(s, "Dark Magician", OPP)  # one in the opponent's GY -> both count
    assert s.effective_attack(dmg.iid) == 2000 + 600
    # A "Dark Magician Girl" in the GY must NOT count (exact-name match, not substring).
    _to_gy(s, "Dark Magician Girl", ME)
    assert s.effective_attack(dmg.iid) == 2000 + 600
    # "Magician of Black Chaos" counts as well.
    _to_gy(s, "Magician of Black Chaos", ME)
    assert s.effective_attack(dmg.iid) == 2000 + 900


# ------------------------------------------------------------------------ Giant Germ


def test_giant_germ_burns_and_summons_copies_on_battle_death():
    s = _fresh(tp=OPP)
    skull = _spawn(s, "Summoned Skull", OPP, 0)  # 2500 destroys the Germ
    germ = _spawn(s, "Giant Germ", ME, 0)  # 1000 ATK
    for _ in range(2):
        _to_deck(s, "Giant Germ", ME)
    lp_before = s.players[OPP].life_points
    _attack(s, skull.iid, germ.iid)
    assert germ.zone is Zone.GRAVEYARD
    assert s.players[OPP].life_points == lp_before - 500
    on_field = [i for i in s.players[ME].monster_zones if i is not None]
    assert len(on_field) == 2  # the two Deck copies, Special Summoned


# ------------------------------------------------------------------- Unhappy Maiden


def test_unhappy_maiden_ends_battle_phase_when_killed_by_battle():
    s = _fresh(tp=OPP)  # opponent's Battle Phase; they attack the Maiden
    raider = _spawn(s, "Summoned Skull", OPP, 0)  # 2500
    maiden = _spawn(s, "The Unhappy Maiden", ME, 0)  # 0 ATK -> destroyed
    assert s.battle_phase_ended is False
    _attack(s, raider.iid, maiden.iid)
    assert maiden.zone is Zone.GRAVEYARD
    assert s.battle_phase_ended is True


def test_unhappy_maiden_battle_phase_flag_resets_each_battle_phase():
    s = _fresh(tp=ME, phase=Phase.BATTLE)
    s.turn_count = 3  # not turn 1, so a Battle Phase actually runs
    s.battle_phase_ended = True  # stale from a previous turn
    # An empty board: the Battle-Phase loop opens, resets the flag, then Passes.
    Engine(s, [RandomAgent(seed=1), RandomAgent(seed=2)])._battle_phase(ME)
    assert s.battle_phase_ended is False
