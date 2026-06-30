"""Deck/card HTTP API helpers (pure functions behind the FastAPI routes)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")  # the server extra may not be installed everywhere

from ygo.server import app as srv  # noqa: E402


def test_card_to_dict_shape():
    card = srv.REGISTRY.get("Blue-Eyes White Dragon")
    d = srv.card_to_dict(card)
    assert d["name"] == "Blue-Eyes White Dragon"
    assert d["cardType"] == "monster"
    assert d["attack"] == 3000
    assert d["functional"] is True  # vanilla -> always playable
    assert d["extraDeck"] is False


def test_resolve_deck_id_rejects_traversal():
    # A real bundled blueprint resolves.
    assert srv.resolve_deck_id("vanilla/slice1_alpha.txt") is not None
    # Escapes and unknowns do not.
    assert srv.resolve_deck_id("../../../etc/passwd") is None
    assert srv.resolve_deck_id("vanilla/does_not_exist.txt") is None
    assert srv.resolve_deck_id("") is None
    assert srv.resolve_deck_id(None) is None


def test_deck_catalog_has_entries():
    catalog = srv.deck_catalog()
    assert len(catalog) > 100
    sample = catalog[0]
    assert {"id", "name", "main", "extra", "legal", "playablePct"} <= sample.keys()
    # at least one fully-legal deck exists
    assert any(d["legal"] for d in catalog)


def test_validate_endpoint_logic():
    # Two copies each of 20 distinct main-deck vanillas -> a legal 40-card deck.
    vanillas = [c.name for c in srv.REGISTRY if c.is_vanilla and not c.goes_in_extra_deck][:20]
    main = {name: 2 for name in vanillas}
    result = srv.validation_dict(srv.decklist_from_counts("Test", main, {}))
    assert result["legal"] is True
    assert result["mainSize"] == 40
    assert result["playablePct"] == 100

    # An unknown card name surfaces as an error.
    bad = srv.validation_dict(srv.decklist_from_counts("Bad", {"Not A Card": 3}, {}))
    assert bad["legal"] is False
    assert any("Not A Card" in e for e in bad["errors"])
