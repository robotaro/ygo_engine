"""Effects Batch 72: deck-impact staples — Ring of Destruction, Card Destruction,
Dust Tornado.

Ring of Destruction (Normal Trap, opponent's turn): both players take damage equal to
the targeted opponent monster's ATK, then it is destroyed. Card Destruction: both
players discard their whole hand and draw that many. Dust Tornado: destroy 1 of the
opponent's Spell/Traps (via the new `opponent_spell_trap` target pool).
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.effects import EffectContext
from ygo.enums import Phase, Position, Zone
from ygo.moves import target_candidates
from ygo.state import GameState
from ygo.card_effects import EFFECTS

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.MAIN_1
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _spell(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, idx, pos)
    return inst


def _to_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _stock_deck(s, player, n, name="Celtic Guardian"):
    for _ in range(n):
        inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(inst.iid)


def _resolve(s, name, controller, targets=()):
    effect = EFFECTS[name][0]
    ctx = EffectContext(state=s, controller=controller, source_iid=-1, targets=list(targets))
    for prim in effect.resolve:
        prim.execute(ctx)
    return effect


# --------------------------------------------------------------------------- Ring


def test_ring_of_destruction_burns_both_by_atk_then_destroys():
    s = _fresh(tp=OPP)  # Ring is used on the opponent's turn
    skull = _spawn(s, "Summoned Skull", OPP, 0)  # 2500 ATK
    _resolve(s, "Ring of Destruction", ME, targets=[skull.iid])
    assert s.players[ME].life_points == 8000 - 2500
    assert s.players[OPP].life_points == 8000 - 2500
    assert skull.zone is Zone.GRAVEYARD


def test_ring_of_destruction_only_on_opponents_turn():
    cond = EFFECTS["Ring of Destruction"][0].condition
    s_opp_turn = _fresh(tp=OPP)
    s_my_turn = _fresh(tp=ME)
    assert cond(s_opp_turn, ME) is True  # opponent is turn player -> allowed
    assert cond(s_my_turn, ME) is False  # my own turn -> not allowed


# ------------------------------------------------------------------ Card Destruction


def test_card_destruction_both_discard_and_redraw_equal():
    s = _fresh(tp=ME)
    for _ in range(2):
        _to_hand(s, "Kuriboh", ME)
    for _ in range(3):
        _to_hand(s, "Kuriboh", OPP)
    _stock_deck(s, ME, 5)
    _stock_deck(s, OPP, 5)
    gy_me, gy_opp = len(s.players[ME].graveyard), len(s.players[OPP].graveyard)
    _resolve(s, "Card Destruction", ME)
    # Each player redrew exactly what they discarded.
    assert len(s.players[ME].hand) == 2
    assert len(s.players[OPP].hand) == 3
    assert len(s.players[ME].graveyard) == gy_me + 2
    assert len(s.players[OPP].graveyard) == gy_opp + 3
    assert len(s.players[ME].deck) == 3 and len(s.players[OPP].deck) == 2


def test_card_destruction_draw_capped_at_deck_size():
    s = _fresh(tp=ME)
    for _ in range(4):
        _to_hand(s, "Kuriboh", ME)
    _stock_deck(s, ME, 1)  # only 1 card to draw from
    _resolve(s, "Card Destruction", ME)
    assert len(s.players[ME].hand) == 1  # discarded 4, could only draw 1
    assert len(s.players[ME].deck) == 0


# --------------------------------------------------------------------- Dust Tornado


def test_dust_tornado_targets_only_opponent_spell_trap():
    s = _fresh(tp=ME)
    foe_st = _spell(s, "Messenger of Peace", OPP, 0)
    mine_st = _spell(s, "Messenger of Peace", ME, 0)
    spec = EFFECTS["Dust Tornado"][0].target
    cands = target_candidates(s, ME, spec)
    assert foe_st.iid in cands
    assert mine_st.iid not in cands


def test_dust_tornado_destroys_the_targeted_spell_trap():
    s = _fresh(tp=ME)
    foe_st = _spell(s, "Messenger of Peace", OPP, 0)
    _resolve(s, "Dust Tornado", ME, targets=[foe_st.iid])
    assert foe_st.zone is Zone.GRAVEYARD
