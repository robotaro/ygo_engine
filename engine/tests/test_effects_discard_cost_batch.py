"""Effects Batch 8: discard-cost activations (discard N cards to activate).

The cost is paid from the hand at activation, before the payload resolves, and is
gated into legal enumeration (no fodder -> the card can't be activated). Cards:
Tribute to the Doomed (destroy 1 monster), Lightning Vortex (destroy all face-up
opponent monsters), Raigeki Break (destroy 1 card on the field), Rising Energy
(+1500 ATK to a face-up monster until the End Phase)."""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _activatable(s, iid, player=0):
    return [a for a in legal_actions(s, player) if isinstance(a, ActivateSpell) and a.iid == iid]


# --- Tribute to the Doomed: discard 1, destroy 1 monster -----------------------
def test_tribute_to_the_doomed_discards_and_destroys():
    s = GameState.new(("A", "B"), seed=0)
    victim = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    fodder = _in_hand(s, "Mystical Elf")
    spell = _in_hand(s, "Tribute to the Doomed")
    apply(s, ActivateSpell(spell.iid, targets=(victim.iid,)))
    assert s.inst(victim.iid).zone is Zone.GRAVEYARD
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD  # paid as the discard cost
    assert s.inst(spell.iid).zone is Zone.GRAVEYARD  # the spent Normal Spell


def test_discard_cost_card_not_activatable_without_fodder():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    spell = _in_hand(s, "Tribute to the Doomed")  # the only card in hand -> no fodder
    assert _activatable(s, spell.iid) == []


def test_discard_cost_card_is_activatable_with_fodder():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    _in_hand(s, "Mystical Elf")  # fodder
    spell = _in_hand(s, "Tribute to the Doomed")
    assert _activatable(s, spell.iid)  # now it can pay the cost


# --- Lightning Vortex: discard 1, destroy all face-up opponent monsters ---------
def test_lightning_vortex_destroys_only_face_up_opponent_monsters():
    s = GameState.new(("A", "B"), seed=0)
    up = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    down = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_DOWN_DEFENSE)
    mine = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    fodder = _in_hand(s, "Mystical Elf")
    spell = _in_hand(s, "Lightning Vortex")
    apply(s, ActivateSpell(spell.iid))
    assert s.inst(up.iid).zone is Zone.GRAVEYARD
    assert s.inst(down.iid).zone is Zone.MONSTER  # face-down is untouched
    assert s.inst(mine.iid).zone is Zone.MONSTER  # your own monster is untouched
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD


# --- Raigeki Break: discard 1, destroy 1 card on the field (any card) -----------
def test_raigeki_break_can_destroy_a_spell_trap():
    s = GameState.new(("A", "B"), seed=0)
    foe_spell = _in_hand(s, "Messenger of Peace", player=1)
    s.place_spell_trap(foe_spell.iid, 1, 0, Position.FACE_UP_ATTACK)
    fodder = _in_hand(s, "Mystical Elf")
    trap = _in_hand(s, "Raigeki Break")
    apply(s, ActivateSpell(trap.iid, targets=(foe_spell.iid,)))
    assert s.inst(foe_spell.iid).zone is Zone.GRAVEYARD  # a Spell/Trap is a valid target
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD


# --- Rising Energy: discard 1, +1500 ATK to a face-up monster (temporary) -------
def test_rising_energy_pumps_a_face_up_monster_temporarily():
    s = GameState.new(("A", "B"), seed=0)
    mon = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # ATK 800
    fodder = _in_hand(s, "Summoned Skull")
    trap = _in_hand(s, "Rising Energy")
    apply(s, ActivateSpell(trap.iid, targets=(mon.iid,)))
    assert s.effective_attack(mon.iid) == 800 + 1500
    assert s.inst(fodder.iid).zone is Zone.GRAVEYARD


# --- the agent's discard heuristic ---------------------------------------------
def test_choose_discards_default_dumps_the_weakest():
    s = GameState.new(("A", "B"), seed=0)
    weak = _in_hand(s, "Mystical Elf")  # ATK 800
    strong = _in_hand(s, "Summoned Skull")  # ATK 2500
    assert Agent().choose_cost_fodder(s, 0, [weak.iid, strong.iid], 1, kind="discard") == (weak.iid,)
