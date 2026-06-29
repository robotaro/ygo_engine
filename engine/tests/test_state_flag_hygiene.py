"""Regression: transient per-instance flags don't leak across field departures.

died_by_battle is stamped by a battle destruction and read by the "destroyed by
battle" trigger drain; tributed_iids records a Tribute cost's fodder. Both must be
cleared when a card leaves the field and when it is (re)placed, so a later effect
that reads them at a distance can't see a stale value (e.g. a revived monster that
once died in battle)."""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    return GameState.new(("A", "B"), seed=0)


def test_died_by_battle_is_cleared_when_revived_from_the_graveyard():
    s = _fresh()
    mon = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    s.send_to_graveyard(mon.iid, by_battle=True)
    assert s.inst(mon.iid).died_by_battle is True  # stamped by the battle death
    # Revive it (Monster Reborn / Call of the Haunted style placement from the GY).
    s.place_monster(mon.iid, 0, 0, Position.FACE_UP_ATTACK)
    assert s.inst(mon.iid).died_by_battle is False  # no stale flag on the field


def test_effect_destruction_does_not_set_died_by_battle():
    s = _fresh()
    mon = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    s.send_to_graveyard(mon.iid)  # an effect destroys it (by_battle defaults False)
    assert s.inst(mon.iid).died_by_battle is False


def test_tributed_iids_does_not_outlive_the_field():
    s = _fresh()
    src = s.spawn_on_field(reg.get("Mystical Elf"), 0, 0, Position.FACE_UP_ATTACK)
    src.tributed_iids = [999]  # as if it had paid a Tribute cost
    s.send_to_graveyard(src.iid)
    assert s.inst(src.iid).tributed_iids == []  # cleared on leaving the field
