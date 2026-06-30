"""Effects Batch 76: deck-impact toolbox.

Cyber-Stein pays 5000 LP to Special Summon a Fusion Monster from the Extra Deck
(``SpecialSummonFromExtraDeck``). Morphing Jar #2's Flip shuffles every field monster
into the Decks, then each player excavates until they reveal as many monsters as they
shuffled in, re-summoning the Level-4-or-lower ones face-down and dumping the rest
(``ShuffleFieldMonstersThenExcavate``). Limiter Removal doubles every Machine you
control, then the engine destroys those monsters in the End Phase
(``DoubleControlledRaceAtkThenEndPhaseDestroy`` + ``CardInstance.destroy_at_end_phase``).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _resolve(effect, s, controller, source_iid=-1, targets=()):
    ctx = EffectContext(
        state=s, controller=controller, source_iid=source_iid, targets=list(targets)
    )
    for prim in effect.resolve:
        prim.execute(ctx)


# ------------------------------------------------------------------- Cyber-Stein


def test_cyber_stein_pays_5000_and_summons_fusion_from_extra():
    s = _fresh(tp=ME)
    stein = _spawn(s, "Cyber-Stein", ME, 0)
    fusion = s.create_instance(reg.get("Aqua Dragon"), owner=ME, zone=Zone.EXTRA_DECK)
    s.players[ME].extra_deck.append(fusion.iid)
    s.players[ME].life_points = 8000
    eff = EFFECTS["Cyber-Stein"][0]
    assert eff.life_cost == 5000
    s.players[ME].life_points -= eff.life_cost  # pay the activation cost
    _resolve(eff, s, ME, stein.iid)
    assert fusion.zone is Zone.MONSTER
    assert fusion.controller == ME
    assert fusion.position is Position.FACE_UP_ATTACK
    assert s.players[ME].life_points == 3000


def test_cyber_stein_does_nothing_with_empty_extra_deck():
    s = _fresh(tp=ME)
    stein = _spawn(s, "Cyber-Stein", ME, 0)
    before = [i for i in s.players[ME].monster_zones if i is not None]
    _resolve(EFFECTS["Cyber-Stein"][0], s, ME, stein.iid)
    after = [i for i in s.players[ME].monster_zones if i is not None]
    assert after == before  # no Fusion to summon


# --------------------------------------------------------------- Morphing Jar #2


def test_morphing_jar_2_shuffles_and_reexcavates():
    s = _fresh(tp=ME)
    mj = _spawn(s, "Morphing Jar #2", ME, 0, pos=Position.FACE_UP_DEFENSE)  # L3
    foe = _spawn(s, "Gemini Elf", OPP, 0)  # L4
    # Both Decks empty -> the only card each excavates is the monster just shuffled in.
    _resolve(EFFECTS["Morphing Jar #2"][0], s, ME, mj.iid)
    assert mj.zone is Zone.MONSTER and mj.position is Position.FACE_DOWN_DEFENSE
    assert foe.zone is Zone.MONSTER and foe.position is Position.FACE_DOWN_DEFENSE
    assert s.players[ME].deck == [] and s.players[OPP].deck == []


def test_morphing_jar_2_sends_high_level_excavated_to_gy():
    s = _fresh(tp=ME)
    mj = _spawn(s, "Morphing Jar #2", ME, 0, pos=Position.FACE_UP_DEFENSE)  # L3 -> re-summoned
    boss = _spawn(s, "Summoned Skull", ME, 1)  # L6 -> too big, sent to GY
    _resolve(EFFECTS["Morphing Jar #2"][0], s, ME, mj.iid)
    assert mj.zone is Zone.MONSTER and mj.position is Position.FACE_DOWN_DEFENSE
    assert boss.zone is Zone.GRAVEYARD
    assert s.players[ME].deck == []


# --------------------------------------------------------------- Limiter Removal


def test_limiter_removal_doubles_machines_and_destroys_in_end_phase():
    s = _fresh(tp=ME)
    machine = _spawn(s, "Barrel Dragon", ME, 0)  # Machine, 2600 ATK
    other = _spawn(s, "Gemini Elf", ME, 1)  # Spellcaster, 1900 ATK (unaffected)
    _resolve(EFFECTS["Limiter Removal"][0], s, ME)
    assert s.effective_attack(machine.iid) == 5200  # doubled
    assert s.effective_attack(other.iid) == 1900  # unchanged
    # End Phase: the doubled Machine is destroyed; the non-Machine survives.
    s.phase = Phase.END
    Engine(s, [Agent(), Agent()])._end_phase(ME)
    assert machine.zone is Zone.GRAVEYARD
    assert other.zone is Zone.MONSTER
