#!/usr/bin/env python3
"""City Record personnel actions — the city's legal record of who started and left.

Source: City Record Online (`dg92-zbpx`), section "Changes in Personnel". Every
hire, promotion, raise, resignation, retirement and dismissal the city is
required to publish. ~960,000 records back to 2013, and the only NYC source that
carries an *effective date* for an appointment.

This is what the two directory datasets cannot do. The Greenbook and the
governance inventory each assert a current state with no history, so when they
disagree there is nothing in either to break the tie. The City Record says when
each person started, which settles it.

WHAT IT IS NOT
--------------
- **Not current.** This section runs roughly two to three months behind
  publication, even though the dataset as a whole updates daily. An appointment
  made last month will not be here yet, so silence is never evidence of absence.
- **Not organizational.** `agency_name` is the *payroll* agency. Small mayoral
  offices are paid through a parent — a Veterans' Services commissioner files
  under the Fire Department — so an agency mismatch does not mean a different
  person, and an agency match is only corroboration.

MATCHING IS DELIBERATELY STRICT
-------------------------------
Names alone are not enough, and the failure mode is severe: publishing that a
sitting commissioner has quit when they have not. Two real examples caught while
building this, both of which name-only matching got wrong —

  "LEE, RICHARD J" resigned from the City Council. The Green Book's Richard Lee
  is the Finance commissioner. Different people.

  "ANDERSON, GREGORY J" retired from the Police Department on a police title
  code. The Green Book's Gregory P. Anderson runs Sanitation. Different people.

So a match requires the given and family names, a compatible middle initial, AND
a corroborating agency. Anything less is reported as unverified rather than
asserted.
"""

import json
import os
import re
import time
import unicodedata
import urllib.parse
from datetime import datetime

import requests

DOMAIN = "https://data.cityofnewyork.us"
DATASET = "dg92-zbpx"
SECTION = "Changes in Personnel"

# Two years is enough to date every appointment in a mayoral term while keeping
# the fetch to a couple of pages.
DEFAULT_SINCE = "2025-01-01T00:00:00"
MIN_ROWS = 20000

DEPARTURES = {"RESIGNED", "RETIRED", "TERMINATED", "DISMISSED", "DECEASED"}
ARRIVALS = {"APPOINTED", "PROMOTED"}

# When one person has two actions with the same effective date it is a transfer,
# not a departure: they resign one post and are appointed to another the same
# day. The arrival is the one that describes where they are now.
REASON_RANK = {"APPOINTED": 4, "PROMOTED": 3, "INCREASE": 2, "DECREASE": 2}

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "esq", "phd", "md", "asa", "maaa",
            "cpa", "rn", "jd", "mpa", "mph", "msw", "aicp", "pe", "faia",
            "aia", "dr", "mba"}

# Words describing the form of an agency rather than identifying it.
AGENCY_NOISE = {"department", "dept", "office", "of", "the", "nyc", "new",
                "york", "city", "for", "and", "administration", "commission",
                "authority", "bureau", "division", "board"}

UA = "nyc-green-book/1.0 (+https://github.com/joshgreenman1973/nyc-green-book)"


def _fold(s):
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _agency_tokens(s):
    return {t for t in _fold(s).split() if t not in AGENCY_NOISE and len(t) > 1}


def _datekey(s):
    """MM/DD/YYYY -> sortable tuple."""
    try:
        m, d, y = s.split("/")
        return (y, m, d)
    except (ValueError, AttributeError):
        return ("0000", "00", "00")


def parse_name(raw):
    """City Record writes 'LAST,FIRST MI'. Return (given, family, initial)."""
    if not raw or "," not in raw:
        return None
    last, first = raw.split(",", 1)
    fam = [t for t in _fold(last).split() if t not in SUFFIXES]
    giv = _fold(first).split()
    if not fam or not giv:
        return None
    initial = ""
    # A trailing single letter is a middle initial, not a name.
    if len(giv) > 1 and len(giv[-1]) == 1:
        initial = giv[-1]
        giv = giv[:-1]
    given = [t for t in giv if t not in SUFFIXES]
    if not given:
        return None
    return (given[0], fam[-1], initial)


def directory_name(display):
    """The Green Book's 'Sideya I. Sherman' -> (given, family, initial)."""
    n = re.sub(r"[\"'‘’“”(][^\"'‘’“”)]+"
               r"[\"'‘’“”)]", " ", display or "")
    n = n.replace(",", " ")
    toks = [t for t in _fold(n).split() if t not in SUFFIXES]
    if len(toks) < 2:
        return None
    initial = ""
    if len(toks) > 2 and len(toks[1]) == 1:
        initial = toks[1]
    toks = [t for t in toks if len(t) > 1]
    if len(toks) < 2:
        return None
    return (toks[0], toks[-1], initial)


def fetch(since=DEFAULT_SINCE, session=None):
    """Every personnel action published since `since`, parsed."""
    s = session or requests.Session()
    s.headers.update({"User-Agent": UA})
    token = os.environ.get("SOCRATA_APP_TOKEN")
    headers = {"X-App-Token": token} if token else {}

    rows, offset, limit = [], 0, 50000
    while True:
        params = {
            "$where": f"section_name='{SECTION}' AND start_date>'{since}'",
            "$select": "start_date,agency_name,short_title,additional_description_1",
            "$order": ":id",
            "$limit": limit,
            "$offset": offset,
        }
        url = f"{DOMAIN}/resource/{DATASET}.json?" + urllib.parse.urlencode(params)
        r = s.get(url, headers=headers, timeout=180)
        if r.status_code == 403:
            time.sleep(5)
            r = s.get(url, headers=headers, timeout=180)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    if len(rows) < MIN_ROWS:
        raise SystemExit(
            f"FATAL: City Record returned {len(rows)} personnel rows, expected "
            f"at least {MIN_ROWS}. Refusing to draw conclusions about who has "
            f"left their job from a short read."
        )

    out = []
    for r in rows:
        blob = r.get("additional_description_1") or ""

        def field(pattern):
            m = re.search(pattern, blob)
            return m.group(1).strip() if m else ""

        name = field(r"Employee Name:\s*(.+?)\s*\.?$")
        parsed = parse_name(name)
        if not parsed:
            continue
        salary = field(r"Salary:\s*([\d.]+)")
        out.append({
            "key": parsed,
            "raw_name": name,
            "reason": field(r"Reason For Change:\s*([A-Z ]+?)(?:;|$)") or
                      (r.get("short_title") or "").upper(),
            "effective": field(r"Effective Date:\s*([\d/]+)"),
            "title_code": field(r"Title Code:\s*(\w+)"),
            "salary": float(salary) if salary else 0.0,
            "agency": r.get("agency_name", ""),
            "published": (r.get("start_date") or "")[:10],
        })
    return out


def latest_published(records):
    """The most recent effective date in the feed — i.e. how stale it is.

    Sorted on the parsed date, never the MM/DD/YYYY string, which would put
    12/31/2025 above 03/15/2026.
    """
    dates = [r["effective"] for r in records if r["effective"]]
    if not dates:
        return ""
    return max(dates, key=_datekey)


def index(records):
    """Group actions by person, newest first."""
    by_person = {}
    for r in records:
        by_person.setdefault(r["key"][:2], []).append(r)
    for k in by_person:
        by_person[k].sort(
            key=lambda r: (_datekey(r["effective"]),
                           REASON_RANK.get(r["reason"], 1)),
            reverse=True,
        )
    return by_person


def agency_matcher(directory_agencies, records):
    """Map each directory agency to the payroll agencies that could be it."""
    payroll = sorted({r["agency"] for r in records if r["agency"]})
    payroll_tokens = [(_agency_tokens(p), p) for p in payroll]
    out = {}
    for name in directory_agencies:
        want = _agency_tokens(name)
        if not want:
            continue
        hits = set()
        for have, p in payroll_tokens:
            if have and (want <= have or have <= want):
                hits.add(p)
        if hits:
            out[name] = hits
    return out


def lookup(person_name, agency, by_person, agency_map):
    """The person's latest personnel action, or None if it cannot be trusted.

    Returns None rather than a guess whenever identity is not corroborated —
    see the module docstring for why that bar is set where it is.
    """
    key = directory_name(person_name)
    if not key:
        return None
    actions = by_person.get(key[:2])
    if not actions:
        return None

    allowed = agency_map.get(agency, set())
    for a in actions:
        # A middle initial on both sides must agree.
        if key[2] and a["key"][2] and key[2] != a["key"][2]:
            continue
        if allowed and a["agency"] in allowed:
            return a
    return None


def onward_move(action, by_person):
    """Where someone went, when a departure is really a transfer.

    A resignation dated the same day as an appointment somewhere else is one
    person moving desks, not leaving government. Saying "resigned" flatly about
    those would be wrong in a way that matters — Howard Singer resigned from
    Correction and started at DCAS the same morning, and Sadye Campoamor left
    the comptroller's office for the Department of Education on one date.
    """
    if not action or action["reason"] not in DEPARTURES:
        return ""
    for other in by_person.get(action["key"][:2], []):
        if (other is not action
                and other["reason"] in ARRIVALS
                and other["effective"] == action["effective"]
                and other["agency"] != action["agency"]):
            return other["agency"].title()
    return ""


if __name__ == "__main__":
    recs = fetch()
    print(f"{len(recs)} personnel actions parsed")
    print(f"latest effective date in the feed: {latest_published(recs)}")
