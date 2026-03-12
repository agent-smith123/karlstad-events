#!/usr/bin/env python3
"""
Enrich events.json with normalized category slugs.

Categories returned by APIs (e.g. Visit Värmland Algolia, Bibliotek Värmland)
are Swedish free-text labels. This script normalizes everything to a small set
of clean slugs used by the frontend filter pills.

Valid output slugs:
  concert, theater, opera, cinema, sport, museum, library, culture, festival,
  park, children, food, other
"""

import json
import re
from pathlib import Path

PROJ = Path(__file__).parent.parent
EVENTS_JSON = PROJ / "assets" / "data" / "events.json"

# ── Explicit source name → slug ──────────────────────────────────────────────
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

# ── Raw category value → slug  (substring match, lower-cased) ────────────────
# Applied to whatever is already in the `category` field from the API.
# Checked in priority order — first match wins.
CATEGORY_VALUE_MAP: list[tuple[str, str]] = [
    # Opera
    ("opera", "opera"),
    # Theater / performing arts
    ("teater", "theater"),
    ("theater", "theater"),
    ("scenkonst", "theater"),
    ("föreställning", "theater"),
    ("underhållning", "theater"),
    ("standup", "theater"),
    ("komedi", "theater"),
    ("revyn", "theater"),
    # Music / concert
    ("musik", "concert"),
    ("konsert", "concert"),
    ("concert", "concert"),
    ("live", "concert"),
    # Cinema
    ("bio", "cinema"),
    ("film", "cinema"),
    # Sport
    ("sport", "sport"),
    ("motion", "sport"),
    ("hälsa", "sport"),
    ("idrott", "sport"),
    ("hockey", "sport"),
    ("fotboll", "sport"),
    ("bandy", "sport"),
    ("simhall", "sport"),
    ("tennis", "sport"),
    ("golf", "sport"),
    ("löpning", "sport"),
    ("cykel", "sport"),
    ("trav", "sport"),
    # Festival
    ("festival", "festival"),
    # Museum / exhibitions
    ("utställning", "museum"),
    ("museum", "museum"),
    ("konsthal", "museum"),
    ("konst", "museum"),
    ("guidning", "museum"),
    # Children
    ("barn", "children"),
    ("sagostund", "children"),
    ("baby", "children"),
    ("påsklov", "children"),
    ("pyssel", "children"),
    ("lego", "children"),
    # Food
    ("mat", "food"),
    ("dryck", "food"),
    ("lunch", "food"),
    ("fika", "food"),
    ("brunch", "food"),
    ("middag", "food"),
    # Library / culture talks (before generic "culture")
    ("bibliotek", "library"),
    ("bokcirkel", "library"),
    ("bokklubb", "library"),
    ("läsning", "library"),
    ("författar", "library"),
    ("föreläsning", "culture"),
    ("workshop", "culture"),
    ("kurs", "culture"),
    ("dans", "culture"),
    ("marknad", "culture"),
    ("mässa", "culture"),
    ("loppis", "culture"),
    ("hantverk", "culture"),
    ("slöjd", "culture"),
    ("natur", "park"),
    ("park", "park"),
]

# ── Pattern-based fallback on SOURCE name ────────────────────────────────────
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


def normalize_existing_category(raw: str) -> str | None:
    """
    If the event already has a category set by an API, try to normalize it to
    a clean slug. Returns None if the value is already a known slug or can't
    be mapped (caller will then fall back to source-based lookup).
    """
    KNOWN_SLUGS = {
        "concert", "theater", "opera", "cinema", "sport", "museum",
        "library", "culture", "festival", "park", "children", "food", "other",
    }
    if not raw:
        return None
    if raw in KNOWN_SLUGS:
        return raw  # already normalized

    low = raw.lower()
    for substring, slug in CATEGORY_VALUE_MAP:
        if substring in low:
            return slug
    return None  # couldn't map — fall through to source lookup


def get_category_from_source(source: str) -> str:
    """Return a category slug based on the event source name."""
    if not source:
        return "other"
    if source in SOURCE_CATEGORY:
        return SOURCE_CATEGORY[source]
    s = source.lower()
    for pattern, cat in SOURCE_PATTERNS:
        if re.search(pattern, s):
            return cat
    if "visit värmland" in s or "visitvarmland" in s:
        return "culture"
    return "other"


def main():
    with open(EVENTS_JSON) as f:
        events = json.load(f)

    print(f"Total events: {len(events)}")

    for event in events:
        raw_cat = event.get("category", "")
        normalized = normalize_existing_category(raw_cat)
        if normalized:
            event["category"] = normalized
        else:
            # Either no category, or couldn't map raw API value → use source
            event["category"] = get_category_from_source(event.get("source", ""))

    # Show distribution
    dist: dict[str, int] = {}
    for e in events:
        cat = e.get("category", "other")
        dist[cat] = dist.get(cat, 0) + 1

    print("\nCategory distribution:")
    for cat, count in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {cat:20s} {count}")

    missing = sum(1 for e in events if not e.get("category"))
    print(f"\nEvents without category: {missing}")

    with open(EVENTS_JSON, "w") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"✓ Wrote {len(events)} events to {EVENTS_JSON}")


if __name__ == "__main__":
    main()
