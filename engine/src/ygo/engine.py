"""The engine kernel: the turn/phase state machine that drives a duel.

This is the "universal machinery" — finite and written once. It steps through
the six phases, asks the agents for moves, applies them, and watches for the win
conditions. It deliberately knows nothing about specific cards.

At Milestone 1 only the turn player acts within a phase. The opponent's priority
windows and the Chain are added at M2, slotting into the same per-phase loops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .agents import Agent
from .effects import (
    OPPONENT,
    SELF,
    DefenseAfterAttack,
    DrawTrigger,
    EndPhaseSummonSweep,
    EndPhaseTrigger,
    GraveyardStandbyGainLife,
    GraveyardStandbyReturn,
    SpellCounterHolder,
    StandbyTrigger,
    StandbyUpkeep,
)
from .enums import Phase, Position, TURN_PHASES, Zone
from .moves import (
    ActivateMonsterEffect,
    ActivateSpell,
    ChainLink,
    DeclareAttack,
    FlipSummon,
    NormalSummon,
    Pass,
    SetSpellTrap,
    SpecialSummonFromHand,
    apply,
    can_ritual_summon,
    controls_toon_world,
    legal_actions,
    makeable_fusions,
    pay_costs,
    response_options,
    resolve_effect,
    reveal_for_activation,
    ritual_monster_in_hand,
    ritual_tribute_pool,
    target_candidates,
)
from .state import GameState

# Safety cap so a misbehaving agent can never spin a phase forever.
_MAX_ACTIONS_PER_PHASE = 200


@dataclass
class DuelResult:
    winner: int | None  # player index, or None for a draw
    reason: str


class Engine:
    def __init__(
        self,
        state: GameState,
        agents: list[Agent],
        *,
        first_player_skips_draw: bool = True,  # modern errata
        max_turns: int = 200,
        log: Callable[[str], None] | None = None,
        on_change: Callable[[], None] | None = None,
        pacer: Callable[[], None] | None = None,
    ):
        self.state = state
        self.agents = agents
        self.first_player_skips_draw = first_player_skips_draw
        self.max_turns = max_turns
        self.result: DuelResult | None = None
        self._log = log
        self._on_change = on_change
        self._pacer = pacer
        self._processing_gy = False  # re-entrancy guard for "sent to GY" triggers

    def log(self, message: str) -> None:
        if self._log is not None:
            self._log(message)

    def _changed(self) -> None:
        """Notify observers (e.g. the web server) that the state advanced."""
        if self._on_change is not None:
            self._on_change()

    def _pace(self) -> None:
        """Dramatic pause at a resolution step (no-op when running headless)."""
        if self._pacer is not None:
            self._pacer()

    # ------------------------------------------------------------------ #
    def run(self) -> DuelResult:
        self.state.pending_draws.clear()  # ignore the opening-hand draws (pre-game)
        self.state.summon_events.clear()  # ignore any pre-game Special Summons
        while self.result is None and self.state.turn_count <= self.max_turns:
            self._run_turn()
        if self.result is None:
            self.result = DuelResult(None, f"turn limit reached ({self.max_turns})")
        self.log(f"\nResult: {self._result_text()}")
        return self.result

    def _result_text(self) -> str:
        r = self.result
        assert r is not None
        if r.winner is None:
            return f"draw — {r.reason}"
        return f"{self.state.players[r.winner].name} wins — {r.reason}"

    # ------------------------------------------------------------------ #
    def _run_turn(self) -> None:
        s = self.state
        tp = s.turn_player
        self.log(f"\n=== Turn {s.turn_count}: {s.players[tp].name} ===")
        self._begin_turn(tp)
        for phase in TURN_PHASES:
            if self.result is not None:
                return
            s.phase = phase
            self._changed()
            self._run_phase(phase, tp)
        if self.result is not None:
            return
        s.turn_player = s.opponent_of(tp)
        s.turn_count += 1

    def _begin_turn(self, tp: int) -> None:
        s = self.state
        s.normal_summon_used = False
        s.forced_attack_target = None  # Staunch Defender's lock lasts only its turn
        s.action_locks = {k: v for k, v in s.action_locks.items() if v >= s.turn_count}
        # Reset per-turn flags on BOTH players' monsters: "this turn" means the turn that
        # just started, so a monster summoned on the opponent's previous turn must not keep
        # a stale `summoned_this_turn` (else Infinite Dismissal's both-sides End-Phase sweep
        # would destroy it as if summoned this turn). Mirrors ygopro's RESET_SELF/OPPO_TURN.
        for pl in (tp, s.opponent_of(tp)):
            for iid in s.players[pl].monster_zones:
                if iid is not None:
                    s.inst(iid).reset_turn_flags()

    def _run_phase(self, phase: Phase, tp: int) -> None:
        if phase is Phase.DRAW:
            self._draw_phase(tp)
        elif phase is Phase.STANDBY:
            self._standby_phase(tp)
        elif phase in (Phase.MAIN_1, Phase.MAIN_2):
            self._interactive_phase(tp)
        elif phase is Phase.BATTLE:
            self._battle_phase(tp)
        elif phase is Phase.END:
            self._end_phase(tp)

    # ------------------------------------------------------------------ #
    def _draw_phase(self, tp: int) -> None:
        s = self.state
        if s.turn_count == 1 and self.first_player_skips_draw:
            self.log(f"{s.players[tp].name} skips the first Draw Phase")
            return
        drawn = s.draw(tp, 1)
        if not drawn:
            self.result = DuelResult(s.opponent_of(tp), f"{s.players[tp].name} decked out")
            return
        self.log(f"{s.players[tp].name} draws {s.inst(drawn[0]).name}")
        self._process_draw_triggers()
        self._check_exodia()
        self._changed()

    def _process_draw_triggers(self) -> None:
        """Solemn Wishes: pay each queued draw out to its drawer's face-up cards.

        Unlike the gy_from_field / summon_events drain this needs no re-entrancy guard:
        a draw trigger only gains Life Points, so draining one can't itself queue a draw.
        """
        s = self.state
        while s.pending_draws:
            player = s.pending_draws.pop(0)
            for inst, mod in s.active_markers(DrawTrigger, (player,)):
                if mod.gain_life:
                    s.players[player].life_points += mod.gain_life
                    self.log(f"  {s.players[player].name} gains {mod.gain_life} LP from {inst.name}")

    # ------------------------------------------------------------------ #
    def _standby_phase(self, tp: int) -> None:
        """Resolve each face-up card's per-Standby upkeep (Slice 8).

        Any face-up card on either side may carry a ``StandbyUpkeep`` — a
        maintenance cost (Messenger of Peace), a recovery (Cure Mermaid), or a
        burn (Burning Land). The hook is card-type-agnostic: monsters, Continuous
        Spells/Traps and Field Spells are all scanned the same way.
        """
        s = self.state
        fired = False
        for iid in self._standby_upkeep_order():
            if self.result is not None:
                break
            inst = s.cards.get(iid)
            if inst is None or not inst.is_face_up or not inst.effects_active:
                continue  # left the field, or a Gemini not yet Gemini Summoned
            if s.effect_negated(iid):
                continue  # Skill Drain (Cure Mermaid) / Imperial Order (Snatch Steal, Burning Land)
            for mod in inst.card.continuous:
                if isinstance(mod, StandbyUpkeep) and self._apply_standby_upkeep(inst, mod, tp):
                    fired = True
                elif isinstance(mod, StandbyTrigger):
                    # Fires a full Effect on its own Chain (Bowganian's burn) — that
                    # path runs its own life-point / GY / draw checks, so it doesn't
                    # need the fixed-LP `fired` bookkeeping below.
                    self._fire_standby_trigger(inst, mod, tp)
        self._fire_graveyard_standby_effects(tp)
        if fired:
            self._check_life_points()
            self._check_field_to_gy_triggers()
            self._changed()

    def _fire_graveyard_standby_effects(self, tp: int) -> None:
        """Graveyard-sourced Standby effects on the turn player's own GY: Sinister Serpent
        (``GraveyardStandbyReturn`` — add one carrier back to the hand, once per turn) and
        Darklord Marie (``GraveyardStandbyGainLife`` — gain LP per carrier). Only the turn
        player's own GY is scanned ("during YOUR Standby Phase, if this card is in YOUR GY")."""
        s = self.state
        if self.result is not None:
            return
        # Return-to-hand: at most one carrier per Standby Phase.
        for iid in list(s.players[tp].graveyard):
            inst = s.cards.get(iid)
            if inst is None or inst.owner != tp:
                continue
            if any(isinstance(m, GraveyardStandbyReturn) for m in inst.card.continuous):
                s.return_to_hand(iid)
                self.log(f"  {s.players[tp].name} adds {inst.name} from the GY to their hand")
                self._changed()
                break  # one per turn
        # Gain-life: each carrier grants its LP (Darklord Marie).
        for iid in list(s.players[tp].graveyard):
            inst = s.cards.get(iid)
            if inst is None or inst.owner != tp:
                continue
            for mod in inst.card.continuous:
                if isinstance(mod, GraveyardStandbyGainLife) and mod.amount:
                    s.players[tp].life_points += mod.amount
                    self.log(f"  {s.players[tp].name} gains {mod.amount} LP from {inst.name} (GY)")
                    self._changed()

    def _standby_upkeep_order(self) -> list[int]:
        """Face-up cards that might carry a Standby upkeep, in a stable order
        (turn player first), snapshotted so destroying one mid-phase is safe."""
        s = self.state
        order: list[int] = []
        for pl in (s.turn_player, s.opponent_of(s.turn_player)):
            order.extend(s.field_cards(pl, face_up_only=True))
        return order

    def _apply_standby_upkeep(self, inst, mod: StandbyUpkeep, tp: int) -> bool:
        """Resolve one StandbyUpkeep during ``tp``'s Standby Phase. Returns True if
        it did anything (so the caller knows to re-check Life Points / the field)."""
        s = self.state
        controller = inst.controller
        if mod.whose == "controller" and controller != tp:
            return False  # only fires during the controller's own Standby Phase
        if mod.whose == "opponent" and controller == tp:
            return False  # only fires during the controller's opponent's Standby Phase
        # The beneficiary (who gains/pays) is the controller, except "opponent"
        # upkeeps (Snatch Steal), which benefit the controller's opponent.
        beneficiary = s.opponent_of(controller) if mod.whose == "opponent" else controller
        name = inst.name
        if mod.pay_life:
            player = s.players[beneficiary]
            if player.life_points > mod.pay_life:
                player.life_points -= mod.pay_life
                self.log(f"  {player.name} pays {mod.pay_life} LP to maintain {name}")
            else:
                self.log(f"  {player.name} cannot pay {mod.pay_life} LP — {name} is destroyed")
                s.send_to_graveyard(inst.iid)
            return True
        if mod.gain_life:
            player = s.players[beneficiary]
            player.life_points += mod.gain_life
            self.log(f"  {player.name} gains {mod.gain_life} LP from {name}")
            return True
        if mod.burn_life:
            victim = s.players[tp]  # the active player takes the damage
            victim.life_points -= mod.burn_life
            self.log(f"  {victim.name} takes {mod.burn_life} damage from {name}")
            return True
        return False

    def _fire_standby_trigger(self, inst, mod: StandbyTrigger, tp: int) -> None:
        """Fire a face-up card's StandbyTrigger during ``tp``'s Standby Phase — the
        source controller's Effect on a fresh Chain (Bowganian's burn, Dancing Fairy's
        LP gain, Destiny HERO - Defender's "opponent draws"). Scoped by ``whose`` and
        the source's battle position; suppressed while the source's effects are negated
        (Skill Drain on a monster, Royal Decree / Imperial Order on a Spell/Trap)."""
        s = self.state
        if self.result is not None:
            return
        controller = inst.controller
        if mod.whose == "controller" and controller != tp:
            return  # only the controller's own Standby Phase
        if mod.whose == "opponent" and controller == tp:
            return  # only the controller's opponent's Standby Phase
        if mod.requires_defense and inst.position is not Position.FACE_UP_DEFENSE:
            return
        if mod.requires_attack and inst.position is not Position.FACE_UP_ATTACK:
            return
        if mod.requires_equipped and inst.equipped_to is None:
            return  # Blast Sphere fires only once it has equipped to the attacker
        if s.effect_negated(inst.iid):
            return
        self._trigger_effect(inst.iid, mod.effect, controller)

    def _fire_end_phase_triggers(self, tp: int) -> None:
        """Fire every face-up card's EndPhaseTrigger during ``tp``'s End Phase — the
        End-Phase analogue of the Standby-Phase trigger sweep (Lady Heat's burn, the
        Lightsworn mills, Little-Winguard / Garuda position changes). Same face-up,
        turn-player-first, snapshotted order so a card destroying another mid-phase is
        safe."""
        s = self.state
        for iid in self._standby_upkeep_order():  # generic face-up field scan
            if self.result is not None:
                break
            inst = s.cards.get(iid)
            if inst is None or not inst.is_face_up or not inst.effects_active:
                continue  # left the field, or a Gemini not yet Gemini Summoned
            for mod in inst.card.continuous:
                if isinstance(mod, EndPhaseTrigger):
                    self._fire_end_phase_trigger(inst, mod, tp)

    def _fire_end_phase_trigger(self, inst, mod: EndPhaseTrigger, tp: int) -> None:
        """Fire one face-up card's EndPhaseTrigger during ``tp``'s End Phase — the
        source controller's Effect on a fresh Chain. Scoped by ``whose`` and the
        source's battle position; suppressed while the source's effects are negated.
        (Identical scoping to ``_fire_standby_trigger``, one phase later.)"""
        s = self.state
        if self.result is not None:
            return
        controller = inst.controller
        if mod.whose == "controller" and controller != tp:
            return  # only the controller's own End Phase
        if mod.whose == "opponent" and controller == tp:
            return  # only the controller's opponent's End Phase
        if mod.requires_defense and inst.position is not Position.FACE_UP_DEFENSE:
            return
        if mod.requires_attack and inst.position is not Position.FACE_UP_ATTACK:
            return
        if s.effect_negated(inst.iid):
            return
        self._trigger_effect(inst.iid, mod.effect, controller)

    def _interactive_phase(self, tp: int) -> None:
        """Main Phase 1 / 2: the turn player takes moves until they Pass."""
        s = self.state
        for _ in range(_MAX_ACTIONS_PER_PHASE):
            if self.result is not None:
                return
            menu = legal_actions(s, tp) + [Pass()]
            choice = self.agents[tp].decide(s, menu)
            if isinstance(choice, Pass):
                return
            if isinstance(choice, ActivateSpell):
                self._activate_as_chain(choice, tp)
            elif isinstance(choice, ActivateMonsterEffect):
                self._activate_monster_effect(choice, tp)
            elif isinstance(choice, NormalSummon):
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._changed()
                s.summon_events.append((choice.iid, tp, "normal"))
                # One drain handles both: a Tribute's "sent to GY" triggers, then the
                # Summon's response window (Trap Hole) + the monster's trigger (Breaker).
                self._check_field_to_gy_triggers()
                self._check_life_points()
            elif isinstance(choice, SpecialSummonFromHand):
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._changed()
                # The summon was queued by state.special_summon; draining it opens the
                # opponent's response window (Black Horn, Bottomless) + fires the monster's
                # own "when Special Summoned" Trigger — the same path every SS route uses.
                self._check_field_to_gy_triggers()
                self._check_life_points()
            elif isinstance(choice, FlipSummon):
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._changed()
                s.summon_events.append((choice.iid, tp, "flip"))
                # Drain: the opponent may respond to the Flip Summon (Torrential), then
                # the Flip Effect (Man-Eater Bug) + any "when Summoned" trigger resolve.
                self._check_field_to_gy_triggers()
                self._check_life_points()
            else:
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._check_life_points()
                self._changed()

    def _battle_phase(self, tp: int) -> None:
        s = self.state
        s.battle_phase_ended = False
        if s.turn_count == 1:  # the player going first gets no Battle Phase
            return
        for _ in range(_MAX_ACTIONS_PER_PHASE):
            if self.result is not None or s.battle_phase_ended:
                return
            menu = legal_actions(s, tp) + [Pass()]
            choice = self.agents[tp].decide(s, menu)
            if isinstance(choice, Pass):
                break
            if isinstance(choice, DeclareAttack):
                self._declare_attack(choice, tp)
            else:
                self.log(f"  {s.players[tp].name}: {apply(s, choice)}")
                self._check_life_points()
                self._changed()
        self._wipe_spell_counters_after_battle()  # Mythical Beast Cerberus

    def _declare_attack(self, action: DeclareAttack, tp: int) -> None:
        """Declare an attack, open a response window, then resolve it if still valid."""
        s = self.state
        attacker, target = action.attacker, action.target
        s.attack_negated = False
        s.attack_redirect = None
        s.reflect_battle_damage = False
        # Mark at declaration (not only in _resolve_attack) so a *negated* attack — which
        # returns before resolving — still counts as this monster having attacked.
        s.inst(attacker).attacked_this_turn = True
        # Dark Elf: pay the LP cost required to attack (enumeration already verified it is
        # payable). Paid at declaration, even if the attack is later negated.
        cost = s.attack_life_cost(attacker)
        if cost:
            s.players[tp].life_points -= cost
            self.log(f"  {s.players[tp].name} pays {cost} LP for {s.inst(attacker).name} to attack")
        self.log(f"  {s.players[tp].name} declares an attack with {s.inst(attacker).name}")
        self._changed()

        self._response_window(
            {"kind": "attack_declared", "player": tp, "attacker": attacker, "target": target}
        )
        if self.result is not None:
            return

        # The attacker's own "when this declares an attack" Trigger (Jirai Gumo) fires now.
        self._fire_attack_declared_trigger(attacker)
        if self.result is not None:
            return

        if s.attack_negated:
            # A negated attack still CONSUMES the attack (no replay) — unlike a target
            # that merely left the field, which grants an attack replay. _resolve_attack
            # (skipped here) is where attacks_made is normally counted, so count it now.
            neg = s.cards.get(attacker)
            if neg is not None and neg.zone is Zone.MONSTER:
                neg.attacks_made_this_turn += 1
            self.log("  the attack is negated")
            self._changed()
            return
        atk = s.cards.get(attacker)
        if atk is None or atk.zone is not Zone.MONSTER or atk.position is not Position.FACE_UP_ATTACK:
            self.log("  the attacker is no longer able to attack")
            self._changed()
            return
        # A response may have redirected the attack to a different monster the defender
        # controls (Call of the Earthbound, Jam Defender).
        if s.attack_redirect is not None and s.attack_redirect in s.cards:
            target = s.attack_redirect
            self.log(f"  the attack is redirected to {s.inst(target).name}")
        if target is not None and target not in s.cards:
            self._changed()  # the target left the field; the attack fizzles
            return

        # "When this card is attacked" — the attacked monster's OWN reactive Trigger
        # fires before damage calculation (Blast Sphere equips itself to the attacker).
        # If it pulls the target out of the monster zone, the attack fizzles.
        if target is not None:
            self._fire_attacked_trigger(target, attacker)
            if self.result is not None:
                return
            tinst = s.cards.get(target)
            if tinst is None or tinst.zone is not Zone.MONSTER:
                self.log("  the attack target is no longer on the field; the attack fizzles")
                self._changed()
                return
            atk = s.cards.get(attacker)
            if atk is None or atk.zone is not Zone.MONSTER or atk.position is not Position.FACE_UP_ATTACK:
                self.log("  the attacker is no longer able to attack")
                self._changed()
                return

        # A face-down monster being attacked is flipped — note its Flip Effect first.
        flip_pending = None
        if target is not None:
            tinst = s.cards.get(target)
            if tinst is not None and tinst.position is Position.FACE_DOWN_DEFENSE:
                effect = self._flip_effect(tinst.card)
                if effect is not None:
                    flip_pending = (target, tinst.controller, effect)

        self.log(f"  {s.players[tp].name}: {apply(s, DeclareAttack(attacker, target))}")
        self._check_life_points()
        self._changed()
        self._check_field_to_gy_triggers()  # combat may have sent a trigger monster to GY

        # Flip Effects resolve after damage (even if the monster was destroyed in battle).
        if flip_pending is not None and self.result is None:
            iid, controller, effect = flip_pending
            self._trigger_effect(iid, effect, controller)
            self._check_life_points()

        # "When this card inflicts battle damage to your opponent" (Don Zaloog,
        # Airknight Parshath) — fired after combat from the state's transient record.
        self._fire_battle_damage_trigger()

        # "When this card destroys a monster by battle" (Masked Chopper, Guardian Angel
        # Joan, Hydrogeddon) — fired from the (destroyer, destroyed) pairs combat recorded.
        self._fire_destroys_by_battle_trigger()

        # "When this card battles an opponent's monster" (D.D. Warrior Lady's mutual
        # banish) — fired from the recorded combatant pair, regardless of who survived.
        self._fire_battles_trigger()

        # "When you take battle damage" — the player who took the combat damage may now
        # activate a Set Trap that reacts to it (Numinous Healer, Attack and Receive,
        # Damage Condenser).
        self._fire_damage_taken_window()

        # Spear Dragon / Goblin Attack Force: switch the attacker to Defense once its
        # attack has resolved (and lock its position if the rider says so).
        self._switch_attacker_to_defense_after_attack(attacker)

    # ------------------------------------------------------------------ #
    #  The Chain
    # ------------------------------------------------------------------ #
    def _activate_as_chain(self, action: ActivateSpell, controller: int) -> None:
        """Turn player activates a Spell: it becomes Chain Link 1, then build/resolve."""
        s = self.state
        card = s.inst(action.iid).card
        if any(e.timing == "fusion" for e in card.effects):
            self._fusion_summon(action.iid, controller)
            return
        if any(e.timing == "ritual" for e in card.effects):
            self._ritual_summon(action.iid, controller)
            return
        effect = next((e for e in card.effects if e.timing in ("ignition", "quick")), card.effects[0])
        reveal_for_activation(s, action.iid, action.zone_index)
        self.log(f"  {s.players[controller].name} activates {card.name}")
        self._pay_activation_cost(action.iid, controller, effect, tuple(action.targets))
        self._mark_once_per_turn(action.iid, effect)
        self._run_chain([ChainLink(action.iid, effect, controller, tuple(action.targets), None)])

    def _activate_monster_effect(self, action: ActivateMonsterEffect, controller: int) -> None:
        """Turn player activates a face-up monster's Ignition effect (Royal Magical
        Library). Pay its cost, then resolve it as a one-link Chain."""
        s = self.state
        card = s.inst(action.iid).card
        effect = next((e for e in card.effects if e.timing == "ignition"), card.effects[0])
        self.log(f"  {s.players[controller].name} activates {card.name}'s effect")
        self._pay_activation_cost(action.iid, controller, effect, tuple(action.targets))
        self._mark_once_per_turn(action.iid, effect)
        self._run_chain([ChainLink(action.iid, effect, controller, tuple(action.targets), None)])

    def _mark_once_per_turn(self, iid: int, effect) -> None:
        """Stamp the per-turn bookkeeping an activated effect leaves on its source: a
        "once per turn" use (so enumeration won't offer it again this turn) and/or a
        "cannot attack the turn this effect is activated" lock."""
        if iid not in self.state.cards:
            return
        inst = self.state.inst(iid)
        if effect.once_per_turn:
            inst.effect_activated_on_turn = self.state.turn_count
        if effect.disables_attack_this_turn:
            inst.attack_disabled_on_turn = self.state.turn_count

    def _pay_activation_cost(self, source_iid: int, controller: int, effect, targets=()) -> None:
        """Pay an effect's activation costs (discard / Tribute / counter / send-to-GY /
        banish-from-GY) before it resolves. The player picks the fodder (bot via
        heuristic, human via a prompt); an illegal pick falls back to the default
        heuristic. ``targets`` are excluded from the banish-from-GY fodder."""
        s = self.state

        def picker(kind: str, fodder: list[int], need: int):
            chosen = self.agents[controller].choose_cost_fodder(s, controller, fodder, need, kind=kind)
            if len(set(chosen)) != need or any(c not in fodder for c in chosen):
                chosen = Agent().choose_cost_fodder(s, controller, fodder, need, kind=kind)  # safe default
            return chosen

        lines = pay_costs(s, controller, source_iid, effect, picker, targets)
        for line in lines:
            self.log(f"  {s.players[controller].name} {line} (cost)")
        if lines:
            self._changed()

    def _fusion_summon(self, poly_iid: int, controller: int) -> None:
        """Polymerization: pick a makeable Fusion, send its materials from hand/field
        to the GY, and Special Summon it from the Extra Deck."""
        s = self.state
        options = makeable_fusions(s, controller)
        if not options:
            return  # nothing to make (shouldn't happen — gated at activation)
        reveal_for_activation(s, poly_iid)  # Polymerization shows in a Spell/Trap zone
        self.log(f"  {s.players[controller].name} activates Polymerization")
        self._changed()

        fusion_iids = [fid for fid, _ in options]
        chosen = self.agents[controller].choose_card(s, "Fusion Summon which monster?", fusion_iids)
        if chosen not in fusion_iids:
            chosen = fusion_iids[0]
        materials = next(mats for fid, mats in options if fid == chosen)

        if s.special_summon_locked(controller, s.inst(chosen).card):
            self.log("  Fusion Summon barred by a Special Summon lock")
            s.send_to_graveyard(poly_iid)  # Polymerization fizzles; materials stay
            self._changed()
            return

        names = " + ".join(s.inst(m).name for m in materials)
        for m in materials:
            s.send_to_graveyard(m)
        s.special_summon(chosen, controller, Position.FACE_UP_ATTACK)
        self.log(f"  Fusion Summon: {s.inst(chosen).name} ({names})")
        s.send_to_graveyard(poly_iid)  # Polymerization is spent (Normal Spell)
        self._check_life_points()
        self._changed()
        self._check_field_to_gy_triggers()  # materials leaving the field may trigger (Sangan)

    def _ritual_summon(self, spell_iid: int, controller: int) -> None:
        """A Ritual Spell: Tribute monsters (Levels >= the Ritual Monster's Level)
        from hand/field, then Special Summon that monster from the hand."""
        from .card_effects import RITUALS

        s = self.state
        monster_name = RITUALS.get(s.inst(spell_iid).card.name)
        if monster_name is None or not can_ritual_summon(s, controller, monster_name):
            return  # gated at activation; defensive
        monster_iid = ritual_monster_in_hand(s, controller, monster_name)
        if s.special_summon_locked(controller, s.inst(monster_iid).card):
            return  # a Special Summon lock bars the Ritual Summon (gated at activation too)
        required = s.inst(monster_iid).card.level or 0
        pool = ritual_tribute_pool(s, controller, monster_iid)

        reveal_for_activation(s, spell_iid)  # the Ritual Spell shows in a Spell/Trap zone
        self.log(f"  {s.players[controller].name} activates {s.inst(spell_iid).name}")
        self._changed()

        tributes = self.agents[controller].choose_tributes(s, controller, pool, required)
        valid = (
            tributes
            and len(set(tributes)) == len(tributes)
            and all(t in pool for t in tributes)
            and sum(s.inst(t).card.level or 0 for t in tributes) >= required
        )
        if not valid:  # bad selection — pick a default that satisfies the cost
            tributes = Agent().choose_tributes(s, controller, pool, required)

        names = ", ".join(s.inst(t).name for t in tributes)
        for t in tributes:
            s.send_to_graveyard(t)
        if not s.special_summon(monster_iid, controller, Position.FACE_UP_ATTACK):
            s.send_to_graveyard(spell_iid)  # no room (shouldn't happen) — fizzle
            return
        self.log(f"  Ritual Summon: {s.inst(monster_iid).name} (Tribute: {names})")
        s.send_to_graveyard(spell_iid)  # the Ritual Spell is spent
        self._check_life_points()
        self._changed()
        self._check_field_to_gy_triggers()

    def _response_window(self, event: dict) -> None:
        """Give the opponent of the acting player a chance to start a chain."""
        s = self.state
        responder = s.opponent_of(event["player"])
        link = self._offer_response(responder, event, last_speed=1)
        if link is not None:
            self._run_chain([link])

    def _run_chain(self, links: list[ChainLink]) -> None:
        """Build the chain by alternating priority, then resolve last-in-first-out."""
        s = self.state
        s.chain = list(links)
        self._changed()
        self._pace()

        responder = s.opponent_of(s.chain[-1].controller)
        passes = 0
        while passes < 2 and self.result is None:
            link = self._offer_response(responder, event=None, last_speed=s.chain[-1].effect.speed)
            if link is not None:
                s.chain.append(link)
                passes = 0
                self._changed()
                self._pace()
            else:
                passes += 1
            responder = s.opponent_of(responder)

        self._resolve_chain()

    def _offer_response(self, player: int, event: dict | None, last_speed: int):
        """Ask ``player`` to activate a fast-enough effect, or pass. Returns a link or None."""
        s = self.state
        options = response_options(s, player, event, last_speed)
        if not options:
            return None
        chosen = self.agents[player].respond(s, options, event)
        if chosen is None:
            return None
        card = s.inst(chosen.iid).card
        effect = card.effects[0]
        reveal_for_activation(s, chosen.iid, chosen.zone_index)
        self.log(f"  {s.players[player].name} activates {card.name}")
        self._pay_activation_cost(chosen.iid, player, effect)
        return ChainLink(chosen.iid, effect, player, tuple(chosen.targets), event)

    def _resolve_chain(self) -> None:
        s = self.state
        for link in reversed(s.chain):
            # A link is negated either explicitly (a Counter Trap marked it) or because
            # a face-up class negator (Royal Decree negates Traps, Imperial Order negates
            # Spells) shuts off the resolving Spell/Trap's effect — evaluated now, at
            # resolution, so the negator only has to be live at that moment.
            if link.negated or s.effect_negated(link.source_iid):
                name = s.inst(link.source_iid).name if link.source_iid in s.cards else "effect"
                self.log(f"  {name} is negated")
                self._changed()
                self._pace()
                continue
            resolve_effect(s, link.effect, link.source_iid, link.targets, link.event)
            self._check_life_points()
            self._check_exodia()  # a search/draw effect may have completed an Exodia hand
            # "Each time a Spell Card resolves, place 1 Spell Counter" (Royal Magical
            # Library, Mythical Beast Cerberus) — one per resolved Spell link.
            spell = s.cards.get(link.source_iid)
            if spell is not None and spell.card.is_spell:
                self._place_spell_counters()
            self._changed()
            self._pace()
        # Spent, non-permanent Spells/Traps go to the Graveyard — except a Normal
        # Spell/Trap that "remains on the field" (Swords of Revealing Light), which we
        # recognise by it carrying continuous markers that must stay live.
        for link in s.chain:
            inst = s.cards.get(link.source_iid)
            if (
                inst is not None
                and inst.zone is Zone.SPELL_TRAP
                and not inst.card.is_permanent
                and not inst.card.continuous
            ):
                s.send_to_graveyard(link.source_iid)
        s.chain = []
        self._changed()
        self._check_field_to_gy_triggers()  # resolution may have sent trigger monsters to GY
        self._process_draw_triggers()  # resolution may have drawn cards (Pot of Greed)

    # ------------------------------------------------------------------ #
    #  Monster-effect triggers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _trigger_effects(card, kind=None, by=None):
        """Yield ``card``'s ``timing="trigger"`` Effects, optionally narrowed to a
        Trigger ``kind`` and/or ``by`` side — the one place that knows the shape of a
        trigger Effect, so every _fire_*/find_* trigger helper filters off this."""
        for e in card.effects:
            if e.timing != "trigger" or e.trigger is None:
                continue
            if kind is not None and e.trigger.kind != kind:
                continue
            if by is not None and e.trigger.by != by:
                continue
            yield e

    @staticmethod
    def _flip_effect(card):
        return next((e for e in card.effects if e.timing == "flip"), None)

    def _trigger_flip_effect(self, iid: int) -> None:
        inst = self.state.cards.get(iid)
        if inst is None:
            return
        effect = self._flip_effect(inst.card)
        if effect is not None:
            self._trigger_effect(iid, effect, inst.controller)

    def _trigger_summon_effect(self, iid: int, summon_kind: str) -> None:
        """Fire a monster's own "when (Normal) Summoned" Trigger Effect — its
        controller's effect on a fresh Chain, after the Summon has resolved and
        survived any summon-negation window (Breaker places a Spell Counter on
        itself; Gravekeeper's Curse burns 500). A ``summon_kinds``-restricted
        Trigger only fires on its kinds (Breaker = Normal Summon only)."""
        if self.result is not None:
            return
        inst = self.state.cards.get(iid)
        if inst is None or inst.zone is not Zone.MONSTER or not inst.is_face_up:
            return  # the Summon was negated / the monster left the field
        if not inst.effects_active:
            return  # a Gemini Normal Summoned (not yet Gemini Summoned) has no live effect
        effect = next(
            (
                e
                for e in self._trigger_effects(inst.card, kind="summon", by=SELF)
                if not e.trigger.summon_kinds or summon_kind in e.trigger.summon_kinds
            ),
            None,
        )
        if effect is not None:
            if effect.condition is not None and not effect.condition(self.state, inst.controller):
                return  # Mazera DeVille needs "Pandemonium" on the field
            self._trigger_effect(iid, effect, inst.controller)

    def _fire_battle_damage_trigger(self) -> None:
        """Fire a monster's "when it inflicts battle damage to your opponent" SELF
        Trigger (Don Zaloog, Vampire Lady, Airknight Parshath) — read from the state's
        transient ``battle_damage_dealt`` record set during combat. Only fires if the
        dealer is still face-up on the field; the event carries the damage ``amount``."""
        s = self.state
        dealt = s.battle_damage_dealt
        s.battle_damage_dealt = None
        if dealt is None or self.result is not None:
            return
        dealer_iid, amount = dealt
        inst = s.cards.get(dealer_iid)
        if inst is None or inst.zone is not Zone.MONSTER or not inst.is_face_up:
            return
        effect = next(
            self._trigger_effects(inst.card, kind="battle_damage_inflicted", by=SELF), None
        )
        if effect is not None:
            self._trigger_effect(dealer_iid, effect, inst.controller, {"amount": amount})

    def _fire_damage_taken_window(self) -> None:
        """Open a response window for the player who just took battle damage, letting them
        activate a Set Trap that triggers on it (Numinous Healer, Attack and Receive,
        Damage Condenser). Unlike ``_response_window`` (which always offers the *opponent*
        of the acting player), this targets the victim specifically — the victim may be the
        attacker, when their monster lost the battle. Read from the transient
        ``battle_damage_taken`` record; the event carries the damage ``amount``."""
        s = self.state
        rec = s.battle_damage_taken
        s.battle_damage_taken = None
        if rec is None or self.result is not None:
            return
        victim, amount = rec
        if amount <= 0:
            return
        event = {"kind": "battle_damage_taken", "player": victim, "amount": amount}
        link = self._offer_response(victim, event, last_speed=1)
        if link is not None:
            self._run_chain([link])

    def _fire_destroys_by_battle_trigger(self) -> None:
        """Fire each monster's "when this card destroys a monster by battle" SELF Trigger
        (Masked Chopper's 2000 burn, Guardian Angel Joan's LP gain, Hydrogeddon's recruit,
        Divine Knight Ishzark's banish) from the transient ``battle_destroyed_by`` record.
        Each (destroyer, destroyed) pair fires the destroyer's effect on a fresh Chain,
        guarded on the destroyer still being a live face-up monster — so mutual destruction,
        where the destroyer itself died, does not fire. The event carries the ``destroyed``
        iid so the payload can read its original ATK (Joan) or banish it (Ishzark)."""
        s = self.state
        pairs = s.battle_destroyed_by
        s.battle_destroyed_by = []
        for destroyer_iid, destroyed_iid in pairs:
            if self.result is not None:
                return
            inst = s.cards.get(destroyer_iid)
            if inst is None or inst.zone is not Zone.MONSTER or not inst.is_face_up:
                continue
            if not inst.effects_active:
                continue  # a Gemini not yet Gemini Summoned has no effect
            effect = next(self._trigger_effects(inst.card, kind="destroys_by_battle", by=SELF), None)
            if effect is None:
                continue
            if effect.condition is not None and not effect.condition(s, inst.controller):
                continue
            self._trigger_effect(
                destroyer_iid,
                effect,
                inst.controller,
                {"destroyer": destroyer_iid, "destroyed": destroyed_iid},
            )

    def _fire_battles_trigger(self) -> None:
        """Fire a monster's "when this card battles an opponent's monster" SELF Trigger
        after damage calculation (D.D. Warrior Lady's mutual banish), from the transient
        ``battle_pair`` combatants. Each carrier banishes its foe and itself; it fires
        even if the carrier was destroyed in the battle (it banishes itself from the
        Graveyard), so — unlike the destroys/dealt-damage triggers — it is NOT gated on
        the source still being a live face-up monster. The event carries the ``foe`` iid
        (the opponent's monster in the battle)."""
        s = self.state
        pair = s.battle_pair
        s.battle_pair = None
        if pair is None or self.result is not None:
            return
        a, b = pair
        for me_iid, foe_iid in ((a, b), (b, a)):
            if self.result is not None:
                return
            inst = s.cards.get(me_iid)
            if inst is None or not inst.card.is_monster:
                continue
            if s.monster_effects_negated(me_iid):
                continue  # Skill Drain on a survivor; a GY carrier is never negated
            effect = next(self._trigger_effects(inst.card, kind="battles", by=SELF), None)
            if effect is None:
                continue
            if effect.condition is not None and not effect.condition(s, inst.controller):
                continue
            self._trigger_effect(me_iid, effect, inst.controller, {"foe": foe_iid})

    def _fire_attack_declared_trigger(self, attacker_iid: int) -> None:
        """Fire the attacking monster's OWN "when this card declares an attack" Trigger
        Effect (Jirai Gumo's coin toss) on a fresh Chain — after the opponent's response
        window, guarded on the attacker still being a live, face-up attacker."""
        s = self.state
        if self.result is not None:
            return
        inst = s.cards.get(attacker_iid)
        if (
            inst is None
            or inst.zone is not Zone.MONSTER
            or inst.position is not Position.FACE_UP_ATTACK
            or not inst.effects_active
        ):
            return
        effect = next(self._trigger_effects(inst.card, kind="attack_declared", by=SELF), None)
        if effect is not None:
            if effect.condition is not None and not effect.condition(s, inst.controller):
                return  # Gravekeeper's Assailant needs "Necrovalley" on the field
            self._trigger_effect(attacker_iid, effect, inst.controller, {"attacker": attacker_iid})

    def _fire_attacked_trigger(self, target_iid: int, attacker_iid: int) -> None:
        """Fire the ATTACKED monster's OWN "when this card is attacked" Trigger
        (Blast Sphere — equip itself to the attacking monster) on a fresh Chain, BEFORE
        damage calculation. ``by=OPPONENT`` since the attacker belongs to the source's
        opponent. Guarded on the target still being a monster on the field and its
        monster effects not negated; the event carries the attacker so the effect can
        equip onto it. The caller re-checks the target afterward: if the effect removed
        it from the monster zone, the attack fizzles."""
        s = self.state
        if self.result is not None:
            return
        inst = s.cards.get(target_iid)
        if inst is None or inst.zone is not Zone.MONSTER:
            return
        if s.monster_effects_negated(target_iid):
            return
        effect = next(self._trigger_effects(inst.card, kind="attacked", by=OPPONENT), None)
        if effect is None:
            return
        if effect.condition is not None and not effect.condition(s, inst.controller):
            return
        self._trigger_effect(
            target_iid, effect, inst.controller,
            {"attacker": attacker_iid, "target": target_iid},
        )

    def _switch_attacker_to_defense_after_attack(self, attacker_iid: int) -> None:
        """A monster carrying a ``DefenseAfterAttack`` rider (Spear Dragon, the Goblin
        Attack Force family) is changed to Defense Position once its attack resolves. A
        ``lock_position`` rider also freezes it there through its controller's next turn
        (turn_count + 2). No-op if it left the field or was flipped face-down in battle."""
        s = self.state
        inst = s.cards.get(attacker_iid)
        if inst is None or inst.zone is not Zone.MONSTER or inst.position is not Position.FACE_UP_ATTACK:
            return
        mod = next((m for m in inst.card.continuous if isinstance(m, DefenseAfterAttack)), None)
        if mod is None:
            return
        inst.position = Position.FACE_UP_DEFENSE
        inst.position_changed_this_turn = True  # spent its position change for the turn
        if mod.lock_position:
            inst.position_locked_until = s.turn_count + 2  # through its controller's next turn
        self.log(f"  {inst.name} switches to Defense Position after attacking")
        self._changed()

    def _trigger_effect(self, source_iid: int, effect, controller: int, event: dict | None = None):
        """Put a triggered/flip monster effect onto a fresh Chain and resolve it.

        If the effect targets, the controller chooses (human via a prompt, bot via
        heuristic). With no legal target the effect simply doesn't activate.
        """
        s = self.state
        targets: tuple[int, ...] = ()
        if effect.target is not None:
            candidates = target_candidates(s, controller, effect.target)
            required = 1 if effect.target.up_to else effect.target.count
            if len(candidates) < required:
                return
            targets = tuple(
                self.agents[controller].choose_targets(s, source_iid, effect.target, candidates)
            )
        self.log(f"  {s.players[controller].name}'s {s.inst(source_iid).name} effect activates")
        self._run_chain([ChainLink(source_iid, effect, controller, targets, event)])

    def _cleanup_equips(self) -> None:
        """Destroy Equip cards whose equipped monster is no longer on the field."""
        s = self.state
        for player in s.players:
            for sid in list(player.spell_trap_zones):
                if sid is None:
                    continue
                equip = s.inst(sid)
                if equip.equipped_to is None:
                    continue
                monster = s.cards.get(equip.equipped_to)
                if monster is None or monster.zone is not Zone.MONSTER:
                    s.send_to_graveyard(sid)

    def _cleanup_linked(self) -> None:
        """Enforce Call-of-the-Haunted bonds: if either partner has left the field,
        the other is destroyed too. The link is recorded on both cards, so this is
        direction-agnostic (trap destroyed -> monster dies; monster dies -> trap goes)."""
        s = self.state
        for inst in list(s.cards.values()):
            if inst.linked_to is None or inst.zone not in (Zone.MONSTER, Zone.SPELL_TRAP):
                continue  # not bonded, or already gone (cleaned up via its partner)
            partner = s.cards.get(inst.linked_to)
            if partner is None or partner.zone not in (Zone.MONSTER, Zone.SPELL_TRAP):
                s.send_to_graveyard(inst.iid)

    def _cleanup_control(self) -> None:
        """Snatch Steal: when the control-granting Equip leaves the field (or is no
        longer attached), control of the monster returns to its owner."""
        s = self.state
        for inst in list(s.cards.values()):
            eid = inst.control_equip_iid
            if eid is None or inst.zone is not Zone.MONSTER:
                continue
            equip = s.cards.get(eid)
            if equip is None or equip.zone is not Zone.SPELL_TRAP or equip.equipped_to != inst.iid:
                self._return_control(inst)

    def _cleanup_toons(self) -> None:
        """Destroy a player's Toon monsters once they no longer control a face-up
        Toon World (Slice 17)."""
        s = self.state
        for pl in (0, 1):
            if controls_toon_world(s, pl):
                continue
            for iid in list(s.players[pl].monster_zones):
                if iid is not None and s.cards[iid].card.is_toon:
                    self.log(f"  {s.cards[iid].name} is destroyed (no Toon World)")
                    s.send_to_graveyard(iid)

    def _return_control(self, monster) -> None:
        """Hand a monster back to its original controller; if their field is full it
        can't return and is sent to the Graveyard."""
        s = self.state
        original = monster.control_reverts_to
        monster.control_reverts_to = None
        monster.control_until_end_of_turn = None
        monster.control_equip_iid = None
        if original is None:
            return
        index = s.first_empty_monster_zone(original)
        if index is None:
            self.log(f"  {monster.name} can't return to {s.players[original].name} — to the Graveyard")
            s.send_to_graveyard(monster.iid)
        else:
            s.move_control(monster.iid, original, index)
            self.log(f"  {monster.name} returns to {s.players[original].name}")

    def _place_spell_counters(self) -> None:
        """A Spell resolved: every face-up card with a SpellCounterHolder gains 1
        Spell Counter, up to its max (0 = no limit)."""
        s = self.state
        bumped = False
        for inst, holder in s.active_markers(SpellCounterHolder):
            if not holder.accumulates:
                continue  # Breaker only gets its summon counter — never accrues more
            current = inst.counters.get("spell", 0)
            if holder.max_counters and current >= holder.max_counters:
                continue
            inst.counters["spell"] = current + 1
            bumped = True
        if bumped:
            self._changed()

    def _wipe_spell_counters_after_battle(self) -> None:
        """End of the Battle Phase: a monster that battled and whose SpellCounterHolder
        says so loses all its Spell Counters (Mythical Beast Cerberus)."""
        s = self.state
        for inst, holder in s.active_markers(SpellCounterHolder, (s.turn_player,)):
            if holder.wipe_after_battle and inst.attacked_this_turn and inst.counters.get("spell"):
                inst.counters["spell"] = 0
                self._changed()

    def _reconcile_field(self) -> None:
        """Destroy orphaned Equips and broken Call-of-the-Haunted bonds, return loaned
        monsters, and clear Toons with no Toon World — run after any card leaves play."""
        self._cleanup_equips()
        self._cleanup_linked()
        self._cleanup_control()
        self._cleanup_toons()

    def _check_field_to_gy_triggers(self) -> None:
        """Reconcile the board, then drain the two post-event queues: "sent from field to
        GY" / "destroyed by battle" effects (Sangan, Mystic Tomato), and Special Summons
        (the opponent's response window + the monster's own "when Special Summoned"
        Trigger). One guarded loop so a trigger that itself sends/summons is drained too —
        e.g. a recruiter (a GY trigger) Special Summons a monster the opponent may then
        respond to with Bottomless Trap Hole."""
        self._reconcile_field()
        if self._processing_gy:
            return  # a nested resolution; the outer loop will drain the queues
        self._processing_gy = True
        try:
            s = self.state
            while (s.gy_from_field or s.summon_events) and self.result is None:
                if s.gy_from_field:
                    iid = s.gy_from_field.pop(0)
                    inst = s.cards.get(iid)
                    if inst is not None:
                        effect = self._find_gy_trigger(inst)
                        if effect is not None:
                            self._trigger_effect(iid, effect, inst.controller)
                else:
                    self._fire_summon_event(*s.summon_events.pop(0))
                # That resolution may have broken more bonds / orphaned more Equips.
                self._reconcile_field()
        finally:
            self._processing_gy = False

    def _fire_summon_event(self, iid: int, summoner: int, kind: str = "special") -> None:
        """For a monster just Summoned (any kind): let the opponent respond — Torrential
        Tribute to any Summon, Bottomless Trap Hole / Black Horn of Heaven to a Special
        Summon, Trap Hole to a Normal/Flip Summon — then fire the monster's own "when
        Summoned" Trigger; a Flip Summon also resolves its Flip Effect. Each step is
        guarded on the monster still being face-up (a negated/removed Summon does none)."""
        inst = self.state.cards.get(iid)
        if inst is None or inst.zone is not Zone.MONSTER or not inst.is_face_up:
            return
        self._response_window(
            {"kind": "summon", "player": summoner, "monster": iid, "summon_kind": kind}
        )
        if kind == "flip":
            self._trigger_flip_effect(iid)  # e.g. Man-Eater Bug
        self._trigger_summon_effect(iid, kind)

    @classmethod
    def _find_gy_trigger(cls, inst):
        """The card's "sent from field to GY" trigger effect (a battle-only one fires
        only on a battle death), or None."""
        return next(
            (
                e
                for e in cls._trigger_effects(inst.card)
                if e.trigger.kind == "sent_to_gy_from_field"
                or (e.trigger.kind == "destroyed_by_battle" and inst.died_by_battle)
            ),
            None,
        )

    def _revert_end_of_turn_control(self, tp: int) -> None:
        """Change of Heart: temporary control loans taken this turn end now."""
        s = self.state
        reverted = False
        for inst in list(s.cards.values()):
            if inst.control_until_end_of_turn == s.turn_count and inst.zone is Zone.MONSTER:
                self._return_control(inst)
                reverted = True
        if reverted:
            self._changed()
            self._check_field_to_gy_triggers()

    def _return_spirits(self, tp: int) -> None:
        """Spirit monsters return to their owner's hand during the End Phase of the
        turn they were Normal/Flip Summoned or flipped face-up. A face-up Spirit
        never persists past an End Phase, so bouncing every face-up Spirit on the
        field here is exactly the rule (both sides, in case one was flipped in
        battle on the opponent's turn)."""
        s = self.state
        bounced = False
        for pl in (s.turn_player, s.opponent_of(s.turn_player)):
            for iid in list(s.players[pl].monster_zones):
                inst = s.cards.get(iid) if iid is not None else None
                if inst is not None and inst.is_face_up and inst.card.is_spirit:
                    self.log(f"  {inst.name} returns to {s.players[inst.owner].name}'s hand (Spirit)")
                    s.return_to_hand(iid)
                    bounced = True
        if bounced:
            self._changed()
            self._check_field_to_gy_triggers()  # orphaned Equips on the bounced Spirit

    def _destroy_end_phase_marked(self) -> None:
        """Destroy every monster marked to die in this turn's End Phase (Limiter Removal
        destroys the Machines it doubled). The mark stores the turn it was set on, so it
        only fires in that same turn's End Phase."""
        s = self.state
        victims = [
            iid
            for iid, inst in s.cards.items()
            if inst.zone is Zone.MONSTER and inst.destroy_at_end_phase == s.turn_count
        ]
        if not victims:
            return
        for iid in victims:
            self.log(f"  {s.inst(iid).name} is destroyed (End Phase)")
            s.send_to_graveyard(iid)
        self._changed()
        self._check_field_to_gy_triggers()

    def _apply_end_phase_summon_sweep(self) -> None:
        """Infinite Dismissal: while a face-up card carrying an ``EndPhaseSummonSweep``
        floodgate is on the field, every monster Normal/Flip Summoned this turn (face-up,
        summoned this turn, not Special Summoned) of Level <= the floodgate's cap is
        destroyed during the End Phase — both players'. A negated floodgate (Royal Decree)
        is skipped."""
        s = self.state
        caps = [
            m.max_level
            for pl in (0, 1)
            for iid in s.field_cards(pl, face_up_only=True)
            if not s.effect_negated(iid)
            for m in s.inst(iid).card.continuous
            if isinstance(m, EndPhaseSummonSweep)
        ]
        if not caps:
            return
        cap = max(caps)
        victims = [
            iid
            for pl in (0, 1)
            for iid in s.players[pl].monster_zones
            if iid is not None
            and s.inst(iid).is_face_up
            and s.inst(iid).summoned_this_turn
            and not s.inst(iid).was_special_summoned
            and (s.inst(iid).card.level or 0) <= cap
        ]
        if not victims:
            return
        for iid in victims:
            self.log(f"  {s.inst(iid).name} is destroyed (Infinite Dismissal)")
            s.send_to_graveyard(iid)
        self._changed()
        self._check_field_to_gy_triggers()

    def _clear_temp_stats(self) -> None:
        """Wipe every monster's 'until the end of this turn' ATK/DEF deltas."""
        s = self.state
        for inst in s.cards.values():
            if inst.temp_atk or inst.temp_def:
                inst.temp_atk = 0
                inst.temp_def = 0

    def _end_phase(self, tp: int) -> None:
        self._revert_end_of_turn_control(tp)
        if self.result is None:
            self._fire_end_phase_triggers(tp)
        if self.result is None:
            self._return_spirits(tp)
        if self.result is None:
            self._destroy_end_phase_marked()
        if self.result is None:
            self._apply_end_phase_summon_sweep()
        if self.result is None:
            s = self.state
            for _ in range(_MAX_ACTIONS_PER_PHASE):
                menu = legal_actions(s, tp)  # discards only, no Pass while over the limit
                if not menu:
                    break
                choice = self.agents[tp].decide(s, menu)
                self.log(f"  {s.players[tp].name} {apply(s, choice)} (hand-size limit)")
                self._changed()
        self._clear_temp_stats()  # combat tricks wear off at the turn's end

    # ------------------------------------------------------------------ #
    def _check_life_points(self) -> None:
        s = self.state
        for p in (0, 1):
            if s.players[p].life_points <= 0:
                self.result = DuelResult(s.opponent_of(p), f"{s.players[p].name} reached 0 LP")
                return

    def _check_exodia(self) -> None:
        """End the Duel if a player has assembled all five Forbidden One pieces in hand.
        Called after any hand change (a draw, a card added to hand by an effect)."""
        if self.result is not None:
            return
        winner = self.state.exodia_winner()
        if winner is not None:
            self.result = DuelResult(winner, f"{self.state.players[winner].name} assembled Exodia")
