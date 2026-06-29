"""Effects Batch 65: Standby-Phase effects (StandbyTrigger).

The Standby hook (engine._standby_phase) used to handle only fixed-LP maintenance
(StandbyUpkeep). The new StandbyTrigger continuous marker fires a *full* Effect on a
fresh Chain during a qualifying Standby Phase — scoped by `whose` (controller's own
Standby / the opponent's) and the source's battle position, and suppressed while the
source's effects are negated (Skill Drain on a monster). Authored: Bowganian (burn 600),
Ebon Magician Curran (burn 300 x opponent's monsters), Dancing Fairy (+1000 LP in
Defense), Spirit of the Breeze (+1000 LP in Attack), Destiny HERO - Defender (opponent
draws 1, in Defense), Lava Golem (controller takes 1000), Minor Goblin Official
(Continuous Trap, burn 500 during the opponent's Standby).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()

ME, OPP = 0, 1


def _fresh(tp=ME):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, Phase.STANDBY
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _trap(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    s.place_spell_trap(inst.iid, player, idx, pos)
    return inst


def _standby(s, tp):
    Engine(s, [Agent(), Agent()])._standby_phase(tp)


def test_bowganian_burns_opponent_only_on_your_standby():
    s = _fresh(tp=ME)
    _spawn(s, "Bowganian", ME, 0)
    _standby(s, ME)
    assert s.players[OPP].life_points == 8000 - 600
    # whose="controller": nothing happens on the opponent's Standby Phase.
    s2 = _fresh(tp=OPP)
    _spawn(s2, "Bowganian", ME, 0)
    _standby(s2, OPP)
    assert s2.players[OPP].life_points == 8000


def test_ebon_curran_scales_with_opponent_monster_count():
    s = _fresh(tp=ME)
    _spawn(s, "Ebon Magician Curran", ME, 0)
    _spawn(s, "Celtic Guardian", OPP, 0)
    _spawn(s, "Mystical Elf", OPP, 1)
    _standby(s, ME)
    assert s.players[OPP].life_points == 8000 - 600  # 300 x 2 monsters
    # No opponent monsters -> no damage.
    s2 = _fresh(tp=ME)
    _spawn(s2, "Ebon Magician Curran", ME, 0)
    _standby(s2, ME)
    assert s2.players[OPP].life_points == 8000


def test_dancing_fairy_gains_only_in_defense():
    s = _fresh(tp=ME)
    _spawn(s, "Dancing Fairy", ME, 0, pos=Position.FACE_UP_DEFENSE)
    _standby(s, ME)
    assert s.players[ME].life_points == 8000 + 1000
    # In Attack Position the gate blocks it.
    s2 = _fresh(tp=ME)
    _spawn(s2, "Dancing Fairy", ME, 0, pos=Position.FACE_UP_ATTACK)
    _standby(s2, ME)
    assert s2.players[ME].life_points == 8000


def test_spirit_of_the_breeze_gains_only_in_attack():
    s = _fresh(tp=ME)
    _spawn(s, "Spirit of the Breeze", ME, 0, pos=Position.FACE_UP_ATTACK)
    _standby(s, ME)
    assert s.players[ME].life_points == 8000 + 1000
    s2 = _fresh(tp=ME)
    _spawn(s2, "Spirit of the Breeze", ME, 0, pos=Position.FACE_UP_DEFENSE)
    _standby(s2, ME)
    assert s2.players[ME].life_points == 8000


def test_destiny_hero_defender_makes_opponent_draw_on_their_standby():
    s = _fresh(tp=OPP)  # the controller's opponent is the turn player
    _spawn(s, "Destiny HERO - Defender", ME, 0, pos=Position.FACE_UP_DEFENSE)
    # Give the opponent a card to draw.
    card = s.create_instance(reg.get("Celtic Guardian"), owner=OPP, zone=Zone.DECK)
    s.players[OPP].deck.append(card.iid)
    before = len(s.players[OPP].hand)
    _standby(s, OPP)
    assert len(s.players[OPP].hand) == before + 1
    # whose="opponent": it does NOT fire on the controller's own Standby Phase.
    s2 = _fresh(tp=ME)
    _spawn(s2, "Destiny HERO - Defender", ME, 0, pos=Position.FACE_UP_DEFENSE)
    c2 = s2.create_instance(reg.get("Celtic Guardian"), owner=OPP, zone=Zone.DECK)
    s2.players[OPP].deck.append(c2.iid)
    _standby(s2, ME)
    assert len(s2.players[OPP].hand) == 0


def test_lava_golem_burns_its_controller():
    s = _fresh(tp=ME)
    _spawn(s, "Lava Golem", ME, 0)
    _standby(s, ME)
    assert s.players[ME].life_points == 8000 - 1000


def test_minor_goblin_official_burns_opponent_on_their_standby():
    s = _fresh(tp=OPP)
    _trap(s, "Minor Goblin Official", ME, 0)
    _standby(s, OPP)
    assert s.players[OPP].life_points == 8000 - 500


def test_minor_goblin_official_activation_is_gated_on_low_opponent_lp():
    from ygo.card_effects import EFFECTS

    s = _fresh(tp=ME)
    activation = EFFECTS["Minor Goblin Official"][0]
    assert activation.condition is not None
    assert not activation.condition(s, ME)  # opponent at 8000 LP -> cannot activate
    s.players[OPP].life_points = 3000
    assert activation.condition(s, ME)  # 3000 or less -> can activate


def test_skill_drain_suppresses_a_standby_monster_effect():
    s = _fresh(tp=ME)
    _spawn(s, "Bowganian", ME, 0)
    _trap(s, "Skill Drain", ME, 0)  # negates all face-up monster effects
    _standby(s, ME)
    assert s.players[OPP].life_points == 8000  # Bowganian's burn is shut off
