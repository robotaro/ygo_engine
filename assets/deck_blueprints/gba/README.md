# GBA Yu-Gi-Oh! dataset — enemy decks, booster packs, and images

Everything extracted from the **8 Game Boy Advance Yu-Gi-Oh! card-battle games**
(all pre-Synchro, 2002–2006, so fully compatible with the engine's v6.0 rules and
the 3,117-card v6.0 pool). Sourced from the **Yu-Gi-Oh! Fandom wiki** via the
MediaWiki API (`{{Decklist}}` / `(XXX-BP)` set pages / `imageinfo` + `pageimages`).

## What's here

| Game | Enemy decks | Card packs | Filter packs | Pack art | 
|---|---:|---:|---:|---:|
| The Eternal Duelist Soul (2002) | 16 | 23 | – | 23 |
| Worldwide Edition: Stairway to the Destined Duel (2003) | 16 | 29 | 4 | 21 |
| The Sacred Cards (2003) | 17 | — (RPG) | — | — |
| Reshef of Destruction (2004) | 28 | — (RPG) | — | — |
| World Championship Tournament 2004 (2004) | 28 | 19 | 5 | – |
| 7 Trials to Glory: WCT 2005 (2005) | 16 | 20 | 13 | – |
| Ultimate Masters: WCT 2006 (2006) | 25 | 5 | 46 | 2 |
| GX Duel Academy (2006) | 8 | 47 | 1 | – |
| **Total** | **154** | **143** | **69** | **46** |

Plus **62 opponent portraits** (one per unique opponent).

## Layout

```
deck_blueprints/gba/
  <game>/*.txt        enemy decks — "<count> Card Name", loadable by ygo.decks.load_decklist
  _portraits/*.webp   opponent portraits (filename = opponent slug)
  INDEX.md            per-game deck listing
  _MISMATCHES.md      deck cards not in the v6.0 pool
card_packs/gba/
  <game>/*.txt        booster packs — "# metadata" header then card names by "## Rarity"
  _images/<game>/*    booster-pack box art (filename = pack slug)
  INDEX.md            per-game pack listing
  _MISMATCHES.md      pack cards not in the v6.0 pool
```

## Formats
- **Decks**: comment lines (`//`), then `<count> <Card Name>`. A `#EXTRA DECK` line
  separates Fusion-type cards (the loader also auto-routes by card type). Directly
  loadable; cards not in the pool report as missing.
- **Packs**: `# metadata` header (cards/pack, price, unlock), card names grouped by
  `## Rarity`. **Filter/random packs** ("All Effect Monsters", "Dorothy's Gift") have
  no fixed list — the file records the rule instead.
- **Images**: WebP. Filenames are the opponent/pack slug, so they pair with the `.txt`.

## Coverage & caveats (read me)
- **Card resolution**: ~98% of all card names resolve to the v6.0 pool. The rest are
  kept in the lists and flagged in the two `_MISMATCHES.md`. They're mostly the
  **Egyptian God** cards (Slifer/Obelisk/Ra, used by story bosses) and a set of very
  old or game-exclusive cards your pool doesn't include (e.g. Trakadon, Mechanical
  Spider, Makiu) — useful as a "what my pool is missing vs. these games" list.
- **Sacred Cards & Reshef** are RPGs: no booster packs (cards are won through the
  story), so they have no `card_packs/` folder.
- **Undocumented opponents**: only opponents the wiki documents are included. Several
  minor EDS/Worldwide duelists (Espa Roba, Mako, Duel Computer, Ryou Bakura…) only
  have their **WCT2004** deck documented, not their other-game decks. **GX Duel
  Academy** documents only the 8 named cast; its generic students' decks exist only on
  GameFAQs, which blocks automated access.
- **Missing art**: ~31 Worldwide/EDS pack-art links are broken on the wiki; WCT2004/2005
  and GX packs have no box art; the WCT2006 "Duel Monster" opponents (Kuriboh, Des Frog)
  and a couple of others have no portrait.

## Regenerating
Built by standalone Python scripts (Fandom MediaWiki API → parse → resolve → write).
The scripts are not committed; ask and they can be added to `engine/scripts/`.
These images (~5 MB) are checked in; they can be `.gitignore`d like
`assets/card_images/` if you'd rather keep them out of git.
