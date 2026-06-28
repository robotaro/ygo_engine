"""Loading the raw YGOPRODeck card data that seeds our card pool.

Both maintenance scripts (``scripts/build_card_db.py`` and
``scripts/download_card_images.py``) read the *same* source: either a JSON blob
saved to disk, or a fresh download from the API. The default filter is the
**v6.0 / pre-Synchro** pool the engine targets — every card that existed in the
OCG before Synchro Monsters arrived (Starter Deck 2008, 2008-03-15). Because
Synchro/Xyz/Pendulum/Link card types did not exist yet, that single date cutoff
*is* the v6.0-legal pool; no per-type exclusion is needed.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
UA = {"User-Agent": "ygo_engine/0.1 (personal toy project)"}

#: The v6.0 card pool: every OCG card printed before the first Synchro Monsters.
V6_FILTER: dict[str, str] = {
    "startdate": "1999-01-01",
    "enddate": "2008-03-14",  # day before OCG Starter Deck 2008 (first Synchros)
    "dateregion": "ocg",
}


def download_cards(**overrides: str) -> list[dict]:
    """Fetch the card list from the YGOPRODeck API for the v6.0 date filter.

    Pass ``enddate=``/``dateregion=``/``startdate=`` to override the defaults.
    """
    params = {**V6_FILTER, **overrides}
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["data"]


def load_cards(source: Path | str | None = None, **overrides: str) -> list[dict]:
    """Return the YGOPRODeck card list, from a saved blob or a fresh download.

    ``source`` is a path to a JSON file shaped either as the raw API response
    (``{"data": [...]}``) or a bare list of card dicts. With ``source=None`` the
    list is downloaded live using :data:`V6_FILTER` (plus any ``overrides``).
    """
    if source is None:
        return download_cards(**overrides)
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    return data["data"] if isinstance(data, dict) else data
