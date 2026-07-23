#!/usr/bin/env python3
"""Has the city published anything new since the last build?

Runs cheap and often so the directory can follow Open Data rather than a
calendar. Each Socrata dataset exposes `rowsUpdatedAt` in its metadata — two
small requests, no row data — which is compared against the stamps recorded in
the last build. If either has moved, the full rebuild is worth running.

Exit codes:
  0  something changed, rebuild
  1  nothing changed
  2  could not tell (network/parse failure) — treated as "rebuild anyway",
     because a missed refresh is worse than a redundant one

Prints `changed=true|false` to $GITHUB_OUTPUT when running in Actions.
"""

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BUILT = ROOT / "docs" / "data" / "greenbook.json"
DOMAIN = "https://data.cityofnewyork.us"
DATASETS = {"greenbook": "mdcw-n682", "agencies": "t3jq-9nkf"}

UA = "nyc-green-book/1.0 (+https://github.com/joshgreenman1973/nyc-green-book)"


def emit(changed, reason):
    print(reason)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")


def main():
    if not BUILT.exists():
        emit(True, "No previous build; rebuilding.")
        return 0
    try:
        prev = json.loads(BUILT.read_text())["sources"]
    except Exception as e:
        emit(True, f"Could not read previous build ({e}); rebuilding.")
        return 0

    moved = []
    for key, ds in DATASETS.items():
        try:
            r = requests.get(f"{DOMAIN}/api/views/{ds}.json",
                             headers={"User-Agent": UA}, timeout=45)
            r.raise_for_status()
            stamp = r.json()["rowsUpdatedAt"]
        except Exception as e:
            emit(True, f"Could not check {ds} ({e}); rebuilding to be safe.")
            return 2

        from datetime import datetime, timezone
        now = datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
        was = prev.get(key, {}).get("updated", "")
        print(f"  {ds}: city has {now}, build has {was or '(none)'}")
        if now != was:
            moved.append(f"{ds} {was or '(none)'} -> {now}")

    if moved:
        emit(True, "Changed: " + "; ".join(moved))
        return 0
    emit(False, "Nothing new since the last build.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
