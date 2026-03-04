#!/usr/bin/env python3
"""
Parallel AI Event Fetcher
Uses multiple sub-agents to fetch events in parallel from manual venues
"""

import os
import sys
import yaml
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

# Current year for validation
CURRENT_YEAR = datetime.now().year
VALID_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1}


def fetch_single_venue(venue_key: str, config: dict) -> Tuple[str, List[Dict]]:
    """
    Fetch events from a single venue using AI/web search
    Returns (venue_key, events)
    """
    venue_name = config.get('name', venue_key)
    location = config.get('location', 'Karlstad')
    events = []
    
    try:
        import requests
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin, urlparse
        
        print(f"  🔄 {venue_name}")
        
        # Get venue URLs
        urls = config.get('urls', {})
        venue_events = []
        
        for url_type, url in urls.items():
            if not isinstance(url, str) or not url.startswith('http'):
                continue
            
            try:
                # Fetch page
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Parse JSON-LD events
                scripts = soup.find_all('script', type='application/ld+json')
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, list):
                            for item in data:
                                if item.get('@type') == 'Event':
                                    event = parse_jsonld_event(item, config, url)
                                    if event and is_valid_event(event):
                                        venue_events.append(event)
                        elif isinstance(data, dict) and data.get('@type') == 'Event':
                            event = parse_jsonld_event(data, config, url)
                            if event and is_valid_event(event):
                                venue_events.append(event)
                    except:
                        pass
                
                # Parse event links
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if '/event/' in href or '/forestallning/' in href or '/konsert/' in href:
                        event = parse_event_link(link, config, url)
                        if event and is_valid_event(event):
                            venue_events.append(event)
                
            except Exception as e:
                pass
        
        # Deduplicate events
        seen = set()
        unique_events = []
        for e in venue_events:
            key = (e['title'], e['date'], e['venue'])
            if key not in seen:
                seen.add(key)
                unique_events.append(e)
        
        print(f"    ✓ {len(unique_events)} events")
        return (venue_key, unique_events)
        
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return (venue_key, events)


def parse_jsonld_event(data: dict, config: dict, url: str) -> Dict:
    """Parse JSON-LD event data"""
    try:
        name = data.get('name', '')
        start_date = data.get('startDate', '')
        
        if not name or not start_date:
            return None
        
        date_str = start_date[:10] if 'T' in start_date else start_date
        
        return {
            'title': name,
            'date': date_str,
            'venue': config.get('name', 'Unknown'),
            'location': config.get('location', 'Karlstad'),
            'link': data.get('url', url),
            'source': f"AI:{config.get('name', venue_key)}",
            'source_type': 'jsonld'
        }
    except:
        return None


def parse_event_link(link_elem, config: dict, base_url: str) -> Dict:
    """Parse event from a link element"""
    try:
        href = link_elem.get('href', '')
        text = link_elem.get_text(strip=True)
        
        if not text or len(text) < 5:
            return None
        
        # Try to extract date from text
        date_str = parse_date_from_text(text)
        if not date_str:
            return None
        
        link = urljoin(base_url, href) if href.startswith('/') else href
        
        return {
            'title': text,
            'date': date_str,
            'venue': config.get('name', 'Unknown'),
            'location': config.get('location', 'Karlstad'),
            'link': link,
            'source': f"AI:{config.get('name', '')}",
            'source_type': 'link'
        }
    except:
        return None


def parse_date_from_text(text: str) -> str:
    """Parse date from text"""
    import re
    
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12,
        'januari': 1, 'februari': 2, 'mars': 3, 'april': 4, 'juni': 6,
        'juli': 7, 'augusti': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12
    }
    
    # ISO format: 2026-03-15
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    
    # Swedish format: 15 mars 2026
    match = re.search(
        r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec|januari|februari|mars|april|juni|juli|augusti|september|oktober|november|december)[\.\s,]+(\d{4})',
        text.lower()
    )
    if match:
        day = int(match.group(1))
        month_str = match.group(2)[:3]
        month = months.get(month_str, 1)
        year = int(match.group(3))
        return f"{year}-{month:02d}-{day:02d}"
    
    # Short format: 15 mar
    match = re.search(
        r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)',
        text.lower()
    )
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        month = months.get(month_str, 1)
        year = CURRENT_YEAR
        return f"{year}-{month:02d}-{day:02d}"
    
    return None


def is_valid_event(event: Dict) -> bool:
    """Check if event is valid"""
    if not event.get('title') or not event.get('date') or not event.get('venue'):
        return False
    
    try:
        year = int(event['date'][:4])
        if year not in VALID_YEARS:
            return False
        
        # Check if not too far in the past
        event_date = datetime.strptime(event['date'], '%Y-%m-%d').date()
        if event_date < datetime.now().date():
            return False
        
        return True
    except:
        return False


def parallel_fetch_venues(venues_config: dict, max_workers: int = 5, timeout: int = 120) -> List[Dict]:
    """
    Fetch events from all manual venues in parallel
    """
    # Find manual venues with AI fallback
    manual_venues = []
    
    for tier in ['tier1_major', 'tier2_cultural', 'tier3_small', 'tier4_aggregators', 'tier5_municipal']:
        tier_venues = venues_config.get(tier, {})
        for venue_key, config in tier_venues.items():
            if not config.get('active', False):
                continue
            
            scraper_config = config.get('scraper', {})
            scraper_type = scraper_config.get('type', 'static')
            fallback = scraper_config.get('fallback')
            
            if scraper_type == 'manual' and fallback == 'ai':
                manual_venues.append((venue_key, config))
    
    if not manual_venues:
        print("  ℹ️  No manual venues with AI fallback")
        return []
    
    print(f"\n🤖 Parallel AI Fetcher")
    print(f"=" * 50)
    print(f"  📋 Processing {len(manual_venues)} venues")
    print(f"  ⚙️  Max workers: {max_workers}")
    print(f"  ⏱️  Timeout: {timeout}s per venue\n")
    
    all_events = []
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_venue = {
            executor.submit(fetch_single_venue, key, config): key
            for key, config in manual_venues
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_venue, timeout=timeout * len(manual_venues)):
            venue_key = future_to_venue[future]
            try:
                key, events = future.result()
                all_events.extend(events)
            except Exception as e:
                print(f"  ❌ {venue_key}: {e}")
    
    print(f"\n  ✅ Total events fetched: {len(all_events)}")
    
    return all_events


if __name__ == "__main__":
    with open(SCRIPT_DIR / "venues.yaml") as f:
        venues = yaml.safe_load(f)
    
    events = parallel_fetch_venues(venues, max_workers=5, timeout=30)
    
    print(f"\n✅ Fetched {len(events)} events in parallel")
    
    for e in events[:10]:
        print(f"  • {e['date']}: {e['title'][:50]} ({e['venue']})")