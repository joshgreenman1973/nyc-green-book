#!/usr/bin/env python3
"""Tests for the two judgement calls in the build: is this the same person,
and is this title an agency head?

Both feed the "who runs it" comparison, which is the one place the site makes
a claim the underlying data does not make on its own. A false positive there
puts a wrong accusation of staleness next to a named official, so the bar is
that every case below must hold.

Run: python3 scripts/test_matching.py
"""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build", Path(__file__).parent / "build.py"
)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

# (greenbook name, governance name, expected status)
NAME_CASES = [
    # Same person, written differently. These must never read as a conflict.
    ("Alister F. Martin MD, MPP", "Alister Martin", "agree"),
    ("Jonathan Darche, Esq.", "Jonathan Darche", "agree"),
    ("Samuel A. Levine", "Sam Levine", "agree"),
    ("Carolyn Lisa Miller", "Carolyn Miller", "agree"),
    ("Marek Tyszkiewicz ASA, MAAA", "Marek Tyszkiewicz", "agree"),
    ("Donovan J. Richards Jr.", "Donovan Richards", "agree"),
    ("Rebecca Jones Gaston", "Rebecca Gaston", "agree"),
    ("Mercer 'Monte' Givhan", "Mercer Givhan", "agree"),
    ("Andrew Kimball", "Andrew Kimball", "agree"),
    # Genuinely different people.
    ("Laurie Cumbo", "Diya Vij", "differs"),
    ("Eduardo del Valle P.E.", "Paul Ochoa", "differs"),
    ("Pauline Toole", "Shawn(ta) Smith-Cruz", "differs"),
    # Same surname, unrelated given name: flagged softly, not as a conflict.
    ("Robert Ochoa", "Paul Ochoa", "variant"),
    # One-sided.
    ("Jane Doe", "", "greenbook_only"),
    ("", "Jane Doe", "governance_only"),
    ("", "", "none"),
]

# (title, is it a head-of-agency title)
TITLE_CASES = [
    ("Commissioner", True),
    ("Police Commissioner", True),
    ("Acting Commissioner", True),
    ("Commissioner and Chair", True),
    ("Chief Technology Officer & Commissioner", True),
    ("President & CEO", True),
    ("Executive Director", True),
    ("Director", True),
    ("Chancellor", True),
    ("Borough President", True),
    # Not heads, however senior they sound.
    ("Deputy Commissioner", False),
    ("First Deputy Commissioner", False),
    ("Assistant Commissioner", False),
    ("Executive Deputy Commissioner", False),
    ("Chief of Staff", False),
    ("Chief of Detectives", False),
    ("Chief of Department", False),
    ("Director, Communications", False),
    ("Director, Administration, Secretary of the Commission", False),
    ("General Counsel", False),
    ("Chief Operating Officer", False),
    ("Deputy Commissioner, Legal Matters", False),
]


def main():
    fails = []
    for gb, gov, want in NAME_CASES:
        got = b.head_status(gb, gov)
        if got != want:
            fails.append(f"name: {gb!r} vs {gov!r} -> {got}, wanted {want}")
    for title, want in TITLE_CASES:
        got = b.head_rank(title) is not None
        if got != want:
            fails.append(f"title: {title!r} -> head={got}, wanted {want}")

    total = len(NAME_CASES) + len(TITLE_CASES)
    if fails:
        print(f"{len(fails)}/{total} FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print(f"{total}/{total} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
