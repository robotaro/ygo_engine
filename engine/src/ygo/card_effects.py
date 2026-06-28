"""Per-card effect definitions, keyed by card name.

This is the content layer: each entry encodes a card's *current ruling* as data,
composed from the primitive verbs in ``effects.py``. The card pool CSV provides
the roster and flavour text; the rules behaviour lives here.

Grows card-by-card. Vanilla monsters never appear (they have no effects).
"""

from __future__ import annotations

from .effects import (
    OPPONENT,
    SELF,
    AttackRestriction,
    DamageEqualToAttackerAtk,
    DestroyAllFieldSpells,
    DestroyAllMonsters,
    DestroyAttackingAttackPositionMonsters,
    DestroyLowestAtkOpponentMonster,
    DestroyTargets,
    Draw,
    Effect,
    EquipMod,
    EquipToTarget,
    FieldMod,
    InflictDamage,
    NegateAttack,
    ReturnSpellFromGraveyardToHand,
    SearchMonsterToHand,
    SpecialSummonFromGraveyard,
    StandbyUpkeep,
    SwitchTargetsToAttack,
    TakeControl,
    TargetSpec,
    Trigger,
)
from .enums import Attribute

# A bare "activate it onto the field" effect: Field/Continuous Spells have no
# resolution of their own — placing them face-up is what turns on their layer.
_ACTIVATE_ONTO_FIELD = (Effect(timing="ignition"),)

# Equip-target spec shared by the Equip Spells below.
_EQUIP_TARGET = TargetSpec(count=1, where="any_monster")


def _opponent_has_faceup_monster(state, controller) -> bool:
    opp = state.opponent_of(controller)
    return any(
        iid is not None and state.inst(iid).is_face_up
        for iid in state.players[opp].monster_zones
    )


def _has_free_monster_zone(state, controller) -> bool:
    """Gate the Special Summon: you need an open Monster Zone to revive into."""
    return state.first_empty_monster_zone(controller) is not None


EFFECTS: dict[str, tuple[Effect, ...]] = {
    # --- Slice 1: Ignition Normal Spells, no cost, no targets ---
    "Pot of Greed": (Effect(resolve=(Draw(count=2),)),),
    "Dark Hole": (Effect(resolve=(DestroyAllMonsters(),)),),
    "Raigeki": (Effect(resolve=(DestroyAllMonsters(side=OPPONENT),)),),
    # --- Slice 2: targeting (player-chosen + automatic) and burn ---
    "Stop Defense": (
        Effect(
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(SwitchTargetsToAttack(),),
        ),
    ),
    "Fissure": (
        Effect(
            condition=_opponent_has_faceup_monster,
            resolve=(DestroyLowestAtkOpponentMonster(),),
        ),
    ),
    "Tremendous Fire": (
        Effect(resolve=(InflictDamage(OPPONENT, 1000), InflictDamage(SELF, 500))),
    ),
    "Hinotama": (Effect(resolve=(InflictDamage(OPPONENT, 500),)),),
    # --- Slice 3: the Chain — Traps & Quick-Play (speed 2) ---
    "Trap Hole": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="summon", by=OPPONENT, subject="monster", min_atk=1000),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Mirror Force": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            resolve=(NegateAttack(), DestroyAttackingAttackPositionMonsters()),
        ),
    ),
    "Magic Cylinder": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(NegateAttack(), DamageEqualToAttackerAtk()),
        ),
    ),
    "Mystical Space Typhoon": (
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="spell_trap_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    # --- Slice 4: monster effects (Flip + Trigger) ---
    "Man-Eater Bug": (
        Effect(
            speed=1,
            timing="flip",
            target=TargetSpec(count=1, where="any_monster"),  # "regardless of position"
            resolve=(DestroyTargets(),),
        ),
    ),
    "Magician of Faith": (
        Effect(speed=1, timing="flip", resolve=(ReturnSpellFromGraveyardToHand(),)),
    ),
    "Sangan": (
        Effect(
            speed=1,
            timing="trigger",
            trigger=Trigger(kind="sent_to_gy_from_field", by=SELF),
            resolve=(SearchMonsterToHand(1500),),
        ),
    ),
    # --- Slice 5: Equip Spells — activate (target a monster) then stay attached ---
    "Axe of Despair": (Effect(timing="ignition", target=_EQUIP_TARGET, resolve=(EquipToTarget(),)),),
    "United We Stand": (Effect(timing="ignition", target=_EQUIP_TARGET, resolve=(EquipToTarget(),)),),
    "Mage Power": (Effect(timing="ignition", target=_EQUIP_TARGET, resolve=(EquipToTarget(),)),),
    # --- Slice 6: Special Summon from the Graveyard ---
    # Monster Reborn — Normal Spell: revive a monster from *either* Graveyard.
    "Monster Reborn": (
        Effect(
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="any_graveyard_monster"),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    # Call Of The Haunted — Continuous Trap (CSV spells it with capital O/T/H):
    # revive from *your own* Graveyard and bond to it (linked destruction below).
    "Call Of The Haunted": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster"),
            resolve=(SpecialSummonFromGraveyard(link=True),),
        ),
    ),
    # --- Slice 7: Field Spells (stat layers) + one Continuous attack restriction ---
    # These have no resolution effect; activating them just places them face-up,
    # and their `continuous` layer (below) does the rest.
    "Sogen": _ACTIVATE_ONTO_FIELD,
    "Yami": _ACTIVATE_ONTO_FIELD,
    "Gaia Power": _ACTIVATE_ONTO_FIELD,
    "The Dark Door": _ACTIVATE_ONTO_FIELD,
    # --- Slice 8: Standby-Phase upkeep (maintenance cost / per-Standby burn) ---
    # Messenger of Peace — Continuous Spell with no activation effect; its
    # pay-or-destroy upkeep and ATK>=1500 attack lock live in CONTINUOUS below.
    "Messenger of Peace": _ACTIVATE_ONTO_FIELD,
    # Burning Land — Continuous Spell: activating it wipes every Field Spell, then
    # it burns the active player 500 each Standby (the burn lives in CONTINUOUS).
    "Burning Land": (Effect(timing="ignition", resolve=(DestroyAllFieldSpells(),)),),
    # Cure Mermaid is an Effect Monster with no activated ability — only the
    # continuous Standby recovery below — so it needs no EFFECTS entry.
    # --- Slice 9: take-control ---
    # Change of Heart — Normal Spell: borrow an opponent's monster (any position)
    # until your End Phase. Needs a free Monster Zone to receive it.
    "Change of Heart": (
        Effect(
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(TakeControl(until_end_of_turn=True),),
        ),
    ),
    # Snatch Steal — Equip Spell: take control while equipped; control reverts when
    # the Equip leaves the field (its Standby LP gift lives in CONTINUOUS below).
    "Snatch Steal": (
        Effect(
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(TakeControl(equip=True),),
        ),
    ),
}


# Passive modifiers applied while a card is face-up on the field (the "layers").
# A card may radiate EquipMods (attached Equips), FieldMods (field-wide stat
# layers), or AttackRestrictions (continuous rules limits) — consumers filter by
# type, so a card can mix them.
CONTINUOUS: dict[str, tuple] = {
    "Axe of Despair": (EquipMod(atk=1000),),
    "United We Stand": (EquipMod(scaling="face_up_monsters", scale_atk=800, scale_defn=800),),
    "Mage Power": (EquipMod(scaling="spell_trap", scale_atk=500, scale_defn=500),),
    # Field Spells — flat ATK/DEF to every matching monster on the field, both sides.
    "Sogen": (FieldMod(atk=200, defn=200, races=frozenset({"Warrior", "Beast-Warrior"})),),
    "Yami": (
        FieldMod(atk=200, defn=200, races=frozenset({"Fiend", "Spellcaster"})),
        FieldMod(atk=-200, defn=-200, races=frozenset({"Fairy"})),
    ),
    "Gaia Power": (FieldMod(atk=500, defn=-400, attributes=frozenset({Attribute.EARTH})),),
    # Continuous Spell — a rules restriction, not a stat layer.
    "The Dark Door": (AttackRestriction(one_per_battle_phase=True),),
    # --- Slice 8: Standby-Phase upkeep ---
    # Messenger of Peace: pay 100 each of your Standby Phases or it's destroyed,
    # and no monster with ATK >= 1500 can attack (both players).
    "Messenger of Peace": (
        StandbyUpkeep(pay_life=100, whose="controller"),
        AttackRestriction(min_atk_cannot_attack=1500),
    ),
    # Burning Land: the active player takes 500 during each of their Standbys.
    "Burning Land": (StandbyUpkeep(burn_life=500, whose="turn_player"),),
    # Cure Mermaid (Effect Monster): recover 800 each of your Standby Phases — the
    # same hook, on a monster, proving it isn't tied to Spells/Traps.
    "Cure Mermaid": (StandbyUpkeep(gain_life=800, whose="controller"),),
    # --- Slice 9: take-control ---
    # Snatch Steal gifts its victim 1000 LP at each of *their* Standby Phases.
    "Snatch Steal": (StandbyUpkeep(gain_life=1000, whose="opponent"),),
}
