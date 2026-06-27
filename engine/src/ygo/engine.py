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
from .enums import Phase, TURN_PHASES
from .moves import (
    ActivateSpell,
    Pass,
    apply,
    legal_actions,
    place_activated_spell,
    resolve_card_effects,
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
                self._activate_spell(choice, tp)
            else:
                self.log(f"  {s.players[tp].name} {apply(s, choice)}")
                self._check_life_points()
                self._changed()

    def _activate_spell(self, action: ActivateSpell, tp: int) -> None:
        """Activate a Spell as watchable steps: place -> (pause) -> resolve -> (pause) -> GY."""
        s = self.state
        card = s.inst(action.iid).card
        place_activated_spell(s, action.iid, action.zone_index)
        self.log(f"  {s.players[tp].name} activates {card.name}")
        self._changed()
        self._pace()
        resolve_card_effects(s, action.iid, action.targets)
        self._check_life_points()
        self._changed()
        self._pace()
        s.send_to_graveyard(action.iid)
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
            self.log(f"  {s.players[tp].name}: {apply(s, choice)}")
            self._check_life_points()
            self._changed()

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
