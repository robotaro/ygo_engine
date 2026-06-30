"""Effects Batch 74: deck-impact win conditions & toolbox flips.

Exodia the Forbidden One is a kernel-level alternate win condition — holding all five
"Forbidden One" pieces in hand wins the Duel (``GameState.exodia_winner`` /
``Engine._check_exodia``, re-checked after every draw / hand-add). Cyber Jar's Flip
wipes the board and floods both players from the top of their Decks
(``RevealTopSummonRestToHand``). Maha Vailo gains 500 ATK per Equip on it (SelfStatMod
``"equips_on_self"``). Time Wizard's once/turn coin toss either wipes the opponent's
monsters (right call) or backfires on your own with half-ATK burn (wrong call).
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


def _to_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _to_deck_top(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)  # end of list == top of deck
    return inst


def _equip(s, name, host, player, idx):
    eq = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(eq.iid)
    s.place_spell_trap(eq.iid, player, idx, Position.FACE_UP_ATTACK)
    eq.equipped_to = host.iid
    return eq


def _resolve(effect, s, controller, source_iid, targets=()):
    ctx = EffectContext(
        state=s, controller=controller, source_iid=source_iid, targets=list(targets)
    )
    for prim in effect.resolve:
        prim.execute(ctx)


class _Rng:
    """A coin that always lands the same way — CoinFlip only reads ``.random()``."""

    def __init__(self, val):
        self.val = val

    def random(self):
        return self.val


# --------------------------------------------------------------------- Exodia

_PIECES = [
    "Exodia the Forbidden One",
    "Right Arm of the Forbidden One",
    "Left Arm of the Forbidden One",
    "Right Leg of the Forbidden One",
    "Left Leg of the Forbidden One",
]


def test_exodia_winner_detects_full_hand():
    s = _fresh()
    for name in _PIECES:
        _to_hand(s, name, ME)
    assert s.exodia_winner() == ME


def test_exodia_four_pieces_is_no_win():
    s = _fresh()
    for name in _PIECES[:4]:
        _to_hand(s, name, ME)
    assert s.exodia_winner() is None


def test_engine_ends_duel_when_draw_completes_exodia():
    s = _fresh(tp=ME, phase=Phase.DRAW)
    for name in _PIECES[:4]:
        _to_hand(s, name, ME)
    _to_deck_top(s, _PIECES[4], ME)  # the fifth piece is the top draw
    eng = Engine(s, [Agent(), Agent()])
    eng._draw_phase(ME)
    assert eng.result is not None
    assert eng.result.winner == ME
    assert "Exodia" in eng.result.reason


# ------------------------------------------------------------------- Cyber Jar


def test_cyber_jar_flip_wipes_board_and_floods_from_deck():
    s = _fresh(tp=ME)
    jar = _spawn(s, "Cyber Jar", ME, 0, pos=Position.FACE_DOWN_DEFENSE)
    foe = _spawn(s, "Summoned Skull", OPP, 0)
    # Controller's top 5: three Level-4 monsters (Special Summoned), one Level-6 monster
    # and one Spell (both added to hand). The opponent's Deck is empty -> no flood there.
    _to_deck_top(s, "Celtic Guardian", ME)  # L4 -> summoned
    _to_deck_top(s, "Gemini Elf", ME)  # L4 -> summoned
    _to_deck_top(s, "Mystical Elf", ME)  # L4 -> summoned
    _to_deck_top(s, "Summoned Skull", ME)  # L6 -> to hand
    _to_deck_top(s, "Pot of Greed", ME)  # Spell -> to hand
    _resolve(EFFECTS["Cyber Jar"][0], s, ME, jar.iid)
    # The board is wiped first.
    assert jar.zone is Zone.GRAVEYARD and foe.zone is Zone.GRAVEYARD
    # The three Level-4 monsters are Special Summoned face-up.
    on_field = [i for i in s.players[ME].monster_zones if i is not None]
    assert len(on_field) == 3
    assert all(s.inst(i).position is Position.FACE_UP_ATTACK for i in on_field)
    # The Level-6 monster and the Spell go to the hand; the Deck is emptied.
    hand_names = {s.inst(i).card.name for i in s.players[ME].hand}
    assert "Summoned Skull" in hand_names and "Pot of Greed" in hand_names
    assert s.players[ME].deck == []


# ------------------------------------------------------------------- Maha Vailo


def test_maha_vailo_gains_500_per_equip():
    s = _fresh()
    maha = _spawn(s, "Maha Vailo", ME, 0)  # printed 1550 ATK
    assert s.effective_attack(maha.iid) == 1550
    _equip(s, "Axe of Despair", maha, ME, 0)  # +1000 (Axe) +500 (Maha's own)
    assert s.effective_attack(maha.iid) == 1550 + 1000 + 500
    _equip(s, "Axe of Despair", maha, ME, 1)  # a second Equip -> +1000 more, +500 more
    assert s.effective_attack(maha.iid) == 1550 + 2000 + 1000


# ------------------------------------------------------------------- Time Wizard


def test_time_wizard_right_call_wipes_opponent():
    s = _fresh(tp=ME)
    s.rng = _Rng(0.0)  # heads -> called it right
    tw = _spawn(s, "Time Wizard", ME, 0)
    mine = _spawn(s, "Celtic Guardian", ME, 1)
    foe1 = _spawn(s, "Summoned Skull", OPP, 0)
    foe2 = _spawn(s, "Gemini Elf", OPP, 1)
    _resolve(EFFECTS["Time Wizard"][0], s, ME, tw.iid)
    assert foe1.zone is Zone.GRAVEYARD and foe2.zone is Zone.GRAVEYARD
    assert tw.zone is Zone.MONSTER and mine.zone is Zone.MONSTER


def test_time_wizard_wrong_call_destroys_own_and_burns_half_atk():
    s = _fresh(tp=ME)
    s.rng = _Rng(0.9)  # tails -> called it wrong
    tw = _spawn(s, "Time Wizard", ME, 0)  # 500 ATK
    ally = _spawn(s, "Summoned Skull", ME, 1)  # 2500 ATK
    lp_before = s.players[ME].life_points
    _resolve(EFFECTS["Time Wizard"][0], s, ME, tw.iid)
    assert tw.zone is Zone.GRAVEYARD and ally.zone is Zone.GRAVEYARD
    # Half of the combined face-up ATK destroyed: (500 + 2500) // 2 = 1500.
    assert s.players[ME].life_points == lp_before - 1500
