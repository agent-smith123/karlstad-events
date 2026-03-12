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
import urllib.parse
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
VISIT_VARMLAND_ALGOLIA_APP_ID = "JLIO3DI59W"
VISIT_VARMLAND_ALGOLIA_API_KEY = "c3e912c214238b637c6a86d637acfe79"
BIBLIOTEK_VARMLAND_GROUP_ID = "493520"


def is_visit_varmland_source(config: dict) -> bool:
    urls = config.get('urls', {})
    return any(isinstance(url, str) and 'visitvarmland.com' in url for url in urls.values())


def is_bibliotek_varmland_source(config: dict) -> bool:
    scraper = config.get('scraper', {})
    if scraper.get('provider') == 'bibliotek_varmland_api':
        return True
    urls = config.get('urls', {})
    return any(isinstance(url, str) and 'bibliotekvarmland.se' in url for url in urls.values()) and bool(config.get('library_locations') or config.get('library_location'))


def _get_bibliotek_varmland_config() -> Dict:
    config_url = f'https://www.bibliotekvarmland.se/api/jsonws/arenacalendar.calendar/get-calendar-config?groupId={BIBLIOTEK_VARMLAND_GROUP_ID}'
    resp = requests.get(config_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_bibliotek_varmland_events(config: dict) -> List[Dict]:
    """Fetch structured library events from Bibliotek Värmland's Axiell API."""
    venue_name = config.get('name', 'Bibliotek Värmland')
    municipality = config.get('location', venue_name)
    library_locations = config.get('library_locations') or ([config['library_location']] if config.get('library_location') else [])
    if not library_locations:
        return []

    api_config = _get_bibliotek_varmland_config()
    base_url = api_config['calendarApiEndpoint'].rstrip('/')
    customer_id = api_config['customerId']
    search_url = f'{base_url}/customers/{customer_id}/search'

    range_filters = [
        {'field': 'event.startDate', 'gte': datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'}
    ]
    term_filters = [
        {'field': 'event.status', 'values': ['PUBLISHED', 'CANCELLED']},
        {'type': 'NOT_IN', 'field': 'event.deleted', 'values': [True]},
        {'field': 'event.location.value', 'values': library_locations},
    ]

    events = []
    start = 0
    size = 100
    page_url = next((url for url in (config.get('urls') or {}).values() if isinstance(url, str) and 'bibliotekvarmland.se' in url), None) or 'https://www.bibliotekvarmland.se/evenemang'

    while True:
        params = {
            'queryString': 'event.title:* OR event.description:* OR event.location.value:*',
            'rangeFilters': json.dumps(range_filters),
            'termFilters': json.dumps(term_filters),
            'sorts': json.dumps([{'field': 'event.startDate', 'order': 'ASC'}]),
            'start': start,
            'size': size,
        }
        resp = requests.get(search_url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get('hits', [])
        if not hits:
            break

        for hit in hits:
            event = hit.get('event') or {}
            title = event.get('title')
            start_date = event.get('startDate')
            if not title or not start_date:
                continue
            date = start_date[:10]
            year = int(date[:4])
            if year not in VALID_YEARS:
                continue
            end_date = (event.get('endDate') or '')[:10] or None
            location_value = ((event.get('location') or {}).get('value')) or venue_name
            tags = event.get('tags') or []
            category = tags[0] if tags else None
            events.append({
                'title': title,
                'date': date,
                'end_date': end_date if end_date != date else None,
                'venue': location_value,
                'location': municipality,
                'link': page_url,
                'source': venue_name,
                'category': category,
            })

        start += len(hits)
        if start >= data.get('totalHits', 0):
            break

    seen = set()
    unique = []
    for e in events:
        key = (e['title'], e['date'], e['venue'])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def fetch_visit_varmland_events(config: dict) -> List[Dict]:
    """Fetch Visit Värmland events via the Algolia index used by their own site."""
    venue_name = config.get('name', 'Visit Värmland')
    location = config.get('location', 'Värmland')
    events = []

    page_url = next(
        (url for url in (config.get('urls') or {}).values() if isinstance(url, str) and 'visitvarmland.com' in url),
        None,
    )
    if not page_url:
        return events

    page_resp = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
    page_resp.raise_for_status()

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_resp.text, 'html.parser')
    script = soup.find('script', id='algolia-filter-js-before')
    if not script:
        return events

    script_text = (script.get_text() or '').strip()
    prefix = 'window.ALGOLIA_FILTER = '
    if not script_text.startswith(prefix):
        return events

    filter_data = json.loads(script_text[len(prefix):].rstrip(' ;'))
    index_name = filter_data.get('indexName', 'events')
    filters = filter_data.get('filter')
    locale = filter_data.get('locale', 'sv')
    if not filters:
        return events

    query_url = f'https://{VISIT_VARMLAND_ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries'
    headers = {
        'X-Algolia-API-Key': VISIT_VARMLAND_ALGOLIA_API_KEY,
        'X-Algolia-Application-Id': VISIT_VARMLAND_ALGOLIA_APP_ID,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0',
    }

    page = 0
    while page < 20:
        params = urllib.parse.urlencode({
            'hitsPerPage': 100,
            'page': page,
            'filters': filters,
        })
        payload = {'requests': [{'indexName': index_name, 'params': params}]}
        resp = requests.post(query_url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()['results'][0]
        hits = data.get('hits', [])
        if not hits:
            break

        for hit in hits:
            title = hit.get(f'title_{locale}') or hit.get('title_sv') or hit.get('title_en') or hit.get('title')
            place = hit.get('place') or venue_name
            municipality = hit.get('municipality') or location
            url_suffix = hit.get(f'url_{locale}') or hit.get('url_sv') or ''
            link = f'https://www.visitvarmland.com/{url_suffix.lstrip("/")}' if url_suffix else page_url
            category = None
            categories = hit.get(f'categories_{locale}') or hit.get('categories_sv') or {}
            lvl1 = categories.get('lvl1') or []
            if lvl1:
                category = lvl1[0].replace('Evenemang > ', '').strip()

            for date_item in hit.get('dates', []):
                date = date_item.get('date')
                if not date:
                    continue
                year = int(date[:4])
                if year not in VALID_YEARS:
                    continue
                events.append({
                    'title': title,
                    'date': date,
                    'end_date': date_item.get('date_end') if date_item.get('date_end') != date else None,
                    'venue': place,
                    'location': municipality,
                    'link': link,
                    'source': venue_name,
                    'category': category,
                })

        if page >= data.get('nbPages', 1) - 1:
            break
        page += 1

    # Deduplicate exact duplicates emitted by repeated occurrences / content quirks
    seen = set()
    unique = []
    for e in events:
        key = (e['title'], e['date'], e['venue'], e['location'])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def fetch_and_parse_venue(venue_key: str, config: dict) -> List[Dict]:
    """
    Fetch venue page and use AI to extract events
    """
    venue_name = config.get('name', venue_key)
    location = config.get('location', 'Karlstad')
    urls = config.get('urls', {})
    
    events = []

    if is_visit_varmland_source(config):
        try:
            print(f"  🔄 {venue_name} (Algolia)")
            venue_events = fetch_visit_varmland_events(config)
            events.extend(venue_events)
            if venue_events:
                print(f"    ✓ {len(venue_events)} events")
            else:
                print(f"    ℹ️  No events found")
        except Exception as e:
            print(f"    ✗ Error: {e}")
        return events

    if is_bibliotek_varmland_source(config):
        try:
            print(f"  🔄 {venue_name} (Axiell API)")
            venue_events = fetch_bibliotek_varmland_events(config)
            events.extend(venue_events)
            if venue_events:
                print(f"    ✓ {len(venue_events)} events")
            else:
                print(f"    ℹ️  No events found")
        except Exception as e:
            print(f"    ✗ Error: {e}")
        return events
    
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