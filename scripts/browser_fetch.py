#!/usr/bin/env python3
"""
Browser Automation Event Fetcher - Improved
Uses Playwright to fetch events from JavaScript-heavy sites
"""

import json
import re
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

PROJECT_DIR = Path(__file__).parent.parent
OUTPUT_FILE = PROJECT_DIR / "assets" / "data" / "events.json"

def parse_swedish_date(date_str):
    """Parse Swedish date format like '06 mar' or '13 apr'"""
    if not date_str:
        return None
    
    months = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12
    }
    
    # Try "06 mar" format
    match = re.search(r'(\d{1,2})\s+([a-z]{3})', date_str.lower())
    if match:
        day = int(match.group(1))
        month = months.get(match.group(2))
        if month:
            return f"2026-{month:02d}-{day:02d}"
    
    # Try ISO format
    match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if match:
        return match.group(1)
    
    return None

def normalize_text(text):
    """Convert ALL CAPS to Title Case"""
    if not text:
        return text
    text = ' '.join(text.split())  # Clean whitespace
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
    return text.strip()

def extract_nöjesfabriken(html, url):
    """Extract events from Nöjesfabriken structure"""
    soup = BeautifulSoup(html, 'html.parser')
    events = []
    
    # Look for event blocks
    for div in soup.find_all('div', class_=re.compile('event|evenemang', re.I)):
        text = div.get_text(separator=' ', strip=True)
        
        # Look for date pattern like "06 mar"
        date_match = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)', text.lower())
        if date_match:
            months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
                     'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12}
            day = int(date_match.group(1))
            month = months.get(date_match.group(2))
            if month:
                date = f"2026-{month:02d}-{day:02d}"
                
                # Look for title (usually after date)
                title_match = re.search(r'(?:\d{1,2}\s+(?:jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec))\s*\n*\s*([A-Z][^\n]+)', text, re.I)
                title = title_match.group(1).strip() if title_match else text[:100]
                
                # Look for venue
                venue_match = re.search(r'(Sundstaaulan|Nöjesfabriken|Karlstad)', text, re.I)
                venue = venue_match.group(1) if venue_match else 'Nöjesfabriken'
                
                if len(title) > 3 and len(title) < 150:
                    events.append({
                        'title': normalize_text(title),
                        'date': date,
                        'venue': normalize_text(venue),
                        'location': 'Karlstad',
                        'link': url,
                        'category': 'concert',
                        'source': 'Nöjesfabriken'
                    })
    
    return events

def extract_scalateatern(html, url):
    """Extract events from Scalateatern structure"""
    soup = BeautifulSoup(html, 'html.parser')
    events = []
    
    for elem in soup.find_all(['article', 'div'], class_=re.compile('event|show|performance', re.I)):
        text = elem.get_text(separator=' ', strip=True)
        
        date_match = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)', text.lower())
        if date_match:
            months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
                     'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12}
            day = int(date_match.group(1))
            month = months.get(date_match.group(2))
            if month:
                date = f"2026-{month:02d}-{day:02d}"
                
                title = text[:100].strip()
                if len(title) > 3:
                    events.append({
                        'title': normalize_text(title),
                        'date': date,
                        'venue': 'Scalateatern',
                        'location': 'Karlstad',
                        'link': url,
                        'category': 'theater',
                        'source': 'Scalateatern'
                    })
    
    return events

def fetch_with_playwright(url, name, extractor):
    """Fetch events using Playwright"""
    print(f"\n🌐 {name}")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle', timeout=30000)
            html = page.content()
            browser.close()
            
            events = extractor(html, url)
            print(f"   ✓ Found {len(events)} events")
            return events
            
    except Exception as e:
        print(f"   ⚠️ {str(e)[:50]}")
        return []

def main():
    print("=" * 60)
    print("📅 Browser Automation Event Fetcher")
    print("=" * 60)
    
    # Sites with custom extractors
    sites = [
        {"name": "Nöjesfabriken", "url": "https://www.nojesfabriken.se/nojeskalendern/", "extractor": extract_nöjesfabriken},
        {"name": "Scalateatern", "url": "https://www.scalateatern.se/forestillningar/", "extractor": extract_scalateatern},
    ]
    
    all_events = []
    for site in sites:
        events = fetch_with_playwright(site['url'], site['name'], site['extractor'])
        all_events.extend(events)
    
    print(f"\n📊 Browser fetched: {len(all_events)}")
    
    # Load existing
    try:
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)
    except:
        existing = []
    
    print(f"   Existing: {len(existing)}")
    
    # Merge and dedupe
    seen = set()
    unique = []
    for e in existing + all_events:
        key = f"{e['date']}-{e['title'].lower()[:30]}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    
    unique.sort(key=lambda x: x.get('date', ''))
    print(f"🔍 Total: {len(unique)}")
    
    # Save
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)
    
    # Build & deploy
    import subprocess
    subprocess.run(['hugo'], cwd=PROJECT_DIR, capture_output=True)
    subprocess.run(['surge', './public', 'karlstad-events.surge.sh'], cwd=PROJECT_DIR, capture_output=True)
    
    print(f"✅ Published {len(unique)} events!")

if __name__ == '__main__':
    main()