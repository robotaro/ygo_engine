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
    ActivationLock,
    ApplyActionLock,
    AttackLifeCost,
    AttackRestriction,
    AttackTargetProtection,
    BanishAttackingDefensePositionMonsters,
    BanishEquippedMonster,
    BanishEventMonster,
    BanishFaceDownThenDeckBanishIfFlip,
    BanishSelfAndEventMonster,
    BanishTargets,
    ChangeAllPositions,
    ChangeTargetPosition,
    BattleIndestructible,
    BounceTargetsToDeck,
    BounceTargetsToHand,
    CanAttackDirectly,
    CardDestructionExchange,
    CardEffectNegation,
    CoinFlip,
    CardFilter,
    CountdownSelfDestruct,
    CountTimes,
    CreateToken,
    DamageEqualToAttackerAtk,
    DamageStepBonus,
    DebuffBattleDestroyer,
    DefenseAfterAttack,
    DestroyedByBattleAttack,
    DestroyEquipHostThenBurn,
    DestroyAllFieldSpells,
    DestroyAllOtherCards,
    DestroyAllSpecialSummoned,
    DestroyAllSpellTraps,
    DestroyAllMonsters,
    DestroyAttackingAttackPositionMonsters,
    DestroyFaceUpMonstersWithDefAtMost,
    DestroyHighestAtkMonster,
    DestroyHighestDefOpponentMonster,
    DestroyLowestAtkOpponentMonster,
    DestroyOwnMonstersHalfAtkBurn,
    DestroyTargets,
    DiscardFromHand,
    DiscardHandThenBurn,
    DoubleControlledRaceAtkThenEndPhaseDestroy,
    Draw,
    DrawAgainOnDraw,
    DrawTrigger,
    Effect,
    EndBattlePhase,
    EndPhaseSummonSweep,
    EndPhaseTrigger,
    LifeGainTrigger,
    EquipMod,
    EquipSelfToAttacker,
    EquipToTarget,
    FieldMod,
    GainLifePoints,
    GraveyardStandbyGainLife,
    GraveyardStandbyReturn,
    HandSpecialSummon,
    InflictDamage,
    LoseHalfLifePoints,
    MillFromDeck,
    ModifyAllStatsTemporary,
    ModifySelfPermanentStats,
    ModifyStatsTemporary,
    ScaleSelfAtkTemporary,
    MultiAttacker,
    NegateAttack,
    NegatePreviousLink,
    Piercing,
    PlaceCountersOnSelf,
    PreventBattleDamageThisBattle,
    PreventBattleDamageThisTurn,
    ReturnAllSetCardsToHand,
    ReturnAllSpellTrapsToHand,
    ReturnFromGraveyardToDeck,
    ReturnFromGraveyardToHand,
    ForceAttackTarget,
    RedirectAttackToTarget,
    ReflectBattleDamage,
    ReturnFromHandToDeck,
    ReturnSelfToDeck,
    ReturnSpellFromGraveyardToHand,
    PlantSelfInOpponentDeck,
    LookAtTopReorderBestFirst,
    DestroyFaceUpMonstersOfDeclaredType,
    ShuffleHandIntoDeckThenDraw,
    AttackTributeCost,
    ReturnEventAttackerToHand,
    AbsorbMonsterAsEquip,
    NoBattleDamageWhileUmi,
    BanishInsteadOfGraveyard,
    BurnOnHandDiscard,
    AcidTrapHole,
    SearchCardToTopOfDeck,
    OpponentMillToAttack,
    CannotBeSpecialSummoned,
    ReturnsToHandAtEndPhase,
    HalvesBattleDamageDealt,
    BurnDefenseMonsterOriginalAtk,
    SwapControlWithTarget,
    SummonTokenIfDestroyedByBattle,
    SameNameAnthem,
    DestroySelf,
    NoNormalSummonWhileControllingMonster,
    CannotAttackUnlessControlRace,
    NameTreatedAs,
    SearchFromDeck,
    SearchMonsterToHand,
    SelfStatMod,
    RevealRandomHandCardSummonOrGY,
    RevealTopSummonRestToHand,
    SetEventAttackerAtkZero,
    ShuffleFieldMonstersThenExcavate,
    SpecialSummonFromDeck,
    SpecialSummonFromDeckAtkAtMostBattleDamage,
    SpecialSummonFromExtraDeck,
    SpecialSummonFromGraveyard,
    SpecialSummonFromHand,
    SpecialSummonSelf,
    SpecialSummonLock,
    SpellCounterHolder,
    StandbyTrigger,
    StandbyUpkeep,
    SummonCost,
    SwitchTargetsToAttack,
    TakeControl,
    TargetAttack,
    TargetSpec,
    Trigger,
    TributedAttack,
    UnionMod,
    SpellTrapProperty,
)
from .enums import Attribute, Phase, Position

# A bare "activate it onto the field" effect: Field/Continuous Spells have no
# resolution of their own — placing them face-up is what turns on their layer.
_ACTIVATE_ONTO_FIELD = (Effect(timing="ignition"),)


def _equip_effect(races=(), attributes=(), names=(), name_contains=()):
    """A standard Equip Spell: activate by targeting a restricted monster (by race/
    attribute, an exact name, or an archetype substring), then attach. The ATK/DEF
    boost lives in CONTINUOUS as an EquipMod."""
    return (
        Effect(
            timing="ignition",
            target=TargetSpec(
                count=1,
                where="any_monster",
                races=frozenset(races),
                attributes=frozenset(attributes),
                names=frozenset(names),
                name_contains=frozenset(name_contains),
            ),
            resolve=(EquipToTarget(),),
        ),
    )


def _flip(resolve, target=None):
    """A Flip Effect (speed 1) — fires when the monster is turned face-up (Flip
    Summoned or flipped by an attack). ``target`` is an optional TargetSpec."""
    return Effect(speed=1, timing="flip", target=target, resolve=resolve)


def _on_sent_to_gy(resolve):
    """A trigger (speed 1) that fires when this card is sent from the field to the GY
    — destroyed directly or orphaned (Black Pendant's burn, Magic Formula's LP gain)."""
    return Effect(
        speed=1,
        timing="trigger",
        trigger=Trigger(kind="sent_to_gy_from_field", by=SELF),
        resolve=resolve,
    )


def _on_battle_damage(resolve, target=None):
    """A trigger that fires when this monster inflicts battle damage to the opponent
    (Masked Sorcerer draws, White Magical Hat discards). The engine fires it from the
    state's transient combat record (engine._fire_battle_damage_trigger)."""
    return Effect(
        timing="trigger",
        trigger=Trigger(kind="battle_damage_inflicted", by=SELF),
        target=target,
        resolve=resolve,
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


def _opponent_controls_3plus_attack(state, controller) -> bool:
    """Radiant Mirror Force gate: the attacking player (your opponent) must control 3+
    face-up Attack-Position monsters."""
    opp = state.opponent_of(controller)
    return (
        sum(
            1
            for iid in state.players[opp].monster_zones
            if iid is not None and state.inst(iid).position is Position.FACE_UP_ATTACK
        )
        >= 3
    )


def _controls_monster_with_free_zone(state, controller) -> bool:
    """Magical Arm Shield gate: you must control a monster (printed requirement) and have
    a free Monster Zone to put the stolen monster in."""
    has_monster = any(i is not None for i in state.players[controller].monster_zones)
    return has_monster and state.first_empty_monster_zone(controller) is not None


def _any_special_summoned_monster(state, controller) -> bool:
    """Gate "destroy all Special Summoned monsters" (Jowgen, Special Hurricane) — only
    worth paying the discard when a face-up Special-Summoned monster is on the field."""
    return any(
        iid is not None
        and state.inst(iid).is_face_up
        and state.inst(iid).was_special_summoned
        for pl in (0, 1)
        for iid in state.players[pl].monster_zones
    )


def _opponent_has_free_monster_zone(state, controller) -> bool:
    """Gate a Token summon onto the opponent's field (Ojama Trio)."""
    return state.first_empty_monster_zone(state.opponent_of(controller)) is not None


def _only_controls_roid_machines(state, controller) -> bool:
    """Supercharge gate: the only monsters you control are Machine-Type "roid" monsters
    (so you must control at least one, and every monster you control qualifies)."""
    mons = [state.inst(i) for i in state.players[controller].monster_zones if i is not None]
    return bool(mons) and all(
        m.card.race == "Machine" and "roid" in m.card.name for m in mons
    )


def _controls_amazoness(state, controller) -> bool:
    """Amazoness Archers gate: you control at least one face-up "Amazoness" monster."""
    return any(
        iid is not None
        and state.inst(iid).is_face_up
        and "Amazoness" in state.inst(iid).card.name
        for iid in state.players[controller].monster_zones
    )


def _has_card_in_hand(state, controller) -> bool:
    """A Hero Emerges gate: the controller must hold at least one card to reveal."""
    return bool(state.players[controller].hand)


def _field_spell_on_field(name):
    """Build a condition: a face-up Field Spell of this name sits in either player's Field
    Zone (Gravekeeper's Assailant needs "Necrovalley" on the field)."""

    def cond(state, controller) -> bool:
        for pl in (0, 1):
            fz = state.players[pl].field_zone
            if fz is not None and state.inst(fz).is_face_up and state.inst(fz).card.name == name:
                return True
        return False

    return cond


_necrovalley_on_field = _field_spell_on_field("Necrovalley")


def _gy_has_match(card_filter):
    """Activation gate for a recover-from-GY effect: the controller's Graveyard holds
    at least one card matching ``card_filter`` (so it can't whiff)."""

    def cond(state, controller) -> bool:
        return any(
            card_filter.matches(state.inst(i).card)
            for i in state.players[controller].graveyard
        )

    return cond


def _no_cards_in_hand(state, controller) -> bool:
    """Magical Explosion's gate: the controller holds no cards."""
    return not state.players[controller].hand


def _opponent_has_hand_cards(state, controller) -> bool:
    """Hand-disruption gate: the opponent is holding at least one card."""
    return bool(state.players[state.opponent_of(controller)].hand)


def _opponent_hand_at_least_with_monster(n: int):
    """Trap Dustshoot's gate: the opponent holds ``n``+ cards, one of them a Monster."""

    def cond(state, controller) -> bool:
        opp = state.opponent_of(controller)
        hand = state.players[opp].hand
        return len(hand) >= n and any(state.inst(i).card.is_monster for i in hand)

    return cond


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


def _exactly_n_attr_in_gy(n: int, attribute: Attribute):
    """Dark Armed Dragon's gate: you have *exactly* ``n`` monsters of ``attribute``
    in your Graveyard."""

    def cond(state, controller) -> bool:
        count = sum(
            1
            for i in state.players[controller].graveyard
            if state.inst(i).card.is_monster and state.inst(i).card.attribute is attribute
        )
        return count == n

    return cond


def _lp_above(amount: int):
    """Activation gate for a Life-Point cost: the controller must have more than
    ``amount`` LP to pay it (Toon World's 1000)."""

    def cond(state, controller) -> bool:
        return state.players[controller].life_points > amount

    return cond


def _opp_lp_at_most(amount: int):
    """Activation gate keyed off the opponent's Life Points (Minor Goblin Official
    can only be activated when your opponent is at ``amount`` LP or less)."""

    def cond(state, controller) -> bool:
        return state.players[state.opponent_of(controller)].life_points <= amount

    return cond


def _chain_top_card(state):
    """The printed card whose activation is currently on top of the Chain — the one
    a Counter Trap would be responding to (None if the Chain is empty)."""
    chain = state.chain
    if not chain:
        return None
    inst = state.cards.get(chain[-1].source_iid)
    return inst.card if inst is not None else None


def _chain_top_is_spell(state, controller) -> bool:
    card = _chain_top_card(state)
    return card is not None and card.is_spell


def _chain_top_is_trap(state, controller) -> bool:
    card = _chain_top_card(state)
    return card is not None and card.is_trap


def _chain_top_is_spell_or_trap(state, controller) -> bool:
    card = _chain_top_card(state)
    return card is not None and (card.is_spell or card.is_trap)


def _chain_top_is_monster(state, controller) -> bool:
    card = _chain_top_card(state)
    return card is not None and card.is_monster


def _all_conditions(*conds):
    """Combine activation gates: all must hold (e.g. pay-LP gate AND a Chain gate)."""

    def cond(state, controller) -> bool:
        return all(c(state, controller) for c in conds)

    return cond


def _can_search(card_filter: CardFilter):
    """Activation gate for a Deck-search Spell: a matching card must be in the
    controller's Deck (you can't activate Reinforcement of the Army with no Warrior
    to fetch)."""

    def cond(state, controller) -> bool:
        return any(
            card_filter.matches(state.inst(iid).card)
            for iid in state.players[controller].deck
        )

    return cond


def _search_effect(card_filter: CardFilter):
    """A Deck-search Normal Spell: activatable only when a matching card is in the
    Deck; on resolution fetch one (highest-ATK match) and shuffle."""
    return Effect(
        timing="ignition",
        condition=_can_search(card_filter),
        resolve=(SearchFromDeck(card_filter=card_filter),),
    )


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
        _flip(target=TargetSpec(count=1, where="any_monster"), resolve=(BounceTargetsToHand(),)),
    ),
    "Gravekeeper's Guard": (  # FLIP: bounce 1 of the opponent's monsters
        _flip(target=TargetSpec(count=1, where="opponent_monsters"), resolve=(BounceTargetsToHand(),)),
    ),
    "Gale Lizard": (  # FLIP: bounce 1 of the opponent's monsters
        _flip(target=TargetSpec(count=1, where="opponent_monsters"), resolve=(BounceTargetsToHand(),)),
    ),
    # Giant Trunade — return every Spell/Trap on the field to hand.
    "Giant Trunade": (Effect(resolve=(ReturnAllSpellTrapsToHand(),)),),
    # --- Effects Batch 11: "up to N" targeting (variable count) ---
    # FLIP effects that return up to N monsters to the hand (the player chooses how
    # many, 1..N). Reuses the bounce primitive with TargetSpec(up_to=True).
    "Penguin Soldier": (
        _flip(target=TargetSpec(count=2, where="any_monster", up_to=True), resolve=(BounceTargetsToHand(),)),
    ),
    "Hade-Hane": (
        _flip(target=TargetSpec(count=3, where="any_monster", up_to=True), resolve=(BounceTargetsToHand(),)),
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
    # Batch 59: Nightmare Penguin — flipped face-up: bounce 1 card the opponent controls
    # (its WATER anthem is the CONTINUOUS FieldMod).
    "Nightmare Penguin": (
        _flip(
            target=TargetSpec(count=1, where="opponent_card_field"),
            resolve=(BounceTargetsToHand(),),
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
    # --- Effects Batch 15: generalised Deck search ("add 1 [X] from Deck to hand") ---
    # Normal Spells that fetch one matching card from the Deck, then shuffle. The
    # CardFilter both gates activation (a match must exist) and selects the fetch.
    # The pick is deterministic (highest-ATK match) — interactive player choice is
    # a deferred enhancement (same gap Fusion had).
    "Reinforcement of the Army": (  # 1 Level 4 or lower Warrior monster
        _search_effect(CardFilter(card_kind="monster", races=frozenset({"Warrior"}), max_level=4)),
    ),
    "Summoner's Art": (  # 1 Level 5 or higher Normal Monster
        _search_effect(CardFilter(card_kind="normal_monster", min_level=5)),
    ),
    "Terraforming": (  # 1 Field Spell
        _search_effect(CardFilter(card_kind="field_spell")),
    ),
    "Fusion Sage": (  # 1 Polymerization
        _search_effect(CardFilter(names=frozenset({"Polymerization"}))),
    ),
    "E - Emergency Call": (  # 1 Elemental HERO monster
        _search_effect(CardFilter(card_kind="monster", name_contains=frozenset({"Elemental HERO"}))),
    ),
    "Gladiator Proving Ground": (  # 1 Level 4 or lower Gladiator Beast monster
        _search_effect(
            CardFilter(
                card_kind="monster",
                name_contains=frozenset({"Gladiator Beast"}),
                max_level=4,
            )
        ),
    ),
    "Toon Table of Contents": (  # 1 "Toon" card (any card with Toon in its name)
        _search_effect(CardFilter(name_contains=frozenset({"Toon"}))),
    ),
    # --- Effects Batch 16: negate the activation (Counter Traps, Spell Speed 3) ---
    # Chained in response to an activation, they negate the Chain link directly
    # below (NegatePreviousLink) so it never resolves, and destroy that card. The
    # condition gates them to the kind of card they may negate (read off the Chain
    # top). pay-1000-LP is modelled at resolution (like Toon World).
    "Magic Jammer": (  # discard 1; negate a Spell + destroy it
        Effect(
            speed=3,
            timing="quick",
            discard_cost=1,
            condition=_chain_top_is_spell,
            resolve=(NegatePreviousLink(),),
        ),
    ),
    "Seven Tools of the Bandit": (  # pay 1000 LP; negate a Trap + destroy it
        Effect(
            speed=3,
            timing="quick",
            condition=_all_conditions(_lp_above(1000), _chain_top_is_trap),
            resolve=(InflictDamage(SELF, 1000, is_cost=True), NegatePreviousLink()),
        ),
    ),
    "Dark Bribe": (  # opponent draws 1; negate a Spell/Trap + destroy it
        Effect(
            speed=3,
            timing="quick",
            condition=_chain_top_is_spell_or_trap,
            resolve=(Draw(OPPONENT, count=1), NegatePreviousLink()),
        ),
    ),
    # --- Effects Batch 17: negate the Summon / a monster effect / negate+bounce ---
    # Negate the Summon: a Counter Trap in the Summon response window that removes
    # the just-Summoned monster (subject="monster"). Our Summon window fires only on
    # Normal Summons, so these act on Normal Summons (a known simplification).
    "Horn of Heaven": (  # Tribute 1 monster; negate the Summon + destroy that monster
        Effect(
            speed=3,
            timing="trigger",
            trigger=Trigger(kind="summon", by=OPPONENT, subject="monster"),
            tribute_cost=1,
            resolve=(DestroyTargets(),),
        ),
    ),
    "Forced Back": (  # negate the Normal/Flip Summon + return that monster to hand
        Effect(
            speed=3,
            timing="trigger",
            trigger=Trigger(
                kind="summon",
                by=OPPONENT,
                subject="monster",
                summon_kinds=frozenset({"normal", "flip"}),
            ),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    "Black Horn of Heaven": (  # negate a Special Summon + destroy that monster
        Effect(
            speed=3,
            timing="trigger",
            trigger=Trigger(
                kind="summon",
                by=OPPONENT,
                subject="monster",
                summon_kinds=frozenset({"special"}),
            ),
            resolve=(DestroyTargets(),),
        ),
    ),
    # --- Effects Batch 19: "when sent from the field to the GY" triggers ---
    # Equip Spells with a parting effect: activate (equip), boost via CONTINUOUS,
    # and fire a trigger when they leave the field for the GY (whether destroyed
    # directly or orphaned when the equipped monster leaves).
    "Black Pendant": (
        *_equip_effect(),
        _on_sent_to_gy((InflictDamage(OPPONENT, 500),)),  # parting shot to the opponent
    ),
    "Horn of the Unicorn": (
        *_equip_effect(),
        _on_sent_to_gy((ReturnSelfToDeck(to_top=True),)),  # back to the top of the Deck
    ),
    # --- Effects Batch 20: Spell Counters (accumulate + counter-cost / scaling) ---
    # Royal Magical Library: a face-up monster Ignition effect that removes 3 Spell
    # Counters (its activation cost) to draw 1. The counters themselves accumulate
    # via the SpellCounterHolder in CONTINUOUS below.
    "Royal Magical Library": (
        Effect(timing="ignition", counter_cost=3, counter_type="spell", resolve=(Draw(count=1),)),
    ),
    # Mythical Beast Cerberus is purely passive (CONTINUOUS only) — no EFFECTS entry.
    # --- Effects Batch 21: on-Summon monster Trigger Effects ---
    # A monster's own "when (Normal) Summoned" effect now fires on a fresh Chain
    # (engine._trigger_summon_effect), after the Summon survives any negation window.
    # Breaker the Magical Warrior: on Normal Summon, place 1 Spell Counter on itself
    # (max. 1, non-accumulating — see CONTINUOUS); +300 ATK per counter; an Ignition
    # effect removes 1 counter to destroy 1 Spell/Trap on the field.
    "Breaker the Magical Warrior": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            resolve=(PlaceCountersOnSelf(count=1),),
        ),
        Effect(
            timing="ignition",
            counter_cost=1,
            counter_type="spell",
            target=TargetSpec(count=1, where="spell_trap_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    # Hannibal Necromancer: same shape as Breaker, but its Ignition destroys only a
    # face-up Trap on the field.
    "Hannibal Necromancer": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            resolve=(PlaceCountersOnSelf(count=1),),
        ),
        Effect(
            timing="ignition",
            counter_cost=1,
            counter_type="spell",
            target=TargetSpec(count=1, where="spell_trap_field", card_kind="trap", face_up=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    # Gravekeeper's Curse: when Summoned (any way), inflict 500 damage to the opponent.
    "Gravekeeper's Curse": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF),
            resolve=(InflictDamage(OPPONENT, 500),),
        ),
    ),
    # Byser Shock: when Summoned (any way), return all Set cards on the field to hand.
    "Byser Shock": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF),
            resolve=(ReturnAllSetCardsToHand(),),
        ),
    ),
    # --- Effects Batch 22: send-from-field-to-GY activation cost ---
    # Levia-Dragon - Daedalus: Ignition — send a face-up "Umi" you control to the GY
    # (the cost); destroy all OTHER cards on the field.
    "Levia-Dragon - Daedalus": (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(names=frozenset({"Umi"})),
            send_to_gy_face_up=True,
            resolve=(DestroyAllOtherCards(),),
        ),
    ),
    # Ultimate Baseball Kid: Ignition — send another face-up FIRE monster you control
    # to the GY; inflict 500 damage. Its +1000 ATK/FIRE-monster scale is in CONTINUOUS.
    "Ultimate Baseball Kid": (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(card_kind="monster", attributes=frozenset({Attribute.FIRE})),
            send_to_gy_face_up=True,
            send_to_gy_exclude_self=True,
            resolve=(InflictDamage(OPPONENT, 500),),
        ),
    ),
    # --- Effects Batch 23: "destroyed by battle" -> Special Summon from the Deck ---
    # The classic recruiter family: when destroyed by battle and sent to the GY,
    # Special Summon 1 matching monster (ATK 1500 or less) from the Deck. Fires via
    # the engine's "destroyed_by_battle" trigger; the fetch is deterministic
    # (highest-ATK match under the cap). All summon in face-up Attack Position.
    **{
        name: (
            Effect(
                timing="trigger",
                trigger=Trigger(kind="destroyed_by_battle", by=SELF),
                resolve=(SpecialSummonFromDeck(card_filter=recruit),),
            ),
        )
        for name, recruit in {
            "Mystic Tomato": CardFilter(card_kind="monster", attributes=frozenset({Attribute.DARK}), max_atk=1500),
            "Giant Rat": CardFilter(card_kind="monster", attributes=frozenset({Attribute.EARTH}), max_atk=1500),
            "Mother Grizzly": CardFilter(card_kind="monster", attributes=frozenset({Attribute.WATER}), max_atk=1500),
            "Flying Kamakiri #1": CardFilter(card_kind="monster", attributes=frozenset({Attribute.WIND}), max_atk=1500),
            "UFO Turtle": CardFilter(card_kind="monster", attributes=frozenset({Attribute.FIRE}), max_atk=1500),
            "Shining Angel": CardFilter(card_kind="monster", attributes=frozenset({Attribute.LIGHT}), max_atk=1500),
            "Masked Dragon": CardFilter(card_kind="monster", races=frozenset({"Dragon"}), max_atk=1500),
            "Howling Insect": CardFilter(card_kind="monster", races=frozenset({"Insect"}), max_atk=1500),
            "UFOroid": CardFilter(card_kind="monster", races=frozenset({"Machine"}), max_atk=1500),
            "Warrior Lady of the Wasteland": CardFilter(
                card_kind="monster", races=frozenset({"Warrior"}),
                attributes=frozenset({Attribute.EARTH}), max_atk=1500,
            ),
            "Pyramid Turtle": CardFilter(card_kind="monster", races=frozenset({"Zombie"}), max_def=2000),
        }.items()
    },
    # --- Effects Batch 24: name-restricted Equip Spells ---
    # The equip target is filtered by exact name or by an archetype substring
    # (TargetSpec.names / name_contains). Flat ATK boost lives in CONTINUOUS; the
    # ones with a parting effect reuse the Batch 19 "sent from field to GY" trigger.
    "Cyber Shield": _equip_effect(names=("Harpie Lady", "Harpie Lady Sisters")),
    "Ancient Gear Tank": (
        *_equip_effect(name_contains=("Ancient Gear",)),
        _on_sent_to_gy((InflictDamage(OPPONENT, 600),)),  # 600 damage to the opponent
    ),
    "Fuhma Shuriken": (
        *_equip_effect(name_contains=("Ninja",)),
        _on_sent_to_gy((InflictDamage(OPPONENT, 700),)),  # 700 damage to the opponent
    ),
    "Magic Formula": (
        *_equip_effect(names=("Dark Magician", "Dark Magician Girl")),
        _on_sent_to_gy((GainLifePoints(SELF, 1000),)),  # gain 1000 LP
    ),
    # --- Effects Batch 25: Flip Effects sweep (composed from existing primitives) ---
    # timing="flip" fires via engine._trigger_flip_effect when the monster is turned
    # face-up (Flip Summon, or being attacked). These reuse targeted/typed
    # destruction, bounce, burn-per-card, the Batch 23 SS-from-Deck and Batch 15 search.
    "Old Vindictive Magician": (  # destroy 1 monster the opponent controls
        _flip(target=TargetSpec(count=1, where="opponent_monsters"), resolve=(DestroyTargets(),)),
    ),
    "White Ninja": (  # destroy 1 Defense Position monster on the field
        _flip(
            target=TargetSpec(count=1, where="any_monster", defense_position=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Armed Ninja": (  # destroy 1 Spell on the field
        _flip(
            target=TargetSpec(count=1, where="spell_trap_field", card_kind="spell"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Crimson Ninja": (  # destroy 1 Trap on the field
        _flip(
            target=TargetSpec(count=1, where="spell_trap_field", card_kind="trap"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Trap Master": (  # select 1 Trap on the field and destroy it
        _flip(
            target=TargetSpec(count=1, where="spell_trap_field", card_kind="trap"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Tornado Bird": (  # return 2 Spell/Trap Cards on the field to their owners' hands
        _flip(target=TargetSpec(count=2, where="spell_trap_field"), resolve=(BounceTargetsToHand(),)),
    ),
    # --- Batch 61: more clean Flip effects (existing primitives, no new mechanism) ---
    "Bite Shoes": (  # change the battle position of 1 face-up monster
        _flip(
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ChangeTargetPosition(to="toggle"),),
        ),
    ),
    "Gravitic Orb": (  # change the positions of all the opponent's face-up monsters
        _flip(resolve=(ChangeAllPositions(side=OPPONENT, to="toggle"),)),
    ),
    "DUCKER Mobile Cannon": (  # add 1 Level 4 monster from your GY to your hand
        _flip(
            resolve=(
                ReturnFromGraveyardToHand(CardFilter(card_kind="monster", min_level=4, max_level=4)),
            ),
        ),
    ),
    "Mask of Darkness": (  # add 1 Trap from your GY to your hand
        _flip(resolve=(ReturnFromGraveyardToHand(CardFilter(card_kind="trap")),)),
    ),
    "Rafflesia Seduction": (  # take control of 1 face-up opponent monster until the End Phase
        _flip(
            target=TargetSpec(count=1, where="opponent_monsters", face_up=True),
            resolve=(TakeControl(until_end_of_turn=True),),
        ),
    ),
    "Jowls of Dark Demise": (  # take control of 1 opponent monster until the End Phase
        _flip(
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(TakeControl(until_end_of_turn=True),),
        ),
    ),
    "Dragon Manipulator": (  # take control of 1 face-up opponent Dragon until the End Phase
        _flip(
            target=TargetSpec(
                count=1, where="opponent_monsters", face_up=True, races=frozenset({"Dragon"})
            ),
            resolve=(TakeControl(until_end_of_turn=True),),
        ),
    ),
    # --- Batch 62: more clean Flip effects (GY summon / GY->Deck / LP / count-burn) ---
    "Spirit Caller": (  # SS 1 Level 3-or-lower Normal Monster from your GY
        _flip(
            target=TargetSpec(
                count=1, where="own_graveyard_monster", normal_only=True, max_level=3
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    "Des Feral Imp": (  # shuffle 1 card from your GY into the Deck
        _flip(resolve=(ReturnFromGraveyardToDeck(CardFilter()),)),
    ),
    "Princess of Tsurugi": (  # 500 damage per Spell/Trap the opponent controls
        _flip(resolve=(InflictDamage(OPPONENT, value=CountTimes(500, "opponent_spell_trap")),)),
    ),
    "The Immortal of Thunder": (  # gain 3000 LP; when sent from field to GY, lose 5000 LP
        _flip(resolve=(GainLifePoints(SELF, 3000),)),
        _on_sent_to_gy((InflictDamage(SELF, 5000),)),
    ),
    # --- Batch 63: turn-scoped lockout Flip effects (ApplyActionLock) ---
    "Guard Dog": (  # opponent cannot Special Summon for the rest of this turn
        _flip(resolve=(ApplyActionLock(kind="special_summon", who=OPPONENT),)),
    ),
    "Sonic Jammer": (  # opponent cannot activate Spells until the end of next turn
        _flip(resolve=(ApplyActionLock(kind="spell", who=OPPONENT, extra_turns=1),)),
    ),
    "Whirlwind Weasel": (  # opponent cannot activate Spells or Traps for the rest of this turn
        _flip(
            resolve=(
                ApplyActionLock(kind="spell", who=OPPONENT),
                ApplyActionLock(kind="trap", who=OPPONENT),
            )
        ),
    ),
    "Searchlightman": (  # opponent cannot Set any cards for the rest of this turn
        _flip(resolve=(ApplyActionLock(kind="set", who=OPPONENT),)),
    ),
    "Des Koala": (  # 400 damage to the opponent for each card in their hand
        _flip(resolve=(InflictDamage(OPPONENT, value=CountTimes(400, "opponent_hand")),)),
    ),
    "Gravekeeper's Spy": (  # SS 1 "Gravekeeper's" monster with 1500 or less ATK from Deck
        _flip(
            resolve=(
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster",
                        name_contains=frozenset({"Gravekeeper's"}),
                        max_atk=1500,
                    )
                ),
            ),
        ),
    ),
    "Bubonic Vermin": (  # SS 1 "Bubonic Vermin" from the Deck in face-down Defense
        _flip(
            resolve=(
                SpecialSummonFromDeck(
                    card_filter=CardFilter(names=frozenset({"Bubonic Vermin"})),
                    position=Position.FACE_DOWN_DEFENSE,
                ),
            ),
        ),
    ),
    "Machina Defender": (  # add 1 "Commander Covington" from the Deck to the hand
        _flip(resolve=(SearchFromDeck(card_filter=CardFilter(names=frozenset({"Commander Covington"}))),)),
    ),
    # --- Effects Batch 26: more Flip Effects (banish, mill, filtered mass destroy) ---
    "Witch Doctor of Chaos": (  # banish 1 monster from either Graveyard
        _flip(target=TargetSpec(count=1, where="any_graveyard_monster"), resolve=(BanishTargets(),)),
    ),
    "Reaper of the Cards": (  # destroy 1 Trap on the field
        _flip(
            target=TargetSpec(count=1, where="spell_trap_field", card_kind="trap"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Needle Worm": (  # send the top 5 cards of the opponent's Deck to the GY
        _flip(resolve=(MillFromDeck(OPPONENT, 5),)),
    ),
    "Magnetic Mosquito": (  # destroy all face-up Machine-Type monsters on the field
        _flip(resolve=(DestroyAllMonsters(races=frozenset({"Machine"}), face_up_only=True),)),
    ),
    "4-Starred Ladybug of Doom": (  # destroy all Level 4 monsters the opponent controls
        _flip(resolve=(DestroyAllMonsters(side=OPPONENT, level=4),)),
    ),
    # --- Effects Batch 27: once-per-turn monster Ignition effects ---
    # Effect.once_per_turn gates re-use this turn (engine stamps the source);
    # disables_attack_this_turn bars the monster from attacking after it fires.
    "Neo-Spacian Air Hummingbird": (  # gain 500 LP per card in the opponent's hand
        Effect(
            timing="ignition",
            once_per_turn=True,
            resolve=(GainLifePoints(SELF, value=CountTimes(500, "opponent_hand")),),
        ),
    ),
    "Cyber Gymnast": (  # discard 1; destroy a face-up Attack Position opponent monster
        Effect(
            timing="ignition",
            once_per_turn=True,
            discard_cost=1,
            target=TargetSpec(count=1, where="opponent_monsters", attack_position=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Volcanic Slicer": (  # 500 damage, but it can't attack this turn
        Effect(
            timing="ignition",
            once_per_turn=True,
            disables_attack_this_turn=True,
            resolve=(InflictDamage(OPPONENT, 500),),
        ),
    ),
    "Super Conductor Tyranno": (  # Tribute 1 monster -> 1000 damage, can't attack this turn
        Effect(
            timing="ignition",
            once_per_turn=True,
            tribute_cost=1,
            disables_attack_this_turn=True,
            resolve=(InflictDamage(OPPONENT, 1000),),
        ),
    ),
    # Negate a monster effect: chain onto a monster-effect link and negate it, then
    # destroy that monster (NegatePreviousLink handles a monster on the Chain).
    "Divine Wrath": (  # discard 1; negate a monster effect + destroy that monster
        Effect(
            speed=3,
            timing="quick",
            discard_cost=1,
            condition=_chain_top_is_monster,
            resolve=(NegatePreviousLink(aftermath="destroy"),),
        ),
    ),
    # Negate the activation of a Spell, but return it to the hand instead of destroy.
    "Goblin Out of the Frying Pan": (  # pay 500 LP; negate a Spell + bounce it to hand
        Effect(
            speed=3,
            timing="quick",
            condition=_all_conditions(_lp_above(500), _chain_top_is_spell),
            resolve=(InflictDamage(SELF, 500, is_cost=True), NegatePreviousLink(aftermath="bounce")),
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
            trigger=Trigger(
                kind="summon",
                by=OPPONENT,
                subject="monster",
                min_atk=1000,
                summon_kinds=frozenset({"normal", "flip"}),  # not Special Summons
            ),
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
    # --- Batch 45: reactive "when an opponent's monster declares an attack" Traps ---
    # (the attack-declaration response window already exists; these all key off it)
    # Sakuretsu Armor — destroy the attacker (the attack fizzles: no attacker left).
    "Sakuretsu Armor": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(DestroyTargets(),),
        ),
    ),
    # Negate Attack — negate the attacking monster's attack (the "end the Battle Phase"
    # clause is approximated by negating just this attack).
    "Negate Attack": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(NegateAttack(),),
        ),
    ),
    # Malevolent Catastrophe — destroy all Spell/Trap Cards on the field.
    "Malevolent Catastrophe": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            resolve=(DestroyAllSpellTraps(),),
        ),
    ),
    # Widespread Ruin — destroy the opponent's highest-ATK Attack-Position monster.
    "Widespread Ruin": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            resolve=(DestroyHighestAtkMonster(side=OPPONENT),),
        ),
    ),
    # Radiant Mirror Force — only when the attacker controls 3+ Attack-Position monsters:
    # destroy all of them.
    "Radiant Mirror Force": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            condition=_opponent_controls_3plus_attack,
            resolve=(DestroyAttackingAttackPositionMonsters(),),
        ),
    ),
    # Dark Mirror Force — banish all the attacker's Defense-Position monsters.
    "Dark Mirror Force": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            resolve=(BanishAttackingDefensePositionMonsters(),),
        ),
    ),
    # --- Batch 46: battle-position change ---
    # Targeted:
    "Block Attack": (  # change 1 opponent's Attack-Position monster to Defense
        Effect(
            timing="ignition",
            target=TargetSpec(count=1, where="opponent_monsters", attack_position=True),
            resolve=(ChangeTargetPosition(to="defense"),),
        ),
    ),
    "Book of Moon": (  # Quick-Play: change 1 face-up monster to face-down Defense
        Effect(
            timing="quick",
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
    ),
    "Ready for Intercepting": (  # change 1 Warrior/Spellcaster to face-down Defense
        Effect(
            speed=2,
            timing="ignition",
            target=TargetSpec(
                count=1,
                where="any_monster",
                face_up=True,
                races=frozenset({"Warrior", "Spellcaster"}),
            ),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
    ),
    # Mass:
    "Earthquake": (  # change all face-up monsters to Defense
        Effect(timing="ignition", resolve=(ChangeAllPositions(to="defense"),)),
    ),
    "No Entry!!": (  # Normal Trap: change all face-up monsters to Defense
        Effect(speed=2, timing="ignition", resolve=(ChangeAllPositions(to="defense"),)),
    ),
    "Zero Gravity": (  # Normal Trap: rotate every face-up monster's position
        Effect(speed=2, timing="ignition", resolve=(ChangeAllPositions(to="toggle"),)),
    ),
    "Windstorm of Etaqua": (  # rotate every face-up monster the opponent controls
        Effect(
            speed=2,
            timing="ignition",
            resolve=(ChangeAllPositions(side=OPPONENT, to="toggle"),),
        ),
    ),
    # Attack-reaction (the equip "+500 ATK" mode of Kunai is omitted):
    "Kunai with Chain": (  # change the attacking monster to Defense (the attack stops)
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(ChangeTargetPosition(to="defense"),),
        ),
    ),
    # --- Batch 49: take-control-the-attack + battle-damage reflection ---
    # Magical Arm Shield — steal a non-attacking opponent monster (until the End Phase)
    # and redirect the attack onto it (the attacker battles the monster you just took).
    "Magical Arm Shield": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            condition=_controls_monster_with_free_zone,
            target=TargetSpec(
                count=1, where="opponent_monsters", face_up=True, exclude_attacker=True
            ),
            resolve=(TakeControl(until_end_of_turn=True), RedirectAttackToTarget()),
        ),
    ),
    # Dimension Wall — the Battle Damage you would take from this battle hits the attacker.
    "Dimension Wall": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            resolve=(ReflectBattleDamage(),),
        ),
    ),
    # --- Batch 50: "selected as an attack target" gate + board-state-gated attack Traps ---
    # Mirage Tube — Quick-Play, cannot be activated from hand (modelled as a Set-only
    # trigger-timed Quick-Play): when a monster you control is the attack target, burn 1000.
    "Mirage Tube": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, target_self_control=True),
            resolve=(InflictDamage(OPPONENT, 1000),),
        ),
    ),
    # Froggy Forcefield — your "Frog" (not "Frog the Jam") is the attack target: destroy
    # all the opponent's Attack-Position monsters (the attacking player's).
    "Froggy Forcefield": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(
                kind="attack_declared",
                by=OPPONENT,
                target_self_control=True,
                target_name_contains=frozenset({"Frog"}),
                target_exclude_names=frozenset({"Frog the Jam"}),
            ),
            resolve=(DestroyAttackingAttackPositionMonsters(),),
        ),
    ),
    # Justi-Break — opponent attacks your face-up Normal Monster: destroy every monster
    # except face-up Attack-Position Normal Monsters.
    "Justi-Break": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(
                kind="attack_declared",
                by=OPPONENT,
                target_self_control=True,
                target_normal_only=True,
            ),
            resolve=(DestroyAllMonsters(spare_face_up_attack_normal=True),),
        ),
    ),
    # Supercharge — opponent declares an attack while the only monsters you control are
    # Machine "roid" monsters: draw 2.
    "Supercharge": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            condition=_only_controls_roid_machines,
            resolve=(Draw(count=2),),
        ),
    ),
    # Amazoness Archers — opponent declares an attack while you control an "Amazoness":
    # switch all the opponent's monsters to Attack Position and drop them 500 ATK. (The
    # "must attack this turn" clause — a drawback for the opponent — is omitted.)
    "Amazoness Archers": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            condition=_controls_amazoness,
            resolve=(
                ChangeAllPositions(side=OPPONENT, to="attack"),
                ModifyAllStatsTemporary(side=OPPONENT, atk=-500),
            ),
        ),
    ),
    # --- Batch 51: forced attack target ---
    # Staunch Defender — when the opponent declares an attack, pick a face-up monster you
    # control: redirect the current attack onto it, and for the rest of this turn the
    # opponent may only attack that monster.
    "Staunch Defender": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            target=TargetSpec(count=1, where="own_monsters", face_up=True),
            resolve=(RedirectAttackToTarget(), ForceAttackTarget()),
        ),
    ),
    # --- Batch 52: Special Summon from the hand on an attack ---
    # A Hero Emerges — reveal 1 random card from your hand; if it's a freely-summonable
    # monster, Special Summon it, otherwise send it to the Graveyard.
    "A Hero Emerges": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            condition=_has_card_in_hand,
            resolve=(RevealRandomHandCardSummonOrGY(),),
        ),
    ),
    # Relieve Monster — return 1 monster you control to the hand, then Special Summon 1
    # Level 4-or-lower monster from your hand.
    "Relieve Monster": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            target=TargetSpec(count=1, where="own_monsters"),
            resolve=(
                BounceTargetsToHand(),
                SpecialSummonFromHand(card_filter=CardFilter(card_kind="monster", max_level=4)),
            ),
        ),
    ),
    # --- Batch 53: was-Tribute-Summoned gate ---
    # Blast Held by a Tribute — when a Tribute-Summoned opponent monster attacks, destroy
    # all their face-up Attack-Position monsters and burn 1000.
    "Blast Held by a Tribute": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(
                kind="attack_declared", by=OPPONENT, attacker_was_tribute_summoned=True
            ),
            resolve=(DestroyAttackingAttackPositionMonsters(), InflictDamage(OPPONENT, 1000)),
        ),
    ),
    # --- Batch 54: monster "when this declares an attack" (condition-gated) ---
    # Gravekeeper's Assailant — when it attacks while "Necrovalley" is on the field, flip
    # an opponent's monster's battle position. Fires via engine._fire_attack_declared_trigger.
    "Gravekeeper's Assailant": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=SELF),
            condition=_necrovalley_on_field,
            target=TargetSpec(count=1, where="opponent_monsters", face_up=True),
            resolve=(ChangeTargetPosition(to="toggle"),),
        ),
    ),
    # --- Batch 48: attack redirect / cost-bearing attack Trap ---
    # Call of the Earthbound — redirect the attack to a monster you choose to control.
    "Call of the Earthbound": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            target=TargetSpec(count=1, where="own_monsters"),
            resolve=(RedirectAttackToTarget(),),
        ),
    ),
    # Jam Defender — redirect the attack to your "Revival Jam".
    "Jam Defender": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT),
            target=TargetSpec(
                count=1, where="own_monsters", name_contains=frozenset({"Revival Jam"})
            ),
            resolve=(RedirectAttackToTarget(),),
        ),
    ),
    # Chaos Burst — Tribute 1 monster; destroy the attacker, then 1000 damage.
    "Chaos Burst": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            tribute_cost=1,
            resolve=(DestroyTargets(), InflictDamage(OPPONENT, 1000)),
        ),
    ),
    # --- Batch 47: coin-flip (CoinFlip RNG primitive; calling is 50/50 -> heads) ---
    # Jirai Gumo — when it declares an attack, coin toss; wrong -> lose half your LP.
    "Jirai Gumo": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=SELF),
            resolve=(CoinFlip(lose=(LoseHalfLifePoints(SELF),)),),
        ),
    ),
    # Abare Ushioni — once/turn: coin toss; right -> 1000 to opponent, wrong -> 1000 to you.
    "Abare Ushioni": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            resolve=(
                CoinFlip(win=(InflictDamage(OPPONENT, 1000),), lose=(InflictDamage(SELF, 1000),)),
            ),
        ),
    ),
    # Cup of Ace — coin toss; heads -> you draw 2, tails -> opponent draws 2.
    "Cup of Ace": (
        Effect(
            timing="ignition",
            resolve=(CoinFlip(win=(Draw(SELF, 2),), lose=(Draw(OPPONENT, 2),)),),
        ),
    ),
    # Barrel Dragon — once/turn: target 1 opponent monster; 3 tosses, 2+ heads -> destroy it.
    "Barrel Dragon": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(CoinFlip(win=(DestroyTargets(),), count=3, win_threshold=2),),
        ),
    ),
    # Blowback Dragon — once/turn: target 1 opponent card; 3 tosses, 2+ heads -> destroy it.
    "Blowback Dragon": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            target=TargetSpec(count=1, where="opponent_card_field"),
            resolve=(CoinFlip(win=(DestroyTargets(),), count=3, win_threshold=2),),
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
        # "regardless of position"
        _flip(target=TargetSpec(count=1, where="any_monster"), resolve=(DestroyTargets(),)),
    ),
    "Magician of Faith": (_flip(resolve=(ReturnSpellFromGraveyardToHand(),)),),
    # --- Effects Batch 4: more clean Flip effects (reuse the flip timing) ---
    "Poison Mummy": (_flip(resolve=(InflictDamage(OPPONENT, 500),)),),
    "Skelengel": (_flip(resolve=(Draw(count=1),)),),
    "Nobleman-Eater Bug": (
        # you select 2 to destroy
        _flip(target=TargetSpec(count=2, where="any_monster"), resolve=(DestroyTargets(),)),
    ),
    "Sangan": (_on_sent_to_gy((SearchMonsterToHand(1500),)),),
    # Dandylion — sent from the field to the GY: 2 Fluff Tokens (Plant/WIND/L1/0/0).
    "Dandylion": (
        _on_sent_to_gy(
            (
                CreateToken(
                    token_name="Fluff Token",
                    count=2,
                    position=Position.FACE_UP_DEFENSE,
                    race="Plant",
                    attribute=Attribute.WIND,
                    level=1,
                ),
            )
        ),
    ),
    # --- Batch 32: banish-from-GY activation cost ---
    # Dark Armed Dragon: banish 1 DARK monster from your GY, then destroy 1 card on
    # the field (its hand_summon condition is in HAND_SUMMONS / Batch 29).
    "Dark Armed Dragon": (
        Effect(
            timing="ignition",
            banish_from_gy_cost=1,
            banish_from_gy_filter=CardFilter(card_kind="monster", attributes=frozenset({Attribute.DARK})),
            target=TargetSpec(count=1, where="any_card_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    # Lekunga: banish 2 WATER monsters from your GY; Special Summon 1 Lekunga Token
    # (Plant/WATER/L2/700/700). The "you can only control 1" limit is not modelled.
    "Lekunga": (
        Effect(
            timing="ignition",
            banish_from_gy_cost=2,
            banish_from_gy_filter=CardFilter(card_kind="monster", attributes=frozenset({Attribute.WATER})),
            condition=_has_free_monster_zone,
            resolve=(
                CreateToken(
                    token_name="Lekunga Token",
                    count=1,
                    race="Plant",
                    attribute=Attribute.WATER,
                    level=2,
                    atk=700,
                    defn=700,
                ),
            ),
        ),
    ),
    # --- Batch 33: recover cards from your Graveyard (to hand / to Deck) ---
    # Quick Charger — Quick-Play: add 2 Level-4-or-lower "Batteryman" from GY to hand.
    "Quick Charger": (
        Effect(
            speed=2,
            timing="quick",
            condition=_gy_has_match(
                CardFilter(card_kind="monster", name_contains=frozenset({"Batteryman"}), max_level=4)
            ),
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(
                        card_kind="monster", name_contains=frozenset({"Batteryman"}), max_level=4
                    ),
                    count=2,
                ),
            ),
        ),
    ),
    # Ray of Hope — Normal Trap: add 2 LIGHT monsters from your GY to the Deck, shuffle.
    "Ray of Hope": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_gy_has_match(CardFilter(card_kind="monster", attributes=frozenset({Attribute.LIGHT}))),
            resolve=(
                ReturnFromGraveyardToDeck(
                    card_filter=CardFilter(card_kind="monster", attributes=frozenset({Attribute.LIGHT})),
                    count=2,
                ),
            ),
        ),
    ),
    # Volcanic Recharge — Normal Trap: return up to 3 "Volcanic" monsters to the Deck.
    "Volcanic Recharge": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_gy_has_match(CardFilter(card_kind="monster", name_contains=frozenset({"Volcanic"}))),
            resolve=(
                ReturnFromGraveyardToDeck(
                    card_filter=CardFilter(card_kind="monster", name_contains=frozenset({"Volcanic"})),
                    count=3,
                ),
            ),
        ),
    ),
    # Monster Eye — monster Ignition: pay 1000 LP; add 1 "Polymerization" from GY to hand.
    "Monster Eye": (
        Effect(
            timing="ignition",
            life_cost=1000,
            condition=_gy_has_match(CardFilter(names=frozenset({"Polymerization"}))),
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(names=frozenset({"Polymerization"})), count=1
                ),
            ),
        ),
    ),
    # --- Batch 34: burn/gain scaling with a Graveyard count ---
    # Magical Explosion — Normal Trap: with an empty hand, 200 damage per Spell in your GY.
    "Magical Explosion": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_no_cards_in_hand,
            resolve=(
                InflictDamage(
                    OPPONENT,
                    value=CountTimes(200, "own_graveyard", card_filter=CardFilter(card_kind="spell")),
                ),
            ),
        ),
    ),
    # Volcanic Hammerer — monster Ignition: 200 damage per "Volcanic" monster in your GY,
    # then it cannot attack this turn (once per turn).
    "Volcanic Hammerer": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            disables_attack_this_turn=True,
            resolve=(
                InflictDamage(
                    OPPONENT,
                    value=CountTimes(
                        200,
                        "own_graveyard",
                        card_filter=CardFilter(card_kind="monster", name_contains=frozenset({"Volcanic"})),
                    ),
                ),
            ),
        ),
    ),
    # Cemetary Bomb — Normal Trap: 100 damage per card in the OPPONENT's GY (existing pool).
    "Cemetary Bomb": (
        Effect(
            speed=2,
            timing="ignition",
            resolve=(InflictDamage(OPPONENT, value=CountTimes(100, "opponent_graveyard")),),
        ),
    ),
    # Full Salvo — Normal Trap: send your whole hand to the GY, 200 damage per card sent.
    "Full Salvo": (
        Effect(speed=2, timing="ignition", resolve=(DiscardHandThenBurn(per=200),)),
    ),
    # --- Batch 35: hand disruption (look at the opponent's hand, then strip it) ---
    # Confiscation — pay 1000 LP; look at the opponent's hand and discard 1 (you pick).
    "Confiscation": (
        Effect(
            timing="ignition",
            life_cost=1000,
            condition=_opponent_has_hand_cards,
            resolve=(DiscardFromHand(OPPONENT, count=1),),
        ),
    ),
    # Delinquent Duo — pay 1000 LP; opponent discards 1 random, then 1 more (if any left).
    "Delinquent Duo": (
        Effect(
            timing="ignition",
            life_cost=1000,
            condition=_opponent_has_hand_cards,
            resolve=(
                DiscardFromHand(OPPONENT, count=1, random=True),
                DiscardFromHand(OPPONENT, count=1),
            ),
        ),
    ),
    # The Forceful Sentry — look at the opponent's hand; return 1 card to their Deck.
    "The Forceful Sentry": (
        Effect(
            timing="ignition",
            condition=_opponent_has_hand_cards,
            resolve=(ReturnFromHandToDeck(OPPONENT, count=1),),
        ),
    ),
    # Trap Dustshoot — Normal Trap: only if the opponent holds 4+ cards; return 1
    # Monster from their hand to the Deck.
    "Trap Dustshoot": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_opponent_hand_at_least_with_monster(4),
            resolve=(ReturnFromHandToDeck(OPPONENT, count=1, monsters_only=True),),
        ),
    ),
    # --- Batch 36: "when this inflicts battle damage to your opponent" triggers ---
    # The engine fires a SELF "battle_damage_inflicted" Trigger after combat (see
    # engine._fire_battle_damage_trigger). Cards offering a *choice* of effects model
    # one representative mode (noted per card).
    # Airknight Parshath: draw 1 (its piercing rider is the CONTINUOUS entry above).
    "Airknight Parshath": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="battle_damage_inflicted", by=SELF),
            resolve=(Draw(count=1),),
        ),
    ),
    # Don Zaloog: discard 1 random card from the opponent's hand (the deck-mill mode
    # of its "1 of these effects" choice is not modelled).
    "Don Zaloog": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="battle_damage_inflicted", by=SELF),
            resolve=(DiscardFromHand(OPPONENT, count=1, random=True),),
        ),
    ),
    # Dark Scorpion - Chick the Yellow: return 1 card on the field to the hand (the
    # look-at-top-of-Deck mode is not modelled).
    "Dark Scorpion - Chick the Yellow": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="battle_damage_inflicted", by=SELF),
            target=TargetSpec(count=1, where="any_card_field"),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    # --- Batch 37: more "inflicts battle damage" monsters (existing primitives) ---
    "Masked Sorcerer": (_on_battle_damage((Draw(count=1),)),),  # draw 1
    "The Bistro Butcher": (_on_battle_damage((Draw(OPPONENT, count=2),)),),  # opp draws 2
    "White Magical Hat": (  # opponent discards 1 random
        _on_battle_damage((DiscardFromHand(OPPONENT, count=1, random=True),)),
    ),
    "Goe Goe the Gallant Ninja": (  # opponent discards 2 random
        _on_battle_damage((DiscardFromHand(OPPONENT, count=2, random=True),)),
    ),
    "Blood Sucker": (_on_battle_damage((MillFromDeck(OPPONENT, count=1),)),),  # mill 1
    # Goblin Zombie: mill 1 (its "when sent to GY, recover a Zombie" half is not modelled).
    "Goblin Zombie": (_on_battle_damage((MillFromDeck(OPPONENT, count=1),)),),
    # Spirit Reaper: opponent discards 1 random on battle damage (it's also
    # battle-indestructible — see CONTINUOUS).
    "Spirit Reaper": (_on_battle_damage((DiscardFromHand(OPPONENT, count=1, random=True),)),),
    # --- Batch 66: "when this card destroys a monster by battle" SELF Triggers ---
    # The engine fires a SELF "destroys_by_battle" Trigger after combat for each monster
    # that destroyed an opponent's monster (engine._fire_destroys_by_battle_trigger); the
    # event's "destroyed" iid lets the payload read the dead monster's original ATK / banish it.
    # Masked Chopper: burn the opponent 2000.
    "Masked Chopper": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(InflictDamage(OPPONENT, 2000),),
        ),
    ),
    # Guardian Angel Joan: gain LP equal to the destroyed monster's original ATK.
    "Guardian Angel Joan": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(GainLifePoints(SELF, value=DestroyedByBattleAttack()),),
        ),
    ),
    # Hydrogeddon: Special Summon another "Hydrogeddon" from your Deck (the recruit is
    # deterministic, as with the battle-recruiters).
    "Hydrogeddon": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(SpecialSummonFromDeck(CardFilter(names=frozenset({"Hydrogeddon"})),),),
        ),
    ),
    # Divine Knight Ishzark: banish the monster it destroyed (instead of leaving it in the GY).
    "Divine Knight Ishzark": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(BanishEventMonster(),),
        ),
    ),
    # Blue Thunder T-45: Special Summon 1 "Thunder Option Token" (Machine/LIGHT/Lv4/
    # 1500/1500). The "cannot be Tributed for a Tribute Summon" rider is not modelled.
    "Blue Thunder T-45": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(
                CreateToken(
                    token_name="Thunder Option Token",
                    race="Machine",
                    attribute=Attribute.LIGHT,
                    level=4,
                    atk=1500,
                    defn=1500,
                ),
            ),
        ),
    ),
    # --- Slice 5: Equip Spells — activate (target a monster) then stay attached ---
    "Axe of Despair": _equip_effect(),
    "United We Stand": _equip_effect(),
    "Mage Power": _equip_effect(),
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
    # --- Batch 28: reborn-style Spell/Traps (SS another monster from a Graveyard) ---
    # Premature Burial — Equip Spell: pay 800 LP, revive any monster from your GY in
    # Attack and bond to it (it dies if this Equip leaves the field).
    "Premature Burial": (
        Effect(
            timing="ignition",
            life_cost=800,
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster"),
            resolve=(SpecialSummonFromGraveyard(link=True),),
        ),
    ),
    # Birthright — Continuous Trap: revive a Normal Monster from your GY in Attack.
    "Birthright": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster", normal_only=True),
            resolve=(SpecialSummonFromGraveyard(link=True),),
        ),
    ),
    # Silent Doom — Normal Spell: revive a Normal Monster from your GY in Defense
    # (a Defense-Position monster can't declare attacks — the card's "cannot attack").
    "Silent Doom": (
        Effect(
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster", normal_only=True),
            resolve=(SpecialSummonFromGraveyard(position=Position.FACE_UP_DEFENSE),),
        ),
    ),
    # Soul Resurrection — Continuous Trap: revive a Normal Monster in Defense, bonded.
    "Soul Resurrection": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster", normal_only=True),
            resolve=(SpecialSummonFromGraveyard(link=True, position=Position.FACE_UP_DEFENSE),),
        ),
    ),
    # Limit Reverse — Continuous Trap: revive a 1000-or-less-ATK monster in Attack,
    # bonded (the position-change destruction rider is not modelled).
    "Limit Reverse": (
        Effect(
            speed=2,
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster", max_atk=1000),
            resolve=(SpecialSummonFromGraveyard(link=True),),
        ),
    ),
    # O - Oversoul — Normal Spell: revive an "Elemental HERO" Normal Monster.
    "O - Oversoul": (
        Effect(
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(
                count=1,
                where="own_graveyard_monster",
                normal_only=True,
                name_contains=frozenset({"Elemental HERO"}),
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    # Fossil Excavation — Continuous Trap: discard 1, revive a Dinosaur from your GY,
    # bonded (the "negate its effects" rider is not modelled).
    "Fossil Excavation": (
        Effect(
            speed=2,
            timing="ignition",
            discard_cost=1,
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster", races=frozenset({"Dinosaur"})),
            resolve=(SpecialSummonFromGraveyard(link=True),),
        ),
    ),
    # Autonomous Action Unit — Equip Spell: pay 1500 LP, steal a monster from the
    # OPPONENT's GY to your side in Attack, bonded.
    "Autonomous Action Unit": (
        Effect(
            timing="ignition",
            life_cost=1500,
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="opponent_graveyard_monster"),
            resolve=(SpecialSummonFromGraveyard(link=True),),
        ),
    ),
    # --- Batch 30: Token generators (CreateToken). The "you cannot Summon other
    # monsters this turn" / "cannot be Tributed" riders are not modelled. ---
    "Scapegoat": (  # Quick-Play: 4 Sheep Tokens (Beast/EARTH/L1/0/0) in Defense
        Effect(
            speed=2,
            timing="quick",
            condition=_has_free_monster_zone,
            resolve=(
                CreateToken(
                    token_name="Sheep Token",
                    count=4,
                    position=Position.FACE_UP_DEFENSE,
                    race="Beast",
                    attribute=Attribute.EARTH,
                    level=1,
                ),
            ),
        ),
    ),
    "Fires of Doomsday": (  # Quick-Play: 2 Doomsday Tokens (Fiend/DARK/L1/0/0) Defense
        Effect(
            speed=2,
            timing="quick",
            condition=_has_free_monster_zone,
            resolve=(
                CreateToken(
                    token_name="Doomsday Token",
                    count=2,
                    position=Position.FACE_UP_DEFENSE,
                    race="Fiend",
                    attribute=Attribute.DARK,
                    level=1,
                ),
            ),
        ),
    ),
    "Fiend's Sanctuary": (  # Normal Spell: 1 Metal Fiend Token (Fiend/DARK/L1/0/0)
        Effect(
            timing="ignition",
            condition=_has_free_monster_zone,
            resolve=(
                CreateToken(
                    token_name="Metal Fiend Token",
                    count=1,
                    race="Fiend",
                    attribute=Attribute.DARK,
                    level=1,
                ),
            ),
        ),
    ),
    "Ojama Trio": (  # Normal Trap: 3 Ojama Tokens (Beast/LIGHT/L2/0/1000) to OPPONENT
        Effect(
            speed=2,
            timing="ignition",
            condition=_opponent_has_free_monster_zone,
            resolve=(
                CreateToken(
                    token_name="Ojama Token",
                    count=3,
                    position=Position.FACE_UP_DEFENSE,
                    to_opponent=True,
                    race="Beast",
                    attribute=Attribute.LIGHT,
                    level=2,
                    defn=1000,
                ),
            ),
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
    # Marshmallon Glasses — Continuous Spell: while "Marshmallon" is in your Monster
    # Zone, the opponent can only attack your Marshmallon (the protection is in CONTINUOUS).
    "Marshmallon Glasses": _ACTIVATE_ONTO_FIELD,
    # --- Batch 42: class-negating Continuous Traps (the negation lives in CONTINUOUS) ---
    # Royal Decree negates all other Trap effects; Imperial Order negates all Spell
    # effects (+ a Standby pay-700-or-die upkeep). Both just need to reach the field.
    "Royal Decree": _ACTIVATE_ONTO_FIELD,
    "Imperial Order": _ACTIVATE_ONTO_FIELD,
    # --- Batch 43: Skill Drain — Continuous Trap, pay 1000 LP to activate (the
    # monster-effect negation lives in CONTINUOUS).
    "Skill Drain": (Effect(timing="ignition", life_cost=1000),),
    # --- Batch 44: "destroy all Special Summoned monsters" floodgates ---
    # Fossil Dyna Pachycephalo — Flip: destroy every Special-Summoned monster on the
    # field (the continuous "neither player can Special Summon" lock is in CONTINUOUS).
    "Fossil Dyna Pachycephalo": (_flip((DestroyAllSpecialSummoned(),)),),
    # Jowgen the Spiritualist — Ignition: discard 1 -> destroy all Special-Summoned
    # monsters (the continuous SS lock is in CONTINUOUS). The pool's "1 random" discard
    # is modelled as a chosen discard cost (minor).
    "Jowgen the Spiritualist": (
        Effect(
            timing="ignition",
            discard_cost=1,
            condition=_any_special_summoned_monster,
            resolve=(DestroyAllSpecialSummoned(),),
        ),
    ),
    # Special Hurricane — Normal Spell: discard 1 -> destroy all Special-Summoned monsters.
    "Special Hurricane": (
        Effect(
            timing="ignition",
            discard_cost=1,
            condition=_any_special_summoned_monster,
            resolve=(DestroyAllSpecialSummoned(),),
        ),
    ),
    # --- Batch 65: Standby-Phase effects (StandbyTrigger; payloads in CONTINUOUS) ---
    # Minor Goblin Official — Continuous Trap: activate only while the opponent is at
    # 3000 LP or less; thereafter it burns them 500 each of THEIR Standby Phases.
    "Minor Goblin Official": (Effect(timing="ignition", condition=_opp_lp_at_most(3000)),),
    # Burning Land — Continuous Spell: activating it wipes every Field Spell, then
    # it burns the active player 500 each Standby (the burn lives in CONTINUOUS).
    "Burning Land": (Effect(timing="ignition", resolve=(DestroyAllFieldSpells(),)),),
    # --- Slice 17: Toon World — Continuous Spell, pay 1000 LP to activate ---
    # While it's face-up it enables your Toon monsters (the engine checks for it by
    # name); if it leaves the field, your Toon monsters are destroyed.
    "Toon World": (
        Effect(timing="ignition", condition=_lp_above(1000), resolve=(InflictDamage(SELF, 1000, is_cost=True),)),
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
# The Chaos cost: banish 1 LIGHT *and* 1 DARK monster from your Graveyard.
_CHAOS_BANISH = (
    SummonCost(count=1, card_filter=CardFilter(card_kind="monster", attributes=frozenset({Attribute.LIGHT}))),
    SummonCost(count=1, card_filter=CardFilter(card_kind="monster", attributes=frozenset({Attribute.DARK}))),
)

HAND_SUMMONS: dict[str, HandSpecialSummon] = {
    "Cyber Dragon": HandSpecialSummon(condition=_only_opponent_controls_monster),
    "The Fiend Megacyber": HandSpecialSummon(condition=_opponent_controls_at_least_more(2)),
    "Ancient Gear": HandSpecialSummon(condition=_controls_named_face_up("Ancient Gear")),
    # --- Batch 29: cost/condition self-Special-Summon (cannot be Normal Summoned) ---
    # The Chaos monsters: banish 1 LIGHT + 1 DARK from the GY (their on-field effects
    # are deferred to a later batch; this makes them reach the field legally).
    "Black Luster Soldier - Envoy of the Beginning": HandSpecialSummon(
        cannot_normal_summon=True, banish_costs=_CHAOS_BANISH
    ),
    "Chaos Emperor Dragon - Envoy of the End": HandSpecialSummon(
        cannot_normal_summon=True, banish_costs=_CHAOS_BANISH
    ),
    "Chaos Sorcerer": HandSpecialSummon(
        cannot_normal_summon=True, banish_costs=_CHAOS_BANISH
    ),
    # Dark Armed Dragon: SS by *having exactly 3 DARK monsters* in the GY (a board
    # condition, no banish cost for the Summon itself).
    "Dark Armed Dragon": HandSpecialSummon(
        cannot_normal_summon=True, condition=_exactly_n_attr_in_gy(3, Attribute.DARK)
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
    # --- Effects Batch 19: Equips with a "sent to GY" parting effect (above) ---
    "Black Pendant": (EquipMod(atk=500),),
    "Horn of the Unicorn": (EquipMod(atk=700, defn=700),),
    # --- Effects Batch 20: Spell Counter holders ---
    # Royal Magical Library accumulates up to 3 Spell Counters (its draw cost).
    "Royal Magical Library": (SpellCounterHolder(max_counters=3),),
    # Mythical Beast Cerberus: no cap, +500 ATK per counter, wiped after it battles.
    "Mythical Beast Cerberus": (
        SpellCounterHolder(per_counter_atk=500, wipe_after_battle=True),
    ),
    # --- Effects Batch 21: Breaker-family Spell Counter holders ---
    # Breaker: holds its single summon-placed counter (max 1, non-accumulating),
    # +300 ATK while it carries it.
    "Breaker the Magical Warrior": (
        SpellCounterHolder(max_counters=1, per_counter_atk=300, accumulates=False),
    ),
    # Hannibal Necromancer: max 1, non-accumulating, no stat rider.
    "Hannibal Necromancer": (
        SpellCounterHolder(max_counters=1, accumulates=False),
    ),
    # --- Effects Batch 22: Ultimate Baseball Kid's scaling self-boost ---
    # +1000 ATK for each OTHER face-up FIRE monster on the field (both sides).
    "Ultimate Baseball Kid": (
        SelfStatMod(
            scaling="face_up_attr_monsters", scale_atk=1000, count_attribute=Attribute.FIRE
        ),
    ),
    # Airknight Parshath: piercing rider (the draw-on-damage trigger is in EFFECTS).
    "Airknight Parshath": (Piercing(),),
    # --- Batch 38: battle modifiers (direct attack / cannot be destroyed by battle) ---
    # Direct attackers (secondary riders — Goblin's end-Battle position change, Raging
    # Flame Sprite's ATK growth — are not modelled).
    "Goblin Black Ops": (CanAttackDirectly(), DefenseAfterAttack(lock_position=True)),
    "Raging Flame Sprite": (CanAttackDirectly(),),
    # Battle-indestructible (Arcana Force 0's no-position-change, Marshmallon's flipped
    # 1000 burn, and Spirit Reaper's destroy-when-targeted riders are not modelled).
    "Arcana Force 0 - The Fool": (BattleIndestructible(),),
    "Marshmallon": (BattleIndestructible(),),
    "Spirit Reaper": (BattleIndestructible(),),  # its battle-damage discard is in EFFECTS
    # --- Batch 39: attack twice (MultiAttacker; secondary riders not modelled) ---
    "Hayabusa Knight": (MultiAttacker(),),
    "Mataza the Zapper": (MultiAttacker(),),
    "Twinheaded Beast": (MultiAttacker(),),
    # --- Batch 40: attack-target protection ("cannot be selected as an attack target") ---
    # Decoyroid: the opponent must attack it — every OTHER monster you control is
    # protected (a pure decoy).
    "Decoyroid": (AttackTargetProtection(exclude_self=True),),
    # Marauding Captain: your other Warriors can't be attacked (only the Captain).
    # Its optional "on Normal Summon, SS a Lv4- monster from hand" rider is not modelled.
    "Marauding Captain": (AttackTargetProtection(race="Warrior", exclude_self=True),),
    # Queen's Bodyguard: "Allure Queen" monsters you control can't be attacked.
    "Queen's Bodyguard": (AttackTargetProtection(name_contains="Allure Queen"),),
    # Marshmallon Glasses (Continuous Spell): while you control "Marshmallon", the
    # opponent can only attack your Marshmallon — every other monster is protected.
    "Marshmallon Glasses": (
        AttackTargetProtection(
            exclude_name_contains="Marshmallon",
            requires_control_name_contains="Marshmallon",
        ),
    ),
    # --- Batch 41: Special Summon locks (Barrier Statues / Vanity) ---
    # The "Cannot be Special Summoned" clause restricting each Vanity monster *itself*
    # is a card-level summon restriction the engine doesn't track yet (minor).
    "Vanity's Fiend": (SpecialSummonLock(whose="both"),),
    "Vanity's Ruler": (SpecialSummonLock(whose="opponent"),),
    "Barrier Statue of the Inferno": (
        SpecialSummonLock(whose="both", except_attribute=Attribute.FIRE),
    ),
    "Barrier Statue of the Torrent": (
        SpecialSummonLock(whose="both", except_attribute=Attribute.WATER),
    ),
    # --- Batch 42: negate-while-face-up locks (whole Spell/Trap class negators) ---
    # Jinzo (monster): Traps "cannot be activated", and all Trap effects on the field
    # are negated — both sides. (Amplifier's "doesn't negate its controller's Traps"
    # rider is not modelled.)
    "Jinzo": (CardEffectNegation(negates="trap", prevent_activation=True, whose="both"),),
    # Spell Canceller (monster): the Spell-side mirror — Spells cannot be activated and
    # all Spell effects on the field are negated, both sides.
    "Spell Canceller": (
        CardEffectNegation(negates="spell", prevent_activation=True, whose="both"),
    ),
    # Royal Decree (Continuous Trap): negate all OTHER Trap effects on the field — Traps
    # can still be activated, but their effects do nothing (exclude_self keeps Decree live).
    "Royal Decree": (
        CardEffectNegation(negates="trap", prevent_activation=False, whose="both"),
    ),
    # Imperial Order (Continuous Trap): negate all Spell effects on the field (Spells still
    # activate, then do nothing). Standby cost: pay 700 LP or it is destroyed — modelled
    # by StandbyUpkeep (the engine auto-pays when able; the "you may let it die" choice is
    # not offered).
    "Imperial Order": (
        CardEffectNegation(negates="spell", prevent_activation=False, whose="both"),
        StandbyUpkeep(pay_life=700, whose="controller"),
    ),
    # --- Batch 43: Skill Drain — negate the effects of ALL face-up monsters, both
    # sides, while they are face-up (their effects can still be activated). Suppresses
    # every face-up monster's continuous riders and negates its effects on resolution.
    "Skill Drain": (
        CardEffectNegation(negates="monster", prevent_activation=False, whose="both"),
    ),
    # --- Batch 44: SS-floodgate monsters — "neither player can Special Summon" while
    # face-up (the one-shot "destroy all SS monsters" half lives in EFFECTS).
    "Fossil Dyna Pachycephalo": (SpecialSummonLock(whose="both"),),
    "Jowgen the Spiritualist": (SpecialSummonLock(whose="both"),),
    # --- Batch 31: continuous ATK scaling by the controller's own Graveyard ---
    # Chaos Necromancer: base 0 ATK, so its ATK *is* 300 x (monsters in your GY).
    "Chaos Necromancer": (SelfStatMod(scaling="graveyard_monsters", scale_atk=300),),
    # Shadow Ghoul: +100 ATK per monster in your GY.
    "Shadow Ghoul": (SelfStatMod(scaling="graveyard_monsters", scale_atk=100),),
    # Mudora: +200 ATK per Fairy-Type monster in your GY.
    "Mudora": (SelfStatMod(scaling="graveyard_monsters", scale_atk=200, count_race="Fairy"),),
    # Beelze Frog: +300 ATK per "T.A.D.P.O.L.E." in your GY.
    "Beelze Frog": (
        SelfStatMod(scaling="graveyard_monsters", scale_atk=300, count_name_contains="T.A.D.P.O.L.E."),
    ),
    # Grass Phantom: +500 ATK per "Grass Phantom" in your GY.
    "Grass Phantom": (
        SelfStatMod(scaling="graveyard_monsters", scale_atk=500, count_name_contains="Grass Phantom"),
    ),
    # --- Batch 55: continuous ATK scaling by the controller's own face-up monsters ---
    # Amazoness Paladin: +100 ATK per "Amazoness" monster you control (counts itself).
    "Amazoness Paladin": (
        SelfStatMod(scaling="controlled_monsters", scale_atk=100, count_name_contains="Amazoness"),
    ),
    # Amazoness Tiger: +400 ATK per "Amazoness" you control, and the opponent can't attack
    # any face-up "Amazoness" except this one ("you can only control 1" omitted).
    "Amazoness Tiger": (
        SelfStatMod(scaling="controlled_monsters", scale_atk=400, count_name_contains="Amazoness"),
        AttackTargetProtection(name_contains="Amazoness", exclude_self=True),
    ),
    # Botanical Lion: +300 ATK per Plant-Type monster you control ("control can't switch" omitted).
    "Botanical Lion": (
        SelfStatMod(scaling="controlled_monsters", scale_atk=300, count_race="Plant"),
    ),
    # Elemental HERO Heat: +200 ATK per "Elemental HERO" monster you control.
    "Elemental HERO Heat": (
        SelfStatMod(scaling="controlled_monsters", scale_atk=200, count_name_contains="Elemental HERO"),
    ),
    # Lava Battleguard: +500 ATK per "Swamp Battleguard" you control (counts its partner).
    "Lava Battleguard": (
        SelfStatMod(scaling="controlled_monsters", scale_atk=500, count_name_contains="Swamp Battleguard"),
    ),
    # Swamp Battleguard: +500 ATK per "Lava Battleguard" you control.
    "Swamp Battleguard": (
        SelfStatMod(scaling="controlled_monsters", scale_atk=500, count_name_contains="Lava Battleguard"),
    ),
    # --- Batch 56: monster-borne attribute anthems (field-wide, both sides) ---
    # The elemental boosters: +500 ATK to one Attribute, -400 ATK to the opposing one.
    "Bladefly": (
        FieldMod(atk=500, attributes=frozenset({Attribute.WIND})),
        FieldMod(atk=-400, attributes=frozenset({Attribute.EARTH})),
    ),
    "Milus Radiant": (
        FieldMod(atk=500, attributes=frozenset({Attribute.EARTH})),
        FieldMod(atk=-400, attributes=frozenset({Attribute.WIND})),
    ),
    "Star Boy": (
        FieldMod(atk=500, attributes=frozenset({Attribute.WATER})),
        FieldMod(atk=-400, attributes=frozenset({Attribute.FIRE})),
    ),
    "Witch's Apprentice": (
        FieldMod(atk=500, attributes=frozenset({Attribute.DARK})),
        FieldMod(atk=-400, attributes=frozenset({Attribute.LIGHT})),
    ),
    # --- Batch 57: conditional flat self-ATK (gated SelfStatMod) ---
    # Boot-Up Soldier - Dread Dynamo: +2000 ATK while you control a "Gadget" monster.
    "Boot-Up Soldier - Dread Dynamo": (
        SelfStatMod(atk=2000, active_if_control_name_contains="Gadget"),
    ),
    # Cybernetic Cyclopean: +1000 ATK while you have no cards in your hand.
    "Cybernetic Cyclopean": (SelfStatMod(atk=1000, active_if_hand_at_most=0),),
    # Theban Nightmare: +1500 ATK while you have no cards in hand nor in your S/T Zones.
    "Theban Nightmare": (
        SelfStatMod(atk=1500, active_if_hand_at_most=0, active_if_empty_spell_trap=True),
    ),
    # --- Batch 58: Damage-Step combat pumps (DamageStepBonus rider) ---
    # Cipher Soldier: +2000 ATK/DEF while it battles a Warrior-Type monster.
    "Cipher Soldier": (
        DamageStepBonus(atk=2000, defn=2000, when="either", vs_race="Warrior"),
    ),
    # Etoile Cyber: +500 ATK when it attacks directly.
    "Etoile Cyber": (DamageStepBonus(atk=500, when="attacking", vs_direct=True),),
    # Insect Soldiers of the Sky: +1000 ATK when it attacks a WIND monster.
    "Insect Soldiers of the Sky": (
        DamageStepBonus(atk=1000, when="attacking", vs_attribute=Attribute.WIND),
    ),
    # Penumbral Soldier Lady: +1000 ATK while it battles a LIGHT monster.
    "Penumbral Soldier Lady": (
        DamageStepBonus(atk=1000, when="either", vs_attribute=Attribute.LIGHT),
    ),
    # Steamroid: +500 ATK attacking a monster, -500 ATK when attacked.
    "Steamroid": (
        DamageStepBonus(atk=500, when="attacking"),
        DamageStepBonus(atk=-500, when="attacked"),
    ),
    # Black Veloci: +400 ATK attacking a monster, -400 ATK when attacked.
    "Black Veloci": (
        DamageStepBonus(atk=400, when="attacking"),
        DamageStepBonus(atk=-400, when="attacked"),
    ),
    # --- Batch 59: archetype/race anthems + "lord shields itself" ---
    # Command Knight: all your Warriors +400 ATK; while you control another monster, the
    # opponent can't target Command Knight for attacks.
    "Command Knight": (
        FieldMod(atk=400, races=frozenset({"Warrior"}), side="self"),
        AttackTargetProtection(self_only=True, requires_control_other=True),
    ),
    # Freya, Spirit of Victory: all your Fairies +400 ATK/DEF; while you control another
    # Fairy, the opponent can't target Freya for attacks.
    "Freya, Spirit of Victory": (
        FieldMod(atk=400, defn=400, races=frozenset({"Fairy"}), side="self"),
        AttackTargetProtection(self_only=True, requires_control_other_race="Fairy"),
    ),
    # Hunter Owl: +500 ATK per face-up WIND monster you control (counts itself); while you
    # control another WIND monster, the opponent can't target it for attacks.
    "Hunter Owl": (
        SelfStatMod(scaling="controlled_monsters", scale_atk=500, count_attribute=Attribute.WIND),
        AttackTargetProtection(self_only=True, requires_control_other_attribute=Attribute.WIND),
    ),
    # Nightmare Penguin: all your face-up WATER monsters +200 ATK (its flip-bounce is in EFFECTS).
    "Nightmare Penguin": (
        FieldMod(atk=200, attributes=frozenset({Attribute.WATER}), side="self"),
    ),
    # --- Batch 60: more attribute anthems (both sides) + a position-gated anthem ---
    # Harpie Lady 1: all WIND monsters (both sides) +300 ATK.
    "Harpie Lady 1": (FieldMod(atk=300, attributes=frozenset({Attribute.WIND})),),
    # Hoshiningen: all LIGHT monsters +500 ATK, all DARK monsters -400 ATK (both sides).
    "Hoshiningen": (
        FieldMod(atk=500, attributes=frozenset({Attribute.LIGHT})),
        FieldMod(atk=-400, attributes=frozenset({Attribute.DARK})),
    ),
    # Little Chimera: all FIRE monsters +500 ATK, all WATER monsters -400 ATK (both sides).
    "Little Chimera": (
        FieldMod(atk=500, attributes=frozenset({Attribute.FIRE})),
        FieldMod(atk=-400, attributes=frozenset({Attribute.WATER})),
    ),
    # Fairy King Truesdale: while it's in Defense Position, your Plant monsters +500 ATK/DEF.
    "Fairy King Truesdale": (
        FieldMod(atk=500, defn=500, races=frozenset({"Plant"}), side="self", source_in_defense=True),
    ),
    # --- Batch 64: continuous activation locks (ActivationLock rider) ---
    # Mirage Dragon / Pitch-Black Warwolf: opponent can't activate Traps in the Battle Phase.
    "Mirage Dragon": (ActivationLock(locks="trap", during_battle_phase_only=True),),
    "Pitch-Black Warwolf": (ActivationLock(locks="trap", during_battle_phase_only=True),),
    # Invader of Darkness: opponent can't activate Quick-Play Spells.
    "Invader of Darkness": (ActivationLock(locks="spell", quick_play_only=True),),
    # Mechanical Hound: while you hold no cards, opponent can't activate Spells.
    "Mechanical Hound": (ActivationLock(locks="spell", requires_empty_hand=True),),
    # --- Effects Batch 24: name-restricted Equip Spell boosts ---
    "Cyber Shield": (EquipMod(atk=500),),
    "Ancient Gear Tank": (EquipMod(atk=600),),
    "Fuhma Shuriken": (EquipMod(atk=700),),
    "Magic Formula": (EquipMod(atk=700),),
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
    # --- Batch 65: Standby-Phase effects (StandbyTrigger fires a full Effect each
    # qualifying Standby Phase — beyond StandbyUpkeep's fixed-LP maintenance) ---
    # Bowganian: burn the opponent 600 each of your Standby Phases.
    "Bowganian": (
        StandbyTrigger(Effect(resolve=(InflictDamage(OPPONENT, 600),)), whose="controller"),
    ),
    # Ebon Magician Curran: burn 300 for each monster your opponent controls.
    "Ebon Magician Curran": (
        StandbyTrigger(
            Effect(resolve=(InflictDamage(OPPONENT, value=CountTimes(300, "opponent_monsters")),)),
            whose="controller",
        ),
    ),
    # Dancing Fairy: while in face-up Defense, gain 1000 LP each of your Standby Phases.
    "Dancing Fairy": (
        StandbyTrigger(
            Effect(resolve=(GainLifePoints(SELF, 1000),)),
            whose="controller",
            requires_defense=True,
        ),
    ),
    # Spirit of the Breeze: while in face-up Attack, gain 1000 LP each of your Standbys.
    "Spirit of the Breeze": (
        StandbyTrigger(
            Effect(resolve=(GainLifePoints(SELF, 1000),)),
            whose="controller",
            requires_attack=True,
        ),
    ),
    # Destiny HERO - Defender: while in face-up Defense, your opponent draws 1 card at
    # each of THEIR Standby Phases (a drawback that helps them).
    "Destiny HERO - Defender": (
        StandbyTrigger(
            Effect(resolve=(Draw(OPPONENT, 1),)),
            whose="opponent",
            requires_defense=True,
        ),
    ),
    # Lava Golem (Special Summoned to the opponent's field): its controller takes 1000
    # damage each of their Standby Phases.
    "Lava Golem": (
        StandbyTrigger(Effect(resolve=(InflictDamage(SELF, 1000),)), whose="controller"),
    ),
    # Minor Goblin Official (Continuous Trap; activation gate in EFFECTS): burn the
    # opponent 500 each of their Standby Phases.
    "Minor Goblin Official": (
        StandbyTrigger(Effect(resolve=(InflictDamage(OPPONENT, 500),)), whose="opponent"),
    ),
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


# ===== Effects Batch 67: author-only sweep (chunks 0-2) (author-sweep) =====
EFFECTS.update({
    '7 Completed': _equip_effect(races=("Machine",)),
    'A Wingbeat of Giant Dragon': (
        Effect(
            timing="ignition",
            target=TargetSpec(
                count=1, where="own_monsters", races=frozenset({"Dragon"}), min_level=5
            ),
            resolve=(BounceTargetsToHand(), DestroyAllSpellTraps()),
        ),
    ),
    'Abaki': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(InflictDamage(SELF, 500), InflictDamage(OPPONENT, 500)),
        ),
    ),
    'Acid Rain': (
        Effect(resolve=(DestroyAllMonsters(races=frozenset({"Machine"}), face_up_only=True),)),
    ),
    'Aegis of Gaia': (
        Effect(speed=2, timing="ignition", resolve=(GainLifePoints(SELF, 3000),)),
        _on_sent_to_gy((InflictDamage(SELF, 3000),)),
    ),
    'Altar for Tribute': (
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            resolve=(GainLifePoints(SELF, value=TributedAttack()),),
        ),
    ),
    'Amazoness Archer': (
        Effect(timing="ignition", tribute_cost=2, resolve=(InflictDamage(OPPONENT, 1200),)),
    ),
    'Ancient Gear Cannon': (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(names=frozenset({"Ancient Gear Cannon"})),
            send_to_gy_face_up=True,
            resolve=(
                InflictDamage(OPPONENT, 500),
                # The opponent cannot activate Spells OR Traps (rest-of-turn approximates
                # "until the end of the Damage Step"). Self is NOT locked.
                ApplyActionLock(kind="spell", who=OPPONENT),
                ApplyActionLock(kind="trap", who=OPPONENT),
            ),
        ),
    ),
    'Ancient Gear Workshop': (
        Effect(
            timing="ignition",
            condition=_gy_has_match(
                CardFilter(card_kind="monster", name_contains=frozenset({"Ancient Gear"}))
            ),
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(
                        card_kind="monster", name_contains=frozenset({"Ancient Gear"})
                    ),
                    count=1,
                ),
            ),
        ),
    ),
    'Ancient Rules': (
        Effect(
            timing="ignition",
            condition=lambda s, c: s.first_empty_monster_zone(c) is not None
            and any(
                s.inst(i).card.is_vanilla and (s.inst(i).card.level or 0) >= 5
                for i in s.players[c].hand
            ),
            resolve=(SpecialSummonFromHand(card_filter=CardFilter(card_kind="normal_monster", min_level=5)),),
        ),
    ),
    'Anti-Aircraft Flower': (
        Effect(
            timing="ignition",
            tribute_cost=1,
            tribute_races=frozenset({"Insect"}),
            resolve=(InflictDamage(OPPONENT, 800),),
        ),
    ),
    'Aquarian Alessa': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(DiscardFromHand(OPPONENT, count=1, random=True),),
        ),
    ),
    'Arcane Archer of the Forest': (
        Effect(
            timing="ignition",
            tribute_cost=1,
            tribute_races=frozenset({"Plant"}),
            target=TargetSpec(count=1, where="spell_trap_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Assault on GHQ': (
        Effect(
            speed=2,
            timing="ignition",
            target=TargetSpec(count=1, where="own_monsters"),
            resolve=(DestroyTargets(), MillFromDeck(OPPONENT, 2)),
        ),
    ),
    'Atomic Firefly': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(InflictDamage(OPPONENT, 1000),),
        ),
    ),
    'Battery Charger': (
        Effect(
            timing="ignition",
            life_cost=500,
            target=TargetSpec(
                count=1,
                where="own_graveyard_monster",
                name_contains=frozenset({"Batteryman"}),
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    'Batteryman Micro-Cell': (
        _flip(
            resolve=(
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster",
                        name_contains=frozenset({"Batteryman"}),
                        max_level=4,
                    )
                ),
            ),
        ),
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(Draw(count=1),),
        ),
    ),
    'Berfomet': (
        Effect(
            timing="trigger",
            trigger=Trigger(
                kind="summon", by=SELF, summon_kinds=frozenset({"normal", "flip"})
            ),
            resolve=(
                SearchFromDeck(
                    card_filter=CardFilter(
                        names=frozenset({"Gazelle the King of Mythical Beasts"})
                    )
                ),
            ),
        ),
    ),
    'Birdface': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                SearchFromDeck(card_filter=CardFilter(names=frozenset({"Harpie Lady"}))),
            ),
        ),
    ),
    "Black Dragon's Chick": (
        Effect(
            timing="ignition",
            condition=lambda s, c: any(
                s.inst(i).card.name == "Red-Eyes Black Dragon"
                for i in s.players[c].hand
            ),
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(names=frozenset({"Black Dragon's Chick"})),
            send_to_gy_face_up=True,
            resolve=(
                SpecialSummonFromHand(
                    card_filter=CardFilter(names=frozenset({"Red-Eyes Black Dragon"}))
                ),
            ),
        ),
    ),
    'Brain Control': (
        Effect(
            timing="ignition",
            life_cost=800,
            target=TargetSpec(count=1, where="opponent_monsters", face_up=True),
            resolve=(TakeControl(until_end_of_turn=True),),
        ),
    ),
    'Breath of Light': (
        Effect(
            resolve=(
                DestroyAllMonsters(face_up_only=True, races=frozenset({"Rock"})),
            )
        ),
    ),
    'Broken Bamboo Sword': _equip_effect(),
    'Burning Algae': (_on_sent_to_gy((GainLifePoints(OPPONENT, 1000),)),),
    'Cannon Soldier': (
        Effect(timing="ignition", tribute_cost=1, resolve=(InflictDamage(OPPONENT, 500),)),
    ),
    'Cannon Soldier MK-2': (
        Effect(timing="ignition", tribute_cost=2, resolve=(InflictDamage(OPPONENT, 1500),)),
    ),
    'Card Trader': _ACTIVATE_ONTO_FIELD,
    'Castle Walls': (
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ModifyStatsTemporary(defn=500),),
        ),
    ),
    'Chaos Sorcerer': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            disables_attack_this_turn=True,
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(BanishTargets(),),
        ),
    ),
    'Chorus of Sanctuary': _ACTIVATE_ONTO_FIELD,
    'Cloudian - Sheep Cloud': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                CreateToken(
                    token_name="Cloudian Token",
                    count=2,
                    position=Position.FACE_UP_DEFENSE,
                    race="Fairy",
                    attribute=Attribute.WATER,
                    level=1,
                ),
            ),
        ),
    ),
    'Cockroach Knight': (_on_sent_to_gy((ReturnSelfToDeck(to_top=True),)),),
    'Cold Wave': (
        Effect(
            timing="ignition",
            resolve=(
                ApplyActionLock(kind="spell", who="self", extra_turns=1),
                ApplyActionLock(kind="spell", who=OPPONENT, extra_turns=1),
                ApplyActionLock(kind="trap", who="self", extra_turns=1),
                ApplyActionLock(kind="trap", who=OPPONENT, extra_turns=1),
                ApplyActionLock(kind="set", who="self", extra_turns=1),
                ApplyActionLock(kind="set", who=OPPONENT, extra_turns=1),
            ),
        ),
    ),
    'Counter Counter': (
        Effect(
            speed=3,
            timing="quick",
            condition=lambda s, c: (card := _chain_top_card(s)) is not None
            and card.is_trap
            and card.subtype is SpellTrapProperty.COUNTER,
            resolve=(NegatePreviousLink(),),
        ),
    ),
    'Cross Porter': (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(card_kind="monster"),
            condition=lambda s, c: any(
                "Neo-Spacian" in s.inst(i).card.name for i in s.players[c].hand
            ),
            resolve=(
                SpecialSummonFromHand(
                    card_filter=CardFilter(
                        card_kind="monster", name_contains=frozenset({"Neo-Spacian"})
                    )
                ),
            ),
        ),
        _on_sent_to_gy(
            (
                SearchFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster", name_contains=frozenset({"Neo-Spacian"})
                    )
                ),
            )
        ),
    ),
    'Cunning of the Six Samurai': (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_face_up=True,
            send_to_gy_filter=CardFilter(
                card_kind="monster", name_contains=frozenset({"Six Samurai"})
            ),
            target=TargetSpec(
                count=1,
                where="any_graveyard_monster",
                name_contains=frozenset({"Six Samurai"}),
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    'Curse of Aging': (
        Effect(
            speed=2,
            timing="quick",
            discard_cost=1,
            resolve=(ModifyAllStatsTemporary(side=OPPONENT, atk=-500, defn=-500),),
        ),
    ),
    'Cybernetic Hidden Technology': (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(
                names=frozenset(
                    {
                        "Cyber Dragon",
                        "Cyber End Dragon",
                        "Cyber Twin Dragon",
                        "Chimeratech Overdragon",
                        "Chimeratech Fortress Dragon",
                    }
                )
            ),
            resolve=(DestroyTargets(),),
        ),
    ),
    'D - Counter': (
        Effect(
            speed=3,
            timing="trigger",
            trigger=Trigger(
                kind="attack_declared",
                by=OPPONENT,
                subject="attacker",
                target_self_control=True,
                target_name_contains=frozenset({"Destiny HERO"}),
            ),
            resolve=(DestroyTargets(),),
        ),
    ),
    'D - Spirit': (
        Effect(
            timing="ignition",
            condition=_all_conditions(
                _has_free_monster_zone,
                lambda s, c: not any(
                    i is not None
                    and s.inst(i).is_face_up
                    and "Destiny HERO" in s.inst(i).card.name
                    for i in s.players[c].monster_zones
                ),
            ),
            resolve=(
                SpecialSummonFromHand(
                    card_filter=CardFilter(
                        card_kind="monster",
                        name_contains=frozenset({"Destiny HERO"}),
                        max_level=4,
                    )
                ),
            ),
        ),
    ),
    'D.D. Crazy Beast': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(BanishEventMonster(),),
        ),
    ),
})
CONTINUOUS.update({
    'Barrier Statue of the Abyss': (
        SpecialSummonLock(whose="both", except_attribute=Attribute.DARK),
    ),
    'Barrier Statue of the Drought': (
        SpecialSummonLock(whose="both", except_attribute=Attribute.EARTH),
    ),
    'Barrier Statue of the Heavens': (
        SpecialSummonLock(whose="both", except_attribute=Attribute.LIGHT),
    ),
    'Barrier Statue of the Stormwinds': (
        SpecialSummonLock(whose="both", except_attribute=Attribute.WIND),
    ),
    'Batteryman D': (AttackTargetProtection(race="Thunder", exclude_self=True),),
    'Bitelon': (Piercing(),),
    'Chthonian Emperor Dragon': (MultiAttacker(),),
    'Cyber End Dragon': (Piercing(),),
    'Cyber Twin Dragon': (MultiAttacker(),),
})


# ===== Effects Batch 68: author-only sweep (chunks 3-15) (author-sweep) =====
EFFECTS.update({
    'Dark Eruption': (
        Effect(
            timing="ignition",
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(
                        attributes=frozenset({Attribute.DARK}),
                        max_atk=1500,
                        card_kind="monster",
                    ),
                    count=1,
                ),
            ),
        ),
    ),
    'Dark Magic Attack': (
        Effect(
            timing="ignition",
            condition=_controls_named_face_up("Dark Magician"),
            resolve=(DestroyAllSpellTraps(OPPONENT),),
        ),
    ),
    'Dark Magician Knight': (
        Effect(
            timing="trigger",
            trigger=Trigger(
                kind="summon", by=SELF, summon_kinds=frozenset({"special"})
            ),
            target=TargetSpec(count=1, where="any_card_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Dark Red Enchanter': (
        Effect(
            timing="trigger",
            trigger=Trigger(
                kind="summon", by=SELF, summon_kinds=frozenset({"normal"})
            ),
            resolve=(PlaceCountersOnSelf(count=2),),
        ),
        Effect(
            timing="ignition",
            once_per_turn=True,
            counter_cost=2,
            counter_type="spell",
            resolve=(DiscardFromHand(OPPONENT, 1, random=True),),
        ),
    ),
    'Dark Sage': (
        Effect(
            timing="trigger",
            trigger=Trigger(
                kind="summon", by=SELF, summon_kinds=frozenset({"special"})
            ),
            resolve=(SearchFromDeck(CardFilter(card_kind="spell")),),
        ),
    ),
    'Dark World Dealings': (
        Effect(
            timing="ignition",
            resolve=(
                Draw(SELF, 1),
                Draw(OPPONENT, 1),
                DiscardFromHand(SELF, 1),
                DiscardFromHand(OPPONENT, 1),
            ),
        ),
    ),
    'Darkness Approaches': (
        Effect(
            timing="ignition",
            discard_cost=2,
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
    ),
    'De-Spell': (
        Effect(
            timing="ignition",
            target=TargetSpec(count=1, where="spell_trap_field", card_kind="spell"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Dekoichi the Battlechanted Locomotive': (_flip(resolve=(Draw(SELF, 1),)),),
    'Demise, King of Armageddon': (
        Effect(timing="ignition", life_cost=2000, resolve=(DestroyAllOtherCards(),)),
    ),
    'Desert Sunlight': (
        Effect(
            speed=2,
            timing="ignition",
            resolve=(ChangeAllPositions(side=SELF, to="defense"),),
        ),
    ),
    'Desertapir': (
        _flip(
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
    ),
    'Destruction Ring': (
        Effect(
            speed=2,
            timing="ignition",
            target=TargetSpec(count=1, where="own_monsters", face_up=True),
            resolve=(
                DestroyTargets(),
                InflictDamage(SELF, 1000),
                InflictDamage(OPPONENT, 1000),
            ),
        ),
    ),
    'Doom Dozer': (_on_battle_damage(resolve=(MillFromDeck(OPPONENT, 1),)),),
    'Dragon Seeker': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal", "flip"})),
            target=TargetSpec(count=1, where="any_monster", races=frozenset({"Dragon"}), face_up=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Eagle Eye': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            resolve=(
                ApplyActionLock(kind="trap", who="opponent", extra_turns=0),
                ApplyActionLock(kind="trap", who="self", extra_turns=0),
            ),
        ),
    ),
    'Edge Hammer': (
        Effect(
            speed=2,
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(names=frozenset({"Elemental HERO Bladedge"})),
            send_to_gy_face_up=True,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(InflictDamage(OPPONENT, value=TargetAttack(index=0)), DestroyTargets()),
        ),
    ),
    'Elemental HERO Flame Wingman': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(InflictDamage(OPPONENT, value=DestroyedByBattleAttack()),),
        ),
    ),
    'Elemental HERO Plasma Vice': (
        Effect(
            timing="ignition",
            discard_cost=1,
            target=TargetSpec(count=1, where="opponent_monsters", attack_position=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Elemental HERO Steam Healer': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(GainLifePoints(SELF, value=DestroyedByBattleAttack()),),
        ),
    ),
    'Elemental HERO Thunder Giant': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            discard_cost=1,
            target=TargetSpec(count=1, where="any_monster", face_up=True, max_atk=2399),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Elemental HERO Wild Wingman': (
        Effect(
            timing="ignition",
            discard_cost=1,
            target=TargetSpec(count=1, where="spell_trap_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Eradicating Aerosol': (
        Effect(resolve=(DestroyAllMonsters(races=frozenset({"Insect"})),)),
    ),
    'Eternal Drought': (
        Effect(resolve=(DestroyAllMonsters(races=frozenset({"Fish"}), face_up_only=True),)),
    ),
    'Exile of the Wicked': (
        Effect(resolve=(DestroyAllMonsters(races=frozenset({"Fiend"})),)),
    ),
    'Exiled Force': (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(names=frozenset({"Exiled Force"})),
            send_to_gy_face_up=True,
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Expressroid': (
        Effect(
            timing="trigger",
            trigger=Trigger(
                kind="summon", by=SELF, summon_kinds=frozenset({"normal", "flip"})
            ),
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(card_kind="monster", name_contains=frozenset({"roid"})),
                    count=2,
                ),
            ),
        ),
    ),
    'Fifth Hope': (
        Effect(
            condition=lambda s, c: sum(
                1 for i in s.players[c].graveyard if "Elemental HERO" in s.inst(i).card.name
            ) >= 5,
            resolve=(
                ReturnFromGraveyardToDeck(
                    card_filter=CardFilter(name_contains=frozenset({"Elemental HERO"})), count=5
                ),
                Draw(count=2),
            ),
        ),
    ),
    'Final Destiny': (
        Effect(discard_cost=5, resolve=(DestroyAllOtherCards(),)),
    ),
    'Fine': (
        Effect(speed=2, timing="ignition", resolve=(DiscardFromHand(SELF, count=2),)),
    ),
    'Fire Trooper': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF),
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(names=frozenset({"Fire Trooper"})),
            send_to_gy_face_up=True,
            resolve=(InflictDamage(OPPONENT, 1000),),
        ),
    ),
    'Flame Ogre': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            resolve=(Draw(count=1),),
        ),
    ),
    'Flash of the Forbidden Spell': (
        Effect(
            condition=lambda s, c: all(
                i is not None for i in s.players[s.opponent_of(c)].monster_zones
            ),
            resolve=(DestroyAllMonsters(side=OPPONENT),),
        ),
    ),
    'Future Samurai': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            banish_from_gy_cost=1,
            banish_from_gy_filter=CardFilter(card_kind="monster"),
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Gather Your Mind': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            condition=_can_search(CardFilter(names=frozenset({"Gather Your Mind"}))),
            resolve=(SearchFromDeck(card_filter=CardFilter(names=frozenset({"Gather Your Mind"}))),),
        ),
    ),
    'Gift Card': (
        Effect(speed=2, timing="ignition", resolve=(GainLifePoints(OPPONENT, 3000),)),
    ),
    "Gladiator's Return": (
        Effect(
            condition=lambda s, c: sum(
                1 for i in s.players[c].graveyard if "Gladiator Beast" in s.inst(i).card.name
            ) >= 3,
            resolve=(
                ReturnFromGraveyardToDeck(
                    card_filter=CardFilter(name_contains=frozenset({"Gladiator Beast"})), count=3
                ),
                Draw(count=1),
            ),
        ),
    ),
    'Goblin Thief': (
        Effect(resolve=(InflictDamage(OPPONENT, 500), GainLifePoints(SELF, 500))),
    ),
    'Gokipon': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                SearchFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster", races=frozenset({"Insect"}), max_atk=1500
                    )
                ),
            ),
        ),
    ),
    'Golden Bamboo Sword': (
        Effect(
            condition=lambda s, c: any(
                i is not None
                and s.inst(i).is_face_up
                and s.inst(i).card.subtype is SpellTrapProperty.EQUIP
                and "Bamboo Sword" in s.inst(i).card.name
                for i in s.players[c].spell_trap_zones
            ),
            resolve=(Draw(count=2),),
        ),
    ),
    'Golem Sentry': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            target=TargetSpec(
                count=1, where="own_monsters", face_up=True, names=frozenset({"Golem Sentry"})
            ),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
        _flip(
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    'Graceful Charity': (
        Effect(resolve=(Draw(count=3), DiscardFromHand(SELF, 2))),
    ),
    'Grand Convergence': (
        Effect(
            condition=lambda s, c: any(
                i is not None
                and s.inst(i).is_face_up
                and s.inst(i).card.name == "Macro Cosmos"
                for i in s.players[c].spell_trap_zones
            ),
            resolve=(InflictDamage(OPPONENT, 300), DestroyAllMonsters()),
        ),
    ),
    'Grave Squirmer': (
        Effect(
            speed=1,
            timing="trigger",
            trigger=Trigger(kind="sent_to_gy_from_field", by=SELF),
            target=TargetSpec(count=1, where="any_card_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    "Gravekeeper's Chief": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            target=TargetSpec(
                count=1,
                where="own_graveyard_monster",
                name_contains=frozenset({"Gravekeeper's"}),
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    "Graverobber's Retribution": _ACTIVATE_ONTO_FIELD,
    'Green Gadget': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal", "special"})),
            resolve=(SearchFromDeck(card_filter=CardFilter(names=frozenset({"Red Gadget"}))),),
        ),
    ),
    "HERO's Bond": (
        Effect(
            timing="ignition",
            condition=lambda s, c: any(
                i is not None and s.inst(i).is_face_up and "HERO" in s.inst(i).card.name
                for pl in (0, 1)
                for i in s.players[pl].monster_zones
            ),
            resolve=(
                SpecialSummonFromHand(
                    card_filter=CardFilter(name_contains=frozenset({"Elemental HERO"}), max_level=4)
                ),
                SpecialSummonFromHand(
                    card_filter=CardFilter(name_contains=frozenset({"Elemental HERO"}), max_level=4)
                ),
            ),
        ),
    ),
    'Hand Destruction': (
        Effect(
            condition=lambda s, c: len(s.players[c].hand) >= 3
            and len(s.players[s.opponent_of(c)].hand) >= 2,
            resolve=(
                DiscardFromHand(SELF, 2),
                DiscardFromHand(OPPONENT, 2),
                Draw(SELF, 2),
                Draw(OPPONENT, 2),
            ),
        ),
    ),
    'Helping Robo for Combat': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(Draw(SELF, 1), ReturnFromHandToDeck(SELF, count=1)),
        ),
    ),
    'Herald of Creation': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            discard_cost=1,
            condition=_gy_has_match(CardFilter(card_kind="monster", min_level=7)),
            resolve=(ReturnFromGraveyardToHand(CardFilter(card_kind="monster", min_level=7)),),
        ),
    ),
    'Hero Barrier': (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            condition=lambda s, c: any(
                i is not None
                and s.inst(i).is_face_up
                and "Elemental HERO" in s.inst(i).card.name
                for i in s.players[c].monster_zones
            ),
            resolve=(NegateAttack(),),
        ),
    ),
    'Hero Medal': (
        _on_sent_to_gy((ReturnSelfToDeck(to_top=False), Draw(SELF, 1))),
    ),
    'Hidden Spellbook': (
        Effect(
            speed=2,
            timing="ignition",
            condition=lambda s, c: sum(
                1 for i in s.players[c].graveyard if s.inst(i).card.is_spell
            )
            >= 2,
            resolve=(ReturnFromGraveyardToDeck(card_filter=CardFilter(card_kind="spell"), count=2),),
        ),
    ),
    'Hysteric Fairy': (
        Effect(timing="ignition", tribute_cost=2, resolve=(GainLifePoints(SELF, 1000),)),
    ),
    'Inferno Hammer': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            target=TargetSpec(count=1, where="opponent_monsters", face_up=True),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
    ),
    'Insect Armor with Laser Cannon': _equip_effect(races=("Insect",)),
    'Introduction to Gallantry': (
        Effect(
            speed=2,
            timing="ignition",
            condition=lambda s, c: len(s.players[s.opponent_of(c)].hand) >= 5,
            resolve=(DiscardFromHand(OPPONENT, count=1, random=True),),
        ),
    ),
    'Invigoration': _equip_effect(attributes=(Attribute.EARTH,)),
    'Jar of Greed': (Effect(speed=2, timing="ignition", resolve=(Draw(count=1),)),),
    'Kaibaman': (
        Effect(
            timing="ignition",
            tribute_cost=1,
            resolve=(
                SpecialSummonFromHand(
                    card_filter=CardFilter(names=frozenset({"Blue-Eyes White Dragon"}))
                ),
            ),
        ),
    ),
    'King Pyron': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            resolve=(InflictDamage(OPPONENT, 1000),),
        ),
    ),
    'Kryuel': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(CoinFlip(win=(DestroyTargets(),)),),
        ),
    ),
    'Laser Cannon Armor': _equip_effect(races=("Insect",)),
    'Last Day of Witch': (
        Effect(resolve=(DestroyAllMonsters(face_up_only=True, races=frozenset({"Spellcaster"})),)),
    ),
    'Legendary Sword': _equip_effect(races=("Warrior",)),
    'Lesser Fiend': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(BanishEventMonster(),),
        ),
    ),
    'Level Limit - Area A': _ACTIVATE_ONTO_FIELD,
    'Lightning Blade': _equip_effect(races=("Warrior",)),
    'Lord Poison': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster", races=frozenset({"Plant"})),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    'Lucky Pied Piper': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(Draw(count=1),),
        ),
    ),
    'Machine Conversion Factory': _equip_effect(races=("Machine",)),
    'Mad Reloader': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            discard_cost=2,
            resolve=(Draw(count=2),),
        ),
    ),
    'Magical Marionette': (
        Effect(
            timing="ignition",
            counter_cost=2,
            counter_type="spell",
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Magical Stone Excavation': (
        Effect(
            timing="ignition",
            discard_cost=2,
            condition=_gy_has_match(CardFilter(card_kind="spell")),
            resolve=(ReturnFromGraveyardToHand(card_filter=CardFilter(card_kind="spell"), count=1),),
        ),
    ),
    'Magnet Circle LV2': (
        Effect(
            condition=_has_free_monster_zone,
            resolve=(SpecialSummonFromHand(card_filter=CardFilter(races=frozenset({"Machine"}), max_level=2)),),
        ),
    ),
    'Malevolent Nuzzler': (
        *_equip_effect(),
        Effect(
            speed=1,
            timing="trigger",
            trigger=Trigger(kind="sent_to_gy_from_field", by=SELF),
            life_cost=500,
            resolve=(ReturnSelfToDeck(to_top=True),),
        ),
    ),
    'Mask of Brutality': _equip_effect(),
    'Mask of Weakness': (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(ModifyStatsTemporary(atk=-700),),
        ),
    ),
    'Mass Driver': (
        Effect(timing="ignition", tribute_cost=1, resolve=(InflictDamage(OPPONENT, 400),)),
    ),
    'Mazera DeVille': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"special"})),
            condition=_field_spell_on_field("Pandemonium"),
            resolve=(DiscardFromHand(OPPONENT, 3, random=True),),
        ),
    ),
    'Mecha-Dog Marron': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(InflictDamage(SELF, 1000), InflictDamage(OPPONENT, 1000)),
        ),
        _on_sent_to_gy((InflictDamage(OPPONENT, 1000),)),
    ),
    'Medusa Worm': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            target=TargetSpec(
                count=1,
                where="own_monsters",
                face_up=True,
                names=frozenset({"Medusa Worm"}),
            ),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
        _flip(
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Meteor of Destruction': (
        Effect(
            condition=lambda s, c: s.players[s.opponent_of(c)].life_points > 3000,
            resolve=(InflictDamage(OPPONENT, 1000),),
        ),
    ),
    'Mind Control': (
        Effect(
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(TakeControl(until_end_of_turn=True),),
        ),
    ),
    'Mine Golem': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(InflictDamage(OPPONENT, 500),),
        ),
    ),
    'Moai Interceptor Cannons': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            target=TargetSpec(
                count=1,
                where="own_monsters",
                face_up=True,
                names=frozenset({"Moai Interceptor Cannons"}),
            ),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
    ),
    'Mobius the Frost Monarch': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            target=TargetSpec(count=2, up_to=True, where="spell_trap_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Monster Reincarnation': (
        Effect(
            timing="ignition",
            discard_cost=1,
            condition=_gy_has_match(CardFilter(card_kind="monster")),
            resolve=(
                ReturnFromGraveyardToHand(card_filter=CardFilter(card_kind="monster"), count=1),
            ),
        ),
    ),
    'Mooyan Curry': (Effect(resolve=(GainLifePoints(SELF, 200),)),),
    'Morphing Jar': (
        _flip(
            resolve=(
                DiscardFromHand(SELF, count=99),
                DiscardFromHand(OPPONENT, count=99),
                Draw(SELF, 5),
                Draw(OPPONENT, 5),
            )
        ),
    ),
    'Multiplication of Ants': (
        Effect(
            timing="ignition",
            tribute_cost=1,
            tribute_races=frozenset({"Insect"}),
            resolve=(
                CreateToken(
                    token_name="Army Ant Token",
                    count=2,
                    race="Insect",
                    attribute=Attribute.EARTH,
                    level=4,
                    atk=500,
                    defn=1200,
                ),
            ),
        ),
    ),
    'Mystical Moon': _equip_effect(races=("Beast-Warrior",)),
    'Mystik Wok': (
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            resolve=(GainLifePoints(SELF, value=TributedAttack()),),
        ),
    ),
    'Needle Ball': (
        _flip(resolve=(InflictDamage(SELF, 2000), InflictDamage(OPPONENT, 1000))),
    ),
    'Needle Ceiling': (
        Effect(
            speed=2,
            timing="quick",
            condition=lambda s, c: sum(
                1 for pl in (0, 1) for i in s.players[pl].monster_zones if i is not None
            ) >= 4,
            resolve=(DestroyAllMonsters(face_up_only=True),),
        ),
    ),
    'Newdoria': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Nova Summoner': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster",
                        attributes=frozenset({Attribute.LIGHT}),
                        races=frozenset({"Fairy"}),
                        max_atk=1500,
                    )
                ),
            ),
        ),
    ),
    'Orbital Bombardment': (
        Effect(
            speed=2,
            timing="quick",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(
                card_kind="monster", name_contains=frozenset({"Alien"})
            ),
            target=TargetSpec(count=1, where="spell_trap_field"),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Outstanding Dog Marron': (_on_sent_to_gy((ReturnSelfToDeck(to_top=False),)),),
    'Pinch Hopper': (
        _on_sent_to_gy(
            (
                SpecialSummonFromHand(
                    card_filter=CardFilter(
                        card_kind="monster", races=frozenset({"Insect"})
                    )
                ),
            )
        ),
    ),
    'Poison Draw Frog': (_on_sent_to_gy((Draw(count=1),)),),
    'Pot of Avarice': (
        Effect(
            condition=lambda s, c: sum(
                1 for i in s.players[c].graveyard if s.inst(i).card.is_monster
            ) >= 5,
            resolve=(
                ReturnFromGraveyardToDeck(
                    card_filter=CardFilter(card_kind="monster"), count=5
                ),
                Draw(count=2),
            ),
        ),
    ),
    'Pot of Generosity': (Effect(resolve=(ReturnFromHandToDeck(SELF, count=2),)),),
    'Power of Kaishin': _equip_effect(races=("Aqua",)),
    'Raimei': (Effect(resolve=(InflictDamage(OPPONENT, 300),)),),
    'Rain of Mercy': (
        Effect(resolve=(GainLifePoints(SELF, 1000), GainLifePoints(OPPONENT, 1000))),
    ),
    'Rainbow Path': (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(name_contains=frozenset({"Crystal Beast"})),
            resolve=(
                NegateAttack(),
                SearchFromDeck(
                    card_filter=CardFilter(
                        names=frozenset({"Rainbow Dragon", "Rainbow Dark Dragon"})
                    )
                ),
            ),
        ),
    ),
    'Raise Body Heat': _equip_effect(races=("Dinosaur",)),
    'Raiza the Storm Monarch': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            target=TargetSpec(count=1, where="any_card_field"),
            resolve=(BounceTargetsToDeck(to_top=True),),
        ),
    ),
    'Recurring Nightmare': (
        Effect(
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(
                        card_kind="monster",
                        attributes=frozenset({Attribute.DARK}),
                        max_def=0,
                    ),
                    count=2,
                ),
            )
        ),
    ),
    'Red Gadget': (
        Effect(
            timing="trigger",
            trigger=Trigger(
                kind="summon", by=SELF, summon_kinds=frozenset({"normal", "special"})
            ),
            resolve=(SearchFromDeck(card_filter=CardFilter(names=frozenset({"Yellow Gadget"}))),),
        ),
    ),
    'Regenerating Rose': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            condition=_has_free_monster_zone,
            resolve=(
                CreateToken(
                    token_name="Regenerating Rose Token",
                    count=2,
                    race="Plant",
                    attribute=Attribute.DARK,
                    level=3,
                    atk=1200,
                    defn=1200,
                ),
            ),
        ),
    ),
    'Remove Trap': (
        Effect(
            timing="ignition",
            target=TargetSpec(count=1, where="spell_trap_field", card_kind="trap", face_up=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Rite of Spirit': (
        Effect(
            speed=2,
            timing="ignition",
            condition=_has_free_monster_zone,
            target=TargetSpec(
                count=1, where="own_graveyard_monster", name_contains=frozenset({"Gravekeeper's"})
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    'Ruthless Denial': (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(card_kind="monster"),
            resolve=(DiscardFromHand(OPPONENT, count=1, random=True),),
        ),
    ),
    'Ryko, Lightsworn Hunter': (
        _flip(
            target=TargetSpec(count=1, where="any_card_field", up_to=True),
            resolve=(DestroyTargets(), MillFromDeck(SELF, 3)),
        ),
    ),
    'Sacred Crane': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"special"})),
            resolve=(Draw(count=1),),
        ),
    ),
    'Sage of Silence': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(ApplyActionLock(kind="spell", who=OPPONENT, extra_turns=1),),
        ),
    ),
    'Sage of Stillness': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(ApplyActionLock(kind="trap", who=OPPONENT, extra_turns=1),),
        ),
    ),
    'Salamandra': _equip_effect(attributes=(Attribute.FIRE,)),
    'Shine Palace': _equip_effect(attributes=(Attribute.LIGHT,)),
    'Salvage': (
        Effect(
            condition=_gy_has_match(
                CardFilter(card_kind="monster", attributes=frozenset({Attribute.WATER}), max_atk=1500)
            ),
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(
                        card_kind="monster", attributes=frozenset({Attribute.WATER}), max_atk=1500
                    ),
                    count=2,
                ),
            ),
        ),
    ),
    'Scarr, Scout of Dark World': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                SearchFromDeck(
                    CardFilter(card_kind="monster", name_contains=frozenset({"Dark World"}), max_level=4)
                ),
            ),
        ),
    ),
    'Shadow Tamer': (
        _flip(
            target=TargetSpec(count=1, where="opponent_monsters", races=frozenset({"Fiend"})),
            resolve=(TakeControl(until_end_of_turn=True),),
        ),
    ),
    'Shadowpriestess of Ohm': (
        Effect(
            timing="ignition",
            tribute_cost=1,
            tribute_attributes=frozenset({Attribute.DARK}),
            resolve=(InflictDamage(OPPONENT, 800),),
        ),
    ),
    "Shien's Footsoldier": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                SpecialSummonFromDeck(
                    CardFilter(card_kind="monster", name_contains=frozenset({"Six Samurai"}), max_level=3)
                ),
            ),
        ),
    ),
    'Simultaneous Loss': (
        Effect(
            speed=2,
            timing="ignition",
            resolve=(MillFromDeck(SELF, count=1), MillFromDeck(OPPONENT, count=1)),
        ),
    ),
    'Skull-Mark Ladybug': (_on_sent_to_gy((GainLifePoints(SELF, 1000),)),),
    'Snake Fang': (
        Effect(
            speed=2,
            timing="ignition",
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(ModifyStatsTemporary(defn=-500),),
        ),
    ),
    'Spiritual Earth Art - Kurogane': (
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            tribute_attributes=frozenset({Attribute.EARTH}),
            target=TargetSpec(
                count=1, where="own_graveyard_monster",
                attributes=frozenset({Attribute.EARTH}), max_level=4,
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    'Spiritual Water Art - Aoi': (
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            tribute_attributes=frozenset({Attribute.WATER}),
            resolve=(DiscardFromHand(OPPONENT, count=1),),
        ),
    ),
    'Spiritual Wind Art - Miyabi': (
        Effect(
            speed=2,
            timing="ignition",
            tribute_cost=1,
            tribute_attributes=frozenset({Attribute.WIND}),
            target=TargetSpec(count=1, where="opponent_card_field"),
            resolve=(BounceTargetsToDeck(to_top=False),),
        ),
    ),
    'Spiritualism': (
        Effect(
            target=TargetSpec(count=1, where="spell_trap_field"),
            resolve=(BounceTargetsToHand(),),
        ),
    ),
    'Stamping Destruction': (
        Effect(
            timing="ignition",
            condition=lambda s, c: any(
                i is not None and s.inst(i).card.race == "Dragon"
                for i in s.players[c].monster_zones
            ),
            target=TargetSpec(count=1, where="spell_trap_field"),
            resolve=(DestroyTargets(), InflictDamage(OPPONENT, 500)),
        ),
    ),
    'Statue of the Wicked': (
        _on_sent_to_gy(
            (
                CreateToken(
                    token_name="Wicked Token",
                    race="Fiend",
                    attribute=Attribute.DARK,
                    level=4,
                    atk=1000,
                    defn=1000,
                ),
            )
        ),
    ),
    'Stray Asmodian': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(GainLifePoints(SELF, 800), GainLifePoints(OPPONENT, 800)),
        ),
    ),
    'Sword of Dark Destruction': _equip_effect(attributes=(Attribute.DARK,)),
    'Sword of Deep-Seated': (
        *_equip_effect(),
        _on_sent_to_gy((ReturnSelfToDeck(to_top=True),)),
    ),
    'Symbols of Duty': (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(card_kind="normal_monster"),
            target=TargetSpec(count=1, where="any_graveyard_monster"),
            resolve=(SpecialSummonFromGraveyard(link=True),),
        ),
    ),
    'T.A.D.P.O.L.E.': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(SearchFromDeck(card_filter=CardFilter(names=frozenset({"T.A.D.P.O.L.E."}))),),
        ),
    ),
    'Tactical Espionage Expert': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            resolve=(
                ApplyActionLock(kind="trap", who=OPPONENT, extra_turns=0),
                ApplyActionLock(kind="trap", who=SELF, extra_turns=0),
            ),
        ),
    ),
    'Taunt': (
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="own_monsters"),
            resolve=(ForceAttackTarget(),),
        ),
    ),
    'Terrible Deal': (
        Effect(
            speed=2,
            timing="quick",
            condition=_chain_top_is_spell,
            life_cost=1000,
            resolve=(DiscardFromHand(OPPONENT, count=1, random=True),),
        ),
    ),
    'Test Ape': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        name_contains=frozenset({"Gladiator Beast"}), max_level=4
                    )
                ),
            ),
        ),
    ),
    'The Cheerful Coffin': (Effect(resolve=(DiscardFromHand(SELF, count=3),)),),
    'The Creator': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            discard_cost=1,
            condition=_has_free_monster_zone,
            target=TargetSpec(count=1, where="own_graveyard_monster"),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
    'The Creator Incarnate': (
        Effect(
            timing="ignition",
            send_to_gy_cost=1,
            send_to_gy_filter=CardFilter(names=frozenset({"The Creator Incarnate"})),
            send_to_gy_face_up=True,
            condition=lambda s, c: any(
                s.inst(i).card.name == "The Creator" for i in s.players[c].hand
            ),
            resolve=(
                SpecialSummonFromHand(card_filter=CardFilter(names=frozenset({"The Creator"}))),
            ),
        ),
    ),
    'The Flute of Summoning Kuriboh': (
        _search_effect(CardFilter(names=frozenset({"Kuriboh", "Winged Kuriboh"}))),
    ),
    'The Forces of Darkness': (
        Effect(
            speed=2,
            timing="ignition",
            condition=_gy_has_match(
                CardFilter(card_kind="monster", name_contains=frozenset({"Dark World"}))
            ),
            resolve=(
                ReturnFromGraveyardToHand(
                    CardFilter(card_kind="monster", name_contains=frozenset({"Dark World"})),
                    count=2,
                ),
            ),
        ),
    ),
    'The Gift of Greed': (
        Effect(speed=2, timing="ignition", resolve=(Draw(OPPONENT, 2),)),
    ),
    'The Graveyard in the Fourth Dimension': (
        Effect(
            condition=_gy_has_match(
                CardFilter(card_kind="monster", name_contains=frozenset({"LV"}))
            ),
            resolve=(
                ReturnFromGraveyardToDeck(
                    card_filter=CardFilter(card_kind="monster", name_contains=frozenset({"LV"})),
                    count=2,
                ),
            ),
        ),
    ),
    'The Little Swordsman of Aile': (
        Effect(
            timing="ignition",
            tribute_cost=1,
            target=TargetSpec(
                count=1,
                where="own_monsters",
                face_up=True,
                names=frozenset({"The Little Swordsman of Aile"}),
            ),
            resolve=(ModifyStatsTemporary(atk=700),),
        ),
    ),
    'The Paths of Destiny': (
        Effect(
            speed=2,
            timing="ignition",
            resolve=(
                CoinFlip(win=(GainLifePoints(SELF, 2000),), lose=(InflictDamage(SELF, 2000),)),
                CoinFlip(
                    win=(GainLifePoints(OPPONENT, 2000),),
                    lose=(InflictDamage(OPPONENT, 2000),),
                ),
            ),
        ),
    ),
    'The Reliable Guardian': (
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ModifyStatsTemporary(defn=700),),
        ),
    ),
    'The Thing in the Crater': (
        _on_sent_to_gy(
            (
                SpecialSummonFromHand(
                    card_filter=CardFilter(card_kind="monster", races=frozenset({"Pyro"}))
                ),
            )
        ),
    ),
    'The Warrior Returning Alive': (
        Effect(
            condition=_gy_has_match(
                CardFilter(card_kind="monster", races=frozenset({"Warrior"}))
            ),
            resolve=(
                ReturnFromGraveyardToHand(
                    CardFilter(card_kind="monster", races=frozenset({"Warrior"})),
                    count=1,
                ),
            ),
        ),
    ),
    'Torrential Tribute': (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="summon", by=OPPONENT),
            resolve=(DestroyAllMonsters(),),
        ),
    ),
    'Trap Jammer': (
        Effect(
            speed=3,
            timing="quick",
            condition=_all_conditions(_chain_top_is_trap, lambda s, c: s.phase.name == "BATTLE"),
            resolve=(NegatePreviousLink(),),
        ),
    ),
    'Troop Dragon': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(SpecialSummonFromDeck(card_filter=CardFilter(names=frozenset({"Troop Dragon"}))),),
        ),
    ),
    'Tsukuyomi': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
        _flip(
            target=TargetSpec(count=1, where="any_monster", face_up=True),
            resolve=(ChangeTargetPosition(to="face_down"),),
        ),
    ),
    'Twister': (
        Effect(
            speed=2,
            timing="quick",
            life_cost=500,
            target=TargetSpec(count=1, where="spell_trap_field", face_up=True),
            resolve=(DestroyTargets(),),
        ),
    ),
    'Ultra Evolution Pill': (
        Effect(
            timing="ignition",
            tribute_cost=1,
            tribute_races=frozenset({"Reptile"}),
            resolve=(
                SpecialSummonFromHand(
                    card_filter=CardFilter(card_kind="monster", races=frozenset({"Dinosaur"}))
                ),
            ),
        ),
    ),
    'Upstart Goblin': (
        Effect(resolve=(Draw(SELF, 1), GainLifePoints(OPPONENT, 1000))),
    ),
    'Valhalla, Hall of the Fallen': (
        Effect(
            timing="ignition",
            once_per_turn=True,
            condition=_control_no_monsters,
            resolve=(
                SpecialSummonFromHand(
                    card_filter=CardFilter(card_kind="monster", races=frozenset({"Fairy"}))
                ),
            ),
        ),
    ),
    'Vampiric Orchis': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            resolve=(
                SpecialSummonFromHand(card_filter=CardFilter(names=frozenset({"Des Dendle"}))),
            ),
        ),
    ),
    'Violet Crystal': _equip_effect(races=("Zombie",)),
    'Vortex Trooper': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            resolve=(ReturnFromHandToDeck(SELF, count=2), Draw(count=2)),
        ),
        _on_sent_to_gy((Draw(count=1),)),
    ),
    'Warrior Elimination': (
        Effect(resolve=(DestroyAllMonsters(races=frozenset({"Warrior"})),)),
    ),
    'Witch of the Black Forest': (
        _on_sent_to_gy(
            (SearchFromDeck(card_filter=CardFilter(card_kind="monster", max_def=1500)),)
        ),
    ),
    'Wonder Garage': (
        _on_sent_to_gy(
            (
                SpecialSummonFromHand(
                    card_filter=CardFilter(
                        card_kind="monster",
                        races=frozenset({"Machine"}),
                        name_contains=frozenset({"roid"}),
                        max_level=4,
                    )
                ),
            )
        ),
    ),
    'Wroughtweiler': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(name_contains=frozenset({"Elemental HERO"})), count=1
                ),
                ReturnFromGraveyardToHand(
                    card_filter=CardFilter(names=frozenset({"Polymerization"})), count=1
                ),
            ),
        ),
    ),
    'Yellow Gadget': (
        Effect(
            timing="trigger",
            trigger=Trigger(
                kind="summon", by=SELF, summon_kinds=frozenset({"normal", "special"})
            ),
            resolve=(SearchFromDeck(card_filter=CardFilter(names=frozenset({"Green Gadget"}))),),
        ),
    ),
    'Yellow Luster Shield': _ACTIVATE_ONTO_FIELD,
    'Zaborg the Thunder Monarch': (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, summon_kinds=frozenset({"normal"})),
            target=TargetSpec(count=1, where="any_monster"),
            resolve=(DestroyTargets(),),
        ),
    ),
})
CONTINUOUS.update({
    'Doitsu': (
        UnionMod(host_names=frozenset({"Soitsu"})),
        EquipMod(atk=2500),
    ),
    'Dragon Master Knight': (
        SelfStatMod(scaling="controlled_monsters", count_race="Dragon", count_exclude_self=True, scale_atk=500),
    ),
    'Elemental HERO Bladedge': (Piercing(),),
    'Elemental HERO Inferno': (DamageStepBonus(atk=1000, when="either", vs_attribute=Attribute.WATER),),
    'Elemental HERO Phoenix Enforcer': (BattleIndestructible(),),
    'Gemini Lancer': (Piercing(),),
    'Gora Turtle': (AttackRestriction(min_atk_cannot_attack=1900),),
    "Gravekeeper's Spear Soldier": (Piercing(),),
    "Harpie's Pet Dragon": (
        SelfStatMod(
            scaling="controlled_monsters",
            scale_atk=300,
            scale_defn=300,
            count_name_contains="Harpie Lady",
        ),
    ),
    'Heavy Mech Support Platform': (
        UnionMod(host_races=frozenset({"Machine"})),
        EquipMod(atk=500, defn=500),
    ),
    'Inaba White Rabbit': (CanAttackDirectly(),),
    'Jinzo #7': (CanAttackDirectly(),),
    'Lancer Dragonute': (Piercing(),),
    'Leghul': (CanAttackDirectly(),),
    'Luminous Soldier': (DamageStepBonus(atk=500, when="either", vs_attribute=Attribute.DARK),),
    'Machina Sniper': (
        AttackTargetProtection(name_contains="Machina", exclude_name_contains="Machina Sniper"),
    ),
    "Magician's Valkyria": (AttackTargetProtection(race="Spellcaster", exclude_self=True),),
    'Master Monk': (MultiAttacker(times=2),),
    'Mystic Lamp': (CanAttackDirectly(),),
    'Nightmare Horse': (CanAttackDirectly(),),
    'Ooguchi': (CanAttackDirectly(),),
    'Phantom Beast Wild-Horn': (Piercing(),),
    'Princess Curran': (
        StandbyTrigger(
            Effect(
                resolve=(
                    InflictDamage(OPPONENT, value=CountTimes(600, "opponent_monsters")),
                )
            ),
            whose="controller",
        ),
    ),
    "Queen's Double": (CanAttackDirectly(),),
    'Rainbow Flower': (CanAttackDirectly(),),
    'Saber Beetle': (Piercing(),),
    'Servant of Catabolism': (CanAttackDirectly(),),
    'Super Vehicroid Jumbo Drill': (Piercing(),),
    'The Fiend Megacyber': (HandSpecialSummon(condition=_opponent_controls_at_least_more(2)),),
    'Ultimate Insect LV7': (FieldMod(atk=-700, defn=-700, side=OPPONENT),),
    'W-Wing Catapult': (
        UnionMod(host_names=frozenset({"V-Tiger Jet"})),
        EquipMod(atk=400, defn=400),
    ),
    'Z-Metal Tank': (
        UnionMod(host_names=frozenset({"X-Head Cannon", "Y-Dragon Head"})),
        EquipMod(atk=600, defn=600),
    ),
})


# ===== Effects Batch 69: during-End-Phase triggers (EndPhaseTrigger) =====
EFFECTS.update({
    # Lumina, Lightsworn Summoner — Ignition revive (the End-Phase mill is in CONTINUOUS):
    # discard 1, then Special Summon a Level-4-or-lower "Lightsworn" from your GY.
    "Lumina, Lightsworn Summoner": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            discard_cost=1,
            target=TargetSpec(
                count=1,
                where="own_graveyard_monster",
                max_level=4,
                name_contains=frozenset({"Lightsworn"}),
            ),
            resolve=(SpecialSummonFromGraveyard(),),
        ),
    ),
})
CONTINUOUS.update({
    # Elemental HERO Lady Heat — during each of YOUR End Phases, burn the opponent 200
    # for each face-up "Elemental HERO" you control (counts Lady Heat herself).
    "Elemental HERO Lady Heat": (
        EndPhaseTrigger(
            Effect(
                resolve=(
                    InflictDamage(
                        OPPONENT,
                        value=CountTimes(
                            200,
                            "own_monsters",
                            card_filter=CardFilter(
                                card_kind="monster",
                                name_contains=frozenset({"Elemental HERO"}),
                            ),
                        ),
                    ),
                )
            ),
            whose="controller",
        ),
    ),
    # Little-Winguard — during your End Phase you may change its own battle position
    # (self-target by name, toggle ATK<->DEF).
    "Little-Winguard": (
        EndPhaseTrigger(
            Effect(
                once_per_turn=True,
                target=TargetSpec(
                    count=1,
                    where="own_monsters",
                    face_up=True,
                    names=frozenset({"Little-Winguard"}),
                ),
                resolve=(ChangeTargetPosition(to="toggle"),),
            ),
            whose="controller",
        ),
    ),
    # Garuda the Wind Spirit — during your OPPONENT's End Phase, change the battle
    # position of 1 face-up monster they control. (Its Nomi summon restriction — only
    # Special Summoned by banishing a WIND monster from your GY — is a summon-method
    # rule not modelled here.)
    "Garuda the Wind Spirit": (
        EndPhaseTrigger(
            Effect(
                target=TargetSpec(count=1, where="opponent_monsters", face_up=True),
                resolve=(ChangeTargetPosition(to="toggle"),),
            ),
            whose="opponent",
        ),
    ),
    # Lumina, Lightsworn Summoner — during your End Phase, send the top 3 of your Deck
    # to the GY (the Lightsworn mill; its revive is the Ignition Effect above).
    "Lumina, Lightsworn Summoner": (
        EndPhaseTrigger(Effect(resolve=(MillFromDeck(SELF, 3),)), whose="controller"),
    ),
    # The Wicked Worm Beast — mandatory: returns itself to the owner's hand during the
    # controller's End Phase (self-target by name so it only ever bounces itself).
    "The Wicked Worm Beast": (
        EndPhaseTrigger(
            Effect(
                target=TargetSpec(
                    count=1,
                    where="own_monsters",
                    face_up=True,
                    names=frozenset({"The Wicked Worm Beast"}),
                ),
                resolve=(BounceTargetsToHand(),),
            ),
            whose="controller",
        ),
    ),
})


# ===== Effects Batch 70: attack-lock floodgates (AttackRestriction extension) =====
EFFECTS.update({
    # Swords of Revealing Light — Normal Spell that stays face-up on the field; just
    # activating it places it there (the lock + 3-turn timer live in CONTINUOUS). Its
    # flip-the-opponent's-face-down-monsters rider on activation is not modelled.
    "Swords of Revealing Light": _ACTIVATE_ONTO_FIELD,
    # Gravity Bind — Continuous Trap: activate it onto the field; the Level lock is in
    # CONTINUOUS.
    "Gravity Bind": _ACTIVATE_ONTO_FIELD,
})
CONTINUOUS.update({
    # Swords of Revealing Light — while face-up, the opponent's monsters cannot declare
    # an attack; it self-destructs on the opponent's 3rd End Phase (EndPhaseTrigger ticks
    # the countdown each of their End Phases).
    "Swords of Revealing Light": (
        AttackRestriction(all_cannot_attack=True, affects="opponent"),
        EndPhaseTrigger(
            Effect(resolve=(CountdownSelfDestruct(turns=3),)), whose="opponent"
        ),
    ),
    # Gravity Bind — Level 4 or higher monsters cannot attack (both sides).
    "Gravity Bind": (AttackRestriction(max_level_can_attack=3),),
})


# ===== Effects Batch 71: "switch to Defense after attacking" family (DefenseAfterAttack) =====
CONTINUOUS.update({
    # Spear Dragon — piercing battle damage, then switches to Defense after it attacks.
    "Spear Dragon": (Piercing(), DefenseAfterAttack()),
    # Axe Dragonute — switches to Defense at the end of the Damage Step it attacks.
    "Axe Dragonute": (DefenseAfterAttack(),),
    # Goblin Attack Force — 2300 ATK; after attacking it sits in Defense and cannot
    # change position until its next turn.
    "Goblin Attack Force": (DefenseAfterAttack(lock_position=True),),
    # Goblin Elite Attack Force — same drawback (2200/1500).
    "Goblin Elite Attack Force": (DefenseAfterAttack(lock_position=True),),
    # Indomitable Fighter Lei Lei — same after-attack Defense + position lock.
    "Indomitable Fighter Lei Lei": (DefenseAfterAttack(lock_position=True),),
    # Giant Orc — 2200 ATK; after attacking, locked in Defense until its next turn.
    "Giant Orc": (DefenseAfterAttack(lock_position=True),),
})


# ===== Effects Batch 72: deck-impact staples (Ring of Destruction, Card Destruction, Dust Tornado) =====
EFFECTS.update({
    # Ring of Destruction — Normal Trap (current ruling): during the opponent's turn,
    # target 1 face-up monster they control; you take damage equal to its ATK, then deal
    # the same to the opponent, then destroy it. (Simplifications: the "ATK <= their LP"
    # targeting clause is dropped, and the burn reads effective ATK — the engine has no
    # original-ATK value source for an arbitrary target.)
    "Ring of Destruction": (
        Effect(
            speed=2,
            timing="quick",
            once_per_turn=True,
            condition=lambda s, c: s.turn_player != c,  # only during the opponent's turn
            target=TargetSpec(count=1, where="opponent_monsters", face_up=True),
            resolve=(
                InflictDamage("self", value=TargetAttack()),
                InflictDamage(OPPONENT, value=TargetAttack()),
                DestroyTargets(),
            ),
        ),
    ),
    # Card Destruction — both players discard their whole hand, then each draws that many.
    "Card Destruction": (Effect(resolve=(CardDestructionExchange(),)),),
    # Dust Tornado — Normal Trap: destroy 1 Spell/Trap your opponent controls. (Its
    # optional "then you can Set 1 Spell/Trap from your hand" rider is not modelled.)
    "Dust Tornado": (
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="opponent_spell_trap"),
            resolve=(DestroyTargets(),),
        ),
    ),
})


# ===== Effects Batch 73: permanent ATK debuff + Megamorph + Nimble (deck-impact) =====
EFFECTS.update({
    # Slate Warrior — FLIP: gains 500 ATK/DEF (a permanent self-buff). And when it is
    # destroyed by battle, the monster that destroyed it permanently loses 500 ATK/DEF.
    "Slate Warrior": (
        _flip(resolve=(ModifySelfPermanentStats(atk=500, defn=500),)),
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(DebuffBattleDestroyer(atk=-500, defn=-500),),
        ),
    ),
    # Zombyra the Dark — each time it destroys a monster by battle it permanently loses
    # 200 ATK. (Its "cannot attack directly" clause is the default for a monster, so it
    # needs no marker.)
    "Zombyra the Dark": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(ModifySelfPermanentStats(atk=-200),),
        ),
    ),
    # Megamorph — Equip Spell: activating it attaches to a monster; the LP-comparison
    # ATK multiplier (double while behind on LP, half while ahead) is the EquipMod below.
    "Megamorph": _equip_effect(),
    # Nimble Momonga — destroyed by battle & sent to the GY: gain 1000 LP, then Special
    # Summon any number of "Nimble Momonga" from the Deck in face-down Defense Position.
    "Nimble Momonga": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                GainLifePoints(SELF, 1000),
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster", name_contains=frozenset({"Nimble Momonga"})
                    ),
                    position=Position.FACE_DOWN_DEFENSE,
                    count=2,
                ),
            ),
        ),
    ),
})
CONTINUOUS.update({
    # Megamorph — ATK becomes double the equipped monster's original ATK while your LP
    # is below your opponent's, or half while it is above (read in effective_attack).
    "Megamorph": (EquipMod(scaling="lp_megamorph"),),
})

# --------------------------------------------------------------------------- #
# Effects Batch 74: deck-impact win conditions & toolbox flips. Exodia the Forbidden
# One is a kernel-level alternate win condition (assemble all five pieces in hand) —
# handled by GameState.exodia_winner / Engine._check_exodia, so the pieces need no card
# entry here. Cyber Jar floods both boards from a Flip; Maha Vailo scales with its own
# Equips; Time Wizard is a once/turn coin toss.
EFFECTS.update({
    # Cyber Jar — FLIP: destroy every monster on the field, then both players reveal the
    # top 5 of their Decks, Special Summon all revealed Level 4-or-lower monsters and add
    # the rest to their hands.
    "Cyber Jar": (
        _flip(
            resolve=(
                DestroyAllMonsters(),
                RevealTopSummonRestToHand(count=5, max_level=4, side=None),
            ),
        ),
    ),
    # Time Wizard — once/turn: toss a coin. Right -> destroy every monster the opponent
    # controls; wrong -> destroy every monster you control and take half their total ATK.
    "Time Wizard": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            resolve=(
                CoinFlip(
                    win=(DestroyAllMonsters(side=OPPONENT),),
                    lose=(DestroyOwnMonstersHalfAtkBurn(),),
                ),
            ),
        ),
    ),
})
CONTINUOUS.update({
    # Maha Vailo — gains 500 ATK for each Equip Card equipped to it (its own boost is on
    # top of whatever ATK the Equips themselves grant).
    "Maha Vailo": (SelfStatMod(scaling="equips_on_self", scale_atk=500),),
})

# --------------------------------------------------------------------------- #
# Effects Batch 75: deck-impact mechanisms — a battle-banish trigger, a GY-Standby
# self-return, and a conditional named Special Summon.
EFFECTS.update({
    # D.D. Warrior Lady — after damage calculation, when it battles an opponent's monster:
    # banish that monster and banish this card (fires whether or not either was destroyed).
    "D.D. Warrior Lady": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="battles", by=SELF),
            resolve=(BanishSelfAndEventMonster(),),
        ),
    ),
    # Elegant Egotist — while you control a "Harpie Lady", Special Summon 1 "Harpie Lady"
    # or "Harpie Lady Sisters" from your Deck (the deterministic highest-ATK pick brings
    # out Harpie Lady Sisters when it is available).
    "Elegant Egotist": (
        Effect(
            timing="ignition",
            condition=lambda s, c: any(
                i is not None
                and s.inst(i).is_face_up
                and "Harpie Lady" in s.inst(i).card.name
                and "Sisters" not in s.inst(i).card.name
                for i in s.players[c].monster_zones
            ),
            resolve=(
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster", name_contains=frozenset({"Harpie Lady"})
                    ),
                ),
            ),
        ),
    ),
})
CONTINUOUS.update({
    # Sinister Serpent — during your Standby Phase, if it is in your GY, add it back to
    # your hand. Read off the card in the GY by the engine's Standby hook.
    "Sinister Serpent": (GraveyardStandbyReturn(),),
})

# --------------------------------------------------------------------------- #
# Effects Batch 76: deck-impact toolbox — an Extra-Deck cheat, a board-reset flood, and
# the Machine ATK-doubler.
EFFECTS.update({
    # Cyber-Stein — pay 5000 LP: Special Summon 1 Fusion Monster from your Extra Deck in
    # Attack Position (deterministic highest-ATK Fusion).
    "Cyber-Stein": (
        Effect(
            timing="ignition",
            life_cost=5000,
            resolve=(SpecialSummonFromExtraDeck(),),
        ),
    ),
    # Morphing Jar #2 — FLIP: shuffle all monsters on the field into the Decks, then each
    # player excavates until they reveal as many monsters as they shuffled in, Special
    # Summoning the Level 4-or-lower ones face-down and sending the rest to the GY.
    "Morphing Jar #2": (_flip(resolve=(ShuffleFieldMonstersThenExcavate(),)),),
    # Limiter Removal — Quick-Play: double the ATK of every Machine you control until end
    # of turn, then destroy those monsters in the End Phase.
    "Limiter Removal": (
        Effect(
            speed=2,
            timing="quick",
            resolve=(DoubleControlledRaceAtkThenEndPhaseDestroy(race="Machine"),),
        ),
    ),
})

# --------------------------------------------------------------------------- #
# Effects Batch 77: deck-impact — a both-GY stat anthem, a battle-recruiter, and a
# Battle-Phase-ender.
EFFECTS.update({
    # Giant Germ — destroyed by battle & sent to the GY: inflict 500 damage, then Special
    # Summon as many "Giant Germ" as possible from the Deck in face-up Attack Position.
    "Giant Germ": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(
                InflictDamage(OPPONENT, 500),
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster", name_contains=frozenset({"Giant Germ"})
                    ),
                    count=2,
                ),
            ),
        ),
    ),
    # The Unhappy Maiden — when sent to the GY as a result of battle, the Battle Phase
    # ends immediately.
    "The Unhappy Maiden": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_battle", by=SELF),
            resolve=(EndBattlePhase(),),
        ),
    ),
})
CONTINUOUS.update({
    # Dark Magician Girl — gains 300 ATK for each "Dark Magician" or "Magician of Black
    # Chaos" in either Graveyard.
    "Dark Magician Girl": (
        SelfStatMod(
            scaling="named_in_graveyards",
            scale_atk=300,
            count_names=frozenset({"Dark Magician", "Magician of Black Chaos"}),
        ),
    ),
})

# --------------------------------------------------------------------------- #
# Effects Batch 78: deck-impact — a coin-toss attacker-neutering Trap, a GY-Standby LP
# drip, and an End-Phase summon floodgate.
EFFECTS.update({
    # Fairy Box — reactive Trap: when the opponent's monster declares an attack, toss a
    # coin; if you call it right, that monster's ATK becomes 0 for the battle. (Modelled
    # as a one-shot reaction like the other attack-declaration Traps; the Continuous
    # "pay 500 each Standby" upkeep is not modelled.)
    "Fairy Box": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="attack_declared", by=OPPONENT, subject="attacker"),
            resolve=(CoinFlip(win=(SetEventAttackerAtkZero(),)),),
        ),
    ),
    # Infinite Dismissal — Continuous Trap: activate it onto the field; the End-Phase
    # summon sweep lives in CONTINUOUS.
    "Infinite Dismissal": _ACTIVATE_ONTO_FIELD,
})
CONTINUOUS.update({
    # Darklord Marie — while in the Graveyard, gain 200 LP during each of your Standby
    # Phases.
    "Darklord Marie": (GraveyardStandbyGainLife(amount=200),),
    # Infinite Dismissal — Level 3-or-lower monsters Normal/Flip Summoned this turn are
    # destroyed in the End Phase.
    "Infinite Dismissal": (EndPhaseSummonSweep(max_level=3),),
})

# --------------------------------------------------------------------------- #
# Effects Batch 79: deck-impact — a pay-LP-to-attack monster, a face-down banisher, and a
# Nomi banish-Summon with a Battle-Phase-only enemy debuff.
EFFECTS.update({
    # Nobleman of Crossout — target 1 face-down monster; destroy and banish it, then, if
    # it was a Flip monster, each player banishes every card with that monster's name from
    # their Main Deck. (A face-down monster never flips, so no Flip Effect fires on removal.)
    "Nobleman of Crossout": (
        Effect(
            timing="ignition",
            target=TargetSpec(where="any_monster", count=1, face_down=True),
            resolve=(BanishFaceDownThenDeckBanishIfFlip(),),
        ),
    ),
})
CONTINUOUS.update({
    # Dark Elf — its controller must pay 1000 LP to declare an attack with it.
    "Dark Elf": (AttackLifeCost(amount=1000),),
    # Soul of Purity and Light — every monster the opponent controls loses 300 ATK, but
    # only during the opponent's Battle Phase.
    "Soul of Purity and Light": (
        FieldMod(atk=-300, side="opponent", only_opponent_battle_phase=True),
    ),
})
HAND_SUMMONS.update({
    # Soul of Purity and Light — cannot be Normal Summoned or Set; Special Summon it from
    # the hand by banishing 2 LIGHT monsters from your Graveyard.
    "Soul of Purity and Light": HandSpecialSummon(
        cannot_normal_summon=True,
        banish_costs=(
            SummonCost(
                count=2,
                card_filter=CardFilter(
                    card_kind="monster", attributes=frozenset({Attribute.LIGHT})
                ),
            ),
        ),
    ),
})

# --------------------------------------------------------------------------- #
# Effects Batch 80: "when you take battle damage" reactive Traps. A new post-combat
# response window (engine._fire_damage_taken_window) lets the player who took battle
# damage activate a Set Trap triggered on it; the event carries the damage amount.
# (Effect-damage activation — Numinous Healer/Attack and Receive also trigger off burn —
# is not yet modelled; only battle damage opens the window.)
EFFECTS.update({
    # Numinous Healer — when you take damage (battle OR effect): gain 1000 LP, plus 500 more
    # for each "Numinous Healer" already in your Graveyard (this copy is still on the chain,
    # not yet in the GY, so it counts only earlier copies).
    "Numinous Healer": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="damage_taken", by=SELF),
            resolve=(
                GainLifePoints(SELF, 1000),
                GainLifePoints(
                    SELF,
                    value=CountTimes(
                        per=500,
                        pool="own_graveyard",
                        card_filter=CardFilter(names=frozenset({"Numinous Healer"})),
                    ),
                ),
            ),
        ),
    ),
    # Attack and Receive — when you take damage (battle OR effect): inflict 700 to your opponent.
    "Attack and Receive": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="damage_taken", by=SELF),
            resolve=(InflictDamage(OPPONENT, 700),),
        ),
    ),
    # Damage Condenser — when you take battle damage: discard 1 card, then Special Summon 1
    # monster from your Deck with ATK <= the battle damage you took, in face-up Attack
    # Position (deterministic highest-ATK eligible pick).
    "Damage Condenser": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(kind="damage_taken", by=SELF, battle_only=True),
            discard_cost=1,
            resolve=(SpecialSummonFromDeckAtkAtMostBattleDamage(),),
        ),
    ),
})

# --------------------------------------------------------------------------- #
# Effects Batch 81: deck-COMPLETION targets (each is the last unimplemented card in 2-3
# GBA decks). A Ritual Spell, a Nomi Winged Beast, and a piercing Equip.
EFFECTS.update({
    # Black Magic Ritual — Ritual Summon "Magician of Black Chaos" (Tribute monsters
    # totalling Level 8+). Structurally identical to Black Luster Ritual.
    "Black Magic Ritual": (
        Effect(timing="ritual", condition=_can_ritual_summon_for("Magician of Black Chaos")),
    ),
    # Big Bang Shot — Equip: +400 ATK, the equipped monster pierces, and when this card
    # leaves the field it banishes the monster it was equipped to.
    "Big Bang Shot": (
        *_equip_effect(),
        _on_sent_to_gy((BanishEquippedMonster(),)),
    ),
})
RITUALS.update({
    "Black Magic Ritual": "Magician of Black Chaos",
})
CONTINUOUS.update({
    # Big Bang Shot — +400 ATK and grants piercing while attached (read by has_piercing).
    "Big Bang Shot": (EquipMod(atk=400, grants_piercing=True),),
})
HAND_SUMMONS.update({
    # Harpie Lady Sisters — cannot be Normal Summoned/Set; it has no self-Summon of its
    # own (the condition never holds), so it only ever reaches the field via Elegant
    # Egotist (which Special Summons it from the Deck — see Batch 75).
    "Harpie Lady Sisters": HandSpecialSummon(
        cannot_normal_summon=True, condition=lambda s, c: False
    ),
})

# --------------------------------------------------------------------------- #
# Effects Batch 82: Blast Sphere (deck-impact). A face-down Defense monster that, when
# attacked, equips ITSELF to the attacker before damage calculation (the attack then
# fizzles — its target is gone), then on the attacker's controller's next Standby Phase
# destroys that monster and burns its controller for its ATK.
EFFECTS.update({
    # Part 1 (reactive Trigger): attacked by an opponent's monster -> equip to the
    # attacker. The engine fires this before damage calculation and re-checks the
    # target afterward, so the moved monster fizzles the attack.
    "Blast Sphere": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="attacked", by=OPPONENT),
            resolve=(EquipSelfToAttacker(),),
        ),
    ),
})
CONTINUOUS.update({
    # Part 2 (delayed payoff): once Blast Sphere is an Equip Card, on its controller's
    # opponent's (= the attacker's) next Standby Phase, destroy the equipped monster and
    # inflict its ATK as damage. ``requires_equipped`` keeps it inert while Blast Sphere
    # is still a face-up monster; firing destroys the host -> Blast Sphere is orphaned and
    # cleaned to the GY, so it resolves exactly once.
    "Blast Sphere": (
        StandbyTrigger(
            Effect(resolve=(DestroyEquipHostThenBurn(),)),
            whose="opponent",
            requires_equipped=True,
        ),
    ),
})

# Effects Batch 83: the "when this card is destroyed" bucket. The engine now stamps an
# effect destruction (``died_by_effect``, set by every Destroy* primitive) the way it
# already stamped a battle death, so a monster's field→GY trigger can key off HOW it
# died: "destroyed_by_effect" (only a card effect) or the unified "destroyed" (battle OR
# effect, but not a tribute/discard/mill send). Both fire from the same GY-queue drain
# the recruiters use.
EFFECTS.update({
    # Babycerasaurus: "If this card is destroyed by a card effect and sent to the
    # Graveyard: Special Summon 1 Level 4 or lower Dinosaur-Type monster from your Deck."
    # A clean "destroyed_by_effect" SELF trigger — a battle death does NOT fire it.
    "Babycerasaurus": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed_by_effect", by=SELF),
            resolve=(
                SpecialSummonFromDeck(
                    card_filter=CardFilter(
                        card_kind="monster", races=frozenset({"Dinosaur"}), max_level=4
                    )
                ),
            ),
        ),
    ),
    # Granadora: gains 1000 LP on ANY Summon (Normal/Flip/Special), and on being
    # destroyed and sent to the GY — by battle OR by a card effect — burns its controller
    # 2000. The unified "destroyed" trigger covers both death causes; the summon half is a
    # plain by-SELF summon trigger (no summon_kinds = any Summon).
    "Granadora": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF),
            resolve=(GainLifePoints(SELF, 1000),),
        ),
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed", by=SELF),
            resolve=(InflictDamage(SELF, 2000),),
        ),
    ),
})

# Effects Batch 84: "when you gain Life Points" (ROADMAP #3, TIMING_RECOVER). state.
# gain_life_points is now the single LP-gain sink (every healing path — the GainLifePoints
# primitive, the Standby/draw-trigger upkeep markers — routes through it), recording each
# gain so the engine's life-gain window can react. Fire Princess is the sole pre-Synchro
# consumer, but the window is reusable for any future "each time you gain LP" card.
CONTINUOUS.update({
    # Fire Princess: "Each time you gain Life Points, inflict 500 damage to your opponent."
    # A face-up continuous trigger (LifeGainTrigger) fired once per gain event as the
    # controller's effect, so it pairs with the classic LP engines — Solemn Wishes (gain
    # on draw), Cure Mermaid (Standby gain), Numinous Healer, any healing Spell.
    "Fire Princess": (
        LifeGainTrigger(Effect(resolve=(InflictDamage(OPPONENT, 500),))),
    ),
})

# Effects Batch 85: battle-damage prevention (deck-impact #18 — Kuriboh). All battle
# damage to a player now flows through one chokepoint (_resolve_attack's _take_battle_
# damage), which consults state.takes_no_battle_damage, so a card can zero the damage for
# one battle or one turn.
EFFECTS.update({
    # Kuriboh: "During damage calculation, if your opponent's monster attacks (Quick
    # Effect): You can discard this card; you take no battle damage from that battle." A
    # hand quick effect offered by the engine's damage-step window (kind="damage_step",
    # by=OPPONENT — the attacker is the activator's opponent); discarding it is the cost,
    # and PreventBattleDamageThisBattle adds the controller to the per-battle immunity.
    "Kuriboh": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="damage_step", by=OPPONENT),
            resolve=(PreventBattleDamageThisBattle(),),
        ),
    ),
    # Winged Kuriboh: "If this card on the field is destroyed and sent to the GY: For the
    # rest of this turn, you take no battle damage." Reuses Batch 83's unified "destroyed"
    # GY trigger (battle OR effect); PreventBattleDamageThisTurn stamps the turn-scoped
    # immunity that the same _take_battle_damage chokepoint reads.
    "Winged Kuriboh": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroyed", by=SELF),
            resolve=(PreventBattleDamageThisTurn(),),
        ),
    ),
})

# Effects Batch 86: Nutrient Z (deck-impact #19) — a PRE-damage replacement. The engine's
# damage-step window now previews the incoming battle damage (battle_damage_preview), so a
# Set Trap can react to its amount before it lands. Nutrient Z gains 4000 LP *first* when
# its controller is about to take 2000+ battle damage, then the (unchanged) damage applies
# — and the gain itself feeds the Batch 84 life-gain window (Fire Princess).
EFFECTS.update({
    # "During damage calculation, when you are about to take 2000 or more battle damage:
    # Gain 4000 LP first." A Set Normal Trap (speed 2) offered to the player about to take
    # the damage (to_victim) when the previewed amount is 2000+ (min_battle_damage).
    "Nutrient Z": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(
                kind="damage_step", by=SELF, to_victim=True, min_battle_damage=2000
            ),
            resolve=(GainLifePoints(SELF, 4000),),
        ),
    ),
})

# Effects Batch 87: "when you draw" draw-again engines (ROADMAP #3, TIMING_DRAW). draw()
# now records WHICH cards each draw event produced; the engine, after every draw, draws 1
# more if a face-up DrawAgainOnDraw card the drawer controls matches a just-drawn card. The
# extra draw is a fresh event, so a run of matches chains (bounded by the deck).
CONTINUOUS.update({
    # Heart of the Underdog (Continuous Spell): "During your Draw Phase, when you draw a
    # Normal Monster(s): You can reveal it; draw 1 more card." Draw-Phase-only, vanilla.
    "Heart of the Underdog": (
        DrawAgainOnDraw(CardFilter(card_kind="normal_monster"), draw_phase_only=True),
    ),
    # Tethys, Goddess of Light: "When you draw a Fairy monster(s) ...: draw 1 card." Any
    # draw (must be face-up on the field, which the active-markers scan already requires).
    "Tethys, Goddess of Light": (
        DrawAgainOnDraw(CardFilter(card_kind="monster", races=frozenset({"Fairy"}))),
    ),
})

# Effects Batch 88: Parasite Paracide (deck-impact) — the bury-and-ambush Flip Insect.
# Two effects compose its two-stage trick, riding infrastructure already in place:
#  (1) FLIP -> PlantSelfInOpponentDeck buries this card in the opponent's Deck and
#      shuffles (state.send_to_player_deck transfers ownership so it lives entirely on
#      their side; the copy is flagged ``planted``).
#  (2) timing="drawn" -> when that buried copy is drawn, engine._fire_drawn_card_triggers
#      resolves this effect FOR THE DRAWER (riding Batch 87's per-draw record): it Special
#      Summons itself onto the drawer's field in face-up Defense (SpecialSummonSelf) and
#      burns the drawer 1000 (InflictDamage(SELF, ...) — SELF == the resolving drawer).
# DEFERRED RIDER: the printed "all monsters the drawer controls become Insect-Type" clause
# is a continuous race-override (EFFECT_CHANGE_RACE). No pre-Synchro pool card we ship keys
# off the *opponent's* monsters being Insect in a way that this would swing (the Insect
# consumers — Eradicating Aerosol, tribute_races, the Laser Cannon equips — read the static
# printed race), and a derived effective_race() through every consumer is broad infra for a
# rare combo. The high-impact behavior (a dead monster + 1000 burn dumped on the drawer) is
# modeled; the Insect-typing rider is a documented simplification.
EFFECTS.update({
    "Parasite Paracide": (
        _flip(resolve=(PlantSelfInOpponentDeck(),)),
        Effect(
            speed=1,
            timing="drawn",
            resolve=(
                SpecialSummonSelf(position=Position.FACE_UP_DEFENSE),
                InflictDamage(SELF, 1000),
            ),
        ),
    ),
})

# Effects Batch 89: the Exodia package — the single highest-leverage deck-coverage move.
# Exodia itself needs NO effect entry: the five "Forbidden One" pieces win via the engine
# kernel (state.exodia_winner / engine._check_exodia), so deckbuild._KERNEL_IMPLEMENTED now
# counts the head as functional (it was a false negative). These three companion cards are
# the real builds — each is a blocker alongside Exodia in the GBA Exodia-stall decks:
EFFECTS.update({
    # Big Eye: "FLIP: Look at up to 5 cards from the top of your Deck, then place them on
    # the top in any order." Headless, the engine surfaces the best monster to the top.
    "Big Eye": (_flip(resolve=(LookAtTopReorderBestFirst(count=5),)),),
    # Backup Soldier (Normal Trap): "While there are 5+ monsters in your GY: add up to 3
    # non-Effect Monsters with <=1500 ATK from your GY to your hand." Manually activated
    # (speed-2 ignition), gated on the GY count.
    "Backup Soldier": (
        Effect(
            speed=2,
            timing="ignition",
            condition=lambda s, c: sum(
                1 for i in s.players[c].graveyard if s.inst(i).card.is_monster
            )
            >= 5,
            resolve=(
                ReturnFromGraveyardToHand(
                    CardFilter(card_kind="normal_monster", max_atk=1500), count=3
                ),
            ),
        ),
    ),
})

# Buster Blader: continuous self-boost — "Gains 500 ATK for each Dragon monster your
# opponent controls or is in their GY" (ATK only). New SelfStatMod scaling mode.
CONTINUOUS.update({
    "Buster Blader": (
        SelfStatMod(
            scaling="opponent_field_and_gy_race", scale_atk=500, count_race="Dragon"
        ),
    ),
})

# Effects Batch 90: the heavy-hitting disruption cards (each a blocker in ~8 GBA decks).
EFFECTS.update({
    # Solemn Judgment (Counter Trap): "Pay half your LP; negate a Summon OR a Spell/Trap
    # activation, and if you do, destroy that card." Composed from the two existing
    # negation seams — the quick chain-response (Magic Jammer / Dark Bribe) for a S/T
    # activation, and the Summon-response window (Horn of Heaven) for a Summon — each
    # paying half LP first (LoseHalfLifePoints subtracts directly, so it's a cost, not
    # damage). The Summon window fires on Normal Summons (the documented simplification).
    "Solemn Judgment": (
        Effect(
            speed=3,
            timing="quick",
            condition=_chain_top_is_spell_or_trap,
            resolve=(LoseHalfLifePoints(SELF), NegatePreviousLink()),
        ),
        Effect(
            speed=3,
            timing="trigger",
            trigger=Trigger(kind="summon", by=OPPONENT, subject="monster"),
            resolve=(LoseHalfLifePoints(SELF), DestroyTargets()),
        ),
    ),
    # Tribe-Infecting Virus: "Discard 1; declare 1 Type; destroy all face-up monsters of
    # that Type on the field." A monster Ignition effect: discard cost paid by the engine,
    # gated to when the opponent has a face-up monster; the new primitive declares the
    # Type that nets the most enemy monsters and wipes both sides of it.
    "Tribe-Infecting Virus": (
        Effect(
            timing="ignition",
            discard_cost=1,
            condition=_opponent_has_faceup_monster,
            resolve=(DestroyFaceUpMonstersOfDeclaredType(),),
        ),
    ),
})

# Effects Batch 91: utility + battle staples (each a blocker across several GBA decks).
EFFECTS.update({
    # Magical Mallet: "Shuffle any number of cards from your hand into the Deck, then draw
    # that many." Headless = shuffle the whole hand back and redraw it (a full refresh).
    "Magical Mallet": (Effect(resolve=(ShuffleHandIntoDeckThenDraw(),)),),
    # Metalmorph (Normal Trap): equip to a face-up monster you control. +300 ATK/DEF
    # (EquipMod, below) and — when it attacks — half its target's ATK during the Damage
    # Step (the DamageStepBonus half_opposing_atk rider, below).
    "Metalmorph": (
        Effect(
            speed=2,
            timing="quick",
            target=TargetSpec(count=1, where="own_monsters", face_up=True),
            resolve=(EquipToTarget(),),
        ),
    ),
    # Wall of Illusion: "If this card is attacked, after damage calculation: return the
    # attacker to the hand." A speed-1 trigger off the attacked-monster window.
    "Wall of Illusion": (
        Effect(
            speed=1,
            timing="trigger",
            trigger=Trigger(kind="attacked", by=OPPONENT),
            resolve=(ReturnEventAttackerToHand(),),
        ),
    ),
})

CONTINUOUS.update({
    # Metalmorph's equipped boost + the attack-time damage-step rider (read off the equip).
    "Metalmorph": (
        EquipMod(atk=300, defn=300),
        DamageStepBonus(when="attacking", half_opposing_atk=True),
    ),
    # Panther Warrior: "cannot declare an attack unless you Tribute 1 monster."
    "Panther Warrior": (AttackTributeCost(count=1),),
})


# Effects Batch 92: the Toon monsters. The engine already enforces the shared Toon rules
# — a Toon needs your face-up Toon World to be Summoned (moves.controls_toon_world), can't
# attack the turn it's Summoned, attacks directly unless the opponent controls a Toon
# (moves._toon_attack_targets), and is destroyed when Toon World leaves (engine._cleanup_
# toons). These entries add the per-card pieces.
def _controls_toon_world(state, controller) -> bool:
    return any(
        sid is not None
        and state.inst(sid).is_face_up
        and state.inst(sid).card.name == "Toon World"
        for sid in state.players[controller].spell_trap_zones
    )


HAND_SUMMONS.update({
    # Blue-Eyes Toon Dragon: cannot be Normal Summoned; SS from hand by Tributing 2 while
    # you control Toon World. Toon Summoned Skull is the same with 1 Tribute.
    "Blue-Eyes Toon Dragon": HandSpecialSummon(
        cannot_normal_summon=True, tribute_count=2, condition=_controls_toon_world
    ),
    "Toon Summoned Skull": HandSpecialSummon(
        cannot_normal_summon=True, tribute_count=1, condition=_controls_toon_world
    ),
})

CONTINUOUS.update({
    # "You must pay 500 LP to declare an attack" — the two big Toons (Toon Gemini Elf has
    # no such cost). Reuses the AttackLifeCost rider (enumeration gates on payability;
    # engine._declare_attack pays it).
    "Blue-Eyes Toon Dragon": (AttackLifeCost(amount=500),),
    "Toon Summoned Skull": (AttackLifeCost(amount=500),),
})

EFFECTS.update({
    # Toon Gemini Elf: a Level-4 Toon (Normal-Summonable while you control Toon World, which
    # the engine already gates). "If this card inflicts battle damage to your opponent:
    # discard 1 random card from their hand."
    "Toon Gemini Elf": (
        _on_battle_damage((DiscardFromHand(OPPONENT, count=1, random=True),)),
    ),
})


# Effects Batch 93: the Ritual-absorb cluster — Relinquished + Thousand-Eyes Restrict.
# Their signature is the absorb: once per turn, equip an opponent's monster onto this card
# (it leaves their field), and this card's ATK/DEF become equal to it. Relinquished is
# Ritual Summoned (Black Illusion Ritual); Thousand-Eyes Restrict is Fusion Summoned
# ("Relinquished" + "Thousand-Eyes Idol") and additionally locks the board.
# DEFERRED (documented): the printed "if this card would be destroyed by battle, destroy
# the equipped monster instead" battle-replacement, and TER's "cannot change battle
# position" half of its lock. TER's attack-lock is modeled as a both-sides blanket that
# also stops TER itself (a 0-ATK floodgate) — a minor simplification of "OTHER monsters".
RITUALS.update({"Black Illusion Ritual": "Relinquished"})

FUSIONS.update({"Thousand-Eyes Restrict": ("Relinquished", "Thousand-Eyes Idol")})

EFFECTS.update({
    # Black Illusion Ritual: the Ritual Spell that summons Relinquished.
    "Black Illusion Ritual": (
        Effect(timing="ritual", condition=_can_ritual_summon_for("Relinquished")),
    ),
    # The absorb — once per turn, target a monster the opponent controls and equip it.
    "Relinquished": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(AbsorbMonsterAsEquip(),),
        ),
    ),
    "Thousand-Eyes Restrict": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(AbsorbMonsterAsEquip(),),
        ),
    ),
})

CONTINUOUS.update({
    # ATK/DEF become equal to the absorbed monster (base 0/0 + the absorbed stats).
    "Relinquished": (SelfStatMod(scaling="absorbed_monster"),),
    # TER copies too, and locks the board: no monster may declare an attack while it's out.
    "Thousand-Eyes Restrict": (
        SelfStatMod(scaling="absorbed_monster"),
        AttackRestriction(all_cannot_attack=True, affects="both"),
    ),
})


# Effects Batch 94: the Water / "Umi" cluster — A Legendary Ocean, Tornado Wall, The
# Legendary Fisherman. A Legendary Ocean is always treated as "Umi" (state._UMI_NAMES), so
# the other two key off it via state.controls_face_up_umi.
# DEFERRED (documented): A Legendary Ocean's "reduce all WATER monsters' Level by 1" (no
# effective-Level layer yet); The Legendary Fisherman's "unaffected by Spell effects" (no
# spell-immunity layer); Tornado Wall's self-destruct when Umi leaves (the no-damage effect
# already re-checks Umi each time, so it simply stops working — the card just lingers).
EFFECTS.update({
    "A Legendary Ocean": _ACTIVATE_ONTO_FIELD,  # a Field Spell (treated as "Umi")
    "Tornado Wall": _ACTIVATE_ONTO_FIELD,  # a Continuous Trap
})

CONTINUOUS.update({
    # All WATER monsters on the field gain 200 ATK/DEF.
    "A Legendary Ocean": (
        FieldMod(atk=200, defn=200, attributes=frozenset({Attribute.WATER})),
    ),
    # While you control a face-up Umi, you take no battle damage from attacking monsters.
    "Tornado Wall": (NoBattleDamageWhileUmi(),),
    # While Umi is face-up, The Legendary Fisherman cannot be selected as an attack target
    # (the opponent may still attack you directly).
    "The Legendary Fisherman": (
        AttackTargetProtection(self_only=True, requires_face_up_umi=True),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 95: the Graveyard / discard punishers — Banisher of the Light and
# Magical Thorn. Both are state-level replacements/triggers read by send_to_graveyard:
# Banisher redirects every send-to-GY into a banish; Magical Thorn burns the opponent
# whenever one of their hand cards is discarded. Each clears two one-card-from-ready decks.
CONTINUOUS.update({
    # Banisher of the Light — any card (either player's) sent to the GY is banished instead.
    "Banisher of the Light": (BanishInsteadOfGraveyard(),),
    # Magical Thorn — when an opponent's hand card is discarded to the GY, burn them 500
    # for each (a Continuous Trap: it must be face-up to apply).
    "Magical Thorn": (BurnOnHandDiscard(amount=500),),
})

EFFECTS.update({
    # Magical Thorn is a Continuous Trap: activating it just sets it face-up on the field,
    # where its BurnOnHandDiscard rider then watches every opponent discard.
    "Magical Thorn": _ACTIVATE_ONTO_FIELD,
})


# --------------------------------------------------------------------------- #
# Effects Batch 96: the Weevil insect-trap pair — Acid Trap Hole and Drill Bug.
# Together they flip Weevil's 4th Reshef deck (a two-blocker) to fully ready, and Acid
# Trap Hole flips two more one-card-from-ready decks on its own.
EFFECTS.update({
    # Acid Trap Hole — a Normal Trap activated at will: target 1 face-down Defense-Position
    # monster, flip it up, then destroy it if its DEF <= 2000, else set it back face-down.
    "Acid Trap Hole": (
        Effect(
            speed=2,
            timing="ignition",
            target=TargetSpec(count=1, where="any_monster", face_down=True),
            resolve=(AcidTrapHole(),),
        ),
    ),
    # Drill Bug — when it inflicts battle damage to the opponent, fetch 1 "Parasite
    # Paracide" from your Deck, shuffle, and set it on top of your Deck (its Batch 88 combo
    # piece: you then draw and bury it in the opponent's Deck).
    "Drill Bug": (_on_battle_damage((SearchCardToTopOfDeck(name="Parasite Paracide"),)),),
})


# --------------------------------------------------------------------------- #
# Effects Batch 97: a clean summon/attack/flip trio — Eatgaboon (a Trap-Hole variant),
# The Stern Mystic (a no-op reveal Flip), and Gravekeeper's Servant (an attack-mill tax).
# Each clears one more one-card-from-ready deck.
EFFECTS.update({
    # Eatgaboon — when the opponent Normal/Flip Summons a monster with ATK <= 500, destroy
    # it (the same response-trap shape as Trap Hole, with an upper ATK gate instead).
    "Eatgaboon": (
        Effect(
            speed=2,
            timing="trigger",
            trigger=Trigger(
                kind="summon",
                by=OPPONENT,
                subject="monster",
                max_atk=500,
                summon_kinds=frozenset({"normal", "flip"}),  # not Special Summons
            ),
            resolve=(DestroyTargets(),),
        ),
    ),
    # The Stern Mystic — FLIP: reveal all face-down cards, then return them to their
    # original positions. That nets to no board change, so its Flip resolves to nothing
    # (the information reveal isn't modelled); the Flip entry keeps the card functional.
    "The Stern Mystic": (_flip(resolve=()),),
    # Gravekeeper's Servant — a Continuous Spell: activating it sets it face-up, where its
    # OpponentMillToAttack rider taxes the opponent 1 mill per attack declaration.
    "Gravekeeper's Servant": _ACTIVATE_ONTO_FIELD,
})

CONTINUOUS.update({
    # The opponent must send 1 card from the top of their Deck to the GY to declare an
    # attack (an opponent who can't pay simply cannot attack).
    "Gravekeeper's Servant": (OpponentMillToAttack(count=1),),
})


# --------------------------------------------------------------------------- #
# Effects Batch 98: Susa Soldier — a 2000-ATK beatstick whose three printed static
# abilities (carried as continuous riders) clear two more one-card-from-ready decks.
CONTINUOUS.update({
    # Susa Soldier: cannot be Special Summoned; returns to the owner's hand during the End
    # Phase of the turn it is Normal Summoned / flipped face-up; the battle damage it
    # inflicts to the opponent is halved.
    "Susa Soldier": (
        CannotBeSpecialSummoned(),
        ReturnsToHandAtEndPhase(),
        HalvesBattleDamageDealt(),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 99: a Ritual pair + their boss. Curse of the Masked Beast and Shinato's
# Ark are Ritual Spells (mirroring the Black Illusion Ritual wiring of Batch 93); Shinato,
# King of a Higher Plane gets its Defense-Position battle burn so it is functional too.
# The two Ritual Spells each clear one more one-card-from-ready deck.
RITUALS.update({
    "Curse of the Masked Beast": "The Masked Beast",
    "Shinato's Ark": "Shinato, King of a Higher Plane",
})

EFFECTS.update({
    "Curse of the Masked Beast": (
        Effect(timing="ritual", condition=_can_ritual_summon_for("The Masked Beast")),
    ),
    "Shinato's Ark": (
        Effect(timing="ritual", condition=_can_ritual_summon_for("Shinato, King of a Higher Plane")),
    ),
    # Shinato — when it destroys a Defense-Position monster by battle, burn the opponent
    # for that monster's original ATK.
    "Shinato, King of a Higher Plane": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="destroys_by_battle", by=SELF),
            resolve=(BurnDefenseMonsterOriginalAtk(),),
        ),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 100: position & flip control — Dream Clown and Invader of the Throne.
# Built on two new engine seams: a "changed_to_defense" Trigger fired when a monster is
# manually switched from Attack to face-up Defense, and state.swap_control (a deadlock-free
# permanent control exchange). Each card clears one more one-card-from-ready deck.
def _not_battle_phase(state, controller) -> bool:
    """Invader of the Throne's FLIP cannot be activated during the Battle Phase."""
    return state.phase is not Phase.BATTLE


EFFECTS.update({
    # Dream Clown — when switched from Attack to face-up Defense Position, destroy 1
    # monster the opponent controls.
    "Dream Clown": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="changed_to_defense", by=SELF),
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(DestroyTargets(),),
        ),
    ),
    # Invader of the Throne — FLIP: switch control of 1 opponent monster with this card
    # (not during the Battle Phase, so a flip in combat does nothing).
    "Invader of the Throne": (
        Effect(
            speed=1,
            timing="flip",
            condition=_not_battle_phase,
            target=TargetSpec(count=1, where="opponent_monsters"),
            resolve=(SwapControlWithTarget(),),
        ),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 101: Insect Queen — a board-scaling Insect boss with three clauses, all
# carried as continuous riders. Clears one more one-card-from-ready deck and anchors the
# Insect package (Weevil's decks still also want Steel Scorpion).
CONTINUOUS.update({
    "Insect Queen": (
        # Gains 200 ATK for each Insect monster on the field (both sides, itself included).
        SelfStatMod(scaling="race_on_field", scale_atk=200, count_race="Insect"),
        # Cannot declare an attack unless you Tribute 1 monster (reuses the Panther Warrior
        # attack-Tribute cost wired in Batch 91).
        AttackTributeCost(count=1),
        # Once per turn during the End Phase, if it destroyed an opponent's monster by
        # battle this turn, Special Summon 1 "Insect Monster Token" (Insect/EARTH/L1/100/100).
        EndPhaseTrigger(
            effect=Effect(
                resolve=(
                    SummonTokenIfDestroyedByBattle(
                        token_name="Insect Monster Token",
                        race="Insect",
                        attribute=Attribute.EARTH,
                        level=1,
                        atk=100,
                        defn=100,
                    ),
                ),
            ),
            whose="controller",
        ),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 102: board-conditional stat cards — Nuvia the Wicked and Aqua Chorus.
# Each clears one more one-card-from-ready deck.
EFFECTS.update({
    # Nuvia the Wicked — if Normal Summoned, destroy itself (a downside that makes it a
    # Set/Flip-only body). Its ATK-loss per opponent monster lives in CONTINUOUS below.
    "Nuvia the Wicked": (
        Effect(
            timing="trigger",
            trigger=Trigger(kind="summon", by=SELF, subject="monster", summon_kinds=frozenset({"normal"})),
            resolve=(DestroySelf(),),
        ),
    ),
    # Aqua Chorus — a Continuous Trap: activating it just sets it face-up, where its
    # SameNameAnthem rider boosts every same-named pair on the field.
    "Aqua Chorus": _ACTIVATE_ONTO_FIELD,
})

CONTINUOUS.update({
    # Nuvia the Wicked loses 200 ATK for each monster the opponent controls.
    "Nuvia the Wicked": (SelfStatMod(scaling="opponent_monsters", scale_atk=-200),),
    # Aqua Chorus: monsters sharing a name with another face-up monster gain 500 ATK/DEF.
    "Aqua Chorus": (SameNameAnthem(atk=500, defn=500),),
})


# --------------------------------------------------------------------------- #
# Effects Batch 103: Multiply — the Kuriboh token-swarm Quick-Play. Adds a reusable
# tribute_names cost filter (Tribute fodder restricted by exact name). Clears one more
# one-card-from-ready deck.
def _controls_face_up_kuriboh(state, controller) -> bool:
    return any(
        i is not None and state.cards[i].is_face_up and state.cards[i].card.name == "Kuriboh"
        for i in state.players[controller].monster_zones
    )


EFFECTS.update({
    # Multiply — Tribute 1 face-up "Kuriboh"; Special Summon as many "Kuriboh Tokens"
    # (Fiend/DARK/L1/300/200) as possible in Defense Position. CreateToken fills every
    # empty Monster Zone (the Tribute frees one first).
    "Multiply": (
        Effect(
            speed=2,
            timing="quick",
            condition=_controls_face_up_kuriboh,
            tribute_cost=1,
            tribute_names=frozenset({"Kuriboh"}),
            resolve=(
                CreateToken(
                    token_name="Kuriboh Token",
                    race="Fiend",
                    attribute=Attribute.DARK,
                    level=1,
                    atk=300,
                    defn=200,
                    count=5,
                    position=Position.FACE_UP_DEFENSE,
                ),
            ),
        ),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 104: Cave Dragon — two reusable static restrictions. Clears one more
# one-card-from-ready deck.
CONTINUOUS.update({
    "Cave Dragon": (
        # Cannot be Normal Summoned/Set while you control a monster.
        NoNormalSummonWhileControllingMonster(),
        # Cannot declare an attack unless you control another Dragon-Type monster.
        CannotAttackUnlessControlRace(race="Dragon"),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 105: Cyber Harpie Lady — its name is always treated as "Harpie Lady", so
# Harpie support (Cyber Shield's equip, Elegant Egotist, Harpie's Pet Dragon's count) sees
# it as one. Modelled as a NameTreatedAs rider read by card_matches_traits. Clears one more
# one-card-from-ready deck (Mai Valentine's Harpie deck).
CONTINUOUS.update({
    "Cyber Harpie Lady": (NameTreatedAs(name="Harpie Lady"),),
})


# --------------------------------------------------------------------------- #
# Effects Batch 106: Alligator's Sword Dragon — a Fusion that can attack directly when the
# opponent's only face-up monsters are EARTH/WATER/FIRE. Clears one more one-card-from-ready
# deck (Joey's Worldwide deck).
FUSIONS.update({"Alligator's Sword Dragon": ("Baby Dragon", "Alligator's Sword")})

CONTINUOUS.update({
    "Alligator's Sword Dragon": (
        CanAttackDirectly(
            only_if_opponent_attributes=frozenset({Attribute.EARTH, Attribute.WATER, Attribute.FIRE})
        ),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 107: continuous ATK/DEF scaling by board/hand count. The single
# highest-incidence cheap win — Machine King appears in 5 GBA decks, the Muka Mukas
# and Flash Assailant in several more. Machine King reuses the existing "race_on_field"
# mode (Insect Queen, Batch 101); the Muka Muka family needs only the new "hand_size"
# scaling mode added to state._self_stat_delta.
CONTINUOUS.update({
    # Machine King: gains 100 ATK for each Machine-Type monster on the field (both
    # sides, including itself — race_on_field counts every face-up Machine).
    "Machine King": (SelfStatMod(scaling="race_on_field", count_race="Machine", scale_atk=100),),
    # Muka Muka: gains 300 ATK and DEF for each card in your hand.
    "Muka Muka": (SelfStatMod(scaling="hand_size", scale_atk=300, scale_defn=300),),
    # Enraged Muka Muka: the same, but +400 per card.
    "Enraged Muka Muka": (SelfStatMod(scaling="hand_size", scale_atk=400, scale_defn=400),),
    # Flash Assailant: LOSES 400 ATK and DEF for each card in your hand (negative scale).
    "Flash Assailant": (SelfStatMod(scaling="hand_size", scale_atk=-400, scale_defn=-400),),
})


# --------------------------------------------------------------------------- #
# Effects Batch 108: Standby/End-Phase upkeep beatsticks — both reuse existing infra,
# no engine change. Solar Flare Dragon (3 GBA decks) and Legendary Fiend (3) were the
# only pool cards in this seam with a fully-clean single ruling; the rest are Nomi/LV/
# pay-or-die/counter cards deferred elsewhere.
CONTINUOUS.update({
    # Solar Flare Dragon: cannot be selected as an attack target while you control another
    # Pyro (a self-only AttackTargetProtection gated on another Pyro), and burns the
    # opponent for 500 at each of your End Phases.
    "Solar Flare Dragon": (
        AttackTargetProtection(self_only=True, requires_control_other_race="Pyro"),
        EndPhaseTrigger(Effect(resolve=(InflictDamage(OPPONENT, 500),)), whose="controller"),
    ),
    # Legendary Fiend: once per turn during your Standby Phase, permanently gains 700 ATK
    # (whose="controller" already fires exactly once per turn, satisfying "once per turn").
    "Legendary Fiend": (
        StandbyTrigger(Effect(resolve=(ModifySelfPermanentStats(atk=700),)), whose="controller"),
    ),
})


# --------------------------------------------------------------------------- #
# Effects Batch 109: coin-flip stat gamble. Goddess of Whim is the only pool coin card
# with a fully-clean single ruling (the rest are Arcana Force / multi-coin-tier / skip-
# turn cards). New reusable ScaleSelfAtkTemporary primitive (double/halve own ATK till the
# End Phase), driven by the existing CoinFlip win/lose branches.
EFFECTS.update({
    "Goddess of Whim": (
        Effect(
            timing="ignition",
            once_per_turn=True,
            resolve=(
                CoinFlip(
                    win=(ScaleSelfAtkTemporary(num=2, den=1),),  # called right -> double ATK
                    lose=(ScaleSelfAtkTemporary(num=1, den=2),),  # called wrong -> halve ATK
                ),
            ),
        ),
    ),
})
