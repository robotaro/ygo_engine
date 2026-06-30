"""Effects Batch 93: the Ritual-absorb cluster — Relinquished + Thousand-Eyes Restrict.

Signature mechanic (both): once per turn, equip an opponent's monster onto this card (it
leaves their field); this card's ATK/DEF become equal to the absorbed monster's. Max 1.
When this card leaves, the absorbed monster is destroyed (to its owner's GY).

- Relinquished is Ritual Summoned via Black Illusion Ritual.
- Thousand-Eyes Restrict is Fusion-summoned ("Relinquished" + "Thousand-Eyes Idol") and
  locks the board: no monster may declare an attack while it's face-up.

Deferred (documented): the battle-destruction-redirect, and TER's position-change lock.
TER's attack-lock also stops TER itself (a 0-ATK floodgate) — a minor simplification.
"""

from __future__ import annotations

from ygo.agents import Agent
from ygo.cards import CardRegistry
from ygo.card_effects import EFFECTS, FUSIONS
from ygo.engine import Engine
from ygo.enums import Phase, Position, Zone
from ygo.moves import DeclareAttack, _battle_phase_actions, can_ritual_summon, resolve_effect
from ygo.state import GameState

reg = CardRegistry.load_csv()

A, B = 0, 1


def _fresh(tp=0, phase=Phase.MAIN_1):
    s = GameState.new(("A", "B"), seed=0)
    s.turn_count, s.turn_player, s.phase = 3, tp, phase
    return s


def _spawn(s, name, player, idx, pos=Position.FACE_UP_ATTACK):
    return s.spawn_on_field(reg.get(name), player, idx, pos)


def _in_hand(s, name, player):
    inst = s.create_instance(reg.get(name), owner=player, zone=Zone.HAND)
    s.players[player].hand.append(inst.iid)
    return inst


# ------------------------------------------------------------------------- the absorb


def test_relinquished_absorbs_and_copies_stats():
    s = _fresh()
    rel = _spawn(s, "Relinquished", A, 0)  # base 0/0
    prey = _spawn(s, "Summoned Skull", B, 0)  # 2500/1200
    assert s.effective_attack(rel.iid) == 0
    resolve_effect(s, EFFECTS["Relinquished"][0], rel.iid, (prey.iid,))
    assert s.inst(prey.iid).zone is Zone.SPELL_TRAP  # absorbed as an equip
    assert s.inst(prey.iid).equipped_to == rel.iid
    assert prey.iid not in s.players[B].monster_zones  # gone from the opponent's field
    assert s.effective_attack(rel.iid) == 2500  # ATK becomes the absorbed monster's
    assert s.effective_defense(rel.iid) == 1200


def test_absorb_is_max_one_releasing_the_previous():
    s = _fresh()
    rel = _spawn(s, "Relinquished", A, 0)
    a = _spawn(s, "Mystical Elf", B, 0)
    b = _spawn(s, "Summoned Skull", B, 1)
    resolve_effect(s, EFFECTS["Relinquished"][0], rel.iid, (a.iid,))
    resolve_effect(s, EFFECTS["Relinquished"][0], rel.iid, (b.iid,))
    assert s.inst(a.iid).zone is Zone.GRAVEYARD  # the first absorbed is released
    assert a.iid in s.players[B].graveyard  # to its owner's GY
    assert s.inst(b.iid).equipped_to == rel.iid  # the new one is held
    assert s.effective_attack(rel.iid) == 2500


def test_absorbed_monster_returns_to_owner_gy_when_host_leaves():
    s = _fresh()
    rel = _spawn(s, "Relinquished", A, 0)
    prey = _spawn(s, "Summoned Skull", B, 0)
    resolve_effect(s, EFFECTS["Relinquished"][0], rel.iid, (prey.iid,))
    eng = Engine(s, [Agent(), Agent()])
    s.send_to_graveyard(rel.iid)  # Relinquished leaves the field
    eng._cleanup_equips()
    assert s.inst(prey.iid).zone is Zone.GRAVEYARD
    assert prey.iid in s.players[B].graveyard  # back to its owner, not the absorber


def test_absorbed_monster_radiates_no_passives():
    # A monster with a field anthem (Bladefly: all WIND +500 / EARTH -400) must not radiate
    # while sitting as an absorbed equip in a Spell/Trap zone.
    s = _fresh()
    rel = _spawn(s, "Relinquished", A, 0)
    bladefly = _spawn(s, "Bladefly", B, 0)
    wind = _spawn(s, "Spear Dragon", A, 1)  # WIND; gains +500 from Bladefly's anthem
    printed = reg.get("Spear Dragon").attack
    assert s.effective_attack(wind.iid) == printed + 500  # anthem active while on the field
    resolve_effect(s, EFFECTS["Relinquished"][0], rel.iid, (bladefly.iid,))
    assert s.effective_attack(wind.iid) == printed  # absorbed -> radiates nothing


# ------------------------------------------------------------ Thousand-Eyes Restrict lock


def test_ter_locks_all_attacks():
    s = _fresh(tp=B, phase=Phase.BATTLE)
    _spawn(s, "Thousand-Eyes Restrict", A, 0)
    attacker = _spawn(s, "Summoned Skull", B, 0)  # the turn player's monster
    _spawn(s, "Mystical Elf", A, 1)  # a target to attack
    actions = _battle_phase_actions(s, B)
    assert not any(isinstance(a, DeclareAttack) for a in actions)  # board is frozen
    assert attacker  # (silence lint)


def test_ter_also_absorbs():
    s = _fresh()
    ter = _spawn(s, "Thousand-Eyes Restrict", A, 0)
    prey = _spawn(s, "Summoned Skull", B, 0)
    resolve_effect(s, EFFECTS["Thousand-Eyes Restrict"][0], ter.iid, (prey.iid,))
    assert s.inst(prey.iid).equipped_to == ter.iid
    assert s.effective_attack(ter.iid) == 2500


# --------------------------------------------------------------- summon mechanics wired


def test_relinquished_ritual_summonable():
    s = _fresh()
    _in_hand(s, "Relinquished", A)  # Level 1
    _in_hand(s, "Black Illusion Ritual", A)
    _spawn(s, "Summoned Skull", A, 0)  # a Tribute whose Level (6) covers Relinquished's
    assert can_ritual_summon(s, A, "Relinquished")


def test_ter_fusion_recipe_registered():
    assert FUSIONS["Thousand-Eyes Restrict"] == ("Relinquished", "Thousand-Eyes Idol")
