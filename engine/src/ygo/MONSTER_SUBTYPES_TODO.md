# TODO — monster sub-types in the v6.0 pool (note for the effects/features work)

The new v6.0 card pool (`assets/card_databases/card_db_ocg_pre_synchro_v6.csv`,
3,117 cards, built by `scripts/build_card_db.py`) contains monster sub-types that
the engine does **not** model yet. `MonsterCategory` only has
`NORMAL / EFFECT / FUSION / RITUAL / TOKEN`, so the converter currently
**flattens every special sub-type into `EFFECT`**. The behaviour is lost — only
the "this is an effect monster" bit survives.

Counts now sitting in the pool as plain `Effect` monsters:

| Sub-type | Count | Rule that needs modelling |
|---|---:|---|
| **Flip**   | 92 | Effect triggers when flipped face-up. *Partly here already* — `card_effects.py` uses `timing="flip"` (Man-Eater Bug, Magician of Faith). |
| **Gemini** ("Dual") | 18 | Acts as a vanilla Normal Monster until a 2nd Normal Summon ("Gemini Summon") unlocks its effect. |
| **Union**  | 18 | Can equip *itself* to another monster (and unequip back). Not Fusion-related. |
| **Spirit** | 12 | Returns to the hand during the End Phase it's summoned/flipped; cannot be Special Summoned. |
| **Toon**   |  9 | Toon-specific summon/attack rules (needs Toon World, can attack directly, etc.). |

(Also in the pool and already modelled by category: 137 Fusion, 26 Ritual.)

## Suggested direction
1. Add the sub-types so the engine can *recognise* them — either new
   `MonsterCategory` members (`FLIP`, `SPIRIT`, `UNION`, `GEMINI`, `TOON`) or a
   separate tag set on `CardDef`. If you add categories, update
   `build_card_db.py:TYPE_CATEGORIES` to emit them instead of folding to `Effect`,
   and `cards.py:_CATEGORY_WORDS` will pick them up automatically.
2. Then author the behaviours in `card_effects.py` / `effects.py` as new slices,
   the same way the current effects are built.

## Gotcha when switching the engine to this pool
This CSV uses **YGOPRODeck canonical names**, which differ in capitalisation from
the legacy "Stairway" CSV. e.g. legacy `"Call Of The Haunted"` is
`"Call of the Haunted"` here. `EFFECTS`/`CONTINUOUS`/`FUSIONS` keys must match the
**active pool's** spelling, so re-key those dicts if `paths.DEFAULT_CARD_DB` is
pointed at `card_db_ocg_pre_synchro_v6.csv`.
