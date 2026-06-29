"""Effects Batch 30: Token generators (CreateToken).

A Token is synthesised on the fly (no registry entry) and flagged ``is_token`` so it
is removed from the game — never sent to the Graveyard — when it leaves the field.
``CreateToken`` drops N Tokens into empty Monster Zones (the controller's, or the
opponent's for Ojama Trio), stopping early when zones fill. Cards: Scapegoat,
Fires of Doomsday, Fiend's Sanctuary, Ojama Trio (Spell/Trap) and Dandylion
(monster sent-to-GY trigger).
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _set_spell_trap(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    idx = next(i for i, z in enumerate(s.players[player].spell_trap_zones) if z is None)
    s.place_spell_trap(inst.iid, player, idx, Position.FACE_DOWN)
    inst.set_on_turn = s.turn_count - 1
    return inst


def _tokens(s, player):
    return [
        s.inst(i)
        for i in s.players[player].monster_zones
        if i is not None and s.inst(i).card.is_token
    ]


def _activate(s, spell_iid, targets=()):
    Engine(s, [Agent(), Agent()])._activate_as_chain(ActivateSpell(spell_iid, targets=targets), 0)


# --- making Tokens -----------------------------------------------------------------
def test_scapegoat_makes_four_sheep_tokens_in_defense():
    s = _fresh()
    goat = _set_spell_trap(s, "Scapegoat", 0)
    _activate(s, goat.iid)
    toks = _tokens(s, 0)
    assert len(toks) == 4
    assert all(t.position is Position.FACE_UP_DEFENSE for t in toks)
    assert all(t.card.name == "Sheep Token" and t.card.race == "Beast" for t in toks)
    assert all(t.card.attack == 0 and t.card.level == 1 for t in toks)


def test_token_count_is_capped_by_open_zones():
    s = _fresh()
    s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    s.spawn_on_field(reg.get("Mystical Elf"), 0, 1, Position.FACE_UP_ATTACK)
    goat = _set_spell_trap(s, "Scapegoat", 0)
    _activate(s, goat.iid)
    assert len(_tokens(s, 0)) == 3  # only 3 of the 5 zones were free


def test_fiends_sanctuary_makes_one_metal_fiend_token():
    s = _fresh()
    fs = _set_spell_trap(s, "Fiend's Sanctuary", 0)
    _activate(s, fs.iid)
    toks = _tokens(s, 0)
    assert len(toks) == 1
    assert toks[0].card.name == "Metal Fiend Token"
    assert toks[0].card.attribute.name == "DARK"


# --- to the opponent's field (Ojama Trio) ------------------------------------------
def test_ojama_trio_summons_three_to_opponent():
    s = _fresh()
    trio = _set_spell_trap(s, "Ojama Trio", 0)
    _activate(s, trio.iid)
    assert _tokens(s, 0) == []  # none on the activator's side
    opp = _tokens(s, 1)
    assert len(opp) == 3
    assert all(t.card.defense == 1000 and t.card.level == 2 for t in opp)
    assert all(t.controller == 1 for t in opp)


# --- Tokens vanish (never to the GY) when they leave the field ---------------------
def test_token_is_removed_from_game_not_sent_to_graveyard():
    s = _fresh()
    goat = _set_spell_trap(s, "Scapegoat", 0)
    _activate(s, goat.iid)
    tok = _tokens(s, 0)[0]
    iid = tok.iid
    before_gy = len(s.players[0].graveyard)
    s.send_to_graveyard(iid)
    assert iid not in s.cards  # removed from the game entirely
    assert len(s.players[0].graveyard) == before_gy  # not in the GY
    assert all(z != iid for z in s.players[0].monster_zones)


# --- Dandylion: sent from the field to the GY -> 2 Fluff Tokens --------------------
def test_dandylion_spawns_two_fluff_tokens_on_death():
    s = _fresh()
    dandy = s.spawn_on_field(reg.get("Dandylion"), 0, 0, Position.FACE_UP_ATTACK)
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(dandy.iid)
    eng._check_field_to_gy_triggers()  # drain the queued "sent to GY" trigger
    toks = _tokens(s, 0)
    assert len(toks) == 2
    assert all(t.card.name == "Fluff Token" and t.card.race == "Plant" for t in toks)
    assert s.inst(dandy.iid).zone is Zone.GRAVEYARD  # Dandylion itself is in the GY
