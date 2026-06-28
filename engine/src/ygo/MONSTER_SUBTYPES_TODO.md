# Monster sub-types in the v6.0 pool — STATUS: implemented (Slices 13–17)

The v6.0 card pool (`assets/card_databases/card_db_ocg_pre_synchro_v6.csv`, 3,117
cards) contains five monster sub-types beyond `NORMAL/EFFECT/FUSION/RITUAL/TOKEN`.
The converter used to flatten them all into a plain `Effect` monster; they are now
**recognised and behaviour-modelled**. This file is kept as a map of where each
lives.

## Recognition (Slice 13)
`MonsterCategory` has `FLIP/SPIRIT/UNION/GEMINI/TOON`; `build_card_db.py`
(`TYPE_CATEGORIES`) emits each as a token alongside `Effect` (e.g.
`Aqua / Flip / Effect`), so a sub-type monster stays a non-vanilla effect monster.
`CardDef` exposes `is_flip / is_spirit / is_union / is_gemini / is_toon`.
`tests/test_card_pool.py` guards the counts (92 Flip, 12 Spirit, 18 Union,
18 Gemini, 9 Toon) and that each keeps its EFFECT tag.

## Behaviours
| Sub-type | Count | Slice | How it's modelled |
|---|---:|---|---|
| **Flip**   | 92 | (pre-existing) | `timing="flip"` effects (Man-Eater Bug, Magician of Faith); the category is now recognised too. |
| **Spirit** | 12 | 14 | `engine._return_spirits` bounces every face-up Spirit to the owner's hand at each End Phase; excluded from the revival pool (no Special Summon). Demo: Susa Soldier. `test_spirit.py`. |
| **Gemini** | 18 | 15 | `GeminiSummon` action (a 2nd Normal Summon) sets `gemini_unlocked`; `CardInstance.effects_active` gates the effect until then (and a `SelfStatMod` layer). Demo: Goggle Golem (1500→2100). `test_gemini.py`. |
| **Union**  | 18 | 16 | `UnionEquip` / `UnionUnequip` (once per turn via `union_acted_on_turn`); an equipped Union sits in a Spell/Trap zone and reuses the Equip layer + cleanup. `UnionMod` describes valid hosts. Demo: Y-Dragon Head → X-Head Cannon. `test_union.py`. |
| **Toon**   |  9 | 17 | Toon World (Continuous Spell, pay 1000) gates Toon summons (`controls_toon_world`); can't attack the turn summoned; direct attack unless the opponent has a Toon; `engine._cleanup_toons` destroys Toons when Toon World leaves. Demo: Toon Gemini Elf. `test_toon.py`. |

(Also already modelled by category: 137 Fusion, 26 Ritual.)

## Known per-card simplifications
- Only one representative card per sub-type carries an authored effect; other
  sub-type monsters get the framework behaviour but their individual effect text
  isn't authored yet (they behave as effect-less bodies of that sub-type).
- Union: the "destroy the Union instead of the host" battle protection isn't
  modelled, and an equipped Union occupies a Spell/Trap zone (real Unions don't).
- The GreedyAgent doesn't proactively activate Toon World / continuous enablers,
  so Toons (and Gemini/Union plays) are mainly exercised in browser play + tests.

## Naming gotcha (still relevant)
The CSV uses **YGOPRODeck canonical names** — author all `EFFECTS`/`CONTINUOUS`/
`FUSIONS`/`RITUALS` keys against those spellings (the pool guard test enforces it).
