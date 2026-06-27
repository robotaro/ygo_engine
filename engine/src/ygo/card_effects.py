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
    DestroyAllMonsters,
    DestroyLowestAtkOpponentMonster,
    Draw,
    Effect,
    InflictDamage,
    SwitchTargetsToAttack,
    TargetSpec,
)


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
}
