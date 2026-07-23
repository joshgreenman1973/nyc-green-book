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

### Which name gets shown

For the 16 `differs` agencies the directory has to display one name, and it
shows the **governance dataset's**. That file is maintained continuously — the
Office of Technology and Innovation takes corrections through a public form —
while the Green Book lags on political appointees. 12 listings are rewritten
this way.

**Except where the Green Book says `Acting` or `Interim`.** That is the Green
Book reporting a departure the governance file has not registered, which makes
it the newer source for that post, so its name wins. This applies to 4 agencies:
Investigation, Design and Construction, Taxi & Limousine, and the Board of
Correction. The rule is worth stating because it is the counter-example to the
default: neither file is uniformly fresher, and the acting/interim flag is the
one reliable signal of which one moved last.

**Nothing is discarded.** Every rewritten listing keeps the superseded name, and
both names stay searchable — searching "Cumbo" lands on the Cultural Affairs
commissioner's post and shows Diya Vij holds it, with the Green Book's name
struck through. In the CSV this is the `name_source` and `other_source_name`
columns. In the JSON it is `src` and `alt` on the person record.

**One caveat.** A direct phone number belongs to the desk, not the person. On a
post that has changed hands the line may still reach the predecessor's office.

`scripts/test_matching.py` holds 38 cases covering every rule above. Run it
before trusting a change to the comparison logic:

```bash
python3 scripts/test_matching.py
```

**What a disagreement does not mean.** The rule above picks the likelier of two
official answers; it does not verify either against reality, and it is not
evidence that any individual is or is not in post. During a mayoral transition
both files lag in different places and at different speeds. Treat a flagged post
as a reason to check, never as a finding.

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

Writes `docs/data/greenbook.json` and `docs/data/greenbook.csv`.

### Refresh cadence

The directory follows Open Data rather than a calendar. `scripts/check_freshness.py`
reads each dataset's own `rowsUpdatedAt` — two metadata requests, no row data —
and compares it to the stamps recorded in the last build. A GitHub Action runs
that check **every four hours** and rebuilds only when the city has actually
published something. This matters: the Green Book moved twice in the week this
was built, so a weekly schedule would have served stale data for days.

A **Monday run is forced** regardless, because the NYC.gov press-contacts page
carries no update stamp and the only way to catch a change there is to look.

The check fails open: if it cannot reach Socrata it exits 2 and the rebuild runs
anyway, on the principle that a redundant build is cheaper than a missed one.
The build itself commits only when the output actually differs, so a restamped
source with unchanged rows produces no commit.
