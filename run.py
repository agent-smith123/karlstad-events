#!/usr/bin/env python3
"""
Event Calendar - Simplified Flow
Uses browser tool for reliable fetching with JavaScript support
"""

import json
import yaml
import re
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

PROJECT_DIR = Path(__file__).parent
SOURCES_FILE = PROJECT_DIR / "sources.yaml"
OUTPUT_FILE = PROJECT_DIR / "assets" / "data" / "events.json"

def load_sources():
    with open(SOURCES_FILE) as f:
        return yaml.safe_load(f).get('sources', [])

def parse_date(text):
    match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if match:
        return match.group(1)
    months = {
        'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
        'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'december': 12
    }
    match = re.search(r'(\d{1,2})\s+([a-zåäö]+)', text.lower())
    if match:
        day = int(match.group(1))
        month = months.get(match.group(2)[:3], 0)
        if month:
            return f"2026-{month:02d}-{day:02d}"
    return None

def normalize_text(text):
    if not text:
        return text
    alpha = [c for c in text if c.isalpha()]
    if len(alpha) > 3 and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.8:
        words = text.lower().split()
        result = []
        for i, w in enumerate(words):
            if i > 0 and w in ['och', 'eller', 'i', 'på', 'med', 'till', 'från', 'av']:
                result.append(w)
            else:
                result.append(w.capitalize())
        return ' '.join(result)
    return text

def fetch_with_browser(url):
    """Use browser tool to fetch page with JavaScript support"""
    try:
        import subprocess
        result = subprocess.run(
            ['openclaw', 'browser', 'open', '--url', url, '--timeout', '30'],
            capture_output=True,
            text=True,
            timeout=45
        )
        return result.stdout
    except:
        return None

def fetch_source(source):
    name = source['name']
    url = source['url']
    
    print(f"\n🌐 {name}")
    
    events = []
    
    try:
        # Try regular fetch first
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        resp = session.get(url, timeout=30)
        
        if resp.status_code >= 400:
            print(f"   ⚠️ HTTP {resp.status_code}")
            return []
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # JSON-LD
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get('@type') == 'Event':
                        title = item.get('name', '')
                        date = item.get('startDate', '')[:10] if 'startDate' in item else ''
                        if title and date:
                            loc = item.get('location', {})
                            venue = loc.get('name', name) if isinstance(loc, dict) else name
                            events.append({
                                'title': normalize_text(title),
                                'date': date,
                                'venue': normalize_text(venue),
                                'location': source.get('location', 'Karlstad'),
                                'link': item.get('url', url),
                                'category': source.get('category', 'event'),
                                'source': name
                            })
            except:
                pass
        
        # Event patterns
        for elem in soup.find_all(['article', 'div', 'li'], class_=re.compile('event|evenemang|program', re.I)):
            text = elem.get_text()
            date = parse_date(text)
            if date:
                title_elem = elem.find(['h1', 'h2', 'h3', 'h4'])
                title = title_elem.get_text().strip() if title_elem else text[:100]
                link_elem = elem.find('a', href=True)
                link = link_elem['href'] if link_elem else url
                if link and not link.startswith('http'):
                    from urllib.parse import urljoin
                    link = urljoin(url, link)
                
                if len(title) > 5:
                    events.append({
                        'title': normalize_text(title[:200]),
                        'date': date,
                        'venue': normalize_text(name),
                        'location': source.get('location', 'Karlstad'),
                        'link': link,
                        'category': source.get('category', 'event'),
                        'source': name
                    })
        
        print(f"   ✓ Found {len(events)} events")
        return events
        
    except Exception as e:
        print(f"   ⚠️ {str(e)[:60]}")
        return []

def validate_event(event):
    if not event.get('title') or len(event['title']) < 3:
        return False
    if not event.get('date'):
        return False
    try:
        dt = datetime.strptime(event['date'], '%Y-%m-%d')
        if dt.year not in [2026, 2027]:
            return False
        if dt.date() < datetime.now().date():
            return False
    except:
        return False
    return True

def deduplicate(events):
    seen = set()
    unique = []
    for e in events:
        key = f"{e['date']}-{e['title'].lower()[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique

def main():
    print("=" * 60)
    print("📅 Event Calendar - Simplified Flow")
    print("=" * 60)
    
    sources = load_sources()
    print(f"\n📋 {len(sources)} sources")
    
    all_events = []
    for i, src in enumerate(sources, 1):
        print(f"\n[{i}/{len(sources)}]", end="")
        events = fetch_source(src)
        all_events.extend(events)
    
    print(f"\n\n📊 Total fetched: {len(all_events)}")
    
    valid = [e for e in all_events if validate_event(e)]
    print(f"✅ Valid: {len(valid)}")
    
    unique = deduplicate(valid)
    print(f"🔍 Unique: {len(unique)}")
    
    unique.sort(key=lambda e: e['date'])
    
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Saved {len(unique)} events")
    
    import subprocess
    subprocess.run(['hugo'], cwd=PROJECT_DIR, capture_output=True)
    subprocess.run(['surge', './public', 'karlstad-events.surge.sh'], cwd=PROJECT_DIR, capture_output=True)
    
    print(f"🚀 Published to https://karlstad-events.surge.sh")
    print("=" * 60)

if __name__ == '__main__':
    main()