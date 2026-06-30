"""The web GameSession records a replay of the duel it just ran."""

from __future__ import annotations

import json
import threading
import time

from ygo.paths import DECKS_DIR
from ygo.server.session import GameSession

DECK_A = DECKS_DIR / "vanilla" / "beatdown_alpha.txt"
DECK_B = DECKS_DIR / "vanilla" / "beatdown_beta.txt"


def test_session_saves_a_replay(tmp_path, monkeypatch):
    # Drop the UI pacing so the duel runs at full speed in the test.
    import ygo.server.session as sess

    monkeypatch.setattr(sess.time, "sleep", lambda *a, **k: None)

    session = GameSession(
        deck_a=DECK_A, deck_b=DECK_B, seed=2, human_player=0, record_dir=tmp_path
    )
    worker = threading.Thread(target=session.run, daemon=True)
    worker.start()

    # Feed the human seat (player 0): pass everything, discard when forced.
    finished = None
    deadline = time.time() + 30
    while time.time() < deadline:
        msg = session.outbound.get(timeout=15)
        if msg["type"] == "result":
            finished = msg
            break
        if msg["type"] != "decision":
            continue
        legal = msg.get("legal") or {}
        if legal.get("discards"):
            session.submit_intent({"kind": "discard", "iid": legal["discards"][0]})
        else:
            session.submit_intent({"kind": "pass"})

    worker.join(timeout=5)
    assert finished is not None, "duel never finished"

    replays = list(tmp_path.glob("*.json"))
    assert replays, "no replay file was written"
    data = json.loads(replays[0].read_text())
    assert data["result"]["reason"]
    assert len(data["decisions"]) == 2  # one decision log per seat
    assert data["seed"] == 2
