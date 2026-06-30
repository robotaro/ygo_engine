"""Effects Batch 126: Two-Pronged Attack.

"Select and destroy 2 of your monsters and 1 of your opponent's." A Normal Trap: the player
targets the opponent's monster; the new DestroyOwnMonsters(2) primitive pays the self-
destruction (deterministic — lowest ATK first). Gated to need >=2 of your own and >=1 of the
opponent's monsters.
"""

from __future__ import annotations

from ygo.card_effects import EFFECTS, _can_two_pronged_attack
from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, A, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _place_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, s.first_empty_spell_trap_zone(player), Position.FACE_UP_ATTACK)
    return inst


def _resolve(s, name, controller, source_iid, targets):
    ctx = EffectContext(state=s, controller=controller, source_iid=source_iid, targets=targets)
    for prim in EFFECTS[name][0].resolve:
        prim.execute(ctx)


def test_destroys_two_lowest_own_and_the_targeted_opponent():
    s = _fresh()
    weak = _spawn(s, "Celtic Guardian", A, 0)  # 1400
    mid = _spawn(s, "Mystical Elf", A, 1)  # 800 — also low
    strong = _spawn(s, "Summoned Skull", A, 2)  # 2500 — should survive
    foe = _spawn(s, "Luster Dragon", B, 0)
    trap = _place_st(s, "Two-Pronged Attack", A)
    _resolve(s, "Two-Pronged Attack", A, trap.iid, [foe.iid])
    # The two lowest-ATK of A's monsters are destroyed; the strongest survives.
    assert strong.zone is Zone.MONSTER
    assert weak.zone is Zone.GRAVEYARD
    assert mid.zone is Zone.GRAVEYARD
    assert foe.zone is Zone.GRAVEYARD  # the targeted opponent monster


def test_condition_requires_two_own_and_one_opponent():
    s = _fresh()
    _spawn(s, "Celtic Guardian", A, 0)
    _spawn(s, "Summoned Skull", A, 1)
    assert _can_two_pronged_attack(s, A) is False  # opponent controls nothing
    _spawn(s, "Luster Dragon", B, 0)
    assert _can_two_pronged_attack(s, A) is True


def test_condition_false_with_only_one_own_monster():
    s = _fresh()
    _spawn(s, "Celtic Guardian", A, 0)
    _spawn(s, "Luster Dragon", B, 0)
    assert _can_two_pronged_attack(s, A) is False
