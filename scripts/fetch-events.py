#!/usr/bin/env python3
"""Research events in Karlstad area - generates markdown files for Hugo."""

import os
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
CONTENT_DIR = Path(__file__).parent.parent / "content" / "events"

# Known venues and their URLs
VENUES = [
    {"name": "Wermland Opera", "url": "https://www.wermlandopera.com/evenemang/", "location": "Karlstad"},
    {"name": "Nöjesfabriken", "url": "https://www.nojesfabriken.se/nojeskalendern/", "location": "Karlstad"},
    {"name": "Karlstad CCC", "url": "https://www.karlstadccc.se/17/38/program-biljetter/", "location": "Karlstad"},
    {"name": "Kulturhuset", "url": "https://kulturhusetstadsteatern.se/kalender", "location": "Karlstad"},
]

AREAS = ["Karlstad", "Forshaga", "Kil", "Molkom", "Skattkärr", "Väse", "Vålberg", "Deje"]

def slugify(text):
    """Create a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')

def create_event_markdown(title, date, venue, location, time=None, link=None, description=""):
    """Create markdown content for an event."""
    date_str = date.strftime("%Y-%m-%d") if isinstance(date, datetime) else date
    
    md = f"""---
title: "{title}"
date: {date_str}
venue: "{venue}"
location: "{location}"
"""
    if time:
        md += f'time: "{time}"\n'
    if link:
        md += f'link: "{link}"\n'
    md += f"""categories: ["Evenemang"]
---

{description}
"""
    return md

def main():
    print("🔍 Karlstad Events Research")
    print("=" * 40)
    print(f"\n📁 Output: {CONTENT_DIR}")
    print(f"📅 Week of: {datetime.now().strftime('%Y-%m-%d')}")
    print("\n⚠️  This is a stub - real implementation needs:")
    print("   - Brave Search API integration")
    print("   - Web fetching and parsing")
    print("   - Deduplication logic")
    print("\n✅ Script ready for enhancement!")

if __name__ == "__main__":
    main()
