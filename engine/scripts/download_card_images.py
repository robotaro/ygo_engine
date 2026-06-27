"""Download card art for our card pool from the YGOPRODeck API.

YGOPRODeck asks apps to download and host images locally rather than hotlink, so
this fetches each matched card once into assets/card_images/cards/<id>.jpg and
writes a name -> image-id map the engine loads.

Run:  uv run python scripts/download_card_images.py
Idempotent: existing images are skipped, so re-runs only fetch what's missing.
"""

from __future__ import annotations

import concurrent.futures
import json
import urllib.request
from pathlib import Path

from ygo.cards import CardRegistry
from ygo.paths import ASSETS, CARD_DB_DIR

API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
IMG_DIR = ASSETS / "card_images" / "cards"
MAP_PATH = CARD_DB_DIR / "card_image_ids.json"
UA = {"User-Agent": "ygo_engine/0.1 (personal toy project)"}


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def fetch_all_cards() -> list[dict]:
    req = urllib.request.Request(API, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["data"]


def download(item: tuple[int, str]) -> bool:
    card_id, url = item
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            (IMG_DIR / f"{card_id}.jpg").write_bytes(resp.read())
        return True
    except Exception:
        return False


def main() -> None:
    reg = CardRegistry.load_csv()
    our_names = [c.name for c in reg]
    print(f"card pool: {len(our_names)} cards")

    print("fetching the YGOPRODeck card database (one request)...")
    cards = fetch_all_cards()
    by_name: dict[str, dict] = {}
    by_norm: dict[str, dict] = {}
    for c in cards:
        image = c["card_images"][0]
        by_name[c["name"].lower()] = image
        by_norm.setdefault(_norm(c["name"]), image)

    mapping: dict[str, int] = {}
    urls: dict[int, str] = {}
    misses: list[str] = []
    for name in our_names:
        image = by_name.get(name.lower()) or by_norm.get(_norm(name))
        if image is None:
            misses.append(name)
            continue
        mapping[name] = image["id"]
        urls[image["id"]] = image["image_url"]

    print(f"matched {len(mapping)}/{len(our_names)} cards; {len(misses)} unmatched")
    if misses:
        print("  unmatched (no art):", ", ".join(sorted(misses)[:25]), "..." if len(misses) > 25 else "")

    MAP_PATH.write_text(json.dumps(mapping, indent=0, sort_keys=True))
    print(f"wrote name->id map: {MAP_PATH}")

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    todo = [(cid, urls[cid]) for cid in set(mapping.values()) if not (IMG_DIR / f"{cid}.jpg").exists()]
    print(f"downloading {len(todo)} images ({len(set(mapping.values())) - len(todo)} already present)...")

    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for i, success in enumerate(pool.map(download, todo), 1):
            ok += success
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}")
    print(f"done: {ok}/{len(todo)} new images; {len(list(IMG_DIR.glob('*.jpg')))} total on disk")


if __name__ == "__main__":
    main()
