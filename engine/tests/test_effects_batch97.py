"""Effects Batch 97: a clean summon/attack/flip trio.

- Eatgaboon: a Normal Trap — when the opponent Normal/Flip Summons a monster with ATK
  500 or less, destroy it (a Trap-Hole variant with an upper ATK gate).
- The Stern Mystic: FLIP that reveals all face-down cards then returns them — a no-op on
  the board (the information reveal isn't modelled).
- Gravekeeper's Servant: a Continuous Spell — the opponent must send 1 card from the top
  of their Deck to the GY to declare an attack (and cannot attack if they can't pay).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, NormalSummon, Pass, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


class ActivateByName(Agent):
    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _fresh(tp=A, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _in_deck(s, name, player, n=1):
    last = None
    for _ in range(n):
        last = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(last.iid)
    return last


def _set_card(s, name, player, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = 1
    return inst


def _faceup_spell(s, name, player, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_UP_ATTACK)
    return inst


# ----------------------------------------------------------------------- Eatgaboon


def _summon_then_window(eng, s, iid, player=A):
    apply(s, NormalSummon(iid))
    eng._response_window(
        {"kind": "summon", "player": player, "monster": iid, "summon_kind": "normal"}
    )


def test_eatgaboon_destroys_weak_summon():
    s = _fresh()
    weak = _in_hand(s, "Petit Moth", A)  # 300 ATK <= 500
    _set_card(s, "Eatgaboon", B)
    eng = Engine(s, [Agent(), ActivateByName("Eatgaboon")])
    _summon_then_window(eng, s, weak.iid)
    assert s.inst(weak.iid).zone is Zone.GRAVEYARD  # destroyed by Eatgaboon


def test_eatgaboon_ignores_strong_summon():
    s = _fresh()
    strong = _in_hand(s, "7 Colored Fish", A)  # 1800 ATK > 500 -> no trigger
    _set_card(s, "Eatgaboon", B)
    eng = Engine(s, [Agent(), ActivateByName("Eatgaboon")])
    _summon_then_window(eng, s, strong.iid)
    assert s.inst(strong.iid).zone is Zone.MONSTER  # survives — too strong


# ------------------------------------------------------------------ The Stern Mystic


def test_stern_mystic_flip_is_a_noop_on_the_board():
    s = _fresh()
    mystic = _spawn(s, "The Stern Mystic", A, 0, Position.FACE_DOWN_DEFENSE)
    foe_set = _spawn(s, "Summoned Skull", B, 0, Position.FACE_DOWN_DEFENSE)
    effect = EFFECTS["The Stern Mystic"][0]
    assert effect.timing == "flip"
    from ygo.moves import resolve_effect

    resolve_effect(s, effect, mystic.iid)  # reveal-then-return nets nothing
    assert s.inst(foe_set.iid).position is Position.FACE_DOWN_DEFENSE  # unchanged
    assert s.inst(foe_set.iid).zone is Zone.MONSTER


def test_stern_mystic_counts_as_functional():
    from ygo.deckbuild import is_functional

    assert is_functional(reg.get("The Stern Mystic"))


# ------------------------------------------------------------- Gravekeeper's Servant


def test_servant_taxes_a_deck_card_per_attack():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    attacker = _spawn(s, "7 Colored Fish", A, 0)
    _in_deck(s, "Petit Moth", A, n=5)
    _faceup_spell(s, "Gravekeeper's Servant", B)  # B taxes A's attacks
    s.players[B].life_points = 8000
    before = len(s.players[A].deck)
    eng = Engine(s, [Agent(), Agent()])
    eng._declare_attack(DeclareAttack(attacker.iid, None), A)
    assert len(s.players[A].deck) == before - 1  # one card milled to attack


def test_servant_blocks_attack_with_empty_deck():
    s = _fresh(tp=A, phase=Phase.BATTLE)
    attacker = _spawn(s, "7 Colored Fish", A, 0)
    _faceup_spell(s, "Gravekeeper's Servant", B)
    s.players[A].deck.clear()  # nothing left to mill
    acts = [
        a for a in legal_actions(s, A) if isinstance(a, DeclareAttack) and a.attacker == attacker.iid
    ]
    assert not acts  # cannot pay the mill cost -> cannot declare an attack
