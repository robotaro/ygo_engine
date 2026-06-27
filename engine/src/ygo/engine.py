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
    legal_actions,
    response_options,
    resolve_effect,
    reveal_for_activation,
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
            pass  # nothing happens for vanilla play
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
        self._changed()

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
        effect = next((e for e in card.effects if e.timing in ("ignition", "quick")), card.effects[0])
        reveal_for_activation(s, action.iid, action.zone_index)
        self.log(f"  {s.players[controller].name} activates {card.name}")
        self._run_chain([ChainLink(action.iid, effect, controller, tuple(action.targets), None)])

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
        reveal_for_activation(s, chosen.iid, chosen.zone_index)
        self.log(f"  {s.players[player].name} activates {card.name}")
        return ChainLink(chosen.iid, card.effects[0], player, tuple(chosen.targets), event)

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

    def _check_field_to_gy_triggers(self) -> None:
        """Fire "when sent from the field to the Graveyard" effects (e.g. Sangan)."""
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
        finally:
            self._processing_gy = False

    def _end_phase(self, tp: int) -> None:
        s = self.state
        for _ in range(_MAX_ACTIONS_PER_PHASE):
            menu = legal_actions(s, tp)  # discards only, no Pass while over the limit
            if not menu:
                return
            choice = self.agents[tp].decide(s, menu)
            self.log(f"  {s.players[tp].name} {apply(s, choice)} (hand-size limit)")
            self._changed()

    # ------------------------------------------------------------------ #
    def _check_life_points(self) -> None:
        s = self.state
        for p in (0, 1):
            if s.players[p].life_points <= 0:
                self.result = DuelResult(s.opponent_of(p), f"{s.players[p].name} reached 0 LP")
                return
