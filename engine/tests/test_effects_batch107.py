"""Effects Batch 107: continuous ATK/DEF scaling by board/hand count.

- Machine King: +100 ATK per Machine-Type monster on the field (both sides, itself
  included) — reuses the existing "race_on_field" scaling mode.
- Muka Muka (+300) / Enraged Muka Muka (+400): gain ATK *and* DEF per card in your hand.
- Flash Assailant: LOSES 400 ATK and DEF per card in your hand (negative scale, floored
  at 0) — exercises the new "hand_size" scaling mode.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _give_hand(s, player, names):
    """Put fresh instances of ``names`` into ``player``'s hand; return their iids."""
    iids = []
    for name in names:
        inst = s.create_instance(reg.get(name), player, Zone.HAND)
        s.players[player].hand.append(inst.iid)
        iids.append(inst.iid)
    return iids


# ----------------------------------------------------------------- Machine King anthem


def test_machine_king_counts_itself():
    s = _fresh()
    mk = _spawn(s, "Machine King", A, 0)  # base 2200, +100 for itself (a Machine)
    assert s.effective_attack(mk.iid) == 2200 + 100
    assert s.effective_defense(mk.iid) == 2000  # DEF unaffected (scale_defn=0)


def test_machine_king_scales_with_machines_both_sides():
    s = _fresh()
    mk = _spawn(s, "Machine King", A, 0)
    _spawn(s, "Cyber Soldier", A, 1)  # a Machine on my side
    _spawn(s, "Roboyarou", B, 0)  # a Machine on the opponent's side counts too
    assert s.effective_attack(mk.iid) == 2200 + 100 * 3  # itself + 2 others


def test_machine_king_ignores_non_machines():
    s = _fresh()
    mk = _spawn(s, "Machine King", A, 0)
    _spawn(s, "Muka Muka", A, 1)  # a Rock — not a Machine
    assert s.effective_attack(mk.iid) == 2200 + 100  # still just itself


# ------------------------------------------------------------------ hand-size scaling


def test_muka_muka_scales_with_hand():
    s = _fresh()
    mm = _spawn(s, "Muka Muka", A, 0)  # base 600 / 300
    _give_hand(s, A, ["Kuriboh", "Kuriboh", "Kuriboh"])  # 3 cards in hand
    assert s.effective_attack(mm.iid) == 600 + 300 * 3
    assert s.effective_defense(mm.iid) == 300 + 300 * 3


def test_muka_muka_empty_hand_is_base():
    s = _fresh()
    mm = _spawn(s, "Muka Muka", A, 0)
    assert s.effective_attack(mm.iid) == 600
    assert s.effective_defense(mm.iid) == 300


def test_muka_muka_counts_only_its_controllers_hand():
    s = _fresh()
    mm = _spawn(s, "Muka Muka", A, 0)
    _give_hand(s, B, ["Kuriboh", "Kuriboh"])  # opponent's hand must not count
    assert s.effective_attack(mm.iid) == 600


def test_enraged_muka_muka_scales_400():
    s = _fresh()
    mm = _spawn(s, "Enraged Muka Muka", A, 0)  # base 1200 / 600
    _give_hand(s, A, ["Kuriboh", "Kuriboh"])
    assert s.effective_attack(mm.iid) == 1200 + 400 * 2
    assert s.effective_defense(mm.iid) == 600 + 400 * 2


def test_flash_assailant_loses_stats_per_hand_card():
    s = _fresh()
    fa = _spawn(s, "Flash Assailant", A, 0)  # base 2000 / 2000
    _give_hand(s, A, ["Kuriboh", "Kuriboh", "Kuriboh"])
    assert s.effective_attack(fa.iid) == 2000 - 400 * 3
    assert s.effective_defense(fa.iid) == 2000 - 400 * 3


def test_flash_assailant_floors_at_zero():
    s = _fresh()
    fa = _spawn(s, "Flash Assailant", A, 0)
    _give_hand(s, A, ["Kuriboh"] * 6)  # 2000 - 2400 = -400 -> floored to 0
    assert s.effective_attack(fa.iid) == 0
    assert s.effective_defense(fa.iid) == 0
