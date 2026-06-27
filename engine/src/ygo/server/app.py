"""FastAPI app exposing one duel per WebSocket connection.

Run (dev)::

    uv run uvicorn ygo.server.app:app --reload --port 8000

The Svelte dev server (web/) proxies ``/ws`` here. If a production build exists
at ``web/dist`` it is served at ``/``.
"""

from __future__ import annotations

import asyncio
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles

from ..paths import ASSETS, DECKS_DIR, REPO_ROOT
from .session import GameSession

app = FastAPI(title="ygo_engine")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DECK_A = DECKS_DIR / "vanilla" / "slice1_alpha.txt"
DECK_B = DECKS_DIR / "vanilla" / "slice1_beta.txt"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.websocket("/ws")
async def duel_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    seed = int(websocket.query_params.get("seed", "0"))

    session = GameSession(deck_a=DECK_A, deck_b=DECK_B, seed=seed, human_player=0)
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
