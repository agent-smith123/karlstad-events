#!/usr/bin/env python3
"""
Comprehensive Event Fetcher
Uses AI to parse ALL event sources in Värmland
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

# All important event sources
EVENT_SOURCES = [
    # Karlstad kommun
    {'name': 'Karlstads kommun Evenemang', 'url': 'https://karlstad.se/uppleva-och-gora/evenemang', 'type': 'kommun'},
    {'name': 'Kultur i Karlstad', 'url': 'https://karlstad.se/uppleva-och-gora/kultur/kultur-i-karlstad---kalender', 'type': 'kultur'},
    {'name': 'Mariebergsskogen', 'url': 'https://karlstad.se/mariebergsskogen', 'type': 'park'},
    {'name': 'Biblioteken Karlstad', 'url': 'https://karlstad.se/uppleva-och-gora/bibliotek/kalender-for-biblioteken-i-karlstad', 'type': 'bibliotek'},
    
    # Markets & City Events
    {'name': 'Centrum Karlstad', 'url': 'https://www.centrumkarlstad.se/evenemang', 'type': 'marknad'},
    {'name': 'Marknadskalendern Karlstad', 'url': 'https://marknadskalendern.se/ort/karlstad', 'type': 'marknad'},
    {'name': 'Stadsevent Stora Torget', 'url': 'https://stadsevent.se/karlstad/evenemang/Stora%20torget', 'type': 'marknad'},
    
    # Regional
    {'name': 'Visit Värmland Karlstad', 'url': 'https://www.visitvarmland.com/karlstad/evenemang', 'type': 'turism'},
    {'name': 'Visit Värmland Events', 'url': 'https://www.visitvarmland.com/evenemang', 'type': 'turism'},
    
    # Aggregators
    {'name': 'Karlstad.com', 'url': 'https://www.karlstad.com/evenemang', 'type': 'aggregator'},
]


def search_brave_api(query: str, count: int = 10) -> List[Dict]:
    """Search using Brave API"""
    api_key = os.getenv('BRAVE_API_KEY')
    if not api_key:
        import json
        config_path = Path.home() / '.openclaw' / 'openclaw.json'
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                api_key = config.get('tools', {}).get('web', {}).get('search', {}).get('apiKey', '')
    
    if not api_key:
        return []
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key
    }
    params = {
        "q": query,
        "count": count,
        "freshness": "py",
        "country": "SE",
        "search_lang": "sv"
    }
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get('web', {}).get('results', [])
    except:
        return []


def parse_date(text: str, year: int = None) -> Optional[str]:
    """Parse date from Swedish text"""
    if not year:
        year = datetime.now().year
    
    months = {
        'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
        'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
        'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12
    }
    
    # ISO format
    iso_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if iso_match:
        return iso_match.group(0)
    
    # Swedish: "15 mars 2026" or "15 mars"
    swe_match = re.search(r'(\d{1,2})\s+([a-zåäö]+)(?:\s+(\d{4}))?', text.lower())
    if swe_match:
        day = int(swe_match.group(1))
        month_name = swe_match.group(2)[:3]
        found_year = int(swe_match.group(3)) if swe_match.group(3) else year
        
        if month_name in months:
            return f"{found_year}-{months[month_name]:02d}-{day:02d}"
    
    # Date range: "23–28 juni 2026"
    range_match = re.search(r'(\d{1,2})\s*[–-]\s*(\d{1,2})\s+([a-zåäö]+)(?:\s+(\d{4}))?', text.lower())
    if range_match:
        start_day = int(range_match.group(1))
        end_day = int(range_match.group(2))
        month_name = range_match.group(3)[:3]
        found_year = int(range_match.group(4)) if range_match.group(4) else year
        
        if month_name in months:
            return f"{found_year}-{months[month_name]:02d}-{start_day:02d}"
    
    return None


def parse_end_date(text: str, start_date: str) -> Optional[str]:
    """Parse end date for multi-day events"""
    months = {
        'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
        'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
    }
    
    # Date range: "23–28 juni 2026"
    range_match = re.search(r'(\d{1,2})\s*[–-]\s*(\d{1,2})\s+([a-zåäö]+)(?:\s+(\d{4}))?', text.lower())
    if range_match:
        end_day = int(range_match.group(2))
        month_name = range_match.group(3)[:3]
        year = int(range_match.group(4)) if range_match.group(4) else int(start_date[:4])
        
        if month_name in months:
            return f"{year}-{months[month_name]:02d}-{end_day:02d}"
    
    return None


def extract_events_from_html(html: str, source_name: str, source_url: str, source_type: str) -> List[Dict]:
    """Extract events from HTML using AI-like pattern matching"""
    events = []
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try JSON-LD first
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') == 'Event':
                        title = item.get('name', '')
                        date = item.get('startDate', '')[:10] if 'startDate' in item else ''
                        end_date = item.get('endDate', '')[:10] if 'endDate' in item else None
                        
                        if title and date:
                            location = item.get('location', {})
                            venue = location.get('name', source_name) if isinstance(location, dict) else source_name
                            
                            events.append({
                                'title': title,
                                'date': date,
                                'end_date': end_date if end_date and end_date != date else None,
                                'venue': venue,
                                'location': 'Karlstad',
                                'link': item.get('url', source_url),
                                'category': source_type,
                                'source': source_name
                            })
        except:
            pass
    
    # Look for event listings
    event_selectors = [
        ('article', ['event', 'evenemang', 'program']),
        ('div', ['event', 'evenemang', 'program', 'kalender', 'activity']),
        ('li', ['event', 'evenemang', 'program']),
        ('a', ['event', 'evenemang']),
    ]
    
    for tag, classes in event_selectors:
        for cls in classes:
            elements = soup.find_all(tag, class_=re.compile(cls, re.I))
            for elem in elements:
                text = elem.get_text()
                date = parse_date(text)
                
                if date:
                    # Find title
                    title_elem = elem.find(['h1', 'h2', 'h3', 'h4', 'strong', 'b'])
                    title = title_elem.get_text().strip() if title_elem else text[:100]
                    
                    # Find link
                    link_elem = elem.find('a', href=True)
                    link = link_elem['href'] if link_elem else source_url
                    if link and not link.startswith('http'):
                        from urllib.parse import urljoin
                        link = urljoin(source_url, link)
                    
                    # Clean title
                    title = re.sub(r'\s+', ' ', title).strip()
                    
                    if len(title) > 5 and date:
                        events.append({
                            'title': title[:200],
                            'date': date,
                            'end_date': parse_end_date(text, date),
                            'venue': source_name,
                            'location': 'Karlstad',
                            'link': link,
                            'category': source_type,
                            'source': source_name
                        })
    
    return events


def fetch_from_source(source: Dict) -> List[Dict]:
    """Fetch events from a single source"""
    events = []
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'sv-SE,sv;q=0.9,en;q=0.8'
        })
        
        resp = session.get(source['url'], timeout=20)
        resp.raise_for_status()
        
        events = extract_events_from_html(resp.text, source['name'], source['url'], source['type'])
        
    except Exception as e:
        print(f"  ⚠️ {source['name']}: {e}")
    
    return events


def search_for_events() -> List[Dict]:
    """Search for events using web search"""
    events = []
    seen_titles = set()
    
    queries = [
        # Markets
        'marknad Karlstad 2026',
        'loppis Karlstad Värmland 2026',
        'julmarknad Karlstad 2026',
        'matmarknad Karlstad 2026',
        
        # Exhibitions
        'utställning Karlstad museum 2026',
        'konstutställning Värmland 2026',
        
        # Lectures & Seminars
        'föreläsning Karlstad bibliotek 2026',
        'seminarium Värmland universitet 2026',
        
        # Festivals
        'festival Karlstad 2026',
        'konsert Karlstad 2026',
        
        # Special events
        'SM-veckan Karlstad 2026',
        'International Food Festival Karlstad',
        'midsommar Karlstad 2026',
    ]
    
    for query in queries:
        print(f"  🔍 {query}")
        results = search_brave_api(query, count=10)
        
        for result in results:
            title = result.get('title', '')
            description = result.get('description', '')
            url = result.get('url', '')
            
            # Skip non-events
            skip = ['wikipedia', 'instagram', 'facebook.com/', 'twitter.com', 'linkedin.com']
            if any(s in url.lower() for s in skip):
                continue
            
            full_text = f"{title} {description}"
            
            # Must be in Värmland
            varmland = ['karlstad', 'värmland', 'arvika', 'kristinehamn', 'säffle', 'sunne', 'filipstad', 'torsby', 'hagfors', 'kil', 'grums', 'hammarö', 'forshaga', 'molkom', 'deje', 'skoghall', 'vålberg', 'väse', 'skattkärr']
            if not any(loc in full_text.lower() or loc in url.lower() for loc in varmland):
                continue
            
            date = parse_date(full_text)
            if not date:
                continue
            
            # Check future
            try:
                event_date = datetime.strptime(date, '%Y-%m-%d')
                if event_date.date() < datetime.now().date():
                    continue
            except:
                continue
            
            title_key = title.lower()[:40]
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            
            # Determine category
            category = 'evenemang'
            full_lower = full_text.lower()
            if 'marknad' in full_lower or 'loppis' in full_lower:
                category = 'marknad'
            elif 'utställning' in full_lower or 'konst' in full_lower:
                category = 'utställning'
            elif 'föreläsning' in full_lower or 'seminarium' in full_lower:
                category = 'föreläsning'
            elif 'konsert' in full_lower or 'musik' in full_lower:
                category = 'konsert'
            elif 'festival' in full_lower:
                category = 'festival'
            elif 'sport' in full_lower or 'idrott' in full_lower or 'sm-' in full_lower:
                category = 'sport'
            
            events.append({
                'title': title[:200],
                'date': date,
                'end_date': parse_end_date(full_text, date),
                'venue': 'Karlstad',
                'location': 'Karlstad',
                'link': url,
                'category': category,
                'source': 'Web Search'
            })
            print(f"    ✓ {date}: {title[:50]}")
    
    return events


def main():
    """Main function"""
    print("🎨 Comprehensive Event Fetcher")
    print("=" * 50)
    
    all_events = []
    
    # 1. Fetch from all sources
    print("\n📡 Phase 1: Fetching from event sources")
    for source in EVENT_SOURCES:
        print(f"  🌐 {source['name']}...")
        events = fetch_from_source(source)
        all_events.extend(events)
        if events:
            print(f"    ✓ {len(events)} events")
    
    # 2. Search for events
    print("\n🔍 Phase 2: Web search for events")
    search_events = search_for_events()
    all_events.extend(search_events)
    
    # 3. Deduplicate
    seen = set()
    unique_events = []
    for event in all_events:
        key = f"{event['date']}-{event['title'][:30].lower()}"
        if key not in seen:
            seen.add(key)
            unique_events.append(event)
    
    print(f"\n✅ Total unique events: {len(unique_events)}")
    
    # 4. Save
    output_file = DATA_DIR / 'comprehensive_events.json'
    DATA_DIR.mkdir(exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(unique_events, f, indent=2, ensure_ascii=False)
    print(f"📁 Saved to {output_file}")
    
    # 5. Merge with existing
    events_json = ASSETS_DIR / 'events.json'
    if events_json.exists():
        with open(events_json) as f:
            existing = json.load(f)
        
        existing_keys = {f"{e['date']}-{e['title'][:30].lower()}" for e in existing}
        added = 0
        for event in unique_events:
            key = f"{event['date']}-{event['title'][:30].lower()}"
            if key not in existing_keys:
                existing.append(event)
                added += 1
        
        with open(events_json, 'w') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        
        print(f"📊 Added {added} new events. Total: {len(existing)}")
    
    return unique_events


if __name__ == '__main__':
    main()