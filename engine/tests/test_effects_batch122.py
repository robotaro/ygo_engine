"""Effects Batch 122: The Forgiving Maiden.

"Tribute this face-up card to return to your hand 1 of your monsters destroyed as a result
of battle during this turn." The self-Tribute reuses the send-to-GY cost idiom (Exiled
Force); the payload (ReturnOwnBattleDeadToHand) recovers a monster the new per-instance
battle-death turn stamp (state.died_on_turn) marks as a THIS-turn battle death, so an older
battle death or an effect destruction is never returned.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateMonsterEffect, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, A, Phase.MAIN_1
    return s


def _battle_dead(s, name, player):
    """Spawn ``name`` for ``player`` then send it to the GY as a battle death this turn."""
    inst = s.spawn_on_field(reg.get(name), player, 0, Position.FACE_UP_ATTACK)
    s.send_to_graveyard(inst.iid, by_battle=True)
    return inst


def test_send_to_graveyard_stamps_battle_death_turn():
    s = _fresh()
    mon = s.spawn_on_field(reg.get("Mystical Elf"), A, 0, Position.FACE_UP_ATTACK)
    s.send_to_graveyard(mon.iid, by_battle=True)
    assert s.inst(mon.iid).died_by_battle is True
    assert s.inst(mon.iid).died_on_turn == s.turn_count
    # A non-battle send (tribute / cost) leaves no battle-death turn stamp.
    other = s.spawn_on_field(reg.get("Mystical Elf"), A, 1, Position.FACE_UP_ATTACK)
    s.send_to_graveyard(other.iid)
    assert other.died_by_battle is False
    assert other.died_on_turn is None


def test_offered_and_returns_this_turn_battle_dead():
    s = _fresh()
    maiden = s.spawn_on_field(reg.get("The Forgiving Maiden"), A, 2, Position.FACE_UP_ATTACK)
    dead = _battle_dead(s, "Summoned Skull", A)
    actions = [a for a in legal_actions(s, A) if isinstance(a, ActivateMonsterEffect) and a.iid == maiden.iid]
    assert actions, "Forgiving Maiden's effect should be offered with a this-turn battle death in the GY"
    eng = Engine(s, [Agent(), Agent()])
    eng._activate_monster_effect(ActivateMonsterEffect(maiden.iid), A)
    assert s.inst(maiden.iid).zone is Zone.GRAVEYARD  # tributed as the cost
    assert s.inst(dead.iid).zone is Zone.HAND  # the battle-dead monster came back
    assert dead.iid in s.players[A].hand


def test_not_offered_without_a_battle_dead_monster():
    s = _fresh()
    maiden = s.spawn_on_field(reg.get("The Forgiving Maiden"), A, 2, Position.FACE_UP_ATTACK)
    actions = [a for a in legal_actions(s, A) if isinstance(a, ActivateMonsterEffect) and a.iid == maiden.iid]
    assert actions == []  # nothing died by battle this turn


def test_ignores_an_older_battle_death():
    s = _fresh()
    maiden = s.spawn_on_field(reg.get("The Forgiving Maiden"), A, 2, Position.FACE_UP_ATTACK)
    dead = _battle_dead(s, "Summoned Skull", A)  # stamped at turn 2
    s.turn_count = 4  # ...but it's now a later turn
    actions = [a for a in legal_actions(s, A) if isinstance(a, ActivateMonsterEffect) and a.iid == maiden.iid]
    assert actions == []
    assert s.inst(dead.iid).zone is Zone.GRAVEYARD  # stays put


def test_ignores_an_effect_destruction():
    s = _fresh()
    maiden = s.spawn_on_field(reg.get("The Forgiving Maiden"), A, 2, Position.FACE_UP_ATTACK)
    mon = s.spawn_on_field(reg.get("Summoned Skull"), A, 0, Position.FACE_UP_ATTACK)
    s.send_to_graveyard(mon.iid, by_effect=True)  # destroyed by an effect, not battle
    actions = [a for a in legal_actions(s, A) if isinstance(a, ActivateMonsterEffect) and a.iid == maiden.iid]
    assert actions == []
    assert s.inst(mon.iid).zone is Zone.GRAVEYARD
