#!/usr/bin/env python3
"""
AI Cultural Events Fetcher
Finds exhibitions, markets, seminars, and lectures using web search + AI parsing
"""

import os
import json
import re
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
ASSETS_DIR = PROJECT_DIR / "assets" / "data"

# Event type keywords
EVENT_TYPES = {
    'utställning': ['utställning', 'konstutställning', 'photo exhibition', 'museum'],
    'marknad': ['marknad', 'loppis', 'julmarknad', 'hantverksmarknad'],
    'seminarium': ['seminarium', 'workshop', 'kurs', 'utbildning'],
    'föreläsning': ['föreläsning', 'föredrag', 'föreläsningar', 'talk'],
}

# Venues with their URLs
CULTURAL_VENUES = {
    'Värmlands Museum': {
        'url': 'https://varmlandsmuseum.se/utstallningar/',
        'type': 'utställning',
        'location': 'Karlstad'
    },
    'Sandgrund Lars Lerin': {
        'url': 'https://www.sandgrundlarslerin.se/',
        'type': 'utställning',
        'location': 'Karlstad'
    },
    'Kristinehamns Konstmuseum': {
        'url': 'https://kristinehamnskonstmuseum.se/',
        'type': 'utställning',
        'location': 'Kristinehamn'
    },
    'Bibliotekshuset': {
        'url': 'https://karlstad.se/uppleva-och-gora/bibliotek/kalender-for-biblioteken-i-karlstad',
        'type': 'föreläsning',
        'location': 'Karlstad'
    },
    'Rackstadmuseet': {
        'url': 'https://rackstadmuseet.se/',
        'type': 'utställning',
        'location': 'Arvika'
    },
}


def search_brave_api(query: str, count: int = 10) -> List[Dict]:
    """Search using Brave API"""
    api_key = os.getenv('BRAVE_API_KEY')
    if not api_key:
        # Try to get from OpenClaw config
        import json
        config_path = Path.home() / '.openclaw' / 'openclaw.json'
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_key = config.get('tools', {}).get('web', {}).get('search', {}).get('apiKey', '')
    
    if not api_key:
        print("⚠️ No BRAVE_API_KEY found")
        return []
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key
    }
    params = {
        "q": query,
        "count": count,
        "freshness": "py",  # Past year
        "country": "SE",
        "search_lang": "sv"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get('web', {}).get('results', [])
    except Exception as e:
        print(f"Search error: {e}")
        return []


def parse_date(text: str, year: int = None) -> Optional[str]:
    """Parse date from Swedish text"""
    if not year:
        year = datetime.now().year
    
    # Swedish month names
    months = {
        'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
        'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
        'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12
    }
    
    # Try ISO format first
    iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if iso_match:
        return iso_match.group(0)
    
    # Try Swedish format: "15 mars 2026" or "15 mars"
    swe_match = re.search(r'(\d{1,2})\s+([a-zåäö]+)(?:\s+(\d{4}))?', text.lower())
    if swe_match:
        day = int(swe_match.group(1))
        month_name = swe_match.group(2)
        found_year = int(swe_match.group(3)) if swe_match.group(3) else year
        
        if month_name in months:
            return f"{found_year}-{months[month_name]:02d}-{day:02d}"
    
    # Try date range: "31 maj–13 september 2026"
    range_match = re.search(r'(\d{1,2})\s+([a-zåäö]+)\s*[–-]\s*(\d{1,2})\s+([a-zåäö]+)(?:\s+(\d{4}))?', text.lower())
    if range_match:
        start_day = int(range_match.group(1))
        start_month = months.get(range_match.group(2), 1)
        end_day = int(range_match.group(3))
        end_month = months.get(range_match.group(4), 1)
        found_year = int(range_match.group(5)) if range_match.group(5) else year
        
        return f"{found_year}-{start_month:02d}-{start_day:02d}"
    
    return None


def extract_event_from_result(result: Dict, event_type: str) -> Optional[Dict]:
    """Extract event info from search result"""
    title = result.get('title', '')
    description = result.get('description', '')
    url = result.get('url', '')
    
    # Skip non-events
    skip_patterns = ['wikipedia', 'instagram', 'facebook.com/', 'twitter.com', 'skansen.se']
    for pattern in skip_patterns:
        if pattern in url.lower():
            return None
    
    full_text = f"{title} {description}"
    
    # Must be in Värmland region
    varmland_locations = ['karlstad', 'värmland', 'arvika', 'kristinehamn', 'säffle', 'sunne', 
                          'filipstad', 'torsby', 'hagfors', 'kil', 'grums', 'hammarö', 'forshaga']
    is_varmland = any(loc in full_text.lower() or loc in url.lower() for loc in varmland_locations)
    if not is_varmland:
        return None
    
    # Extract date from description
    date = parse_date(full_text)
    
    if not date:
        return None
    
    # Check if date is in the future
    try:
        event_date = datetime.strptime(date, '%Y-%m-%d')
        if event_date.date() < datetime.now().date():
            return None
    except:
        return None
    
    # Determine venue from URL or description
    venue = 'Okänd plats'
    for venue_name, venue_info in CULTURAL_VENUES.items():
        if venue_name.lower() in full_text.lower() or venue_name.lower() in url.lower():
            venue = venue_name
            break
    
    # Extract location
    location = 'Karlstad'
    for loc in varmland_locations:
        if loc in full_text.lower():
            location = loc.title()
            break
    
    return {
        'title': title,
        'date': date,
        'venue': venue,
        'location': location,
        'link': url,
        'category': event_type,
        'source': 'AI Cultural Search'
    }


def search_cultural_events() -> List[Dict]:
    """Search for cultural events using web search"""
    events = []
    seen_titles = set()
    
    # Search queries for each event type
    queries = [
        # Exhibitions
        ('utställning Karlstad 2026', 'utställning'),
        ('Värmlands Museum utställning 2026', 'utställning'),
        ('Sandgrund Lars Lerin utställning 2026', 'utställning'),
        ('konstutställning Värmland 2026', 'utställning'),
        
        # Markets
        ('marknad Karlstad 2026', 'marknad'),
        ('loppis Karlstad 2026', 'marknad'),
        ('julmarknad Värmland 2026', 'marknad'),
        
        # Seminars & Lectures
        ('föreläsning Karlstad bibliotek 2026', 'föreläsning'),
        ('seminarium Värmland 2026', 'seminarium'),
        ('workshop Karlstad 2026', 'seminarium'),
        ('föredrag bibliotek Karlstad 2026', 'föreläsning'),
    ]
    
    for query, event_type in queries:
        print(f"🔍 Searching: {query}")
        results = search_brave_api(query, count=10)
        
        for result in results:
            event = extract_event_from_result(result, event_type)
            if event:
                title_key = event['title'].lower()[:50]
                if title_key not in seen_titles:
                    seen_titles.add(title_key)
                    events.append(event)
                    print(f"  ✓ {event['date']}: {event['title'][:50]}")
    
    return events


def fetch_from_venue_pages() -> List[Dict]:
    """Fetch events directly from venue pages"""
    events = []
    
    for venue_name, venue_info in CULTURAL_VENUES.items():
        print(f"🌐 Fetching from {venue_name}...")
        
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            resp = session.get(venue_info['url'], timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Look for JSON-LD events
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') == 'Event':
                        title = data.get('name', '')
                        date = data.get('startDate', '')[:10] if 'startDate' in data else ''
                        
                        if title and date:
                            events.append({
                                'title': title,
                                'date': date,
                                'venue': venue_name,
                                'location': venue_info['location'],
                                'link': data.get('url', venue_info['url']),
                                'category': venue_info['type'],
                                'source': venue_name
                            })
                            print(f"  ✓ {date}: {title[:50]}")
                except:
                    pass
            
            # Look for date patterns in text
            text = soup.get_text()
            dates = parse_date(text)
            if dates:
                # Try to find event title near date
                # This is simplified - real implementation would need more parsing
                pass
                
        except Exception as e:
            print(f"  ⚠️ Error: {e}")
    
    return events


def main():
    """Main function to fetch all cultural events"""
    print("🎨 AI Cultural Events Fetcher")
    print("=" * 50)
    
    all_events = []
    
    # 1. Search for events
    print("\n🔍 Phase 1: Web Search")
    search_events = search_cultural_events()
    all_events.extend(search_events)
    print(f"  Found {len(search_events)} events via search")
    
    # 2. Fetch from venue pages
    print("\n🌐 Phase 2: Venue Pages")
    venue_events = fetch_from_venue_pages()
    all_events.extend(venue_events)
    print(f"  Found {len(venue_events)} events from venue pages")
    
    # 3. Deduplicate
    seen = set()
    unique_events = []
    for event in all_events:
        key = f"{event['date']}-{event['title'][:30]}"
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    print(f"\n✅ Total unique events: {len(unique_events)}")
    
    # 4. Save to file
    output_file = DATA_DIR / 'cultural_events.json'
    DATA_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(unique_events, f, indent=2, ensure_ascii=False)
    print(f"📁 Saved to {output_file}")
    
    # 5. Merge with existing events.json
    events_json = ASSETS_DIR / 'events.json'
    if events_json.exists():
        with open(events_json) as f:
            existing = json.load(f)
        
        # Add cultural events
        existing_titles = {e['title'].lower()[:30] for e in existing}
        for event in unique_events:
            if event['title'].lower()[:30] not in existing_titles:
                existing.append(event)
        
        with open(events_json, 'w') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        
        print(f"📊 Total events after merge: {len(existing)}")
    
    return unique_events


if __name__ == '__main__':
    main()