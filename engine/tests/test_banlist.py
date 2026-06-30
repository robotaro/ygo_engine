"""Forbidden/Limited lists: the bundled presets, the catalogue, and custom saves."""

from __future__ import annotations

import pytest

import ygo.paths as paths
from ygo.deckbuild import (
    MAX_COPIES,
    BanList,
    DeckBuilder,
    list_banlists,
    load_banlist,
    save_banlist,
)
from ygo.cards import CardRegistry

REG = CardRegistry.load_csv()


# --------------------------------------------------------------------------- #
#  BanList primitives
# --------------------------------------------------------------------------- #
def test_no_restrictions_defaults_to_three():
    bl = load_banlist(None)
    assert bl.limit_for("Raigeki") == MAX_COPIES
    assert load_banlist("none").limit_for("Anything") == MAX_COPIES


def test_counts_by_status():
    bl = BanList(name="x", limits={"a": 0, "b": 0, "c": 1, "d": 2})
    assert bl.counts_by_status() == {"forbidden": 2, "limited": 1, "semi-limited": 1}


# --------------------------------------------------------------------------- #
#  The bundled OCG March 2008 preset
# --------------------------------------------------------------------------- #
def test_ocg_2008_preset_caps():
    bl = load_banlist("ocg_2008_03")
    assert bl.limit_for("Raigeki") == 0  # Forbidden
    assert bl.limit_for("Mirror Force") == 1  # Limited
    assert bl.limit_for("Cyber Dragon") == 2  # Semi-Limited
    assert bl.limit_for("Kuriboh") == MAX_COPIES  # unlisted


def test_ocg_2008_preset_only_references_pool_cards():
    bl = load_banlist("ocg_2008_03")
    pool = {c.name for c in REG}
    missing = [name for name in bl.limits if name not in pool]
    assert not missing, f"banlist names not in pool: {missing}"


def test_catalogue_lists_presets_with_none_first():
    cat = list_banlists()
    ids = [e["id"] for e in cat]
    assert cat[0]["id"] == "none"
    assert "ocg_2008_03" in ids
    ocg = next(e for e in cat if e["id"] == "ocg_2008_03")
    assert ocg["builtin"] and ocg["restricted"] == 109


# --------------------------------------------------------------------------- #
#  Validation actually enforces a banlist
# --------------------------------------------------------------------------- #
def test_validate_enforces_forbidden():
    bl = load_banlist("ocg_2008_03")
    b = DeckBuilder(REG, banlist=bl)
    # a 40-card legal vanilla base, then add a Forbidden staple
    vanillas = [c.name for c in REG if c.is_vanilla and not c.goes_in_extra_deck][:20]
    for name in vanillas:
        b.add(name, 2)
    b.remove(vanillas[0], 1)
    b.add("Raigeki", 1)  # Forbidden -> illegal
    report = b.validate()
    assert not report.is_legal
    assert any("Raigeki" in e.message for e in report.errors)


# --------------------------------------------------------------------------- #
#  Custom save round-trip (isolated to a tmp dir)
# --------------------------------------------------------------------------- #
def test_save_custom_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "BANLISTS_DIR", tmp_path)
    bl = BanList(name="House Rules", limits={"Pot of Greed": 0, "Sangan": 1})
    path = save_banlist(bl, "house")
    assert path.parent.name == "user"

    reloaded = load_banlist("user/house")
    assert reloaded.limits == {"Pot of Greed": 0, "Sangan": 1}

    cat = list_banlists()
    assert cat[0]["id"] == "none"  # still offered with no file present
    custom = next(e for e in cat if e["id"] == "user/house")
    assert not custom["builtin"] and custom["restricted"] == 2


def test_save_cannot_escape_user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "BANLISTS_DIR", tmp_path)
    # a crafted id must never climb out of user/ to clobber a preset
    with pytest.raises(ValueError):
        save_banlist(BanList(name="evil"), "../ocg_2008_03")
