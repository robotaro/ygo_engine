"""Effects Batch 31: continuous ATK scaling by the controller's own Graveyard.

A new ``SelfStatMod`` scaling mode, ``"graveyard_monsters"``, adds ``scale_atk`` per
monster in the controller's own Graveyard — narrowable by ``count_attribute`` /
``count_race`` / ``count_name_contains``. Read live by ``GameState.effective_attack``,
so the value tracks the Graveyard as it changes. Cards: Chaos Necromancer (base 0,
so ATK *is* 300 x monsters), Shadow Ghoul (+100/monster), Mudora (+200/Fairy),
Beelze Frog (+300 per "T.A.D.P.O.L.E."), Grass Phantom (+500 per "Grass Phantom").
"""

from __future__ import annotations

from ygo.cards import CardRegistry
from ygo.enums import Phase, Position, Zone
from ygo.state import GameState

reg = CardRegistry.load_csv()


def _fresh():
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 2, 0, Phase.MAIN_1
    return s


def _in_gy(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.GRAVEYARD)
    s.players[player].graveyard.append(inst.iid)
    return inst


# --- Chaos Necromancer: ATK = monsters in your GY x 300 ----------------------------
def test_chaos_necromancer_scales_with_graveyard():
    s = _fresh()
    necro = s.spawn_on_field(reg.get("Chaos Necromancer"), 0, 0, Position.FACE_UP_ATTACK)
    assert s.effective_attack(necro.iid) == 0  # empty GY -> base 0
    for _ in range(3):
        _in_gy(s, "Mystical Elf", 0)
    assert s.effective_attack(necro.iid) == 900  # 3 monsters x 300


def test_chaos_necromancer_counts_only_monsters_in_own_gy():
    s = _fresh()
    necro = s.spawn_on_field(reg.get("Chaos Necromancer"), 0, 0, Position.FACE_UP_ATTACK)
    _in_gy(s, "Mystical Elf", 0)  # a monster -> counts
    _in_gy(s, "Monster Reborn", 0)  # a Spell -> does NOT count
    _in_gy(s, "Summoned Skull", 1)  # opponent's GY -> does NOT count
    assert s.effective_attack(necro.iid) == 300  # only the one own-GY monster


# --- Shadow Ghoul: +100 ATK per monster in your GY ---------------------------------
def test_shadow_ghoul_adds_to_its_base():
    s = _fresh()
    ghoul = s.spawn_on_field(reg.get("Shadow Ghoul"), 0, 0, Position.FACE_UP_ATTACK)
    assert s.effective_attack(ghoul.iid) == 1600  # base, empty GY
    for _ in range(5):
        _in_gy(s, "Mystical Elf", 0)
    assert s.effective_attack(ghoul.iid) == 1600 + 500  # +100 x 5


# --- Mudora: +200 ATK per Fairy in your GY (race-filtered) -------------------------
def test_mudora_counts_only_fairies():
    s = _fresh()
    mudora = s.spawn_on_field(reg.get("Mudora"), 0, 0, Position.FACE_UP_ATTACK)
    _in_gy(s, "Mystical Elf", 0)  # Spellcaster -> ignored
    _in_gy(s, "Agido", 0)  # Fairy -> counts
    _in_gy(s, "Absorbing Kid from the Sky", 0)  # Fairy -> counts
    assert s.effective_attack(mudora.iid) == 1500 + 400  # base + 200 x 2 Fairies


# --- name-filtered counts (Beelze Frog, Grass Phantom) -----------------------------
def test_beelze_frog_counts_named_tadpole():
    s = _fresh()
    frog = s.spawn_on_field(reg.get("Beelze Frog"), 0, 0, Position.FACE_UP_ATTACK)
    _in_gy(s, "T.A.D.P.O.L.E.", 0)
    _in_gy(s, "T.A.D.P.O.L.E.", 0)
    _in_gy(s, "Mystical Elf", 0)  # not a T.A.D.P.O.L.E.
    assert s.effective_attack(frog.iid) == 1200 + 600  # base + 300 x 2


def test_grass_phantom_counts_copies_of_itself_in_gy():
    s = _fresh()
    phantom = s.spawn_on_field(reg.get("Grass Phantom"), 0, 0, Position.FACE_UP_ATTACK)
    _in_gy(s, "Grass Phantom", 0)
    assert s.effective_attack(phantom.iid) == 1000 + 500  # base + 500 x 1 copy in GY


# --- the boost is suppressed while face-down (no active effect) --------------------
def test_graveyard_scaler_is_off_while_face_down():
    s = _fresh()
    ghoul = s.spawn_on_field(reg.get("Shadow Ghoul"), 0, 0, Position.FACE_DOWN_DEFENSE)
    for _ in range(3):
        _in_gy(s, "Mystical Elf", 0)
    # effective_defense of a face-down monster doesn't get the self-scaler (effect inactive)
    assert s.effective_defense(ghoul.iid) == reg.get("Shadow Ghoul").defense
