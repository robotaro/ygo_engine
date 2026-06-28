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
    DrawTrigger,
    Effect,
    EquipMod,
    EquipToTarget,
    FieldMod,
    InflictDamage,
    NegateAttack,
    ReturnSpellFromGraveyardToHand,
    SearchMonsterToHand,
    SelfStatMod,
    SpecialSummonFromGraveyard,
    StandbyUpkeep,
    SwitchTargetsToAttack,
    TakeControl,
    TargetSpec,
    Trigger,
    UnionMod,
)
from .enums import Attribute

# A bare "activate it onto the field" effect: Field/Continuous Spells have no
# resolution of their own — placing them face-up is what turns on their layer.
_ACTIVATE_ONTO_FIELD = (Effect(timing="ignition"),)

# Equip-target spec shared by the Equip Spells below.
_EQUIP_TARGET = TargetSpec(count=1, where="any_monster")


def _equip_effect(races=(), attributes=()):
    """A standard Equip Spell: activate by targeting a (race/attribute-restricted)
    monster, then attach. The ATK/DEF boost lives in CONTINUOUS as an EquipMod."""
    return (
        Effect(
            timing="ignition",
            target=TargetSpec(
                count=1,
                where="any_monster",
                races=frozenset(races),
                attributes=frozenset(attributes),
            ),
            resolve=(EquipToTarget(),),
        ),
    )


def _opponent_has_faceup_monster(state, controller) -> bool:
    opp = state.opponent_of(controller)
    return any(
        iid is not None and state.inst(iid).is_face_up
        for iid in state.players[opp].monster_zones
    )


def _has_free_monster_zone(state, controller) -> bool:
    """Gate the Special Summon: you need an open Monster Zone to revive into."""
    return state.first_empty_monster_zone(controller) is not None


def _lp_above(amount: int):
    """Activation gate for a Life-Point cost: the controller must have more than
    ``amount`` LP to pay it (Toon World's 1000)."""

    def cond(state, controller) -> bool:
        return state.players[controller].life_points > amount

    return cond


def _can_fusion_summon(state, controller) -> bool:
    """Gate Polymerization: at least one Extra Deck Fusion is makeable right now."""
    from .moves import makeable_fusions  # lazy import avoids a card_effects<->moves cycle

    return bool(makeable_fusions(state, controller))


def _can_ritual_summon_for(monster_name: str):
    """Build the activation gate for a Ritual Spell that summons ``monster_name``:
    that Ritual Monster must be in hand and enough Tribute fodder must be on hand."""

    def cond(state, controller) -> bool:
        from .moves import can_ritual_summon  # lazy import avoids a module cycle

        return can_ritual_summon(state, controller, monster_name)

    return cond


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
    # --- Effects Batch 2: race/attribute-restricted flat Equip Spells ---
    # Race-restricted +300 ATK/DEF (the classic "tribal" equips). The host filter
    # is on the target; the boost is the EquipMod in CONTINUOUS below.
    "Beast Fangs": _equip_effect(races=("Beast",)),
    "Book of Secret Arts": _equip_effect(races=("Spellcaster",)),
    "Dark Energy": _equip_effect(races=("Fiend",)),
    "Dragon Treasure": _equip_effect(races=("Dragon",)),
    "Electro-Whip": _equip_effect(races=("Thunder",)),
    "Follow Wind": _equip_effect(races=("Winged Beast",)),
    "Silver Bow and Arrow": _equip_effect(races=("Fairy",)),
    "Vile Germs": _equip_effect(races=("Plant",)),
    # Attribute-restricted +400 ATK / -200 DEF.
    "Burning Spear": _equip_effect(attributes=(Attribute.FIRE,)),
    "Elf's Light": _equip_effect(attributes=(Attribute.LIGHT,)),
    "Gust Fan": _equip_effect(attributes=(Attribute.WIND,)),
    "Steel Shell": _equip_effect(attributes=(Attribute.WATER,)),
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
    # Call of the Haunted — Continuous Trap: revive from *your own* Graveyard and
    # bond to it (linked destruction below).
    "Call of the Haunted": (
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
    # --- Effects Batch 1: more Field Spells (pure stat layers, see CONTINUOUS) ---
    "Forest": _ACTIVATE_ONTO_FIELD,
    "Mountain": _ACTIVATE_ONTO_FIELD,
    "Wasteland": _ACTIVATE_ONTO_FIELD,
    "Umi": _ACTIVATE_ONTO_FIELD,
    "Jurassic World": _ACTIVATE_ONTO_FIELD,
    "Umiiruka": _ACTIVATE_ONTO_FIELD,
    "Mystic Plasma Zone": _ACTIVATE_ONTO_FIELD,
    "Molten Destruction": _ACTIVATE_ONTO_FIELD,
    "Luminous Spark": _ACTIVATE_ONTO_FIELD,
    "Rising Air Current": _ACTIVATE_ONTO_FIELD,
    "Acidic Downpour": _ACTIVATE_ONTO_FIELD,
    # --- Slice 8: Standby-Phase upkeep (maintenance cost / per-Standby burn) ---
    # Messenger of Peace — Continuous Spell with no activation effect; its
    # pay-or-destroy upkeep and ATK>=1500 attack lock live in CONTINUOUS below.
    "Messenger of Peace": _ACTIVATE_ONTO_FIELD,
    # Burning Land — Continuous Spell: activating it wipes every Field Spell, then
    # it burns the active player 500 each Standby (the burn lives in CONTINUOUS).
    "Burning Land": (Effect(timing="ignition", resolve=(DestroyAllFieldSpells(),)),),
    # --- Slice 17: Toon World — Continuous Spell, pay 1000 LP to activate ---
    # While it's face-up it enables your Toon monsters (the engine checks for it by
    # name); if it leaves the field, your Toon monsters are destroyed.
    "Toon World": (
        Effect(timing="ignition", condition=_lp_above(1000), resolve=(InflictDamage(SELF, 1000),)),
    ),
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
    # --- Slice 10: draw-trigger hook ---
    # Solemn Wishes — Continuous Trap: no resolution of its own. Set it, then
    # activate it (flip face-up) on a later turn; its CONTINUOUS draw layer pays out.
    "Solemn Wishes": (Effect(speed=2, timing="ignition"),),
    # --- Slice 11: Fusion Summoning ---
    # Polymerization — the "fusion" timing routes to the engine's Fusion flow:
    # pick a makeable Extra Deck monster, send its materials from hand/field to the
    # GY, and Special Summon it. Only activatable when something is makeable.
    "Polymerization": (Effect(timing="fusion", condition=_can_fusion_summon),),
    # --- Slice 12: Ritual Summoning ---
    # A Ritual Spell summons one named Ritual Monster from the hand, Tributing
    # monsters whose Levels total at least that monster's Level. The "ritual"
    # timing routes to the engine's Ritual flow.
    "Black Luster Ritual": (
        Effect(timing="ritual", condition=_can_ritual_summon_for("Black Luster Soldier")),
    ),
    "Hamburger Recipe": (
        Effect(timing="ritual", condition=_can_ritual_summon_for("Hungry Burger")),
    ),
}


# Fusion recipes (Slice 11): Fusion monster name -> the exact material card names
# it needs (multiplicity matters). Materials come from the controller's hand/field.
FUSIONS: dict[str, tuple[str, ...]] = {
    "Gaia the Dragon Champion": ("Gaia The Fierce Knight", "Curse of Dragon"),
    "Flame Swordsman": ("Flame Manipulator", "Masaki the Legendary Swordsman"),
    "Black Skull Dragon": ("Summoned Skull", "Red-Eyes Black Dragon"),
}

# Ritual recipes (Slice 12): Ritual Spell name -> the Ritual Monster it summons
# from the hand. The Tributes' total Level must reach that monster's own Level.
RITUALS: dict[str, str] = {
    "Black Luster Ritual": "Black Luster Soldier",
    "Hamburger Recipe": "Hungry Burger",
}


# Passive modifiers applied while a card is face-up on the field (the "layers").
# A card may radiate EquipMods (attached Equips), FieldMods (field-wide stat
# layers), or AttackRestrictions (continuous rules limits) — consumers filter by
# type, so a card can mix them.
CONTINUOUS: dict[str, tuple] = {
    "Axe of Despair": (EquipMod(atk=1000),),
    "United We Stand": (EquipMod(scaling="face_up_monsters", scale_atk=800, scale_defn=800),),
    "Mage Power": (EquipMod(scaling="spell_trap", scale_atk=500, scale_defn=500),),
    # --- Effects Batch 2: race/attribute-restricted flat Equip Spells ---
    "Beast Fangs": (EquipMod(atk=300, defn=300),),
    "Book of Secret Arts": (EquipMod(atk=300, defn=300),),
    "Dark Energy": (EquipMod(atk=300, defn=300),),
    "Dragon Treasure": (EquipMod(atk=300, defn=300),),
    "Electro-Whip": (EquipMod(atk=300, defn=300),),
    "Follow Wind": (EquipMod(atk=300, defn=300),),
    "Silver Bow and Arrow": (EquipMod(atk=300, defn=300),),
    "Vile Germs": (EquipMod(atk=300, defn=300),),
    "Burning Spear": (EquipMod(atk=400, defn=-200),),
    "Elf's Light": (EquipMod(atk=400, defn=-200),),
    "Gust Fan": (EquipMod(atk=400, defn=-200),),
    "Steel Shell": (EquipMod(atk=400, defn=-200),),
    # Field Spells — flat ATK/DEF to every matching monster on the field, both sides.
    "Sogen": (FieldMod(atk=200, defn=200, races=frozenset({"Warrior", "Beast-Warrior"})),),
    "Yami": (
        FieldMod(atk=200, defn=200, races=frozenset({"Fiend", "Spellcaster"})),
        FieldMod(atk=-200, defn=-200, races=frozenset({"Fairy"})),
    ),
    "Gaia Power": (FieldMod(atk=500, defn=-400, attributes=frozenset({Attribute.EARTH})),),
    # --- Effects Batch 1: more Field Spells (field-wide stat layers) ---
    # Race-based +200/+200 (the classic terrain Field Spells).
    "Forest": (FieldMod(atk=200, defn=200, races=frozenset({"Insect", "Beast", "Plant", "Beast-Warrior"})),),
    "Mountain": (FieldMod(atk=200, defn=200, races=frozenset({"Dragon", "Winged Beast", "Thunder"})),),
    "Wasteland": (FieldMod(atk=200, defn=200, races=frozenset({"Dinosaur", "Zombie", "Rock"})),),
    "Umi": (
        FieldMod(atk=200, defn=200, races=frozenset({"Fish", "Sea Serpent", "Thunder", "Aqua"})),
        FieldMod(atk=-200, defn=-200, races=frozenset({"Machine", "Pyro"})),
    ),
    "Jurassic World": (FieldMod(atk=300, defn=300, races=frozenset({"Dinosaur"})),),
    # Attribute-based "glass cannon" Field Spells (+500 ATK / -400 DEF, or the reverse).
    "Umiiruka": (FieldMod(atk=500, defn=-400, attributes=frozenset({Attribute.WATER})),),
    "Mystic Plasma Zone": (FieldMod(atk=500, defn=-400, attributes=frozenset({Attribute.DARK})),),
    "Molten Destruction": (FieldMod(atk=500, defn=-400, attributes=frozenset({Attribute.FIRE})),),
    "Luminous Spark": (FieldMod(atk=500, defn=-400, attributes=frozenset({Attribute.LIGHT})),),
    "Rising Air Current": (FieldMod(atk=500, defn=-400, attributes=frozenset({Attribute.WIND})),),
    "Acidic Downpour": (FieldMod(atk=-500, defn=400, attributes=frozenset({Attribute.EARTH})),),
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
    # --- Slice 10: draw-trigger hook ---
    # Solemn Wishes: gain 500 LP each time its controller draws a card(s).
    "Solemn Wishes": (DrawTrigger(gain_life=500),),
    # --- Slice 15: Gemini monster ---
    # Goggle Golem: a Normal Monster (1500 ATK) until Gemini Summoned, then "the
    # original ATK of this card becomes 2100" — a +600 self-layer that the engine
    # only applies once `gemini_unlocked` is set (effects_active).
    "Goggle Golem": (SelfStatMod(atk=600),),
    # --- Slice 16: Union monster ---
    # Y-Dragon Head: equips only to "X-Head Cannon" you control; the host gains
    # 400 ATK/DEF (the EquipMod flows through the normal Equip layer once attached).
    # (Simplification: the "destroy this card instead of the host" protection is
    # not modelled — when the host leaves, the Union follows it to the GY.)
    "Y-Dragon Head": (
        UnionMod(host_names=frozenset({"X-Head Cannon"})),
        EquipMod(atk=400, defn=400),
    ),
}
