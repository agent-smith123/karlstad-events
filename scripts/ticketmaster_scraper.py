#!/usr/bin/env python3
"""
Ticketmaster Web Scraper
Scrapes events from Ticketmaster.se venue pages without requiring API key
Uses Playwright for JS-rendered content
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
CACHE_FILE = DATA_DIR / "ticketmaster_cache.json"

# Swedish months for date parsing
MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12,
    'januari': 1, 'februari': 2, 'mars': 3, 'april': 4, 'juni': 6,
    'juli': 7, 'augusti': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12
}

CURRENT_YEAR = datetime.now().year
VALID_YEARS = {CURRENT_YEAR, CURRENT_YEAR + 1}


class TicketmasterWebScraper:
    """Scrape events from Ticketmaster venue pages"""
    
    def __init__(self):
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        if CACHE_FILE.exists():
            with open(CACHE_FILE) as f:
                return json.load(f)
        return {}
    
    def _save_cache(self):
        with open(CACHE_FILE, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    def scrape_venue(self, venue_key: str, config: dict) -> List[Dict]:
        """Scrape events from a Ticketmaster venue page"""
        events = []
        urls = config.get('urls', {})
        
        # Find Ticketmaster URL
        tm_url = None
        for key, url in urls.items():
            if isinstance(url, str) and 'ticketmaster.se/venue' in url.lower():
                tm_url = url
                break
        
        if not tm_url:
            print(f"    ⚠️  No Ticketmaster URL for {config.get('name', venue_key)}")
            return events
        
        print(f"    🎫 {config.get('name', venue_key)}: {tm_url[:60]}...")
        
        # Check cache
        cache_key = f"{venue_key}_{datetime.now().strftime('%Y-%m-%d')}"
        if cache_key in self.cache:
            print(f"      ✓ Using cached data")
            return self.cache[cache_key]
        
        # Scrape with Playwright
        if HAS_PLAYWRIGHT:
            events = self._scrape_with_playwright(tm_url, config)
        else:
            events = self._scrape_with_requests(tm_url, config)
        
        # Cache results
        if events:
            self.cache[cache_key] = events
            self._save_cache()
        
        return events
    
    def _scrape_with_playwright(self, url: str, config: dict) -> List[Dict]:
        """Scrape using Playwright for JS-rendered content"""
        events = []
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Navigate to venue page
                page.goto(url, wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(2000)
                
                # Get rendered HTML
                html = page.content()
                browser.close()
                
                if not HAS_BS4:
                    return events
                
                soup = BeautifulSoup(html, 'html.parser')
                
                # Find event listings
                # Ticketmaster uses various selectors
                event_selectors = [
                    '[data-testid="event-list-item"]',
                    '.event-list-item',
                    'article[data-testid*="event"]',
                    '.event-card',
                    '[class*="EventCard"]',
                    'a[href*="/event/"]'
                ]
                
                for selector in event_selectors:
                    elements = soup.select(selector)
                    for elem in elements:
                        event = self._parse_event_element(elem, config, url)
                        if event:
                            events.append(event)
                
                # If no events found with selectors, try to find links
                if not events:
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '')
                        if '/event/' in href:
                            event = self._parse_event_link(link, config, url)
                            if event:
                                events.append(event)
                
        except Exception as e:
            print(f"      ❌ Playwright error: {e}")
        
        print(f"      ✓ Found {len(events)} events")
        return events
    
    def _scrape_with_requests(self, url: str, config: dict) -> List[Dict]:
        """Fallback scraping with requests (may not work for JS sites)"""
        events = []
        
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            
            if not HAS_BS4:
                return events
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Try to find event data in JSON-LD
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        for item in data:
                            if item.get('@type') == 'Event':
                                event = self._parse_jsonld_event(item, config)
                                if event:
                                    events.append(event)
                    elif isinstance(data, dict) and data.get('@type') == 'Event':
                        event = self._parse_jsonld_event(data, config)
                        if event:
                            events.append(event)
                except:
                    pass
            
            # Try to find event links
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if '/event/' in href:
                    event = self._parse_event_link(link, config, url)
                    if event:
                        events.append(event)
            
        except Exception as e:
            print(f"      ❌ Requests error: {e}")
        
        return events
    
    def _parse_event_element(self, elem, config: dict, base_url: str) -> Optional[Dict]:
        """Parse event from HTML element"""
        try:
            # Try to find title
            title_elem = elem.find(['h2', 'h3', 'h4']) or elem.find(class_=re.compile('title|name', re.I))
            if not title_elem:
                # Try to get title from link text
                link = elem.find('a')
                if link:
                    title_elem = link
            
            if not title_elem:
                return None
            
            title = title_elem.get_text(strip=True)
            
            if len(title) < 5:
                return None
            
            # Try to find date
            date_str = None
            
            # Look for date in element
            date_elem = elem.find('time') or elem.find(class_=re.compile('date|datum', re.I))
            if date_elem:
                if date_elem.get('datetime'):
                    date_str = date_elem.get('datetime')[:10]
                else:
                    date_str = self._parse_date_from_text(date_elem.get_text())
            
            if not date_str:
                date_str = self._parse_date_from_text(elem.get_text())
            
            if not date_str:
                return None
            
            # Find link
            link = None
            link_elem = elem.find('a', href=True)
            if link_elem:
                href = link_elem.get('href', '')
                if href.startswith('/'):
                    link = urljoin(base_url, href)
                elif href.startswith('http'):
                    link = href
            
            return {
                'title': title,
                'date': date_str,
                'venue': config.get('name', 'Unknown'),
                'location': config.get('location', 'Karlstad'),
                'link': link,
                'source': 'Ticketmaster',
                'source_type': 'web_scrape'
            }
            
        except Exception as e:
            return None
    
    def _parse_event_link(self, link_elem, config: dict, base_url: str) -> Optional[Dict]:
        """Parse event from a link element"""
        try:
            href = link_elem.get('href', '')
            text = link_elem.get_text(strip=True)
            
            if not text or len(text) < 5:
                return None
            
            # Try to extract date from URL or text
            date_str = self._parse_date_from_text(text)
            if not date_str:
                date_str = self._parse_date_from_text(href)
            
            if not date_str:
                return None
            
            link = urljoin(base_url, href) if href.startswith('/') else href
            
            return {
                'title': text,
                'date': date_str,
                'venue': config.get('name', 'Unknown'),
                'location': config.get('location', 'Karlstad'),
                'link': link,
                'source': 'Ticketmaster',
                'source_type': 'web_scrape'
            }
            
        except:
            return None
    
    def _parse_jsonld_event(self, data: dict, config: dict) -> Optional[Dict]:
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
                'link': data.get('url'),
                'source': 'Ticketmaster',
                'source_type': 'jsonld'
            }
        except:
            return None
    
    def _parse_date_from_text(self, text: str) -> Optional[str]:
        """Parse date from text"""
        # ISO format: 2026-03-15
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
            month = MONTHS.get(month_str, 1)
            year = int(match.group(3))
            return f"{year}-{month:02d}-{day:02d}"
        
        # Short format: 15 mar
        match = re.search(
            r'(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)',
            text.lower()
        )
        if match:
            day = int(match.group(1))
            month_str = match.group(2)
            month = MONTHS.get(month_str, 1)
            year = CURRENT_YEAR
            return f"{year}-{month:02d}-{day:02d}"
        
        return None


def scrape_all_ticketmaster_venues(venues_config: dict) -> List[Dict]:
    """Scrape all Ticketmaster venues"""
    scraper = TicketmasterWebScraper()
    all_events = []
    
    print("\n🎫 Ticketmaster Web Scraper")
    print("=" * 50)
    
    for tier in ['tier1_major', 'tier2_cultural', 'tier3_small', 'tier4_aggregators']:
        tier_venues = venues_config.get(tier, {})
        for venue_key, config in tier_venues.items():
            if not config.get('active', False):
                continue
            
            scraper_type = config.get('scraper', {}).get('type', 'static')
            if scraper_type not in ['ticketmaster', 'ticketmaster_html']:
                continue
            
            events = scraper.scrape_venue(venue_key, config)
            all_events.extend(events)
            
            # Be nice to servers
            time.sleep(1)
    
    # Filter valid events
    valid_events = []
    for e in all_events:
        try:
            year = int(e['date'][:4])
            if year in VALID_YEARS:
                valid_events.append(e)
        except:
            pass
    
    print(f"\n  ✅ Total Ticketmaster events: {len(valid_events)}")
    
    return valid_events


if __name__ == "__main__":
    import yaml
    
    with open(SCRIPT_DIR / "venues.yaml") as f:
        venues = yaml.safe_load(f)
    
    events = scrape_all_ticketmaster_venues(venues)
    
    print(f"\n✅ Scraped {len(events)} events from Ticketmaster")
    
    for e in events[:10]:
        print(f"  • {e['date']}: {e['title'][:50]} ({e['venue']})")