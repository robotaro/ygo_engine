"""Effects Batch 79: deck-impact.

Dark Elf carries an ``AttackLifeCost`` rider — its controller must pay 1000 LP to
declare an attack with it (gated in the battle-phase enumeration, paid by the engine at
declaration). Nobleman of Crossout targets a face-down monster (new ``TargetSpec.face_down``
filter) and banishes it via ``BanishFaceDownThenDeckBanishIfFlip``, also banishing every
same-named card from both Main Decks when the monster was a Flip monster. Soul of Purity
and Light is a Nomi monster (banish 2 LIGHT from the GY to Special Summon) whose monster-borne
``FieldMod`` only bites during the opponent's Battle Phase (``only_opponent_battle_phase``).
"""

from __future__ import annotations

from ygo.agents import Agent, GreedyAgent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.effects import EffectContext
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import (
    ActivateSpell,
    DeclareAttack,
    NormalSummon,
    SetMonster,
    SpecialSummonFromHand,
    apply,
    legal_actions,
)
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME, phase=Phase.BATTLE):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _in_deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _resolve(prims, s, controller, targets):
    ctx = EffectContext(state=s, controller=controller, source_iid=-1, targets=list(targets))
    for prim in prims:
        prim.execute(ctx)


# ------------------------------------------------------------------------- Dark Elf


def test_dark_elf_attack_requires_1000_lp_in_enumeration():
    s = _fresh(tp=ME)
    elf = _spawn(s, "Dark Elf", ME, 0)  # opponent has no monsters -> direct attack
    s.players[ME].life_points = 8000
    assert any(isinstance(a, DeclareAttack) and a.attacker == elf.iid for a in legal_actions(s, ME))
    # At exactly the cost the attack cannot be paid (it would leave 0 LP).
    s.players[ME].life_points = 1000
    assert not any(isinstance(a, DeclareAttack) and a.attacker == elf.iid for a in legal_actions(s, ME))


def test_dark_elf_pays_1000_lp_when_it_attacks():
    s = _fresh(tp=ME)
    elf = _spawn(s, "Dark Elf", ME, 0)  # 2000 ATK, direct attack
    s.players[ME].life_points = 8000
    Engine(s, [Agent(), Agent()])._declare_attack(DeclareAttack(elf.iid, None), ME)
    assert s.players[ME].life_points == 7000  # paid the 1000 LP cost
    assert s.players[OPP].life_points == 6000  # took 2000 battle damage


def test_dark_elf_cost_suppressed_while_effect_negated():
    s = _fresh(tp=ME)
    elf = _spawn(s, "Dark Elf", ME, 0)
    drain = s.create_instance(reg.get("Skill Drain"), owner=ME, zone=Zone.HAND)  # negates monster effects
    s.players[ME].hand.append(drain.iid)
    s.place_spell_trap(drain.iid, ME, 0, Position.FACE_UP_ATTACK)
    assert s.monster_effects_negated(elf.iid)
    assert s.attack_life_cost(elf.iid) == 0  # the "pay to attack" effect is itself negated


def test_dark_elf_pays_its_cost_only_once_on_an_attack_replay():
    # Dark Elf attacks a face-down Blast Sphere, which equips itself to the attacker *before
    # damage* — the target leaves the field, so the attack fizzles into a replay. The replay
    # is legal (Dark Elf re-declares and hits directly), but it must NOT re-charge the 1000 LP:
    # the cost is paid once per attack, not once per declaration.
    s = _fresh(tp=ME)
    elf = _spawn(s, "Dark Elf", ME, 0)  # 2000 ATK
    _spawn(s, "Blast Sphere", OPP, 0, pos=Position.FACE_DOWN_DEFENSE)
    s.players[ME].life_points = 8000
    s.players[OPP].life_points = 8000
    Engine(s, [GreedyAgent(), GreedyAgent()])._battle_phase(ME)
    assert s.players[ME].life_points == 7000  # paid 1000 LP exactly once (the bug charged 2000)
    assert s.players[OPP].life_points == 6000  # the replay landed a 2000 direct hit
    assert s.inst(elf.iid).attacks_made_this_turn == 1  # exactly one completed attack


# ------------------------------------------------------------- Nobleman of Crossout


def test_nobleman_banishes_facedown_flip_and_all_deck_copies():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    target = _spawn(s, "Man-Eater Bug", OPP, 0, pos=Position.FACE_DOWN_DEFENSE)  # a Flip monster
    mine = [_in_deck(s, "Man-Eater Bug", ME) for _ in range(2)]
    theirs = [_in_deck(s, "Man-Eater Bug", OPP) for _ in range(1)]
    decoy = _in_deck(s, "Summoned Skull", ME)  # a different name -> untouched
    _resolve(EFFECTS["Nobleman of Crossout"][0].resolve, s, ME, [target.iid])
    assert target.zone is Zone.BANISHED
    assert all(c.zone is Zone.BANISHED for c in mine + theirs)
    assert decoy.zone is Zone.DECK
    assert decoy.iid in s.players[ME].deck


def test_nobleman_on_nonflip_leaves_the_decks_alone():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    target = _spawn(s, "Summoned Skull", OPP, 0, pos=Position.FACE_DOWN_DEFENSE)  # not a Flip monster
    deck_copy = _in_deck(s, "Summoned Skull", OPP)
    _resolve(EFFECTS["Nobleman of Crossout"][0].resolve, s, ME, [target.iid])
    assert target.zone is Zone.BANISHED
    assert deck_copy.zone is Zone.DECK  # no name-banish: it was not a Flip monster


def test_nobleman_only_targets_face_down_monsters():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    nob = _in_hand(s, "Nobleman of Crossout", ME)
    face_up = _spawn(s, "Summoned Skull", OPP, 0, pos=Position.FACE_UP_ATTACK)
    face_down = _spawn(s, "Man-Eater Bug", OPP, 1, pos=Position.FACE_DOWN_DEFENSE)
    targets = {
        a.targets[0]
        for a in legal_actions(s, ME)
        if isinstance(a, ActivateSpell) and a.iid == nob.iid
    }
    assert targets == {face_down.iid}
    assert face_up.iid not in targets


def test_nobleman_not_activatable_without_a_face_down_target():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    nob = _in_hand(s, "Nobleman of Crossout", ME)
    _spawn(s, "Summoned Skull", OPP, 0, pos=Position.FACE_UP_ATTACK)  # only a face-up monster
    assert not any(isinstance(a, ActivateSpell) and a.iid == nob.iid for a in legal_actions(s, ME))


# --------------------------------------------------------- Soul of Purity and Light


def test_soul_of_purity_cannot_be_normal_summoned():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    soul = _in_hand(s, "Soul of Purity and Light", ME)
    assert not reg.get("Soul of Purity and Light").can_normal_summon
    assert not any(
        isinstance(a, (NormalSummon, SetMonster)) and a.iid == soul.iid for a in legal_actions(s, ME)
    )


def test_soul_of_purity_summons_by_banishing_two_light():
    s = _fresh(tp=ME, phase=Phase.MAIN_1)
    soul = _in_hand(s, "Soul of Purity and Light", ME)

    def _ss(iid):
        return [a for a in legal_actions(s, ME) if isinstance(a, SpecialSummonFromHand) and a.iid == iid]

    assert _ss(soul.iid) == []  # empty GY
    light1 = _in_gy(s, "Mystical Elf", ME)
    assert _ss(soul.iid) == []  # only 1 LIGHT
    light2 = _in_gy(s, "Shining Angel", ME)
    assert _ss(soul.iid)  # 2 LIGHT -> payable
    apply(s, SpecialSummonFromHand(soul.iid))
    assert s.inst(soul.iid).zone is Zone.MONSTER
    assert s.inst(light1.iid).zone is Zone.BANISHED
    assert s.inst(light2.iid).zone is Zone.BANISHED


def test_soul_of_purity_debuffs_only_during_opponents_battle_phase():
    s = _fresh(tp=OPP, phase=Phase.BATTLE)
    _spawn(s, "Soul of Purity and Light", ME, 0)
    foe = _spawn(s, "Summoned Skull", OPP, 1)  # 2500 ATK
    # The opponent (OPP) is the turn player and it's the Battle Phase -> -300 applies.
    assert s.effective_attack(foe.iid) == 2200
    # My own monster is never debuffed (side="opponent").
    mine = _spawn(s, "Celtic Guardian", ME, 1)
    assert s.effective_attack(mine.iid) == reg.get("Celtic Guardian").attack


def test_soul_of_purity_debuff_is_dormant_off_opponents_battle_phase():
    s = _fresh(tp=OPP, phase=Phase.MAIN_1)
    _spawn(s, "Soul of Purity and Light", ME, 0)
    foe = _spawn(s, "Summoned Skull", OPP, 1)
    assert s.effective_attack(foe.iid) == 2500  # opponent's Main Phase, not Battle Phase
    s.phase = Phase.BATTLE
    s.turn_player = ME  # my Battle Phase -> still dormant (it's not THEIR Battle Phase)
    assert s.effective_attack(foe.iid) == 2500
