#!/usr/bin/env python3
"""
Simple Event Fetcher - KISS principle
Focus on reliable sources only
"""

import os
import json
import requests
import yaml
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import re

# Configuration
CONTENT_DIR = Path(__file__).parent.parent / "content" / "events"
VENUES_FILE = Path(__file__).parent / "venues.yaml"

# Swedish month mapping
MONTHS_SV = {
    'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
    'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
    'september': 9, 'oktober': 10, 'november': 11, 'december': 12
}

def load_venues() -> Dict:
    """Load venues from YAML."""
    with open(VENUES_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def slugify(text: str) -> str:
    """Create URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')[:12]

def normalize_title(title: str) -> str:
    """Convert ALL CAPS to proper title case."""
    if not title:
        return title
    
    upper_count = sum(1 for c in title if c.isupper())
    alpha_count = sum(1 for c in title if c.isalpha())
    
    if alpha_count > 0 and (alpha_count - upper_count) / alpha_count < 0.3:
        return title.title()
    
    return title

def parse_date(date_text: str) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD."""
    date_text = date_text.strip().lower()
    
    # Swedish format: 15 mars 2026
    for month_sv, month_num in MONTHS_SV.items():
        if month_sv in date_text:
            match = re.search(r'(\d{1,2})\s+' + month_sv + r'\s+(\d{4})', date_text)
            if match:
                day, year = match.groups()
                return f"{year}-{month_num:02d}-{int(day):02d}"
            match = re.search(r'(\d{1,2})\s+' + month_sv + r'(?:\s|$)', date_text)
            if match:
                day = match.group(1)
                return f"{datetime.now().year}-{month_num:02d}-{int(day):02d}"
    
    # ISO format: 2026-03-15
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    
    return None

def fetch_ticketmaster_events(city: str = "Karlstad", country: str = "SE") -> List[Dict]:
    """Fetch events from Ticketmaster API."""
    api_key = os.getenv('TICKETMASTER_API_KEY')
    if not api_key:
        print("  ⚠️  No Ticketmaster API key")
        return []
    
    events = []
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    
    params = {
        'apikey': api_key,
        'city': city,
        'countryCode': country,
        'radius': 50,
        'unit': 'km',
        'size': 100,
        'sort': 'date,asc'
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        for e in data.get('_embedded', {}).get('events', []):
            try:
                name = e.get('name', '')
                dates = e.get('dates', {}).get('start', {})
                date_str = dates.get('localDate', '')
                time_str = dates.get('localTime', '')[:5] if dates.get('localTime') else None
                
                venues = e.get('_embedded', {}).get('venues', [])
                venue_name = venues[0].get('name', 'Unknown') if venues else 'Unknown'
                city = venues[0].get('city', {}).get('name', city) if venues else city
                
                url = e.get('url', '')
                
                events.append({
                    'title': name,
                    'date': date_str,
                    'time': time_str,
                    'venue': venue_name,
                    'location': city,
                    'link': url,
                    'source': 'Ticketmaster'
                })
            except Exception as e:
                print(f"    ⚠️  Parse error: {e}")
                
    except Exception as e:
        print(f"  ⚠️  Ticketmaster API error: {e}")
    
    return events

def fetch_wermland_opera() -> List[Dict]:
    """Fetch events from Wermland Opera website."""
    events = []
    url = "https://www.wermlandopera.com/evenemang/"
    
    try:
        resp = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        resp.raise_for_status()
        
        # Simple pattern matching for event info
        # Look for event cards with title, date, venue
        content = resp.text
        
        # Pattern: event title and date
        title_pattern = r'<h[23][^>]*>([^<]+)</h[23]>'
        date_pattern = r'(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})'
        
        # This is a simplified version - real implementation would need BeautifulSoup
        print("  ℹ️  Wermland Opera: Use Ticketmaster for now")
        
    except Exception as e:
        print(f"  ⚠️  Wermland Opera error: {e}")
    
    return events

def fetch_karlstad_ccc() -> List[Dict]:
    """Fetch events from Karlstad CCC website."""
    events = []
    url = "https://www.karlstadccc.se/17/38/program-biljetter/"
    
    try:
        resp = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        resp.raise_for_status()
        
        # Simple extraction using regex patterns
        # Look for event titles and dates in the page
        content = resp.text
        
        # Extract event blocks - looking for title, date, time pattern
        # This is simplified - production would use BeautifulSoup
        print("  ℹ️  Karlstad CCC: Basic fetch (improve with proper parsing)")
        
    except Exception as e:
        print(f"  ⚠️  Karlstad CCC error: {e}")
    
    return events

def save_event(event: Dict) -> str:
    """Save event to markdown file."""
    # Generate unique ID
    event_id = hashlib.md5(
        f"{event['title']}|{event['date']}|{event['venue']}".encode()
    ).hexdigest()[:12]
    
    filename = f"{event['date']}-{event_id}.md"
    filepath = CONTENT_DIR / filename
    
    # Check if already exists
    if filepath.exists():
        return None
    
    # Normalize title
    title = normalize_title(event['title'])
    
    # Build markdown
    md = f"""---
title: "{title}"
date: {event['date']}
venue: "{event['venue']}"
location: "{event['location']}"
"""
    
    if event.get('time'):
        md += f'time: "{event["time"]}"\n'
    if event.get('link'):
        md += f'link: "{event["link"]}"\n'
    
    md += f"""categories: ["Evenemang"]
source: "{event.get('source', 'Unknown')}"
---

{event.get('description', '')}
"""
    
    filepath.write_text(md, encoding='utf-8')
    return filename

def main():
    print("🎯 Simple Event Fetcher")
    print("=" * 40)
    print(f"📁 Output: {CONTENT_DIR}")
    print()
    
    # Load venues
    venues = load_venues()
    print(f"📍 Loaded {len(venues.get('tier1_major', {}))} major venues")
    print()
    
    all_events = []
    
    # 1. Ticketmaster API (most reliable)
    print("📡 Fetching from Ticketmaster...")
    tm_events = fetch_ticketmaster_events()
    print(f"  Found {len(tm_events)} events")
    all_events.extend(tm_events)
    print()
    
    # Save events
    saved_count = 0
    for event in all_events:
        if save_event(event):
            saved_count += 1
    
    print(f"✅ Saved {saved_count} new events")
    
    return all_events

if __name__ == "__main__":
    main()