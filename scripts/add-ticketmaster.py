#!/usr/bin/env python3
"""
Add Ticketmaster events to the calendar
"""

import json
import re
from pathlib import Path
from datetime import datetime

OUTPUT_FILE = Path(__file__).parent.parent / "assets" / "data" / "events.json"

# Events from Ticketmaster Karlstad
ticketmaster_events = [
    {"title": "Stora Dialektshowen - Fredrik Lindström", "date": "2026-03-05", "venue": "Scalateatern", "category": "show"},
    {"title": "Carl-Einar Häckner - Siluetter", "date": "2026-03-06", "venue": "Scalateatern", "category": "show"},
    {"title": "Thank You for the Music - Part Two", "date": "2026-03-06", "venue": "Karlstad CCC", "category": "concert"},
    {"title": "Weeping Willows Vårturné 2026", "date": "2026-03-06", "venue": "Sundstaaulan", "category": "concert"},
    {"title": "Allt Jag Inte Sa - Encima Dansstudio", "date": "2026-03-07", "time": "15:00", "venue": "Arenan Bibliotekshuset", "category": "dance"},
    {"title": "Och Sen Var Ingen Kvart", "date": "2026-03-07", "venue": "Tempelriddaren", "category": "theater"},
    {"title": "Allt Jag Inte Sa - Encima Dansstudio", "date": "2026-03-07", "time": "18:00", "venue": "Arenan Bibliotekshuset", "category": "dance"},
    {"title": "Svansjön - En Kväll Med Balett i Världsklass", "date": "2026-03-07", "venue": "Karlstad CCC", "category": "ballet"},
    {"title": "Trad on the Prom - The Concert", "date": "2026-03-07", "venue": "Sundstaaulan", "category": "concert"},
    {"title": "Eric Clapton Tribute", "date": "2026-03-07", "venue": "Scalateatern", "category": "concert"},
    {"title": "Den Sårade Divan", "date": "2026-03-10", "venue": "Arenan Bibliotekshuset", "category": "theater"},
    {"title": "Och Sen Var Ingen Kvart", "date": "2026-03-11", "venue": "Tempelriddaren", "category": "theater"},
    {"title": "Sven-Ingvars - Igår, Idag, Imorgon. 70 år.", "date": "2026-03-11", "venue": "Scalateatern", "category": "concert"},
    {"title": "Och Sen Var Ingen Kvart", "date": "2026-03-12", "venue": "Tempelriddaren", "category": "theater"},
    {"title": "Sven-Ingvars - Igår, Idag, Imorgon. 70 år.", "date": "2026-03-12", "venue": "Scalateatern", "category": "concert"},
    {"title": "Sven-Ingvars - Igår, Idag, Imorgon. 70 år.", "date": "2026-03-13", "venue": "Scalateatern", "category": "concert"},
    {"title": "Den Svenska Sångboken", "date": "2026-03-13", "venue": "Sundstaaulan", "category": "concert"},
    {"title": "En Jäkla Massa Schlager", "date": "2026-03-13", "venue": "Karlstad CCC", "category": "concert"},
    {"title": "Sven-Ingvars - Igår, Idag, Imorgon. 70 år.", "date": "2026-03-14", "venue": "Scalateatern", "category": "concert"},
    {"title": "Och Sen Var Ingen Kvart", "date": "2026-03-14", "venue": "Tempelriddaren", "category": "theater"},
]

def normalize_text(text):
    """Normalize text to Title Case"""
    if not text:
        return text
    words = text.split()
    result = []
    for i, w in enumerate(words):
        if i > 0 and w.lower() in ['och', 'eller', 'i', 'på', 'med', 'till', 'från', 'av', 'en', 'ett', 'den', 'det']:
            result.append(w.lower())
        else:
            result.append(w.capitalize() if w.isupper() else w)
    return ' '.join(result)

def main():
    # Load existing events
    with open(OUTPUT_FILE) as f:
        existing = json.load(f)
    
    print(f"Existing events: {len(existing)}")
    
    # Add Ticketmaster events
    new_events = []
    for tm in ticketmaster_events:
        event = {
            'title': normalize_text(tm['title']),
            'date': tm['date'],
            'venue': normalize_text(tm['venue']),
            'location': 'Karlstad',
            'category': tm['category'],
            'link': f"https://www.ticketmaster.se/discover/karlstad",
            'source': 'Ticketmaster'
        }
        if 'time' in tm:
            event['time'] = tm['time']
        new_events.append(event)
    
    # Merge and deduplicate
    seen = set()
    unique = []
    
    for e in existing + new_events:
        key = f"{e['date']}-{e['title'].lower()[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    
    unique.sort(key=lambda x: x.get('date', ''))
    
    print(f"Added {len(new_events)} Ticketmaster events")
    print(f"Total unique: {len(unique)}")
    
    # Save
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    
    # Build and deploy
    import subprocess
    subprocess.run(['hugo'], cwd=Path(__file__).parent.parent, capture_output=True)
    subprocess.run(['surge', './public', 'karlstad-events.surge.sh'], cwd=Path(__file__).parent.parent, capture_output=True)
    
    print(f"✅ Published {len(unique)} events!")

if __name__ == '__main__':
    main()