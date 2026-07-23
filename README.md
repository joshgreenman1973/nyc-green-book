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
- **Who runs what** — the two datasets that name agency heads disagree about 16
  of them. Knowing which ones before you call is the point.
- **Vacancies** — 128 posts the city lists with nobody in them, grouped by
  agency.
- **Addresses** — 2,609 listings sit at 200 addresses. Tap one to see every
  agency that answers there.
- **[Download the whole thing as CSV](https://joshgreenman1973.github.io/nyc-green-book/data/greenbook.csv).**
  The city offers no export.

## Sources

Three, all official, all re-fetched on every build:

- **Greenbook** (`mdcw-n682`), Dept. of Citywide Administrative Services
- **NYC Agencies and Governance Organizations** (`t3jq-9nkf`), Office of
  Technology and Innovation
- **[Agency press contacts](https://www.nyc.gov/main/agency-press-contacts)**,
  NYC.gov

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
directory. A GitHub Action reruns it weekly and commits only on change.

## Not affiliated with the City of New York

Built from NYC Open Data and NYC.gov. The official directory remains at
[a856-gbol.nyc.gov](https://a856-gbol.nyc.gov/GBOLWebsite/GreenBook/Online).
