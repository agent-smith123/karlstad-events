#!/usr/bin/env python3
"""
Enrich events.json with category field based on source name and known mappings.
Run this after fetching events to ensure all events have a category.
"""

import json
import re
from pathlib import Path

PROJ = Path(__file__).parent.parent
EVENTS_JSON = PROJ / "assets" / "data" / "events.json"

# Explicit source name → category
SOURCE_CATEGORY: dict[str, str] = {
    # Concerts / music
    "Karlstad CCC": "concert",
    "Nöjesfabriken": "concert",
    "Sundstaaulan": "concert",
    "Medis - Säffle Medborgarhus": "concert",
    "Medis Säffle": "concert",
    "Ritz Arvika": "concert",
    # Theater
    "Scalateatern": "theater",
    "Tempelriddaren": "theater",
    "Arenan Bibliotekshuset": "theater",
    "Arenan (Bibliotekshuset)": "theater",
    "Värmlandsteatern": "theater",
    "Karlstads Teater": "theater",
    # Opera
    "Wermland Opera": "opera",
    # Museum / exhibitions
    "Värmlands Museum": "museum",
    "Kristinehamns Konstmuseum": "museum",
    "Rackstadmuseet": "museum",
    # Cinema
    "Filmstaden Karlstad": "cinema",
    # Sport
    "Färjestad BK": "sport",
    "Löfbergs Arena": "sport",
    "SM-veckan 2026": "sport",
    # Park / nature
    "Mariebergsskogen": "park",
}

# Pattern-based fallbacks (checked in order)
SOURCE_PATTERNS: list[tuple[str, str]] = [
    (r"opera", "opera"),
    (r"teater|theater", "theater"),
    (r"konsert|concert|musik|nöjes|ccc|aul[ae]n|medis|ritz|medborgarhus", "concert"),
    (r"bio|film|cinema|filmstaden", "cinema"),
    (r"museum|konstmuseum|konsthal", "museum"),
    (r"sport|idrotts|hockey|fotboll|bandy|simhall|arena", "sport"),
    (r"bibliotek|library", "library"),
    (r"festival", "festival"),
]


def get_category(source: str) -> str:
    """Return a category for the given source string."""
    if not source:
        return "other"

    # Exact match first
    if source in SOURCE_CATEGORY:
        return SOURCE_CATEGORY[source]

    # Pattern match (case-insensitive on normalized source)
    s = source.lower()
    for pattern, cat in SOURCE_PATTERNS:
        if re.search(pattern, s):
            return cat

    # Visit Värmland events are broadly "culture"
    if "visit värmland" in s or "visitvarmland" in s:
        return "culture"

    return "other"


def main():
    with open(EVENTS_JSON) as f:
        events = json.load(f)

    before_missing = sum(1 for e in events if not e.get("category"))
    print(f"Events without category before enrichment: {before_missing}/{len(events)}")

    for event in events:
        if not event.get("category"):
            event["category"] = get_category(event.get("source", ""))

    after_missing = sum(1 for e in events if not e.get("category"))
    print(f"Events without category after enrichment:  {after_missing}/{len(events)}")

    # Show distribution
    dist: dict[str, int] = {}
    for e in events:
        cat = e.get("category", "other")
        dist[cat] = dist.get(cat, 0) + 1
    print("\nCategory distribution:")
    for cat, count in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {cat:20s} {count}")

    with open(EVENTS_JSON, "w") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Wrote {len(events)} events to {EVENTS_JSON}")


if __name__ == "__main__":
    main()
