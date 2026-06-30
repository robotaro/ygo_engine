"""FastAPI app: one duel per WebSocket, plus a small HTTP API for deck building.

Run (dev)::

    uv run uvicorn ygo.server.app:app --reload --port 8000

The Svelte dev server (web/) proxies ``/ws`` and ``/api`` here. If a production
build exists at ``web/dist`` it is served at ``/``.

HTTP API (all under ``/api``):
  * ``GET  /decks``           — catalogue of every blueprint (legality, playability)
  * ``GET  /cards``           — search the card pool (filters via query params)
  * ``POST /decks/validate``  — validate a deck given as ``{name, main, extra}``
  * ``POST /decks``           — save a deck blueprint under ``deck_blueprints/user/``

The WebSocket ``/ws`` accepts ``?deck=<id>&opp=<id>&seed=<n>`` so the human can
choose both decks; a deck *id* is its path relative to ``deck_blueprints/``.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import threading
import unicodedata
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..cards import CardDef, CardRegistry
from ..deckbuild import (
    MAX_COPIES,
    BanList,
    deck_playability,
    is_functional,
    list_banlists,
    load_banlist,
    save_banlist,
    search_pool,
    to_blueprint_text,
    validate_deck,
)
from ..decks import DeckList, load_decklist
from ..enums import Attribute, CardType
from ..packs import get_pack, list_packs, open_pack
from .. import pricing
from ..paths import ASSETS, DECKS_DIR, REPO_ROOT
from ..profile import STARTER_DECK_ID, Profile, load_profile, new_profile, save_profile
from .. import tournament as tour
from .session import GameSession

app = FastAPI(title="ygo_engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One shared, read-only registry for every request (the CSV is ~3,100 rows).
REGISTRY = CardRegistry.load_csv()

# Sensible defaults if the client doesn't pick decks.
DECK_A = DECKS_DIR / "vanilla" / "slice1_alpha.txt"
DECK_B = DECKS_DIR / "vanilla" / "slice1_beta.txt"

# Every duel played here is recorded for later replay (override with $YGO_RECORD_DIR).
RECORD_DIR = Path(os.environ.get("YGO_RECORD_DIR", REPO_ROOT / "replays"))


# --------------------------------------------------------------------------- #
#  Serialisation helpers (pure; unit-tested without HTTP)
# --------------------------------------------------------------------------- #
def card_to_dict(card: CardDef) -> dict:
    price = pricing.price_detail(card, REGISTRY)
    return {
        "name": card.name,
        "cardType": card.card_type.value,
        "subtype": card.subtype.value if card.subtype else None,
        "attribute": card.attribute.value if card.attribute else None,
        "race": card.race,
        "level": card.level,
        "attack": card.attack,
        "defense": card.defense,
        "text": card.text,
        "imageId": card.image_id,
        "extraDeck": card.goes_in_extra_deck,
        "functional": is_functional(card),
        "rarity": price["rarity"],
        "value": price["value"],
        "buy": price["buy"],
        "sell": price["sell"],
    }


def resolve_deck_id(deck_id: str | None) -> Path | None:
    """Map a deck *id* (path relative to ``deck_blueprints/``) to a file, refusing
    anything that escapes the blueprints directory (no ``..`` traversal)."""
    if not deck_id:
        return None
    root = DECKS_DIR.resolve()
    candidate = (root / deck_id).resolve()
    if root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def resolve_banlist(format_id: str | None) -> BanList:
    """Resolve a ?format= id to a BanList; unknown/empty falls back to no restrictions."""
    try:
        return load_banlist(format_id)
    except (FileNotFoundError, ValueError):
        return load_banlist(None)


def deck_catalog(banlist: BanList | None = None) -> list[dict]:
    """Summarise every bundled blueprint: legality + how playable it is today."""
    out = []
    for path in sorted(DECKS_DIR.rglob("*.txt")):
        deck = load_decklist(path, REGISTRY)
        report = validate_deck(deck, banlist=banlist)
        play = deck_playability(deck)
        rel = path.relative_to(DECKS_DIR)
        out.append(
            {
                "id": rel.as_posix(),
                "name": deck.name,
                "source": rel.parts[0],
                "main": deck.main_size,
                "extra": deck.extra_size,
                "legal": report.is_legal,
                "playablePct": round(play.pct),
            }
        )
    return out


def decklist_from_counts(name: str, main: dict, extra: dict) -> DeckList:
    """Build a DeckList from ``{card_name: count}`` maps, tracking unknown names."""
    deck = DeckList(name=name or "Untitled")
    for counts in (main or {}, extra or {}):
        for card_name, n in counts.items():
            card = REGISTRY.get(card_name)
            if card is None:
                deck.missing.extend([card_name] * int(n))
                continue
            target = deck.extra if card.goes_in_extra_deck else deck.main
            target.extend([card] * int(n))
    return deck


def restricted_in_deck(deck: DeckList, banlist: BanList) -> list[dict]:
    """Per-card detail for every deck card the banlist restricts (for inline UI)."""
    counts = Counter(c.name for c in (*deck.main, *deck.extra))
    out = []
    for name, n in sorted(counts.items()):
        cap = banlist.limit_for(name)
        if cap < MAX_COPIES:
            out.append({"name": name, "cap": cap, "count": n, "ok": n <= cap})
    return out


def validation_dict(deck: DeckList, format_id: str | None = None) -> dict:
    banlist = resolve_banlist(format_id)
    report = validate_deck(deck, banlist=banlist)
    play = deck_playability(deck)
    return {
        "deckName": report.deck_name,
        "mainSize": report.main_size,
        "extraSize": report.extra_size,
        "legal": report.is_legal,
        "errors": [i.message for i in report.errors],
        "warnings": [i.message for i in report.warnings],
        "playablePct": round(play.pct),
        "nonfunctional": play.nonfunctional,
        "format": {"id": format_id or "none", "name": banlist.name},
        "restricted": restricted_in_deck(deck, banlist),
    }


# --------------------------------------------------------------------------- #
#  HTTP API
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/decks")
def list_decks(format: str | None = None) -> dict:
    return {"decks": deck_catalog(resolve_banlist(format) if format else None)}


@app.get("/api/formats")
def formats() -> dict:
    """Every selectable Forbidden/Limited list: bundled presets + custom lists."""
    return {"formats": list_banlists()}


@app.get("/api/banlist")
def get_banlist(id: str) -> dict:
    """Full per-card limits for one banlist, for the custom-list editor."""
    try:
        bl = load_banlist(id)
    except (FileNotFoundError, ValueError):
        return {"id": id, "name": "No Restrictions", "limits": {}}
    return {"id": id, "name": bl.name, "limits": dict(bl.limits)}


@app.post("/api/banlists")
def save_custom_banlist(payload: dict) -> dict:
    """Save a custom Forbidden/Limited list to assets/banlists/user/."""
    name = (payload.get("name") or "Custom List").strip()
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "custom"
    raw_limits = payload.get("limits") or {}
    # keep only real restrictions (0/1/2); 3 == unlimited, so drop it
    limits = {n: int(c) for n, c in raw_limits.items() if int(c) in (0, 1, 2)}
    path = save_banlist(BanList(name=name, limits=limits), slug)
    return {"id": path.relative_to(path.parents[1]).with_suffix("").as_posix(), "name": name, "restricted": len(limits)}


@app.get("/api/cards")
def cards(
    query: str | None = None,
    type: str | None = None,
    attribute: str | None = None,
    functional: bool = False,
    sort: str = "name",
    order: str = "asc",
    limit: int = 120,
) -> dict:
    card_type = {"monster": CardType.MONSTER, "spell": CardType.SPELL, "trap": CardType.TRAP}.get(
        (type or "").lower()
    )
    attr = None
    if attribute and attribute.upper() in Attribute.__members__:
        attr = Attribute[attribute.upper()]
    if sort not in ("name", "attack", "defense", "type"):
        sort = "name"
    order = "desc" if str(order).lower() == "desc" else "asc"
    hits = search_pool(
        REGISTRY,
        text=query or None,
        card_type=card_type,
        attribute=attr,
        functional_only=functional,
        sort=sort,
        order=order,
        limit=max(1, min(limit, 5000)),
    )
    return {"count": len(hits), "cards": [card_to_dict(c) for c in hits]}


# --------------------------------------------------------------------------- #
#  Opponent roster (the 154 GBA enemy decks, with portraits)
# --------------------------------------------------------------------------- #
GBA_DIR = DECKS_DIR / "gba"
PORTRAIT_DIR = GBA_DIR / "_portraits"
GAME_TITLES = {
    "eternal_duelist_soul": "The Eternal Duelist Soul",
    "worldwide_edition": "Worldwide Edition",
    "sacred_cards": "The Sacred Cards",
    "reshef_of_destruction": "Reshef of Destruction",
    "wct_2004": "WCT 2004",
    "wct_2005": "WCT 2005: 7 Trials to Glory",
    "wct_2006": "WCT 2006: Ultimate Masters",
    "gx_duel_academy": "GX Duel Academy",
}
GAME_ORDER = [
    "eternal_duelist_soul",
    "worldwide_edition",
    "sacred_cards",
    "reshef_of_destruction",
    "wct_2004",
    "wct_2005",
    "wct_2006",
    "gx_duel_academy",
]
# Duelists whose portrait file isn't just a slug of their name.
PORTRAIT_ALIASES = {"keith howard": "bandit_keith"}


def _slug(text: str) -> str:
    """Lowercase ascii slug (strips accents: 'Téa' -> 'tea')."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def portrait_url(name: str) -> str | None:
    key = PORTRAIT_ALIASES.get(name.strip().lower(), _slug(name))
    return f"/portraits/{key}.png" if (PORTRAIT_DIR / f"{key}.png").is_file() else None


def _gba_index() -> dict[str, tuple[str, str]]:
    """Map ``<game>/<file>.txt`` -> (clean duelist name, deck variant)."""
    path = GBA_DIR / "_index.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, str]] = {}
    for game, rows in data.items():
        for name, variant, _main, _extra, fn in rows:
            out[f"{game}/{fn}"] = (name, variant or "")
    return out


def opponent_roster(banlist: BanList | None = None) -> list[dict]:
    """Every GBA enemy deck, grouped by game, with portraits + legality."""
    index = _gba_index()
    by_game: dict[str, list[dict]] = {}
    for path in sorted(GBA_DIR.rglob("*.txt")):
        rel = path.relative_to(DECKS_DIR)  # gba/<game>/<file>.txt
        if len(rel.parts) < 3:
            continue
        game = rel.parts[1]
        deck = load_decklist(path, REGISTRY)
        name, variant = index.get(f"{game}/{path.name}", (path.stem.replace("_", " ").title(), ""))
        by_game.setdefault(game, []).append(
            {
                "id": rel.as_posix(),
                "name": name,
                "variant": variant,
                "main": deck.main_size,
                "extra": deck.extra_size,
                "legal": validate_deck(deck, banlist=banlist).is_legal,
                "playablePct": round(deck_playability(deck).pct),
                "portrait": portrait_url(name),
            }
        )
    games = []
    ordered = GAME_ORDER + [g for g in by_game if g not in GAME_ORDER]
    for g in ordered:
        if g in by_game:
            roster = sorted(by_game[g], key=lambda d: (d["name"], d["variant"]))
            games.append({"key": g, "title": GAME_TITLES.get(g, g), "duelists": roster})
    return games


@app.get("/api/opponents")
def opponents(format: str | None = None) -> dict:
    return {"games": opponent_roster(resolve_banlist(format) if format else None)}


# --------------------------------------------------------------------------- #
#  Player profile: Duelist Points, card library (collection), and your decks
# --------------------------------------------------------------------------- #
# The pool-filtered pack catalogue is static (registry never changes), so build
# it once; per-request we only re-read affordability from the profile.
_PACK_CACHE: list | None = None


def _all_packs() -> list:
    global _PACK_CACHE
    if _PACK_CACHE is None:
        _PACK_CACHE = list_packs(REGISTRY)
    return _PACK_CACHE


def deck_summary(deck_id: str, profile: Profile, banlist: BanList | None = None) -> dict | None:
    """Summarise one of the player's decks: sizes, legality, and ownership."""
    path = resolve_deck_id(deck_id)
    if path is None:
        return None
    deck = load_decklist(path, REGISTRY)
    counts = Counter(c.name for c in (*deck.main, *deck.extra))
    missing = profile.missing_for_deck(dict(counts))
    return {
        "id": deck_id,
        "name": deck.name,
        "main": deck.main_size,
        "extra": deck.extra_size,
        "legal": validate_deck(deck, banlist=banlist).is_legal,
        "playablePct": round(deck_playability(deck).pct),
        "owned": not missing,  # fully buildable from the collection
        "missing": missing,
        "isStarter": deck_id == STARTER_DECK_ID,
    }


def profile_summary(profile: Profile) -> dict:
    decks = [deck_summary(d, profile) for d in profile.deck_ids()]
    return {
        "name": profile.name,
        "duelistPoints": profile.duelist_points,
        "stats": profile.stats,
        "packsOpened": profile.packs_opened,
        "collectionDistinct": len(profile.collection),
        "collectionTotal": profile.total_cards(),
        "activeDeck": profile.active_deck,
        "decks": [d for d in decks if d is not None],
        "pendingReward": profile.pending_reward,
    }


@app.get("/api/profile")
def get_profile() -> dict:
    return profile_summary(load_profile())


@app.post("/api/profile/reset")
def reset_profile() -> dict:
    """Start over with a fresh save (Starter Deck cards + starting DP)."""
    profile = new_profile()
    save_profile(profile)
    return profile_summary(profile)


@app.get("/api/collection")
def collection(
    query: str | None = None,
    type: str | None = None,
    sort: str = "name",
    order: str = "asc",
) -> dict:
    """The cards you own, with counts — same shape as /api/cards plus ``owned``."""
    profile = load_profile()
    card_type = {"monster": CardType.MONSTER, "spell": CardType.SPELL, "trap": CardType.TRAP}.get(
        (type or "").lower()
    )
    if sort not in ("name", "attack", "defense", "type"):
        sort = "name"
    order = "desc" if str(order).lower() == "desc" else "asc"
    hits = search_pool(
        REGISTRY, text=query or None, card_type=card_type, sort=sort, order=order, limit=5000
    )
    cards = [
        {**card_to_dict(c), "owned": profile.collection[c.name]}
        for c in hits
        if c.name in profile.collection
    ]
    return {"count": len(cards), "cards": cards, "distinct": len(profile.collection)}


def pack_art_url(pack) -> str | None:
    """Box art for a pack: the full, high-res art of its flagship card. (The
    scraped GBA box images are tiny — 48px wide in places — so we render the
    namesake/flagship card from our 813x1185 card art instead.)"""
    name = pack.cover_card
    card = REGISTRY.get(name) if name else None
    return f"/cards/{card.image_id}.jpg" if card and card.image_id else None


@app.get("/api/packs")
def packs() -> dict:
    """The booster-pack shop, grouped by game, with prices and affordability."""
    profile = load_profile()
    by_game: dict[str, list[dict]] = {}
    for p in _all_packs():
        price = pricing.pack_price(p, REGISTRY)
        by_game.setdefault(p.game, []).append(
            {
                "id": p.id,
                "name": p.name,
                "price": price,
                "cardsPerPack": p.cards_per_pack,
                "distinct": p.distinct,
                "affordable": profile.can_afford(price),
                "art": pack_art_url(p),
            }
        )
    games = []
    ordered = GAME_ORDER + [g for g in by_game if g not in GAME_ORDER]
    for g in ordered:
        if g in by_game:
            games.append({"key": g, "title": GAME_TITLES.get(g, g), "packs": by_game[g]})
    return {"games": games, "duelistPoints": profile.duelist_points}


@app.post("/api/packs/open")
def buy_pack(payload: dict) -> dict:
    """Spend DP to open a pack; the pulled cards go into your library."""
    profile = load_profile()
    pack = get_pack(payload.get("packId", ""), REGISTRY)
    if pack is None:
        raise HTTPException(status_code=404, detail="Unknown pack")
    price = pricing.pack_price(pack, REGISTRY)
    if not profile.can_afford(price):
        raise HTTPException(
            status_code=400,
            detail=f"Not enough DP — need {price}, have {profile.duelist_points}",
        )
    profile.spend(price)
    pulled = open_pack(pack, random.Random())
    before = set(profile.collection)
    profile.add_cards(Counter(pulled))
    profile.packs_opened += 1
    save_profile(profile)
    cards = []
    for name in pulled:
        card = REGISTRY.get(name)
        entry = card_to_dict(card)
        entry["isNew"] = name not in before
        cards.append(entry)
    return {
        "pack": pack.name,
        "pulled": cards,
        "spent": price,
        "duelistPoints": profile.duelist_points,
    }


# --------------------------------------------------------------------------- #
#  Single-card shop: buy specific cards, sell duplicates back
# --------------------------------------------------------------------------- #
def _shop_card(payload: dict) -> tuple[CardDef, int]:
    """Resolve the {name, qty} of a buy/sell request, or raise 4xx."""
    card = REGISTRY.get((payload.get("name") or "").strip())
    if card is None:
        raise HTTPException(status_code=404, detail="Unknown card")
    qty = int(payload.get("qty", 1) or 1)
    if qty < 1:
        raise HTTPException(status_code=400, detail="Quantity must be at least 1")
    return card, qty


@app.post("/api/shop/buy")
def shop_buy(payload: dict) -> dict:
    """Buy a card outright (single-card shop) at its full value."""
    profile = load_profile()
    card, qty = _shop_card(payload)
    unit = pricing.buy_value(card, REGISTRY)
    cost = unit * qty
    if not profile.can_afford(cost):
        raise HTTPException(
            status_code=400,
            detail=f"Not enough DP — need {cost}, have {profile.duelist_points}",
        )
    profile.spend(cost)
    profile.add_cards({card.name: qty})
    save_profile(profile)
    return {
        "card": card_to_dict(card),
        "qty": qty,
        "spent": cost,
        "owned": profile.collection.get(card.name, 0),
        "duelistPoints": profile.duelist_points,
        "profile": profile_summary(profile),
    }


@app.post("/api/shop/sell")
def shop_sell(payload: dict) -> dict:
    """Sell duplicates back for DP (a fraction of the card's value)."""
    profile = load_profile()
    card, qty = _shop_card(payload)
    if not profile.owns(card.name, qty):
        have = profile.collection.get(card.name, 0)
        raise HTTPException(status_code=400, detail=f"You only own {have}x {card.name}")
    unit = pricing.sell_value(card, REGISTRY)
    proceeds = unit * qty
    profile.remove_cards({card.name: qty})
    profile.earn(proceeds)
    save_profile(profile)
    return {
        "card": card_to_dict(card),
        "qty": qty,
        "earned": proceeds,
        "owned": profile.collection.get(card.name, 0),
        "duelistPoints": profile.duelist_points,
        "profile": profile_summary(profile),
    }


# --------------------------------------------------------------------------- #
#  Win rewards: a free booster pack chosen from the opponent's game (GBA-style)
# --------------------------------------------------------------------------- #
def opponent_game(opp_id: str | None) -> str | None:
    """The GBA game an opponent deck belongs to. Deck ids look like
    ``gba/<game>/<duelist>.txt``; returns ``<game>`` or None for non-GBA decks."""
    parts = (opp_id or "").split("/")
    return parts[1] if len(parts) >= 3 and parts[0] == "gba" else None


def packs_for_game(game: str | None) -> list:
    return [p for p in _all_packs() if p.game == game] if game else []


def reward_pack_dict(pack) -> dict:
    return {
        "id": pack.id,
        "name": pack.name,
        "cardsPerPack": pack.cards_per_pack,
        "distinct": pack.distinct,
        "art": pack_art_url(pack),
    }


@app.get("/api/rewards")
def rewards() -> dict:
    """The booster packs offered for an unclaimed win reward (opponent's game)."""
    profile = load_profile()
    reward = profile.pending_reward
    if not reward:
        return {"pending": False, "packs": []}
    game = reward.get("game")
    return {
        "pending": True,
        "game": game,
        "gameTitle": GAME_TITLES.get(game, game),
        "packs": [reward_pack_dict(p) for p in packs_for_game(game)],
    }


@app.post("/api/rewards/claim")
def claim_reward(payload: dict) -> dict:
    """Open the chosen reward pack for free and clear the pending reward."""
    profile = load_profile()
    reward = profile.pending_reward
    if not reward:
        raise HTTPException(status_code=400, detail="No reward to claim")
    pack = get_pack(payload.get("packId", ""), REGISTRY)
    game = reward.get("game")
    if pack is None or (game and pack.game != game):
        raise HTTPException(status_code=400, detail="That pack isn't one of your reward choices")
    pulled = open_pack(pack, random.Random())
    before = set(profile.collection)
    profile.add_cards(Counter(pulled))
    profile.packs_opened += 1
    profile.pending_reward = None
    save_profile(profile)
    cards = []
    for name in pulled:
        card = REGISTRY.get(name)
        entry = card_to_dict(card)
        entry["isNew"] = name not in before
        cards.append(entry)
    return {
        "pack": pack.name,
        "pulled": cards,
        "duelistPoints": profile.duelist_points,
        "profile": profile_summary(profile),
    }


# --------------------------------------------------------------------------- #
#  Tournaments: a gauntlet bracket of GBA duelists, played for DP
# --------------------------------------------------------------------------- #
TOURNEY_SIZE = 6  # opponents per bracket (cap)
_TOURNEY_CACHE: list | None = None


def tournament_presets() -> list[dict]:
    """One championship per GBA game, made of that game's legal duelists."""
    global _TOURNEY_CACHE
    if _TOURNEY_CACHE is not None:
        return _TOURNEY_CACHE
    presets = []
    for game in opponent_roster():
        legal = [d for d in game["duelists"] if d["legal"]][:TOURNEY_SIZE]
        if len(legal) < 2:
            continue
        opponents = [{"id": d["id"], "name": d["name"], "portrait": d["portrait"]} for d in legal]
        presets.append(
            {
                "id": "game:" + game["key"],
                "name": game["title"] + " Championship",
                "game": game["key"],
                "rounds": len(opponents),
                "reward": tour.DP_PER_ROUND * len(opponents),
                "opponents": opponents,
            }
        )
    _TOURNEY_CACHE = presets
    return presets


def _tournament_state(profile: Profile) -> dict:
    return {
        "tournament": profile.tournament,
        "currentOpponent": tour.current_opponent(profile.tournament),
    }


@app.get("/api/tournaments")
def tournaments() -> dict:
    profile = load_profile()
    return {"presets": tournament_presets(), **_tournament_state(profile)}


@app.get("/api/tournament")
def tournament_now() -> dict:
    return _tournament_state(load_profile())


@app.post("/api/tournaments/start")
def start_tournament(payload: dict) -> dict:
    profile = load_profile()
    preset = next((p for p in tournament_presets() if p["id"] == payload.get("presetId")), None)
    if preset is None:
        raise HTTPException(status_code=404, detail="Unknown tournament")
    deck_id = payload.get("deckId") or profile.active_deck
    summary = deck_summary(deck_id, profile)
    if summary is None:
        raise HTTPException(status_code=400, detail="Unknown deck")
    if not summary["owned"]:
        raise HTTPException(status_code=400, detail="You don't own every card in that deck")
    if not summary["legal"]:
        raise HTTPException(status_code=400, detail="That deck isn't tournament-legal")
    profile.tournament = tour.start_run(preset["name"], deck_id, preset["opponents"])
    profile.active_deck = deck_id
    save_profile(profile)
    return _tournament_state(profile)


@app.post("/api/tournament/advance")
def advance_tournament(payload: dict) -> dict:
    """Report a tournament-match result; advance the bracket and award any bonus."""
    profile = load_profile()
    run = profile.tournament
    if not run or not run.get("active"):
        return {**_tournament_state(profile), "bonus": 0}
    run, bonus = tour.advance(run, bool(payload.get("won")))
    if bonus:
        profile.earn(bonus)
    profile.tournament = run
    save_profile(profile)
    return {**_tournament_state(profile), "bonus": bonus, "duelistPoints": profile.duelist_points}


@app.post("/api/tournament/forfeit")
def forfeit_tournament() -> dict:
    profile = load_profile()
    profile.tournament = None
    save_profile(profile)
    return _tournament_state(profile)


@app.post("/api/decks/validate")
def validate(payload: dict) -> dict:
    deck = decklist_from_counts(
        payload.get("name", "Untitled"), payload.get("main", {}), payload.get("extra", {})
    )
    return validation_dict(deck, payload.get("format"))


@app.post("/api/decks")
def save_deck(payload: dict) -> dict:
    """Save one of *your* decks — buildable only from cards you own."""
    profile = load_profile()
    name = (payload.get("name") or "Untitled").strip()
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "deck"
    deck = decklist_from_counts(name, payload.get("main", {}), payload.get("extra", {}))
    counts = Counter(c.name for c in (*deck.main, *deck.extra))
    missing = profile.missing_for_deck(dict(counts))
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"error": "Your library is short on some cards", "missing": missing},
        )
    user_dir = DECKS_DIR / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{slug}.txt"
    path.write_text(to_blueprint_text(deck), encoding="utf-8")
    deck_id = path.relative_to(DECKS_DIR).as_posix()
    # Editing + renaming a deck would otherwise leave the old file orphaned —
    # clean it up (only user decks, never a bundled one).
    replaces = payload.get("replaces")
    if replaces and replaces != deck_id:
        old = resolve_deck_id(replaces)
        user_root = (DECKS_DIR / "user").resolve()
        if old is not None and user_root in old.resolve().parents:
            old.unlink(missing_ok=True)
            if replaces in profile.decks:
                profile.decks.remove(replaces)
    if deck_id not in profile.decks:
        profile.decks.append(deck_id)
    profile.active_deck = deck_id
    save_profile(profile)
    return {
        "id": deck_id,
        "validation": validation_dict(deck, payload.get("format")),
    }


@app.get("/api/decks/{deck_id:path}")
def get_deck(deck_id: str) -> dict:
    """One deck's card counts, for loading it into the builder to edit."""
    path = resolve_deck_id(deck_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown deck")
    deck = load_decklist(path, REGISTRY)
    return {
        "id": deck_id,
        "name": deck.name,
        "main": dict(Counter(c.name for c in deck.main)),
        "extra": dict(Counter(c.name for c in deck.extra)),
    }


@app.delete("/api/decks/{deck_id:path}")
def delete_deck(deck_id: str) -> dict:
    """Delete one of your built decks (only files under ``user/``)."""
    path = resolve_deck_id(deck_id)
    user_root = (DECKS_DIR / "user").resolve()
    if path is None or user_root not in path.resolve().parents:
        raise HTTPException(status_code=400, detail="Not a deletable deck")
    path.unlink()
    profile = load_profile()
    if deck_id in profile.decks:
        profile.decks.remove(deck_id)
    if profile.active_deck == deck_id:
        profile.active_deck = STARTER_DECK_ID
    save_profile(profile)
    return {"deleted": deck_id}


# --------------------------------------------------------------------------- #
#  WebSocket duel
# --------------------------------------------------------------------------- #
@app.websocket("/ws")
async def duel_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    seed = int(websocket.query_params.get("seed", "0"))
    opp_id = websocket.query_params.get("opp")
    your_deck = resolve_deck_id(websocket.query_params.get("deck")) or DECK_A
    opp_deck = resolve_deck_id(opp_id) or DECK_B

    session = GameSession(
        deck_a=your_deck, deck_b=opp_deck, seed=seed, human_player=0, record_dir=RECORD_DIR
    )
    worker = threading.Thread(target=session.run, daemon=True)
    worker.start()

    loop = asyncio.get_running_loop()

    async def pump_outbound() -> None:
        # Bridge the engine thread's blocking queue to the async socket.
        while True:
            message = await loop.run_in_executor(None, session.outbound.get)
            if message.get("type") == "result":
                # The duel is over — tally it. A win grants a free booster-pack
                # pick from the opponent's game (GBA-style) instead of flat DP;
                # a loss still pays the small consolation DP.
                profile = load_profile()
                won = bool(message.get("youWin"))
                game = opponent_game(opp_id)
                if won and packs_for_game(game):
                    earned = profile.record_result(True, dp=0)
                    profile.pending_reward = {"game": game}
                else:
                    earned = profile.record_result(won)
                save_profile(profile)
                message = {
                    **message,
                    "dpEarned": earned,
                    "duelistPoints": profile.duelist_points,
                    "pendingReward": profile.pending_reward,
                }
            await websocket.send_json(message)

    pump = asyncio.create_task(pump_outbound())
    try:
        while True:
            intent = await websocket.receive_json()
            session.submit_intent(intent)
    except WebSocketDisconnect:
        pass
    finally:
        session.abort()
        pump.cancel()


# Card art (downloaded by scripts/download_card_images.py). Mounted before "/".
_cards_dir = ASSETS / "card_images" / "cards"
if _cards_dir.is_dir():
    app.mount("/cards", StaticFiles(directory=str(_cards_dir)), name="cards")

# Duelist portraits for the opponent picker.
if PORTRAIT_DIR.is_dir():
    app.mount("/portraits", StaticFiles(directory=str(PORTRAIT_DIR)), name="portraits")

# Serve the built frontend if present (optional; dev uses the Vite server).
_dist = REPO_ROOT / "web" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="web")
