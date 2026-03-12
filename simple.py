#!/usr/bin/env python3
"""
Simplified Event Calendar Orchestrator
Processes sources one by one using AI tools
"""

import json
import yaml
import subprocess
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
SOURCES_FILE = PROJECT_DIR / "sources.yaml"
OUTPUT_FILE = PROJECT_DIR / "assets" / "data" / "events.json"

def load_sources():
    with open(SOURCES_FILE) as f:
        return yaml.safe_load(f).get('sources', [])

def fetch_source(name, url, category, location):
    """Fetch events from a single source using AI"""
    print(f"\n🌐 {name}")
    
    # Use web_fetch to get the page
    try:
        result = subprocess.run(
            ['web_fetch', url],
            capture_output=True,
            text=True,
            timeout=30
        )
        content = result.stdout
        
        # Simple extraction - look for date patterns and titles
        import re
        events = []
        
        # Look for dates in format YYYY-MM-DD
        dates = re.findall(r'(\d{4}-\d{2}-\d{2})', content)
        
        # Look for event titles (h1, h2, h3 tags)
        titles = re.findall(r'<h[123][^>]*>([^<]+)</h[123]>', content)
        
        for i, date in enumerate(dates[:10]):  # Limit to first 10
            if i < len(titles):
                title = titles[i].strip()
                if len(title) > 5:
                    events.append({
                        'title': title,
                        'date': date,
                        'venue': name,
                        'location': location,
                        'link': url,
                        'category': category,
                        'source': name
                    })
        
        print(f"   ✓ Found {len(events)} events")
        return events
        
    except Exception as e:
        print(f"   ⚠️ Error: {e}")
        return []

def main():
    print("=" * 50)
    print("📅 Event Calendar - Simplified")
    print("=" * 50)
    
    sources = load_sources()
    print(f"\n📋 {len(sources)} sources")
    
    all_events = []
    for i, src in enumerate(sources, 1):
        print(f"\n[{i}/{len(sources)}] {src['name']}")
        events = fetch_source(src['name'], src['url'], src.get('category'), src.get('location'))
        all_events.extend(events)
    
    print(f"\n📊 Total: {len(all_events)} events")
    
    # Save
    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_events, f, indent=2)
    
    # Build & deploy
    subprocess.run(['hugo'], cwd=PROJECT_DIR, capture_output=True)
    subprocess.run(['surge', './public', 'karlstad-events.surge.sh'], cwd=PROJECT_DIR, capture_output=True)
    
    print(f"✅ Published {len(all_events)} events")

if __name__ == '__main__':
    main()