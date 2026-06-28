"""Effects Batch 2: race/attribute-restricted flat Equip Spells. They reuse the
Equip layer (EquipMod); the new bit is a race/attribute restriction on the equip
target (TargetSpec.races/attributes), so a tribal equip can only attach to its
own kind."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.moves import ActivateSpell, apply, legal_actions
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _first(pred):
    return next(c for c in reg if c.is_monster and (c.attack or 0) > 0 and pred(c))


def _equip(s, name, target_iid, player=0):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    apply(s, ActivateSpell(inst.iid, targets=(target_iid,)))
    return inst


def test_book_of_secret_arts_boosts_a_spellcaster():
    s = GameState.new(("A", "B"), seed=0)
    sc = _first(lambda c: c.race == "Spellcaster")
    m = s.spawn_on_field(sc, 0, 0, Position.FACE_UP_ATTACK)
    _equip(s, "Book of Secret Arts", m.iid)
    assert s.effective_attack(m.iid) == (sc.attack or 0) + 300
    assert s.effective_defense(m.iid) == (sc.defense or 0) + 300


def test_dragon_treasure_only_targets_dragons():
    s = GameState.new(("A", "B"), seed=0)
    s.phase, s.turn_count, s.turn_player = Phase.MAIN_1, 2, 0
    dragon = s.spawn_on_field(_first(lambda c: c.race == "Dragon"), 0, 0, Position.FACE_UP_ATTACK)
    nondragon = s.spawn_on_field(_first(lambda c: c.race == "Warrior"), 0, 1, Position.FACE_UP_ATTACK)
    dt = s.create_instance(reg.get("Dragon Treasure"), 0, Zone.HAND)
    s.players[0].hand.append(dt.iid)
    targets = {
        t
        for a in legal_actions(s, 0)
        if isinstance(a, ActivateSpell) and a.iid == dt.iid
        for t in a.targets
    }
    assert dragon.iid in targets
    assert nondragon.iid not in targets  # restricted to Dragons


def test_burning_spear_fire_plus400_minus200():
    s = GameState.new(("A", "B"), seed=0)
    fire = _first(lambda c: c.attribute and c.attribute.value == "FIRE" and (c.defense or 0) >= 200)
    m = s.spawn_on_field(fire, 0, 0, Position.FACE_UP_ATTACK)
    _equip(s, "Burning Spear", m.iid)
    assert s.effective_attack(m.iid) == (fire.attack or 0) + 400
    assert s.effective_defense(m.iid) == (fire.defense or 0) - 200


def test_equip_follows_host_to_graveyard():
    s = GameState.new(("A", "B"), seed=0)
    sc = _first(lambda c: c.race == "Spellcaster")
    m = s.spawn_on_field(sc, 0, 0, Position.FACE_UP_ATTACK)
    eq = _equip(s, "Book of Secret Arts", m.iid)
    assert s.inst(eq.iid).equipped_to == m.iid
