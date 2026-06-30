"""Effects Batch 87: "when you draw" draw-again engines (TIMING_DRAW).

state.draw now records WHICH cards each draw event produced (pending_draws holds
(player, drawn_iids)). After every draw, engine._fire_draw_again_triggers draws 1 more
card for each face-up DrawAgainOnDraw the drawer controls whose filter a just-drawn card
matches. The extra draw is a fresh event, so a run of matches chains (bounded by the deck).

- Heart of the Underdog (Continuous Spell): "During your Draw Phase, when you draw a Normal
  Monster(s): draw 1 more card." Draw-Phase-only, vanilla monsters.
- Tethys, Goddess of Light (Fairy/Effect monster): "When you draw a Fairy monster(s): draw
  1 card." Any phase, but must be face-up on the field.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _draw_state(tp=0, phase=Phase.DRAW):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _faceup_st(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _stack_deck(s, player, names_top_first):
    """Put cards on the deck so ``names_top_first[0]`` is the next card drawn."""
    for name in reversed(names_top_first):
        c = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
        s.players[player].deck.append(c.iid)


def _process_one_draw(s, player):
    eng = Engine(s, [Agent(), Agent()])
    s.draw(player, 1)
    eng._process_draw_triggers()


def _gained(s, player, before):
    return [s.inst(i).name for i in s.players[player].hand[before:]]


# ----------------------------------------------------------- Heart of the Underdog


def test_heart_draws_one_more_on_a_normal_monster():
    s = _draw_state()
    _faceup_st(s, "Heart of the Underdog", 0)
    _stack_deck(s, 0, ["Celtic Guardian", "Sangan"])  # Normal, then Effect (stops the chain)
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Celtic Guardian", "Sangan"]


def test_heart_chains_through_consecutive_normals():
    s = _draw_state()
    _faceup_st(s, "Heart of the Underdog", 0)
    _stack_deck(s, 0, ["Celtic Guardian", "Mystical Elf", "Sangan"])  # Normal, Normal, Effect
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Celtic Guardian", "Mystical Elf", "Sangan"]  # 1 -> +2


def test_heart_does_not_fire_outside_the_draw_phase():
    s = _draw_state(phase=Phase.MAIN_1)
    _faceup_st(s, "Heart of the Underdog", 0)
    _stack_deck(s, 0, ["Celtic Guardian", "Mystical Elf"])
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Celtic Guardian"]  # Draw-Phase-only, no bonus


def test_heart_does_not_fire_on_a_non_normal_draw():
    s = _draw_state()
    _faceup_st(s, "Heart of the Underdog", 0)
    _stack_deck(s, 0, ["Sangan", "Celtic Guardian"])  # an Effect monster on top
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Sangan"]  # not a Normal Monster -> no extra draw


# ------------------------------------------------------ Tethys, Goddess of Light


def test_tethys_draws_one_more_on_a_fairy():
    s = _draw_state(phase=Phase.MAIN_1)  # any phase
    _spawn(s, "Tethys, Goddess of Light", 0, 0)
    _stack_deck(s, 0, ["Dunames Dark Witch", "Sangan"])  # Fairy, then non-Fairy
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Dunames Dark Witch", "Sangan"]


def test_tethys_does_not_fire_on_a_non_fairy_draw():
    s = _draw_state(phase=Phase.MAIN_1)
    _spawn(s, "Tethys, Goddess of Light", 0, 0)
    _stack_deck(s, 0, ["Celtic Guardian", "Dunames Dark Witch"])  # a Warrior on top
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Celtic Guardian"]


def test_tethys_inert_off_the_field():
    s = _draw_state(phase=Phase.MAIN_1)
    t = s.create_instance(reg.get("Tethys, Goddess of Light"), owner=0, zone=Zone.HAND)
    s.players[0].hand.append(t.iid)  # in hand, not on the field
    _stack_deck(s, 0, ["Dunames Dark Witch", "Sangan"])
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Dunames Dark Witch"]  # no extra — Tethys must be face-up


def test_tethys_inert_under_skill_drain():
    s = _draw_state(phase=Phase.MAIN_1)
    _spawn(s, "Tethys, Goddess of Light", 0, 0)
    _faceup_st(s, "Skill Drain", 1)  # negates all face-up monster effects
    _stack_deck(s, 0, ["Dunames Dark Witch", "Sangan"])
    before = len(s.players[0].hand)
    _process_one_draw(s, 0)
    assert _gained(s, 0, before) == ["Dunames Dark Witch"]  # Tethys negated -> no extra
