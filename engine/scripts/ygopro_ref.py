"""Authoring aid: pull the OFFICIAL ruling + reference implementation for a card.

For each of the ~1,800 effects still to author, the canonical sources are:
  * the current PSCT ruling text (YGOPRODeck — the same DB our pool was built from, so
    names match), and
  * the reference implementation as a Lua script from ygopro-core's script repo
    (Fluorohydride/ygopro-scripts), named ``c<passcode>.lua``.

This maps a card *name* -> passcode (via the YGOPRODeck API) -> Lua script (fetched from
raw.githubusercontent, or read from a local clone with ``--local``). Reading the official
Lua while authoring is both faster and more correct than inferring rulings from the CSV
text — e.g. it confirmed Blast Sphere fires on the opponent's Standby (``GetTurnPlayer()~=tp``)
and revealed that the modern ruling damages a *fixed* opponent (``Duel.Damage(1-tp,...)``),
not the equipped monster's current controller.

Usage:
    uv run python scripts/ygopro_ref.py "Blast Sphere"
    uv run python scripts/ygopro_ref.py "Mazera DeVille" --local /path/to/ygopro-scripts

Needs network for the passcode lookup (and the Lua, unless ``--local`` is given). Stdlib
only — no added dependencies. Importable: ``passcode_for(name)`` / ``script_for(name)``.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php?name="
_RAW = "https://raw.githubusercontent.com/Fluorohydride/ygopro-scripts/master/c{}.lua"


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ygo-engine-authoring"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def lookup(name: str) -> dict:
    """Return the YGOPRODeck record for an EXACT card name (raises if not found)."""
    raw = _get(_API + urllib.parse.quote(name))
    payload = json.loads(raw)
    if "data" not in payload or not payload["data"]:
        raise LookupError(f"no card named {name!r} on YGOPRODeck")
    return payload["data"][0]


def passcode_for(name: str) -> int:
    return int(lookup(name)["id"])


def script_for(name: str, local_dir: str | None = None) -> tuple[int, str]:
    """(passcode, Lua source) for ``name``. Reads ``local_dir/c<id>.lua`` if given, else
    fetches from raw.githubusercontent. Raises FileNotFoundError if the card has no script
    (e.g. a vanilla monster)."""
    pid = passcode_for(name)
    if local_dir is not None:
        path = Path(local_dir) / f"c{pid}.lua"
        if not path.exists():
            raise FileNotFoundError(f"no script c{pid}.lua in {local_dir} (vanilla card?)")
        return pid, path.read_text(encoding="utf-8")
    try:
        return pid, _get(_RAW.format(pid)).decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(f"no script c{pid}.lua upstream (vanilla card?)") from exc
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Official ruling + Lua reference for a card.")
    ap.add_argument("name", help="exact card name (as in the pool / YGOPRODeck)")
    ap.add_argument("--local", help="path to a local ygopro-scripts clone (offline Lua)")
    ap.add_argument("--text-only", action="store_true", help="print only the ruling text")
    args = ap.parse_args(argv)

    try:
        rec = lookup(args.name)
    except Exception as exc:  # noqa: BLE001 — surface any lookup failure plainly
        print(f"lookup failed: {exc}", file=sys.stderr)
        return 1
    print(f"# {rec['name']}  (passcode {rec['id']})")
    print(f"# {rec.get('type', '?')} — {', '.join(rec.get('typeline', []))}")
    print(f"\n{rec.get('desc', '(no text)')}\n")
    if args.text_only:
        return 0
    try:
        pid, lua = script_for(args.name, args.local)
    except FileNotFoundError as exc:
        print(f"-- {exc}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"-- could not fetch script: {exc}", file=sys.stderr)
        return 1
    print(f"--- official script c{pid}.lua ---")
    print(lua)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
