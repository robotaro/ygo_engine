"""Effects Batch 13: dynamic values — an effect amount derived from the board.

Count-based "... for each ..." burn/heal (Just Desserts, Restructer Revolution,
Secret Barrel, Cemetary Bomb, D.D. Dynamite, Gift of The Mystical Elf) via
CountTimes, and stat-based "equal to its ATK" Traps that read the attacking
monster (Enchanted Javelin, Draining Shield) via TargetAttack."""

from __future__ import annotations

from ygo.agents import Agent, GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, Pass, apply
from ygo.state import GameState

reg = CardRegistry.load_csv()


class ActivateByName(Agent):
    """Springs a named card whenever a response window allows it."""

    def __init__(self, name):
        self.name = name

    def decide(self, state, legal):
        return next((a for a in legal if isinstance(a, Pass)), legal[0])

    def respond(self, state, options, event):
        return next((o for o in options if state.inst(o.iid).card.name == self.name), None)


def _set_trap(s, name, player=0, index=0):
    """Put a Trap face-down on the field, ready to activate (atomic path)."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, player, index, Position.FACE_DOWN)
    inst.set_on_turn = 1
    return inst


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


# --- count-based burn ---------------------------------------------------------
def test_just_desserts_burns_500_per_opponent_monster():
    s = GameState.new(("A", "B"), seed=0)
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 1, Position.FACE_DOWN_DEFENSE)
    trap = _set_trap(s, "Just Desserts", 0)
    apply(s, ActivateSpell(trap.iid))
    assert s.players[1].life_points == 8000 - 1000  # 500 x 2 monsters (face-up + face-down)
    assert s.inst(trap.iid).zone is Zone.GRAVEYARD  # Normal Trap is spent


def test_just_desserts_does_nothing_with_no_opponent_monsters():
    s = GameState.new(("A", "B"), seed=0)
    trap = _set_trap(s, "Just Desserts", 0)
    apply(s, ActivateSpell(trap.iid))
    assert s.players[1].life_points == 8000  # 500 x 0


def test_restructer_revolution_burns_200_per_card_in_opponent_hand():
    s = GameState.new(("A", "B"), seed=0)
    for _ in range(3):
        _in_hand(s, "Mystical Elf", 1)
    spell = _in_hand(s, "Restructer Revolution", 0)
    apply(s, ActivateSpell(spell.iid))
    assert s.players[1].life_points == 8000 - 600  # 200 x 3 cards in hand


def test_secret_barrel_counts_opponent_hand_and_field():
    s = GameState.new(("A", "B"), seed=0)
    _in_hand(s, "Mystical Elf", 1)
    _in_hand(s, "Summoned Skull", 1)  # 2 in hand
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 0, Position.FACE_UP_ATTACK)  # 1 monster
    _set_trap(s, "Mirror Force", 1, 0)  # 1 Spell/Trap
    field = _in_hand(s, "Sogen", 1)
    s.place_field_spell(field.iid, 1, Position.FACE_UP_ATTACK)  # 1 Field Spell
    trap = _set_trap(s, "Secret Barrel", 0, 1)
    apply(s, ActivateSpell(trap.iid))
    assert s.players[1].life_points == 8000 - 1000  # 200 x (2 hand + 3 field)


def test_cemetary_bomb_burns_100_per_card_in_opponent_graveyard():
    s = GameState.new(("A", "B"), seed=0)
    for _ in range(4):
        _gy(s, "Mystical Elf", 1)
    trap = _set_trap(s, "Cemetary Bomb", 0)
    apply(s, ActivateSpell(trap.iid))
    assert s.players[1].life_points == 8000 - 400  # 100 x 4 in the Graveyard


def test_dd_dynamite_burns_300_per_opponent_banished_card():
    s = GameState.new(("A", "B"), seed=0)
    for i in range(3):
        m = s.spawn_on_field(reg.get("Mystical Elf"), 1, i, Position.FACE_UP_ATTACK)
        s.banish(m.iid)
    trap = _set_trap(s, "D.D. Dynamite", 0)
    apply(s, ActivateSpell(trap.iid))
    assert s.players[1].life_points == 8000 - 900  # 300 x 3 banished


# --- count-based heal ---------------------------------------------------------
def test_gift_of_the_mystical_elf_heals_300_per_monster_on_the_field():
    s = GameState.new(("A", "B"), seed=0)
    s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # yours
    s.spawn_on_field(reg.get("Summoned Skull"), 1, 0, Position.FACE_UP_ATTACK)  # theirs
    s.spawn_on_field(reg.get("Mystical Elf"), 1, 1, Position.FACE_DOWN_DEFENSE)  # theirs
    trap = _set_trap(s, "Gift of The Mystical Elf", 0)
    apply(s, ActivateSpell(trap.iid))
    assert s.players[0].life_points == 8000 + 900  # 300 x 3 monsters on the field (both sides)


# --- stat-based: equal to the attacking monster's ATK -------------------------
def test_enchanted_javelin_gains_lp_equal_to_target_atk():
    s = GameState.new(("A", "B"), seed=0)
    attacker = s.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 1, 0, Position.FACE_UP_ATTACK)
    trap = _set_trap(s, "Enchanted Javelin", 0)
    apply(s, ActivateSpell(trap.iid, targets=(attacker.iid,)))
    assert s.players[0].life_points == 8000 + 3000  # gain = the monster's ATK


def test_target_attack_reads_effective_atk_not_base():
    s = GameState.new(("A", "B"), seed=0)
    attacker = s.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 1, 0, Position.FACE_UP_ATTACK)
    attacker.temp_atk += 500  # a combat-trick boost still on the monster
    trap = _set_trap(s, "Enchanted Javelin", 0)
    apply(s, ActivateSpell(trap.iid, targets=(attacker.iid,)))
    assert s.players[0].life_points == 8000 + 3500  # 3000 base + 500 boost


def test_draining_shield_negates_attack_and_heals_by_attacker_atk():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    attacker = s.spawn_on_field(reg.get("Blue-Eyes White Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    inst = s.create_instance(reg.get("Draining Shield"), owner=1, zone=Zone.DECK)
    s.players[1].deck.append(inst.iid)
    s.place_spell_trap(inst.iid, 1, 0, Position.FACE_DOWN)
    inst.set_on_turn = 1
    eng = Engine(s, [GreedyAgent(), ActivateByName("Draining Shield")])
    eng._declare_attack(DeclareAttack(attacker.iid, None), 0)
    assert s.players[1].life_points == 8000 + 3000  # attack negated, healed by ATK
    assert s.chain == []
