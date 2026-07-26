# The Green Book

The City of New York's official directory, rebuilt as something you can actually
search.

**Live: https://joshgreenman1973.github.io/nyc-green-book/**

2,609 officials, 124 agencies, 2,123 direct phone numbers — every one of them a
tap away from a call — and the 82 email addresses the city publishes for its
press offices. One search box over all of it.

## Why

[Green Book Online](https://a856-gbol.nyc.gov/GBOLWebsite/GreenBook/Online) is
the city's own directory and the data underneath it is good. Reaching it is the
problem: you pick a category, then a subcategory, then wait for a page to
reload. There is no export, no way to call a number from a phone, no way to link
to a listing, and no way to search across everything at once.

This is the same public data, reorganized:

- **One box searches everything** — people, titles, agencies, divisions,
  addresses and press offices. Paste in a number a city line called you from
  and it works in reverse too.
- **Every number dials.** Including vanity numbers — `(212) NEW-YORK` and
  `1-800-CUNY-YES` are translated to keypad digits.
- **Every press office emails.** The city publishes these; neither open dataset
  does.
- **Built for a phone.** Big tap targets, a swipe-away detail sheet, dark mode.
- **Who runs what** — the two directories disagree about 15 agency heads, and
  neither carries a date. The City Record does, so where it has published an
  appointment it settles the question. It cuts both ways: it confirms governance
  at Cultural Affairs and overrules it at City Planning. Unsettled conflicts say
  so. Both names are kept and both stay searchable — search `Cumbo` and you land
  on the Cultural Affairs post with Diya Vij in it.
- **Already gone** — 42 people the Green Book still lists have left the job it
  lists them in, found by matching the directory against the City Record. 14 of
  them moved to another agency rather than leaving, and the site says where.
- **Vacancies** — 128 posts the city lists with nobody in them, grouped by
  agency.
- **Addresses** — 2,609 listings sit at 200 addresses. Tap one to see every
  agency that answers there.
- **[Download the whole thing as CSV](https://joshgreenman1973.github.io/nyc-green-book/data/greenbook.csv).**
  The city offers no export.
- **[The mayoral administration as a contact list](https://joshgreenman1973.github.io/nyc-green-book/data/mayoral_administration.csv)**
  — 62 people: the mayor, the deputy mayors, the chief of staff and every agency
  head under them, with direct lines where published. Separately elected offices
  are excluded on purpose. The email column is blank because the city publishes
  no email address for any of these posts.

## Sources

Three, all official, all re-fetched on every build:

- **Greenbook** (`mdcw-n682`), Dept. of Citywide Administrative Services
- **NYC Agencies and Governance Organizations** (`t3jq-9nkf`), Office of
  Technology and Innovation
- **[Agency press contacts](https://www.nyc.gov/main/agency-press-contacts)**,
  NYC.gov
- **City Record — Changes in Personnel** (`dg92-zbpx`), the city's legally
  required record of every appointment and departure, with effective dates

No email address here was ever inferred from a name pattern. Every one was read
off a page the city published. See [METHODOLOGY.md](METHODOLOGY.md) for how the
sources are joined, how agency heads are compared, and where this can be wrong.

## Build

```bash
pip install requests beautifulsoup4
python3 scripts/test_matching.py   # 38 cases over the name/title matching
python3 scripts/build.py           # rewrites docs/data/
```

The build fails loudly on a short read rather than quietly shipping a thinner
directory.

**Refresh follows Open Data, not a calendar.** A GitHub Action checks each
dataset's own `rowsUpdatedAt` every four hours and rebuilds only when the city
has published something — the Green Book moved twice in the week this was built,
so weekly would have meant days of stale data. Mondays run regardless, because
the NYC.gov press page carries no update stamp.

```bash
python3 scripts/check_freshness.py   # exit 0 = rebuild, 1 = nothing new
```

## Not affiliated with the City of New York

Built from NYC Open Data and NYC.gov. The official directory remains at
[a856-gbol.nyc.gov](https://a856-gbol.nyc.gov/GBOLWebsite/GreenBook/Online).
