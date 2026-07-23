# Methodology

How this directory is assembled, what it claims, and where it can be wrong.

Everything below is reproducible: `python3 scripts/build.py` fetches all three
sources live and rewrites `docs/data/`. Nothing is hand-edited, and no data file
is committed that the script cannot regenerate.

## Sources

| Source | Publisher | What it gives | Rows |
|---|---|---|---|
| [Greenbook](https://data.cityofnewyork.us/City-Government/Greenbook/mdcw-n682) (`mdcw-n682`) | Dept. of Citywide Administrative Services | People: name, title, division, address, direct phone | 2,609 |
| [NYC Agencies and Governance Organizations](https://data.cityofnewyork.us/dataset/t3jq-9nkf) (`t3jq-9nkf`) | Office of Technology and Innovation | Structure: organization type, principal officer, `reports_to` | 306 |
| [Agency press contacts](https://www.nyc.gov/main/agency-press-contacts) | NYC.gov | Named press officers with email addresses | 82 people / 60 offices |

The two Open Data feeds are complementary and neither is sufficient alone. The
Greenbook knows who sits where and on what phone number but nothing about how
agencies relate to one another. The governance dataset knows the shape of city
government but names only one officer per organization. Joining them is most of
the value here.

The press-contacts page exists in this build for one reason: **neither open
dataset contains a single email address.** If you want to email someone in New
York City government, the city's own directory cannot help you.

## What the build does

**Fetches live, fails loud.** Every run re-fetches all three sources. A response
shorter than a floor (2,000 Greenbook rows, 200 organizations, 1 press contact)
raises and aborts rather than overwriting good data with a short read. A silent
partial fetch is the failure mode that quietly rots a directory, so it is
treated as fatal.

**Normalizes.** Names are assembled from the five columns the Greenbook splits
them across. Phone numbers are reformatted and given `tel:` links, including
vanity numbers — `(212) NEW-YORK` and `1-800-CUNY-YES` are translated to
keypad digits so they dial. Websites get a scheme. Text is repaired where NYC
Open Data has served UTF-8 already mangled into latin-1.

**Rebuilds the division tree.** The Greenbook stores a four-level hierarchy
bottom-up across four columns (`division_name`, `parent_division`,
`grand_parent_division`, `great_grand_parentdivision`). These are inverted back
into a real tree per agency. In the current data the hierarchy runs three levels
deep; the fourth column is empty throughout.

**Groups addresses.** 2,609 listings collapse onto 200 distinct addresses, which
is what makes "who else works at 1 Centre Street" answerable. Addresses are
grouped as published text — nothing is geocoded and there is no map.

**Links the two datasets.** Greenbook agencies are matched to governance
organizations by acronym, then by a bag-of-significant-words key that ignores
`of`/`the`/`department`/`office`. 90 of 124 agencies match. Unmatched agencies
are reported as unmatched rather than guessed at.

## The one claim this site makes on its own

Both datasets name agency heads, and they do not always name the same person.
Working out which of those differences are real is the only inference here, and
it is the only place the site can be wrong in a way that reflects on a named
individual. So it is deliberately strict.

**Finding the head.** Only listings at the top of an agency (no division) are
considered. A title qualifies as head only if the whole title is a head title —
`Commissioner`, `Chancellor`, `Executive Director`, `Police Commissioner`,
`President & CEO`, and so on, with `Acting`/`Interim` stripped first. A title
carrying a comma (`Director, Communications`) names a subordinate post and never
qualifies. Neither does anything beginning `Deputy`, `Assistant`, `Associate`,
`First Deputy`, `Executive Deputy` or `Special`, nor `Chief of ...` — Chief of
Staff and Chief of Detectives are not agency heads however senior they are. If
no title qualifies, the site reports that no head is listed rather than picking
the most senior-sounding name available.

**Comparing names.** Surnames are compared after stripping credentials and
honorifics by shape rather than by list: a trailing all-caps token of two to
five letters is a credential. So `Alister F. Martin MD, MPP` and
`Alister Martin` are one person, as are `Jonathan Darche, Esq.` and
`Jonathan Darche`. Given names are compared with nicknames tolerated by prefix
(`Sam`/`Samuel`), quoted nicknames dropped, and middle names ignored.

**Outcomes.** Every agency lands in one of six states, of which only `differs`
asserts a genuine disagreement:

| Status | Agencies | Meaning |
|---|---|---|
| `agree` | 59 | Both sources name the same person |
| `differs` | 16 | The sources name different people |
| `none` | 29 | Neither source names a head |
| `governance_only` | 13 | Only the governance dataset names one |
| `greenbook_only` | 7 | Only the Green Book names one |
| `variant` | 0 | Same surname, unrelated given name |

`scripts/test_matching.py` holds 38 cases covering every rule above. Run it
before trusting a change to the comparison logic:

```bash
python3 scripts/test_matching.py
```

**What a disagreement does not mean.** It tells you the two city files differ.
It does not tell you which one is right, and it is not evidence that either
official is or is not in post. Treat a flag as a reason to check, never as a
finding. During a mayoral transition both files lag reality in different places
and at different speeds.

## Email addresses

The rule is absolute: **an address enters this directory only if it was read
verbatim off a page the city published.** None is inferred from a name pattern,
none comes from a broker or a social profile, and none is carried over from an
older scrape. This is not a theoretical concern — a language model asked to
summarize a contact page will cheerfully return a plausible, wrong address that
follows the right pattern.

In practice that means:

- The 82 press-office addresses are parsed out of the rendered NYC.gov page
  structure, not regexed out of raw HTML (which picks up tag-boundary artifacts
  like `nARudansky@buildings.nyc.gov`).
- No individual official in the Greenbook has an email address here, because the
  city does not publish one. Their entries link to the agency's official contact
  page instead, where the city publishes one.
- Press offices are labeled as press offices. They are the right door for a
  reporter and the wrong one for a complaint about a pothole.

Press offices are matched to Green Book agencies conservatively. NYC.gov and the
Green Book name agencies differently, so a press name may carry extra words
(`Parks & Recreation` for `Parks, NYC`) — but the reverse is treated as a
warning. If the Green Book name carries a distinguishing word the press name
lacks, it is a different body: **Campaign Finance Board** does not get the
Finance press office, the **Board of Correction** does not get Correction's, and
the **Fire Museum** does not get the Fire Department's. Words describing
organizational form (`department`, `administration`, `office`) are ignored;
words that distinguish one body from another (`board`, `commission`,
`authority`, `corporation`, `fund`, `museum`) never are. 39 of 124 agencies get
a press office; the other 21 press offices remain searchable on their own.

## Known limits

- **The open dataset is narrower than the website.** Green Book Online also
  covers Federal, State and International listings. `mdcw-n682` carries only
  City (2,367), County (131) and Courts (111).
- **216 governance organizations have no Green Book agency listing.** Most are
  advisory boards, nonprofits and mayoral offices that appear inside another
  agency's division tree rather than as agencies of their own. The count is a
  measure of how differently the two files are organized, not of 216 missing
  bodies.
- **Freshness is the city's, not this site's.** The build stamps each source
  with the city's own `rowsUpdatedAt`. If the Green Book is three months stale
  on an agency, so is this.
- **Vacancies are as listed.** 128 posts carry the literal name "Vacant". That
  is the city's assertion about its own staffing, reproduced, not verified.
- **No emails for individuals, by design.** See above. This will look like a
  gap. It is the city's gap, and filling it by guessing would be worse than
  leaving it open.

## Rebuilding

```bash
pip install requests beautifulsoup4
python3 scripts/test_matching.py
python3 scripts/build.py
```

Writes `docs/data/greenbook.json` and `docs/data/greenbook.csv`. A GitHub Action
runs the same commands weekly and commits only when the output changes.
