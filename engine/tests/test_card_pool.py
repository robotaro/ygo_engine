"""Pool-integrity guard. Every card name the engine references — effect/continuous
keys, Fusion recipes, Ritual recipes, and both demo decks — must resolve in the
default card pool. This fails loudly on a name typo or a pool swap, instead of
silently turning an effect card into a vanilla."""

from __future__ import annotations

from ygo.card_effects import CONTINUOUS, EFFECTS, FUSIONS, RITUALS
from ygo.cards import CardRegistry
from ygo.decks import parse_blueprint
from ygo.paths import DECKS_DIR
from ygo.setup import new_duel

reg = CardRegistry.load_csv()  # the default pool


def _referenced_names() -> set[str]:
    names: set[str] = set(EFFECTS) | set(CONTINUOUS) | set(RITUALS) | set(RITUALS.values())
    names |= set(FUSIONS)  # Fusion monster names
    for materials in FUSIONS.values():
        names |= set(materials)
    for deck in ("slice1_alpha.txt", "slice1_beta.txt"):
        for _section, _count, name in parse_blueprint(DECKS_DIR / "vanilla" / deck):
            names.add(name)
    return names


def test_every_referenced_card_name_resolves():
    missing = sorted(n for n in _referenced_names() if reg.get(n) is None)
    assert missing == [], f"names not in the default pool: {missing}"


def test_fusion_recipe_materials_and_monsters_resolve():
    for fusion, materials in FUSIONS.items():
        assert reg.get(fusion) is not None, f"Fusion monster missing: {fusion}"
        assert reg.get(fusion).is_fusion, f"{fusion} is not flagged as a Fusion monster"
        for m in materials:
            assert reg.get(m) is not None, f"Fusion material missing: {m}"


def test_ritual_monsters_resolve_and_are_main_deck():
    for spell, monster in RITUALS.items():
        assert reg.get(spell) is not None, f"Ritual Spell missing: {spell}"
        m = reg.get(monster)
        assert m is not None and m.is_ritual, f"Ritual monster missing/mis-typed: {monster}"
        assert not m.goes_in_extra_deck  # Ritual monsters live in the Main Deck


def test_demo_decks_fully_resolve():
    duel = new_duel(
        DECKS_DIR / "vanilla" / "slice1_alpha.txt",
        DECKS_DIR / "vanilla" / "slice1_beta.txt",
        seed=0,
    )
    assert duel.missing_report == {}, f"unresolved deck cards: {duel.missing_report}"
