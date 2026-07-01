"""Booster-pack catalogue + the pull mechanic."""

from __future__ import annotations

import random

import pytest

from ygo import packs as K
from ygo.cards import CardRegistry

REGISTRY = CardRegistry.load_csv()


@pytest.fixture(scope="module")
def all_packs():
    return K.list_packs(REGISTRY)


def test_catalogue_nonempty_and_well_formed(all_packs):
    assert len(all_packs) > 50
    for p in all_packs:
        assert p.price > 0
        assert p.cards_per_pack > 0
        assert p.distinct >= 1
        # every listed card resolves to the pool (we filter on parse)
        for name in p.card_names:
            assert REGISTRY.get(name) is not None
    # sorted cheapest-first
    prices = [p.price for p in all_packs]
    assert prices == sorted(prices)


def test_get_pack_resolves_and_guards(all_packs):
    sample = all_packs[0]
    assert K.get_pack(sample.id, REGISTRY) is not None
    assert K.get_pack("../../../etc/passwd", REGISTRY) is None
    assert K.get_pack("gba/nope/does_not_exist", REGISTRY) is None
    assert K.get_pack("", REGISTRY) is None


def test_get_pack_rejects_sibling_prefix_traversal(tmp_path, monkeypatch):
    # A `parents`-based guard must reject a SIBLING dir whose path merely *starts
    # with* the root's string (card_packs vs card_packs_evil) — the old prefix
    # check would have wrongly admitted it and read a file outside the packs dir.
    root = tmp_path / "card_packs"
    evil = tmp_path / "card_packs_evil"
    root.mkdir()
    evil.mkdir()
    (evil / "leak.txt").write_text("# Pack: Leak\n## Common\nKuriboh\n", encoding="utf-8")
    monkeypatch.setattr(K, "CARD_PACKS_DIR", root)

    # id resolves to .../card_packs/../card_packs_evil/leak -> outside root -> rejected
    assert K.get_pack("../card_packs_evil/leak", REGISTRY) is None


def test_open_pack_pulls_from_pack_only(all_packs):
    rng = random.Random(7)
    for p in all_packs[:25]:
        pulled = K.open_pack(p, rng)
        assert len(pulled) == min(p.cards_per_pack, p.distinct)
        assert all(name in p.card_names for name in pulled)


def test_open_pack_is_deterministic_per_seed(all_packs):
    pack = next(p for p in all_packs if p.distinct >= 5)
    a = K.open_pack(pack, random.Random(123))
    b = K.open_pack(pack, random.Random(123))
    assert a == b


def test_rarity_weighting_favours_commons():
    # A realistic 3-card pack: the last slot is a guaranteed Rare-or-better, the
    # other two are rarity-weighted. Across many opens, commons should be the
    # biggest bucket and Secret Rares the smallest.
    from collections import Counter

    pack = K.PackDef(
        id="t",
        name="t",
        game="t",
        price=100,
        cards_per_pack=3,
        by_rarity={
            "Common": [f"C{i}" for i in range(20)],
            "Rare": [f"R{i}" for i in range(5)],
            "Secret Rare": ["S"],
        },
    )
    rng = random.Random(1)
    tally: Counter[str] = Counter()
    for _ in range(2000):
        for name in K.open_pack(pack, rng):
            tally[name[0]] += 1  # 'C', 'R', or 'S'
    assert tally["C"] > tally["R"] > tally["S"]


def test_guaranteed_rare_or_better_per_pack():
    # Every pack with a rare+ tier yields at least one rare+ card.
    pack = K.PackDef(
        id="t",
        name="t",
        game="t",
        price=100,
        cards_per_pack=3,
        by_rarity={"Common": [f"C{i}" for i in range(20)], "Ultra Rare": ["U1", "U2"]},
    )
    rng = random.Random(5)
    for _ in range(200):
        pulled = K.open_pack(pack, rng)
        assert any(name.startswith("U") for name in pulled)
