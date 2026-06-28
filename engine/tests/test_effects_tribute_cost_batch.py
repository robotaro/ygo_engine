"""Effects Batch 14: Tribute-cost activations (Tribute a monster to activate).

The cost is paid before the payload resolves, and is gated into legal enumeration
(no eligible monster -> the card can't be activated). The Tributed monster is
recorded on the source card so a dynamic value can read its printed stats.

Cards: Spiritual Fire Art - Kurenai (Tribute 1 FIRE; burn = its original ATK),
Icarus Attack (Tribute 1 Winged Beast; destroy 2 cards on the field), Burst
Breath (Tribute 1 Dragon; destroy all face-up monsters with DEF <= its ATK)."""

from __future__ import annotations

from ygo.agents import Agent, GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _set_trap(s, name, player=0, index=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = 1
    return inst


def _activatable(s, iid, player=0):
    return [a for a in legal_actions(s, player) if isinstance(a, ActivateSpell) and a.iid == iid]


# --- Spiritual Fire Art - Kurenai: Tribute 1 FIRE, burn = its original ATK ------
def test_spiritual_fire_art_burns_for_the_tributed_monsters_atk():
    s = GameState.new(("A", "B"), seed=0)
    fire = s.spawn_on_field(reg.get("Blazing Inpachi"), 0, 0, Position.FACE_UP_ATTACK)  # 1850 ATK
    trap = _set_trap(s, "Spiritual Fire Art - Kurenai", 0)
    apply(s, ActivateSpell(trap.iid))
    assert s.inst(fire.iid).zone is Zone.GRAVEYARD  # Tributed as the cost
    assert s.players[1].life_points == 8000 - 1850  # burn = the Tributed monster's ATK
    assert s.inst(trap.iid).zone is Zone.GRAVEYARD  # the spent Normal Trap


def test_spiritual_fire_art_needs_a_fire_monster_to_tribute():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)  # DARK, not FIRE
    trap = _set_trap(s, "Spiritual Fire Art - Kurenai", 0)
    assert _activatable(s, trap.iid) == []  # no FIRE monster -> can't pay the cost
    s.spawn_on_field(reg.get("Blazing Inpachi"), 0, 1, Position.FACE_UP_ATTACK)
    assert _activatable(s, trap.iid)  # now there is a FIRE monster to Tribute


# --- Icarus Attack: Tribute 1 Winged Beast, destroy 2 cards on the field --------
def test_icarus_attack_tributes_and_destroys_two_cards():
    s = GameState.new(("A", "B"), seed=0)
    bird = s.spawn_on_field(reg.get("Blue-Winged Crown"), 0, 0, Position.FACE_UP_ATTACK)  # Winged Beast
    victim_mon = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)
    victim_st = _set_trap(s, "Mirror Force", 1, 0)
    trap = _set_trap(s, "Icarus Attack", 0)
    apply(s, ActivateSpell(trap.iid, targets=(victim_mon.iid, victim_st.iid)))
    assert s.inst(bird.iid).zone is Zone.GRAVEYARD  # Tributed
    assert s.inst(victim_mon.iid).zone is Zone.GRAVEYARD  # both targets destroyed
    assert s.inst(victim_st.iid).zone is Zone.GRAVEYARD


def test_icarus_attack_needs_a_winged_beast():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)  # a card to target
    trap = _set_trap(s, "Icarus Attack", 0)
    assert _activatable(s, trap.iid) == []  # no Winged Beast to Tribute


# --- Burst Breath: Tribute 1 Dragon, destroy face-up monsters with DEF <= ATK ---
def test_burst_breath_destroys_monsters_within_the_def_threshold():
    s = GameState.new(("A", "B"), seed=0)
    dragon = s.spawn_on_field(reg.get("Luster Dragon"), 0, 0, Position.FACE_UP_ATTACK)  # 1900 ATK
    low = s.spawn_on_field(reg.get("Hitotsu-Me Giant"), 0, 1, Position.FACE_UP_ATTACK)  # DEF 1000
    on_edge = s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # DEF 1200
    survivor = s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_UP_ATTACK)  # DEF 2000
    facedown = s.spawn_on_field(reg.get("Hitotsu-Me Giant"), 1, 2, Position.FACE_DOWN_DEFENSE)
    trap = _set_trap(s, "Burst Breath", 0)
    apply(s, ActivateSpell(trap.iid))
    assert s.inst(dragon.iid).zone is Zone.GRAVEYARD  # Tributed as the cost
    assert s.inst(low.iid).zone is Zone.GRAVEYARD  # DEF 1000 <= 1900
    assert s.inst(on_edge.iid).zone is Zone.GRAVEYARD  # DEF 1200 <= 1900
    assert s.inst(survivor.iid).zone is Zone.MONSTER  # DEF 2000 > 1900 survives
    assert s.inst(facedown.iid).zone is Zone.MONSTER  # face-down is untouched


def test_burst_breath_needs_a_dragon():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    s.spawn_on_field(reg.get("Summoned Skull"), 0, 0, Position.FACE_UP_ATTACK)  # Fiend, not Dragon
    trap = _set_trap(s, "Burst Breath", 0)
    assert _activatable(s, trap.iid) == []


# --- the interactive engine path: the agent picks which monster to Tribute ------
def test_engine_pays_tribute_cost_via_agent_choice_and_records_it():
    s = GameState.new(("A", "B"), seed=0)
    weak = s.spawn_on_field(reg.get("Charcoal Inpachi"), 0, 0, Position.FACE_UP_ATTACK)  # FIRE, 100 ATK
    strong = s.spawn_on_field(reg.get("Blazing Inpachi"), 0, 1, Position.FACE_UP_ATTACK)  # FIRE, 1850
    trap = _set_trap(s, "Spiritual Fire Art - Kurenai", 0)
    eng = Engine(s, [GreedyAgent(), GreedyAgent()])
    effect = trap.card.effects[0]
    eng._pay_activation_cost(trap.iid, 0, effect)
    # The default agent Tributes the weakest FIRE monster (lowest ATK).
    assert s.inst(weak.iid).zone is Zone.GRAVEYARD
    assert s.inst(strong.iid).zone is Zone.MONSTER
    assert s.inst(trap.iid).tributed_iids == [weak.iid]  # recorded for the payload
