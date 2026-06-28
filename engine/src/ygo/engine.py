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
from .effects import DrawTrigger, StandbyUpkeep
from .enums import Phase, Position, TURN_PHASES, Zone
from .moves import (
    ActivateSpell,
    ChainLink,
    DeclareAttack,
    FlipSummon,
    NormalSummon,
    Pass,
    SetSpellTrap,
    apply,
    can_ritual_summon,
    controls_toon_world,
    legal_actions,
    makeable_fusions,
    pay_discard_cost,
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
        for iid in s.players[tp].monster_zones:
            if iid is None:
                continue
            inst = s.inst(iid)
            inst.summoned_this_turn = False
            inst.attacked_this_turn = False
            inst.position_changed_this_turn = False

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
        self._changed()

    def _faceup_cards(self, player: int) -> list[int]:
        """A player's own face-up cards (Field + Spell/Trap + Monster zones),
        snapshotted so destroying one mid-iteration is safe."""
        s = self.state
        p = s.players[player]
        return [
            iid
            for iid in [p.field_zone, *p.spell_trap_zones, *p.monster_zones]
            if iid is not None and s.cards[iid].is_face_up
        ]

    def _process_draw_triggers(self) -> None:
        """Solemn Wishes: pay each queued draw out to its drawer's face-up cards."""
        s = self.state
        while s.pending_draws:
            player = s.pending_draws.pop(0)
            for iid in self._faceup_cards(player):
                inst = s.cards.get(iid)
                if inst is None or not inst.effects_active:
                    continue  # a Gemini not yet Gemini Summoned has no live effect
                for mod in inst.card.continuous:
                    if isinstance(mod, DrawTrigger) and mod.gain_life:
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
            for mod in inst.card.continuous:
                if isinstance(mod, StandbyUpkeep) and self._apply_standby_upkeep(inst, mod, tp):
                    fired = True
        if fired:
            self._check_life_points()
            self._check_field_to_gy_triggers()
            self._changed()

    def _standby_upkeep_order(self) -> list[int]:
        """Face-up cards that might carry a Standby upkeep, in a stable order
        (turn player first), snapshotted so destroying one mid-phase is safe."""
        s = self.state
        order: list[int] = []
        for pl in (s.turn_player, s.opponent_of(s.turn_player)):
            order.extend(self._faceup_cards(pl))
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
            elif isinstance(choice, NormalSummon):
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._changed()
                self._check_field_to_gy_triggers()  # a Tribute may send a trigger monster
                # The opponent may respond to the Summon (e.g. Trap Hole).
                self._response_window({"kind": "summon", "player": tp, "monster": choice.iid})
                self._check_life_points()
            elif isinstance(choice, FlipSummon):
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._changed()
                self._trigger_flip_effect(choice.iid)  # e.g. Man-Eater Bug
                self._check_life_points()
            else:
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._check_life_points()
                self._changed()

    def _battle_phase(self, tp: int) -> None:
        s = self.state
        if s.turn_count == 1:  # the player going first gets no Battle Phase
            return
        for _ in range(_MAX_ACTIONS_PER_PHASE):
            if self.result is not None:
                return
            menu = legal_actions(s, tp) + [Pass()]
            choice = self.agents[tp].decide(s, menu)
            if isinstance(choice, Pass):
                return
            if isinstance(choice, DeclareAttack):
                self._declare_attack(choice, tp)
            else:
                self.log(f"  {s.players[tp].name}: {apply(s, choice)}")
                self._check_life_points()
                self._changed()

    def _declare_attack(self, action: DeclareAttack, tp: int) -> None:
        """Declare an attack, open a response window, then resolve it if still valid."""
        s = self.state
        attacker, target = action.attacker, action.target
        s.attack_negated = False
        s.inst(attacker).attacked_this_turn = True
        self.log(f"  {s.players[tp].name} declares an attack with {s.inst(attacker).name}")
        self._changed()

        self._response_window(
            {"kind": "attack_declared", "player": tp, "attacker": attacker, "target": target}
        )
        if self.result is not None:
            return

        if s.attack_negated:
            self.log("  the attack is negated")
            self._changed()
            return
        atk = s.cards.get(attacker)
        if atk is None or atk.zone is not Zone.MONSTER or atk.position is not Position.FACE_UP_ATTACK:
            self.log("  the attacker is no longer able to attack")
            self._changed()
            return
        if target is not None and target not in s.cards:
            self._changed()  # the target left the field; the attack fizzles
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
        self._pay_activation_cost(action.iid, controller, effect)
        self._run_chain([ChainLink(action.iid, effect, controller, tuple(action.targets), None)])

    def _pay_activation_cost(self, source_iid: int, controller: int, effect) -> None:
        """Pay an effect's activation cost (currently the discard cost) — the player
        chooses the fodder (bot via heuristic, human via a prompt), then it's sent to
        the Graveyard before the effect resolves."""
        need = getattr(effect, "discard_cost", 0)
        if not need:
            return
        s = self.state
        fodder = [i for i in s.players[controller].hand if i != source_iid]
        chosen = self.agents[controller].choose_discards(s, controller, fodder, need)
        if len(set(chosen)) != need or any(c not in fodder for c in chosen):
            chosen = Agent().choose_discards(s, controller, fodder, need)  # safe default
        discarded = pay_discard_cost(s, controller, source_iid, need, chosen)
        names = ", ".join(s.inst(i).name for i in discarded)
        self.log(f"  {s.players[controller].name} discards {names} (cost)")
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

        names = " + ".join(s.inst(m).name for m in materials)
        for m in materials:
            s.send_to_graveyard(m)
        index = s.first_empty_monster_zone(controller)
        s.place_monster(chosen, controller, index, Position.FACE_UP_ATTACK)
        s.inst(chosen).summoned_this_turn = True
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
        index = s.first_empty_monster_zone(controller)
        if index is None:
            s.send_to_graveyard(spell_iid)  # no room (shouldn't happen) — fizzle
            return
        s.place_monster(monster_iid, controller, index, Position.FACE_UP_ATTACK)
        s.inst(monster_iid).summoned_this_turn = True
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
            resolve_effect(s, link.effect, link.source_iid, link.targets, link.event)
            self._check_life_points()
            self._changed()
            self._pace()
        # Spent, non-permanent Spells/Traps go to the Graveyard.
        for link in s.chain:
            inst = s.cards.get(link.source_iid)
            if inst is not None and inst.zone is Zone.SPELL_TRAP and not inst.card.is_permanent:
                s.send_to_graveyard(link.source_iid)
        s.chain = []
        self._changed()
        self._check_field_to_gy_triggers()  # resolution may have sent trigger monsters to GY
        self._process_draw_triggers()  # resolution may have drawn cards (Pot of Greed)

    # ------------------------------------------------------------------ #
    #  Monster-effect triggers
    # ------------------------------------------------------------------ #
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

    def _trigger_effect(self, source_iid: int, effect, controller: int, event: dict | None = None):
        """Put a triggered/flip monster effect onto a fresh Chain and resolve it.

        If the effect targets, the controller chooses (human via a prompt, bot via
        heuristic). With no legal target the effect simply doesn't activate.
        """
        s = self.state
        targets: tuple[int, ...] = ()
        if effect.target is not None:
            candidates = target_candidates(s, controller, effect.target)
            if len(candidates) < effect.target.count:
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

    def _check_field_to_gy_triggers(self) -> None:
        """Reconcile the board after cards leave the field: destroy orphaned Equips
        and broken bonds, return loaned monsters, then fire "sent from field to GY"
        effects (Sangan)."""
        self._cleanup_equips()
        self._cleanup_linked()
        self._cleanup_control()
        self._cleanup_toons()
        if self._processing_gy:
            return  # a nested resolution; the outer loop will drain the queue
        self._processing_gy = True
        try:
            s = self.state
            while s.gy_from_field and self.result is None:
                iid = s.gy_from_field.pop(0)
                inst = s.cards.get(iid)
                if inst is None:
                    continue
                effect = next(
                    (
                        e
                        for e in inst.card.effects
                        if e.timing == "trigger"
                        and e.trigger is not None
                        and e.trigger.kind == "sent_to_gy_from_field"
                    ),
                    None,
                )
                if effect is not None:
                    self._trigger_effect(iid, effect, inst.controller)
                # That resolution may have broken more bonds / orphaned more Equips.
                self._cleanup_equips()
                self._cleanup_linked()
                self._cleanup_control()
                self._cleanup_toons()
        finally:
            self._processing_gy = False

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
            self._return_spirits(tp)
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
