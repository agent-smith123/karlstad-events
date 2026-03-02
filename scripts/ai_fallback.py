#!/usr/bin/env python3
"""
AI Fallback Handler for Event Research
When automated scraping fails, this creates a request for AI agent intervention
"""

import os
import json
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
AI_REQUEST_FILE = DATA_DIR / ".ai-fetch-requested"
AI_RESULTS_FILE = DATA_DIR / "ai-fetched-events.json"
VENUES_FILE = SCRIPT_DIR / "venues.yaml"


def load_venues_needing_attention():
    """Load venues that failed automated scraping"""
    venues = []
    
    # Check for marker files or failed logs
    failed_log = DATA_DIR / "failed_scrapes.json"
    if failed_log.exists():
        with open(failed_log) as f:
            data = json.load(f)
            venues = data.get("failed", [])
    
    return venues


def create_ai_request():
    """Create a structured request for AI agent"""
    
    # Load venue config
    import yaml
    with open(VENUES_FILE) as f:
        venues = yaml.safe_load(f)
    
    # Build request
    request = {
        "timestamp": datetime.now().isoformat(),
        "request_type": "event_fetch",
        "priority_venues": [],
        "instructions": {
            "task": "Fetch current events from these venues",
            "output_format": "JSON array of events",
            "fields_required": ["title", "date", "venue", "location", "link"],
            "notes": "Use web search and browser tools to find events. Focus on upcoming events (next 30-90 days)."
        }
    }
    
    # Add priority venues (those marked as dynamic/manual)
    for tier in ['tier1_major', 'tier2_cultural']:
        for key, venue in venues.get(tier, {}).items():
            scraper_type = venue.get('scraper', {}).get('type')
            if scraper_type in ['dynamic', 'manual'] or not venue.get('active'):
                request["priority_venues"].append({
                    "name": venue['name'],
                    "location": venue.get('location', 'Karlstad'),
                    "urls": venue.get('urls', {}),
                    "type": venue.get('type', ['Evenemang'])
                })
    
    # Save request
    with open(AI_REQUEST_FILE, 'w') as f:
        json.dump(request, f, indent=2)
    
    print("🤖 AI Agent Request Created")
    print(f"   File: {AI_REQUEST_FILE}")
    print(f"   Venues needing attention: {len(request['priority_venues'])}")
    
    # Print summary for human/agent
    print("\n📋 Priority Venues to Check:")
    for v in request["priority_venues"]:
        print(f"   • {v['name']} ({v['location']})")
        if v['urls']:
            for url_type, url in v['urls'].items():
                print(f"     - {url_type}: {url}")
    
    return request


def check_ai_results():
    """Check if AI has provided results"""
    if AI_RESULTS_FILE.exists():
        with open(AI_RESULTS_FILE) as f:
            return json.load(f)
    return None


def main():
    """Entry point"""
    print("🤖 AI Fallback Handler")
    print("=" * 40)
    
    # Check if there's already an AI request pending
    if AI_REQUEST_FILE.exists():
        print("⏳ AI request already pending")
        print(f"   Check: {AI_REQUEST_FILE}")
        
        # Check for results
        results = check_ai_results()
        if results:
            print("✅ AI results found!")
            print(f"   Events fetched: {len(results.get('events', []))}")
            # Process results would go here
        else:
            print("⏳ Waiting for AI agent to complete fetch...")
    else:
        # Create new request
        create_ai_request()
        print("\n📧 The AI agent should now process this request.")
        print("   Results will be saved to:", AI_RESULTS_FILE)


if __name__ == "__main__":
    main()
