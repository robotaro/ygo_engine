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
    BanishTargets,
    BounceTargetsToDeck,
    BounceTargetsToHand,
    CountTimes,
    DamageEqualToAttackerAtk,
    DestroyAllFieldSpells,
    DestroyAllSpellTraps,
    DestroyAllMonsters,
    DestroyAttackingAttackPositionMonsters,
    DestroyFaceUpMonstersWithDefAtMost,
    DestroyHighestAtkMonster,
    DestroyHighestDefOpponentMonster,
    DestroyLowestAtkOpponentMonster,
    DestroyTargets,
    Draw,
    DrawTrigger,
    Effect,
    EquipMod,
    EquipToTarget,
    FieldMod,
    GainLifePoints,
    HandSpecialSummon,
    InflictDamage,
    ModifyStatsTemporary,
    NegateAttack,
    Piercing,
    ReturnAllSpellTrapsToHand,
    ReturnSpellFromGraveyardToHand,
    SearchMonsterToHand,
    SelfStatMod,
    SpecialSummonFromGraveyard,
    StandbyUpkeep,
    SwitchTargetsToAttack,
    TakeControl,
    TargetAttack,
    TargetSpec,
    Trigger,
    TributedAttack,
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


def _control_no_monsters(state, controller) -> bool:
    """Self-SS gate (Evil HERO Infernal Prodigy-style): your Monster Zones are empty."""
    return all(i is None for i in state.players[controller].monster_zones)


def _only_opponent_controls_monster(state, controller) -> bool:
    """Cyber Dragon's gate: the opponent controls a monster and you control none."""
    opp = state.opponent_of(controller)
    you_have = any(i is not None for i in state.players[controller].monster_zones)
    opp_has = any(i is not None for i in state.players[opp].monster_zones)
    return opp_has and not you_have


def _opponent_controls_at_least_more(n: int):
    """The Fiend Megacyber's gate: the opponent controls at least ``n`` more
    monsters than you do."""

    def cond(state, controller) -> bool:
        opp = state.opponent_of(controller)
        mine = sum(1 for i in state.players[controller].monster_zones if i is not None)
        theirs = sum(1 for i in state.players[opp].monster_zones if i is not None)
        return theirs >= mine + n

    return cond


def _controls_named_face_up(name: str):
    """Ancient Gear's gate: you control a face-up monster with this exact name."""

    def cond(state, controller) -> bool:
        return any(
            i is not None and state.inst(i).is_face_up and state.inst(i).card.name == name
            for i in state.players[controller].monster_zones
        )

    return cond


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
    # --- Effects Batch 6: targeted / "highest stat" monster removal Spells ---
    "Smashing Ground": (Effect(resolve=(DestroyHighestDefOpponentMonster(),)),),
    "Hammer Shot": (Effect(resolve=(DestroyHighestAtkMonster(),)),),
    "Soul Taker": (
        Effect(
            target=TargetSpec(count=1, where="opponent_monsters", face_up=True),
            resolve=(DestroyTargets(), GainLifePoints(OPPONENT, 1000)),
        ),
    ),
    "Hinotama": (Effect(resolve=(InflictDamage(OPPONENT, 500),)),),
    # --- Effects Batch 8: discard-cost activations (discard N to activate) ---
    # Normal Spells: pay the discard cost, then the payload resolves.
    "Tribute to the Doomed": (  # discard 1; destroy 1 monster on the field
        Effect(
            discard_cost=1,
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Lightning Vortex": (  # discard 1; destroy all face-up monsters the opponent controls
        Effect(
            discard_cost=1,
            condition=_opponent_has_faceup_monster,
            resolve=(DestroyAllMonsters(side=OPPONENT, face_up_only=True),),
        ),
    ),
    # Normal Traps (speed 2): set first, then activate from the field (paying the cost).
    "Raigeki Break": (  # discard 1; destroy 1 card on the field
        Effect(
            speed=2,
            timing="quick",
            discard_cost=1,
            target=TargetSpec(count=1, where="any_card_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Rising Energy": (  # discard 1; a face-up monster gains 1500 ATK until the End Phase
        Effect(
            speed=2,
            timing="quick",
            discard_cost=1,
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ModifyStatsTemporary(atk=1500),),
        ),
    ),
    # --- Effects Batch 9: banish (remove from play) payloads ---
    # Dark Core — Normal Spell: discard 1, then banish a face-up monster.
    "Dark Core": (
        Effect(
            discard_cost=1,
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(BanishTargets(),),
        ),
    ),
    # Dimensional Prison — Normal Trap: banish the attacking monster (the attack then
    # fizzles, since the attacker has left the field).
    "Dimensional Prison": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(BanishTargets(),),
        ),
    ),
    # Bottomless Trap Hole — Normal Trap: when the opponent Summons a monster with
    # ATK >= 1500, banish it (we move it straight to the banished pile).
    "Bottomless Trap Hole": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="summon", by=OPPONENT, subject="monster", min_atk=1500),
            resolve=(BanishTargets(),),
        ),
    ),
    # --- Effects Batch 10: bounce (return to hand / Deck) ---
    # Return a monster to the hand.
    "Compulsory Evacuation Device": (  # Normal Trap, any time
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    "Hane-Hane": (  # FLIP: bounce 1 monster on the field
        Effect(
            speed=1,
            timing="flip",
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    "Gravekeeper's Guard": (  # FLIP: bounce 1 of the opponent's monsters
        Effect(
            speed=1,
            timing="flip",
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    "Gale Lizard": (  # FLIP: bounce 1 of the opponent's monsters
        Effect(
            speed=1,
            timing="flip",
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    # Giant Trunade — return every Spell/Trap on the field to hand.
    "Giant Trunade": (Effect(resolve=(ReturnAllSpellTrapsToHand(),)),),
    # --- Effects Batch 11: "up to N" targeting (variable count) ---
    # FLIP effects that return up to N monsters to the hand (the player chooses how
    # many, 1..N). Reuses the bounce primitive with TargetSpec(up_to=True).
    "Penguin Soldier": (
        Effect(
            speed=1,
            timing="flip",
            target=TargetSpec(count=2, where="any_monster", up_to=True),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    "Hade-Hane": (
        Effect(
            speed=1,
            timing="flip",
            target=TargetSpec(count=3, where="any_monster", up_to=True),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    # --- Effects Batch 12: mass Spell/Trap destruction + Defense-position removal ---
    "Heavy Storm": (Effect(resolve=(DestroyAllSpellTraps(),)),),  # all S/T on the field
    "Harpie's Feather Duster": (  # all S/T the opponent controls
        Effect(resolve=(DestroyAllSpellTraps(side=OPPONENT),)),
    ),
    "Shield Crush": (  # destroy 1 Defense Position monster on the field
        Effect(
            target=TargetSpec(count=1, where="any_monster", defense_position=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    # Bounce to the top of the Deck (these compose Batch 8's discard cost).
    "Back to Square One": (  # discard 1; put 1 monster on top of its owner's Deck
        Effect(
            discard_cost=1,
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(BounceTargetsToDeck(to_top=True),),
        ),
    ),
    "Phoenix Wing Wind Blast": (  # Normal Trap: discard 1; a card the opponent controls -> top of Deck
        Effect(
            speed=2,
            timing="quick",
            discard_cost=1,
            target=TargetSpec(count=1, where="opponent_card_field"),
            resolve=(BounceTargetsToDeck(to_top=True),),
        ),
    ),
    # --- Effects Batch 13: dynamic values (amount derived from the board) ---
    # Count-based burn/heal ("... for each ..."): the amount is computed at
    # resolution time from a card count via CountTimes(per, pool). The Normal
    # Traps use the same "activate a Set card at will" route as Call of the
    # Haunted (speed-2 ignition) — see the activation note in moves.py.
    "Restructer Revolution": (  # Normal Spell: 200 damage per card in the opponent's hand
        Effect(resolve=(InflictDamage(OPPONENT, value=CountTimes(200, "opponent_hand")),)),
    ),
    "Just Desserts": (  # Normal Trap: 500 damage per monster the opponent controls
        Effect(
            speed=2,
            timing="ignition",
            resolve=(InflictDamage(OPPONENT, value=CountTimes(500, "opponent_monsters")),),
        ),
    ),
    "Secret Barrel": (  # Normal Trap: 200 per card in the opponent's hand and on their field
        Effect(
            speed=2,
            timing="ignition",
            resolve=(InflictDamage(OPPONENT, value=CountTimes(200, "opponent_hand_and_field")),),
        ),
    ),
    "Cemetary Bomb": (  # Normal Trap: 100 per card in the opponent's Graveyard
        Effect(
            speed=2,
            timing="ignition",
            resolve=(InflictDamage(OPPONENT, value=CountTimes(100, "opponent_graveyard")),),
        ),
    ),
    "D.D. Dynamite": (  # Normal Trap: 300 per card the opponent has banished
        Effect(
            speed=2,
            timing="ignition",
            resolve=(InflictDamage(OPPONENT, value=CountTimes(300, "opponent_banished")),),
        ),
    ),
    "Gift of The Mystical Elf": (  # Normal Trap: gain 300 LP per monster on the field
        Effect(
            speed=2,
            timing="ignition",
            resolve=(GainLifePoints(SELF, value=CountTimes(300, "all_monsters")),),
        ),
    ),
    # Stat-based: the value is the attacking monster's ATK. These are reactive
    # Traps whose trigger auto-targets the attacker (subject="attacker"), so
    # TargetAttack() reads ctx.targets[0].
    "Enchanted Javelin": (  # Normal Trap: gain LP equal to the attacking monster's ATK
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(GainLifePoints(SELF, value=TargetAttack()),),
        ),
    ),
    "Draining Shield": (  # Normal Trap: negate the attack, gain LP equal to that monster's ATK
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(NegateAttack(), GainLifePoints(SELF, value=TargetAttack())),
        ),
    ),
    # --- Effects Batch 14: Tribute-cost activations (Tribute a monster to activate) ---
    # The cost is paid before resolution (engine._pay_activation_cost / the atomic
    # path), and the Tributed monster is recorded so the payload can read its stats.
    # These Normal Traps have no trigger, so — like Just Desserts — they activate
    # from the Set zone on your own turn (speed-2 ignition).
    "Spiritual Fire Art - Kurenai": (  # Tribute 1 FIRE monster; burn = its original ATK
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            tribute_attributes=frozenset({Attribute.FIRE}),
            resolve=(InflictDamage(OPPONENT, value=TributedAttack()),),
        ),
    ),
    "Icarus Attack": (  # Tribute 1 Winged Beast; destroy 2 cards on the field
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            tribute_races=frozenset({"Winged Beast"}),
            target=TargetSpec(count=2, where="any_card_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Burst Breath": (  # Tribute 1 Dragon; destroy all face-up monsters with DEF <= its ATK
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            tribute_races=frozenset({"Dragon"}),
            resolve=(DestroyFaceUpMonstersWithDefAtMost(threshold=TributedAttack()),),
        ),
    ),
    # --- Effects Batch 3: fixed burn / heal Normal Spells ---
    "Sparks": (Effect(resolve=(InflictDamage(OPPONENT, 200),)),),
    "Final Flame": (Effect(resolve=(InflictDamage(OPPONENT, 600),)),),
    "Ookazi": (Effect(resolve=(InflictDamage(OPPONENT, 800),)),),
    "Blue Medicine": (Effect(resolve=(GainLifePoints(SELF, 400),)),),
    "Red Medicine": (Effect(resolve=(GainLifePoints(SELF, 500),)),),
    "Goblin's Secret Remedy": (Effect(resolve=(GainLifePoints(SELF, 600),)),),
    "Soul of the Pure": (Effect(resolve=(GainLifePoints(SELF, 800),)),),
    "Dian Keto the Cure Master": (Effect(resolve=(GainLifePoints(SELF, 1000),)),),
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
    # --- Effects Batch 5: temporary (until-end-of-turn) ATK/DEF combat tricks ---
    # Quick-Play / Normal Traps that pump a targeted monster for the turn. The
    # deltas wear off in the End Phase (engine._clear_temp_stats).
    "Rush Recklessly": (  # Quick-Play Spell
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(ModifyStatsTemporary(atk=700),),
        ),
    ),
    "Reinforcements": (  # Normal Trap
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(ModifyStatsTemporary(atk=500),),
        ),
    ),
    "Shield Spear": (  # Normal Trap
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(ModifyStatsTemporary(atk=400, defn=400),),
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
    # --- Effects Batch 4: more clean Flip effects (reuse the flip timing) ---
    "Poison Mummy": (Effect(speed=1, timing="flip", resolve=(InflictDamage(OPPONENT, 500),)),),
    "Skelengel": (Effect(speed=1, timing="flip", resolve=(Draw(count=1),)),),
    "Nobleman-Eater Bug": (
        Effect(
            speed=1,
            timing="flip",
            target=TargetSpec(count=2, where="any_monster"),  # you select 2 to destroy
            resolve=(DestroyTargets(),),
        ),
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


# --- Effects Batch 7: Special Summon from the hand (a monster's own ability) ---
# A monster carries a HandSpecialSummon on its CardDef.hand_summon slot; `moves`
# offers it during the controller's Main Phase as a SpecialSummonFromHand action
# when the board condition holds (it does *not* use up the Normal Summon). These
# are the cleanly-modellable, condition-only (no-cost) ignition self-summons.
HAND_SUMMONS: dict[str, HandSpecialSummon] = {
    "Cyber Dragon": HandSpecialSummon(condition=_only_opponent_controls_monster),
    "The Fiend Megacyber": HandSpecialSummon(condition=_opponent_controls_at_least_more(2)),
    "Ancient Gear": HandSpecialSummon(condition=_controls_named_face_up("Ancient Gear")),
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
    # --- Effects Batch 7: piercing battle damage (a continuous combat rider) ---
    # When these attack a Defense Position monster, the excess (ATK - DEF) is dealt
    # to the defending player (handled in moves._resolve_attack via has_piercing).
    "Dark Driceratops": (Piercing(),),
    "Mad Sword Beast": (Piercing(),),
}
