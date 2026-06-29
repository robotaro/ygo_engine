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
    BattleIndestructible,
    BounceTargetsToDeck,
    BounceTargetsToHand,
    CanAttackDirectly,
    CardFilter,
    CountTimes,
    CreateToken,
    DamageEqualToAttackerAtk,
    DestroyAllFieldSpells,
    DestroyAllOtherCards,
    DestroyAllSpellTraps,
    DestroyAllMonsters,
    DestroyAttackingAttackPositionMonsters,
    DestroyFaceUpMonstersWithDefAtMost,
    DestroyHighestAtkMonster,
    DestroyHighestDefOpponentMonster,
    DestroyLowestAtkOpponentMonster,
    DestroyTargets,
    DiscardFromHand,
    DiscardHandThenBurn,
    Draw,
    DrawTrigger,
    Effect,
    EquipMod,
    EquipToTarget,
    FieldMod,
    GainLifePoints,
    HandSpecialSummon,
    InflictDamage,
    MillFromDeck,
    ModifyStatsTemporary,
    NegateAttack,
    NegatePreviousLink,
    Piercing,
    PlaceCountersOnSelf,
    ReturnAllSetCardsToHand,
    ReturnAllSpellTrapsToHand,
    ReturnFromGraveyardToDeck,
    ReturnFromGraveyardToHand,
    ReturnFromHandToDeck,
    ReturnSelfToDeck,
    ReturnSpellFromGraveyardToHand,
    SearchFromDeck,
    SearchMonsterToHand,
    SelfStatMod,
    SpecialSummonFromDeck,
    SpecialSummonFromGraveyard,
    SpellCounterHolder,
    StandbyUpkeep,
    SummonCost,
    SwitchTargetsToAttack,
    TakeControl,
    TargetAttack,
    TargetSpec,
    Trigger,
    TributedAttack,
    UnionMod,
)
from .enums import Attribute, Position

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


def _opponent_has_free_monster_zone(state, controller) -> bool:
    """Gate a Token summon onto the opponent's field (Ojama Trio)."""
    return state.first_empty_monster_zone(state.opponent_of(controller)) is not None


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
            resolve=(InflictDamage(SELF, 1000), NegatePreviousLink()),
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
            resolve=(InflictDamage(SELF, 500), NegatePreviousLink(aftermath="bounce")),
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
    "Goblin Black Ops": (CanAttackDirectly(),),
    "Raging Flame Sprite": (CanAttackDirectly(),),
    # Battle-indestructible (Arcana Force 0's no-position-change, Marshmallon's flipped
    # 1000 burn, and Spirit Reaper's destroy-when-targeted riders are not modelled).
    "Arcana Force 0 - The Fool": (BattleIndestructible(),),
    "Marshmallon": (BattleIndestructible(),),
    "Spirit Reaper": (BattleIndestructible(),),  # its battle-damage discard is in EFFECTS
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
