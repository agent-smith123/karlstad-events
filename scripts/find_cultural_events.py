#!/usr/bin/env python3
"""
Search for specific event types in Karlstad
Finds exhibitions, markets, seminars, and lectures
"""

import os
import json
import requests
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"

def search_events(query: str, count: int = 10) -> list:
    """Search for events using Brave Search API"""
    api_key = os.getenv('BRAVE_API_KEY')
    if not api_key:
        print("⚠️ No BRAVE_API_KEY set")
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


def find_cultural_events():
    """Find exhibitions, markets, seminars, lectures in Karlstad"""
    
    queries = [
        # Exhibitions
        'utställning Karlstad 2026',
        'konstutställning Värmland 2026',
        'museer Karlstad evenemang 2026',
        
        # Markets
        'marknad Karlstad 2026',
        'loppis Värmland 2026',
        'julmarknad Karlstad 2026',
        
        # Seminars & Lectures
        'föreläsning Karlstad 2026',
        'seminarium Värmland 2026',
        'kulturprogram bibliotek Karlstad 2026',
        
        # Specific venues
        'Värmlands Museum utställning 2026',
        'Sandgrund Lars Lerin program 2026',
        'Kristinehamns Konstmuseum evenemang 2026',
        'Stadsbiblioteket Karlstad föreläsning 2026',
    ]
    
    all_results = []
    for query in queries:
        print(f"Searching: {query}")
        results = search_events(query, count=5)
        for r in results:
            all_results.append({
                'title': r.get('title', ''),
                'url': r.get('url', ''),
                'description': r.get('description', ''),
                'query': query
            })
    
    # Save results
    output_file = DATA_DIR / 'cultural_events_search.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\nFound {len(all_results)} results")
    print(f"Saved to {output_file}")
    
    return all_results


if __name__ == '__main__':
    DATA_DIR.mkdir(exist_ok=True)
    find_cultural_events()