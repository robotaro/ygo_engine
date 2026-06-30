"""Effects Batch 91: utility + battle staples.

- Magical Mallet (Spell): shuffle your hand into the Deck and redraw the same number.
- Metalmorph (Trap, equip): +300 ATK/DEF, and when the equipped monster attacks it gains
  half its target's ATK during the Damage Step (the equip-sourced DamageStepBonus rider).
- Wall of Illusion (monster): when attacked, return the attacker to the hand. The engine's
  attacked-trigger fires before damage (the Blast Sphere seam), so the attacker is bounced
  and the attack fizzles — Wall survives and takes no damage (a documented, favorable
  divergence from the printed "after damage calculation").
- Panther Warrior (monster): cannot declare an attack unless you Tribute 1 other monster.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, _battle_phase_actions, resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_deck(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    return inst


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


# ------------------------------------------------------------------- Magical Mallet


def test_magical_mallet_reshuffles_and_redraws_the_hand():
    s = _fresh()
    mallet = _in_hand(s, "Magical Mallet", 0)
    s.players[0].hand.remove(mallet.iid)  # it's been activated -> out of the hand
    for n in ["Kuriboh", "Sangan", "Celtic Guardian"]:
        _in_hand(s, n, 0)
    for _ in range(10):
        _in_deck(s, "Mystical Elf", 0)
    hand_before, deck_before = len(s.players[0].hand), len(s.players[0].deck)
    resolve_effect(s, EFFECTS["Magical Mallet"][0], mallet.iid)
    assert len(s.players[0].hand) == hand_before  # shuffle 3 in, draw 3 -> size preserved
    assert len(s.players[0].deck) == deck_before  # net zero on the deck too


def test_magical_mallet_empty_hand_is_a_no_op():
    s = _fresh()
    mallet = _in_hand(s, "Magical Mallet", 0)
    s.players[0].hand.remove(mallet.iid)
    for _ in range(5):
        _in_deck(s, "Mystical Elf", 0)
    resolve_effect(s, EFFECTS["Magical Mallet"][0], mallet.iid)
    assert len(s.players[0].hand) == 0 and len(s.players[0].deck) == 5


# ----------------------------------------------------------------------- Metalmorph


def test_metalmorph_boosts_300_and_half_target_atk_on_attack():
    s = _fresh()
    host = _spawn(s, "Celtic Guardian", 0, 0)  # 1400 ATK
    metal = _faceup_st(s, "Metalmorph", 0)
    resolve_effect(s, EFFECTS["Metalmorph"][0], metal.iid, (host.iid,))
    assert s.inst(metal.iid).equipped_to == host.iid
    assert s.effective_attack(host.iid) == 1400 + 300  # the flat equip boost
    assert s.effective_defense(host.iid) == 1200 + 300
    foe = _spawn(s, "Summoned Skull", 1, 0)  # 2500 ATK target
    bonus = s.damage_step_bonus(host.iid, foe.iid, is_attacker=True, which="atk")
    assert bonus == 2500 // 2  # half the attack target's ATK, Damage Step only


def test_metalmorph_damage_bonus_only_when_attacking_a_monster():
    s = _fresh()
    host = _spawn(s, "Celtic Guardian", 0, 0)
    metal = _faceup_st(s, "Metalmorph", 0)
    resolve_effect(s, EFFECTS["Metalmorph"][0], metal.iid, (host.iid,))
    # Direct attack (no defender) and on defence -> no half-ATK bonus.
    assert s.damage_step_bonus(host.iid, None, is_attacker=True, which="atk") == 0
    foe = _spawn(s, "Summoned Skull", 1, 0)
    assert s.damage_step_bonus(host.iid, foe.iid, is_attacker=False, which="atk") == 0


def test_metalmorph_equip_bonus_survives_skill_drain():
    s = _fresh()
    host = _spawn(s, "Celtic Guardian", 0, 0)
    metal = _faceup_st(s, "Metalmorph", 0)
    resolve_effect(s, EFFECTS["Metalmorph"][0], metal.iid, (host.iid,))
    _faceup_st(s, "Skill Drain", 1)  # negates monster effects, NOT equips
    foe = _spawn(s, "Summoned Skull", 1, 0)
    assert s.effective_attack(host.iid) == 1400 + 300  # equip stat boost stands
    assert s.damage_step_bonus(host.iid, foe.iid, is_attacker=True, which="atk") == 2500 // 2


# ------------------------------------------------------------------- Wall of Illusion


def test_wall_of_illusion_bounces_the_attacker():
    s = _fresh(tp=B, phase=Phase.BATTLE)
    wall = _spawn(s, "Wall of Illusion", A, 0, Position.FACE_UP_DEFENSE)  # 1850 DEF
    attacker = _spawn(s, "Celtic Guardian", B, 0)  # 1400 ATK -> would lose to the wall
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(attacker.iid, wall.iid), B)
    assert s.inst(attacker.iid).zone is Zone.HAND  # the attacker is returned to the hand
    assert attacker.iid in s.players[B].hand
    assert s.inst(wall.iid).zone is Zone.MONSTER  # Wall survives (bounce pre-empts damage)


# -------------------------------------------------------------------- Panther Warrior


def test_panther_warrior_cannot_attack_with_no_tribute_fodder():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    panther = _spawn(s, "Panther Warrior", A, 0)  # the only monster -> nothing to Tribute
    _spawn(s, "Mystical Elf", B, 0)  # an opponent to attack
    actions = _battle_phase_actions(s, A)
    assert not any(isinstance(a, DeclareAttack) and a.attacker == panther.iid for a in actions)


def test_panther_warrior_can_attack_after_a_tribute():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    panther = _spawn(s, "Panther Warrior", A, 0)  # 2000 ATK
    fodder = _spawn(s, "Kuriboh", A, 1)  # the Tribute fodder (weakest)
    _spawn(s, "Mystical Elf", B, 0)
    actions = _battle_phase_actions(s, A)
    assert any(isinstance(a, DeclareAttack) and a.attacker == panther.iid for a in actions)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(panther.iid, None), A)  # direct-ish; pays the cost
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # the Tribute was paid
    assert s.inst(panther.iid).attacked_this_turn  # the attack went through
