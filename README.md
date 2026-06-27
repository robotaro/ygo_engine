# ygo_engine

A from-scratch **Yu-Gi-Oh! rules engine** for the version 6.0 era (Worldwide
Edition / *Stairway to the Destined Duel*), built as a personal toy — and as an
experiment in whether card games this complex really need their rules
"hard-coded".

They don't. The trick is one clean seam between two very different things:

1. **The universal machinery** (finite, written once): the turn/phase state
   machine, summoning, the battle/damage step, **the Chain + spell-speed +
   priority**, zone movement, win conditions. The rulebook fully specifies all
   of it and it never grows when you add cards.
2. **The cards** (open-ended, expressed as *data*): each card is a list of
   effect definitions — `{ timing, spell_speed, condition, cost, target, actions }`
   — composed from a small fixed library of primitive verbs (destroy, send to
   graveyard, draw, special summon, tribute, modify ATK/DEF, negate, …). Adding
   a card is adding data, not branching the engine.

This is the architecture proven by EDOPro / `ygopro-core` (a core + one small
script per card, ~13k cards). We're building a clean, modern, *small* version of
it. The historically painful part — authoring thousands of card scripts — is now
something an LLM can generate from the card text, reviewed by a human.

## Why this shape

The engine core is a **pure, deterministic `(state, action) -> state'`** with no
UI dependency. That single property gives us, for free:

- save / load and **replays**
- seeded reproducibility
- **network play** (state + decisions over the wire)
- **bot self-play** — the same "answer a decision request" interface serves
  humans and AI/ML agents alike

## Layout

```
ygo_engine/
├── assets/      card database (CSV), deck blueprints, card images, rulebook PDF
├── engine/      Python: the headless rules engine (+ FastAPI/WS server, later)
│   └── src/ygo/ enums · cards · state · decks · setup · render · …
├── web/         Svelte board with drag-and-drop  (Milestone 1.5)
└── legacy/      the original prototype, kept for reference
```

## Running

```bash
cd engine
uv sync --extra dev
uv run python -m ygo.demo     # load decks, deal, print the board
uv run pytest -q              # foundation tests
```

## Roadmap

- **M1 — the kernel (vanilla only).** Turn/phase FSM, normal summon / set /
  position change, the Battle Phase + damage step, win conditions. Two vanilla
  decks fight a full, correct duel headless, driven by a random bot. *(in progress)*
- **M1.5 — see it.** FastAPI + WebSocket bridge; Svelte board that renders the
  `GameState` and lets you drag cards onto zones.
- **M2 — effects.** The declarative effect DSL + primitive library + the Chain;
  card scripts generated from the card text and reviewed.
- **M3 — bots.** A clean agent interface; random → heuristic → learned.

Fidelity: v6.0 baseline, but effects follow **current rulings / errata** (modern
Problem-Solving Card Text maps to code far more cleanly than the 2006 wording).
