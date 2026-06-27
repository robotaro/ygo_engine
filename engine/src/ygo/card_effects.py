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
    DamageEqualToAttackerAtk,
    DestroyAllMonsters,
    DestroyAttackingAttackPositionMonsters,
    DestroyLowestAtkOpponentMonster,
    DestroyTargets,
    Draw,
    Effect,
    EquipMod,
    EquipToTarget,
    InflictDamage,
    NegateAttack,
    ReturnSpellFromGraveyardToHand,
    SearchMonsterToHand,
    SwitchTargetsToAttack,
    TargetSpec,
    Trigger,
)

# Equip-target spec shared by the Equip Spells below.
_EQUIP_TARGET = TargetSpec(count=1, where="any_monster")


def _opponent_has_faceup_monster(state, controller) -> bool:
    opp = state.opponent_of(controller)
    return any(
        iid is not None and state.inst(iid).is_face_up
        for iid in state.players[opp].monster_zones
    )


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
}


# Passive modifiers applied while a card is face-up on the field (the "layers").
CONTINUOUS: dict[str, tuple] = {
    "Axe of Despair": (EquipMod(atk=1000),),
    "United We Stand": (EquipMod(scaling="face_up_monsters", scale_atk=800, scale_defn=800),),
    "Mage Power": (EquipMod(scaling="spell_trap", scale_atk=500, scale_defn=500),),
}
