#!/usr/bin/env python3
"""
Event Calendar - AI Agent Orchestrator
Uses OpenClaw sessions_spawn to run AI agents for each source
"""

import json
import yaml
import subprocess
from pathlib import Path
from datetime import datetime
import time

PROJECT_DIR = Path(__file__).parent
SOURCES_FILE = PROJECT_DIR / "sources.yaml"
OUTPUT_FILE = PROJECT_DIR / "assets" / "data" / "events.json"

AGENT_PROMPT = """You are an expert event scraper. Fetch ALL events from: {url}

Source: {name}
Category: {category}
Location: {location}

INSTRUCTIONS:
1. Visit the URL using browser or web_fetch tool
2. If pagination exists, navigate through ALL pages
3. For EACH event, extract:
   - title (event name)
   - date (YYYY-MM-DD format)
   - venue (where it takes place)
   - link (URL to event details)
4. Only include events from 2026 or 2027
5. Skip past events
6. Handle infinite scroll / "load more" buttons

DATA QUALITY:
- Convert ALL CAPS to Title Case
- Ensure valid ISO dates
- Include full URLs

Return ONLY JSON array:
[
  {{"title": "Event Name", "date": "2026-03-15", "venue": "Venue", "link": "https://..."}},
  ...
]

If no events found, return: []

Start by visiting the URL."""


def load_sources():
    with open(SOURCES_FILE) as f:
        return yaml.safe_load(f).get('sources', [])


def spawn_agent(source):
    """Spawn AI sub-agent to fetch events from a source"""
    name = source['name']
    url = source['url']
    
    print(f"\n🤖 [{source['index']}/{source['total']}] {name}")
    print(f"   URL: {url[:60]}...")
    
    task = AGENT_PROMPT.format(
        url=url,
        name=name,
        category=source.get('category', 'event'),
        location=source.get('location', 'Karlstad')
    )
    
    try:
        result = subprocess.run(
            [
                'openclaw', 'sessions', 'spawn',
                '--runtime', 'subagent',
                '--task', task,
                '--run-timeout', '180',
                '--mode', 'run'
            ],
            capture_output=True,
            text=True,
            timeout=200
        )
        
        output = result.stdout + result.stderr
        
        # Extract JSON array from output
        import re
        json_match = re.search(r'\[[\s\S]*?\]', output)
        if json_match:
            try:
                events = json.loads(json_match.group(0))
                for e in events:
                    e['source'] = name
                    e['category'] = source.get('category', 'event')
                    e['location'] = source.get('location', 'Karlstad')
                print(f"   ✓ Found {len(events)} events")
                return events
            except json.JSONDecodeError:
                print(f"   ⚠️ JSON parse error")
                return []
        else:
            print(f"   ⚠️ No events found")
            return []
            
    except subprocess.TimeoutExpired:
        print(f"   ⚠️ Timed out")
        return []
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
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


def normalize_event(event):
    event['title'] = normalize_text(event.get('title', ''))
    event['venue'] = normalize_text(event.get('venue', ''))
    return event


def deduplicate(events):
    seen = set()
    unique = []
    for e in events:
        key = f"{e['date']}-{e['title'].lower()[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def verify_link(event):
    import requests
    link = event.get('link')
    if not link:
        return True
    try:
        resp = requests.head(link, timeout=10, allow_redirects=True)
        return resp.status_code < 400
    except:
        return False


def main():
    print("=" * 60)
    print("📅 Event Calendar - AI Agent Orchestrator")
    print("=" * 60)
    
    # Load sources
    print("\n📋 Loading sources...")
    sources = load_sources()
    print(f"   Found {len(sources)} sources")
    
    # Add index for tracking
    for i, src in enumerate(sources, 1):
        src['index'] = i
        src['total'] = len(sources)
    
    # Fetch events from each source using AI agents
    print("\n🔄 Fetching events with AI agents (one by one)...")
    all_events = []
    
    for source in sources:
        events = spawn_agent(source)
        all_events.extend(events)
        time.sleep(2)  # Brief pause between agents
    
    print(f"\n📊 Total fetched: {len(all_events)} events")
    
    # Validate
    print("\n✅ Validating events...")
    valid = [e for e in all_events if validate_event(e)]
    print(f"   Valid: {len(valid)}")
    
    # Normalize text
    print("\n🔧 Normalizing text (converting ALL CAPS)...")
    valid = [normalize_event(e) for e in valid]
    
    # Deduplicate
    print("\n🔍 Removing duplicates...")
    unique = deduplicate(valid)
    print(f"   Unique: {len(unique)}")
    
    # Sort by date
    unique.sort(key=lambda e: e['date'])
    
    # Save
    print(f"\n💾 Saving {len(unique)} events...")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    
    # Build Hugo
    print("\n🏗️ Building Hugo site...")
    subprocess.run(['hugo'], cwd=PROJECT_DIR, capture_output=True)
    
    # Deploy to surge.sh
    print("\n🚀 Deploying to surge.sh...")
    result = subprocess.run(
        ['surge', './public', 'karlstad-events.surge.sh'],
        cwd=PROJECT_DIR,
        capture_output=True
    )
    
    if result.returncode == 0:
        print(f"\n✅ Published {len(unique)} events to https://karlstad-events.surge.sh")
    else:
        print(f"\n⚠️ Deploy issue")
    
    print("=" * 60)


if __name__ == '__main__':
    main()