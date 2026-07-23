#!/usr/bin/env python3
"""Build the data files behind the Green Book rebuild.

Two sources, both NYC Open Data, both fetched live every run:

  mdcw-n682  Greenbook            DCAS   ~2,600 named officials
  t3jq-9nkf  NYC Agencies and
             Governance Orgs      OTI    ~300 organizations

The Greenbook is the people layer: who holds which post, at which desk, on
which phone. It carries a four-level division hierarchy but says nothing about
how agencies relate to each other. The agencies dataset is the structure layer:
organization type, principal officer, and a `reports_to` edge that lets you
draw the actual shape of city government. Neither is much use alone. Joined,
they answer questions the city's own directory cannot.

Addresses are grouped rather than mapped: ~2,600 listings collapse onto ~200
addresses, which is what lets you ask who else sits at 1 Centre Street.

Every fetch fails loud. An empty or short response raises rather than writing a
thinner file over a good one.
"""

import csv
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data"

GREENBOOK_ID = "mdcw-n682"
AGENCIES_ID = "t3jq-9nkf"
DOMAIN = "https://data.cityofnewyork.us"

# Floors below which we assume something broke upstream rather than that the
# city genuinely shed two thirds of its officials overnight.
MIN_GREENBOOK_ROWS = 2000
MIN_AGENCY_ROWS = 200

UA = "nyc-green-book/1.0 (+https://github.com/joshgreenman1973/nyc-green-book)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA})


def log(msg):
    print(msg, flush=True)


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------

def fetch_dataset(dataset_id, minimum):
    """Pull every row plus the dataset's own last-updated stamp."""
    meta_url = f"{DOMAIN}/api/views/{dataset_id}.json"
    meta = SESSION.get(meta_url, timeout=60)
    meta.raise_for_status()
    meta = meta.json()

    rows, offset, limit = [], 0, 50000
    while True:
        url = f"{DOMAIN}/resource/{dataset_id}.json"
        params = {"$limit": limit, "$offset": offset}
        token = os.environ.get("SOCRATA_APP_TOKEN")
        headers = {"X-App-Token": token} if token else {}
        r = SESSION.get(url, params=params, headers=headers, timeout=120)
        if r.status_code == 403:
            # Keyless requests get throttled, not refused. Back off and retry.
            time.sleep(5)
            r = SESSION.get(url, params=params, headers=headers, timeout=120)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    if len(rows) < minimum:
        raise SystemExit(
            f"FATAL: {dataset_id} returned {len(rows)} rows, expected at least "
            f"{minimum}. Refusing to overwrite good data with a short read."
        )

    updated = datetime.fromtimestamp(
        meta["rowsUpdatedAt"], tz=timezone.utc
    ).isoformat()
    log(f"  {dataset_id}: {len(rows)} rows, city last updated {updated}")
    return rows, {"name": meta.get("name"), "updated": updated,
                  "rows": len(rows), "id": dataset_id}


# --------------------------------------------------------------------------
# press offices
# --------------------------------------------------------------------------

PRESS_URL = "https://www.nyc.gov/main/agency-press-contacts"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")


def fetch_press_contacts():
    """Named press officers and their email addresses, from NYC.gov.

    Neither Open Data feed carries a single email address. This page is the
    one place the city publishes working addresses for agency staff, so it is
    read verbatim: every address here was lifted from the rendered page, never
    inferred from a name. Anything that does not look like it came off the page
    is dropped rather than guessed at.
    """
    from bs4 import BeautifulSoup

    r = SESSION.get(PRESS_URL, headers={"User-Agent": BROWSER_UA}, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    email_re = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
    phone_re = re.compile(r"^[\d\s().+-]{7,}$")

    out = {}
    for item in soup.select(".cmp-accordion__item"):
        btn = item.select_one(".cmp-accordion__title, .cmp-accordion__button, button")
        panel = item.select_one(".cmp-accordion__panel")
        if not btn or not panel:
            continue
        agency = clean(btn.get_text(" ", strip=True))
        contacts = []
        for p in panel.find_all("p"):
            lines = [clean(l) for l in p.get_text("\n").split("\n") if clean(l)]
            email = next((l for l in lines if email_re.match(l)), "")
            if not email:
                continue
            phone = next((l for l in lines
                          if phone_re.match(l) and not email_re.match(l)), "")
            head = [l for l in lines if l not in (email, phone)]
            # "Last, First" in the first line, job title in the second.
            name, title = "", ""
            if head:
                first = head[0]
                if "," in first and len(first.split(",")) == 2:
                    last, given = [clean(x) for x in first.split(",")]
                    name = f"{given} {last}".strip()
                else:
                    name = first
                title = head[1] if len(head) > 1 else ""
            disp, tel = norm_phone(phone)
            contacts.append({"n": name, "t": title, "e": email,
                             "p": disp, "tel": tel})
        if contacts:
            out[agency] = contacts

    total = sum(len(v) for v in out.values())
    if not out:
        raise SystemExit(
            "FATAL: parsed 0 press contacts from nyc.gov. The page structure "
            "changed or the fetch was blocked. Not shipping a directory that "
            "silently lost its only email addresses."
        )
    log(f"  press contacts: {total} people across {len(out)} agencies")
    return out


# --------------------------------------------------------------------------
# normalize
# --------------------------------------------------------------------------

def clean(s):
    if not s:
        return ""
    # Socrata serves url-typed columns as {"url": "...", "description": "..."}.
    if isinstance(s, dict):
        s = s.get("url") or s.get("description") or ""
    if not isinstance(s, str):
        s = str(s)
    # Some NYC Open Data feeds serve UTF-8 already mangled into latin-1.
    if "Ã" in s or "Â" in s:
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return re.sub(r"\s+", " ", s).strip()


def fold(s):
    """Accent- and case-insensitive key for search and matching."""
    s = unicodedata.normalize("NFKD", clean(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def norm_phone(p):
    """Return (display, tel) — keeping vanity numbers like (212) NEW-YORK."""
    p = clean(p)
    if not p:
        return "", ""
    digits = re.sub(r"\D", "", p)
    letters = re.sub(r"[^A-Za-z]", "", p)
    if letters and len(digits) < 10:
        # Vanity number. Translate letters to keypad digits for the tel: link.
        keypad = {}
        for i, group in enumerate(
            ["ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"], start=2
        ):
            for ch in group:
                keypad[ch] = str(i)
        conv = "".join(keypad.get(c.upper(), c) for c in p if c.isalnum())
        return p, ("+1" + conv if len(conv) == 10 else "")
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}", "+1" + digits
    if len(digits) == 11 and digits[0] == "1":
        d = digits[1:]
        return f"({d[:3]}) {d[3:6]}-{d[6:]}", "+1" + d
    return p, ""


def norm_url(u):
    u = clean(u)
    if not u:
        return ""
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u.lstrip("/")
    return u


def person_name(r):
    first = clean(r.get("first_name"))
    last = clean(r.get("last_name"))
    mi = clean(r.get("m_i"))
    suffix = clean(r.get("name_suffix"))
    if first.lower() == "vacant" or last.lower() == "vacant":
        return "", True
    parts = [first]
    if mi:
        parts.append(mi if mi.endswith(".") else mi + ".")
    parts.append(last)
    name = " ".join(p for p in parts if p)
    if suffix:
        name += (", " if suffix.lower().rstrip(".") in ("jr", "sr", "esq", "phd",
                                                        "md", "iii", "ii")
                 else " ") + suffix
    return name.strip(), False


def division_path(r):
    """Greenbook stores the tree bottom-up across four columns. Flip it."""
    chain = [
        clean(r.get("great_grand_parentdivision")),
        clean(r.get("grand_parent_division")),
        clean(r.get("parent_division")),
        clean(r.get("division_name")),
    ]
    return [c for c in chain if c]


# --------------------------------------------------------------------------
# cross-link the two datasets
# --------------------------------------------------------------------------

STOP = {"of", "the", "department", "office", "nyc", "new", "york", "city",
        "commission", "board", "for", "and", "&"}


def match_key(name):
    toks = [t for t in fold(name).split() if t not in STOP]
    return " ".join(sorted(toks))


def link_agencies(agencies_by_name, org_rows):
    """Match Greenbook agencies to governance-dataset organizations.

    Exact acronym first, then a bag-of-significant-words key, then nothing.
    Deliberately conservative: an unmatched agency is reported as unmatched
    rather than guessed at.
    """
    by_acronym, by_key = {}, {}
    for o in org_rows:
        ac = fold(o.get("acronym", ""))
        if ac and ac not in by_acronym:
            by_acronym[ac] = o
        for nm in [o.get("name", "")] + [
            n for n in clean(o.get("alternate_or_former_names", "")).split(";") if n
        ]:
            k = match_key(nm)
            if k and k not in by_key:
                by_key[k] = o

    links, matched_ids = {}, set()
    for name, ag in agencies_by_name.items():
        o = None
        ac = fold(ag["acronym"])
        if ac and ac in by_acronym:
            o = by_acronym[ac]
        if o is None:
            o = by_key.get(match_key(name))
        if o is None:
            # "Transportation" -> "Department of Transportation"
            o = by_key.get(match_key("Department of " + name))
        if o:
            links[name] = o["record_id"]
            matched_ids.add(o["record_id"])
    log(f"  linked {len(links)}/{len(agencies_by_name)} Greenbook agencies "
        f"to governance records")
    return links, matched_ids


# --------------------------------------------------------------------------
# who runs it
# --------------------------------------------------------------------------

# Credentials and generational suffixes that are not part of a person's name.
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "esq", "esquire", "phd", "ph d",
            "md", "asa", "maaa", "cpa", "rn", "jd", "mpa", "mph", "msw",
            "aicp", "pe", "faia", "aia", "dr", "mba", "ed d", "edd"}

# Titles that mean "this person runs the place", most senior first. Matched
# against whole title segments, never as a loose prefix — "Chief of Detectives"
# and "Director, Communications" are emphatically not agency heads.
HEAD_TITLES = [
    "commissioner", "chancellor", "comptroller", "public advocate",
    "borough president", "district attorney", "mayor", "president",
    "chair", "chairman", "chairperson", "chairwoman",
    "executive director", "administrator", "director",
    "chief executive officer", "ceo", "executive secretary",
]

# Qualifiers that may precede a head title: "Police Commissioner",
# "Fire Commissioner", "Acting Commissioner".
HEAD_QUALIFIERS = {"police", "fire", "sanitation", "tax", "buildings",
                   "finance", "probation", "corporation", "city", "county",
                   "borough", "deputy mayor"}

# Anything starting with one of these reports to the head; it is not the head.
SUBORDINATE = re.compile(
    r"^(deputy|assistant|associate|first deputy|executive deputy|special|"
    r"senior|acting deputy|vice|under|sub)\b"
)


def strip_credentials(n):
    """Remove trailing degrees and honorifics: 'Martin MD, MPP' -> 'Martin'.

    Detected by shape rather than by list — a trailing all-caps token of two to
    five letters is a credential, not a surname. Names are title-cased in both
    sources, so this does not eat real names.
    """
    prev = None
    while n != prev:
        prev = n
        n = re.sub(r"[,\s]+(?:[A-Z]\.){2,}\.?$", "", n)          # P.E., Ph.D.
        n = re.sub(r"[,\s]+[A-Z]{2,5}\.?$", "", n)               # MD, MPP, ASA
        m = re.search(r"[,\s]+([A-Za-z]+)\.?$", n)
        if m and fold(m.group(1)) in SUFFIXES:
            n = n[: m.start()]
    return n.strip(" ,")


def name_parts(name):
    """Split a display name into (first, last), dropping suffixes/nicknames."""
    n = strip_credentials(clean(name))
    n = re.sub(r"[\"'‘’“”(]([^\"'‘’“”)]+)[\"'‘’“”)]", " ", n)  # 'Monte', (ta)
    n = n.replace(",", " ")
    toks = [t for t in fold(n).split() if t and t not in SUFFIXES]
    toks = [t for t in toks if len(t) > 1 or len(toks) <= 2]  # drop initials
    if not toks:
        return "", ""
    if len(toks) == 1:
        return "", toks[0]
    return toks[0], toks[-1]


def head_status(gb_name, gov_name):
    """agree | variant | differs | greenbook_only | governance_only | none."""
    if not gb_name and not gov_name:
        return "none"
    if gb_name and not gov_name:
        return "greenbook_only"
    if gov_name and not gb_name:
        return "governance_only"

    gf, gl = name_parts(gb_name)
    of, ol = name_parts(gov_name)
    if gl != ol:
        return "differs"
    if gf == of:
        return "agree"
    # Same surname, different given name: nickname or middle-name ordering.
    if gf and of and (gf.startswith(of) or of.startswith(gf)):
        return "agree"
    return "variant"


def head_rank(title):
    """How senior a job title is, or None if it isn't a head-of-agency title.

    Lower is more senior. A title qualified by a comma ("Director, Community
    Affairs") names a subordinate post and never scores.
    """
    raw = clean(title)
    if not raw or "," in raw:
        return None
    # Strip the acting/interim qualifier before anything else — an acting
    # commissioner is still the person running the agency.
    raw = re.sub(r"^\s*(acting|interim)\s*/?\s*(acting|interim)?\s+", "", raw,
                 flags=re.I)
    t = fold(raw)
    if not t or SUBORDINATE.match(t):
        return None
    # "Chief of Staff", "Chief of Detectives", "Chief of Patrol" — deputies of
    # a kind, whatever the org chart says.
    if t.startswith("chief of "):
        return None

    # Split the raw title, because folding has already eaten the separators.
    best = None
    for seg in re.split(r"\s*/\s*|\s*&\s*|\s+\band\b\s+", raw, flags=re.I):
        seg = fold(seg).strip()
        if not seg or SUBORDINATE.match(seg):
            continue
        for i, want in enumerate(HEAD_TITLES):
            if seg == want:
                best = i if best is None else min(best, i)
            elif seg.endswith(" " + want):
                # "Police Commissioner" yes, "Engineering Director" no.
                if seg[: -(len(want) + 1)] in HEAD_QUALIFIERS:
                    best = i if best is None else min(best, i)
    return best


def greenbook_head(people, agency, gov_title=""):
    """The Green Book listing most likely to be the agency's head.

    Prefers an exact match on the governance dataset's own officer title, then
    the most senior canonical head title. Only considers listings at the top of
    the agency rather than inside a division, and returns nothing rather than
    guessing — an agency with no head listed is a fact worth reporting.
    """
    top = [p for p in people if p["a"] == agency and not p["d"] and p["n"]]
    if not top:
        return None

    if gov_title:
        gt = fold(gov_title)
        for p in top:
            if fold(p["t"]) == gt:
                return p

    ranked = [(head_rank(p["t"]), p) for p in top]
    ranked = [(r, p) for r, p in ranked if r is not None]
    if not ranked:
        return None
    return min(ranked, key=lambda rp: rp[0])[1]


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    log("Fetching NYC Open Data...")
    gb_rows, gb_meta = fetch_dataset(GREENBOOK_ID, MIN_GREENBOOK_ROWS)
    org_rows, org_meta = fetch_dataset(AGENCIES_ID, MIN_AGENCY_ROWS)
    (RAW / "greenbook.json").write_text(json.dumps(gb_rows))
    (RAW / "agencies.json").write_text(json.dumps(org_rows))

    log("Fetching published press contacts...")
    press = fetch_press_contacts()
    (RAW / "press.json").write_text(json.dumps(press, indent=1))

    # ---- addresses ----------------------------------------------------
    addr_index = {}
    for r in gb_rows:
        a, c = clean(r.get("address")), clean(r.get("city"))
        if not a:
            continue
        z = clean(r.get("zip_code"))
        key = fold(f"{a}|{c}|{z}")
        addr_index.setdefault(key, {
            "key": key, "address": a, "city": c,
            "state": clean(r.get("state")), "zip": z,
        })
    log(f"  {len(addr_index)} distinct addresses")

    # ---- people -------------------------------------------------------
    log("Building people, agencies, buildings...")
    people = []
    agencies = {}
    for i, r in enumerate(gb_rows):
        agency = clean(r.get("agency_name"))
        if not agency:
            continue
        name, vacant = person_name(r)
        path = division_path(r)
        a, c, z = clean(r.get("address")), clean(r.get("city")), clean(r.get("zip_code"))
        akey = fold(f"{a}|{c}|{z}") if a else ""

        p1, tel1 = norm_phone(r.get("phone_1"))
        p2, tel2 = norm_phone(r.get("phone_2"))
        dphone, dtel = norm_phone(r.get("division_primary_phone"))
        fax, _ = norm_phone(r.get("fax_1"))

        ag = agencies.setdefault(agency, {
            "name": agency,
            "acronym": clean(r.get("agency_acronym")),
            "website": norm_url(r.get("agency_website")),
            "section": clean(r.get("section")),
            "phone": "", "tel": "",
            "count": 0, "vacant": 0, "divisions": {}, "addresses": Counter(),
        })
        if not ag["phone"]:
            ag["phone"], ag["tel"] = norm_phone(r.get("agency_primary_phone"))
        ag["count"] += 1
        if vacant:
            ag["vacant"] += 1
        if akey:
            ag["addresses"][akey] += 1

        people.append({
            "i": i,
            "n": name,
            "t": clean(r.get("office_title")),
            "a": agency,
            "d": path,
            "p": p1, "tel": tel1,
            "p2": p2, "tel2": tel2,
            "dp": dphone, "dtel": dtel,
            "fx": fax,
            "ak": akey,
            "v": 1 if vacant else 0,
            "s": clean(r.get("section")),
        })

    # ---- division trees -------------------------------------------------
    for p in people:
        ag = agencies[p["a"]]
        node = ag["divisions"]
        for seg in p["d"]:
            node = node.setdefault(seg, {"_n": 0, "_c": {}})
            node["_n"] += 1
            node = node["_c"]

    def tree_to_list(node):
        out = []
        for k, v in sorted(node.items(), key=lambda kv: -kv[1]["_n"]):
            out.append({"name": k, "n": v["_n"], "c": tree_to_list(v["_c"])})
        return out

    # ---- organizations + org chart -------------------------------------
    orgs = []
    for o in org_rows:
        orgs.append({
            "id": o.get("record_id", ""),
            "name": clean(o.get("name")),
            "acronym": clean(o.get("acronym")),
            "type": clean(o.get("organization_type")),
            "status": clean(o.get("operational_status")),
            "url": norm_url(o.get("url")),
            "officer": clean(o.get("principal_officer_full_name")),
            "officer_title": clean(o.get("principal_officer_title")),
            "officer_url": norm_url(o.get("principal_officer_contact")),
            "reports_to": [clean(x) for x in
                           clean(o.get("reports_to")).split(";") if clean(x)],
            "alt": [clean(x) for x in
                    clean(o.get("alternate_or_former_names")).split(";") if clean(x)],
            "in_chart": bool(o.get("in_org_chart")),
        })

    # reports_to is written as free text naming another organization. Resolve
    # it to record ids where we can; keep the raw string where we cannot.
    org_by_key = {}
    for o in orgs:
        for nm in [o["name"]] + o["alt"]:
            k = match_key(nm)
            if k:
                org_by_key.setdefault(k, o["id"])
    for o in orgs:
        o["parents"] = []
        for raw in o["reports_to"]:
            pid = org_by_key.get(match_key(raw))
            o["parents"].append({"id": pid, "label": raw})

    links, matched_ids = link_agencies(agencies, org_rows)

    # ---- buildings -------------------------------------------------------
    per_addr = Counter(p["ak"] for p in people if p["ak"])
    addr_agencies = defaultdict(Counter)
    for p in people:
        if p["ak"]:
            addr_agencies[p["ak"]][p["a"]] += 1

    buildings = []
    for key, meta in addr_index.items():
        buildings.append({
            "k": key,
            "addr": meta["address"],
            "city": meta["city"],
            "state": meta["state"],
            "zip": meta["zip"],
            "n": per_addr.get(key, 0),
            "ags": [{"name": a, "n": n}
                    for a, n in addr_agencies[key].most_common()],
        })
    buildings.sort(key=lambda b: -b["n"])

    # ---- attach press offices ---------------------------------------------
    # NYC.gov names agencies its own way ("Children's Services", "Parks &
    # Recreation") and the Green Book names them another ("Children's Services,
    # Administration for", "Parks, NYC"). Match on token containment rather
    # than equality, and require the shared tokens to be distinctive.
    # Words that describe the form of an organization rather than identify it.
    # "Department of Correction" and "Correction" are the same agency; "Board
    # of Correction" is a different body entirely, so board/commission/fund and
    # their kin are never dropped.
    # Words describing the form of an organization rather than identifying it.
    # "Department of Correction" and "Correction" are one agency. "Board of
    # Correction" is a different body, so board/commission/authority and their
    # kin are deliberately absent here and left in as distinguishing words.
    FORM_WORDS = {"department", "administration", "office", "nyc", "new",
                  "york", "city", "dept", "of", "the", "for", "and"}

    def toks(s):
        return {t for t in fold(s).split()
                if len(t) > 1 and t not in FORM_WORDS}

    press_index = [(toks(n), n, c) for n, c in press.items()]
    press_hits = 0
    press_matched = set()

    def find_press(agency_name, acronym):
        """Match only when the Green Book name adds nothing distinguishing.

        NYC.gov writes press-office names loosely ("Parks & Recreation" for
        what the Green Book calls "Parks, NYC"), so the press name may carry
        extra words. The reverse is not safe: a word in the agency name that
        the press name lacks usually means a different body — which is why
        Campaign Finance Board does not match the Finance press office, and
        the Board of Correction does not match Correction's.

        The acronym is tried as an alternative, never merged into the name.
        """
        best, best_score = (None, None), 0.0
        for candidate in (toks(agency_name), toks(acronym) if acronym else set()):
            if not candidate:
                continue
            for pt, pname, contacts in press_index:
                if not pt or not candidate.issubset(pt):
                    continue
                score = len(candidate) / len(pt)  # tightest fit wins
                if score > best_score:
                    best, best_score = (pname, contacts), score
            if best_score:
                break  # a name match beats an acronym match
        return best

    # ---- agency payload ---------------------------------------------------
    agency_list = []
    for name, ag in sorted(agencies.items()):
        pname, pc = find_press(name, ag["acronym"])
        if pc:
            press_hits += 1
            press_matched.add(pname)
        agency_list.append({
            "press": pc or [],
            "press_name": pname or "",
            "name": name,
            "acronym": ag["acronym"],
            "website": ag["website"],
            "section": ag["section"],
            "phone": ag["phone"], "tel": ag["tel"],
            "n": ag["count"], "vacant": ag["vacant"],
            "org": links.get(name),
            "tree": tree_to_list(ag["divisions"]),
            "addrs": [k for k, _ in ag["addresses"].most_common()],
        })

    # ---- what each dataset knows that the other doesn't -------------------
    org_by_id = {o["id"]: o for o in orgs}
    gaps = {
        # Organizations the city lists in its governance inventory but that
        # have no personnel listing in the Green Book at all.
        "orgs_without_listings": sorted(
            [{"id": o["id"], "name": o["name"], "type": o["type"],
              "officer": o["officer"], "url": o["url"]}
             for o in orgs if o["id"] not in matched_ids],
            key=lambda o: o["name"],
        ),
        # Green Book agencies absent from the governance inventory.
        "listings_without_org": sorted(
            [{"name": a["name"], "acronym": a["acronym"], "n": a["n"],
              "section": a["section"]}
             for a in agency_list if not a["org"]],
            key=lambda a: -a["n"],
        ),
    }

    # Who runs each agency, according to each source independently.
    #
    # Both datasets name agency heads and they do not always agree. Most
    # apparent disagreements are cosmetic — "Jonathan Darche" against
    # "Jonathan Darche, Esq.", "Sam Levine" against "Samuel A. Levine" — so
    # comparison is done on stripped surnames with nicknames tolerated, and
    # anything short of a real difference of person is labelled a variant.
    heads = []
    for a in agency_list:
        o = org_by_id.get(a["org"]) if a["org"] else None
        gb = greenbook_head(people, a["name"], o["officer_title"] if o else "")
        gov = o["officer"] if o and o["officer"] else ""
        status = head_status(gb["n"] if gb else "", gov)
        heads.append({
            "agency": a["name"],
            "acronym": a["acronym"],
            "n": a["n"],
            "org": a["org"],
            "gb": {"n": gb["n"], "t": gb["t"], "p": gb["p"], "tel": gb["tel"]}
                  if gb else None,
            "gov": {"n": gov, "t": o["officer_title"] if o else "",
                    "url": o["officer_url"] if o else ""} if gov else None,
            "status": status,
        })
    # ---- resolve the disagreements ----------------------------------------
    # The governance inventory is maintained continuously and is the better
    # source on who currently holds a post; the Green Book lags on political
    # appointees. But it is not uniformly fresher, and there is one signal that
    # reliably says so: when the Green Book calls someone Acting or Interim, it
    # is reporting a vacancy the governance file has not caught up with, and
    # its name is the newer one. Governance wins by default, the Green Book
    # wins on that signal, and both names are always kept.
    ACTING = re.compile(r"\b(acting|interim)\b", re.I)
    applied = 0
    for h in heads:
        if h["status"] != "differs":
            continue
        gb_acting = bool(ACTING.search(h["gb"]["t"]))
        h["use"] = "greenbook" if gb_acting else "governance"
        h["why"] = ("The Green Book names an acting officeholder, which the "
                    "governance dataset has not registered."
                    if gb_acting else
                    "The governance dataset is maintained continuously; the "
                    "Green Book lags on political appointees.")
        if h["use"] == "governance":
            # Rewrite the person record, keeping the superseded name attached.
            for p in people:
                if p["a"] == h["agency"] and p["n"] == h["gb"]["n"] \
                        and p["t"] == h["gb"]["t"]:
                    p["alt"] = {"n": p["n"], "src": "Green Book"}
                    p["n"] = h["gov"]["n"]
                    p["src"] = "governance"
                    applied += 1
                    break
        else:
            for p in people:
                if p["a"] == h["agency"] and p["n"] == h["gb"]["n"] \
                        and p["t"] == h["gb"]["t"]:
                    p["alt"] = {"n": h["gov"]["n"], "src": "governance dataset"}
                    break

    log(f"  applied {applied} governance names over the Green Book; "
        f"kept {sum(1 for h in heads if h.get('use') == 'greenbook')} "
        f"Green Book acting officeholders")

    heads.sort(key=lambda h: (h["status"] != "differs", -h["n"]))
    conflicts = [h for h in heads if h["status"] == "differs"]

    # ---- write ------------------------------------------------------------
    built = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "built": built,
        "sources": {"greenbook": gb_meta, "agencies": org_meta},
        "stats": {
            "people": len(people),
            "named": sum(1 for p in people if p["n"]),
            "vacant": sum(1 for p in people if p["v"]),
            "agencies": len(agency_list),
            "orgs": len(orgs),
            "buildings": len(buildings),
            "phones": sum(1 for p in people if p["p"]),
            "linked": len(links),
            "press_agencies": press_hits,
            "press_emails": sum(len(v) for v in press.values()),
        },
        "people": people,
        "agencies": agency_list,
        "orgs": orgs,
        "buildings": buildings,
        "gaps": gaps,
        "heads": heads,
        # Every press office, including those that do not line up with a Green
        # Book agency — a Parks press secretary is worth finding whether or not
        # the two directories agree on what Parks is called.
        "press": [
            {"office": name, "contacts": contacts,
             "linked": name in press_matched}
            for name, contacts in sorted(press.items())
        ],
    }
    (OUT / "greenbook.json").write_text(json.dumps(payload, separators=(",", ":")))

    # A flat CSV, because a directory you cannot take away with you is a
    # worse directory. The city publishes no such export.
    with open(OUT / "greenbook.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "title", "agency", "acronym", "division_path",
                    "phone", "phone_2", "division_phone", "fax", "address",
                    "city", "state", "zip", "section", "vacant",
                    "name_source", "other_source_name"])
        abyk = {b["k"]: b for b in buildings}
        for p in people:
            b = abyk.get(p["ak"], {})
            ag = next((a for a in agency_list if a["name"] == p["a"]), {})
            w.writerow([
                p["n"] or "(vacant)", p["t"], p["a"], ag.get("acronym", ""),
                " > ".join(p["d"]), p["p"], p["p2"], p["dp"], p["fx"],
                b.get("addr", ""), b.get("city", ""), b.get("state", ""),
                b.get("zip", ""), p["s"], "yes" if p["v"] else "",
                "governance dataset" if p.get("src") else "Green Book",
                (p.get("alt") or {}).get("n", ""),
            ])

    s = payload["stats"]
    log("")
    log(f"Wrote {OUT/'greenbook.json'}")
    log(f"  {s['people']} listings ({s['named']} named, {s['vacant']} vacant)")
    log(f"  {s['agencies']} agencies, {s['orgs']} governance organizations "
        f"({s['linked']} linked)")
    log(f"  {s['buildings']} distinct addresses")
    log(f"  {s['phones']} direct phone numbers")
    log(f"  {len(gaps['orgs_without_listings'])} organizations with no "
        f"Green Book agency listing")
    hs = Counter(h["status"] for h in heads)
    log(f"  agency heads: {dict(hs)}")


if __name__ == "__main__":
    sys.exit(main())
