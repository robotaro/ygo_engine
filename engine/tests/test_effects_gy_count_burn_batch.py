"""Effects Batch 34: burn/gain scaling with a Graveyard count.

Extends ``CountTimes`` with an ``own_graveyard`` pool + optional ``card_filter`` (count
Spells / named monsters in your own GY) and adds the ``DiscardHandThenBurn`` primitive.
Cards: Magical Explosion (200 per Spell in your GY, only with an empty hand), Volcanic
Hammerer (200 per "Volcanic" monster in your GY, then can't attack), Cemetary Bomb (100
per card in the opponent's GY), Full Salvo (dump your hand, 200 per card sent).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, ActivateSpell, DeclareAttack, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _set_spell_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    # placed below; clear it from hand for the no-hand cards by popping after placement
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


def _activate(s, iid, targets=()):
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(iid, targets=targets), 0)


# --- Magical Explosion: 200 per Spell in your GY, empty hand only ------------------
def test_magical_explosion_burns_per_spell_in_gy():
    s = _fresh()
    me = _set_spell_trap(s, "Magical Explosion", 0)
    for _ in range(3):
        _in_gy(s, "Monster Reborn", 0)  # 3 Spells
    _in_gy(s, "Mystical Elf", 0)  # a monster -> not counted
    before = s.players[1].life_points
    _activate(s, me.iid)
    assert s.players[1].life_points == before - 600  # 200 x 3 Spells


def test_magical_explosion_requires_empty_hand():
    s = _fresh()
    me = _set_spell_trap(s, "Magical Explosion", 0)
    _in_gy(s, "Monster Reborn", 0)
    held = s.create_instance(reg.get("Mystical Elf"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(held.iid)  # a card in hand
    offered = [a for a in legal_actions(s, 0) if isinstance(a, ActivateSpell) and a.iid == me.iid]
    assert offered == []  # blocked while holding a card


# --- Volcanic Hammerer: 200 per Volcanic monster in your GY, then can't attack -----
def test_volcanic_hammerer_burns_and_then_cannot_attack():
    s = _fresh()
    ham = s.spawn_on_field(reg.get("Volcanic Hammerer"), 0, 0, Position.FACE_UP_ATTACK)
    _in_gy(s, "Volcanic Blaster", 0)
    _in_gy(s, "Volcanic Counter", 0)
    _in_gy(s, "Summoned Skull", 0)  # not Volcanic -> ignored
    before = s.players[1].life_points
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(ham.iid), 0)
    assert s.players[1].life_points == before - 400  # 200 x 2 Volcanic
    s.phase = Phase.BATTLE
    attacks = [a for a in legal_actions(s, 0) if isinstance(a, DeclareAttack) and a.attacker == ham.iid]
    assert attacks == []  # barred from attacking this turn
    s.phase = Phase.MAIN_1
    assert [a for a in legal_actions(s, 0) if isinstance(a, ActivateMonsterEffect) and a.iid == ham.iid] == []


# --- Cemetary Bomb: 100 per card in the OPPONENT's GY ------------------------------
def test_cemetary_bomb_burns_per_opponent_gy_card():
    s = _fresh()
    bomb = _set_spell_trap(s, "Cemetary Bomb", 0)
    for _ in range(5):
        _in_gy(s, "Mystical Elf", 1)  # opponent's GY
    _in_gy(s, "Mystical Elf", 0)  # own GY -> not counted
    before = s.players[1].life_points
    _activate(s, bomb.iid)
    assert s.players[1].life_points == before - 500  # 100 x 5


# --- Full Salvo: dump your hand, 200 per card sent ---------------------------------
def test_full_salvo_dumps_hand_and_burns():
    s = _fresh()
    salvo = _set_spell_trap(s, "Full Salvo", 0)
    hand = [_in_gy(s, "Mystical Elf", 0) for _ in range(2)]
    # move those two into the hand to act as the discard fodder
    for inst in hand:
        s.players[0].graveyard.remove(inst.iid)
        s.players[0].hand.append(inst.iid)
        inst.zone = Zone.HAND
    before = s.players[1].life_points
    _activate(s, salvo.iid)
    assert s.players[1].life_points == before - 400  # 200 x 2 cards sent
    assert s.players[0].hand == []  # whole hand dumped
    assert all(s.inst(h.iid).zone is Zone.GRAVEYARD for h in hand)
