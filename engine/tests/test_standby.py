"""Slice 8 tests: the Standby-Phase upkeep hook — maintenance costs (Messenger of
Peace: pay 100 or be destroyed, plus an ATK>=1500 attack lock), per-Standby burn
(Burning Land, which also wipes Field Spells on activation), and a per-Standby
recovery on a *monster* (Cure Mermaid), proving the hook isn't tied to a card type.
"""

from __future__ import annotations

from ygo.agents import GreedyAgent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, DeclareAttack, apply, legal_actions
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _engine(s):
    return Engine(s, [GreedyAgent(), GreedyAgent()])


def _continuous_on_field(s, name, player=0):
    """Put a face-up Continuous Spell/Trap in ``player``'s Spell/Trap zone."""
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.DECK)
    s.players[player].deck.append(inst.iid)
    idx = s.first_empty_spell_trap_zone(player)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_UP_ATTACK)
    return inst


def _in_hand(s, name, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


def _attacks(s, player):
    return [a for a in legal_actions(s, player) if isinstance(a, DeclareAttack)]


# --------------------------------------------------------------------------- #
#  Messenger of Peace — pay-or-destroy maintenance cost
# --------------------------------------------------------------------------- #
def test_messenger_charges_100_during_controllers_standby():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    msg = _continuous_on_field(s, "Messenger of Peace", 0)

    _engine(s)._standby_phase(0)  # the controller's own Standby
    assert s.players[0].life_points == 8000 - 100
    assert s.inst(msg.iid).zone is Zone.SPELL_TRAP  # still on the field


def test_messenger_does_not_charge_on_opponents_standby():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 1  # the opponent's turn
    _continuous_on_field(s, "Messenger of Peace", 0)

    _engine(s)._standby_phase(1)
    assert s.players[0].life_points == 8000  # "your Standby Phases" only


def test_messenger_destroyed_when_owner_cannot_pay():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    s.players[0].life_points = 100  # cannot pay 100 without hitting 0
    msg = _continuous_on_field(s, "Messenger of Peace", 0)

    _engine(s)._standby_phase(0)
    assert s.players[0].life_points == 100  # nothing paid
    assert s.inst(msg.iid).zone is Zone.GRAVEYARD  # destroyed instead


# --------------------------------------------------------------------------- #
#  Messenger of Peace — the ATK >= 1500 attack lock
# --------------------------------------------------------------------------- #
def test_messenger_locks_out_strong_attackers_both_sides():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    weak = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # 800
    strong = s.spawn_on_field(reg.get("Summoned Skull"), 0, 1, Position.FACE_UP_ATTACK)  # 2500
    _continuous_on_field(s, "Messenger of Peace", 0)

    attackers = {a.attacker for a in _attacks(s, 0)}
    assert weak.iid in attackers  # 800 ATK can still swing
    assert strong.iid not in attackers  # 2500 ATK is locked out


def test_messenger_lock_uses_effective_attack():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.BATTLE
    elf = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)  # printed 800
    # Equip Axe of Despair (+1000) -> effective 1800, crossing the 1500 line.
    axe = _continuous_on_field(s, "Axe of Despair", 0)
    s.inst(axe.iid).equipped_to = elf.iid
    _continuous_on_field(s, "Messenger of Peace", 0)

    assert s.effective_attack(elf.iid) == 1800
    # Locked by *effective* ATK — a printed-800 check would wrongly let it swing.
    assert elf.iid not in {a.attacker for a in _attacks(s, 0)}


# --------------------------------------------------------------------------- #
#  Burning Land — activation wipes Field Spells; per-Standby burn hits the
#  active player on either turn
# --------------------------------------------------------------------------- #
def test_burning_land_activation_destroys_field_spells():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    my_field = _in_hand(s, "Sogen", 0)
    apply(s, ActivateSpell(my_field.iid, targets=()))
    foe_field = _in_hand(s, "Gaia Power", 1)
    s.place_field_spell(foe_field.iid, 1, Position.FACE_UP_ATTACK)

    burning = _in_hand(s, "Burning Land", 0)
    _engine(s)._activate_as_chain(ActivateSpell(burning.iid, targets=()), 0)

    assert s.inst(my_field.iid).zone is Zone.GRAVEYARD  # both Field Spells wiped
    assert s.inst(foe_field.iid).zone is Zone.GRAVEYARD
    assert s.inst(burning.iid).zone is Zone.SPELL_TRAP  # Burning Land itself stays


def test_burning_land_burns_the_active_player_each_standby():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count = 2
    _continuous_on_field(s, "Burning Land", 0)  # controlled by player 0

    s.turn_player = 0
    _engine(s)._standby_phase(0)
    assert s.players[0].life_points == 8000 - 500  # player 0's Standby hits player 0

    s.turn_player = 1
    _engine(s)._standby_phase(1)
    assert s.players[1].life_points == 8000 - 500  # player 1's Standby hits player 1 too


def test_burning_land_can_end_the_duel():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    s.players[0].life_points = 300
    _continuous_on_field(s, "Burning Land", 1)  # opponent controls it; still burns turn player

    eng = _engine(s)
    eng._standby_phase(0)
    assert s.players[0].life_points == 300 - 500
    assert eng.result is not None and eng.result.winner == 1


# --------------------------------------------------------------------------- #
#  Cure Mermaid — the same hook, on a monster
# --------------------------------------------------------------------------- #
def test_cure_mermaid_recovers_on_its_controllers_standby():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    s.players[0].life_points = 4000
    s.spawn_on_field(reg.get("Cure Mermaid"), 0, 0, Position.FACE_UP_ATTACK)

    _engine(s)._standby_phase(0)
    assert s.players[0].life_points == 4800  # +800

    s.turn_player = 1  # opponent's Standby — Mermaid only heals on "your" Standby
    _engine(s)._standby_phase(1)
    assert s.players[0].life_points == 4800


def test_face_down_card_skips_its_standby_upkeep():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    s.players[0].life_points = 4000
    mermaid = s.spawn_on_field(reg.get("Cure Mermaid"), 0, 0, Position.FACE_DOWN_DEFENSE)

    _engine(s)._standby_phase(0)
    assert s.players[0].life_points == 4000  # face-down: dormant
    assert s.inst(mermaid.iid).zone is Zone.MONSTER


# --------------------------------------------------------------------------- #
#  Integration: the Standby hook runs inside a real turn, and the decks load
# --------------------------------------------------------------------------- #
def test_standby_upkeep_fires_through_the_turn_loop():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player = 2, 0
    _continuous_on_field(s, "Messenger of Peace", 0)

    eng = _engine(s)
    eng._run_phase(Phase.STANDBY, 0)  # the dispatch path the turn loop uses
    assert s.players[0].life_points == 8000 - 100


def test_bot_duel_with_standby_cards_completes():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=5,
    )
    assert not duel.missing_report  # Messenger of Peace / Burning Land / Cure Mermaid resolve
    result = Engine(duel.state, [GreedyAgent(), GreedyAgent()], max_turns=300).run()
    assert result.winner in (0, 1, None)
