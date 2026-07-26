#!/usr/bin/env python3
"""Export the senior ranks of the mayoral administration as a contact CSV.

Scope is the executive branch under the mayor: the Mayor's Office, mayoral
agencies and mayoral offices, plus the public-benefit corporations the mayor
appoints (EDC, HDC, HHC and the like). Separately elected offices are excluded
by design — the comptroller, the public advocate, the borough presidents, the
district attorneys and the Council are not the administration, whatever else
they are.

**On the email column: it is empty, and that is the finding.**

The City of New York does not publish email addresses for its executive-branch
officials. Not in the Greenbook, not in the governance inventory, not on the
agency pages, and not for the mayor. The only addresses the city publishes are
for press offices, and those are deliberately kept out of this file. The column
exists so the file is ready to fill in from your own reporting; it is never
populated by guessing at a pattern.

Run: python3 scripts/export_admin.py [-o out.csv]
"""

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data" / "greenbook.json"

spec = importlib.util.spec_from_file_location("build", Path(__file__).parent / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

# Governance organization types that make up the executive branch.
EXEC_TYPES = {
    "Mayoral Agency",
    "Mayoral Office",
    "Public Benefit or Development Organization",
    "Division",
}

# Separately elected offices, and the bodies attached to them. The Mayor's own
# office is classed "Elected Office" too, so it is allowed back in by name.
ELECTED_EXCLUDE = {
    "Comptroller",
    "Public Advocate for the City of New York",
    "City Council",
    "Borough President - Bronx",
    "Borough President - Brooklyn",
    "Borough President - Manhattan",
    "Borough President - Queens",
    "Borough President - Staten Island",
    "District Attorney",
}

MAYORS_OFFICE = "Mayor, Office of the"

# Tier 1: the mayor and the deputy mayors — the top of the administration.
TIER1 = ("mayor", "first deputy mayor", "deputy mayor")

# Tier 3: the senior posts directly under an agency head.
TIER3 = ("first deputy commissioner", "executive deputy commissioner",
         "chief of staff", "general counsel", "chief operating officer",
         "executive director", "deputy commissioner", "chief financial officer",
         "chief counsel", "deputy director", "first deputy director",
         "chief information officer", "chief technology officer",
         "chief administrative officer", "commissioner")


def tier_of(title, is_head, agency, unit):
    t = build.fold(title)
    t = t.replace("acting ", "").replace("interim ", "")
    if any(t == x or t.startswith(x + " ") or t.startswith(x + ",") for x in TIER1):
        return 1
    # The mayor's own chief of staff sits at the top of the administration. A
    # chief of staff buried inside a division of the Mayor's Office does not —
    # every counsel and commissioner has one.
    if agency == MAYORS_OFFICE and t == "chief of staff" and unit in ("", "Chief of Staff"):
        return 1
    if is_head:
        return 2
    if any(t == x or t.startswith(x + " ") for x in TIER3):
        return 3
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=str(ROOT / "docs" / "data" /
                                               "mayoral_administration.csv"))
    ap.add_argument("--max-tier", type=int, default=2,
                    help="1=mayor+deputy mayors, 2=+agency heads (default), "
                         "3=+their seconds (much longer)")
    args = ap.parse_args()

    if not DATA.exists():
        raise SystemExit("FATAL: run scripts/build.py first.")
    d = json.loads(DATA.read_text())

    orgs = {o["id"]: o for o in d["orgs"]}
    agencies = {a["name"]: a for a in d["agencies"]}
    buildings = {b["k"]: b for b in d["buildings"]}
    heads = {h["agency"]: h for h in d["heads"]}

    def in_scope(a):
        if a["name"] == MAYORS_OFFICE:
            return True
        if a["name"] in ELECTED_EXCLUDE:
            return False
        if a["section"] != "City":
            return False
        o = orgs.get(a["org"]) if a["org"] else None
        if o:
            return o["type"] in EXEC_TYPES
        # Unlinked agencies: keep them only if the Green Book seats a
        # commissioner-style head, which is what a mayoral agency looks like.
        h = heads.get(a["name"])
        return bool(h and h["gb"])

    rows = []
    for p in d["people"]:
        a = agencies.get(p["a"])
        if not a or not in_scope(a):
            continue
        if not p["n"] or p["v"]:
            continue                      # vacant posts are not contacts
        h = heads.get(p["a"])
        is_head = bool(h and h["gb"] and h["gb"]["n"] == p["n"]
                       and h["gb"]["t"] == p["t"]) or bool(p.get("alt"))
        unit = " > ".join(p["d"])
        tier = tier_of(p["t"], is_head, p["a"], unit)
        if not tier or tier > args.max_tier:
            continue
        b = buildings.get(p["ak"], {})
        o = orgs.get(a["org"]) if a["org"] else None
        rows.append({
            "tier": tier,
            "name": p["n"],
            "title": p["t"],
            "email": "",                 # see the module docstring
            # From the City Record, and blank unless it corroborated the person
            # by name, middle initial and agency together.
            "status": ("left this agency" if p.get("gone") else
                       "in post" if p.get("cr") else ""),
            "in_post_since": ((p.get("cr") or {}).get("effective", "")
                              if not p.get("gone") else ""),
            "left_on": ((p.get("cr") or {}).get("effective", "")
                        if p.get("gone") else ""),
            "moved_to": (p.get("cr") or {}).get("moved_to", ""),
            "salary": (p.get("cr") or {}).get("salary", "") or "",
            "agency": p["a"],
            "acronym": a["acronym"],
            "org_type": o["type"] if o else "",
            "unit": unit,
            "direct_phone": p["p"],
            "division_phone": p["dp"],
            "agency_phone": a["phone"],
            "address": ", ".join(x for x in [b.get("addr"), b.get("city"),
                                             b.get("state"), b.get("zip")] if x),
            "agency_website": a["website"],
            "name_source": "governance dataset" if p.get("alt") else "Green Book",
            "superseded_name": (p.get("alt") or {}).get("n", ""),
        })

    # The Green Book lists some officials once per body they sit on, so the same
    # person and post can appear several times under one agency.
    seen, deduped = set(), []
    for r in rows:
        k = (build.fold(r["name"]), build.fold(r["title"]), build.fold(r["agency"]))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    dupes = len(rows) - len(deduped)
    rows = deduped

    order = {1: 0, 2: 1, 3: 2}
    rows.sort(key=lambda r: (order[r["tier"]], r["agency"], r["name"]))

    out = Path(args.out)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    by_tier = {}
    for r in rows:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    withphone = sum(1 for r in rows if r["direct_phone"])
    print(f"Wrote {out}")
    print(f"  {len(rows)} officials "
          f"(tier 1: {by_tier.get(1,0)}, tier 2: {by_tier.get(2,0)}, "
          f"tier 3: {by_tier.get(3,0)}); dropped {dupes} duplicate listings")
    print(f"  {withphone} with a direct phone "
          f"({round(100*withphone/len(rows))}%)")
    dated = sum(1 for r in rows if r["in_post_since"])
    left = sum(1 for r in rows if r["status"] == "left this agency")
    print(f"  {dated} with a City Record start date; {left} already gone")
    print(f"  0 with an email — the city publishes none for these posts")


if __name__ == "__main__":
    sys.exit(main())
