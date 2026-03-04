#!/usr/bin/env python3
"""
Subagent-based AI Event Fetcher
Spawns multiple subagents to fetch events from venues in parallel
"""

import os
import sys
import yaml
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
VENUES_FILE = SCRIPT_DIR / "venues.yaml"

# Current year for validation
CURRENT_YEAR = datetime.now().year
VALID_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1}


def get_manual_venues() -> List[Tuple[str, dict]]:
    """Get list of venues that need AI fallback"""
    with open(VENUES_FILE) as f:
        venues = yaml.safe_load(f)
    
    manual_venues = []
    for tier in ['tier1_major', 'tier2_cultural', 'tier3_small', 'tier4_aggregators', 'tier5_municipal']:
        tier_venues = venues.get(tier, {})
        for venue_key, config in tier_venues.items():
            if not config.get('active', False):
                continue
            
            scraper_config = config.get('scraper', {})
            scraper_type = scraper_config.get('type', 'static')
            fallback = scraper_config.get('fallback')
            
            if scraper_type == 'manual' and fallback == 'ai':
                manual_venues.append((venue_key, config))
    
    return manual_venues


def spawn_subagent_for_batch(batch: List[Tuple[str, dict]], batch_num: int, total_batches: int) -> List[Dict]:
    """
    Spawn a subagent to fetch events from a batch of venues
    
    Note: This function is designed to be called from the main pipeline
    using sessions_spawn. The actual subagent execution happens in
    fetch_venue_batch() below.
    """
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
    
    events = []
    venues_processed = 0
    
    print(f"  🤖 Subagent batch {batch_num}/{total_batches}: {len(batch)} venues")
    
    for venue_key, config in batch:
        venue_name = config.get('name', venue_key)
        location = config.get('location', 'Karlstad')
        urls = config.get('urls', {})
        
        venue_events = []
        
        for url_type, url in urls.items():
            if not isinstance(url, str) or not url.startswith('http'):
                continue
            
            try:
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Parse JSON-LD events
                for script in soup.find_all('script', type='application/ld+json'):
                    try:
                        data = json.loads(script.string)
                        event_list = data if isinstance(data, list) else [data]
                        for item in event_list:
                            if isinstance(item, dict) and item.get('@type') == 'Event':
                                event = parse_jsonld_event(item, config, url)
                                if event and is_valid_event(event):
                                    venue_events.append(event)
                    except:
                        pass
                
                # Parse event links
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if any(x in href.lower() for x in ['/event/', '/forestallning', '/konsert', '/program']):
                        event = parse_event_link(link, config, url)
                        if event and is_valid_event(event):
                            venue_events.append(event)
                
            except Exception as e:
                pass
        
        # Deduplicate
        seen = set()
        for e in venue_events:
            key = (e['title'], e['date'], e['venue'])
            if key not in seen:
                seen.add(key)
                events.append(e)
        
        venues_processed += 1
        if venue_events:
            print(f"    ✓ {venue_name}: {len(venue_events)} events")
    
    print(f"  ✅ Batch {batch_num} complete: {len(events)} events from {venues_processed} venues")
    
    return events


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
            'source': f"AI:{config.get('name', '')}",
            'source_type': 'jsonld'
        }
    except:
        return None


def parse_event_link(link_elem, config: dict, base_url: str) -> Dict:
    """Parse event from a link element"""
    import re
    
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
    
    # ISO format
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
    
    return None


def is_valid_event(event: Dict) -> bool:
    """Check if event is valid"""
    if not event.get('title') or not event.get('date') or not event.get('venue'):
        return False
    
    try:
        year = int(event['date'][:4])
        if year not in VALID_YEARS:
            return False
        
        event_date = datetime.strptime(event['date'], '%Y-%m-%d').date()
        if event_date < datetime.now().date():
            return False
        
        return True
    except:
        return False


def prepare_batches(venues: List[Tuple[str, dict]], batch_size: int = 10) -> List[List[Tuple[str, dict]]]:
    """Split venues into batches"""
    batches = []
    for i in range(0, len(venues), batch_size):
        batches.append(venues[i:i + batch_size])
    return batches


def main():
    """Main entry point - prepare batches for subagent processing"""
    venues = get_manual_venues()
    batches = prepare_batches(venues, batch_size=10)
    
    print(f"\n🤖 Subagent AI Fetcher")
    print(f"=" * 50)
    print(f"  📋 Total venues: {len(venues)}")
    print(f"  📦 Batches: {len(batches)} (10 venues each)")
    print(f"\n  Ready for parallel subagent processing")
    
    # Save batch info for subagent spawning
    batch_info = {
        'total_venues': len(venues),
        'total_batches': len(batches),
        'batch_size': 10,
        'timestamp': datetime.now().isoformat()
    }
    
    with open(DATA_DIR / 'batch_info.json', 'w') as f:
        json.dump(batch_info, f, indent=2)
    
    # Process first batch as a test
    if batches:
        print(f"\n  Processing batch 1 as test...")
        events = spawn_subagent_for_batch(batches[0], 1, len(batches))
        print(f"\n  ✅ Test complete: {len(events)} events from batch 1")
    
    return batches


if __name__ == "__main__":
    main()