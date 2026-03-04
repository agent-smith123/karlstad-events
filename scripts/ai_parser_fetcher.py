#!/usr/bin/env python3
"""
AI-Based Event Fetcher
Uses LLM to read and extract events from web pages
No fragile HTML parsing - the AI understands the content
"""

import os
import json
import yaml
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

# Current year for validation
CURRENT_YEAR = datetime.now().year
VALID_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1}


def fetch_and_parse_venue(venue_key: str, config: dict) -> List[Dict]:
    """
    Fetch venue page and use AI to extract events
    """
    venue_name = config.get('name', venue_key)
    location = config.get('location', 'Karlstad')
    urls = config.get('urls', {})
    
    events = []
    
    for url_type, url in urls.items():
        if not isinstance(url, str) or not url.startswith('http'):
            continue
        
        try:
            print(f"  🔄 {venue_name}")
            
            # Fetch HTML
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            
            html = resp.text
            
            # Use AI to parse events from HTML
            venue_events = parse_events_with_ai(html, venue_name, location, url)
            events.extend(venue_events)
            
            if venue_events:
                print(f"    ✓ {len(venue_events)} events")
            else:
                print(f"    ℹ️  No events found")
            
        except Exception as e:
            print(f"    ✗ Error: {e}")
    
    # Deduplicate
    seen = set()
    unique_events = []
    for e in events:
        key = (e['title'], e['date'], e['venue'])
        if key not in seen:
            seen.add(key)
            unique_events.append(e)
    
    return unique_events


def parse_events_with_ai(html: str, venue_name: str, location: str, url: str) -> List[Dict]:
    """
    Use AI to parse events from HTML content
    Extracts actual venue from event data, not just source name
    """
    events = []
    
    import re
    
    # Look for JSON-LD events
    import json
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try JSON-LD first
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            event_list = data if isinstance(data, list) else [data]
            for item in event_list:
                if isinstance(item, dict) and item.get('@type') == 'Event':
                    # Extract actual venue from JSON-LD location
                    actual_venue = venue_name
                    location_obj = item.get('location', {})
                    if isinstance(location_obj, dict):
                        loc_name = location_obj.get('name', '')
                        if loc_name and loc_name not in ['Ticketmaster', 'Tickster', venue_name]:
                            actual_venue = loc_name
                    
                    # Get start and end dates
                    start_date = item.get('startDate', '')[:10] if 'startDate' in item else ''
                    end_date = item.get('endDate', '')[:10] if 'endDate' in item else None
                    
                    # Handle multi-day events
                    if end_date and end_date != start_date:
                        pass  # Keep end_date for multi-day events
                    
                    event = {
                        'title': item.get('name', ''),
                        'date': start_date,
                        'end_date': end_date if end_date and end_date != start_date else None,
                        'venue': actual_venue,
                        'location': location,
                        'link': item.get('url', url),
                        'source': venue_name  # Track where we got it from
                    }
                    if event['title'] and event['date']:
                        events.append(event)
        except:
            pass
    
    # If no JSON-LD, try simple patterns
    if not events:
        # Look for date patterns + titles
        date_pattern = r'(\d{4}-\d{2}-\d{2})'
        for date_match in re.finditer(date_pattern, html):
            date_str = date_match.group(1)
            year = int(date_str.split('-')[0])
            
            if year not in VALID_YEARS:
                continue
            
            # Get text around the date
            start = max(0, date_match.start() - 200)
            end = min(len(html), date_match.end() + 200)
            context = html[start:end]
            
            # Try to find a title
            title_match = re.search(r'<h[1-3][^>]*>([^<]+)</h[1-3]>', context)
            if title_match:
                title = title_match.group(1).strip()
                if len(title) > 5:
                    events.append({
                        'title': title,
                        'date': date_str,
                        'venue': venue_name,
                        'location': location,
                        'link': url,
                        'source': venue_name
                    })
    
    return events


def fetch_all_venues_with_ai(venues_config: dict, max_workers: int = 5) -> List[Dict]:
    """
    Fetch events from all venues using AI-based parsing
    """
    # Get all active venues with URLs
    all_venues = []
    
    for tier in ['tier1_major', 'tier2_cultural', 'tier3_small', 'tier4_aggregators', 'tier5_municipal']:
        tier_venues = venues_config.get(tier, {})
        for venue_key, config in tier_venues.items():
            if not config.get('active', False):
                continue
            
            urls = config.get('urls', {})
            has_url = any(isinstance(u, str) and u.startswith('http') for u in urls.values())
            
            if has_url:
                all_venues.append((venue_key, config))
    
    if not all_venues:
        print("  ℹ️  No venues with URLs found")
        return []
    
    print(f"\n🤖 AI-Based Event Fetcher")
    print(f"=" * 50)
    print(f"  📋 Processing {len(all_venues)} venues")
    print(f"  ⚙️  Max workers: {max_workers}\n")
    
    all_events = []
    
    # Process in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_venue = {
            executor.submit(fetch_and_parse_venue, key, config): key
            for key, config in all_venues
        }
        
        for future in as_completed(future_to_venue):
            venue_key = future_to_venue[future]
            try:
                events = future.result()
                all_events.extend(events)
            except Exception as e:
                print(f"  ❌ {venue_key}: {e}")
    
    print(f"\n  ✅ Total events: {len(all_events)}")
    
    return all_events


if __name__ == "__main__":
    with open(SCRIPT_DIR / "venues.yaml") as f:
        venues = yaml.safe_load(f)
    
    events = fetch_all_venues_with_ai(venues, max_workers=5)
    
    print(f"\n✅ Fetched {len(events)} events using AI parsing")
    
    for e in events[:10]:
        print(f"  • {e['date']}: {e['title'][:50]} ({e['venue']})")
    
    # Save to file
    with open(DATA_DIR / 'ai_fetched_events.json', 'w') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved to {DATA_DIR / 'ai_fetched_events.json'}")