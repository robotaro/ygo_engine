"""The card-effect layer.

An ``Effect`` is the declarative description of one card ability; a ``Primitive``
is one of the fixed "verbs" its resolution is built from. This layer grows as we
add cards — the engine kernel never changes.

Scope:
  * Slice 1 — Ignition Spell effects (Pot of Greed, Dark Hole).
  * Slice 2 — targeting (player-chosen + automatic) and damage.
  * Slice 3 — the Chain: triggers, spell speed, Traps & Quick-Play (Mirror Force,
    Trap Hole, Magic Cylinder, Mystical Space Typhoon).
  * Slice 6 — Special Summon from the Graveyard (Monster Reborn, Call of the
    Haunted), graveyard target pools, and the Call-of-the-Haunted bond.
  * Slice 7 — Field Spells as field-wide stat layers (Sogen/Yami/Gaia Power) and
    a continuous attack restriction (The Dark Door).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from .enums import Attribute, Position, SpellTrapProperty, Zone

if TYPE_CHECKING:
    from .state import GameState

# Player references resolved relative to the effect's controller.
SELF = "self"
OPPONENT = "opponent"


@dataclass
class EffectContext:
    """Everything a primitive needs while resolving an effect."""

    state: "GameState"
    controller: int
    source_iid: int
    targets: list[int] = field(default_factory=list)
    event: dict | None = None  # the triggering event, for Trigger effects

    def side(self, who: str) -> int:
        return self.controller if who == SELF else self.state.opponent_of(self.controller)


@dataclass(frozen=True)
class EquipMod:
    """A continuous ATK/DEF modifier applied while an Equip is face-up & attached.

    Flat: ``EquipMod(atk=1000)``. Scaling: ``EquipMod(scaling="face_up_monsters",
    scale_atk=800, scale_defn=800)`` adds 800 per face-up monster the equip's
    controller has (United We Stand); "spell_trap" counts their Spell/Trap cards
    (Mage Power). Read by ``GameState.effective_attack`` — never stored on the
    monster, so it's always correct as the board changes ("layers").
    """

    atk: int = 0
    defn: int = 0
    scaling: str | None = None  # None | "face_up_monsters" | "spell_trap" | "lp_megamorph"
    scale_atk: int = 0
    scale_defn: int = 0
    # The equipped monster deals piercing battle damage to a Defense-Position monster it
    # breaks (Big Bang Shot). Read by GameState.has_piercing off the attached Equip.
    grants_piercing: bool = False


@dataclass(frozen=True)
class UnionMod:
    """Marks a Union monster and which monsters it may equip *itself* to. A Union
    can, once per turn, equip to a valid host you control (becoming an Equip Card)
    or unequip and Special Summon itself back. ``host_names`` restricts valid hosts
    to those card names (empty = any face-up monster you control); ``host_races``
    restricts by race. The ATK/DEF boost it grants while equipped is a separate
    ``EquipMod`` in the same ``continuous`` list, read through the normal Equip
    layer once the Union sits (attached) in a Spell/Trap zone."""

    host_names: frozenset[str] = frozenset()
    host_races: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SelfStatMod:
    """A continuous ATK/DEF modifier a face-up monster applies to *itself* (the
    monster's own "layer"). Used for effects like Goggle Golem ("the original ATK
    of this card becomes 2100" — a flat self-boost). Read by
    ``GameState.effective_attack/defense`` straight off the monster's own
    ``continuous`` list, and suppressed while the monster's effect is inactive
    (a Gemini that hasn't been Gemini Summoned yet).

    Optionally *scaling*:
      * ``"face_up_attr_monsters"`` adds ``scale_atk``/``scale_defn`` per OTHER face-up
        monster on the field (both sides) — narrowed to ``count_attribute`` when set
        (Ultimate Baseball Kid: +1000 ATK per other face-up FIRE monster).
      * ``"graveyard_monsters"`` adds them per monster in the controller's *own*
        Graveyard, narrowed by any of ``count_attribute`` / ``count_race`` /
        ``count_name_contains`` (Shadow Ghoul +100 per monster, Mudora +200 per Fairy,
        Beelze Frog +300 per "T.A.D.P.O.L.E."; Chaos Necromancer has base 0 ATK so its
        ATK *is* 300 × the count).
      * ``"controlled_monsters"`` adds them per face-up monster the controller controls,
        narrowed by ``count_attribute`` / ``count_race`` / ``count_name_contains``
        (Amazoness Paladin +100 per "Amazoness", Botanical Lion +300 per Plant, Hunter Owl
        +500 per WIND). The source counts itself when it matches the filter, unless
        ``count_exclude_self`` is set (Dragon Master Knight counts only OTHER Dragons).
      * ``"equips_on_self"`` adds ``scale_atk``/``scale_defn`` per Equip Card attached to
        the source monster (Maha Vailo: +500 ATK for each Equip Card equipped to it).
      * ``"named_in_graveyards"`` adds them per card in EITHER player's Graveyard whose
        exact name is in ``count_names`` (Dark Magician Girl: +300 ATK for each "Dark
        Magician" or "Magician of Black Chaos" in the GYs).
      * ``"opponent_field_and_gy_race"`` adds them per ``count_race`` monster the OPPONENT
        controls face-up PLUS each in the opponent's Graveyard (Buster Blader: +500 ATK for
        every Dragon the opponent controls or has in their GY).
      * ``"hand_size"`` adds ``scale_atk``/``scale_defn`` per card in the controller's hand
        (Muka Muka +300, Enraged Muka Muka +400; Flash Assailant uses negative scales to
        *lose* 400 per card). The source is on the field, so it never counts itself."""

    atk: int = 0
    defn: int = 0
    # None | "face_up_attr_monsters" | "graveyard_monsters" | "controlled_monsters"
    #      | "equips_on_self" | "named_in_graveyards"
    scaling: str | None = None
    scale_atk: int = 0
    scale_defn: int = 0
    count_attribute: "Attribute | None" = None
    count_race: str | None = None
    count_name_contains: str | None = None
    count_names: frozenset = frozenset()
    count_exclude_self: bool = False
    # Optional activation gates — the whole modifier contributes 0 unless ALL set gates
    # hold for the controller: control a face-up monster named like this (Boot-Up Soldier
    # → "Gadget"), hold at most N cards in hand (Cybernetic Cyclopean → 0), and/or control
    # no Spell/Trap cards (Theban Nightmare).
    active_if_control_name_contains: str | None = None
    active_if_hand_at_most: int | None = None
    active_if_empty_spell_trap: bool = False


@dataclass(frozen=True)
class HandSpecialSummon:
    """A monster's built-in ability to Special Summon *itself from the hand* during
    its controller's Main Phase, when a board condition holds (Cyber Dragon, The
    Fiend Megacyber). It is *not* a Chain activation: ``moves`` enumerates it as a
    ``SpecialSummonFromHand`` action — parallel to a Normal Summon, but it does not
    use up the turn's Normal Summon. ``condition`` is ``(state, controller) ->
    bool`` (None = always allowed); ``position`` is the battle position the monster
    arrives in (face-up Attack across the whole v6.0 pool). Carried on its own
    ``CardDef.hand_summon`` slot, not in ``effects``.

    ``cannot_normal_summon`` (the Chaos monsters, the Sacred Beasts): the card can
    *only* reach the field this way — it's barred from Normal/Tribute Summon (read
    by ``CardDef.can_normal_summon``). ``banish_costs`` is an activation cost paid by
    banishing monsters from the controller's Graveyard: each ``SummonCost`` banishes
    ``count`` GY monsters matching its filter (Black Luster Soldier - Envoy of the
    Beginning banishes 1 LIGHT *and* 1 DARK — two SummonCosts). The summon is only
    offered when every sub-cost can be paid from disjoint GY monsters."""

    condition: "Callable[[GameState, int], bool] | None" = None
    position: Position = Position.FACE_UP_ATTACK
    cannot_normal_summon: bool = False
    banish_costs: "tuple[SummonCost, ...]" = ()
    # Special Summon by Tributing this many monsters the controller already controls
    # (Blue-Eyes Toon Dragon = 2, Toon Summoned Skull = 1). The Tributes free a Monster
    # Zone, so the summon is offered whenever that many monsters are on the board.
    tribute_count: int = 0


@dataclass(frozen=True)
class SpellCounterHolder:
    """A face-up card that holds Spell Counters (up to ``max_counters``; 0 = no
    limit). When ``accumulates`` (the default), it gains 1 each time a Spell
    resolves (Royal Magical Library); set it False for a card that only ever
    receives counters from its own effect (Breaker places 1 when Normal Summoned
    and never accrues more). Optional riders read elsewhere:
    ``per_counter_atk``/``per_counter_def`` boost the monster's stats per counter
    (Mythical Beast Cerberus, Breaker), and ``wipe_after_battle`` clears them at the
    end of a Battle Phase in which the monster battled. Counters live on the instance
    (``CardInstance.counters['spell']``); this marker just declares the behaviour."""

    max_counters: int = 0
    per_counter_atk: int = 0
    per_counter_def: int = 0
    wipe_after_battle: bool = False
    accumulates: bool = True


@dataclass(frozen=True)
class Piercing:
    """A face-up monster's continuous rider: when it attacks a Defense Position
    monster and its ATK exceeds the target's DEF, the excess (ATK - DEF) is dealt
    to the defending player as battle damage (Dark Driceratops, Mad Sword Beast).
    Read by the battle step off the attacker's own ``continuous`` list; suppressed
    while the monster's effect is inactive (an un-Summoned Gemini)."""


@dataclass(frozen=True)
class CanAttackDirectly:
    """A face-up monster's rider: it may declare a direct attack even while the
    opponent controls monsters (Raging Flame Sprite, Goblin Black Ops). Read by the
    battle-phase enumeration; suppressed while the monster's effect is inactive.

    ``only_if_opponent_attributes`` (Alligator's Sword Dragon) gates the bypass on every
    face-up monster the opponent controls having an attribute in the set — empty means
    unconditional."""

    only_if_opponent_attributes: frozenset = frozenset()


@dataclass(frozen=True)
class BattleIndestructible:
    """A face-up monster's rider: it cannot be destroyed by battle — it survives a
    combat it would lose, though battle damage still applies normally (Marshmallon,
    Spirit Reaper, Arcana Force 0 - The Fool). Read by the combat step."""


@dataclass(frozen=True)
class NoHandLimit:
    """A face-up card's rider: the End-Phase hand-size limit (discard down to 6) does not
    apply (Infinite Cards). ``whose`` selects who is exempt — "both" (Infinite Cards lifts
    the limit for *both* players while it is face-up), "controller", or "opponent". Read by
    ``GameState.hand_limit_suppressed``; suppressed itself while the card's effect is
    negated (Imperial Order on Infinite Cards restores the limit)."""

    whose: str = "both"  # "both" | "controller" | "opponent"


@dataclass(frozen=True)
class DestroyAttachedEquips:
    """A face-up monster's rider: any Equip Card that would become equipped to it is
    destroyed instead (Gearfried the Iron Knight — "if either player equips an Equip Card
    to this card: destroy it"). Enforced at the equip chokepoint (EquipToTarget): the Equip
    resolves, then goes straight to the GY rather than attaching. Suppressed while the
    monster's effect is inactive/negated."""


@dataclass(frozen=True)
class SafeAttacker:
    """Rocket Warrior: during its controller's Battle Phase, this monster cannot be destroyed
    by battle and its controller takes no battle damage from battles involving it — the
    "attack with impunity" package (it is only ever in a battle during its own Battle Phase,
    i.e. when it attacks). Read by the combat step; suppressed while inactive/negated."""


@dataclass(frozen=True)
class DebuffsAttackTargetAtk:
    """Rocket Warrior: after it attacks a monster, that attack target loses ``amount`` ATK
    until the end of the turn. Applied by the engine after combat from ``battle_pair``, so it
    only fires when this monster is the ATTACKER. Suppressed while inactive/negated."""

    amount: int = 500


@dataclass(frozen=True)
class DestroysBattledDragon:
    """An Equip card's rider (Sword of Dragon's Soul): after the equipped monster battles a
    ``race`` monster (default Dragon), that monster is destroyed at the end of the Battle
    Phase. The engine reads this off the face-up Equip post-combat (from ``state.battle_pair``)
    and, when the equipped host fought a ``race`` foe that survived combat, queues the foe in
    ``state.destroy_at_battle_phase_end`` for destruction when the Battle Phase ends."""

    race: str = "Dragon"


@dataclass(frozen=True)
class LocksAttachedMonster:
    """A face-up card (a Continuous Trap attached to a monster via ``equipped_to``) that locks
    the monster it points at: ``no_attack`` bars it from declaring an attack, ``no_position``
    bars it from changing battle position (Spellbinding Circle does both). Read by
    GameState.monster_attack_locked / monster_position_locked; the engine's orphan-equip
    cleanup destroys the trap when its target leaves the field ("when that monster is
    destroyed, destroy this card")."""

    no_attack: bool = True
    no_position: bool = True


@dataclass(frozen=True)
class PayLifeForExtraNormalSummon:
    """A face-up card (Ultimate Offering, a Continuous Trap) that lets its controller pay
    ``amount`` Life Points for an ADDITIONAL Normal Summon/Set once their one free Normal
    Summon for the turn is spent. Read by GameState.extra_normal_summon_cost, which the
    Main-Phase enumeration uses to offer paid summons; suppressed while the card is face-down or
    negated (Royal Decree). The card's "or during your opponent's Battle Phase" window is a
    deferred enhancement — summons outside your own Main Phase aren't enumerated yet."""

    amount: int = 500


@dataclass(frozen=True)
class RacePositionLock:
    """A face-up floodgate (Dragon Capture Jar, a Continuous Trap) that bars every face-up
    monster of ``race`` on EITHER side from changing its battle position while this card stays
    face-up. Read by GameState.monster_position_locked; suppressed while the card is face-down
    or negated (Royal Decree). The one-shot "flip all ``race`` monsters to Defense" on
    activation is a separate ChangeAllPositions(race=...) in the card's EFFECTS."""

    race: str = "Dragon"


@dataclass(frozen=True)
class HalvesAttackersAtk:
    """A face-up card's rider: every opponent monster that declares an attack while this card
    is face-up has its ATK halved for as long as this card stays on the field (Mirror Wall).
    The catch is recorded on the attacker (CardInstance.atk_halved_by_wall) when it attacks;
    GameState._effective_stat applies the halving while a live Wall remains."""


@dataclass(frozen=True)
class MultiAttacker:
    """A face-up monster's rider: it may declare up to ``times`` attacks each Battle
    Phase (Hayabusa Knight, Mataza the Zapper, Twinheaded Beast all = 2). Read by the
    battle-phase enumeration via ``GameState.max_attacks``; suppressed while inactive."""

    times: int = 2


@dataclass(frozen=True)
class AttackLifeCost:
    """A face-up monster's rider: its controller must pay ``amount`` Life Points to
    declare an attack with it (Dark Elf pays 1000 each time it attacks). The battle-phase
    enumeration only offers its attacks while the controller can pay (LP stays above 0
    after paying), and the engine deducts the cost at attack declaration. Read off the
    monster's own ``continuous`` list via ``GameState.attack_life_cost``; suppressed
    while its effect is inactive or negated (Skill Drain) — then it attacks for free."""

    amount: int = 0


@dataclass(frozen=True)
class AttackTributeCost:
    """A face-up monster's rider: its controller must Tribute ``count`` other monster(s)
    they control to declare an attack with it (Panther Warrior = 1). The battle-phase
    enumeration only offers its attack while the controller has that many OTHER monsters
    to Tribute, and the engine pays the cost (Tributing the weakest others) at attack
    declaration. Read off the monster's own ``continuous`` list via
    ``GameState.attack_tribute_cost``; suppressed while its effect is inactive or negated
    (Skill Drain) — then it attacks for free."""

    count: int = 1


@dataclass(frozen=True)
class DamageStepBonus:
    """A face-up monster's rider: a temporary ATK/DEF swing that applies ONLY during the
    Damage Step of a qualifying battle (Cipher Soldier +2000 vs a Warrior, Etoile Cyber
    +500 on a direct attack, Steamroid +500 attacking / -500 when attacked). It never
    touches the monster's displayed/continuous stats — ``moves._resolve_attack`` folds it
    into the combat math for that one battle. Suppressed while the effect is inactive/negated.

      * ``when`` — "attacking" (this card is the attacker), "attacked" (this card is the
        monster being attacked), or "either" (it battles, on offence or defence).
      * ``vs_direct`` — only on a direct attack (no defending monster); otherwise a
        defending monster must be present, optionally narrowed by ``vs_race`` /
        ``vs_attribute`` (the OTHER monster in the battle).
      * ``half_opposing_atk`` — instead of a flat ``atk``, add half the opposing monster's
        ATK during the Damage Step (Metalmorph: the equipped attacker gains ATK equal to
        half its attack target's ATK). Only contributes with a defending monster present.

    Carried on a monster's own ``continuous`` list, OR on an Equip card's ``continuous``
    so the bonus rides onto the equipped monster (Metalmorph) — equip-sourced bonuses are
    gated by the equip being face-up and un-negated, not by the host monster's effect."""

    atk: int = 0
    defn: int = 0
    when: str = "attacking"  # "attacking" | "attacked" | "either"
    vs_direct: bool = False
    vs_race: str | None = None
    vs_attribute: "Attribute | None" = None
    half_opposing_atk: bool = False


@dataclass(frozen=True)
class AttackTargetProtection:
    """A face-up card's continuous rider: certain monsters on its controller's side
    cannot be *selected* as an attack target by the opponent (they stay on the field —
    this only removes them from the attacker's target list). Read by the battle-phase
    enumeration via ``GameState.is_protected_attack_target``; a monster source is
    suppressed while its effect is inactive.

    Which of the controller's monsters are covered:
      * ``race`` / ``name_contains`` — narrow to monsters of that race / name substring
        (both ``None`` = every monster on the controller's side). Marauding Captain
        protects Warriors; Queen's Bodyguard protects "Allure Queen" monsters.
      * ``exclude_self`` — the source monster itself stays attackable, so the opponent
        is forced to attack *it* (a decoy: Decoyroid).
      * ``exclude_name_contains`` — monsters with this name substring stay attackable
        (a named decoy radiated by another card: Marshmallon Glasses → "Marshmallon").
      * ``requires_control_name_contains`` — the rider is dormant unless the controller
        also controls a face-up monster whose name contains this (Marshmallon Glasses
        only works while "Marshmallon" is on the field).
      * ``self_only`` — the rider covers ONLY the source monster, not a race/name class
        (Command Knight / Freya / Hunter Owl shield just themselves).
      * ``requires_control_other`` / ``requires_control_other_race`` /
        ``requires_control_other_attribute`` — dormant unless the controller also controls
        a face-up monster OTHER than the source (any / of that race / of that attribute):
        Command Knight needs "another monster", Freya "another Fairy", Hunter Owl "another
        WIND monster".
    """

    race: str | None = None
    name_contains: str | None = None
    exclude_self: bool = False
    exclude_name_contains: str | None = None
    requires_control_name_contains: str | None = None
    self_only: bool = False
    requires_control_other: bool = False
    requires_control_other_race: str | None = None
    requires_control_other_attribute: "Attribute | None" = None
    # Dormant unless the controller also controls a face-up "Umi" (or a card treated as
    # Umi). The Legendary Fisherman cannot be targeted for attacks only while Umi is up.
    requires_face_up_umi: bool = False


@dataclass(frozen=True)
class NoBattleDamageWhileUmi:
    """A face-up card's continuous rider: while its controller also controls a face-up
    "Umi" (or a card treated as Umi), that controller takes no battle damage from
    attacking monsters (Tornado Wall). Read by ``GameState.takes_no_battle_damage``."""


@dataclass(frozen=True)
class BanishInsteadOfGraveyard:
    """A face-up card's continuous replacement: while it is live, any card (either
    player's) that would be sent to the Graveyard is banished instead (Banisher of the
    Light). Read by ``GameState.send_to_graveyard``, which redirects to ``banish``."""


@dataclass(frozen=True)
class BurnOnHandDiscard:
    """A face-up card's continuous rider: whenever an *opponent's* card is discarded
    from their hand to the Graveyard, inflict ``amount`` damage to that opponent for
    each card discarded (Magical Thorn). Read by ``GameState.send_to_graveyard``."""

    amount: int = 500


@dataclass(frozen=True)
class OpponentMillToAttack:
    """A face-up card's continuous rider: the controller's *opponent* must send
    ``count`` card(s) from the top of their Deck to the GY to declare an attack
    (Gravekeeper's Servant). Read by ``GameState.attack_deck_cost`` — an opponent who
    cannot pay (empty Deck) cannot declare an attack."""

    count: int = 1


@dataclass(frozen=True)
class SameNameAnthem:
    """A face-up card's continuous rider: while it is live, every monster on the field
    (either side) that shares its name with at least one *other* face-up monster gains
    ``atk``/``defn`` (Aqua Chorus). Read by ``GameState._field_delta``."""

    atk: int = 0
    defn: int = 0


@dataclass(frozen=True)
class CannotBeSpecialSummoned:
    """A static ability carried on the card: it can never be Special Summoned (Susa
    Soldier). Read off ``card.continuous`` by ``GameState.special_summon`` — checked
    against the printed card even while it sits in the hand/Deck/Graveyard."""


@dataclass(frozen=True)
class NameTreatedAs:
    """A static ability: this card's name is always also treated as ``name`` (Cyber
    Harpie Lady is treated as "Harpie Lady"). Read by ``card_matches_traits`` so every
    name check — exact ``names`` and substring ``name_contains`` — sees the alias too."""

    name: str = ""


@dataclass(frozen=True)
class NoNormalSummonWhileControllingMonster:
    """A static ability: this card cannot be Normal Summoned or Set while its controller
    already controls a monster (Cave Dragon). Read off ``card.continuous`` by the
    Normal-Summon enumeration."""


@dataclass(frozen=True)
class CannotAttackUnlessControlRace:
    """A face-up monster's continuous rider: it cannot declare an attack unless its
    controller also controls *another* monster of ``race`` (Cave Dragon needs a second
    Dragon). Read by ``GameState.attack_barred_needs_ally`` (suppressed under Skill Drain)."""

    race: str = ""


@dataclass(frozen=True)
class ReturnsToHandAtEndPhase:
    """A static ability: a face-up copy returns to its owner's hand during the End Phase
    (Susa Soldier — the turn it is Normal Summoned or flipped face-up; since it always
    bounces at the first End Phase it is face-up, a blanket bounce is exact). Read by the
    engine's ``_return_spirits`` End-Phase sweep, alongside true Spirit monsters."""


@dataclass(frozen=True)
class HalvesBattleDamageDealt:
    """A face-up monster's continuous rider: the battle damage *it* inflicts to the
    opponent is halved (Susa Soldier). Read by the attack resolver via
    ``GameState.deals_halved_battle_damage`` (suppressed under Skill Drain)."""


@dataclass(frozen=True)
class SpecialSummonLock:
    """A face-up card's continuous lock on Special Summoning, read by every Special
    Summon route via ``GameState.special_summon_locked`` (a locked summon simply does
    not happen).

      * ``whose`` — "both" (Vanity's Fiend, the Barrier Statues) locks both players;
        "opponent" (Vanity's Ruler) locks only the source controller's opponent.
      * ``except_attribute`` — monsters of this attribute may still be Special Summoned
        despite the lock (the Barrier Statues: Inferno allows FIRE, Torrent allows WATER).
    """

    whose: str = "both"  # "both" | "opponent"
    except_attribute: "Attribute | None" = None


@dataclass(frozen=True)
class ActivationLock:
    """A face-up monster's continuous lock on the OPPONENT *activating* a card class,
    read by ``GameState.cannot_activate_card``. Unlike CardEffectNegation it doesn't
    negate — it just bars activation, and only in its scope:

      * ``locks`` — "spell" or "trap".
      * ``quick_play_only`` — only Quick-Play Spells (Invader of Darkness).
      * ``during_battle_phase_only`` — only during the Battle Phase (Mirage Dragon,
        Pitch-Black Warwolf bar the opponent's Traps mid-combat).
      * ``requires_empty_hand`` — only while the SOURCE's controller has an empty hand
        (Mechanical Hound). Suppressed while the source's effect is inactive/negated.
    """

    locks: str = "spell"  # "spell" | "trap"
    quick_play_only: bool = False
    during_battle_phase_only: bool = False
    requires_empty_hand: bool = False


@dataclass(frozen=True)
class CardEffectNegation:
    """A face-up card that shuts off a whole CLASS of card effects on the field
    (Jinzo, Spell Canceller, Royal Decree, Imperial Order). Read by
    ``GameState.cannot_activate_card`` (enumeration), ``GameState.effect_negated``
    (chain resolution), and ``GameState.active_markers`` (a negated Continuous
    Spell/Trap's own riders go inert).

      * ``negates`` — which class is negated: "spell", "trap" or "monster". The
        "monster" form (Skill Drain) is read by ``GameState.monster_effects_negated``
        and suppresses a face-up monster's continuous riders (SelfStatMod, the battle
        riders, AttackTargetProtection/SpecialSummonLock on a monster) and negates its
        effects on resolution — but ONLY while it is face-up on the field (a recruiter
        firing from the GY is unaffected), and never gates activation.
      * ``prevent_activation`` — True for "… cannot be activated" cards (Jinzo,
        Spell Canceller): a Set/hand card of that class is not even offered for
        activation. False for "negate all … effects" cards (Royal Decree, Imperial
        Order, Skill Drain): the card still activates/resolves, but its effect does
        nothing.
      * ``whose`` — which side's cards are affected: "both" (all four here),
        "opponent" (only the source controller's opponent), "self".
      * ``exclude_self`` — the negator never negates its own card (Royal Decree negates
        "all *other* Trap effects"; a Continuous negator isn't shut off by itself).

    KNOWN LIMITATION: a negator negating *another* negator of the same class (Royal
    Decree vs. Imperial Order) is not modelled — the negator scan does not recurse.
    """

    negates: str = "trap"  # "spell" | "trap"
    prevent_activation: bool = False
    whose: str = "both"  # "both" | "opponent" | "self"
    exclude_self: bool = True


@dataclass(frozen=True)
class FieldMod:
    """A continuous flat ATK/DEF modifier a face-up Field/Continuous Spell radiates
    over every monster on the field that matches its filter (the "field layer").

    A monster qualifies when its race is in ``races`` (empty = any race) *and* its
    attribute is in ``attributes`` (empty = any attribute). ``side``: None = both
    players' monsters (classic Field Spells like Sogen), "self" = only the spell
    controller's monsters, "opponent" = only theirs. Read by
    ``GameState.effective_attack/defense`` — never stored on the monster.
    """

    atk: int = 0
    defn: int = 0
    races: frozenset[str] = frozenset()
    attributes: frozenset[Attribute] = frozenset()
    side: str | None = None  # None | "self" | "opponent"
    # For a MONSTER-borne anthem only: dormant unless the source monster is itself in
    # face-up Defense Position (Fairy King Truesdale). Ignored for Spell/Field sources.
    source_in_defense: bool = False
    # Dormant except during the source controller's OPPONENT's Battle Phase — Soul of
    # Purity and Light's "opponent's monsters lose 300 ATK during their Battle Phase only"
    # (pair it with side="opponent").
    only_opponent_battle_phase: bool = False


@dataclass(frozen=True)
class AttackRestriction:
    """A continuous limit on declaring attacks, radiated by a face-up card.

    ``one_per_battle_phase`` (The Dark Door): each player may declare at most one
    attack per Battle Phase. ``min_atk_cannot_attack`` (Messenger of Peace): no
    monster whose *effective* ATK is at or above this value may declare an attack
    (both players). ``max_level_can_attack`` (Gravity Bind): a monster whose Level is
    *above* this value cannot attack (both players). ``all_cannot_attack`` (Swords of
    Revealing Light): a blanket lock — no monster on the affected side may declare an
    attack at all. ``affects`` scopes the blanket/level locks: "both" sides, or only
    the source controller's "opponent" (Swords). Modelled as data so the kernel stays
    card-agnostic.
    """

    one_per_battle_phase: bool = False
    min_atk_cannot_attack: int | None = None
    max_level_can_attack: int | None = None
    all_cannot_attack: bool = False
    affects: str = "both"  # "both" | "opponent" (of the source's controller)


@dataclass(frozen=True)
class DefenseAfterAttack:
    """A face-up monster that is changed to Defense Position once its attack resolves
    (Spear Dragon, Axe Dragonute, the Goblin Attack Force family). ``lock_position``
    (Goblin Attack Force, Giant Orc, Goblin Black Ops) additionally bars its battle
    position from being changed back until its controller's next turn — the engine
    stamps a turn deadline on the monster. The "end of the Damage Step" vs "end of the
    Battle Phase" wording is immaterial for a single-attack monster, so both are modelled
    as switching right after the attack resolves."""

    lock_position: bool = False


@dataclass(frozen=True)
class StandbyUpkeep:
    """Something a face-up card does at the start of a Standby Phase (Slice 8).

    The engine's Standby hook reads these off *every* face-up card — monster,
    Continuous Spell/Trap, or Field Spell alike — so the behaviour isn't tied to
    a card type (the engine stays card-agnostic). ``whose`` selects which Standby
    Phases it fires on:

      * "controller"  — only the card controller's own Standby Phase
        (Messenger of Peace's cost, Cure Mermaid's recovery).
      * "turn_player" — every Standby Phase, always hitting the active player
        (Burning Land's 500 to whoever's turn it is).
      * "opponent"    — only the controller's *opponent's* Standby Phase, and the
        opponent is the beneficiary (Snatch Steal's 1000 LP to its victim).

    Exactly one knob is set per instance:
      * ``pay_life``  — the beneficiary must pay this to keep the card; if they
        cannot (it would leave them at 0 LP or below), the card is destroyed.
      * ``gain_life`` — the beneficiary gains this much LP.
      * ``burn_life`` — the active (turn) player loses this much LP.
    """

    pay_life: int = 0
    gain_life: int = 0
    burn_life: int = 0
    whose: str = "controller"  # "controller" | "turn_player" | "opponent"


@dataclass(frozen=True)
class StandbyTrigger:
    """A face-up card that fires a full Effect during a qualifying Standby Phase —
    the general case beyond StandbyUpkeep's fixed-LP maintenance (Bowganian's 600
    burn, Ebon Magician Curran's "×monsters they control" burn, Dancing Fairy's LP
    gain, Destiny HERO - Defender's "opponent draws 1"). The engine fires ``effect``
    on a fresh Chain as the *source controller's* effect, so its payload directions
    (``InflictDamage(OPPONENT)``, ``Draw(OPPONENT)``) read relative to the controller.

    ``whose`` mirrors StandbyUpkeep:
      * "controller" — only the source controller's own Standby Phase.
      * "opponent"   — only the controller's opponent's Standby Phase.
      * "both"       — every Standby Phase.
    ``requires_defense`` / ``requires_attack`` gate it on the source's face-up
    battle position (Dancing Fairy must be in Attack, Destiny HERO - Defender in
    Defense). ``requires_equipped`` fires only while the source is itself an Equip
    Card (Blast Sphere, after it has equipped to the attacking monster — inert while
    it is still a face-up monster). The firing is suppressed while the source's
    effects are negated (Skill Drain on a monster, Royal Decree on a Trap)."""

    effect: "Effect"
    whose: str = "controller"  # "controller" | "opponent" | "both"
    requires_defense: bool = False
    requires_attack: bool = False
    requires_equipped: bool = False


@dataclass(frozen=True)
class EndPhaseTrigger:
    """A face-up card that fires a full Effect during a qualifying End Phase — the
    End-Phase analogue of StandbyTrigger (Elemental HERO Lady Heat's "×HEROes" burn,
    Lumina's Lightsworn mill, Little-Winguard's position change, The Wicked Worm
    Beast's self-bounce, Garuda's opponent-End-Phase position change). The engine
    fires ``effect`` on a fresh Chain as the *source controller's* effect, so its
    payload directions read relative to the controller.

    ``whose``:
      * "controller" — only the source controller's own End Phase.
      * "opponent"   — only the controller's opponent's End Phase.
      * "both"       — every End Phase (each player's).
    ``requires_defense`` / ``requires_attack`` gate it on the source's face-up
    battle position. The firing is suppressed while the source's effects are negated
    (Skill Drain on a monster, Royal Decree on a Trap). Optional "you can" wording is
    treated as mandatory in the headless engine, matching StandbyTrigger."""

    effect: "Effect"
    whose: str = "controller"  # "controller" | "opponent" | "both"
    requires_defense: bool = False
    requires_attack: bool = False


@dataclass(frozen=True)
class LifeGainTrigger:
    """A face-up card that fires a full Effect each time its controller GAINS Life Points
    (Fire Princess: "Each time you gain Life Points, inflict 500 damage to your opponent").
    The engine's "when you gain Life Points" window drains every recorded gain (state.
    gain_life_points is the one sink) and fires ``effect`` once per gain event as the
    *source controller's* effect, so its payload directions read relative to the controller
    (``InflictDamage(OPPONENT)`` burns the controller's opponent). Mandatory; suppressed
    while the source's effects are negated (Skill Drain) — the ``active_markers`` scan
    handles the face-up / effects-active / negation gating."""

    effect: "Effect"


@dataclass(frozen=True)
class GraveyardStandbyReturn:
    """A card that, during its owner's Standby Phase while it sits in their Graveyard,
    may add itself back to the hand (Sinister Serpent). Read directly off the card's
    ``continuous`` list by the engine's Standby hook — it is inert on the field (no
    field-passive consumer scans for it). At most one carrier returns per Standby Phase,
    matching the "once per turn" wording, and only on the owner's own Standby Phase.
    (Sinister Serpent's downside — banish 1 copy during the opponent's next End Phase —
    is not modelled; the headless engine treats the optional return as taken.)"""


@dataclass(frozen=True)
class GraveyardStandbyGainLife:
    """A card that, while it sits in its owner's Graveyard, grants its owner ``amount`` LP
    during each of their Standby Phases (Darklord Marie). Read off the card's
    ``continuous`` list in the GY by the engine's Standby hook (one grant per copy per
    Standby Phase); inert on the field. Sibling of GraveyardStandbyReturn."""

    amount: int = 0


@dataclass(frozen=True)
class EndPhaseSummonSweep:
    """A face-up floodgate (Infinite Dismissal): during the End Phase, every monster of
    Level ``max_level`` or lower that was Normal/Flip Summoned this turn — face-up,
    summoned this turn, and not Special Summoned — is destroyed (both players'). Read by
    the engine's End-Phase hook off any face-up field card carrying it; suppressed while
    that card's effect is negated (Royal Decree on the Trap)."""

    max_level: int = 3


@dataclass(frozen=True)
class DrawTrigger:
    """A face-up card's reaction to its controller drawing (Slice 10).

    The controller gains ``gain_life`` LP each time they draw a card(s) — once per
    draw, regardless of how many cards (Solemn Wishes). Read by the engine after
    every draw; never stored on the card.
    """

    gain_life: int = 0


@dataclass(frozen=True)
class DrawOnOpponentDraw:
    """Appropriate: each time the OPPONENT draws a card(s) *outside a Draw Phase*, the
    controller immediately draws ``count`` cards. Read by the engine's draw-event loop
    (the controller's draw queues its own event, so chained Appropriates resolve in turn);
    suppressed while the card's effect is negated (Royal Decree)."""

    count: int = 2


@dataclass(frozen=True)
class TargetSpec:
    """What an effect targets, chosen by the controller at activation.

    ``where`` names a pool the engine can enumerate: "opponent_monsters",
    "any_monster", "spell_trap_field" (both players' Spell/Traps + Field Spells),
    "any_card_field" (every card on the field), "opponent_card_field" (every card the
    opponent controls), "any_graveyard_monster" (either GY), "own_graveyard_monster"
    (the controller's GY only), "opponent_graveyard_monster" (the opponent's GY only —
    Autonomous Action Unit steals a revival target).

    ``races`` / ``attributes`` optionally narrow a monster pool to those races
    (e.g. an Equip that may only attach to a Spellcaster) or attributes — empty
    means "any". ``max_atk`` / ``min_level`` / ``max_level`` bound a revival target's
    printed ATK / Level (Limit Reverse fetches a 1000-or-less-ATK monster from the GY);
    ``normal_only`` restricts it to a Normal (vanilla) monster (Birthright, Silent Doom).
    """

    count: int = 1
    where: str = "opponent_monsters"
    races: frozenset = frozenset()
    attributes: frozenset = frozenset()
    face_up: bool = False  # restrict to face-up monsters (e.g. Soul Taker)
    face_down: bool = False  # restrict to face-down monsters (Nobleman of Crossout)
    defense_position: bool = False  # restrict to Defense Position monsters (Shield Crush)
    attack_position: bool = False  # restrict to face-up Attack Position monsters (Cyber Gymnast)
    exclude_attacker: bool = False  # drop the declared attacker (Magical Arm Shield's "except")
    up_to: bool = False  # ``count`` is a maximum — choose 1..count (Penguin Soldier)
    # Restrict a Spell/Trap pool by kind: None | "spell" | "trap" | "field_spell"
    # (Hannibal Necromancer destroys only a face-up Trap).
    card_kind: str | None = None
    # Restrict to a named target — ``names`` matches the exact card name (any of:
    # Cyber Shield -> Harpie Lady / Harpie Lady Sisters), ``name_contains`` matches
    # an archetype substring (Ancient Gear Tank -> any "Ancient Gear" monster).
    names: frozenset = frozenset()
    name_contains: frozenset = frozenset()
    # Revival-target bounds (own/any/opponent GY pools): cap printed ATK, bound the
    # Level, or require a Normal (vanilla) monster. Unset = no restriction.
    max_atk: int | None = None
    min_level: int | None = None
    max_level: int | None = None
    normal_only: bool = False


def card_matches_traits(
    card,
    *,
    names=frozenset(),
    name_contains=frozenset(),
    races=frozenset(),
    attributes=frozenset(),
    max_atk=None,
    max_def=None,
    min_level=None,
    max_level=None,
) -> bool:
    """Whether a printed card satisfies the name/race/attribute/level/ATK/DEF
    constraints (empty/None = no constraint). The single source of truth for these
    trait checks, shared by ``CardFilter.matches`` and the move layer's target filter so
    the two can never drift. (Card-kind and position checks stay with each caller.)"""
    if names or name_contains:
        # A card treated as another name (Cyber Harpie Lady -> "Harpie Lady") matches under
        # either name, for both exact and substring checks.
        card_names = {card.name}
        card_names.update(m.name for m in card.continuous if isinstance(m, NameTreatedAs))
        if names and card_names.isdisjoint(names):
            return False
        if name_contains and not any(s in n for n in card_names for s in name_contains):
            return False
    if races and card.race not in races:
        return False
    if attributes and card.attribute not in attributes:
        return False
    if max_atk is not None and (card.attack or 0) > max_atk:
        return False
    if max_def is not None and (card.defense or 0) > max_def:
        return False
    if min_level is not None and (card.level or 0) < min_level:
        return False
    if max_level is not None and (card.level or 0) > max_level:
        return False
    return True


@dataclass(frozen=True)
class CardFilter:
    """A predicate over a *printed* card, for fetching from the Deck (Reinforcement
    of the Army, Terraforming, Fusion Sage). Every set criterion must hold (AND);
    an unset criterion is ignored.

    ``card_kind``: None | "monster" | "spell" | "trap" | "field_spell" |
    "normal_monster". ``names`` matches the exact card name (any of); ``name_contains``
    matches an archetype substring (any of); ``races`` / ``attributes`` narrow a
    monster; ``min_level`` / ``max_level`` bound a monster's Level; ``max_atk`` caps
    its ATK (the battle-recruiters fetch a monster with 1500 or less ATK).
    """

    names: frozenset = frozenset()
    name_contains: frozenset = frozenset()
    races: frozenset = frozenset()
    attributes: frozenset = frozenset()
    card_kind: str | None = None
    min_level: int | None = None
    max_level: int | None = None
    max_atk: int | None = None
    max_def: int | None = None

    def matches(self, card) -> bool:
        if not card_matches_traits(
            card,
            names=self.names,
            name_contains=self.name_contains,
            races=self.races,
            attributes=self.attributes,
            max_atk=self.max_atk,
            max_def=self.max_def,
            min_level=self.min_level,
            max_level=self.max_level,
        ):
            return False
        kind = self.card_kind
        if kind == "monster" and not card.is_monster:
            return False
        if kind == "spell" and not card.is_spell:
            return False
        if kind == "trap" and not card.is_trap:
            return False
        if kind == "field_spell" and not (card.is_spell and card.subtype is SpellTrapProperty.FIELD):
            return False
        if kind == "normal_monster" and not card.is_vanilla:
            return False
        return True


@dataclass(frozen=True)
class DrawAgainOnDraw:
    """A face-up card's "when you draw a [matching] card(s): draw 1 more" reaction
    (Heart of the Underdog — draw a Normal Monster in your Draw Phase; Tethys, Goddess
    of Light — draw a Fairy monster). The engine, after each of the controller's draw
    events, draws 1 extra card if any card just drawn matches ``card_filter``; that extra
    draw is itself a new event, so a run of matches chains (bounded by the deck). The
    optional reveal is treated as taken (headless). ``draw_phase_only`` limits it to the
    Draw Phase (Heart of the Underdog)."""

    card_filter: CardFilter = CardFilter()
    draw_phase_only: bool = False


@dataclass(frozen=True)
class SummonCost:
    """One sub-cost of a self-Special-Summon paid by banishing from the controller's
    Graveyard: banish ``count`` GY monsters matching ``card_filter``. A monster with
    several sub-costs (1 LIGHT *and* 1 DARK) lists one ``SummonCost`` each, and they
    are paid from disjoint cards."""

    count: int = 1
    card_filter: CardFilter = CardFilter()


@dataclass(frozen=True)
class Trigger:
    """When a reactive (Trigger-timed) effect may be activated.

    It fires in response to a game event of ``kind`` caused ``by`` the opponent
    (or self). ``subject`` names an event field to auto-target ("monster",
    "attacker"); ``min_atk`` is an optional gate (e.g. Trap Hole needs ATK >= 1000).
    """

    # The game event this reacts to. Known kinds: "summon" (Normal/Flip/Special — see
    # summon_kinds), "attack_declared", "attacked", "battle_damage_inflicted",
    # "battles", "destroys_by_battle", "damage_taken", "sent_to_gy_from_field", and the
    # destruction triggers "destroyed_by_battle" / "destroyed_by_effect" / "destroyed"
    # (the unified battle-OR-effect one) — all three drained off the field→GY queue.
    kind: str
    by: str = OPPONENT
    subject: str | None = None
    min_atk: int | None = None
    max_atk: int | None = None  # an upper ATK gate (Eatgaboon destroys a Summon with ATK <= 500)
    max_def: int | None = None  # an upper DEF gate (House of Adhesive Tape: DEF <= 500)
    # For a "summon" trigger: which Summon kinds it reacts to ("normal" | "flip" |
    # "special"). Empty = any Summon (Bottomless Trap Hole, Horn of Heaven); set it
    # to keep a card to its kinds (Trap Hole = Normal/Flip, Black Horn = Special).
    summon_kinds: frozenset = frozenset()
    # For an "attack_declared" trigger that keys off the DEFENDER's monster being
    # attacked ("when a face-up monster you control is selected as an attack target" —
    # Mirage Tube, Froggy Forcefield, Justi-Break). When ``target_self_control`` is set,
    # the event's ``target`` must be a face-up monster the *activating* player controls,
    # optionally narrowed: ``target_name_contains`` (any substring — "Frog"),
    # ``target_exclude_names`` (not one of these — "Frog the Jam"), ``target_normal_only``
    # (a Normal/vanilla monster — Justi-Break), ``target_max_level`` (Level cap).
    target_self_control: bool = False
    target_name_contains: frozenset = frozenset()
    target_exclude_names: frozenset = frozenset()
    target_normal_only: bool = False
    target_max_level: int | None = None
    # For an "attack_declared" trigger: require the declaring attacker to have been
    # Tribute Summoned (Blast Held by a Tribute).
    attacker_was_tribute_summoned: bool = False
    # For a "damage_taken" trigger: only react to BATTLE damage, not effect damage
    # (Damage Condenser is battle-only; Numinous Healer / Attack and Receive fire on any
    # LP damage). Checked against the event's ``damage_kind``.
    battle_only: bool = False
    # For a "damage_step" trigger activated by the player ABOUT TO TAKE the battle damage
    # (Nutrient Z), regardless of whose turn it is. ``to_victim`` requires the event's
    # ``victim`` to be the activating player; ``min_battle_damage`` gates on the previewed
    # ``incoming_damage`` (Nutrient Z needs 2000+).
    to_victim: bool = False
    min_battle_damage: int | None = None


# --------------------------------------------------------------------------- #
#  Dynamic values — an effect amount computed from the board at resolution time
# --------------------------------------------------------------------------- #
class ValueSource:
    """A number computed when an effect resolves, instead of a fixed constant.

    ``InflictDamage`` / ``GainLifePoints`` read either their flat ``amount`` or, if
    one is given, a ``value`` source — the "equal to its ATK" and "for each ..."
    cards. Each subclass returns one int from the ``EffectContext``.
    """

    def value(self, ctx: EffectContext) -> int:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class TargetAttack(ValueSource):
    """The (effective) ATK of a targeted monster; ``index`` picks which target (0 =
    the first/only one). For "equal to its ATK" effects whose value is the monster
    the effect points at — including Traps that auto-target the attacking monster
    (Draining Shield, Enchanted Javelin). 0 if that target has already left play."""

    index: int = 0

    def value(self, ctx: EffectContext) -> int:
        if self.index >= len(ctx.targets):
            return 0
        iid = ctx.targets[self.index]
        if iid not in ctx.state.cards:
            return 0
        return ctx.state.effective_attack(iid)


@dataclass(frozen=True)
class HalfEquippedHostAtk(ValueSource):
    """Half the (effective) ATK of the monster this Equip Card is attached to (Kiseitai,
    once it has become an Equip Card on the attacker, gains its controller that much LP each
    of the opponent's Standby Phases). 0 if the source is not currently attached or its host
    has left the field."""

    def value(self, ctx: EffectContext) -> int:
        from .enums import Zone

        src = ctx.state.cards.get(ctx.source_iid)
        if src is None or src.equipped_to is None:
            return 0
        host = ctx.state.cards.get(src.equipped_to)
        if host is None or host.zone is not Zone.MONSTER:
            return 0
        return ctx.state.effective_attack(host.iid) // 2


@dataclass(frozen=True)
class DirectBattleDamageThisTurn(ValueSource):
    """The most recent battle damage the controller inflicted by a DIRECT attack this turn
    (Sebek's Blessing gains that much LP). 0 if none yet; reset at the start of each turn."""

    def value(self, ctx: EffectContext) -> int:
        return ctx.state.direct_damage_dealt_this_turn


@dataclass(frozen=True)
class DestroyedByBattleAttack(ValueSource):
    """The original (printed) ATK of the monster this card just destroyed by battle —
    read from the ``destroyed`` iid on the triggering event (Guardian Angel Joan gains
    that much LP). The monster is in the Graveyard by now, so this is its base ATK."""

    def value(self, ctx: EffectContext) -> int:
        iid = (ctx.event or {}).get("destroyed")
        if iid is None or iid not in ctx.state.cards:
            return 0
        return ctx.state.inst(iid).card.attack or 0


def _tributed_atk(ctx: EffectContext) -> int:
    """Sum of the printed ATK of the monster(s) Tributed as this card's activation
    cost — read off the source card's recorded ``tributed_iids``. Printed (base)
    ATK, since the tributed monster is now in the Graveyard."""
    src = ctx.state.cards.get(ctx.source_iid)
    if src is None:
        return 0
    return sum(
        (ctx.state.inst(i).card.attack or 0)
        for i in src.tributed_iids
        if i in ctx.state.cards
    )


@dataclass(frozen=True)
class TributedAttack(ValueSource):
    """The (original/printed) ATK of the monster Tributed to pay this card's cost
    (Spiritual Fire Art - Kurenai: "damage equal to that monster's original ATK").
    For a multi-Tribute cost it sums them."""

    def value(self, ctx: EffectContext) -> int:
        return _tributed_atk(ctx)


@dataclass(frozen=True)
class CountTimes(ValueSource):
    """``per`` × the number of cards in a named pool — the "for each ..." burn/heal
    cards (Just Desserts, Secret Barrel, Cemetary Bomb, D.D. Dynamite, Gift of The
    Mystical Elf). Pools are resolved relative to the effect's controller. For the
    ``own_graveyard`` pool an optional ``card_filter`` narrows the count (Magical
    Explosion counts Spell Cards in your GY; Volcanic Hammerer "Volcanic" monsters)."""

    per: int = 0
    pool: str = "opponent_monsters"
    card_filter: "CardFilter | None" = None

    def value(self, ctx: EffectContext) -> int:
        return self.per * _count_pool(ctx, self.pool, self.card_filter)


def _field_card_count(state: "GameState", player: int) -> int:
    """Cards ``player`` controls on the field: their Monster + Spell/Trap zones,
    plus a Field Spell if any."""
    p = state.players[player]
    n = sum(1 for i in p.monster_zones if i is not None)
    n += sum(1 for i in p.spell_trap_zones if i is not None)
    if p.field_zone is not None:
        n += 1
    return n


def _count_pool(ctx: EffectContext, pool: str, card_filter=None) -> int:
    """Resolve a CountTimes pool name to a card count, relative to the controller."""
    s = ctx.state
    opp = s.opponent_of(ctx.controller)
    if pool == "opponent_monsters":
        return sum(1 for i in s.players[opp].monster_zones if i is not None)
    if pool == "all_monsters":
        return sum(1 for pl in (0, 1) for i in s.players[pl].monster_zones if i is not None)
    if pool == "opponent_hand":
        return len(s.players[opp].hand)
    if pool == "opponent_hand_and_field":
        return len(s.players[opp].hand) + _field_card_count(s, opp)
    if pool == "opponent_spell_trap":
        return sum(1 for i in s.players[opp].spell_trap_zones if i is not None) + (
            1 if s.players[opp].field_zone is not None else 0
        )
    if pool == "opponent_graveyard":
        return len(s.players[opp].graveyard)
    if pool == "opponent_banished":
        return len(s.players[opp].banished)
    if pool == "own_graveyard":
        gy = s.players[ctx.controller].graveyard
        if card_filter is None:
            return len(gy)
        return sum(1 for i in gy if card_filter.matches(s.inst(i).card))
    if pool == "own_monsters":
        # Face-up monsters the controller controls (Elemental HERO Lady Heat's
        # "for each face-up 'Elemental HERO' you control" burn). An optional
        # card_filter narrows by name/race; with none, every face-up own monster.
        zones = s.players[ctx.controller].monster_zones
        return sum(
            1
            for i in zones
            if i is not None
            and s.inst(i).is_face_up
            and (card_filter is None or card_filter.matches(s.inst(i).card))
        )
    return 0


# --------------------------------------------------------------------------- #
#  Primitives — the fixed verb library
# --------------------------------------------------------------------------- #
class Primitive:
    def execute(self, ctx: EffectContext) -> None:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class Draw(Primitive):
    player: str = SELF
    count: int = 1

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.draw(ctx.side(self.player), self.count)


@dataclass(frozen=True)
class DestroyAllMonsters(Primitive):
    """Destroy every monster, or only one side's. ``face_up_only`` restricts it to
    face-up monsters (Lightning Vortex); ``races`` narrows to those Types (Magnetic
    Mosquito = face-up Machines); ``level`` narrows to one printed Level (4-Starred
    Ladybug of Doom = all Level 4 the opponent controls). ``spare_face_up_attack_normal``
    spares face-up Attack-Position Normal (vanilla) monsters (Justi-Break's exception)."""

    side: str | None = None  # None = both players, else SELF / OPPONENT
    face_up_only: bool = False
    races: frozenset = frozenset()
    level: int | None = None
    spare_face_up_attack_normal: bool = False

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        victims = [
            iid
            for pl in players
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None
            and (not self.face_up_only or ctx.state.inst(iid).is_face_up)
            and (not self.races or ctx.state.inst(iid).card.race in self.races)
            and (self.level is None or ctx.state.inst(iid).card.level == self.level)
            and not (
                self.spare_face_up_attack_normal
                and ctx.state.inst(iid).position is Position.FACE_UP_ATTACK
                and ctx.state.inst(iid).card.is_vanilla
            )
            # White Hole: a protected player's monsters survive this chain's destruction.
            and ctx.state.inst(iid).controller not in ctx.state.protected_from_destruction
        ]
        for iid in victims:
            ctx.state.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class ProtectControlledFromDestruction(Primitive):
    """Mark the effect controller's monsters as immune to effect-destruction for the rest of
    this chain (White Hole, chained to the opponent's "Dark Hole", spares its controller's
    board). Cleared by the engine when the chain finishes resolving."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.protected_from_destruction.add(ctx.controller)


@dataclass(frozen=True)
class DestroyFaceUpMonstersOfDeclaredType(Primitive):
    """Tribe-Infecting Virus: declare 1 Type, then destroy every face-up monster of that
    Type on the field (both sides). With no human to declare, the controller picks the
    Type that nets the most enemy monsters destroyed — the opponent's face-up count of a
    race minus its own — so it never wipes more of its own board than the enemy's."""

    def execute(self, ctx: EffectContext) -> None:
        s, me = ctx.state, ctx.controller
        opp = s.opponent_of(me)

        def faceup(pl):
            return [
                s.inst(i)
                for i in s.players[pl].monster_zones
                if i is not None and s.inst(i).is_face_up
            ]

        own, foe = faceup(me), faceup(opp)
        races = {inst.card.race for inst in own + foe if inst.card.race}
        if not races:
            return
        best = max(
            races,
            key=lambda r: (
                sum(1 for inst in foe if inst.card.race == r)
                - sum(1 for inst in own if inst.card.race == r),
                sum(1 for inst in foe if inst.card.race == r),
            ),
        )
        for inst in own + foe:
            if inst.card.race == best:
                s.send_to_graveyard(inst.iid, by_effect=True)


@dataclass(frozen=True)
class DestroyOwnMonstersHalfAtkBurn(Primitive):
    """Time Wizard's wrong call: destroy as many monsters its controller controls as
    possible, and if any were destroyed, the controller takes damage equal to half the
    combined ATK those monsters had while face-up on the field (face-down monsters
    contribute 0). The total is read before the destruction, off each monster's
    effective ATK."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        c = ctx.controller
        victims = [i for i in s.players[c].monster_zones if i is not None]
        total = sum(s.effective_attack(i) for i in victims if s.inst(i).is_face_up)
        for iid in victims:
            s.send_to_graveyard(iid, by_effect=True)
        if victims:
            s.players[c].life_points -= total // 2


@dataclass(frozen=True)
class DestroyOwnMonsters(Primitive):
    """Destroy ``count`` monsters the controller controls (Two-Pronged Attack destroys 2 of
    your own alongside 1 of the opponent's). Deterministic — the lowest-ATK ones first, as
    interactive choice is a deferred enhancement (cf. SearchFromDeck) — and capped at however
    many they actually control."""

    count: int = 2

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        mine = [i for i in s.players[ctx.controller].monster_zones if i is not None]
        mine.sort(key=lambda i: s.effective_attack(i))
        for iid in mine[: self.count]:
            s.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class DestroyAllSpecialSummoned(Primitive):
    """Destroy every face-up Special-Summoned monster on the field, both sides (Fossil
    Dyna Pachycephalo's flip, Jowgen the Spiritualist, Special Hurricane). Reads the
    per-monster ``was_special_summoned`` flag stamped by ``state.special_summon`` /
    Tokens — Normal/Tribute/Flip Summoned and Set monsters are spared."""

    def execute(self, ctx: EffectContext) -> None:
        victims = [
            iid
            for pl in (0, 1)
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None
            and ctx.state.inst(iid).is_face_up
            and ctx.state.inst(iid).was_special_summoned
        ]
        for iid in victims:
            ctx.state.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class DestroyTargets(Primitive):
    """Destroy whatever the effect targeted."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class DestroySelf(Primitive):
    """Destroy the source card (Nuvia the Wicked self-destructs when Normal Summoned)."""

    def execute(self, ctx: EffectContext) -> None:
        if ctx.source_iid in ctx.state.cards:
            ctx.state.send_to_graveyard(ctx.source_iid, by_effect=True)


@dataclass(frozen=True)
class BanishTargets(Primitive):
    """Banish (remove from play) whatever the effect targeted — to the owner's
    banished pile instead of the Graveyard (Dark Core, Dimensional Prison). For a
    card that 'destroys then banishes' (Bottomless Trap Hole) the end state is the
    same: the card ends up banished, so we move it there directly."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.banish(iid)


@dataclass(frozen=True)
class BanishSelfAndEventMonster(Primitive):
    """D.D. Warrior Lady: after a battle, banish the opponent's monster it fought (the
    ``foe`` iid on the triggering event) and banish the source itself — each from
    wherever it now sits, since a combatant destroyed in the battle is already in the
    Graveyard while a survivor is still on the field."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        foe = (ctx.event or {}).get("foe")
        for iid in (foe, ctx.source_iid):
            if (
                iid is not None
                and iid in s.cards
                and s.inst(iid).zone in (Zone.MONSTER, Zone.GRAVEYARD)
            ):
                s.banish(iid)


@dataclass(frozen=True)
class BanishEventMonster(Primitive):
    """Banish the monster named on the triggering event's ``destroyed`` field — the
    monster this card just destroyed by battle (Divine Knight Ishzark banishes it
    instead of leaving it in the Graveyard). It's already in the GY by resolution, so
    this moves it on to the banished pile; the end state is the same."""

    def execute(self, ctx: EffectContext) -> None:
        iid = (ctx.event or {}).get("destroyed")
        if iid is not None and iid in ctx.state.cards:
            ctx.state.banish(iid)


@dataclass(frozen=True)
class BanishFaceDownThenDeckBanishIfFlip(Primitive):
    """Nobleman of Crossout: destroy the targeted face-down monster and banish it (a
    face-down monster never flips, so no Flip Effect fires); then, if that monster was
    a Flip monster, each player reveals their Main Deck and banishes every card in it
    sharing the destroyed monster's name. The brief "destroy → Graveyard → banish" step
    is modelled as a direct banish (the end state is identical — the monster is banished —
    and a face-down monster's on-destroy / sent-to-GY triggers are a minor approximation)."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        if not ctx.targets:
            return
        iid = ctx.targets[0]
        if iid not in s.cards:
            return
        inst = s.inst(iid)
        name = inst.card.name
        is_flip = inst.card.is_flip
        s.banish(iid)
        if not is_flip:
            return
        for pl in s.players:
            for did in [d for d in pl.deck if s.inst(d).card.name == name]:
                s.banish(did)


@dataclass(frozen=True)
class BanishEquippedMonster(Primitive):
    """Banish the monster this Equip Card was attached to when it left the field (Big
    Bang Shot's parting effect). Read from the equip's ``last_equipped_to`` — captured by
    ``send_to_graveyard`` before the field flags were cleared. A no-op if that monster has
    itself already left the field (e.g. the equip was orphaned because the monster died)."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        src = s.cards.get(ctx.source_iid)
        if src is None:
            return
        iid = src.last_equipped_to
        if iid is not None and iid in s.cards and s.inst(iid).zone is Zone.MONSTER:
            s.banish(iid)


@dataclass(frozen=True)
class EquipSelfToAttacker(Primitive):
    """Blast Sphere's reactive effect: when this face-down Defense monster is attacked,
    before damage calculation it leaves the monster zone and equips itself to the
    attacking monster — a monster card becoming an Equip Card, the same move a Union
    monster makes. The attack then fizzles because its target is gone (the engine
    re-checks the target after this fires). The attacker is read from the triggering
    event. A no-op if the controller has no free Spell/Trap Zone (the monster stays in
    the monster zone and battles normally)."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        attacker = (ctx.event or {}).get("attacker")
        src = s.cards.get(ctx.source_iid)
        if src is None or attacker is None:
            return
        host = s.cards.get(attacker)
        if host is None or host.zone is not Zone.MONSTER:
            return
        index = s.first_empty_spell_trap_zone(src.controller)
        if index is None:
            return  # nowhere to put the equip — the monster battles normally
        s.place_spell_trap(ctx.source_iid, src.controller, index, Position.FACE_UP_ATTACK)
        src.equipped_to = attacker


@dataclass(frozen=True)
class DestroyEquipHostThenBurn(Primitive):
    """Blast Sphere's delayed payoff (fired on its controller's opponent's next Standby
    Phase via a ``requires_equipped`` StandbyTrigger): destroy the monster this card is
    equipped to and, if it did, inflict damage equal to its ATK on the field. The damage
    hits whoever CONTROLS the equipped monster at the moment it explodes — read here at
    resolution time, not captured at equip time. This is the GBA-era behaviour and lets
    the classic combo work: hand the about-to-explode monster to the enemy first (Change
    of Heart / a give-away) and *they* take the burn. A no-op if the host has already left
    the field (Blast Sphere would then be an orphaned equip, already cleaned up).

    DELIBERATE, USER-ENDORSED DIVERGENCE: ygopro-core's official script damages a FIXED
    player (``Duel.Damage(1-tp,...)`` = Blast Sphere's controller's opponent) regardless of
    any control change. We intentionally follow the GBA ROM instead (control-follows-the-
    monster) for more interesting play — this is lore-accurate to the game this engine
    recreates, not a bug. Do NOT "fix" it to match the modern C++ ruling."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        src = s.cards.get(ctx.source_iid)
        if src is None or src.equipped_to is None:
            return
        host = s.cards.get(src.equipped_to)
        if host is None or host.zone is not Zone.MONSTER:
            return
        victim = host.controller  # whoever controls it NOW takes the damage
        atk = s.effective_attack(host.iid)
        s.send_to_graveyard(host.iid, by_effect=True)
        if atk > 0:
            s.players[victim].life_points -= atk


@dataclass(frozen=True)
class CountdownSelfDestruct(Primitive):
    """Tick a self-destruct counter on the source each time this fires; once it
    reaches ``turns``, destroy the source. Swords of Revealing Light pairs this with
    an ``EndPhaseTrigger(whose="opponent")`` so it counts the opponent's End Phases and
    expires on their 3rd one."""

    turns: int = 3
    counter: str = "countdown"

    def execute(self, ctx: EffectContext) -> None:
        inst = ctx.state.cards.get(ctx.source_iid)
        if inst is None:
            return
        n = inst.counters.get(self.counter, 0) + 1
        inst.counters[self.counter] = n
        if n >= self.turns:
            ctx.state.send_to_graveyard(ctx.source_iid, by_effect=True)


@dataclass(frozen=True)
class BounceTargetsToHand(Primitive):
    """Return the targeted cards to their owners' hands (Compulsory Evacuation
    Device, Hane-Hane, Gravekeeper's Guard)."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.return_to_hand(iid)


@dataclass(frozen=True)
class BounceTargetsToDeck(Primitive):
    """Return the targeted cards to their owners' Decks — on top by default (Back
    to Square One, Phoenix Wing Wind Blast)."""

    to_top: bool = True

    def execute(self, ctx: EffectContext) -> None:
        for iid in list(ctx.targets):
            if iid in ctx.state.cards:
                ctx.state.return_to_deck(iid, to_top=self.to_top)


@dataclass(frozen=True)
class ReturnSelfToDeck(Primitive):
    """Return this card (the effect's source) to its owner's Deck — top by default.
    Horn of the Unicorn returns itself from the Graveyard to the top of the Deck
    when it leaves the field."""

    to_top: bool = True

    def execute(self, ctx: EffectContext) -> None:
        if ctx.source_iid in ctx.state.cards:
            ctx.state.return_to_deck(ctx.source_iid, to_top=self.to_top)


@dataclass(frozen=True)
class PlantSelfInOpponentDeck(Primitive):
    """FLIP: bury this card in the opponent's Deck and shuffle it in (Parasite
    Paracide). Ownership transfers to the opponent so the card lives entirely on
    their side; it's flagged ``planted`` so its 'when drawn' effect fires only for
    this buried copy — drawing one from your own Deck normally does nothing."""

    def execute(self, ctx: EffectContext) -> None:
        if ctx.source_iid in ctx.state.cards:
            opp = ctx.state.opponent_of(ctx.controller)
            ctx.state.send_to_player_deck(ctx.source_iid, opp, shuffle=True, planted=True)


@dataclass(frozen=True)
class ShuffleHandIntoDeckThenDraw(Primitive):
    """Magical Mallet: 'shuffle any number of cards from your hand into the Deck, then
    draw that same number.' With no human to pick the number, the controller shuffles its
    whole current hand back and redraws the same count — a full hand refresh. The
    activated Magical Mallet is already out of the hand, so it isn't among the shuffled."""

    def execute(self, ctx: EffectContext) -> None:
        s, me = ctx.state, ctx.controller
        hand = list(s.players[me].hand)
        n = len(hand)
        if n == 0:
            return
        for iid in hand:
            s.return_to_deck(iid, to_top=False)  # shuffle it back in
        s.draw(me, min(n, len(s.players[me].deck)))


@dataclass(frozen=True)
class LookAtTopReorderBestFirst(Primitive):
    """Look at the top ``count`` cards of the controller's Deck and place them back in any
    order (Big Eye). With no human to choose, the engine's beneficial default surfaces the
    highest-ATK monster among them to the top so it's drawn next. A no-op if the Deck is
    empty or none of the peeked cards is a monster (the order is already 'as good')."""

    count: int = 5

    def execute(self, ctx: EffectContext) -> None:
        deck = ctx.state.players[ctx.controller].deck  # top of deck == end of the list
        if not deck:
            return
        n = min(self.count, len(deck))
        window = deck[len(deck) - n:]
        monsters = [i for i in window if ctx.state.inst(i).card.is_monster]
        if not monsters:
            return
        best = max(monsters, key=lambda i: ctx.state.inst(i).card.attack or 0)
        deck.remove(best)
        deck.append(best)  # move to the top — the controller's next draw


@dataclass(frozen=True)
class ReturnAllSpellTrapsToHand(Primitive):
    """Giant Trunade: return every Spell/Trap on the field (both players', including
    Field Spells and the activating card itself) to its owner's hand."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        victims = s.field_cards(0, monsters=False) + s.field_cards(1, monsters=False)
        for iid in victims:
            s.return_to_hand(iid)


@dataclass(frozen=True)
class ReturnAllSetCardsToHand(Primitive):
    """Byser Shock: return every face-down (Set) card on the field — Set monsters
    and Set Spells/Traps (and a Set Field Spell), both players' — to its owner's
    hand."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        victims = s.field_cards(0, face_down_only=True) + s.field_cards(1, face_down_only=True)
        for iid in victims:
            s.return_to_hand(iid)


@dataclass(frozen=True)
class PlaceCountersOnSelf(Primitive):
    """Place counters on the effect's own source card (Breaker placing a Spell
    Counter on itself when Normal Summoned). Capped at the source's
    ``SpellCounterHolder.max_counters`` when it declares one (0 = no cap)."""

    count: int = 1
    counter_type: str = "spell"

    def execute(self, ctx: EffectContext) -> None:
        inst = ctx.state.cards.get(ctx.source_iid)
        if inst is None:
            return
        holder = next(
            (m for m in inst.card.continuous if isinstance(m, SpellCounterHolder)), None
        )
        new = inst.counters.get(self.counter_type, 0) + self.count
        if holder is not None and holder.max_counters:
            new = min(new, holder.max_counters)
        inst.counters[self.counter_type] = new


@dataclass(frozen=True)
class DestroyAllOtherCards(Primitive):
    """Destroy every card on the field except the effect's own source — monsters,
    Spells/Traps and Field Spells, both players' (Levia-Dragon - Daedalus)."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        victims = s.field_cards(0) + s.field_cards(1)
        for iid in victims:
            if iid != ctx.source_iid and iid in s.cards:
                s.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class DestroyAllFieldSpells(Primitive):
    """Burning Land: destroy every Field Spell on the field (both players')."""

    def execute(self, ctx: EffectContext) -> None:
        for player in ctx.state.players:
            fz = player.field_zone
            if fz is not None:
                ctx.state.send_to_graveyard(fz, by_effect=True)


@dataclass(frozen=True)
class DestroyAllSpellTraps(Primitive):
    """Heavy Storm (``side=None``) / Harpie's Feather Duster (``side=OPPONENT``):
    destroy every Spell/Trap on the field — the Spell & Trap zones plus the Field
    Spell zone — for both players or only one side."""

    side: str | None = None  # None = both, else SELF / OPPONENT

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        victims: list[int] = []
        for pl in players:
            victims += ctx.state.field_cards(pl, monsters=False)
        for iid in victims:
            ctx.state.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class DestroyLowestAtkOpponentMonster(Primitive):
    """Fissure: destroy the opponent's face-up monster with the lowest ATK."""

    def execute(self, ctx: EffectContext) -> None:
        opp = ctx.state.opponent_of(ctx.controller)
        faceup = [
            iid
            for iid in ctx.state.players[opp].monster_zones
            if iid is not None and ctx.state.inst(iid).is_face_up
        ]
        if not faceup:
            return
        victim = min(faceup, key=lambda i: ctx.state.inst(i).card.attack or 0)
        ctx.state.send_to_graveyard(victim, by_effect=True)


@dataclass(frozen=True)
class ModifyStatsTemporary(Primitive):
    """Add a temporary ATK/DEF change to each targeted monster until the end of this
    turn (combat tricks like Rush Recklessly). The deltas accumulate on the monster
    and the engine clears them in the End Phase."""

    atk: int = 0
    defn: int = 0

    def execute(self, ctx: EffectContext) -> None:
        for iid in ctx.targets:
            inst = ctx.state.cards.get(iid)
            if inst is not None and inst.zone is Zone.MONSTER:
                inst.temp_atk += self.atk
                inst.temp_def += self.defn


@dataclass(frozen=True)
class ScaleSelfAtkTemporary(Primitive):
    """Temporarily scale the effect source's own ATK by ``num``/``den`` until the End
    Phase (Goddess of Whim: double on a winning coin toss with 2/1, halve on a losing one
    with 1/2). Applied as a ``temp_atk`` delta off the source's *current* effective ATK —
    the same convention Limiter Removal uses for doubling — and cleared in the End Phase
    like every other temporary modifier."""

    num: int = 1
    den: int = 1

    def execute(self, ctx: EffectContext) -> None:
        inst = ctx.state.cards.get(ctx.source_iid)
        if inst is not None and inst.zone is Zone.MONSTER and inst.is_face_up:
            cur = ctx.state.effective_attack(ctx.source_iid)
            inst.temp_atk += (cur * self.num) // self.den - cur


@dataclass(frozen=True)
class ModifyAllStatsTemporary(Primitive):
    """Add a temporary ATK/DEF change to every face-up monster on a ``side`` until the
    End Phase (Amazoness Archers drops all the opponent's monsters by 500 ATK). ``side``:
    None = both, else SELF / OPPONENT. Deltas accumulate and clear like ModifyStatsTemporary."""

    side: str | None = None
    atk: int = 0
    defn: int = 0

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        for pl in players:
            for iid in ctx.state.players[pl].monster_zones:
                if iid is None:
                    continue
                inst = ctx.state.inst(iid)
                if inst.is_face_up:
                    inst.temp_atk += self.atk
                    inst.temp_def += self.defn


@dataclass(frozen=True)
class RollDieModifyAllStats(Primitive):
    """Roll a six-sided die and apply ``result × per_pip`` ATK/DEF to every face-up monster
    on a ``side`` until the End Phase — Skull Dice (the opponent's monsters lose 100 × roll)
    and Graceful Dice (your monsters gain 100 × roll). Delegates the swing to
    ModifyAllStatsTemporary, so it rides the same temp-stat layer (cleared in the End Phase)."""

    side: str | None = None  # None = both, else SELF / OPPONENT
    per_pip_atk: int = 0
    per_pip_def: int = 0

    def execute(self, ctx: EffectContext) -> None:
        roll = ctx.state.rng.randint(1, 6)
        ModifyAllStatsTemporary(
            side=self.side, atk=roll * self.per_pip_atk, defn=roll * self.per_pip_def
        ).execute(ctx)


@dataclass(frozen=True)
class ModifySelfPermanentStats(Primitive):
    """Permanently change the effect source's own ATK/DEF for as long as it stays on the
    field (Slate Warrior's FLIP "+500", Zombyra's "loses 200 each time it destroys")."""

    atk: int = 0
    defn: int = 0

    def execute(self, ctx: EffectContext) -> None:
        inst = ctx.state.cards.get(ctx.source_iid)
        if inst is not None and inst.zone is Zone.MONSTER:
            inst.perm_atk += self.atk
            inst.perm_def += self.defn


@dataclass(frozen=True)
class DebuffBattleDestroyer(Primitive):
    """Permanently change the ATK/DEF of the monster that just destroyed the source by
    battle (Slate Warrior: "the monster that destroyed it loses 500 ATK and DEF"). Reads
    the engine's transient ``battle_destroyed_by`` record — still populated when this
    monster's "destroyed by battle" GY trigger resolves, just before it is drained."""

    atk: int = 0
    defn: int = 0

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        destroyer_iid = next(
            (dr for dr, dd in s.battle_destroyed_by if dd == ctx.source_iid and dr is not None),
            None,
        )
        inst = s.cards.get(destroyer_iid) if destroyer_iid is not None else None
        if inst is not None and inst.zone is Zone.MONSTER:
            inst.perm_atk += self.atk
            inst.perm_def += self.defn


@dataclass(frozen=True)
class DestroyHighestDefOpponentMonster(Primitive):
    """Smashing Ground: destroy the opponent's face-up monster with the highest DEF."""

    def execute(self, ctx: EffectContext) -> None:
        opp = ctx.state.opponent_of(ctx.controller)
        faceup = [
            iid
            for iid in ctx.state.players[opp].monster_zones
            if iid is not None and ctx.state.inst(iid).is_face_up
        ]
        if faceup:
            ctx.state.send_to_graveyard(max(faceup, key=ctx.state.effective_defense), by_effect=True)


@dataclass(frozen=True)
class DestroyHighestAtkMonster(Primitive):
    """Hammer Shot: destroy the face-up Attack-Position monster with the highest ATK.
    ``side`` restricts the pool: None = either side (Hammer Shot), OPPONENT = only the
    controller's opponent (Widespread Ruin destroys the attacker's highest)."""

    side: str | None = None

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        cands = [
            iid
            for pl in players
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None and ctx.state.inst(iid).position is Position.FACE_UP_ATTACK
        ]
        if cands:
            ctx.state.send_to_graveyard(max(cands, key=ctx.state.effective_attack), by_effect=True)


@dataclass(frozen=True)
class DestroyFaceUpMonstersWithDefAtMost(Primitive):
    """Burst Breath: destroy every face-up monster on the field whose (effective)
    DEF is at or below ``threshold`` — a dynamic value (the ATK of the monster
    Tributed as the cost). With no threshold source it destroys nothing."""

    threshold: ValueSource | None = None

    def execute(self, ctx: EffectContext) -> None:
        limit = self.threshold.value(ctx) if self.threshold is not None else -1
        victims = [
            iid
            for pl in (0, 1)
            for iid in ctx.state.players[pl].monster_zones
            if iid is not None
            and ctx.state.inst(iid).is_face_up
            and ctx.state.effective_defense(iid) <= limit
        ]
        for iid in victims:
            ctx.state.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class SwitchTargetsToAttack(Primitive):
    """Stop Defense: flip the target face-up into Attack Position."""

    def execute(self, ctx: EffectContext) -> None:
        for iid in ctx.targets:
            ctx.state.inst(iid).position = Position.FACE_UP_ATTACK


_POSITIONS = {
    "attack": Position.FACE_UP_ATTACK,
    "defense": Position.FACE_UP_DEFENSE,
    "face_down": Position.FACE_DOWN_DEFENSE,
}


def _set_position(inst, to: str) -> None:
    """Move a monster to a battle position. ``to`` is "attack"/"defense"/"face_down"
    (the latter, Book of Moon, turns it face-down so its effects switch off and its Flip
    Effect can re-trigger) or "toggle" (rotate a face-up monster ATK<->DEF)."""
    if to == "toggle":
        inst.position = (
            Position.FACE_UP_DEFENSE
            if inst.position is Position.FACE_UP_ATTACK
            else Position.FACE_UP_ATTACK
        )
    else:
        inst.position = _POSITIONS[to]


@dataclass(frozen=True)
class ChangeTargetPosition(Primitive):
    """Change the targeted monster(s) to ``to`` ("attack"/"defense"/"face_down") — Block
    Attack (face-up Defense), Book of Moon / Ready for Intercepting (face-down Defense).
    Only acts on monsters already face-up (it never flips a face-down monster face-up, so
    no Flip Effect fires here)."""

    to: str = "defense"

    def execute(self, ctx: EffectContext) -> None:
        for iid in ctx.targets:
            inst = ctx.state.cards.get(iid)
            if inst is not None and inst.is_face_up:
                _set_position(inst, self.to)


@dataclass(frozen=True)
class ChangeAllPositions(Primitive):
    """Change every face-up monster (optionally one ``side`` / level band) to ``to``:
    "defense" (Earthquake, No Entry!!), "attack" (Level Limit - Area A) or "toggle"
    (Zero Gravity, Windstorm of Etaqua — rotate each ATK<->DEF)."""

    side: str | None = None  # None = both, else SELF / OPPONENT
    to: str = "defense"
    min_level: int | None = None
    max_level: int | None = None
    race: str | None = None  # restrict to a single race (Dragon Capture Jar -> Dragon)

    def execute(self, ctx: EffectContext) -> None:
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        for pl in players:
            for iid in list(ctx.state.players[pl].monster_zones):
                if iid is None:
                    continue
                inst = ctx.state.inst(iid)
                if not inst.is_face_up:
                    continue
                if self.race is not None and inst.card.race != self.race:
                    continue
                lvl = inst.card.level or 0
                if self.min_level is not None and lvl < self.min_level:
                    continue
                if self.max_level is not None and lvl > self.max_level:
                    continue
                _set_position(inst, self.to)


@dataclass(frozen=True)
class InflictDamage(Primitive):
    """Reduce a player's Life Points (burn). The amount is the flat ``amount``, or
    — when given — a dynamic ``value`` computed at resolution time."""

    player: str = OPPONENT
    amount: int = 0
    value: ValueSource | None = None
    # True = this is an LP COST (Toon World, pay-to-negate), NOT "damage" — so it must not
    # open a "when you take damage" window (Numinous Healer / Attack and Receive).
    is_cost: bool = False

    def execute(self, ctx: EffectContext) -> None:
        amount = self.value.value(ctx) if self.value is not None else self.amount
        victim = ctx.side(self.player)
        ctx.state.players[victim].life_points -= amount
        if not self.is_cost and amount > 0:
            # Record effect damage so the engine can open a post-chain "when you take
            # damage" window for the victim. Battle damage uses a separate record.
            ctx.state.effect_damage_pending.append((victim, amount))


@dataclass(frozen=True)
class GainLifePoints(Primitive):
    """Increase a player's Life Points (the healing cards). The amount is the flat
    ``amount``, or — when given — a dynamic ``value`` computed at resolution time."""

    player: str = SELF
    amount: int = 0
    value: ValueSource | None = None

    def execute(self, ctx: EffectContext) -> None:
        amount = self.value.value(ctx) if self.value is not None else self.amount
        ctx.state.gain_life_points(ctx.side(self.player), amount)


@dataclass(frozen=True)
class LoseHalfLifePoints(Primitive):
    """A player loses half their current Life Points, rounded down (Jirai Gumo's
    failed coin toss)."""

    player: str = SELF

    def execute(self, ctx: EffectContext) -> None:
        p = ctx.state.players[ctx.side(self.player)]
        p.life_points -= p.life_points // 2


@dataclass(frozen=True)
class PreventBattleDamageThisBattle(Primitive):
    """Make the effect's controller take no battle damage from the current battle (Kuriboh's
    discard). Adds them to ``GameState.battle_damage_prevented``, which the attack resolution
    reads at every battle-damage site and the engine clears at the next attack declaration."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.battle_damage_prevented.add(ctx.controller)


@dataclass(frozen=True)
class PreventBattleDamageThisTurn(Primitive):
    """Make the effect's controller take no battle damage for the rest of this turn (Winged
    Kuriboh, on being destroyed). Stamps ``no_battle_damage_until_turn`` with the current
    turn so it lapses automatically when the turn advances."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.players[ctx.controller].no_battle_damage_until_turn = ctx.state.turn_count


@dataclass(frozen=True)
class PreventBattleDestructionThisTurn(Primitive):
    """Make the effect controller's monsters indestructible by battle for the rest of this turn
    (Waboku). Stamps ``no_battle_destruction_until_turn`` with the current turn so it lapses
    automatically when the turn advances."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.players[ctx.controller].no_battle_destruction_until_turn = ctx.state.turn_count


@dataclass(frozen=True)
class ReverseStatChangesThisTurn(Primitive):
    """Reverse Trap: until the End Phase, every ATK/DEF increase or decrease on the field flips
    sign (additions subtract, subtractions add). Stamps ``state.reverse_trap_until_turn`` with
    the current turn so it lapses when the turn advances; multiplications (Mirror Wall's
    halving) are unaffected because _effective_stat applies them after the reversal."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.reverse_trap_until_turn = ctx.state.turn_count


@dataclass(frozen=True)
class CoinFlip(Primitive):
    """Toss ``count`` coins (each 50/50 via the seeded RNG) and run the ``win`` branch's
    primitives if at least ``win_threshold`` come up heads, else the ``lose`` branch.
    A single "toss a coin and call it" is count=1/threshold=1 (calling is 50/50 with no
    information, so "call it right" is just a heads); "toss 3 times, 2+ heads" is
    count=3/threshold=2 (Barrel/Blowback Dragon). Sub-primitives share this effect's
    context (so they see the same targets — e.g. Barrel Dragon's targeted monster)."""

    win: tuple = ()
    lose: tuple = ()
    count: int = 1
    win_threshold: int = 1

    def execute(self, ctx: EffectContext) -> None:
        heads = sum(1 for _ in range(self.count) if ctx.state.rng.random() < 0.5)
        for primitive in self.win if heads >= self.win_threshold else self.lose:
            primitive.execute(ctx)


# --- Slice 3: reactive primitives (read the triggering event) ---
@dataclass(frozen=True)
class NegateAttack(Primitive):
    """Stop the current attack from dealing damage / continuing."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.attack_negated = True


@dataclass(frozen=True)
class EndBattlePhase(Primitive):
    """End the current Battle Phase immediately (The Unhappy Maiden, when sent to the GY
    by battle). Sets ``state.battle_phase_ended``, which the engine's Battle-Phase loop
    reads to stop offering further attacks this turn."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.battle_phase_ended = True


@dataclass(frozen=True)
class SetEventAttackerAtkZero(Primitive):
    """Fairy Box: the attacking monster's ATK becomes 0 for the battle — modelled by a
    temporary delta that cancels its current effective ATK. Reads the attacker from the
    triggering event; the combat step then reads the zeroed ATK at damage calculation.
    (The temp delta wears off at the End Phase rather than the Battle Phase's end — a
    harmless over-extension for a monster that has just been neutered in combat.)"""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        attacker = (ctx.event or {}).get("attacker")
        inst = s.cards.get(attacker) if attacker is not None else None
        if inst is not None and inst.zone is Zone.MONSTER:
            inst.temp_atk -= s.effective_attack(attacker)


@dataclass(frozen=True)
class ReturnEventAttackerToHand(Primitive):
    """Wall of Illusion: return the attacking monster (read from the triggering event) to
    its owner's hand. Fired from the attacked monster's own trigger, so the attacker comes
    from the event rather than a chosen target."""

    def execute(self, ctx: EffectContext) -> None:
        attacker = (ctx.event or {}).get("attacker")
        if attacker is not None and attacker in ctx.state.cards:
            if ctx.state.cards[attacker].zone is Zone.MONSTER:
                ctx.state.return_to_hand(attacker)


@dataclass(frozen=True)
class RedirectAttackToTarget(Primitive):
    """Redirect the current attack to this effect's first target — a monster the
    defender controls (Call of the Earthbound: you choose the new target; Jam Defender:
    your Revival Jam; Magical Arm Shield: the monster you just stole). Read by
    engine._declare_attack after the response window."""

    def execute(self, ctx: EffectContext) -> None:
        if ctx.targets:
            ctx.state.attack_redirect = ctx.targets[0]


@dataclass(frozen=True)
class ReflectBattleDamage(Primitive):
    """Dimension Wall: the Battle Damage the controller would take from this battle is
    dealt to the attacking player instead. Read by moves._resolve_attack."""

    def execute(self, ctx: EffectContext) -> None:
        ctx.state.reflect_battle_damage = True


@dataclass(frozen=True)
class ApplyActionLock(Primitive):
    """Set a turn-scoped lock barring a player from an action class for a duration:
    ``kind`` ∈ "special_summon"/"spell"/"trap"/"set"; ``who`` = "opponent" (default) or
    "self"; ``extra_turns`` = 0 for the rest of this turn (Guard Dog, Whirlwind Weasel,
    Searchlightman), 1 to also cover the next turn (Sonic Jammer). Read by
    state.action_locked through the SS / activation / Set gates."""

    kind: str = "spell"
    who: str = OPPONENT
    extra_turns: int = 0

    def execute(self, ctx: EffectContext) -> None:
        player = ctx.side(self.who)
        ctx.state.action_locks[f"{self.kind}:{player}"] = ctx.state.turn_count + self.extra_turns


@dataclass(frozen=True)
class ForceAttackTarget(Primitive):
    """Staunch Defender: for the rest of this turn the opponent may only declare attacks
    against this effect's first target (a face-up monster the controller picks). Sets
    state.forced_attack_target, read by moves._battle_phase_actions; cleared at the start
    of the next turn. The lock lifts on its own if that monster later leaves the field."""

    def execute(self, ctx: EffectContext) -> None:
        if ctx.targets:
            ctx.state.forced_attack_target = ctx.targets[0]


@dataclass(frozen=True)
class NegatePreviousLink(Primitive):
    """Counter-Trap negation (Magic Jammer, Dark Bribe, Divine Wrath, Goblin Out of
    the Frying Pan): negate the activation of the card this was chained to — the
    Chain link directly below this one — so that link's effect never resolves.

    ``aftermath`` then disposes of that card: "destroy" sends it to the Graveyard
    ("and if you do, destroy it"), "bounce" returns it to the owner's hand, "none"
    leaves it where it is. Works for a Spell/Trap *or* a monster (Divine Wrath
    negates a monster effect). Reads ``state.chain`` to find its own link, so it
    only works inside a resolving Chain."""

    aftermath: str = "destroy"  # "destroy" | "bounce" | "none"

    def execute(self, ctx: EffectContext) -> None:
        chain = ctx.state.chain
        idx = next(
            (i for i, link in enumerate(chain) if link.source_iid == ctx.source_iid),
            None,
        )
        if idx is None or idx == 0:
            return  # nothing below to negate
        target = chain[idx - 1]
        target.negated = True
        inst = ctx.state.cards.get(target.source_iid)
        if inst is None or inst.zone not in (Zone.MONSTER, Zone.SPELL_TRAP, Zone.FIELD):
            return  # already gone, or not on the field
        if self.aftermath == "destroy":
            ctx.state.send_to_graveyard(target.source_iid, by_effect=True)
        elif self.aftermath == "bounce":
            ctx.state.return_to_hand(target.source_iid)


@dataclass(frozen=True)
class DestroyAttackingAttackPositionMonsters(Primitive):
    """Mirror Force: destroy all the attacking player's Attack-Position monsters."""

    def execute(self, ctx: EffectContext) -> None:
        attacker_player = (ctx.event or {}).get("player", ctx.state.opponent_of(ctx.controller))
        victims = [
            iid
            for iid in ctx.state.players[attacker_player].monster_zones
            if iid is not None and ctx.state.inst(iid).position is Position.FACE_UP_ATTACK
        ]
        for iid in victims:
            ctx.state.send_to_graveyard(iid, by_effect=True)


@dataclass(frozen=True)
class BanishAttackingDefensePositionMonsters(Primitive):
    """Dark Mirror Force: banish all the attacking player's Defense-Position monsters
    (both face-up and face-down) — removed from play, not destroyed."""

    def execute(self, ctx: EffectContext) -> None:
        attacker_player = (ctx.event or {}).get("player", ctx.state.opponent_of(ctx.controller))
        victims = [
            iid
            for iid in ctx.state.players[attacker_player].monster_zones
            if iid is not None
            and ctx.state.inst(iid).position
            in (Position.FACE_UP_DEFENSE, Position.FACE_DOWN_DEFENSE)
        ]
        for iid in victims:
            ctx.state.banish(iid)


@dataclass(frozen=True)
class DamageEqualToAttackerAtk(Primitive):
    """Magic Cylinder: inflict the attacking monster's ATK to the attacking player."""

    def execute(self, ctx: EffectContext) -> None:
        event = ctx.event or {}
        attacker = event.get("attacker")
        attacker_player = event.get("player", ctx.state.opponent_of(ctx.controller))
        if attacker is None or attacker not in ctx.state.cards:
            return
        dmg = ctx.state.inst(attacker).card.attack or 0
        ctx.state.players[attacker_player].life_points -= dmg


@dataclass(frozen=True)
class EquipToTarget(Primitive):
    """Attach this Equip card to the targeted monster (it stays on the field)."""

    def execute(self, ctx: EffectContext) -> None:
        equip = ctx.state.inst(ctx.source_iid)
        target = ctx.targets[0] if ctx.targets else None
        from .enums import Zone

        if target is not None and target in ctx.state.cards and ctx.state.inst(target).zone is Zone.MONSTER:
            if ctx.state.destroys_attached_equips(target):
                ctx.state.send_to_graveyard(ctx.source_iid)  # Gearfried: the Equip is destroyed
            else:
                equip.equipped_to = target
        else:
            ctx.state.send_to_graveyard(ctx.source_iid)  # nothing to equip -> to the GY


@dataclass(frozen=True)
class AttachSelfToTarget(Primitive):
    """Attach the effect SOURCE (a Continuous Trap like Spellbinding Circle) to the targeted
    monster by setting its ``equipped_to`` — so its LocksAttachedMonster rider can find its
    victim and the engine's orphan cleanup destroys it when the monster leaves. Unlike
    EquipToTarget this skips the Gearfried 'destroys Equip Cards' check (the source is a Trap,
    not an Equip Card)."""

    def execute(self, ctx: EffectContext) -> None:
        from .enums import Zone

        target = ctx.targets[0] if ctx.targets else None
        if target is not None and target in ctx.state.cards and ctx.state.inst(target).zone is Zone.MONSTER:
            ctx.state.inst(ctx.source_iid).equipped_to = target


# --- Slice 4: monster-effect primitives ---
@dataclass(frozen=True)
class SearchMonsterToHand(Primitive):
    """Sangan (auto): move the best Deck monster with ATK <= max_atk to hand, then shuffle."""

    max_atk: int = 1500

    def execute(self, ctx: EffectContext) -> None:
        player = ctx.state.players[ctx.controller]
        eligible = [
            iid
            for iid in player.deck
            if ctx.state.inst(iid).card.is_monster
            and (ctx.state.inst(iid).card.attack or 0) <= self.max_atk
        ]
        if eligible:
            best = max(eligible, key=lambda i: ctx.state.inst(i).card.attack or 0)
            player.deck.remove(best)
            player.hand.append(best)
            ctx.state.inst(best).zone = Zone.HAND
        ctx.state.rng.shuffle(player.deck)


@dataclass(frozen=True)
class SearchFromDeck(Primitive):
    """Add 1 card matching ``filter`` from the controller's Deck to their hand, then
    shuffle (Reinforcement of the Army, Terraforming, Fusion Sage). The pick is
    deterministic — the highest-ATK match (so a monster fetch grabs the strongest
    eligible body; non-monsters tie at 0 and the first in Deck order is taken),
    mirroring ``SearchMonsterToHand`` since primitives have no agent to ask.
    Activation is gated by a condition so there is always a match when it resolves;
    with none it does nothing."""

    card_filter: CardFilter = CardFilter()

    def execute(self, ctx: EffectContext) -> None:
        player = ctx.state.players[ctx.controller]
        eligible = [i for i in player.deck if self.card_filter.matches(ctx.state.inst(i).card)]
        if eligible:
            pick = max(eligible, key=lambda i: ctx.state.inst(i).card.attack or 0)
            player.deck.remove(pick)
            player.hand.append(pick)
            ctx.state.inst(pick).zone = Zone.HAND
        ctx.state.rng.shuffle(player.deck)


@dataclass(frozen=True)
class SpecialSummonFromDeck(Primitive):
    """Special Summon 1 monster matching ``card_filter`` from the controller's Deck to an
    empty Monster Zone (Mystic Tomato & the battle-recruiters: "destroyed by battle
    -> Special Summon 1 [attribute/type] monster with 1500 or less ATK from your
    Deck"). The pick is deterministic — the highest-ATK eligible match (the best
    on-curve body under the recruiter's ATK cap) — since primitives have no agent to
    ask; interactive choice is a deferred enhancement, as with SearchFromDeck. The
    Deck is shuffled afterwards. No empty zone or no match -> nothing happens."""

    card_filter: CardFilter = CardFilter()
    position: Position = Position.FACE_UP_ATTACK
    count: int = 1  # up to this many matches (Nimble Momonga: "any number" of copies)

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        controller = ctx.controller
        deck = s.players[controller].deck
        for _ in range(self.count):
            # Pick among monsters the lock would actually let through (so a Barrier Statue
            # doesn't make us "pick" an un-summonable body while a legal one exists).
            eligible = [
                i
                for i in deck
                if s.inst(i).card.is_monster
                and self.card_filter.matches(s.inst(i).card)
                and not s.special_summon_locked(controller, s.inst(i).card)
            ]
            if not eligible:
                break
            pick = max(eligible, key=lambda i: s.inst(i).card.attack or 0)
            if not s.special_summon(pick, controller, self.position):
                break  # no free Monster Zone left
        s.rng.shuffle(deck)


@dataclass(frozen=True)
class SpecialSummonFromDeckAtkAtMostBattleDamage(Primitive):
    """Damage Condenser: Special Summon 1 monster from the controller's Deck whose ATK is
    at most the battle damage they just took (read off the triggering event's ``amount``),
    in face-up Attack Position. Deterministic highest-ATK eligible pick (like
    SpecialSummonFromDeck), respecting Special-Summon locks; no eligible monster, no free
    zone, or no event amount -> nothing happens. The Deck is shuffled afterwards."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        cap = (ctx.event or {}).get("amount")
        if cap is None:
            return
        controller = ctx.controller
        deck = s.players[controller].deck
        eligible = [
            i
            for i in deck
            if s.inst(i).card.is_monster
            and (s.inst(i).card.attack or 0) <= cap
            and not s.special_summon_locked(controller, s.inst(i).card)
        ]
        if eligible:
            pick = max(eligible, key=lambda i: s.inst(i).card.attack or 0)
            s.special_summon(pick, controller, Position.FACE_UP_ATTACK)
        s.rng.shuffle(deck)


@dataclass(frozen=True)
class SpecialSummonFromExtraDeck(Primitive):
    """Special Summon 1 monster from the controller's Extra Deck (Cyber-Stein → a Fusion
    Monster in Attack Position, after paying its 5000 LP cost). ``fusion_only`` limits the
    pick to Fusion Monsters. Deterministic — the highest-ATK eligible monster — since
    primitives have no agent to ask. No eligible monster or no free Monster Zone -> nothing
    happens (the LP cost is paid up front regardless, as an activation cost)."""

    position: Position = Position.FACE_UP_ATTACK
    fusion_only: bool = True

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        extra = s.players[ctx.controller].extra_deck
        eligible = [
            i
            for i in extra
            if s.inst(i).card.is_monster
            and (not self.fusion_only or s.inst(i).card.is_fusion)
        ]
        if not eligible:
            return
        pick = max(eligible, key=lambda i: s.inst(i).card.attack or 0)
        s.special_summon(pick, ctx.controller, self.position)


@dataclass(frozen=True)
class ShuffleFieldMonstersThenExcavate(Primitive):
    """Morphing Jar #2's flip: shuffle every monster on the field into its owner's Deck
    (a Token ceases to exist instead), counting per player how many of THEIR monsters went
    into the Main Deck. Then each player excavates from the top of their Deck until they
    have excavated that many monsters (or the Deck runs out); each excavated Level
    ``max_level``-or-lower monster that can be freely summoned is Special Summoned in
    face-down Defense Position, and every other excavated card (non-monsters, higher-Level
    or non-summonable monsters) is sent to the Graveyard."""

    max_level: int = 4
    position: Position = Position.FACE_DOWN_DEFENSE

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        counts = {0: 0, 1: 0}
        field_monsters = [
            iid for pl in (0, 1) for iid in s.players[pl].monster_zones if iid is not None
        ]
        for iid in field_monsters:
            inst = s.inst(iid)
            if inst.card.is_token:
                s.send_to_graveyard(iid)  # a Token never reaches the Deck
            else:
                counts[inst.owner] += 1
                s.return_to_deck(iid, to_top=False)  # shuffles the owner's Deck
        for pl in (0, 1):
            seen = 0
            while seen < counts[pl] and s.players[pl].deck:
                iid = s.players[pl].deck[-1]  # peek the top
                card = s.inst(iid).card
                if not card.is_monster:
                    s.send_to_graveyard(iid)
                    continue
                seen += 1
                if (
                    (card.level or 0) <= self.max_level
                    and card.can_normal_summon
                    and not card.is_spirit
                ):
                    if not s.special_summon(iid, pl, self.position):
                        s.send_to_graveyard(iid)  # no free zone -> GY (still in Deck)
                else:
                    s.send_to_graveyard(iid)


@dataclass(frozen=True)
class DoubleControlledRaceAtkThenEndPhaseDestroy(Primitive):
    """Limiter Removal: double the ATK of every face-up monster of ``race`` the controller
    controls until the end of the turn (a temporary boost equal to the monster's current
    effective ATK), and mark each so the engine destroys it during this turn's End Phase."""

    race: str = "Machine"

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        for iid in s.players[ctx.controller].monster_zones:
            if iid is None:
                continue
            inst = s.inst(iid)
            if inst.is_face_up and inst.card.race == self.race:
                inst.temp_atk += s.effective_attack(iid)  # +current ATK = doubled
                inst.destroy_at_end_phase = s.turn_count


@dataclass(frozen=True)
class MillFromDeck(Primitive):
    """Send the top ``count`` cards of a player's Deck to their Graveyard (Needle
    Worm decks the opponent; ``player`` is SELF or OPPONENT). The "top" is the end
    of the deck list (where draws come from). Fewer cards than ``count`` -> mill
    as many as there are."""

    player: str = OPPONENT
    count: int = 1

    def execute(self, ctx: EffectContext) -> None:
        deck = ctx.state.players[ctx.side(self.player)].deck
        for _ in range(min(self.count, len(deck))):
            ctx.state.send_to_graveyard(deck[-1])


@dataclass(frozen=True)
class BanishTopOfDeck(Primitive):
    """Banish the top ``count`` cards of a player's Deck (Lady Assailant of Flames banishes
    the top 3 of her controller's own Deck). The "top" is the end of the deck list, where
    draws come from — same convention as MillFromDeck. ``player`` is SELF or OPPONENT. Fewer
    cards than ``count`` -> banish as many as there are."""

    player: str = SELF
    count: int = 3

    def execute(self, ctx: EffectContext) -> None:
        deck = ctx.state.players[ctx.side(self.player)].deck
        for _ in range(min(self.count, len(deck))):
            ctx.state.banish(deck[-1])


@dataclass(frozen=True)
class DiscardFromHand(Primitive):
    """Make a player discard ``count`` cards from their hand to the Graveyard.
    ``player`` is OPPONENT (Confiscation, Delinquent Duo) or SELF. ``random`` picks
    them at random (a "random card" discard); otherwise the effect's controller picks
    after looking at the hand — deterministic first-eligible for the headless path, as
    interactive choice is a deferred enhancement. Fewer cards than ``count`` -> discard
    as many as there are."""

    player: str = OPPONENT
    count: int = 1
    random: bool = False

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        hand = list(s.players[ctx.side(self.player)].hand)
        n = min(self.count, len(hand))
        if n == 0:
            return
        picks = list(s.rng.sample(hand, n)) if self.random else hand[:n]
        for iid in picks:
            s.send_to_graveyard(iid)


@dataclass(frozen=True)
class CardDestructionExchange(Primitive):
    """Card Destruction: both players discard their entire hand, then each draws that
    many cards (controller first). The activated Card Destruction is already out of the
    hand, so it is not among the discards. Draws are capped at the deck size so a short
    deck can't over-draw."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        for pl in (ctx.controller, s.opponent_of(ctx.controller)):
            hand = list(s.players[pl].hand)
            for iid in hand:
                s.send_to_graveyard(iid)
            if hand:
                s.draw(pl, min(len(hand), len(s.players[pl].deck)))


@dataclass(frozen=True)
class ReturnFromHandToDeck(Primitive):
    """Return ``count`` cards from a player's hand to their Deck, then shuffle (The
    Forceful Sentry, Trap Dustshoot). ``monsters_only`` restricts the pick to Monster
    Cards (Trap Dustshoot returns a Monster). The effect's controller picks after
    looking at the hand — deterministic first-eligible here. ``player`` = OPPONENT/SELF."""

    player: str = OPPONENT
    count: int = 1
    monsters_only: bool = False

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        pool = [
            i
            for i in s.players[ctx.side(self.player)].hand
            if not self.monsters_only or s.inst(i).card.is_monster
        ]
        for iid in pool[: self.count]:
            s.return_to_deck(iid, to_top=False)


@dataclass(frozen=True)
class ReturnSpellFromGraveyardToHand(Primitive):
    """Magician of Faith (auto): return the most recently used Spell from your GY to hand."""

    def execute(self, ctx: EffectContext) -> None:
        player = ctx.state.players[ctx.controller]
        spells = [iid for iid in player.graveyard if ctx.state.inst(iid).card.is_spell]
        if not spells:
            return
        iid = spells[-1]
        player.graveyard.remove(iid)
        player.hand.append(iid)
        ctx.state.inst(iid).zone = Zone.HAND


@dataclass(frozen=True)
class DiscardHandThenBurn(Primitive):
    """Send the controller's *entire* hand to the Graveyard, then inflict ``per`` ×
    (cards sent) damage to the opponent (Full Salvo). The count is read before the
    discard, so it reflects exactly what was sent."""

    per: int = 200

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        hand = list(s.players[ctx.controller].hand)
        for iid in hand:
            s.send_to_graveyard(iid)
        opp = s.opponent_of(ctx.controller)
        s.players[opp].life_points -= self.per * len(hand)


@dataclass(frozen=True)
class ReturnFromGraveyardToHand(Primitive):
    """Add up to ``count`` cards from the controller's Graveyard matching
    ``card_filter`` to the hand (Quick Charger adds 2 low-Level "Batteryman"; Monster
    Eye a "Polymerization"). The pick is deterministic — first eligible — as
    interactive Graveyard selection is a deferred enhancement (cf. SearchFromDeck).
    Fewer matches than ``count`` -> recover as many as there are."""

    card_filter: CardFilter = CardFilter()
    count: int = 1

    def execute(self, ctx: EffectContext) -> None:
        gy = list(ctx.state.players[ctx.controller].graveyard)
        picks = [i for i in gy if self.card_filter.matches(ctx.state.inst(i).card)][: self.count]
        for iid in picks:
            ctx.state.return_to_hand(iid)


@dataclass(frozen=True)
class ReturnOwnBattleDeadToHand(Primitive):
    """Return to the hand 1 of the controller's OWN monsters that was destroyed by battle
    *this turn* (The Forgiving Maiden). Reads the per-instance battle-death stamps the GY
    carries — ``died_by_battle`` with ``died_on_turn`` equal to the current turn — so an
    older battle death (or an effect destruction) is never recovered. Deterministic
    first-eligible pick, like ReturnFromGraveyardToHand; a no-op if there is none (the
    activation condition normally guarantees one)."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        for iid in list(s.players[ctx.controller].graveyard):
            inst = s.inst(iid)
            if inst.card.is_monster and inst.died_by_battle and inst.died_on_turn == s.turn_count:
                s.return_to_hand(iid)
                return


@dataclass(frozen=True)
class ReturnFromGraveyardToDeck(Primitive):
    """Return up to ``count`` matching cards from the controller's Graveyard to the
    Deck, then shuffle (Ray of Hope returns 2 LIGHT monsters; Volcanic Recharge up to
    3 "Volcanic"). Deterministic first-eligible pick, like its to-hand sibling."""

    card_filter: CardFilter = CardFilter()
    count: int = 1

    def execute(self, ctx: EffectContext) -> None:
        gy = list(ctx.state.players[ctx.controller].graveyard)
        picks = [i for i in gy if self.card_filter.matches(ctx.state.inst(i).card)][: self.count]
        for iid in picks:
            ctx.state.return_to_deck(iid, to_top=False)


# --- Slice 6: Special Summon from the Graveyard ---
@dataclass(frozen=True)
class SpecialSummonFromGraveyard(Primitive):
    """Special Summon the targeted Graveyard monster to the controller's side.

    The monster arrives in ``position`` (default face-up Attack; Silent Doom /
    Soul Resurrection summon in face-up Defense). With ``link`` set (Call of the
    Haunted, Premature Burial), the source card and the summoned monster are bonded
    both ways: if either later leaves the field, ``GameState`` / the engine destroy
    the other (see ``_cleanup_linked``). The summon fails quietly with no free
    Monster Zone or no valid target.
    """

    link: bool = False
    position: Position = Position.FACE_UP_ATTACK

    def execute(self, ctx: EffectContext) -> None:
        target = ctx.targets[0] if ctx.targets else None
        if target is None or target not in ctx.state.cards:
            return
        inst = ctx.state.inst(target)
        if inst.zone is not Zone.GRAVEYARD or not inst.card.is_monster:
            return
        if inst.card.is_spirit:
            return  # Spirit monsters can never be Special Summoned
        if not ctx.state.special_summon(target, ctx.controller, self.position):
            return  # a lock barred it, or no free Monster Zone
        if self.link:
            ctx.state.inst(ctx.source_iid).linked_to = target
            inst.linked_to = ctx.source_iid


@dataclass(frozen=True)
class SpecialSummonFromHand(Primitive):
    """Special Summon 1 monster from the controller's hand matching ``card_filter``
    (Relieve Monster summons a Level 4-or-lower monster). The pick is deterministic — the
    highest-ATK eligible monster, like SearchFromDeck; interactive choice is a deferred
    enhancement. Fails quietly with no eligible monster, no free Monster Zone, or under a
    Special Summon lock."""

    card_filter: CardFilter = CardFilter()
    position: Position = Position.FACE_UP_ATTACK

    def execute(self, ctx: EffectContext) -> None:
        eligible = [
            iid
            for iid in ctx.state.players[ctx.controller].hand
            if ctx.state.inst(iid).card.is_monster
            and not ctx.state.inst(iid).card.is_spirit
            and self.card_filter.matches(ctx.state.inst(iid).card)
        ]
        if not eligible:
            return
        iid = max(eligible, key=lambda i: ctx.state.inst(i).card.attack or 0)
        ctx.state.special_summon(iid, ctx.controller, self.position)


@dataclass(frozen=True)
class SpecialSummonSelf(Primitive):
    """Special Summon this card (the effect's source) to the controller's field —
    Parasite Paracide springs onto the drawer's field face-up Defense the moment it
    is drawn. A no-op if it isn't somewhere summonable, no Monster Zone is free, or a
    Special Summon lock bars it (the card simply stays where it is)."""

    position: Position = Position.FACE_UP_ATTACK

    def execute(self, ctx: EffectContext) -> None:
        iid = ctx.source_iid
        inst = ctx.state.cards.get(iid)
        if inst is None or inst.zone is Zone.MONSTER:
            return
        ctx.state.special_summon(iid, ctx.controller, self.position)


@dataclass(frozen=True)
class RevealTopSummonRestToHand(Primitive):
    """Cyber Jar's flood: each affected player reveals the top ``count`` cards of their
    Deck; every revealed monster of Level ``max_level`` or lower that can be freely
    Special Summoned is Special Summoned (face-up Attack Position), and every other
    revealed card — non-monsters, higher-Level or non-freely-summonable monsters, or a
    monster a Special Summon lock / a full board turns away — is added to the hand.

    ``side``: None = both players (Cyber Jar), else SELF / OPPONENT. The "top" is the
    end of the deck list (where draws come from). A deck with fewer than ``count`` cards
    reveals as many as it has."""

    count: int = 5
    max_level: int = 4
    side: str | None = None
    position: Position = Position.FACE_UP_ATTACK

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        players = (0, 1) if self.side is None else (ctx.side(self.side),)
        for pl in players:
            deck = s.players[pl].deck
            revealed = list(deck[-min(self.count, len(deck)) :]) if deck else []
            for iid in revealed:
                card = s.inst(iid).card
                summoned = (
                    card.is_monster
                    and (card.level or 0) <= self.max_level
                    and card.can_normal_summon
                    and not card.is_spirit
                    and s.special_summon(iid, pl, self.position)
                )
                if not summoned and s.inst(iid).zone is Zone.DECK:
                    deck.remove(iid)
                    s.players[pl].hand.append(iid)
                    s.inst(iid).zone = Zone.HAND
                    s.inst(iid).position = None


@dataclass(frozen=True)
class RevealRandomHandCardSummonOrGY(Primitive):
    """A Hero Emerges: reveal 1 random card from the controller's hand. If it's a monster
    that can be Special Summoned (a freely-summonable monster — not a Ritual/Nomi that
    needs its own method — with a free Monster Zone and no lock), Special Summon it;
    otherwise send it to the Graveyard."""

    position: Position = Position.FACE_UP_ATTACK

    def execute(self, ctx: EffectContext) -> None:
        hand = ctx.state.players[ctx.controller].hand
        if not hand:
            return
        iid = ctx.state.rng.choice(list(hand))
        card = ctx.state.inst(iid).card
        summoned = (
            card.is_monster
            and card.can_normal_summon
            and not card.is_spirit
            and ctx.state.special_summon(iid, ctx.controller, self.position)
        )
        if not summoned and ctx.state.inst(iid).zone is Zone.HAND:
            ctx.state.send_to_graveyard(iid)


@dataclass(frozen=True)
class CreateToken(Primitive):
    """Special Summon Token monsters synthesised on the fly (Scapegoat's 4 Sheep
    Tokens, Fires of Doomsday's 2 Doomsday Tokens). The Token's printed body is built
    here — it has no registry entry — and is flagged ``is_token`` so it's removed from
    the game (never to the GY) when it leaves the field. ``count`` Tokens drop into
    empty Monster Zones, stopping early when they fill; ``to_opponent`` puts them on
    the opponent's field instead (Ojama Trio). They arrive in ``position``."""

    token_name: str = "Token"
    count: int = 1
    position: Position = Position.FACE_UP_ATTACK
    to_opponent: bool = False
    race: str = ""
    attribute: Attribute = Attribute.DARK
    level: int = 1
    atk: int = 0
    defn: int = 0

    def execute(self, ctx: EffectContext) -> None:
        from .cards import CardDef, CardType  # local import — cards imports this module

        s = ctx.state
        player = ctx.side(OPPONENT) if self.to_opponent else ctx.controller
        token = CardDef(
            name=self.token_name,
            card_type=CardType.MONSTER,
            attribute=self.attribute,
            race=self.race,
            level=self.level,
            attack=self.atk,
            defense=self.defn,
            is_token=True,
        )
        if s.special_summon_locked(player, token):
            return  # a Barrier Statue / Vanity lock bars Special Summoning Tokens
        for _ in range(self.count):
            index = s.first_empty_monster_zone(player)
            if index is None:
                break
            tok = s.spawn_on_field(token, player, index, self.position)
            tok.was_special_summoned = True  # a Token is Special Summoned (Fossil Dyna hits it)


@dataclass(frozen=True)
class SummonTokenIfDestroyedByBattle(Primitive):
    """Insect Queen's End-Phase recursion: if this card destroyed an opponent's monster by
    battle this turn, Special Summon 1 Token (built like CreateToken). A no-op otherwise."""

    token_name: str = "Token"
    race: str = ""
    attribute: Attribute = Attribute.EARTH
    level: int = 1
    atk: int = 0
    defn: int = 0

    def execute(self, ctx: EffectContext) -> None:
        src = ctx.state.cards.get(ctx.source_iid)
        if src is None or not src.destroyed_a_monster_by_battle_this_turn:
            return
        CreateToken(
            token_name=self.token_name,
            race=self.race,
            attribute=self.attribute,
            level=self.level,
            atk=self.atk,
            defn=self.defn,
            position=Position.FACE_UP_ATTACK,
        ).execute(ctx)


# --- Slice 9: take-control ---
@dataclass(frozen=True)
class TakeControl(Primitive):
    """Move the targeted monster to the controller's side of the field.

    ``until_end_of_turn`` (Change of Heart): control returns to the original
    controller during this turn's End Phase. ``equip`` (Snatch Steal): the source
    Equip card stays attached and control reverts when that Equip leaves the
    field. Keeps the monster's battle position ("regardless of position"). Fails
    quietly (the Equip going to the Graveyard) if the taker has no free Monster
    Zone or the target is gone.
    """

    until_end_of_turn: bool = False
    equip: bool = False

    def execute(self, ctx: EffectContext) -> None:
        target = ctx.targets[0] if ctx.targets else None
        monster = ctx.state.cards.get(target) if target is not None else None
        taker = ctx.controller
        ok = monster is not None and monster.zone is Zone.MONSTER and monster.controller != taker
        index = ctx.state.first_empty_monster_zone(taker) if ok else None
        if not ok or index is None:
            if self.equip:
                ctx.state.send_to_graveyard(ctx.source_iid)  # nothing to take -> to the GY
            return
        original = monster.controller
        ctx.state.move_control(target, taker, index)
        monster.control_reverts_to = original
        if self.until_end_of_turn:
            monster.control_until_end_of_turn = ctx.state.turn_count
        if self.equip:
            ctx.state.inst(ctx.source_iid).equipped_to = target
            monster.control_equip_iid = ctx.source_iid


@dataclass(frozen=True)
class SwapControlWithTarget(Primitive):
    """Invader of the Throne: switch control of the targeted opponent monster *with this
    card* — each moves to the other player's side (a permanent swap). A no-op if either
    monster has left the field, or the target is already on the source's side."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        src = s.cards.get(ctx.source_iid)
        target = ctx.targets[0] if ctx.targets else None
        tmon = s.cards.get(target) if target is not None else None
        if src is None or src.zone is not Zone.MONSTER:
            return
        if tmon is None or tmon.zone is not Zone.MONSTER or tmon.controller == src.controller:
            return
        s.swap_control(ctx.source_iid, target)


@dataclass(frozen=True)
class AbsorbMonsterAsEquip(Primitive):
    """Relinquished / Thousand-Eyes Restrict: equip the targeted opponent monster onto this
    card (max 1). The monster leaves its zone and becomes an Equip in the source
    controller's Spell/Trap zone; the source's ATK/DEF copy it via the ``absorbed_monster``
    SelfStatMod, and ``_cleanup_equips`` sends it to its owner's GY when the source leaves.
    A monster already absorbed is released to its owner's GY first."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        src = ctx.source_iid
        taker = s.cards[src].controller
        target = ctx.targets[0] if ctx.targets else None
        monster = s.cards.get(target) if target is not None else None
        if monster is None or monster.zone is not Zone.MONSTER or monster.controller == taker:
            return
        # Max 1: release any monster already equipped to this card.
        for pl in s.players:
            for sid in list(pl.spell_trap_zones):
                if sid is not None and s.cards[sid].equipped_to == src and s.cards[sid].card.is_monster:
                    s.send_to_graveyard(sid)
        index = s.first_empty_spell_trap_zone(taker)
        if index is None:
            return  # no room to hold the absorbed monster — the effect fizzles
        s.place_spell_trap(target, taker, index, Position.FACE_UP_ATTACK)
        s.cards[target].equipped_to = src


@dataclass(frozen=True)
class AcidTrapHole(Primitive):
    """Acid Trap Hole: flip the targeted face-down Defense-Position monster face-up,
    then destroy it if its DEF is ``threshold`` (2000) or less; otherwise set it
    face-down again. (The forced flip does not fire the monster's Flip effect — a
    documented simplification, consistent with the engine's other forced flips.)"""

    threshold: int = 2000

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        target = ctx.targets[0] if ctx.targets else None
        inst = s.cards.get(target) if target is not None else None
        if inst is None or inst.zone is not Zone.MONSTER:
            return
        inst.position = Position.FACE_UP_DEFENSE  # flip it up to read its DEF
        if s.effective_defense(target) <= self.threshold:
            s.send_to_graveyard(target, by_effect=True)
        else:
            inst.position = Position.FACE_DOWN_DEFENSE  # too tough — set it back down


@dataclass(frozen=True)
class SearchCardToTopOfDeck(Primitive):
    """Drill Bug: search a card named ``name`` from the controller's own Deck, shuffle
    the Deck, then place that card on top (the end of the deck list, which ``draw``
    pops). Does nothing if no copy is in the Deck."""

    name: str = ""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        deck = s.players[ctx.controller].deck
        eligible = [i for i in deck if s.inst(i).card.name == self.name]
        s.rng.shuffle(deck)
        if eligible:
            pick = eligible[0]
            deck.remove(pick)
            deck.append(pick)  # the end of the list is the top of the deck


@dataclass(frozen=True)
class BurnDefenseMonsterOriginalAtk(Primitive):
    """Shinato, King of a Higher Plane: when this card destroys a Defense-Position
    monster by battle, inflict damage to the opponent equal to that monster's original
    (printed) ATK. Reads the triggering event's ``destroyed`` iid; a no-op when the
    destroyed monster was not in Defense Position (ordinary battle damage already applied)."""

    def execute(self, ctx: EffectContext) -> None:
        s = ctx.state
        iid = (ctx.event or {}).get("destroyed")
        inst = s.cards.get(iid) if iid is not None else None
        if inst is None or not inst.died_in_defense:
            return
        opp = s.opponent_of(ctx.controller)
        s.players[opp].life_points -= inst.card.attack or 0


# --------------------------------------------------------------------------- #
#  Effect — a card ability
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Effect:
    speed: int = 1
    # "ignition" (you choose, your Main Phase) | "quick" (any priority) | "trigger"
    timing: str = "ignition"
    trigger: Trigger | None = None
    target: TargetSpec | None = None
    # Optional activation gate: (state, controller) -> bool.
    condition: Callable[["GameState", int], bool] | None = None
    # "Once per turn": the source card may activate this Ignition effect only once
    # each turn. Gated in enumeration via CardInstance.effect_activated_on_turn, which
    # the engine stamps on activation.
    once_per_turn: bool = False
    # "This card cannot attack the turn this effect is activated" (Volcanic Slicer,
    # Super Conductor Tyranno). The engine stamps CardInstance.attack_disabled_on_turn.
    disables_attack_this_turn: bool = False
    # Activation cost: discard this many cards from the hand (paid at activation,
    # before resolution). Gated into legal enumeration — the action is only offered
    # when the controller has enough discard fodder (other than the card itself).
    discard_cost: int = 0
    # Activation cost: Tribute this many monsters you control (Spiritual Fire Art,
    # Icarus Attack, Burst Breath). ``tribute_races`` / ``tribute_attributes``
    # restrict which monsters qualify (empty = any). The Tributed monsters are
    # recorded on the source card so the payload can read their printed stats.
    tribute_cost: int = 0
    tribute_races: frozenset = frozenset()
    tribute_attributes: frozenset = frozenset()
    tribute_names: frozenset = frozenset()  # restrict the Tribute fodder by exact name (Multiply: "Kuriboh")
    # Activation cost: remove this many counters of ``counter_type`` from the source
    # card (Royal Magical Library removes 3 Spell Counters to draw).
    counter_cost: int = 0
    counter_type: str = "spell"
    # Activation cost: send this many cards you control from the field to the GY
    # (Levia-Dragon - Daedalus sends a face-up "Umi"; Ultimate Baseball Kid sends
    # another face-up FIRE monster). ``send_to_gy_filter`` is a printed-card
    # predicate (name/race/attribute/kind), ``send_to_gy_face_up`` requires the card
    # be face-up, and ``send_to_gy_exclude_self`` bars the source card itself.
    send_to_gy_cost: int = 0
    send_to_gy_filter: "CardFilter | None" = None
    send_to_gy_face_up: bool = False
    send_to_gy_exclude_self: bool = False
    # Activation cost: banish this many monsters from the controller's Graveyard
    # (Dark Armed Dragon banishes 1 DARK; Lekunga 2 WATER). ``banish_from_gy_filter``
    # is a printed-card predicate (race/attribute/name). The effect's chosen targets
    # are excluded from the fodder, so a GY-targeting payload never banishes its own
    # target (cost and target stay disjoint).
    banish_from_gy_cost: int = 0
    banish_from_gy_filter: "CardFilter | None" = None
    # Activation cost: pay this many Life Points (Premature Burial pays 800, Autonomous
    # Action Unit 1500). Gated into enumeration — only offered while LP exceed the cost
    # (you can't pay a cost that would drop you to 0 or below).
    life_cost: int = 0
    resolve: tuple[Primitive, ...] = ()
