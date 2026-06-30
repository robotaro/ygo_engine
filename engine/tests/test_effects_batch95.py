"""Effects Batch 95: the Graveyard / discard punishers.

- Banisher of the Light: any card (either player's) sent to the Graveyard is banished
  instead. A floodgate replacement read by GameState.send_to_graveyard.
- Magical Thorn: when an opponent's card is discarded from their hand to the Graveyard,
  inflict 500 damage to that opponent for each card discarded.
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.effects import DiscardFromHand
from ygo.enums import Phase, Position, Zone
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


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


# ------------------------------------------------------------- Banisher of the Light


def test_banisher_redirects_send_to_graveyard():
    s = _fresh()
    _spawn(s, "Banisher of the Light", A, 0)
    victim = _in_hand(s, "7 Colored Fish", B)
    s.send_to_graveyard(victim.iid)
    assert victim.iid not in s.players[B].graveyard  # never reached the GY
    assert victim.iid in s.players[B].banished  # banished instead
    assert s.inst(victim.iid).zone is Zone.BANISHED


def test_banisher_redirects_a_battle_destruction():
    s = _fresh()
    _spawn(s, "Banisher of the Light", A, 0)
    mon = _spawn(s, "7 Colored Fish", B, 0)
    s.send_to_graveyard(mon.iid, by_battle=True)
    assert mon.iid in s.players[B].banished
    assert mon.iid not in s.players[B].graveyard
    assert not s.gy_from_field  # no "sent from field to GY" trigger queued


def test_banisher_off_field_restores_normal_graveyard():
    s = _fresh()
    banisher = _spawn(s, "Banisher of the Light", A, 0)
    s.send_to_graveyard(banisher.iid)  # the Banisher itself is banished while still live
    assert banisher.iid in s.players[A].banished
    # with no Banisher live, a fresh send goes to the GY as normal
    victim = _spawn(s, "7 Colored Fish", B, 0)
    s.send_to_graveyard(victim.iid)
    assert victim.iid in s.players[B].graveyard


def test_banisher_suppressed_face_down():
    s = _fresh()
    s.spawn_on_field(reg.get("Banisher of the Light"), A, 0, Position.FACE_DOWN_DEFENSE)
    victim = _spawn(s, "7 Colored Fish", B, 0)
    s.send_to_graveyard(victim.iid)
    assert victim.iid in s.players[B].graveyard  # face-down Banisher does nothing


# -------------------------------------------------------------------- Magical Thorn


def test_magical_thorn_burns_on_opponent_discard():
    s = _fresh()
    _faceup_st(s, "Magical Thorn", A)  # A's Thorn watches B's discards
    _in_hand(s, "7 Colored Fish", B)
    _in_hand(s, "Summoned Skull", B)
    s.players[B].life_points = 8000
    DiscardFromHand(player="self", count=2).execute(
        _ctx(s, controller=B)
    )
    assert s.players[B].life_points == 8000 - 2 * 500  # 500 per discarded card


def test_magical_thorn_ignores_controllers_own_discard():
    s = _fresh()
    _faceup_st(s, "Magical Thorn", A)  # A's Thorn only watches B
    _in_hand(s, "7 Colored Fish", A)
    s.players[A].life_points = 8000
    DiscardFromHand(player="self", count=1).execute(_ctx(s, controller=A))
    assert s.players[A].life_points == 8000  # A discarding its own card is not punished


def test_magical_thorn_quiet_when_no_discard_from_hand():
    s = _fresh()
    _faceup_st(s, "Magical Thorn", A)
    mon = _spawn(s, "7 Colored Fish", B, 0)
    s.players[B].life_points = 8000
    s.send_to_graveyard(mon.iid)  # a field card to the GY is not a discard
    assert s.players[B].life_points == 8000


def _ctx(s, controller):
    from ygo.effects import EffectContext

    return EffectContext(state=s, controller=controller, source_iid=None, targets=(), event=None)
