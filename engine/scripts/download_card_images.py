"""Download card art for our card pool from YGOPRODeck.

YGOPRODeck asks apps to download and host images locally rather than hotlink, so
this fetches each card's front once into assets/card_images/cards/<id>.jpg. The
card pool comes from the same source the CSV is built from (a saved JSON blob or
a live download), so this covers every card in the v6.0 pool.

Run:  uv run python scripts/download_card_images.py            # uses the saved v6.0 blob
      uv run python scripts/download_card_images.py --download  # fresh OCG pre-Synchro pull
Idempotent: existing images are skipped, so re-runs only fetch what's missing.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import urllib.request
from pathlib import Path

from ygo.paths import ASSETS, CARD_DB_DIR
from ygo.ygoprodeck import UA, load_cards

IMG_DIR = ASSETS / "card_images" / "cards"
CARD_BACK = ASSETS / "card_images" / "card_back.jpg"
CARD_BACK_URL = "https://images.ygoprodeck.com/images/cards/back.jpg"
DEFAULT_SOURCE = CARD_DB_DIR / "card_db_ocg_pre_synchro_v6.json"


def _fetch(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception:
        return False


def ensure_card_back() -> None:
    if CARD_BACK.exists():
        print(f"card back present: {CARD_BACK}")
        return
    print("card back missing; downloading one...")
    if _fetch(CARD_BACK_URL, CARD_BACK):
        print(f"  saved {CARD_BACK}")
    else:
        print(f"  FAILED to fetch card back from {CARD_BACK_URL} (add it manually)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, help="YGOPRODeck JSON blob to read the pool from")
    ap.add_argument("--download", action="store_true", help="fetch a fresh pool from the API")
    ap.add_argument("--workers", type=int, default=8, help="parallel downloads (be polite)")
    args = ap.parse_args()

    ensure_card_back()

    if args.download:
        source = None
    elif args.source:
        source = args.source
    elif DEFAULT_SOURCE.exists():
        source = DEFAULT_SOURCE
    else:
        source = None
    cards = load_cards(source)
    print(f"card pool: {len(cards)} cards")

    # One front per card (the first/original art); de-dupe by image id.
    fronts: dict[int, str] = {}
    for c in cards:
        images = c.get("card_images") or []
        if images:
            fronts[images[0]["id"]] = images[0]["image_url"]

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    todo = [(cid, url) for cid, url in fronts.items() if not (IMG_DIR / f"{cid}.jpg").exists()]
    present = len(fronts) - len(todo)
    print(f"downloading {len(todo)} fronts ({present} already present)...")

    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_fetch, url, IMG_DIR / f"{cid}.jpg"): cid for cid, url in todo}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            ok += fut.result()
            if i % 200 == 0:
                print(f"  {i}/{len(todo)}")
    print(f"done: {ok}/{len(todo)} new images; {len(list(IMG_DIR.glob('*.jpg')))} total on disk")


if __name__ == "__main__":
    main()
