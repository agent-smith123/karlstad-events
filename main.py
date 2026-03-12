#!/usr/bin/env python3
"""
Event Calendar - AI Sub-Agent Orchestrator
Uses sessions_spawn to run AI agents for each source
"""

import json
import yaml
import requests
import subprocess
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict

# Add OpenClaw path for sessions_spawn
sys.path.insert(0, str(Path.home() / '.nvm/versions/node/v24.13.1/lib/node_modules/openclaw'))

PROJECT_DIR = Path(__file__).parent
SOURCES_FILE = PROJECT_DIR / "sources.yaml"
OUTPUT_FILE = PROJECT_DIR / "assets" / "data" / "events.json"
SESSIONS_SPAWN = Path.home() / '.nvm/versions/node/v24.13.1/lib/node_modules/openclaw/bin/openclaw'

# Agent prompt for fetching events
FETCH_PROMPT = """You are an event fetching agent. Your task is to fetch events from: {url}

Source name: {name}
Category: {category}
Location: {location}

Instructions:
1. Visit the URL and extract all events
2. Handle pagination if present - go through ALL pages
3. For each event, extract: title, date (YYYY-MM-DD), venue, link
4. Only include events in 2026 or 2027
5. Normalize text - convert ALL CAPS to Title Case
6. Return events as JSON array

Use web_fetch or browser tools to access the page. If the page uses JavaScript, use playwright/browser automation.

Return ONLY valid JSON:
[
  {{"title": "...", "date": "2026-03-15", "venue": "...", "link": "..."}}
]
"""


def load_sources() -> List[Dict]:
    """Load event sources from YAML"""
    with open(SOURCES_FILE) as f:
        data = yaml.safe_load(f)
    return data.get('sources', [])


def fetch_with_ai_agent(source: Dict) -> List[Dict]:
    """Fetch events using an AI sub-agent via sessions_spawn"""
    import subprocess
    import json
    
    name = source['name']
    url = source['url']
    category = source.get('category', 'event')
    location = source.get('location', 'Karlstad')
    
    print(f"  🤖 Spawning AI agent for {name}...")
    
    # Create the prompt
    prompt = FETCH_PROMPT.format(
        url=url,
        name=name,
        category=category,
        location=location
    )
    
    # Use openclaw sessions_spawn (subagent)
    try:
        result = subprocess.run(
            ['openclaw', 'sessions', 'spawn', '--runtime', 'subagent', '--task', prompt, '--run-timeout', '120'],
            capture_output=True,
            text=True,
            timeout=180
        )
        
        output = result.stdout
        
        # Try to parse JSON from output
        # Look for JSON array in the response
        import re
        json_match = re.search(r'\[\s*\{.*\}\s*\]', output, re.DOTALL)
        if json_match:
            try:
                events = json.loads(json_match.group(0))
                for e in events:
                    e['source'] = name
                    e['category'] = category
                    e['location'] = location
                print(f"    ✓ Found {len(events)} events")
                return events
            except json.JSONDecodeError:
                pass
        
        print(f"    ⚠️ No events found or parse error")
        return []
        
    except subprocess.TimeoutExpired:
        print(f"    ⚠️ Agent timed out")
        return []
    except Exception as e:
        print(f"    ⚠️ Error: {e}")
        return []


def fetch_directly(source: Dict) -> List[Dict]:
    """Fetch events directly (fallback without AI agent)"""
    import re
    from bs4 import BeautifulSoup
    
    events = []
    url = source['url']
    name = source['name']
    
    print(f"  🌐 Fetching directly from {name}...")
    
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        
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
                            events.append({
                                'title': title,
                                'date': date,
                                'venue': name,
                                'location': source.get('location', 'Karlstad'),
                                'link': item.get('url', url),
                                'category': source.get('category', 'event'),
                                'source': name
                            })
            except:
                pass
        
        print(f"    ✓ Found {len(events)} events")
        
    except Exception as e:
        print(f"    ⚠️ Error: {e}")
    
    return events


def validate_event(event: Dict) -> bool:
    """Validate event data"""
    if not event.get('title') or len(event['title']) < 3:
        return False
    if not event.get('date'):
        return False
    try:
        datetime.strptime(event['date'], '%Y-%m-%d')
    except:
        return False
    event_date = datetime.strptime(event['date'], '%Y-%m-%d').date()
    if event_date < datetime.now().date():
        return False
    if int(event['date'][:4]) not in [2026, 2027]:
        return False
    return True


def normalize_event(event: Dict) -> Dict:
    """Normalize event text"""
    def to_title_case(text: str) -> str:
        if not text:
            return text
        alpha = [c for c in text if c.isalpha()]
        if len(alpha) > 3 and sum(1 for c in alpha if c.isupper()) / len(alpha) > 0.8:
            words = text.lower().split()
            result = []
            for i, w in enumerate(words):
                if i > 0 and w in ['och', 'eller', 'i', 'på', 'med', 'till', 'från', 'av', 'för']:
                    result.append(w)
                else:
                    result.append(w.capitalize())
            return ' '.join(result)
        return text
    
    event['title'] = to_title_case(event.get('title', ''))
    event['venue'] = to_title_case(event.get('venue', ''))
    return event


def deduplicate(events: List[Dict]) -> List[Dict]:
    """Remove duplicates"""
    seen = set()
    unique = []
    for e in events:
        key = f"{e['date']}-{e['title'].lower()[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def main():
    print("=" * 50)
    print("📅 Event Calendar - AI Sub-Agent Orchestrator")
    print("=" * 50)
    
    # Load sources
    print("\n📋 Loading sources...")
    sources = load_sources()
    print(f"   Found {len(sources)} sources")
    
    # Fetch events (try AI agent first, fallback to direct)
    print("\n🔄 Fetching events...")
    all_events = []
    
    for i, source in enumerate(sources):
        print(f"\n[{i+1}/{len(sources)}] {source['name']}")
        
        # Try direct fetch first (more reliable)
        events = fetch_directly(source)
        
        # If no events found, could try AI agent
        # events = fetch_with_ai_agent(source) if not events else events
        
        all_events.extend(events)
    
    print(f"\n📊 Total fetched: {len(all_events)}")
    
    # Validate
    print("\n✅ Validating...")
    valid = [e for e in all_events if validate_event(e)]
    print(f"   Valid: {len(valid)}")
    
    # Normalize
    print("\n🔧 Normalizing text...")
    valid = [normalize_event(e) for e in valid]
    
    # Deduplicate
    print("\n🔍 Deduplicating...")
    unique = deduplicate(valid)
    print(f"   Unique: {len(unique)}")
    
    # Sort
    unique.sort(key=lambda e: e['date'])
    
    # Save
    print(f"\n💾 Saving to {OUTPUT_FILE}...")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    
    # Build Hugo
    print("\n🏗️ Building Hugo...")
    subprocess.run(['hugo'], cwd=PROJECT_DIR, capture_output=True)
    
    # Deploy
    print("\n🚀 Deploying...")
    result = subprocess.run(
        ['surge', './public', 'karlstad-events.surge.sh'],
        cwd=PROJECT_DIR,
        capture_output=True
    )
    
    if result.returncode == 0:
        print(f"\n✅ Published {len(unique)} events to https://karlstad-events.surge.sh")
    else:
        print(f"\n⚠️ Deploy issue: {result.stderr.decode()}")
    
    return unique


if __name__ == '__main__':
    main()