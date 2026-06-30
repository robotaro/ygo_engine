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
import os
import re
import threading
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
from ..paths import ASSETS, DECKS_DIR, REPO_ROOT
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
    limit: int = 120,
) -> dict:
    card_type = {"monster": CardType.MONSTER, "spell": CardType.SPELL, "trap": CardType.TRAP}.get(
        (type or "").lower()
    )
    attr = None
    if attribute and attribute.upper() in Attribute.__members__:
        attr = Attribute[attribute.upper()]
    hits = search_pool(
        REGISTRY,
        text=query or None,
        card_type=card_type,
        attribute=attr,
        functional_only=functional,
        limit=max(1, min(limit, 500)),
    )
    return {"count": len(hits), "cards": [card_to_dict(c) for c in hits]}


@app.post("/api/decks/validate")
def validate(payload: dict) -> dict:
    deck = decklist_from_counts(
        payload.get("name", "Untitled"), payload.get("main", {}), payload.get("extra", {})
    )
    return validation_dict(deck, payload.get("format"))


@app.post("/api/decks")
def save_deck(payload: dict) -> dict:
    name = (payload.get("name") or "Untitled").strip()
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "deck"
    deck = decklist_from_counts(name, payload.get("main", {}), payload.get("extra", {}))
    user_dir = DECKS_DIR / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{slug}.txt"
    path.write_text(to_blueprint_text(deck), encoding="utf-8")
    return {
        "id": path.relative_to(DECKS_DIR).as_posix(),
        "validation": validation_dict(deck, payload.get("format")),
    }


# --------------------------------------------------------------------------- #
#  WebSocket duel
# --------------------------------------------------------------------------- #
@app.websocket("/ws")
async def duel_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    seed = int(websocket.query_params.get("seed", "0"))
    your_deck = resolve_deck_id(websocket.query_params.get("deck")) or DECK_A
    opp_deck = resolve_deck_id(websocket.query_params.get("opp")) or DECK_B

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

# Serve the built frontend if present (optional; dev uses the Vite server).
_dist = REPO_ROOT / "web" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="web")
